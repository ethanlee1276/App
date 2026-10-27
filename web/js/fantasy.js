/* THE FANTASY ROOM — loaded the first time the Fantasy page opens (app.js
   renderFantasy, 2026-10-24). A classic script like app.js: it shares the
   page's globals (escapeHtml, icon, state, paidFetch, the team tables …),
   and its renderFantasy replaces app.js's loader of the same name. Every
   declaration here was moved whole out of app.js, in order, with its own
   comments: nothing outside the Fantasy room calls any of it (the split was
   computed from TypeScript's own reading of the file, not by hand). */
const pctRoundZ = (x) => `${Math.round((x || 0) * 100)}%`;          // a missing value reads 0%

/* ============================================================
   Fantasy Football — usage trends, buy-low/sell-high, game scripts
   ============================================================ */
async function renderFantasy() {
  const host = document.getElementById("fantasy-body");
  if (!host) return;
  let d = null, fantasyFailed = false;
  try {
    // The injury board rides along so every roster surface can tag a
    // designation — missing is fine, the tags just come back empty.
    // paidFetch, not fetch: `draft_kit`, `ranks`, `buy_sell` and
    // `scripts` are stripped from the copy Caddy serves off disk
    // (gate.PAID_KEYS_BY_FILE), so the static file hands a SUBSCRIBER a
    // board with no draft kit and no game scripts. The entitled copy
    // lives behind /api/board. Same fix as the UFC card and the
    // prediction-market record before it — the third time this exact
    // shape of bug has been shipped, which is why paidFetch exists.
    // This week's file rides along too (engine/fantasyweek): the room
    // that draws it and the dossier that reads his line out of it.
    const [res, , week] = await Promise.all([
      paidFetch("fantasy.json"), loadInjuryBoard(), ffWeekLoad(), loadFantasyWeek()]);
    _ffWeek = week;
    if (res.ok) { d = await res.json(); _lastGood.set("fantasy", Date.now()); }
    else fantasyFailed = res.status !== 404;
  } catch (e) { fantasyFailed = true; }
  if (!d || !d.season) {
    /* YOUR LEAGUE IS NOT DOWNSTREAM OF OUR USAGE FEED.
       This used to return here, which took the Around-the-league tab
       with it — and that tab was, at the time, the only place a league
       could be linked. So an empty or failed usage build meant nobody
       could link a league AT ALL, including in the offseason, which is
       exactly when people are drafting and most want to.

       The forms have since moved to the Account page, which settles that
       for good: linking no longer depends on this page rendering at all.
       What stays here is the strip that says what is linked, and the
       panels for whatever IS — Sleeper and ESPN read the user's own
       league directly, and last season's target shares have nothing to
       do with it. The empty state stays too: it is true, and it says
       what to run. */
    host.innerHTML = ff101HTML() + (fantasyFailed && !d ? outageHTML("the NFL usage board", "fantasy")
      : `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
      <div class="es-title">No NFL usage data yet</div>
      <div class="es-sub">${escapeHtml((d && d.note) || "This fills once the season’s usage rows — targets, carries, air yards, PPR points — have been ingested. Your own league below does not wait on it.")}</div></div>`) + `
      <div class="ff-sync-alone">
        <div class="section-title">Your leagues
          <span class="sub">— these read your own league and do not wait on the
          usage feed above</span></div>
        ${acctStripHTML()}
        ${ffLinkStripHTML()}
        <div id="sleeper-zone"></div><div id="league-desk"></div>
        <div id="espn-desk"></div>
      </div>`;
    ff101Bind(host);
    renderSleeperZone(d || {});
    renderEspnZone();
    return;
  }
  setStandaloneSource(`Ingested NFL ${d.season} weekly stats (nflverse)`,
                      `NFL ${d.season} · ingested history`);
  const pct = pct0Or;
  const deltaChip = (dv) => {
    if (dv == null || Math.abs(dv) < 0.03) return `<span class="chip">steady</span>`;
    return dv > 0
      ? `<span class="chip up">▲ +${(dv * 100).toFixed(0)}pt<span class="chip-suffix"> vs 4wk</span></span>`
      : `<span class="chip down">▼ ${(dv * 100).toFixed(0)}pt<span class="chip-suffix"> vs 4wk</span></span>`;
  };

  // A flex row with one greedy name column left ~600px of empty table
  // between the player and the numbers on a laptop. It is now a grid, and
  // the space that opened up carries the thing this page says matters
  // most: last week's share as a bar, with a tick where the season
  // average sits — so a riser at 42% is visibly a riser, not just three
  // percentages you have to diff in your head.
  const shareBar = (u) => {
    const scale = 0.5;                              // 50% of team volume = full bar
    const w = (v) => `${Math.min(100, ((v || 0) / scale) * 100).toFixed(1)}%`;
    const up = (u.delta || 0) > 0.03, down = (u.delta || 0) < -0.03;
    const color = up ? "var(--good)" : down ? "var(--bad)" : "var(--brand)";
    return `<span class="ff-bar" title="Last week ${pct(u.last)} of team volume · season average ${pct(u.season)}">
      <i style="width:${w(u.last)};background:${color}"></i>
      ${u.season != null ? `<b style="left:${w(u.season)}"></b>` : ""}</span>`;
  };
  const usageRow = (u) => `
    <div class="ff-row">
      <span class="ff-who" data-dossier="${escapeAttr(u.player)}">${playerAvatar(u.player, u.team, { map: nflMap(), headshot: u.headshot })}
        <span class="ff-name"><strong>${escapeHtml(u.player)}</strong>
          <span class="ff-pos">${escapeHtml(u.position)} · ${nflName(u.team)}${
            u.moved_from ? ` <b style="color:var(--warn)">← traded from ${nflName(u.moved_from)}</b>` : ""}${
            u.roster_flag ? ` <b style="color:var(--warn)">(${escapeHtml(u.roster_flag)})</b>` : ""} · ${escapeHtml(u.metric)}</span></span></span>
      ${shareBar(u)}
      <span class="ff-n" title="season average">${pct(u.season)}</span>
      <span class="ff-n dim" title="4-week average">${pct(u.l4)}</span>
      <span class="ff-n lead" title="most recent week">${pct(u.last)}</span>
      <span class="ff-n trend">${deltaChip(u.delta)}</span>
      <span class="ff-n dim rz" title="TD equity from play-by-play">${u.rz_pg != null ? `${u.rz_pg} ${escapeHtml(u.rz_label || "RZ/g")}` : "—"}</span>
      <span class="ff-n mute">${u.fp_pg} ppg</span>
    </div>`;
  // The table is ranked by how big the role change is, so the top of it is
  // the point and the tail is reference. Showing all 40 at once buried
  // every other section on the page under ~3400px of near-identical rows.
  const USAGE_SHOWN = 12;
  const allUsage = (d.usage || []).slice(0, 40);
  const usageRows = allUsage.slice(0, USAGE_SHOWN).map(usageRow).join("")
    + (allUsage.length > USAGE_SHOWN
      ? `<div id="usage-rest" class="ff-hidden">${allUsage.slice(USAGE_SHOWN).map(usageRow).join("")}</div>
         <button class="ff-more" id="usage-more" aria-expanded="false" aria-controls="usage-rest">
           Show ${allUsage.length - USAGE_SHOWN} more movers ▾</button>` : "");

  const draftKit = draftKitHTML(d.draft_kit);
  const off = d.offseason || {};
  const coachChanged = {};
  (off.coach_changes || []).forEach((c) => { coachChanged[c.team] = c.now; });

  const bs = d.buy_sell || {};
  const tradeCard = (r, kind) => {
    const buy = kind === "buy";
    return `<article class="card" style="--grade-color:${buy ? "var(--good)" : "var(--warn)"}">
      <div class="card-head">
        <div class="card-id" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { map: nflMap(), headshot: r.headshot })}
          <div><div class="player">${escapeHtml(r.player)}</div>
            <div class="subtitle">${escapeHtml(r.position)} · ${nflName(r.team)}${
              r.moved_from ? ` <b style="color:var(--warn)">← traded from ${nflName(r.moved_from)}</b>` : ""}${
              r.roster_flag ? ` <b style="color:var(--warn)">(${escapeHtml(r.roster_flag)})</b>` : ""} ·
              ${r.targets_pg} tgt/g · ${r.carries_pg} car/g</div></div>
        </div>
        <span class="pm-status" style="color:${buy ? "var(--good)" : "var(--warn)"}">${buy ? "BUY LOW" : "SELL HIGH"}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Actual</div><div class="v">${r.actual_ppg}</div></div>
        <div class="metric"><div class="k">${r.basis === "xfp" ? "xFP says" : "Volume says"}</div><div class="v">${r.expected_ppg}</div></div>
        <div class="metric primary"><div class="k">Gap</div><div class="v ${r.gap < 0 ? "pos" : "neg"}">${r.gap > 0 ? "+" : ""}${r.gap}</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">
        ${r.basis === "xfp"
          ? (buy ? "Expected points say the production is coming — his chances are worth more than he has scored from them so far."
                 : "Scoring above what his situations support — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")
          : (buy ? "Usage says the production is coming — the volume is already there."
                 : "Producing above what the opportunity supports — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")}</div>
    </article>`;
  };

  /* Rebuilt 2026-08-18 — Ethan, screenshot in hand: "organize this game
     script page better and also include team logos next to the team
     names, i think that makse it look more professional." The card used
     to spend THREE stacked prose lines on PROE, EPA and pace, each line
     naming both teams again in words — six team names per card and no
     way to compare down a column. Now the matchup header wears the
     clubs' marks and every per-team number sits in one two-row grid:
     read across for a team, down for a stat. Confidence rides the
     subtitle instead of dangling as its own footer line. */
  const gsRow = (t, implied, proe, epa, pace) => `
        <span class="gs-tm">${teamMark(t, 18, nflMap(), "nfl")}<b>${escapeHtml(t)}</b></span>
        <span class="num">${implied != null ? implied : "—"}</span>
        <span class="num">${proe != null ? `${proe >= 0 ? "+" : ""}${(proe * 100).toFixed(1)}%` : "—"}</span>
        <span class="num">${epa != null ? `${epa >= 0 ? "+" : ""}${epa.toFixed(2)}` : "—"}</span>
        <span class="num">${pace != null ? pace.toFixed(1) + "s" : "—"}</span>`;
  /* THE DEEPER DIVE, under the card that summarises it.

     Ethan, 2026-09-03: "on the game script page, we should be able too
     click on the games and see a deeper dive into the game with more
     information and shit."

     Everything here is already in the payload and most of it was never
     drawn. `home_def_epa` / `away_def_epa` in particular have been built
     by `fantasy.game_scripts` all along and shown nowhere — which is the
     half that decides a start/sit, because a good offence into a good
     defence is not the same bet as a good offence into a bad one.

     Nothing is invented. A field the build could not fill (pbp not
     ingested yet, a team with no profile) prints as a dash rather than a
     zero, because a 0.00 EPA reads as "league average" and an absent one
     is not that. */
  const gsNum = (v, dp, sign) => (v === null || v === undefined || v === "")
    ? "—" : `${sign && Number(v) > 0 ? "+" : ""}${Number(v).toFixed(dp)}`;

  /* Offence against the defence it actually faces.

     `def_epa` is the EPA a defence ALLOWS — the identical play value,
     bucketed under the defending team — so a POSITIVE def_epa is a leaky
     defence and the two numbers ADD. The first cut of this subtracted
     them, which had a good offence looking WORSE the softer the defence
     it played, exactly inverted.

     They add around the league mean, not around zero: EPA/play has no
     natural zero and `teamcontext.league_means` is the codebase's own
     answer to "+0.06 means nothing on its own". So the matchup edge is
     (offence − mean) + (defence allowed − mean). No mean on the row means
     no number here — a guessed zero point is a made-up number. */
  const gsEdge = (off, def, mean) => (off === null || off === undefined
      || def === null || def === undefined
      || mean === null || mean === undefined) ? "" :
    `<div class="gs-edge">${gsNum((Number(off) - Number(mean))
        + (Number(def) - Number(mean)), 2, true)}
       <span class="gs-edge-k">matchup vs league</span></div>`;

  /* Seconds per snap into plays, over the ~54 minutes a game spends in
     the balance. A rough number and labelled as one — it is here to say
     "this is a 130-play game, not a 118-play game", which is the part
     that moves volume. */
  const gsPlays = (a, b) => {
    if (a === null || a === undefined || b === null || b === undefined) return "";
    const pace = (Number(a) + Number(b)) / 2;
    if (!(pace > 0)) return "";
    return `<p class="gs-note">About <b>${Math.round(3240 / pace)}</b> plays at this
      pace — the volume every projection on this page divides up.</p>`;
  };

  /* Who on THIS page the script actually moves. The usage board is the
     reason somebody is reading Fantasy at all, so a game's detail that
     does not reach it is trivia. */
  const gsPlayers = (home, away) => {
    const rows = (d.usage || [])
      .filter((u) => u.team === home || u.team === away).slice(0, 6);
    if (!rows.length) return "";
    /* The same three fields the usage table above prints for these
       players — `last`, `metric`, `position` — read off the same rows,
       so a share here and a share there can never disagree. */
    return `<div class="gs-who"><div class="gs-sub">On the usage board from this game</div>
      ${rows.map((u) => `<div class="gs-who-r"><b>${escapeHtml(u.player || "")}</b>
        <span>${escapeHtml(u.position || "")}${u.position && u.team ? " · " : ""}${
          escapeHtml(u.team || "")}</span>
        <span class="gs-who-n">${u.last === null || u.last === undefined
          ? "—" : `${pct(u.last)} ${escapeHtml(u.metric || "share")}`}</span></div>`).join("")}
    </div>`;
  };

  const gsDetail = (s) => `
    <div class="gs-detail" hidden>
      <div class="gs-sub">Where the implied totals come from</div>
      <p class="gs-note">Total ${s.total} split by the spread: each side gets
        half the total, and the favourite takes half the margin.
        <b>${escapeHtml(s.away)} ${s.away_implied}</b> ·
        <b>${escapeHtml(s.home)} ${s.home_implied}</b>.</p>
      <div class="gs-sides">
        ${[[s.away, s.away_role, s.away_lean, s.away_epa, s.home_def_epa],
           [s.home, s.home_role, s.home_lean, s.home_epa, s.away_def_epa]]
          .map(([t, role, lean, off, oppDef]) => `
          <div class="gs-side">
            <div class="gs-side-h">${teamMark(t, 18, nflMap(), "nfl")}
              <b>${escapeHtml(t)}</b>${role
                ? ` <span class="gs-role">${escapeHtml(role)}</span>` : ""}</div>
            ${lean ? `<p class="gs-note">${escapeHtml(lean)}</p>` : ""}
            <div class="gs-vs"><span>offence ${gsNum(off, 2, true)}</span>
              <span class="gs-vs-k">into a defence allowing ${gsNum(oppDef, 2, true)}</span>
              ${gsEdge(off, oppDef, s.epa_mean)}</div>
          </div>`).join("")}
      </div>
      ${gsPlays(s.home_pace, s.away_pace)}
      ${gsPlayers(s.home, s.away)}
      <p class="gs-note gs-mute">EPA/play is measured from every snap of the
        ingested season. A defence’s number is what it ALLOWS, so higher is
        softer, and the matchup line adds both against the league mean${
          s.epa_mean === null || s.epa_mean === undefined
            ? "" : ` (${gsNum(s.epa_mean, 2, true)})`} — positive favours the
        offence. Pass rate over expectation and pace are last season’s
        tendencies unless the card says a coach changed.</p>
    </div>`;

  const scriptCards = (d.scripts || []).slice(0, 16).map((s) => `
    <article class="card gs-card">
      <div class="card-head" data-gs-toggle role="button" tabindex="0"
        aria-expanded="false" style="cursor:pointer">
        <div><div class="gs-match">${teamMark(s.away, 22, nflMap(), "nfl")}<b>${escapeHtml(s.away)}</b>
            <span class="gs-at">@</span>
            ${teamMark(s.home, 22, nflMap(), "nfl")}<b>${escapeHtml(s.home)}</b></div>
          <div class="subtitle">Week ${parseInt(s.week, 10) || escapeHtml(s.week)} · total ${s.total} ·
            ${escapeHtml(s.favorite)} −${Math.abs(s.spread)} · ${escapeHtml(s.confidence)} confidence</div></div>
        <span class="chip">${escapeHtml(s.archetype)}</span>
      </div>
      ${[s.home, s.away].filter((t) => coachChanged[t]).map((t) =>
        `<div class="warning" style="margin-top:8px">${iconMark("clock")}${escapeHtml(t)} has a new head coach
           (${escapeHtml(coachChanged[t])}) — last season’s tendencies (PROE included) may not carry</div>`).join("")}
      <div class="gs-grid">
        <span></span>
        <span class="gs-h" title="Points the total and spread imply for this club">Implied</span>
        <span class="gs-h" title="Pass rate over expectation — intent vs situation, the stable half of game script">PROE</span>
        <span class="gs-h" title="EPA/play: offensive efficiency measured from every snap (league avg ≈ 0)">EPA/play</span>
        <span class="gs-h" title="Seconds per snap with the game in the balance — lower is faster">Pace</span>
        ${gsRow(s.away, s.away_implied, s.away_proe, s.away_epa, s.away_pace)}
        ${gsRow(s.home, s.home_implied, s.home_proe, s.home_epa, s.home_pace)}
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">${escapeHtml(s.read)}
        <span class="gs-more">— tap for the full read ▾</span></div>
      ${gsDetail(s)}
    </article>`).join("");

  const bsCount = (bs.buy_low || []).length + (bs.sell_high || []).length;
  // Four rooms, not one 11-screen scroll. Measured in Chromium: this page
  // was 9,906px with ten section titles stacked in a single column, and
  // the usage table — the thing the page is FOR — sat below camp reports,
  // the waiver pulse, the offseason tracker and the draft kit.
  const _ffLead = `${ff101HTML()}
    <div class="stats">
      <div class="tile"><div class="k">Season</div><div class="v">${d.season}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${d.season < new Date().getFullYear()
          ? "last completed — live weekly in Sept" : "updating weekly"}</div></div>
      <div class="tile"><div class="k">Usage movers</div><div class="v">${(d.usage || []).length}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">biggest role changes tracked</div></div>
      <div class="tile"><div class="k">Trade flags</div><div class="v">${bsCount}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">outside the sustainable band</div></div>
      <div class="tile"><div class="k">Game scripts</div><div class="v">${(d.scripts || []).length}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">games with posted lines</div></div>
    </div>
`;
  const _ffUsage = `    <div class="ls-note">Shares are of TEAM volume: targets for WR/TE/QB, carries for RB.
      The delta column is the money — a riser at 42% beats a flat 60%.</div>
    <div class="section-title">Usage movers
      <span class="sub">— season vs 4-week vs last week, biggest role changes first</span></div>
    ${d.weeks_in && d.weeks_in < 4 ? `<div class="ls-note">${d.weeks_in === 1
        ? "One week in: every share is one game’s volume, so nothing here is a role yet."
        : `${d.weeks_in} weeks in: shares are ${d.weeks_in} games of volume; the four-week trend fills in from Week 4.`}</div>` : ""}
    <div class="card ff-table">
      <div class="ff-row ff-head">
        <span class="ff-who">Player</span><span class="ff-bar-h">Last week’s share</span>
        <span class="ff-n">Season</span><span class="ff-n">4-week</span><span class="ff-n">Last</span>
        <span class="ff-n trend">Trend</span><span class="ff-n rz">RZ/g</span><span class="ff-n">PPR</span>
      </div>
      ${usageRows || `${panelEmpty("No usage rows for this season yet.")}`}
    </div>
`;
  const _ffTrade = `    <div class="section-title">Buy low
      <span class="sub">— volume-expected points say the production is coming</span></div>
    <div class="cards wide">${(bs.buy_low || []).map((r) => tradeCard(r, "buy")).join("") ||
      `${panelEmpty("Nobody outside the sustainable band right now.")}`}</div>
    <div class="section-title">Sell high
      <span class="sub">— outrunning their opportunity; regression risk</span></div>
    <div class="cards wide">${(bs.sell_high || []).map((r) => tradeCard(r, "sell")).join("") ||
      `${panelEmpty("Nobody outside the sustainable band right now.")}`}</div>
`;
  const _ffScripts = `    <div class="section-title">Game scripts
      <span class="sub">— Vegas is the input: implied totals, archetypes, and confidence that
      scales with the spread</span></div>
    <div class="cards wide">${scriptCards ||
      `${panelEmpty("No upcoming NFL games with posted spreads and totals in the DB yet — fills when next season’s lines are ingested.")}`}</div>
`;
  const _ffFoot = `    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Expected points are
      fit from this season’s own data (league value per target and per carry by position) —
      volume-based, so a player can legitimately sustain a positive gap; only gaps beyond
      ~${bs.band || 1.5} PPG are flagged. Updated ${escapeHtml(formatStamp(d.generated_at))}.</p>`;
  _mockKit = d.draft_kit || {};
  _ffData = d;
  /* THE SEASON THE NUMBERS CAME FROM, when it is not the season it
     should be. The whole page is honest about being last season run
     forward; what it could not say was that "last season" on this box
     was 2021 — which is how Tom Brady reached a 2026 draft board
     (Ethan, 2026-08-24). The build stamps usage_stale when the newest
     ingested season lags the calendar; a reader deciding whether to
     trust a tier needs that fact above the tiers, not in a footer. */
  const staleU = d.usage_stale;
  const staleBanner = staleU ? `
    <div class="card" style="border-left:3px solid var(--warn);margin-bottom:14px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} <b>These numbers are
        built from the ${staleU.have} season</b> — the newest one ingested here.
        The ${staleU.expected} season’s usage has not been loaded yet, so
        treat every tier and projection as historical until it is.</p></div>` : "";
  host.innerHTML = _ffLead + staleBanner + subtabbedHTML("fantasy", [
    /* FIRST, because in season it is the question: who to start this
       week, and why. Ethan, 2026-10-22, on the board's offence, defence
       and game-script data: "make sure we wrap that into it how it
       should be." */
    ["week", "This week",
     "every player’s week in fantasy points: the matchup, the script, injuries and why",
     typeof QBWeek !== "undefined" ? `<div id="ff-week">${QBWeek.room(_ffWeek)}</div>` : ""],
    ["usage", "Usage", "who is getting the ball, and whose share is moving",
     _ffUsage],
    ["waivers", "Waivers & starts",
     "whose job just changed, and whose spot is best this week",
     waiverBoardHTML(d.waivers) + streamerHTML(d.streamers)
     + waiverPulseHTML(d.trending)],
    ["trade", "Trade targets",
     "buy low and sell high — where production and opportunity disagree",
     _ffTrade],
    ["scripts", "Game scripts",
     "what the market expects each game to look like", _ffScripts],
    ["ranks", "Rankings",
     "every source we can read without a password, and where they argue",
     rankBoardHTML(d.ranks)],
    ["days", "Calendar",
     "your own roster day by day, then the best play in the league",
     /* YOUR ROSTER FIRST, and this is the whole of Ethan's report on
        2026-09-10: "I want to be able to sync my sleeper league, then
        the calendar will show which players from MY league I should
        [start] that day like I keep saying."

        It was built on 2026-09-09 and it was not on this tab. The
        roster calendar drew inside `renderLeagueDesk`, which mounts
        into "Around the league" — under the camp report, the offseason
        moves and the draft kit — so a reader who opened Fantasy →
        Calendar got the LEAGUE-WIDE board and no sign his own existed.
        Built, unreachable, asked for again: the same shape as the
        touchdown doors this week.

        The placeholder is filled by `renderLeagueDesk` (one copy, not
        two), and carries its own sentence until then — a reader with no
        league linked must be told what to do rather than shown a gap. */
     `<div id="ffcal-mine">${ffCalMinePromptHTML()}</div>` + ffCalendarHTML(d)],
    ["mock", "Mock draft",
     "a snake draft against the room — same board the kit publishes",
     `<div id="mock-room">${mockDraftHTML()}</div>`],
    ["league", "Around the league",
     "camp, the waiver wire, the offseason and the draft kit",
     acctStripHTML() + ffLinkStripHTML()
     + `<div id="sleeper-zone"></div>`
     + `<div id="league-desk"></div>`
     + `<div id="espn-desk"></div>`
     + campHTML(d.camp)
     // The Sleeper pulse moved to the Waivers tab, beside our own signal
     // — the two are the same question asked of two different sources.
     + offseasonHTML(off) + draftKit],
  ], { index: true }) + _ffFoot;
  bindSubtabs(host);
  ff101Bind(host);
  if (typeof QBWeek !== "undefined") QBWeek.bind(host);
  _mockBind(host);
  const more = document.getElementById("usage-more");
  if (more) more.addEventListener("click", () => {
    const rest = document.getElementById("usage-rest");
    const open = rest.classList.toggle("ff-hidden") === false;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Show fewer ▴"
      : `Show ${allUsage.length - USAGE_SHOWN} more movers ▾`;
  });
  initDraftKit(d.draft_kit);
  window._ffRanks = d.ranks || null;
  initRankBoard();
  renderSleeperZone(d);
  renderEspnZone();
}

/* Camp watch — daily depth-chart snapshots diffed across the preseason.
   The chart is the coaching staff's own verdict; the DIFF is the signal:
   who won a job before Week 1 lines and fantasy drafts price it. */
function campHTML(camp) {
  if (!camp) return "";
  const slot = (r, o) => `${escapeHtml(r.position)}${o}`;
  const row = (r, tone) => `
    <div class="os-row"><span class="os-team mk-idrow" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { size: 24, map: nflMap(), headshot: r.headshot })}${escapeHtml(r.player)}
        <span class="dk-pt">${nflName(r.team)}${r.rookie ? " · rookie" : ""}</span></span>
      <span class="os-before">${slot(r, r.from_order)}</span>
      <span class="os-arrow">→</span>
      <span class="os-now" style="color:${tone}">${slot(r, r.to_order)}</span></div>`;
  const box = (title, sub, rows, empty) => `
    <article class="card os-card">
      <div class="card-head"><div><div class="player">${title}</div>
        <div class="subtitle">${sub}</div></div></div>
      <div class="os-body">${rows || panelEmpty(empty)}</div>
    </article>`;
  if ((camp.days || 0) < 2) {
    return `
      <div class="section-title">Camp watch
        <span class="sub">— depth charts snapshotted daily; movers appear as camp
        shakes them out</span></div>
      <div class="card">${panelEmpty(
        `Tracking started ${camp.tracking_since || "today"} — the first movers `
        + `show after a few days of snapshots. The depth chart is the `
        + `coaching staff\u2019s own verdict; the change over camp is the `
        + `honest preseason signal, not August box scores.`)}</div>`;
  }
  const accruing = `No chart movement in the window yet.`;
  return `
    <div class="section-title">Camp watch
      <span class="sub">— depth-chart movement ${escapeHtml(camp.from)} → ${escapeHtml(camp.to)},
      from the coaching staffs' own charts. Preseason box scores are backups vs backups;
      WHO RUNS FIRST-TEAM is the signal that prices Week 1.</span></div>
    <div class="cards wide">
      ${box("New starters", "took over a №1 job during camp — the strongest Week-1 signal here",
            (camp.new_starters || []).map((r) => row(r, "var(--good)")).join(""), accruing)}
      ${box("Risers", "climbing the chart — roles headed their way",
            (camp.risers || []).map((r) => row(r, "var(--good)")).join(""), accruing)}
      ${box("Fallers", "sliding — last season’s usage overstates their Week-1 role",
            (camp.fallers || []).map((r) => row(r, "var(--warn)")).join(""), accruing)}
    </div>`;
}

/* What the Fantasy page wears instead of the forms: what is linked, and
   the way to the page that changes it. */
/* FANTASY 101 (Ethan, 2026-10-27: "I don't know how fantasy works. I don't
   know how that shit works"). The game, the points, the week's rhythm and
   the words every tab uses, in a minute, at the top of the room. Open until
   the reader closes it; the one-line summary stays to open it again. */
const FF101_KEY = "qb_ff101";
const FF101_TERMS = [
  ["PPR", "a point per catch; half-PPR is half a point"],
  ["Flex", "a lineup spot any running back, receiver or tight end can fill; a superflex takes a quarterback too"],
  ["Bye", "the one week each NFL team has off: its players score zero"],
  ["Waivers", "claiming a player nobody owns, usually Tuesday or Wednesday night"],
  ["FAAB", "a season budget (often $100) you bid from, blind, for waiver claims"],
  ["Stream", "picking up a defense, kicker or quarterback for one good matchup, then dropping him"],
  ["Handcuff", "the backup to your starting running back, who takes the job if he is hurt"],
  ["Floor / ceiling", "a bad week and a big week for him: eight weeks in ten land between them"],
  ["Q / D / Out / IR", "questionable (usually plays), doubtful (usually doesn’t), out, injured reserve (out for weeks)"],
];
function ff101Open() {
  try { return localStorage.getItem(FF101_KEY) !== "closed"; } catch (e) { return true; }
}
function ff101HTML() {
  return `<details class="card ff101"${ff101Open() ? " open" : ""}>
    <summary><span class="ff101-k">New to fantasy?</span> How it works, in a minute</summary>
    <ol class="ff101-steps">
      <li><b>Draft a team.</b> You and about ten friends take turns picking real NFL players before the season.</li>
      <li><b>Start a lineup every week.</b> Usually a quarterback, two running backs, two receivers, a tight end, a
        flex, a kicker and a team defense (D/ST). Everyone else sits on your bench and scores nothing that week.</li>
      <li><b>Their real games are your points.</b> A point per 10 rushing or receiving yards and per 25 passing
        yards; 6 per touchdown (4 for a passing one); −2 per interception or lost fumble; in PPR leagues a point per
        catch. A defense scores for sacks, takeaways and touchdowns, and more the fewer points it allows.</li>
      <li><b>Beat one team a week.</b> The best records make the playoffs, usually weeks 15 to 17.</li>
    </ol>
    <div class="ff101-week">
      <div><b>Tue–Wed</b><span>Waivers: claim the players nobody owns</span></div>
      <div><b>Thu</b><span>The first game: its players lock at kickoff</span></div>
      <div><b>Sun</b><span>Inactives come out 90 minutes before kickoff: never start a man who sits</span></div>
      <div><b>Any day</b><span>Trades with the other managers</span></div>
    </div>
    <p class="ff101-start"><b>Start here:</b> link your league (Sleeper, ESPN or Yahoo). Then <b>This week</b> says who to
      start and why, your league desk sets your best lineup and your odds against this week’s opponent, and
      <b>Waivers &amp; starts</b> says who to pick up.</p>
    <dl class="ff101-terms">${FF101_TERMS.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl>
  </details>`;
}
function ff101Bind(host) {
  const d = host.querySelector(".ff101");
  if (d) d.addEventListener("toggle", () => {
    try { localStorage.setItem(FF101_KEY, d.open ? "open" : "closed"); } catch (e) { /* the card still works */ }
  });
}

function ffLinkStripHTML() {
  const bits = [];
  const sl = localStorage.getItem("ff_user");
  const es = localStorage.getItem(ESPN_LEAGUE_KEY);
  if (sl) bits.push(`Sleeper as <b>${escapeHtml(sl)}</b>`);
  if (es) bits.push(`ESPN league <b>${escapeHtml(es)}</b>`);
  return `<div class="acct-strip ff-link-strip${bits.length ? "" : " acct-strip-out"}">
    <span>${bits.length
      ? `Linked: ${bits.join(" · ")}.`
      : "No fantasy league linked yet — Sleeper takes a username, ESPN a "
        + "league id off your own URL. Neither asks for a password."}</span>
    <button class="btn${bits.length ? " ghost" : ""}"
      data-act="toAccount" data-arg="fantasy">${
      bits.length ? "Manage leagues" : "Link a league"}</button>
  </div>`;
}

/* ============================================================
   Offseason panel — what changed since the stats were recorded.
   Coaching changes come from the schedule file itself (each game
   row is stamped with both head coaches); rosters and rookies
   from Sleeper's players feed. All data, no news-cycle memory.
   ============================================================ */
/* The 24h waiver-wire pulse — what every Sleeper league is grabbing and
   dumping RIGHT NOW. Market attention, not our model: the two disagreeing
   is the interesting case, so it sits beside the usage boards. Always
   NFL-labeled via nflMap, whatever sport tab the visitor came from. */
/* THE WAIVER BOARD — our own signal, not a popularity count.

   `waiverPulseHTML` below shows what every Sleeper league grabbed in the
   last 24 hours, which is market attention and worth seeing. This is the
   other thing: who actually gained opportunity, measured off our usage
   rows. The two belong side by side precisely because they disagree —
   the name everybody added and the name whose share moved are often not
   the same name, and that gap is the edge.

   It never says "free agent". The site cannot see your league, so a
   claim about availability would be a guess with a number next to it.
   Role change is what we can measure, and it is the half a claim buys. */
function waiverRowHTML(r) {
  const pct = pct0Or;
  const up = (r.delta || 0) > 0;
  return `<div class="dl-row">
    <span class="dl-main" data-dossier="${escapeAttr(r.player || "")}">
      ${playerAvatar(r.player, r.team, { size: 26, map: nflMap(),
                                         headshot: r.headshot })}
      <span><strong>${escapeHtml(r.player || "")}</strong>
        <span class="dl-sub">${escapeHtml(r.position || "")} ·
          ${escapeHtml(nflName(r.team))} — ${escapeHtml(r.why || "")}</span></span></span>
    <span class="dl-num strong" style="color:${up ? "var(--good)" : "var(--text)"}"
          title="share of his team\u2019s work at that position">${pct(r.share)}</span>
  </div>`;
}

function waiverBoardHTML(w) {
  if (!w) return "";
  const sec = (title, sub, rows, empty) => `
    <div class="section-title minor">${title}
      <span class="sub">— ${sub}</span></div>
    <div class="card" style="padding:14px 16px">${
      (rows || []).length ? rows.map(waiverRowHTML).join("")
                          : panelEmpty(empty)}</div>`;
  return sec("Jobs just vacated",
             "somebody is Out, Doubtful or on IR, and his work has to go "
             + "somewhere. Ranked by the share the beneficiary ALREADY holds "
             + "— the man second in line inherits the job, not the biggest name",
             w.vacancies,
             "Nobody at a skill position is ruled out right now.")
    + sec("Roles on the rise",
          "last week\u2019s target or carry share against his prior four "
          + "weeks. Volume is far stickier week to week than the yards it "
          + "produces, which is why this reads share and not fantasy points",
          w.rising,
          "No share moved far enough this week to call it a role change.")
    + `<p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:10px">${
        escapeHtml(w.note || "")}</p>`;
}

/* THE START/SIT HALF. A different question from "who to add": the same
   player is a different play against a shootout than against a team
   that will run the clock out on him.

   WHAT THE NUMBER IS, said on the panel rather than implied: his share
   of the work times the points the market expects his offense to score,
   nudged by how much that offense throws relative to its situation. It
   is NOT a fantasy-points projection — there is no per-week points model
   here, and printing one would be the fake precision this site refuses.
   Both inputs show on every row so the ranking can be argued with. */
function streamerHTML(st) {
  const POS = ["RB", "WR", "TE"];
  const have = POS.filter((p) => ((st || {})[p] || []).length);
  if (!have.length) return "";
  const row = (r) => `<div class="dl-row">
    <span class="dl-main" data-dossier="${escapeAttr(r.player || "")}">
      ${playerAvatar(r.player, r.team, { size: 26, map: nflMap(),
                                         headshot: r.headshot })}
      <span><strong>${escapeHtml(r.player || "")}</strong>
        <span class="dl-sub">vs ${escapeHtml(nflName(r.opponent))} —
          ${escapeHtml(r.why || "")}</span></span></span>
    <span class="dl-num strong"
          title="share of his team\u2019s work times its implied total">${
      (r.score == null ? "\u2014" : r.score.toFixed(1))}</span>
  </div>`;
  return `<div class="section-title minor">Best spots this week
      <span class="sub">— opportunity times environment, by position</span></div>
    <div class="cards wide">${have.map((p) => `
      <div class="card" style="padding:14px 16px">
        <div style="font-weight:800;margin-bottom:8px">${p}</div>
        ${(st[p] || []).map(row).join("")}
      </div>`).join("")}</div>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:8px">
      The score is his share of the work multiplied by the points the
      market has his offense scoring, tilted by pass rate over
      expectation — a run-lean offense helps its back and costs its
      receivers. It is a ranking of SPOTS, not a projection of points.
      Quarterbacks are absent on purpose: every share here is targets or
      carries, which a quarterback has neither of, and streaming one is
      nearly pure team environment — a call that needs a depth chart we
      would only be guessing at.</p>`;
}

function waiverPulseHTML(t) {
  if (!t || (!(t.adds || []).length && !(t.drops || []).length)) return "";
  const fmt = (n) => n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(n);
  const col = (title, rows, tone, verb) => `
    <div class="card" style="padding:14px 16px">
      <div style="font-weight:800;margin-bottom:8px">${title}</div>
      ${rows.slice(0, 8).map((r) => `
        <div class="dl-row">
          <span class="dl-main" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
            <span><strong>${escapeHtml(r.player)}</strong>
              <span class="dl-sub">${escapeHtml(r.position || "")} · ${escapeHtml(nflName(r.team))}</span></span></span>
          <span class="dl-num strong" style="color:${tone}"
                title="${verb} in ${fmt(t.lookback_hours || 24)}h across all Sleeper leagues">${fmt(r.count)}</span>
        </div>`).join("")}
    </div>`;
  return `
    <div class="section-title">Waiver-wire pulse
      <span class="sub">— who the fantasy world grabbed and dumped in the last
      ${t.lookback_hours || 24}h (every Sleeper league). Market attention, not our model —
      check the movers against the usage boards below before following the crowd.</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:14px">
      ${(t.adds || []).length ? col(`${iconMark("hot")} Most added`, t.adds, "var(--good)", "adds") : ""}
      ${(t.drops || []).length ? col(`${iconMark("cold")} Most dropped`, t.drops, "var(--bad)", "drops") : ""}
    </div>`;
}

function offseasonHTML(off) {
  if (!off || (!off.upcoming_season && !(off.coach_changes || []).length
               && !off.rosters_live)) return "";
  const pair = (c) => `
    <div class="os-row"><span class="os-team">${teamMark(c.team, 20, nflMap(), "nfl")} ${escapeHtml(nflName(c.team))}</span>
      <span class="os-before">${escapeHtml(c.before)}</span>
      <span class="os-arrow">→</span>
      <span class="os-now">${escapeHtml(c.now)}</span></div>`;
  const move = (m) => `
    <div class="os-row"><span class="os-team">${escapeHtml(m.player)}
        <span class="dk-pt">${escapeHtml(m.position)}</span></span>
      <span class="os-before">${escapeHtml(nflName(m.from))}</span>
      <span class="os-arrow">→</span>
      <span class="os-now">${escapeHtml(nflName(m.to))}</span></div>`;
  const rookie = (r) => `
    <div class="os-row"><span class="os-team">${escapeHtml(r.player)}
        <span class="dk-pt">${escapeHtml(r.position)} · ${nflName(r.team)}</span></span>
      <span class="os-now">${escapeHtml(r.depth_pos)}${r.depth_order < 99 ? r.depth_order : ""} on depth chart</span></div>`;
  const box = (title, sub, rows, empty) => `
    <article class="card os-card">
      <div class="card-head"><div><div class="player">${title}</div>
        <div class="subtitle">${sub}</div></div></div>
      <div class="os-body">${rows || panelEmpty(empty)}</div>
    </article>`;
  const syncAge = (() => {
    if (!off.rosters_synced_at) return null;
    const ms = Date.now() - new Date(off.rosters_synced_at).getTime();
    return Number.isFinite(ms) ? ms / 36e5 : null;   // hours
  })();
  const rosterNote = !off.rosters_live ? `
    <div class="warning" style="margin-bottom:12px">${icon('warn')} Roster feed unreachable on the last
      build — team moves and rookies may be missing here until the next refresh.
      Coaching changes still current (they come from the schedule file).</div>`
    : syncAge != null && syncAge > 48 ? `
    <div class="warning" style="margin-bottom:12px">${icon('warn')} Rosters last synced
      ${escapeHtml(off.rosters_synced_at)} — over ${Math.floor(syncAge / 24)} days ago
      (the live pull has been failing and a cached copy is serving). Trades since then
      won’t show until the feed comes back.</div>`
    : off.rosters_synced_at ? `
    <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-bottom:12px">
      Rosters synced ${escapeHtml(off.rosters_synced_at)} — trades checked on every
      launch, refreshed daily.</div>` : "";
  return `
    <div class="section-title">The ${off.upcoming_season || "upcoming"} offseason
      <span class="sub">— what the league changed under last season’s numbers. Derived from
      the schedule and roster feeds on every build, not from a news list that goes stale.</span></div>
    ${rosterNote}
    <div class="cards wide">
      ${box("Coaching changes", "new head coach — last season’s tendencies may not carry",
            (off.coach_changes || []).map(pair).join(""), "No changes detected.")}
      ${box("New starting QBs", "depth-chart QB1 now vs who actually started late last season",
            (off.qb_changes || []).map(pair).join(""), off.rosters_live
              ? "No changes detected." : "Needs the roster feed.")}
      ${box("Board players who moved", "their stats came from a different offense — flagged, never re-projected",
            (off.moves || []).map(move).join(""), off.rosters_live
              ? "Nobody on the board has changed teams." : "Needs the roster feed.")}
    </div>
    ${(off.rookies || []).length ? `
      <div class="section-title">Rookies
        <span class="sub">— on rosters now, deliberately unranked: no NFL volume exists,
        and projecting them would be invention. Depth-chart slot is the honest signal.</span></div>
      <div class="card" style="padding:8px 16px">
        <div class="os-rookies">${off.rookies.map(rookie).join("")}</div>
      </div>` : ""}`;
}

/* ============================================================
   Draft kit — VORP board, tiers, and live Sleeper draft sync.
   ============================================================ */
const TIER_COLORS = ["var(--good)", "var(--cyan)", "var(--brand)",
                     "var(--warn)", "var(--text-mute)"];
const tierColor = (t) => TIER_COLORS[Math.min(t - 1, TIER_COLORS.length - 1)];

function ffRankParseImport(text) {
  // Mirrors engine/fantasy_ranks.parse_import: a leading number is
  // trusted when present (a keeper list numbered 1,2,5 means those gaps);
  // otherwise position in the file is the rank.
  const out = {};
  let seen = 0;
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim().replace(/,+$/, "");
    if (!line || line.startsWith("#")) continue;
    let cells = line.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""))
      .filter(Boolean);
    if (!cells.length) continue;
    let rank = null;
    let m = cells[0].match(/^(\d{1,3})[.)]?$/);
    if (m) { rank = +m[1]; cells = cells.slice(1); }
    else {
      m = cells[0].match(/^(\d{1,3})[.)]?\s+(.*)$/);
      if (m) { rank = +m[1]; cells = [m[2]].concat(cells.slice(1)); }
    }
    if (!cells.length) continue;
    const key = ffNorm(cells[0]);
    if (!key || ["player", "name", "rank", "overall"].includes(key)) continue;
    if (out[key] != null) continue;
    seen += 1;
    out[key] = rank == null ? seen : rank;
  }
  return out;
}

function ffRankMerge(rows, extra) {
  // `extra` is {key: {adp, imported}}. Rows the overlay knows about but
  // the build did not are APPENDED rather than dropped — a rookie taken
  // in your draft is absent from our board by construction, and losing
  // him here would hide the pick that just happened.
  const byKey = {};
  const out = (rows || []).map((r) => {
    const copy = { ...r, ranks: { ...r.ranks } };
    byKey[r.key] = copy;
    return copy;
  });
  Object.entries(extra || {}).forEach(([key, add]) => {
    let row = byKey[key];
    if (!row) {
      row = { key, player: (add.player || key), sources: 0,
              ranks: { ours: null, sleeper: null, adp: null, imported: null } };
      byKey[key] = row;
      out.push(row);
    }
    if (add.adp != null) row.ranks.adp = add.adp;
    if (add.imported != null) row.ranks.imported = add.imported;
  });
  out.forEach((r) => {
    const have = Object.values(r.ranks).filter((v) => v != null).sort((a, b) => a - b);
    r.sources = have.length;
    r.best = have.length ? have[0] : null;
    r.worst = have.length ? have[have.length - 1] : null;
    // Median, matching the engine: mean of the middle two when even.
    const n = have.length, mid = n >> 1;
    r.consensus = !n ? null
      : n % 2 ? have[mid] : Math.round(((have[mid - 1] + have[mid]) / 2) * 10) / 10;
    // A spread needs two opinions; one source disagreeing with nothing
    // is not a disagreement, and an ABSENCE is never a low opinion.
    r.spread = n >= 2 ? r.worst - r.best : null;
  });
  out.sort((a, b) => (a.consensus - b.consensus) || a.player.localeCompare(b.player));
  return out;
}

function ffRankDisagreements(rows, limit) {
  const out = [];
  for (const r of rows) {
    if (!r.spread || r.sources < 2) continue;     // 0 spread is agreement
    const per = Object.entries(r.ranks).filter(([, v]) => v != null);
    per.sort((a, b) => a[1] - b[1]);
    out.push({ ...r, high_source: per[0][0], low_source: per[per.length - 1][0] });
  }
  out.sort((a, b) => (b.spread - a.spread) || (a.consensus - b.consensus));
  return out.slice(0, limit || 12);
}

function rankBoardHTML(ranks) {
  if (!ranks) return "";
  return `
    <div class="section-title">Rankings, side by side
      <span class="sub">— every source we can read without a password, and
        where they argue. Ordered by <b>consensus</b>: the median rank
        across every source that lists him, so a player two sources love
        outranks one that only ours does.</span></div>
    <div class="card" id="rank-card">
      <p class="pre-note" id="rank-coverage"></p>
      <div id="rank-fight"></div>
      <div id="rank-table" class="rank-scroll"></div>
      <details class="rank-import">
        <summary>Add a ranking of your own ▾</summary>
        <p class="rank-help">Paste any list you can already see — a
          FantasyPros export, your league’s board, a friend’s tiers. One
          player per line, or <code>rank,player</code>. This is the honest
          route to the sites this app can’t fetch: their rankings sit
          behind a paid key or a login, and this app never takes a
          password.</p>
        <textarea id="rank-paste" rows="6" spellcheck="false"
          placeholder="1,Ja’Marr Chase&#10;2,Bijan Robinson&#10;3,Justin Jefferson"></textarea>
        <div class="rank-btns">
          <button class="btn" id="rank-apply">Apply</button>
          <button class="btn ghost" id="rank-clear">Clear</button>
          <span id="rank-import-note"></span>
        </div>
      </details>
    </div>`;
}

function renderRankBoard() {
  const host = document.getElementById("rank-table");
  if (!host || !window._ffRanks) return;
  const built = window._ffRanks.rows || [];
  const extra = {};
  // Your draft's real pick order — the only ADP that is about YOUR league.
  Object.entries(dkState.adp || {}).forEach(([k, v]) => {
    (extra[k] = extra[k] || {}).adp = v.rank;
    extra[k].player = v.player;
  });
  let imported = {};
  try { imported = ffRankParseImport(localStorage.getItem(FF_IMPORT_KEY) || ""); }
  catch (e) { imported = {}; }
  Object.entries(imported).forEach(([k, v]) => {
    (extra[k] = extra[k] || {}).imported = v;
  });
  const rows = ffRankMerge(built, extra);
  const counts = {};
  FF_RANK_SOURCES.forEach(([k]) => {
    counts[k] = rows.filter((r) => r.ranks[k] != null).length;
  });
  const cov = document.getElementById("rank-coverage");
  if (cov) {
    cov.innerHTML = FF_RANK_SOURCES.map(([k, label]) =>
      `<span class="chip ${counts[k] ? "" : "ff-dim"}">${escapeHtml(label)}: ${
        counts[k] ? counts[k] : "—"}</span>`).join(" ")
      + ` <span class="rank-help">A blank cell means that source doesn’t
          list him — not that it ranked him last. Every rookie is absent
          from our board by construction, and scoring that as rank 999
          would put the whole rookie class at the top of the arguments.</span>`;
  }
  const fight = document.getElementById("rank-fight");
  const dis = ffRankDisagreements(rows, 10);
  if (fight) {
    fight.innerHTML = !dis.length ? "" : `
      <div class="rank-fight-head">Where they disagree most</div>
      <div class="rank-fight-rows">${dis.map((r) => `
        <div class="rank-fight-row" data-dossier="${escapeAttr(r.player)}">
          ${playerAvatar(r.player, r.team || "", { size: 22, map: nflMap(), headshot: r.headshot })}<b>${escapeHtml(r.player)}</b>
          <span class="chip up">${escapeHtml(ffSrcLabel(r.high_source))} ${
            r.ranks[r.high_source]}</span>
          <span class="chip down">${escapeHtml(ffSrcLabel(r.low_source))} ${
            r.ranks[r.low_source]}</span>
          <span class="rank-spread">${r.spread} apart</span>
        </div>`).join("")}</div>`;
  }
  const cell = (v) => v == null ? `<td class="rank-none">—</td>`
    : `<td>${v}</td>`;
  /* WHY THE ORDER WAS A MYSTERY. Ethan, 2026-08-23: "I'm kinda confused
     on the order of all these players ... if they're lined up a certain
     way, we should display that."

     They were lined up a certain way — `ffRankMerge` sorts on
     `r.consensus`, the median rank across every source — and the board
     showed him no way to know it. Consensus was the SIXTH column on a
     seven-column table inside a horizontal scroller, so on a phone the
     four he could see were Player, Our board, Sleeper and Your draft:
     two columns that are not sorted, one that is empty, and no sign of
     the number doing the sorting.

     Three changes, in order of how much they help:

       * the position leads the row, so a sorted list looks sorted. It is
         the ordinal, not the consensus — consensus is a median and ties
         (four players at 4.0 in the screenshot), and a column of
         1,2,3,4 is what tells a reader at a glance that this IS an
         order;
       * a source nobody is ranked by is not a column. "Your draft" fills
         in when a draft starts and "Imported" when a list is pasted;
         before that they were two of the four columns a phone could
         show, both entirely dashes. The coverage chips above already
         report them as empty, which is where that belongs;
       * the name column is pinned, so it stays put while the numbers
         scroll instead of the reader losing track of whose row they are
         on. */
  const live = FF_RANK_SOURCES.filter(([k]) => counts[k] > 0);
  const shown = live.length ? live : FF_RANK_SOURCES.slice(0, 1);
  host.innerHTML = `<table class="rank-table"><thead><tr>
      <th class="rank-name">#  Player</th>${shown.map(([, l]) =>
        `<th>${escapeHtml(l)}</th>`).join("")}
      <th>Consensus</th><th>Spread</th></tr></thead><tbody>
      ${rows.slice(0, 200).map((r, i) => `<tr>
        <td class="rank-name" data-dossier="${escapeAttr(r.player)}"><span
          class="rank-ord">${i + 1}</span>${playerAvatar(r.player, r.team || "", { size: 20, map: nflMap(), headshot: r.headshot })}${escapeHtml(r.player)}</td>
        ${shown.map(([k]) => cell(r.ranks[k])).join("")}
        <td class="rank-cons">${r.consensus == null ? "—" : r.consensus}</td>
        ${cell(r.spread)}</tr>`).join("")}
    </tbody></table>`;
}

function initRankBoard() {
  const apply = document.getElementById("rank-apply");
  const box = document.getElementById("rank-paste");
  const note = document.getElementById("rank-import-note");
  if (!apply || !box) return;
  const saved = localStorage.getItem(FF_IMPORT_KEY) || "";
  if (saved) box.value = saved;
  const say = () => {
    const n = Object.keys(ffRankParseImport(box.value)).length;
    if (note) note.textContent = n ? `${plural(n, "player")} read` : "";
  };
  say();
  apply.addEventListener("click", () => {
    localStorage.setItem(FF_IMPORT_KEY, box.value);
    acctTouch("fantasy");
    say();
    renderRankBoard();
  });
  const clear = document.getElementById("rank-clear");
  if (clear) clear.addEventListener("click", () => {
    box.value = "";
    localStorage.removeItem(FF_IMPORT_KEY);
    acctTouch("fantasy");
    say();
    renderRankBoard();
  });
  renderRankBoard();
}
const DK_AUC_MIN = 20, DK_AUC_MAX = 1000;      // engine/auction.py's rails
/* The split bar, biggest share first, in one hue stepped by weight. A
   per-position palette was the first draft and it drew two positions in
   the same paint: --warn is defined AS --brand in the default theme.
   Four categories that are shares of one quantity read better as one
   colour anyway. */
const DK_FADE = [1, 0.74, 0.52, 0.34];

function dkAuc() {
  const n = parseInt(localStorage.getItem(DK_AUC_KEY) || "", 10);
  if (!Number.isFinite(n) || n <= 0) return 0;          // 0 = snake board
  return Math.min(DK_AUC_MAX, Math.max(DK_AUC_MIN, n));
}

/* What he is worth of THIS budget. The engine prices the sheet once, at
   its own default; every other budget is a rescale rather than a
   rebuild, and the rescale is exact rather than approximate, because
   value minus the dollar minimum is

       VORP x teams x (budget - slots) / (sum of VORP)

   in which the reader’s budget is the only term that moved. Rounding
   is redone from the published whole dollar, so a rescaled sheet can
   sit a dollar off the one the engine would have printed — a
   difference that cannot change a bid. A dollar player stays a dollar
   player at any budget: he is priced at the minimum bid, which is one
   dollar in every room. */
function dkDollars(kit, r, budget) {
  const a = (kit || {}).auction || {};
  const base = Number(r.auction || 1);
  if (!(base > 1) || !budget || !a.budget || a.budget <= a.slots) return base;
  const k = (budget - a.slots) / (a.budget - a.slots);
  return Math.max(1, Math.round(1 + (base - 1) * k));
}

const dkMoney = (n) => "$" + Number(n).toLocaleString("en-US");

/* The overall board, in whichever currency the reader is drafting in.
   In auction mode the rows are RE-SORTED by dollars: the snake order is
   VORP against a starter-level replacement, and an auction measures
   against the last man drafted instead, so the two genuinely disagree
   about who is next — a board that showed auction dollars in snake
   order would be presenting the disagreement as a typo. */
function dkBoardHTML(kit) {
  const BOARD_SHOWN = 15;
  const auc = dkAuc();
  /* A player with no last-season usage cannot be projected, so he is
     placed at the market’s own draft rank instead (engine/
     draftmarket.py). "0 gm" plus a small-sample warning is technically
     true of such a row and tells the reader nothing useful — it
     reads as a thin measurement rather than as an absent one. This says
     which it is, and whose opinion the number is. */
  const marketNote = (r) => `<span class="dk-market" title="No ${
      kit.season || "last-season"} usage to project from, so this player sits where the
      market drafts him — his points are read off our own board at that rank.
      We have no independent read on him.">${
      r.rookie ? "ROOKIE" : "NO " + (kit.season || "") + " USAGE"} · market #${
      r.market_rank}</span>`;
  const basisNote = (r) => r.source === "market" ? marketNote(r)
    : `${r.games} gm${r.small_sample ? ` ${icon("warn")} small sample` : ""}`;
  const moveNote = (r) => r.moved_from
    ? ` · <span class="dk-moved" title="Traded or signed since these stats — the volume behind this projection came in ${escapeHtml(nflName(r.moved_from))}'s offense">NEW TEAM, was ${escapeHtml(r.moved_from)}</span>`
    : r.roster_flag
      ? ` · <span class="dk-moved">${escapeHtml(r.roster_flag)}</span>` : "";
  const valueCell = (r) => auc
    ? `<span class="dl-num strong dk-money" title="what he is worth of a ${
        dkMoney(auc)} budget — $1 is the minimum bid, not an opinion">${
        dkMoney(dkDollars(kit, r, auc))}</span>`
    : `<span class="dl-num strong pos" title="points per game over the best freely-available ${escapeHtml(r.position)}">+${r.vorp}</span>`;
  const boardRow = (r, i) => `
    <div class="dl-row dk-row" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
      <span class="dl-rank">${i + 1}</span>
      <span class="dl-main dl-id">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
        <span><strong>${escapeHtml(r.player)}</strong>${injTag("nfl", r.player)}
          <span class="dl-sub">${escapeHtml(r.position)}${r.pos_rank} · ${nflName(r.team)}
            · ${basisNote(r)}${moveNote(r)}</span></span></span>
      <span class="dk-tier" style="color:${tierColor(r.tier)}">T${r.tier}</span>
      <span class="dl-num" title="projected PPR points per game">${r.proj}</span>
      ${valueCell(r)}
    </div>`;
  const rows = auc
    ? kit.board.slice().sort((a, b) => (dkDollars(kit, b, auc) - dkDollars(kit, a, auc))
                                       || ((b.vorp || 0) - (a.vorp || 0)))
    : kit.board;
  const open = !!dkState.boardOpen;
  const body = rows.slice(0, BOARD_SHOWN).map(boardRow).join("")
    + (rows.length > BOARD_SHOWN
      ? `<div id="dk-rest"${open ? "" : ` class="ff-hidden"`}>${rows.slice(BOARD_SHOWN)
           .map((r, i) => boardRow(r, i + BOARD_SHOWN)).join("")}</div>
         <button class="ff-more" id="dk-more" aria-expanded="${open}" aria-controls="dk-rest">${
           open ? "Show fewer ▴" : `Show the full board (${rows.length}) ▾`}</button>` : "");
  return `<div class="section-title">Overall board
      <span class="sub">— ${auc
        ? `ordered by what each player is worth of a ${dkMoney(auc)} budget,
           priced against the last man drafted at his position`
        : `ordered by VORP, not points: value over the best player
           still on the wire at the same position`}</span></div>
    <div class="card" style="padding:0">${body}</div>`;
}

function dkTiersHTML(kit) {
  const auc = dkAuc();
  const posCard = (pos) => {
    const rows = (kit.tiers[pos] || []).slice(0, 15);
    if (!rows.length) return "";
    let lastTier = 0;
    const body = rows.map((r) => {
      const brk = r.tier !== lastTier
        ? `<div class="dk-tierlabel" style="color:${tierColor(r.tier)}">Tier ${r.tier}</div>` : "";
      lastTier = r.tier;
      return `${brk}<div class="dk-posrow" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
        <span class="dk-pr">${r.pos_rank}</span>
        ${playerAvatar(r.player, r.team, { size: 18, map: nflMap(), headshot: r.headshot })}
        <span class="dk-pn">${escapeHtml(r.player)}${injTag("nfl", r.player)}
          <span class="dk-pt">${nflName(r.team)}${
            r.source === "market" ? ` · <span class="dk-market">mkt #${r.market_rank}</span>` : ""}</span></span>
        <span class="dk-pp${auc ? " dk-money" : ""}">${
          auc ? dkMoney(dkDollars(kit, r, auc)) : r.proj}</span>
      </div>`;
    }).join("");
    const sub = auc
      ? `replacement ≈ ${((kit.auction || {}).replacement || {})[pos] ?? "—"} PPG
         at ${escapeHtml(pos)}${((kit.auction || {}).ranks || {})[pos] ?? ""}`
      : `replacement ≈ ${kit.replacement[pos] ?? "—"} PPG`;
    return `<article class="card dk-poscard">
      <div class="card-head"><div><div class="player">${escapeHtml(pos)}</div>
        <div class="subtitle">${sub}</div></div></div>
      <div class="dk-posbody">${body}</div>
    </article>`;
  };
  return ["QB", "RB", "WR", "TE"].map(posCard).join("");
}

/* The auction panel: the switch, the budget, and — once it is on —
   where the room’s money goes. The split is the number a snake
   drafter never has to think about and an auction drafter thinks about
   first: it is one thing to know a back is worth $61 and another to
   know that backs take nearly half the money in the room. */
function dkAucBodyHTML(kit) {
  const a = (kit || {}).auction || {};
  const auc = dkAuc();
  if (!auc || !a.priced) return "";
  const k = a.budget && a.budget > a.slots
    ? (auc - a.slots) / (a.budget - a.slots) : 1;
  const split = ["QB", "RB", "WR", "TE"]
    .filter((p) => (a.by_position || {})[p])
    .sort((x, y) => a.by_position[y].share - a.by_position[x].share);
  const fade = (i) => DK_FADE[i] || DK_FADE[DK_FADE.length - 1];
  const bar = split.map((p, i) => {
    const s = a.by_position[p];
    return `<span class="dk-seg" style="flex:${Math.max(s.share, 0.01)};
      background:var(--brand);opacity:${fade(i)}" title="${
      escapeHtml(p)}: ${Math.round(s.share * 100)}% of the room’s money across ${
      s.n} players"></span>`;
  }).join("");
  const key = split.map((p, i) => `<span class="dk-key"><i
    style="background:var(--brand);opacity:${fade(i)}"></i>${escapeHtml(p)} ${
    Math.round(a.by_position[p].share * 100)}%</span>`).join("");
  const ranks = ["QB", "RB", "WR", "TE"]
    .filter((p) => (a.ranks || {})[p]).map((p) => `${p}${a.ranks[p]}`).join(" · ");
  return `
    <div class="dk-split">${bar}</div>
    <div class="dk-keys">${key}</div>
    <p class="dk-aucnote"><b>${a.priced} players priced, ${a.dollar_spots} spots
      at $1.</b> The sheet spends ${dkMoney(Math.round(a.total * k))} exactly —
      every dollar in a ${a.teams}-team room at ${dkMoney(auc)} a manager, because
      values that add up to more than the league can spend are wrong by however
      much they overshoot, and you find that out in the last three rounds.</p>
    <p class="dk-aucnote">Priced against ${escapeHtml(ranks)} — the last man
      drafted at each position, not the last starter. An auction buys every bench
      spot in the room, so the alternative to paying up is the cheapest body who
      still gets drafted, and that is a deeper baseline than the snake board’s.</p>
    <p class="dk-aucnote"><b>This is what he is worth, not what he will go
      for.</b> Rooms overpay at the top and leave dollars unspent at the bottom.
      We have never logged an auction, so there is no inflation curve here to fit
      — the gap between this sheet and the room is yours to trade against.</p>`;
}

function dkAucCardHTML(kit) {
  const auc = dkAuc();
  return `<article class="card dk-auccard">
    <div class="card-head"><div><div class="player">Auction values</div>
      <div class="subtitle">The same projections, denominated in dollars — for
        leagues that bid instead of snake.</div></div>
      <button class="btn ghost dk-aucbtn" id="dk-auc-toggle" aria-pressed="${!!auc}">${
        auc ? "Auction" : "Snake"}</button></div>
    <div class="dk-aucrow${auc ? "" : " ff-hidden"}" id="dk-auc-controls">
      <label for="dk-auc-budget">Budget per team</label>
      <input id="dk-auc-budget" type="number" inputmode="numeric"
        min="${DK_AUC_MIN}" max="${DK_AUC_MAX}" step="1" value="${auc || 200}"/>
    </div>
    <div id="dk-auc-body">${dkAucBodyHTML(kit)}</div>
  </article>`;
}

/* Re-render the three surfaces the currency touches, then put back the
   two pieces of live state that live in the DOM rather than in the
   payload: the draft-room strikeouts and the full-board disclosure. */
function dkAucApply() {
  const kit = (dkState || {}).kit;
  if (!kit) return;
  const wrap = document.getElementById("dk-boardwrap");
  const tiers = document.getElementById("dk-tiers");
  const body = document.getElementById("dk-auc-body");
  if (wrap) wrap.innerHTML = dkBoardHTML(kit);
  if (tiers) tiers.innerHTML = dkTiersHTML(kit);
  if (body) body.innerHTML = dkAucBodyHTML(kit);
  dkBindMore(kit);
  dkCrossOff();
}

function dkBindMore(kit) {
  dkBindPlan();
  const more = document.getElementById("dk-more");
  if (!more) return;
  more.addEventListener("click", () => {
    const rest = document.getElementById("dk-rest");
    const open = rest.classList.toggle("ff-hidden") === false;
    dkState.boardOpen = open;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Show fewer ▴"
      : `Show the full board (${(kit.board || []).length}) ▾`;
  });
}

/* The switch and the budget. Both write the one key and then
   re-render, so there is no in-memory mode that storage does not
   already hold: a reload — or the phone, after a sync — comes back
   in the same currency the laptop was reading. */
function initAuction(kit) {
  const btn = document.getElementById("dk-auc-toggle");
  const box = document.getElementById("dk-auc-budget");
  const controls = document.getElementById("dk-auc-controls");
  if (!btn || !box) return;
  const clamp = (n) => Math.min(DK_AUC_MAX, Math.max(DK_AUC_MIN, n));
  const write = (v) => {
    if (v) localStorage.setItem(DK_AUC_KEY, String(v));
    else localStorage.removeItem(DK_AUC_KEY);
    acctTouch("fantasy");
  };
  btn.addEventListener("click", () => {
    const on = !dkAuc();
    write(on ? clamp(parseInt(box.value, 10) || 200) : 0);
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Auction" : "Snake";
    controls.classList.toggle("ff-hidden", !on);
    dkAucApply();
  });
  /* Typing a budget re-prices the whole sheet, so it waits for the
     reader to stop typing: the "2" on the way to "250" clamps to the
     floor, and repricing it would yank the board out from under him
     between two keystrokes. */
  let t = 0;
  box.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      if (!dkAuc()) return;      // off — the box is not the source of truth
      write(clamp(parseInt(box.value, 10) || 200));
      dkAucApply();
    }, 500);
  });
}

/* The live draft’s strikeouts, re-applied. The poll owns the set and
   refreshes it every twelve seconds; a re-render inside that window
   would otherwise put every drafted player back on the board. */
function dkAssistTaken() {
  return new Set((dkPlan.order || []).map((o) => ffNorm(o.player)).filter(Boolean));
}

function dkCrossOff() {
  /* The Sleeper poll's set and the assistant's hand-marked picks, as
     one set: a player gone in either room is gone on every surface. */
  const live = (dkState || {}).taken;
  const marked = dkAssistTaken();
  if (!live && !marked.size) return;
  const taken = new Set([...(live || []), ...marked]);
  document.querySelectorAll("[data-ffp]").forEach((el) =>
    el.classList.toggle("dk-taken", taken.has(el.dataset.ffp)));
}

function draftKitHTML(kit) {
  if (!kit || !(kit.board || []).length) return "";
  const sleepers = (kit.sleepers || []).map((r) => `
    <div class="dl-row dk-slrow" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
      <span class="dl-main dl-id">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
        <span><strong>${escapeHtml(r.player)}</strong>${injTag("nfl", r.player)}
          <span class="dl-sub">${escapeHtml(r.position)} · ${nflName(r.team)}</span></span></span>
      <span class="dl-num">${r.ppg} actual</span>
      <span class="dl-num strong pos">${r.xppg} expected</span>
    </div>`).join("");

  return `
    <div class="section-title">Draft kit
      <span class="sub">— last season’s volume turned into value over replacement.
      Draft by tier, not rank; rookies are not on this board and it says so.</span></div>
    <div class="card dk-draftday">
      <div class="card-head"><div><div class="player">Draft day — live Sleeper sync</div>
        <div class="subtitle">Paste your Sleeper draft link (or its ID) once the draft room
          opens. Taken players cross off everywhere on this page and the best-available
          list stays current.</div></div>
        <span class="pm-status" id="dk-status" style="color:var(--text-mute)">NOT CONNECTED</span></div>
      <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
        <input id="dk-draft-id" type="text" placeholder="https://sleeper.com/draft/nfl/…  or draft ID"
          style="flex:1;min-width:220px;background:var(--panel-2);color:inherit;
          border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
        <button class="btn" id="dk-connect">Connect</button>
        <button class="btn ghost ff-hidden" id="dk-disconnect">Stop</button>
      </div>
      <div id="dk-advice"></div>
      <div id="dk-best" class="ff-hidden" style="margin-top:12px"></div>
    </div>
    ${dkAssistantHTML(kit)}
    ${dkPlanHTML(kit)}
    ${dkAucCardHTML(kit)}
    <div id="dk-boardwrap">${dkBoardHTML(kit)}</div>
    <div class="section-title">Position tiers
      <span class="sub">— the gaps are the information: inside a tier the differences
      are noise</span></div>
    <div class="cards wide" id="dk-tiers">${dkTiersHTML(kit)}</div>
    ${sleepers ? `<div class="section-title">Usage says buy
        <span class="sub">— expected points clearly above what they actually scored;
        the draft-day version of buy-low</span></div>
      <div class="card" style="padding:0">${sleepers}</div>` : ""}
    ${marketLine(kit)}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:10px">
      ${(kit.notes || []).map(escapeHtml).join(" ")}</p>`;
}

/* ---------------- Your draft plan, and a draft on any platform ----------------
   Ethan, 2026-09-02: "a list for best draft orders of players ... who
   they should draft in what round ... a tool to help users in their
   draft while they are doing it." Both read /api/draftplan, which runs
   the same survival model the Sleeper room gets (engine/fantasy_pick)
   and the greedy round plan (engine/draftplan) over the published kit
   and the consensus ranks. The assistant is for ESPN, Yahoo and the
   kitchen table: mark who is gone and who is yours, and the advice for
   the pick on the clock plus the plan for every pick after it come
   back. State lives in localStorage so a phone that sleeps mid-draft
   comes back where it was. */
const DK_PLAN_KEY = "ff_draft_plan";
const dkPlan = { teams: 12, slot: 7, rounds: 15, type: "snake",
                 order: [], busy: false, last: null };

function dkPlanLoad() {
  try {
    const raw = JSON.parse(localStorage.getItem(DK_PLAN_KEY) || "null");
    if (raw && typeof raw === "object") {
      dkPlan.teams = Math.min(20, Math.max(2, parseInt(raw.teams, 10) || 12));
      dkPlan.rounds = Math.min(30, Math.max(1, parseInt(raw.rounds, 10) || 15));
      dkPlan.slot = Math.min(dkPlan.teams, Math.max(1, parseInt(raw.slot, 10) || 1));
      dkPlan.type = raw.type === "linear" ? "linear" : "snake";
      dkPlan.order = Array.isArray(raw.order)
        ? raw.order.filter((o) => o && typeof o.player === "string").slice(0, 400) : [];
    }
  } catch (e) {}
}

function dkPlanSave() {
  try {
    localStorage.setItem(DK_PLAN_KEY, JSON.stringify({
      teams: dkPlan.teams, slot: dkPlan.slot, rounds: dkPlan.rounds,
      type: dkPlan.type, order: dkPlan.order }));
  } catch (e) {}
}

function dkPlanHTML(kit) {
  dkPlanLoad();
  const seats = Array.from({ length: dkPlan.teams }, (_, i) => i + 1);
  const opt = (vals, cur) => vals.map((v) =>
    `<option value="${v}"${v === cur ? " selected" : ""}>${v}</option>`).join("");
  return `
    <div class="section-title">Your draft plan
      <span class="sub">— who to take in which round from your seat. The most
      valuable player likely to still be there at each of your picks, starting
      slots first, a stretch and a fallback beside every one.</span></div>
    <div class="card dk-plan" id="dk-plan">
      <div class="dk-plan-controls">
        <label>League <select id="dk-plan-teams">${opt([8, 10, 12, 14, 16], dkPlan.teams)}</select></label>
        <label>Your seat <select id="dk-plan-slot">${opt(seats, dkPlan.slot)}</select></label>
        <label>Rounds <select id="dk-plan-rounds">${opt([10, 12, 14, 15, 16, 18, 20], dkPlan.rounds)}</select></label>
        <label>Order <select id="dk-plan-type">
          <option value="snake"${dkPlan.type === "snake" ? " selected" : ""}>Snake</option>
          <option value="linear"${dkPlan.type === "linear" ? " selected" : ""}>Linear</option>
        </select></label>
      </div>
      <div id="dk-plan-body"><div class="dk-advice-note">Building your plan…</div></div>
    </div>`;
}

function dkAssistantHTML(kit) {
  dkPlanLoad();
  return `
    <div class="card dk-draftday" id="dk-assist">
      <div class="card-head"><div><div class="player">Draft assistant — any platform</div>
        <div class="subtitle">ESPN, Yahoo or the kitchen table: type a name as each pick
          is made and mark it <b>Gone</b> or <b>Mine</b>. The pick on the clock and the
          plan for every pick after it update from your seat.</div></div>
        <span class="pm-status" id="dk-assist-status" style="color:var(--text-mute)">${
          dkPlan.order.length ? `${dkPlan.order.length} PICKED` : "READY"}</span></div>
      <div class="dk-assist-search">
        <input id="dk-assist-q" type="text" autocomplete="off" placeholder="Type a player’s name…"
          style="flex:1;min-width:200px;background:var(--panel-2);color:inherit;
          border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
        <button class="btn ghost" id="dk-assist-undo" type="button" title="Take back the last pick">Undo</button>
        <button class="btn ghost" id="dk-assist-reset" type="button" title="Start the draft over">Reset</button>
      </div>
      <div id="dk-assist-hits" class="dk-assist-hits"></div>
      <div id="dk-assist-advice"></div>
      <div id="dk-assist-log" class="dk-assist-log"></div>
    </div>`;
}

/* The pool the search reads: the kit's board plus every consensus row,
   so a rookie or a defense the board cannot project is still markable
   as gone (the plan only needs to know he is off the board). */
function dkAssistPool() {
  const d = _ffData || {};
  const seen = new Set();
  const out = [];
  const add = (r, pos, team) => {
    const k = ffNorm(r.player || "");
    if (!k || seen.has(k)) return;
    seen.add(k);
    out.push({ key: k, player: r.player, position: pos || r.position || "", team: team || r.team || "" });
  };
  ((d.draft_kit || {}).board || []).forEach((r) => add(r));
  ((d.ranks || {}).rows || []).forEach((r) => add(r, r.position, r.team));
  return out;
}

function dkAssistSearch(q) {
  const term = ffNorm(q || "");
  if (term.length < 2) return [];
  const gone = new Set(dkPlan.order.map((o) => ffNorm(o.player)));
  return dkAssistPool()
    .filter((p) => p.key.includes(term) && !gone.has(p.key))
    .slice(0, 8);
}

function dkAssistMark(player, mine) {
  dkPlan.order.push({ player, mine: !!mine });
  dkPlanSave();
  const q = document.getElementById("dk-assist-q");
  if (q) { q.value = ""; }
  const hits = document.getElementById("dk-assist-hits");
  if (hits) hits.innerHTML = "";
  dkPlanRefresh();
}

function dkAssistLogHTML() {
  if (!dkPlan.order.length) return "";
  const rows = dkPlan.order.map((o, i) => `<span class="chip ${o.mine ? "up" : ""}">${
    i + 1}. ${escapeHtml(o.player)}${o.mine ? " · mine" : ""}</span>`);
  return `<div class="dk-bestrow"><span class="dk-bl">Picks so far</span>${rows.join("")}</div>`;
}

async function dkPlanRefresh() {
  const body = {
    teams: dkPlan.teams, slot: dkPlan.slot, rounds: dkPlan.rounds, type: dkPlan.type,
    order: dkPlan.order,
    taken: dkPlan.order.filter((o) => !o.mine).map((o) => o.player),
    mine: dkPlan.order.filter((o) => o.mine).map((o) => o.player),
  };
  const planHost = document.getElementById("dk-plan-body");
  const adviceHost = document.getElementById("dk-assist-advice");
  const logHost = document.getElementById("dk-assist-log");
  const st = document.getElementById("dk-assist-status");
  if (st) st.textContent = dkPlan.order.length ? `${dkPlan.order.length} PICKED` : "READY";
  if (logHost) logHost.innerHTML = dkAssistLogHTML();
  if (dkPlan.busy) return;
  dkPlan.busy = true;
  let got = null;
  try {
    const r = await fetch("/api/draftplan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });
    if (r.ok) got = await r.json();
  } catch (e) {}
  dkPlan.busy = false;
  dkPlan.last = got;
  if (!got || got.empty) {
    if (planHost) planHost.innerHTML = `<div class="dk-advice-note">${escapeHtml(
      (got && got.note) || "The plan could not be built right now.")}</div>`;
    if (adviceHost) adviceHost.innerHTML = "";
    return;
  }
  if (planHost) planHost.innerHTML = dkPlanBodyHTML(got.plan);
  if (adviceHost) adviceHost.innerHTML = dkAssistAdviceHTML(got.advice, got.plan);
  dkCrossOff();
}

function dkPlanBodyHTML(plan) {
  if (!plan || !(plan.rounds || []).length) {
    return `<div class="dk-advice-note">No picks left to plan from this seat.</div>`;
  }
  const pct = pctRoundZ;
  const s = plan.summary || {};
  const who = (c) => c ? `<b>${escapeHtml(c.player)}</b>${mkt(c)} <span class="chip">${
    escapeHtml(c.position)}</span> <span class="mini">+${c.vorp} · ${pct(c.survives)} there</span>` : "";
  const rows = plan.rounds.map((r) => `
    <div class="dk-plan-row${r.empty ? " dk-plan-empty" : ""}">
      <div class="dk-plan-rnd"><b>R${r.round}</b><span class="mini">pick ${r.pick}</span></div>
      <div class="dk-plan-main">
        ${r.plan ? `<div class="dk-plan-take">${who(r.plan)}${
            r.plan.verdict !== "safe" ? ` <span class="chip warn">toss-up</span>` : ""}</div>`
          : `<div class="dk-advice-note">nobody on the board is likely to be here — best available when you get there</div>`}
        ${r.stretch ? `<div class="mini"><span class="dk-bl">If he falls</span> ${
            escapeHtml(r.stretch.player)} (${escapeHtml(r.stretch.position)}, ${pct(r.stretch.survives)})</div>` : ""}
        ${(r.fallbacks || []).length ? `<div class="mini"><span class="dk-bl">Or</span> ${
            r.fallbacks.map((c) => `${escapeHtml(c.player)} (${escapeHtml(c.position)}, ${pct(c.survives)})`).join(" · ")}</div>` : ""}
        ${(r.reach || []).length ? `<div class="mini" style="opacity:.75"><span class="dk-bl">Gone by now</span> ${
            r.reach.map((c) => `${escapeHtml(c.player)} (${pct(c.survives)})`).join(" · ")} — take a round earlier or let go</div>` : ""}
      </div>
    </div>`).join("");
  return `
    <div class="dk-plan-sum">
      <span class="chip">${escapeHtml(s.shape || "")}</span>
      ${s.starters_proj ? `<span class="chip up">starters project ${s.starters_proj} PPG</span>` : ""}
      <span class="chip">room reach ${plan.window}${plan.window_fitted ? "" : " (prior)"}</span>
    </div>
    <div class="dk-plan-rows">${rows}</div>
    <div class="dk-advice-note">${escapeHtml(plan.note || "")}</div>`;
}

function dkAssistAdviceHTML(a, plan) {
  if (!a) return "";
  const pct = pctRoundZ;
  const tone = { gone: "down", "toss-up": "warn", safe: "up" };
  const take = a.take;
  const need = Object.entries(a.needs || {}).map(([p, n]) => `${p}×${n}`).join(" ");
  return `
    <div class="dk-advice">
      <div class="dk-advice-head">
        Seat ${a.slot} of ${a.teams} · ${a.on_the_clock ? "ON THE CLOCK"
          : `next pick ${a.next_pick == null ? "—" : a.next_pick} — ${a.picks_until == null ? "—" : a.picks_until} ${pluralWord(a.picks_until, "pick")} away`}
        <span class="dk-window">room reach ${a.window} deep${a.window_fitted ? "" : " (prior — too few picks to fit yet)"}</span>
      </div>
      ${take ? `<div class="dk-take">
        <b>${escapeHtml(take.player)}</b>${injTag("nfl", take.player)}
        <span class="chip">${escapeHtml(take.position)}</span>
        <span class="chip ${tone[take.verdict] || ""}">${
          take.verdict === "gone" ? "won’t last" : take.verdict === "safe" ? "will last" : "toss-up"} · ${
          pct(take.survives)} to be here at ${a.next_pick || "your next pick"}</span>
        ${take.fills_need ? `<span class="chip up">fills a starting slot</span>` : ""}
        ${mkt(take)}
        <button class="btn" type="button" data-assist-mine="${escapeAttr(take.player)}">I took him</button>
      </div>` : ""}
      ${(a.board || []).length ? `<div class="dk-wait"><span class="dk-bl">Best available</span>
        ${a.board.slice(0, 6).map((r) => `<span class="chip ${tone[r.verdict] || ""}">${
          escapeHtml(r.player)} · ${escapeHtml(r.position)} · ${pct(r.survives)}</span>`).join("")}</div>` : ""}
      ${(a.can_wait || []).length ? `<div class="dk-wait"><span class="dk-bl">Can wait</span>
        ${a.can_wait.slice(0, 4).map((r) => `<span class="chip">${escapeHtml(r.player)} · ${pct(r.survives)}</span>`).join("")}</div>` : ""}
      ${need ? `<div class="mini"><span class="dk-bl">Starters still open</span> ${escapeHtml(need)}</div>` : ""}
    </div>`;
}

function dkBindPlan() {
  const teams = document.getElementById("dk-plan-teams");
  const slot = document.getElementById("dk-plan-slot");
  const rounds = document.getElementById("dk-plan-rounds");
  const type = document.getElementById("dk-plan-type");
  if (!teams || !slot) return;
  const reseat = () => {
    const n = parseInt(teams.value, 10) || 12;
    const cur = Math.min(n, parseInt(slot.value, 10) || 1);
    slot.innerHTML = Array.from({ length: n }, (_, i) => i + 1)
      .map((v) => `<option value="${v}"${v === cur ? " selected" : ""}>${v}</option>`).join("");
  };
  const apply = () => {
    dkPlan.teams = parseInt(teams.value, 10) || 12;
    dkPlan.slot = parseInt(slot.value, 10) || 1;
    dkPlan.rounds = parseInt(rounds.value, 10) || 15;
    dkPlan.type = type.value === "linear" ? "linear" : "snake";
    dkPlanSave();
    dkPlanRefresh();
  };
  teams.addEventListener("change", () => { reseat(); apply(); });
  [slot, rounds, type].forEach((el) => el.addEventListener("change", apply));

  const q = document.getElementById("dk-assist-q");
  const hits = document.getElementById("dk-assist-hits");
  if (q && hits) {
    q.addEventListener("input", () => {
      const rows = dkAssistSearch(q.value);
      hits.innerHTML = rows.map((p) => `
        <div class="dk-assist-hit">
          <span class="dk-pn">${escapeHtml(p.player)} <span class="dk-pt">${escapeHtml(p.position)}${
            p.team ? ` · ${escapeHtml(p.team)}` : ""}</span></span>
          <button class="btn ghost" type="button" data-assist-gone="${escapeAttr(p.player)}">Gone</button>
          <button class="btn" type="button" data-assist-mine="${escapeAttr(p.player)}">Mine</button>
        </div>`).join("") || (q.value.trim().length >= 2
          ? `<div class="dk-advice-note">Nobody by that name on the board.</div>` : "");
    });
  }
  const host = document.getElementById("dk-assist");
  if (host) {
    host.addEventListener("click", (e) => {
      const g = e.target.closest("[data-assist-gone]");
      const m = e.target.closest("[data-assist-mine]");
      if (g) dkAssistMark(g.dataset.assistGone, false);
      else if (m) dkAssistMark(m.dataset.assistMine, true);
    });
    const undo = document.getElementById("dk-assist-undo");
    const reset = document.getElementById("dk-assist-reset");
    if (undo) undo.addEventListener("click", () => {
      dkPlan.order.pop(); dkPlanSave(); dkPlanRefresh(); });
    if (reset) reset.addEventListener("click", () => {
      if (!dkPlan.order.length || confirm("Start the draft over? Every marked pick is cleared.")) {
        dkPlan.order = []; dkPlanSave(); dkPlanRefresh();
      }
    });
  }
  dkPlanRefresh();
}

/* ---------------- This week, in fantasy points -----------------------
   Ethan, 2026-10-22: "make sure we wrap that into it how it should be" —
   the NFL board's projections, in fantasy points (engine/fantasyweek).
   `fantasy_week.json` is paid whole, so it comes through `paidFetch`; the
   drawing lives in js/fantasyweek.js (window.QBWeek), loaded on first use
   like js/report.js. Every caller below asks `typeof QBWeek` first, so a
   page drawn before it loads, or where it failed, draws what it did
   before: season averages and no week. */
async function ffWeekLoad() {
  try {
    const res = await paidFetch("fantasy_week.json");
    if (!res.ok) return null;
    return await res.json();
  } catch (e) { return null; }
}

function loadFantasyWeek() {
  if (window.QBWeek) return Promise.resolve(window.QBWeek);
  return _fwLoading || (_fwLoading = new Promise((resolve) => {
    const s = document.createElement("script"); s.src = "js/fantasyweek.js";
    s.onload = () => resolve(window.QBWeek || null);
    s.onerror = () => { _fwLoading = null; resolve(null); };
    document.head.appendChild(s);
  }));
}
/* THIS WEEK'S FILE (fantasy_week.json, engine/fantasyweek), captured at
   render beside the other two: the "This week" room draws it, and the
   dossier reads his line out of it. Null when it is not built; a locked
   copy (gate.redact) keeps its `locked_reason` so each reader can say
   what it holds. */
let _ffWeek = null;
let _fwLoading = null;            // js/fantasyweek.js, loading

/* ---------------- Mock draft simulator ----------------
   Ethan, 2026-08-18: "Add a mock draft simulator." A snake draft against
   value-hungry CPU rooms, drafted FROM THE KIT'S OWN BOARD — the same
   150 players, projections and VORP the draft kit already publishes, so
   the sim and the kit can never disagree about who is good.

   The CPU model is deliberately simple and stated: each pick samples
   from the best available by VORP, weighted toward the top with noise
   (rooms reach, but rarely far), scaled by a positional-need multiplier
   (a room holding a QB does not draft a second one in round 3). No
   hidden ratings, no personality knobs pretending to be information.

   The end-of-draft read is arithmetic, not a letter grade: your best
   starting lineup's projected PPG, ranked against the CPU rooms' own.
   A grade would imply a model of drafting skill nobody fitted. */
let _mock = null;                 // an in-progress draft survives re-renders
let _mockSel = null;              // the player whose card is open
/* POOL, not board. The draft board is empty at pick 1.01 by definition —
   nobody has picked — so opening on it hands the reader a blank column
   beside the one thing they came to do. The pool is what you choose
   from; the board fills as the room drafts and is one click away. */
let _mockTab = "pool";            // player pool | draft board | my roster
let _mockKit = null;              // the fantasy payload's draft kit, captured at render

//: Starting lineup a roster is judged on (bench fills the rest).
/* ---- League formats ---------------------------------------------------
   Ethan, 2026-08-20: "continue on what was still on your list with the bye
   week shit and te premium and shit like that."

   A format is not a cosmetic setting. Superflex moves quarterbacks from
   the tenth round to the first, because the position stops having a free
   replacement — and that changes which players survive to your next pick,
   which is the whole product. TE premium does the same thing one position
   over. A simulator that offers one format is a simulator of one league.

   EACH FORMAT IS A LINE-UP AND A SCORING TWEAK, and everything else falls
   out of those two by arithmetic: the line-up decides replacement level,
   replacement level decides VORP, VORP decides our board, and the market
   board is built from positional share which the format also sets. No
   format carries a hand-tuned ranking of its own.

   TE PREMIUM IS EXACT, NOT ESTIMATED. It is a bonus per RECEPTION, and
   receptions are now carried on every board row (engine/fantasy_draft.py)
   rather than guessed from targets times an assumed catch rate — which
   would have invented the one number the format turns on. */
const MOCK_FORMATS = {
  ppr: {
    name: "PPR",
    slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2 },
    // Share of picks by position, by band — see _mockMarketOrder.
    share: [
      { until: 12, share: { RB: 0.45, WR: 0.53, TE: 0.02, QB: 0.00 } },
      { until: 60, share: { RB: 0.38, WR: 0.42, TE: 0.11, QB: 0.09 } },
      { until: Infinity, share: { RB: 0.32, WR: 0.34, TE: 0.17, QB: 0.17 } },
    ],
    caps: { QB: 2, TE: 2, RB: 6, WR: 7 },
    // Points added per reception, over the PPR the projections already
    // carry. Zero here because the board is already full PPR.
    bonus: {},
  },
  superflex: {
    name: "Superflex",
    slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2, SFLEX: 1 },
    // A second startable quarterback per team is the whole format: the
    // position runs out, so it goes early and it goes often.
    share: [
      { until: 12, share: { RB: 0.32, WR: 0.36, TE: 0.02, QB: 0.30 } },
      { until: 60, share: { RB: 0.30, WR: 0.33, TE: 0.09, QB: 0.28 } },
      { until: Infinity, share: { RB: 0.30, WR: 0.32, TE: 0.16, QB: 0.22 } },
    ],
    caps: { QB: 4, TE: 2, RB: 6, WR: 7 },
    bonus: {},
  },
  te_prem: {
    name: "TE premium",
    slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2 },
    share: [
      { until: 12, share: { RB: 0.43, WR: 0.49, TE: 0.08, QB: 0.00 } },
      { until: 60, share: { RB: 0.36, WR: 0.39, TE: 0.16, QB: 0.09 } },
      { until: Infinity, share: { RB: 0.31, WR: 0.33, TE: 0.19, QB: 0.17 } },
    ],
    caps: { QB: 2, TE: 3, RB: 6, WR: 7 },
    bonus: { TE: 0.5 },
  },
};
let _mockFormat = "ppr";

/* Keepers survive a reload. Somebody preparing for a real keeper league
   runs the same mock a dozen times against the same four players, and
   re-entering them each time is how a feature goes unused. */
const MOCK_KEEPER_KEY = "qb_mock_keepers";
let _mockKeepers = (() => {
  try {
    const v = JSON.parse(localStorage.getItem(MOCK_KEEPER_KEY) || "[]");
    return Array.isArray(v) ? v.filter((k) => k && k.player) : [];
  } catch (e) { return []; }
})();

function _mockSaveKeepers() {
  try {
    localStorage.setItem(MOCK_KEEPER_KEY, JSON.stringify(_mockKeepers));
  } catch (e) {}
}

/* ---- League settings and mock settings ---------------------------------
   Ethan, 2026-09-08, with a screenshot of FantasyPros' mock-draft settings
   screen: "can you work on making the mock draft better. Here is an
   example of more shit to add." Two cards on it: LEAGUE SETTINGS (scoring,
   draft type, teams, a roster line) and MOCK DRAFT SETTINGS (draft
   position, cheat sheet, pick clock). This is that, built on the format
   machinery above rather than beside it.

   SCORING AND LINE-UP ARE TWO SETTINGS, NOT ONE. The three formats above
   each bundle a scoring tweak with a line-up; a real league picks each
   independently — half PPR AND superflex, standard AND a TE premium. So
   the reader sets scoring (a per-reception value: the board is full PPR,
   so half is −0.5 a catch and standard is −1.0, exact on the carried
   receptions) and a ROSTER (how many of each slot start, and the bench),
   and `_mockFmt` composes the format from them: the line-up decides
   replacement level, replacement decides VORP, VORP decides our board,
   and the market's share bands follow the line-up's shape (a superflex
   roster draws the superflex bands, a TE-premium scoring the TE bands).
   Nothing here carries a hand-tuned ranking.

   KICKER AND DEFENCE ARE ON THE ROSTER LINE AND NOT IN THE DRAFT. The
   kit's board projects neither, and a mock that drafted blanks in rounds
   fifteen and sixteen would be padding. The roster editor keeps them so
   the line reads like the league's, the round count says how many of
   them are drafted here, and the setup panel says why.

   THE PICK CLOCK IS OPT-IN AND REAL. The room's own rule (see the draft
   room notes below) is that a countdown on a CPU pick is an animation —
   nothing is deciding on the other end. A clock on YOUR pick is a
   different thing: it runs out, and something happens (the cheat sheet's
   best legal player is drafted for you), which is the pressure a real
   room puts on and the reason to practise under one. Off by default. */
const MOCK_CFG_KEY = "qb_mock_cfg";
const MOCK_SCORING = { ppr: { name: "PPR", rec: 1 },
                       half: { name: "Half PPR", rec: 0.5 },
                       std: { name: "Standard", rec: 0 } };
const MOCK_DRAFT_TYPES = { snake: "Snake", linear: "Linear",
                           "3rr": "3rd-round reversal" };
const MOCK_SHEETS = { board: "Qellys board (VORP)", market: "Market order (ADP)" };
const MOCK_CLOCKS = [0, 30, 60, 90, 120];
const MOCK_TEAMS_RANGE = [6, 16];
//: The slots a roster can carry, and the most of each the editor allows.
const MOCK_ROSTER_MAX = { QB: 2, RB: 4, WR: 5, TE: 2, FLEX: 3, SFLEX: 1, K: 1, DST: 1, BN: 10 };
const MOCK_DEFAULT_CFG = { scoring: "ppr", tePrem: 0, draftType: "snake",
                           teams: 12, slot: 1, sheet: "board", clock: 0, chaos: 35,
                           roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2, SFLEX: 0,
                                     K: 1, DST: 1, BN: 6 } };
//: One-tap presets that fill the two cards the way a league of that
//: kind usually runs. Each is a starting point, not a lock.
const MOCK_PRESETS = {
  ppr: { name: "PPR", scoring: "ppr", tePrem: 0,
         roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2, SFLEX: 0, K: 1, DST: 1, BN: 6 } },
  half: { name: "Half PPR", scoring: "half", tePrem: 0,
          roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SFLEX: 0, K: 1, DST: 1, BN: 6 } },
  std: { name: "Standard", scoring: "std", tePrem: 0,
         roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SFLEX: 0, K: 1, DST: 1, BN: 6 } },
  superflex: { name: "Superflex", scoring: "ppr", tePrem: 0,
               roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SFLEX: 1, K: 1, DST: 1, BN: 6 } },
  te_prem: { name: "TE premium", scoring: "ppr", tePrem: 0.5,
             roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2, SFLEX: 0, K: 1, DST: 1, BN: 6 } },
};

function _mockCleanCfg(raw) {
  const d = MOCK_DEFAULT_CFG;
  const c = (raw && typeof raw === "object") ? raw : {};
  const num = (v, lo, hi, dflt) => {
    const n = Number(v);
    return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : dflt;
  };
  const roster = {};
  for (const k in d.roster) {
    roster[k] = num((c.roster || {})[k], 0, MOCK_ROSTER_MAX[k], d.roster[k]);
  }
  const teams = num(c.teams, MOCK_TEAMS_RANGE[0], MOCK_TEAMS_RANGE[1], d.teams);
  return {
    scoring: MOCK_SCORING[c.scoring] ? c.scoring : d.scoring,
    tePrem: [0, 0.5, 1].includes(Number(c.tePrem)) ? Number(c.tePrem) : d.tePrem,
    draftType: MOCK_DRAFT_TYPES[c.draftType] ? c.draftType : d.draftType,
    teams, slot: num(c.slot, 1, teams, Math.min(d.slot, teams)),
    sheet: MOCK_SHEETS[c.sheet] ? c.sheet : d.sheet,
    clock: MOCK_CLOCKS.includes(Number(c.clock)) ? Number(c.clock) : d.clock,
    chaos: num(c.chaos, 0, 100, d.chaos),
    roster,
  };
}

function _mockLoadCfg() {
  try {
    if (typeof localStorage === "undefined") return _mockCleanCfg(null);
    return _mockCleanCfg(JSON.parse(localStorage.getItem(MOCK_CFG_KEY) || "null"));
  } catch (e) { return _mockCleanCfg(null); }
}
let _mockCfg = _mockLoadCfg();

function _mockSaveCfg() {
  _mockCfg = _mockCleanCfg(_mockCfg);
  try { localStorage.setItem(MOCK_CFG_KEY, JSON.stringify(_mockCfg)); } catch (e) {}
}

//: The starting line-up the roster implies, in the shape MOCK_FORMATS
//: carries. Kicker and defence are not on it — see the note above.
function _mockCfgSlots(cfg) {
  const r = (cfg || _mockCfg).roster;
  return { QB: r.QB, RB: r.RB, WR: r.WR, TE: r.TE, FLEX: r.FLEX, SFLEX: r.SFLEX };
}

//: Points per reception ON TOP OF the PPR the board already carries —
//: negative for half and standard — plus the TE premium, on the
//: receptions the board carries per game (never estimated).
function _mockCfgBonus(cfg) {
  const c = cfg || _mockCfg;
  const per = (MOCK_SCORING[c.scoring] || MOCK_SCORING.ppr).rec - 1;
  return { RB: per, WR: per, TE: per + (c.tePrem || 0), QB: 0 };
}

//: Which of the three share/cap presets the line-up draws: a second
//: startable quarterback moves the position into round one, a paid
//: catch at tight end moves that one. Keyed off the line-up and the
//: scoring, never off a format name.
function _mockCfgFormatKey(cfg) {
  const c = cfg || _mockCfg;
  if ((c.roster.SFLEX || 0) > 0) return "superflex";
  if ((c.tePrem || 0) > 0) return "te_prem";
  return "ppr";
}

function _mockCfgLabel(cfg) {
  const c = cfg || _mockCfg;
  const bits = [(MOCK_SCORING[c.scoring] || MOCK_SCORING.ppr).name];
  if ((c.roster.SFLEX || 0) > 0) bits.push("Superflex");
  if ((c.tePrem || 0) > 0) bits.push(`TE +${c.tePrem}`);
  return bits.join(" · ");
}

//: How many rounds the league drafts, and how many of them happen HERE.
//: The league's count is every roster slot; the drafted count drops the
//: kicker and defence slots the board cannot fill, then bows to the
//: board's own slack (see `_mockStart`'s note on the 88%).
function _mockCfgRounds(cfg, poolLen, teams) {
  const r = (cfg || _mockCfg).roster;
  const league = ["QB", "RB", "WR", "TE", "FLEX", "SFLEX", "K", "DST", "BN"]
    .reduce((s, k) => s + (r[k] || 0), 0);
  const wanted = league - (r.K || 0) - (r.DST || 0);
  const slack = Math.max(1, Math.floor((poolLen || 0) * 0.88 / Math.max(1, teams || 1)));
  return { league, wanted, drafted: Math.max(1, Math.min(wanted, slack)),
           skipped: (r.K || 0) + (r.DST || 0) };
}

//: The roster line, the way the screenshot writes it: "QB, 2RB, 3WR,
//: WR/RB/TE, TE, K, DST, 6BN".
function _mockRosterLine(cfg) {
  const r = (cfg || _mockCfg).roster;
  // In the order the screenshot writes them: the flex before the tight end.
  const word = { QB: "QB", RB: "RB", WR: "WR", FLEX: "WR/RB/TE", TE: "TE",
                 SFLEX: "QB/WR/RB/TE", K: "K", DST: "DST", BN: "BN" };
  return Object.keys(word).filter((k) => r[k] > 0)
    .map((k) => `${r[k] > 1 ? r[k] : ""}${word[k]}`).join(", ");
}

/* THE FORMAT, COMPOSED. The share bands and the caps come from the
   preset the line-up draws; the line-up itself, the scoring bonus and the
   label come from the settings. Caps rise with the roster so a league
   starting three receivers and two flexes is allowed to hold them. */
function _mockFmt() {
  const base = MOCK_FORMATS[_mockFormat] || MOCK_FORMATS.ppr;
  const slots = _mockCfgSlots();
  const caps = {
    QB: Math.max(base.caps.QB, slots.QB + slots.SFLEX + 1),
    TE: Math.max(base.caps.TE, slots.TE + 1),
    RB: Math.max(base.caps.RB, slots.RB + slots.FLEX + 3),
    WR: Math.max(base.caps.WR, slots.WR + slots.FLEX + 3),
  };
  return { ...base, name: _mockCfgLabel(), slots, caps, bonus: _mockCfgBonus() };
}

/* The board under this format's scoring, with VORP re-derived from the
   line-up it implies. A format that changed projections and left VORP
   alone would move every tight end up the page and leave the number that
   decides the draft describing a different league. */
function _mockScoreBoard(board, fmt, teams) {
  const rows = board.map((p) => {
    const per = (fmt.bonus || {})[p.position] || 0;
    const proj = per ? +( (p.proj || 0) + per * (p.rec_pg || 0) ).toFixed(1)
                     : (p.proj || 0);
    return { ...p, proj };
  });
  // Replacement is the last STARTER at the position across the league —
  // the best player everyone else can have for nothing. Superflex moves
  // it for quarterbacks by roughly a full round of them, which is the
  // entire reason the format drafts differently.
  // THE LEAGUE'S SIZE, HANDED IN. This read `_mock.teams`, and at the
  // moment the board is scored `_mock` is still the previous draft or
  // null — so a ten-team league's replacement level was computed for a
  // twelve-team one, every draft.
  teams = teams || (_mock && _mock.teams) || 12;
  const starters = { QB: fmt.slots.QB + (fmt.slots.SFLEX || 0),
                     RB: fmt.slots.RB, WR: fmt.slots.WR, TE: fmt.slots.TE };
  const byPos = {};
  for (const r of rows) (byPos[r.position] = byPos[r.position] || []).push(r);
  for (const pos in byPos) {
    byPos[pos].sort((a, b) => b.proj - a.proj);
    // The flex eats into backs and receivers beyond their own slots.
    const flexShare = (pos === "RB" || pos === "WR")
      ? Math.round((fmt.slots.FLEX || 0) * teams * 0.45) : 0;
    const rank = Math.max(1, Math.round((starters[pos] || 1) * teams) + flexShare);
    const base = byPos[pos][Math.min(rank, byPos[pos].length) - 1];
    const baseline = base ? base.proj : 0;
    byPos[pos].forEach((r, i) => {
      r.pos_rank = i + 1;
      r.vorp = +(r.proj - baseline).toFixed(1);
    });
  }
  return rows.sort((a, b) => b.vorp - a.vorp);
}

const MOCK_SLOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2 };
const MOCK_FLEX = new Set(["RB", "WR", "TE"]);

/* ---- Who is in the room --------------------------------------------
   Ethan, 2026-08-20: "look at what other features and shit we can add to
   it... we should add where we run the simulation like 20k times over to
   see all the different outcomes."

   The second half of that is only worth anything if the first half is
   real. A room of nine identical value-maximisers produces a draft with
   almost no variance, and running THAT twenty thousand times just
   measures the noise term — a confident-looking probability about a
   league nobody plays in.

   So the CPUs get personas. Every rival simulator worth copying does
   this (FanSpeak assigns archetypes, RotoWire and FantasyPros vary how
   strictly rooms follow rankings), and it is the difference between "the
   board falls the same way every time" and a draft where the run on tight
   ends is sometimes real. The personas below are the recognisable
   season-long builds, not invented flavour: a Zero-RB room genuinely will
   not take a back in the first five, and that is exactly the behaviour
   that decides whether your target survives.

   ONE RULE, TWO CALLERS. _mockScore is used by the CPU that is actually
   drafting AND by the Monte Carlo that predicts it. If the predictor had
   its own copy they would drift, and the page would publish a probability
   about a room that does not exist. */
//: A build moves a position up or down the market board, IN SLOTS, and
//: is drawn with a weight. Both numbers matter and both were measured.
//:
//: SLOTS, not multipliers. The first cut expressed a build as a weight
//: multiplier, which has no natural scale: an "elite TE" room at 2.6x had
//: a real chance of taking its tight end at 1.03, and across 300 drafts
//: the first TE left the board at pick 4.9. A build means "I will take
//: him a round early", which is a number of slots, and slots can be
//: bounded where a tail cannot.
//:
//: WEIGHTED, because most rooms are not characters. A league of twelve
//: managers has one Zero-RB zealot, not four; drawing eight builds
//: uniformly put roughly 1.5 tight-end chasers in every draft and that
//: alone dragged the first TE four picks early no matter how the reach
//: was bounded. Best-available is most of the room, as it is in life.
const MOCK_ARCHETYPES = [
  { key: "bpa", name: "Best available", w: 34, shift: {} },
  { key: "balanced", name: "Balanced", w: 18, shift: { RB: 1, WR: 1 } },
  { key: "robust_rb", name: "Robust RB", w: 10, through: 5, shift: { RB: 4, WR: -2 } },
  { key: "wr_room", name: "WR hoarder", w: 10, through: 8, shift: { WR: 4, RB: -3 } },
  { key: "hero_rb", name: "Hero RB", w: 9, through: 2, shift: { RB: 4 },
    after: { RB: -8, WR: 3 } },
  { key: "zero_rb", name: "Zero RB", w: 7, through: 6, shift: { RB: -14, WR: 4, TE: 2 } },
  { key: "early_qb", name: "Early QB", w: 5, through: 6, shift: { QB: 5 } },
  { key: "elite_te", name: "Elite TE", w: 4, through: 5, shift: { TE: 5 } },
  { key: "late_round", name: "Late-round onesies", w: 3, through: 4,
    shift: { QB: -18, TE: -18 } },
];
//: Drawn once per room from the weights above.
const MOCK_ARCH_TOTAL = MOCK_ARCHETYPES.reduce((s, a) => s + a.w, 0);

function _mockDrawArchetype(rnd) {
  let roll = (rnd || Math.random)() * MOCK_ARCH_TOTAL;
  for (const a of MOCK_ARCHETYPES) { roll -= a.w; if (roll <= 0) return a; }
  return MOCK_ARCHETYPES[0];
}

/* ---- The board the ROOM drafts from, which is not ours ---------------
   Measured before this existed, over 300 full drafts: the first tight end
   left the board at pick 4.9 and the first quarterback at 11.4, rooms
   finished with as many as six of either, and no pick ever reached more
   than eight slots. Real twelve-team drafts do none of those things.

   The cause was one assumption. The CPUs were drafting off OUR board,
   ordered by VORP — and VORP is not draft order. Value over replacement
   says what a player is worth; a draft room says what people will pay,
   and the two disagree hardest exactly at quarterback and tight end,
   where the replacement is nearly as good as the starter but the room
   still takes the name it knows. A simulator whose rooms draft off a
   value metric is a simulator of a league of economists.

   So there are two boards now, which is also the honest shape of the
   thing: the MARKET order the rooms draft from, and our own VORP order
   the human is shown. The gap between them is the entire point of using
   this site to prepare — "the room has him twelfth, we have him
   twenty-fifth" is a fact you can act on, and it only exists once the
   two orders are allowed to differ.

   THE MARKET ORDER IS BUILT FROM POSITIONAL SHARE, not from fitted
   fudge factors. These are the shares of picks each position takes in a
   twelve-team one-quarterback PPR draft — front-loaded with backs and
   receivers, with quarterbacks and tight ends filling in once the
   starters are gone. Slots are dealt to whichever position is furthest
   behind its share, so the resulting order reproduces those shares by
   construction and the only inputs are numbers you can argue with. */
//: Positional share of picks in a twelve-team one-quarterback PPR draft,
//: in three bands. THE FIRST BAND IS THE WHOLE POINT: a flat share across
//: the draft schedules positions EVENLY, which put a tight end in round
//: one by construction — measured, the first TE left at pick 4.9 and no
//: amount of bounding the rooms' reaches could fix a board that already
//: had him there. Round one is backs and receivers; the onesies arrive
//: once starting line-ups are being filled, and take over late.
const MOCK_SHARE_BANDS = [
  { until: 12, share: { RB: 0.45, WR: 0.53, TE: 0.02, QB: 0.00 } },
  { until: 60, share: { RB: 0.38, WR: 0.42, TE: 0.11, QB: 0.09 } },
  { until: Infinity, share: { RB: 0.32, WR: 0.34, TE: 0.17, QB: 0.17 } },
];

function _mockShareAt(slot) {
  const bands = (_mockFmt().share) || MOCK_SHARE_BANDS;
  for (const b of bands) if (slot < b.until) return b.share;
  return bands[bands.length - 1].share;
}

function _mockMarketOrder(board) {
  const q = { QB: [], RB: [], WR: [], TE: [] };
  for (const p of board) if (q[p.position]) q[p.position].push(p);
  for (const k in q) q[k].sort((a, b) => (b.vorp || 0) - (a.vorp || 0));
  const out = [];
  const drawn = { QB: 0, RB: 0, WR: 0, TE: 0 };
  // Entitlement ACCUMULATES slot by slot rather than being recomputed as
  // share x slot. The multiplied form is wrong at every band boundary: it
  // retroactively bills the whole draft at the new rate, so the moment
  // the second band opened a tight end was owed 1.4 picks he had never
  // been owed, and one went off the board immediately.
  const want = { QB: 0, RB: 0, WR: 0, TE: 0 };
  const total = board.length;
  for (let slot = 0; slot < total; slot++) {
    const share = _mockShareAt(slot);
    for (const pos of ["RB", "WR", "TE", "QB"]) want[pos] += share[pos] || 0;
    let best = null, bestDeficit = -Infinity;
    for (const pos of ["RB", "WR", "TE", "QB"]) {
      if (!q[pos].length) continue;
      const deficit = want[pos] - drawn[pos];
      if (deficit > bestDeficit) { bestDeficit = deficit; best = pos; }
    }
    if (!best) break;
    out.push(q[best].shift());
    drawn[best] += 1;
  }
  // Anything the shares never reached (a position that ran out) still
  // belongs on the board, in its own order.
  for (const pos of ["RB", "WR", "TE", "QB"]) out.push(...q[pos]);
  return out;
}

/* HARD CAPS, because the need curve only ever softened. It bottomed out
   at 0.2 and 0.2 is not zero over twelve rounds: measured, rooms finished
   with as many as six quarterbacks. No league does that, and a room that
   might is a room whose picks tell you nothing. */
const MOCK_ROSTER_CAP = { QB: 2, TE: 2, RB: 6, WR: 7 };

/* Rank decay, precomputed. exp(-i/2.5) for the eight candidates a room
   ever considers — a table because the Monte Carlo evaluates this a few
   million times and Math.exp in that loop is most of the run. */
//: Fourteen, not eight. Eight was a WALL: measured over 300 drafts, the
//: deepest reach in the whole sample was exactly eight slots, because
//: the ninth-ranked player was not in the room's field of view. Real
//: drafts reach further than that and everyone has seen it. The decay
//: still makes a deep pick rare — the fourteenth candidate carries about
//: 0.4% of the top one's weight — so this widens the tail without
//: flattening the order. (Read at quarter-slot resolution: MOCK_DECAY_FINE.)
const MOCK_TOPK = 14;

/* How far this build moves a position up (+) or down (−) the market
   board, in slots, at this point in the draft. */
function _mockLean(arch, pos, round) {
  const table = (arch.through != null && round >= arch.through)
    ? (arch.after || {}) : (arch.shift || {});
  return table[pos] || 0;
}

/* Positional need from COUNTS rather than a roster array: the simulator
   carries counts, and rebuilding a roster array per simulated pick was
   the whole cost of the loop. */
function _mockNeedCounts(counts, pos, round) {
  const n = counts[pos] || 0;
  const caps = (_mockFmt().caps) || MOCK_ROSTER_CAP;
  if (n >= (caps[pos] || 99)) return 0;
  // A second quarterback or tight end is a bench luxury all draft, not
  // just before round nine. Measured: relaxing it late pushed rooms to
  // 1.85 QBs each, where a twelve-round league runs about 1.3.
  //
  // EXCEPT WHERE THE FORMAT STARTS TWO. In superflex the second
  // quarterback is a STARTER, and treating him as a luxury would have
  // rooms leaving a line-up slot empty to hold a fourth receiver. The
  // line-up decides this, not a special case for a format name.
  const starts = (_mockFmt().slots.QB || 0) + (_mockFmt().slots.SFLEX || 0);
  if (pos === "QB" && n < starts) return 1.0;
  if (pos === "QB" || pos === "TE") return n >= 1 ? (round < 9 ? 0.05 : 0.18) : 1.0;
  if (pos === "RB" || pos === "WR") return n >= 5 ? 0.3 : 1.0;
  return n >= 2 ? 0.2 : 1.0;
}

/* The chaos dial, as every simulator worth copying has: at 0 the rooms
   follow the board almost exactly and the draft is predictable; at 100
   they reach and slide constantly. It widens the multiplicative noise
   band around each candidate — 0 gives a band of ±0, 100 gives roughly
   0.2x–1.8x, which is enough to move a player a full round. */
function _mockNoiseBand(chaos) {
  return 0.2 + (Math.max(0, Math.min(100, chaos)) / 100) * 1.4;
}

/* THE one scoring rule. `health` is passed in rather than looked up so
   the Monte Carlo can precompute it once instead of normalising a name
   per candidate per simulated pick. */
//: The decay curve at quarter-slot resolution, so a shifted rank still
//: reads off a table rather than calling exp a few million times.
const MOCK_DECAY_FINE = Array.from({ length: 4 * 14 + 1 },
                                   (_, i) => Math.exp(-(i / 4) / 2.5));

function _mockDecayAt(effRank) {
  const i = Math.round(effRank * 4);
  return MOCK_DECAY_FINE[i < 0 ? 0 : i >= MOCK_DECAY_FINE.length
    ? MOCK_DECAY_FINE.length - 1 : i];
}

function _mockScore(p, rank, counts, round, arch, band, rnd, health) {
  const noise = 1 - band / 2 + rnd() * band;
  const need = _mockNeedCounts(counts, p.position, round);
  if (!need) return 0;                      // a full roster spot is closed
  // The build pulls him up or down the board, in slots.
  const shift = _mockLean(arch, p.position, round);
  return _mockDecayAt(rank - shift) * need * health
       * (noise > 0.03 ? noise : 0.03);
}

/* A small seeded generator, so the same board and the same draft state
   produce the same probabilities twice running. Math.random would make
   every re-render jitter the numbers, and a probability that changes
   while you stare at it is one nobody believes — correctly. */
function _mockRng(seed) {
  let a = (seed >>> 0) || 1;
  return function () {
    a ^= a << 13; a >>>= 0;
    a ^= a >> 17;
    a ^= a << 5; a >>>= 0;
    return a / 4294967296;
  };
}

/* ---- Twenty thousand drafts, to answer one question ------------------
   Ethan: "run the simulation like 20k times over to see all the different
   outcomes and then use that data to better display what the simulation
   would carry out."

   The question worth that many runs is the one every drafter actually
   asks on the clock: IF I WAIT, WHO IS STILL THERE? A single mock answers
   it once, which is an anecdote. Twenty thousand answers it as a
   distribution — "Bijan survives 12% of the time, Nabers 61%" — and that
   is a number you can draft against. FantasyPros charges for this (their
   Pick Predictor); the arithmetic is not the hard part, an honest room
   model is, which is what the personas above are for.

   ONLY THE PICKS THAT MATTER ARE SIMULATED. Playing out whole drafts
   would be twenty thousand times fourteen rounds to learn something that
   is decided in the next twenty picks. The sim runs from here to your
   next turn, which on a twelve-team board is at most twenty-two picks —
   about half a million simulated picks for a full run, which is a few
   hundred milliseconds rather than a minute.

   WHAT IT REPORTS is deliberately three things and not a single number:
   who survives, what the BEST thing left is likely to be worth, and how
   many of each position go off the board first. The third is the run
   warning every simulator has and the only one of the three that changes
   what you do about a position rather than about a player. */

//: Simulated drafts per run. Capped by measurement rather than faith:
//: _mockSims backs this off if a device cannot do it inside a frame
//: budget, and the page prints the count it actually managed.
const MOCK_SIMS = 20000;
//: How hard the rooms deviate from the board, 0-100. 35 is a real draft:
//: reaches happen, but the first round is mostly the first round.
let _mockChaos = 35;
//: Measured, not guessed: 20,000 runs of the longest gap a twelve-team
//: board produces (22 picks, from the 1.01 seat) takes ~540ms in a
//: browser, and every later pick is shorter. 800 leaves room for a slower
//: phone to still finish the full count, and a device that genuinely
//: cannot gets fewer runs and a page that says how many.
const MOCK_SIM_BUDGET_MS = 800;

/* Your next turn after `from`, or null if the draft ends first. */
/* ---- Keepers ---------------------------------------------------------
   Ethan, 2026-08-20: "do the keeper shit too."

   A keeper is not a player crossed off a list. It is a player crossed off
   AND A PICK THAT NEVER HAPPENS — the round the keeper costs belongs to
   the room that kept him, and the draft moves straight past it. Getting
   that half wrong is what makes most keeper toggles cosmetic: the board
   falls differently in a keeper league precisely because eleven rooms
   pick in round three instead of twelve, and the survival odds are wrong
   by exactly that much if the slot is left in.

   So a keeper is stored as (player, room, round) and turns into two
   things: the player leaves the pool and joins that room's roster, and
   the pick index he cost goes into a skip set that every reader of the
   draft order honours — the live draft, the predictor, and "when is my
   next turn". One set, every caller, same reason as the scoring rule. */
function _mockSkipSet(m) {
  const skip = new Set();
  for (const k of m.keepers || []) {
    const r = (k.round || 1) - 1;
    if (r < 0 || r >= m.rounds) continue;
    // The index in the snake where that room picks in that round.
    for (let i = r * m.teams; i < (r + 1) * m.teams; i++) {
      if (_mockPicker(i, m.teams) === k.team) { skip.add(i); break; }
    }
  }
  return skip;
}

function _mockSkipped(m, i) {
  return !!(m.skip && m.skip.has(i));
}

function _mockNextTurn(from, teams, you, rounds, skip) {
  const total = teams * rounds;
  for (let i = from; i < total; i++) {
    if (skip && skip.has(i)) continue;
    if (_mockPicker(i, teams) === you) return i;
  }
  return null;
}

/* HOW LONG UNTIL YOU ARE UP, in the only unit a draft has.

   Ethan, 2026-08-20: "make the clock a real picks-until-your-turn
   counter." The render had a ticking "00:47" and there is no clock here
   to tick — a CPU pick is computed in under a millisecond, so a
   countdown would have been an animation pretending somebody is
   deciding. This is the same box answering the same question ("how long
   have I got?") with the number that is actually true.

   IT COUNTS PICKS THAT HAPPEN, not index positions. A keeper-held slot
   is skipped rather than drafted, so counting the raw gap would promise
   twenty-two players coming off the board when three of those slots are
   keepers and only nineteen do. `_mockNextTurn` already skips them; this
   counts the same way, so the two can never disagree about the same
   draft.

   Returns null for "you have no turn left", which is a real state at the
   end of a draft and reads differently from zero. */
function _mockPicksUntil(m) {
  const onClock = _mockPicker(m.pick, m.teams) === m.you
    && !_mockSkipped(m, m.pick);
  const skip = _mockSkipSet(m);
  const next = _mockNextTurn(m.pick + (onClock ? 1 : 0),
                             m.teams, m.you, m.rounds, skip);
  if (onClock) return { onClock: true, picks: 0, next: m.pick };
  if (next == null) return { onClock: false, picks: null, next: null };
  let picks = 0;
  for (let i = m.pick; i < next; i++) if (!skip.has(i)) picks += 1;
  return { onClock: false, picks, next };
}

/* Market order, sorted once per run rather than per simulated pick. The
   rooms draft off the market board; our VORP order is what the human is
   shown, and the survival map is keyed by name so the caller never has to
   care which order produced it. */
function _mockByMarket(m) {
  if (!m.market) return m.pool;
  const rank = (p) => {
    const r = m.market.get(p.player);
    return r == null ? 1e9 : r;
  };
  return m.pool.slice().sort((a, b) => rank(a) - rank(b));
}

function mockSurvival(m, sims) {
  const pool = _mockByMarket(m);
  const n = pool.length;
  // THE QUESTION IS ABOUT THE TURN AFTER THIS ONE. On the clock, "who is
  // still there?" means when it comes BACK to you — the pick in front of
  // you is yours to make, so simulating up to it answers nothing. Off the
  // clock the reference point is simply your next turn.
  const onClock = _mockPicker(m.pick, m.teams) === m.you;
  const from = m.pick + (onClock ? 1 : 0);
  const mine = _mockNextTurn(from, m.teams, m.you, m.rounds, m.skip);
  if (mine == null || mine <= from) return null;
  const gap = mine - from;                   // picks by other rooms first
  if (!gap) return null;

  // Precomputed once, not per simulated pick: name normalisation inside
  // the loop was the difference between 300ms and half a minute.
  const health = new Float64Array(n);
  for (let i = 0; i < n; i++) health[i] = _mockHealth(pool[i].player);
  const posOf = pool.map((p) => p.position);
  const vorpOf = pool.map((p) => p.vorp || 0);
  const band = _mockNoiseBand(m.chaos == null ? 35 : m.chaos);

  const survived = new Float64Array(n);
  const takenBy = { QB: 0, RB: 0, WR: 0, TE: 0 };
  const bestVorp = [];
  // Version stamps instead of clearing an array 20,000 times.
  const stamp = new Int32Array(n);
  const counts = [];                          // per team, per position
  const t0 = (typeof performance === "object" ? performance.now() : Date.now());
  let ran = 0;

  for (let s = 1; s <= sims; s++) {
    for (let t = 0; t < m.teams; t++) {
      counts[t] = counts[t] || {};
      counts[t].QB = 0; counts[t].RB = 0; counts[t].WR = 0; counts[t].TE = 0;
    }
    // What each room already holds this draft.
    for (const e of m.log) {
      const c = counts[e.team];
      if (c && c[e.player.position] != null) c[e.player.position] += 1;
    }
    const rnd = _mockRng(s * 2654435761);
    let cursor = 0;
    for (let k = 0; k < gap; k++) {
      const pickIdx = from + k;
      // A kept round is a pick that does not happen. Left in, the
      // simulator would have a phantom room taking a player who is in
      // fact still on the board when it comes back to you.
      if (_mockSkipped(m, pickIdx)) continue;
      const team = _mockPicker(pickIdx, m.teams);
      const round = Math.floor(pickIdx / m.teams);
      const arch = m.personas[team];
      while (cursor < n && stamp[cursor] === s) cursor++;
      // The top MOCK_TOPK still available, walking past what is gone.
      const idx = [];
      for (let i = cursor; i < n && idx.length < MOCK_TOPK; i++) {
        if (stamp[i] !== s) idx.push(i);
      }
      if (!idx.length) break;
      let total = 0;
      const w = [];
      for (let j = 0; j < idx.length; j++) {
        const i = idx[j];
        const x = _mockScore(pool[i], j, counts[team], round, arch, band,
                             rnd, health[i]);
        w.push(x); total += x;
      }
      // EVERY CANDIDATE CAPPED OUT is a real state late in a draft, and
      // falling back to idx[0] was how a room ended with three
      // quarterbacks under a cap of two: a zero weight has to mean no,
      // not "no unless nothing else scores".
      let chosen = -1;
      if (total > 0) {
        let roll = rnd() * total;
        for (let j = 0; j < idx.length; j++) {
          roll -= w[j];
          if (roll <= 0) { chosen = idx[j]; break; }
        }
        if (chosen < 0) chosen = idx[idx.length - 1];
      } else {
        // NOTHING IN THE WINDOW IS LEGAL, which is an ordinary late-draft
        // state once a room has filled its backs and receivers. The first
        // cut abandoned the pick, and rooms finished a twelve-round draft
        // with about eleven players — a room that stops drafting is not a
        // room. Look past the window instead: somebody legal is always
        // further down a hundred-and-fifty-man board.
        for (let i = cursor; i < n; i++) {
          if (stamp[i] === s) continue;
          if (_mockNeedCounts(counts[team], posOf[i], round)) { chosen = i; break; }
        }
        // STILL NOTHING, which late in a draft is not a bug: the caps are
        // jointly infeasible against this board (twelve rooms wanting six
        // backs each, from forty-four) and by the last rounds what is left
        // is the position everybody already filled. Measured before this:
        // ten of a hundred and forty-four picks were simply never made,
        // and rooms finished with eleven players. A room with nothing
        // legal takes the best man left, which is what a manager does.
        if (chosen < 0) {
          for (let i = cursor; i < n; i++) if (stamp[i] !== s) { chosen = i; break; }
        }
        if (chosen < 0) break;              // the board itself is empty
      }
      stamp[chosen] = s;
      const c = counts[team];
      if (c[posOf[chosen]] != null) c[posOf[chosen]] += 1;
      takenBy[posOf[chosen]] = (takenBy[posOf[chosen]] || 0) + 1;
    }
    // Who is left, and what the best of them is worth.
    let best = 0;
    for (let i = 0; i < n; i++) {
      if (stamp[i] !== s) {
        survived[i] += 1;
        if (vorpOf[i] > best) best = vorpOf[i];
      }
    }
    bestVorp.push(best);
    ran = s;
    // Measured, not assumed. A slow phone gets fewer runs and the page
    // says how many rather than claiming twenty thousand it never did.
    if ((s & 255) === 0) {
      const dt = (typeof performance === "object" ? performance.now() : Date.now()) - t0;
      if (dt > MOCK_SIM_BUDGET_MS) break;
    }
  }
  if (!ran) return null;

  bestVorp.sort((a, b) => a - b);
  const q = (f) => bestVorp[Math.min(bestVorp.length - 1,
                                     Math.floor(f * bestVorp.length))];
  const byPlayer = new Map();
  for (let i = 0; i < n; i++) byPlayer.set(pool[i].player, survived[i] / ran);
  return {
    sims: ran, gap, nextPick: mine,
    survive: byPlayer,
    // What the board will be worth when it comes back to you, as a range
    // rather than a point — the median alone reads as a promise.
    bestP10: q(0.10), bestP50: q(0.50), bestP90: q(0.90),
    // Expected departures per position before your turn: the run warning.
    goneBy: Object.fromEntries(Object.entries(takenBy)
      .map(([k, v]) => [k, v / ran])),
  };
}

//: The draft type of the draft in progress — read by `_mockPicker` when
//: no kind is handed in, so every caller that asks "who picks here?"
//: gets the same answer without threading a parameter through the
//: Monte Carlo.
let _mockDraftType = "snake";

function _mockPicker(pickIdx, teams, kind) {
  kind = kind || (typeof _mockDraftType === "string" ? _mockDraftType : "snake");
  const round = Math.floor(pickIdx / teams);
  const i = pickIdx % teams;
  if (kind === "linear") return i;                       // the same order every round
  // THIRD-ROUND REVERSAL: the snake, except round three runs the same
  // way as round two, so the seat that picked last in round one gets
  // picks 2.01 AND 3.01 before the order turns again. From round four
  // on it alternates as a snake does. The 1.01 seat's 1.01/2.12/3.12/
  // 4.01 against the snake's 1.01/2.12/3.01/4.12.
  const reverse = kind === "3rr"
    ? (round === 1 || (round >= 2 && round % 2 === 0))
    : round % 2 === 1;
  return reverse ? teams - 1 - i : i;
}

function _mockStart(teams, slot) {
  const kit = _mockKit || {};
  // THE SETTINGS DECIDE THE FORMAT AND THE ORDER, before anything reads
  // either: the line-up picks the share preset, the scoring the bonus,
  // and the draft type the picker every caller shares.
  _mockFormat = _mockCfgFormatKey();
  _mockDraftType = MOCK_DRAFT_TYPES[_mockCfg.draftType] ? _mockCfg.draftType : "snake";
  _mockStopClock();
  // OUR order — value over replacement — is what the human is shown.
  const pool = _mockScoreBoard((kit.board || []).slice(), _mockFmt(), teams);
  // THE ROOM'S order is the market's, and the gap between the two is the
  // value column. Built once per draft, deterministic, and carried as a
  // rank per player so both the live CPU and the Monte Carlo read the
  // same board without re-deriving it.
  const market = new Map(_mockMarketOrder(pool).map((p, i) => [p.player, i]));
  // Every room gets a persona, drawn once and kept for the draft — a
  // manager who is Zero-RB in round two and Robust-RB in round three is
  // not a manager. Your own seat gets one too, unused, so the array
  // indexes by team without a special case. With a Sleeper league read,
  // a room whose manager was measured is dealt THAT build, in the seat
  // the league's draft order gives them (`_mockSeatRooms`).
  const personas = _mockSeatRooms(teams, _mockLeague);
  // Keepers whose room still exists in this league size — shrinking from
  // twelve teams to eight must not leave a keeper owned by room ten.
  const keepers = (_mockKeepers || []).filter((k) => k.team < teams);
  // A FROZEN COPY OF THE FULL BOARD. `pool` is spliced as players go, so
  // an index into it is a rank among WHAT IS LEFT — which would make a
  // player's board rank improve every time somebody else was drafted, and
  // make the edge against the market grow all draft for no reason.
  _mock = { teams, you: slot - 1, pool, all: pool.slice(), pick: 0,
            // LEAVE THE BOARD SOME SLACK, because it has no kickers or
            // defences to absorb the end of a draft. Drafting it to the
            // floor leaves the last picks nowhere legal to go — what
            // remains is the position every room already filled — and
            // measured over 300 full drafts, rooms finished carrying four
            // quarterbacks apiece.
            //
            // A FRACTION, not a fixed round: one round of slack fixes a
            // twelve-team board and does nothing for a ten-team one,
            // which draws 140 of 150 either way. At 88% the same 300
            // drafts fill every pick at 8, 10 and 12 teams with the
            // roster caps holding — a third quarterback still turns up
            // occasionally on a CPU bench, which is the price of keeping
            // the draft eleven rounds long instead of ten.
            // THE ROSTER DECIDES THE ROUNDS NOW — starters plus bench,
            // less the kicker and defence slots the board cannot fill —
            // under the same slack. `_mockCfgRounds` carries all three
            // numbers so the hero can say "16 rounds, 14 drafted here".
            rounds: _mockCfgRounds(_mockCfg, pool.length, teams).drafted,
            roundsInfo: _mockCfgRounds(_mockCfg, pool.length, teams),
            type: _mockDraftType,
            // A frozen copy of the settings this draft was started with,
            // so a change in the panel cannot alter a draft in progress.
            cfg: JSON.parse(JSON.stringify(_mockCfg)),
            rosters: Array.from({ length: teams }, () => []), log: [],
            personas, chaos: _mockChaos, sim: null, market, keepers };
  // The skip set needs `rounds` and `teams`, so it is built once the
  // state exists and before anybody reads the draft order.
  _mock.skip = _mockSkipSet(_mock);
  // Kept players leave the board and join the roster that kept them, so
  // every rule that reads a roster — need, caps, the line-up, the bye
  // clash — sees them without a special case anywhere.
  for (const k of keepers) {
    const p = _mock.pool.find((x) => x.player === k.player);
    if (!p) continue;
    _mock.pool = _mock.pool.filter((x) => x !== p);
    _mock.rosters[k.team].push(p);
  }
  _mockAdvance();
}


/* A CPU manager reads the injury report. A man ruled out or on IR is
   not worth a premium pick to a season-long roster; a Questionable in
   August is Tuesday noise. A multiplier, not a ban — the late-round
   stash of a hurt star is a real strategy, and the human can always
   draft anyone the tags warned about. */
function _mockHealth(name) {
  const r = injFind("nfl", name);
  if (!r) return 1;
  return injTone(r.status) === "var(--bad)" ? 0.25 : 0.85;
}

/* The room that is actually drafting, through the SAME rule the Monte
   Carlo predicts with. Two copies would drift, and the page would be
   publishing probabilities about a room that does not exist. */
function _mockCpuPick(ti) {
  const round = Math.floor(_mock.pick / _mock.teams);
  const roster = _mock.rosters[ti];
  const counts = { QB: 0, RB: 0, WR: 0, TE: 0 };
  for (const p of roster) if (counts[p.position] != null) counts[p.position] += 1;
  const arch = (_mock.personas || [])[ti] || MOCK_ARCHETYPES[0];
  const band = _mockNoiseBand(_mock.chaos == null ? 35 : _mock.chaos);
  const cands = _mockByMarket(_mock).slice(0, MOCK_TOPK).map((p, i) => ({
    p, w: _mockScore(p, i, counts, round, arch, band, Math.random,
                     _mockHealth(p.player)) }));
  const total = cands.reduce((s, c) => s + c.w, 0);
  // Same rule as the simulator: a zero weight is a closed roster spot,
  // not a last resort. Falling through to cands[0] is how a room ends
  // with three quarterbacks under a cap of two.
  let choice = null;
  if (total > 0) {
    let roll = Math.random() * total;
    for (const c of cands) { roll -= c.w; if (roll <= 0) { choice = c.p; break; } }
    if (!choice) choice = cands[cands.length - 1].p;
  } else {
    // Same as the simulator: look past the window rather than abandon the
    // pick or take an illegal one.
    const board = _mockByMarket(_mock);
    choice = board.find((p) => _mockNeedCounts(counts, p.position, round))
             || board[0] || cands[0].p;
  }
  _mockTake(ti, choice);
}

function _mockTake(ti, player) {
  _mock.pool = _mock.pool.filter((p) => p !== player);
  _mock.rosters[ti].push(player);
  _mock.log.push({ pick: _mock.pick, team: ti, player });
  _mock.pick += 1;
}

function _mockAdvance() {
  const total = _mock.teams * _mock.rounds;
  while (_mock.pick < total) {
    if (_mockSkipped(_mock, _mock.pick)) { _mock.pick += 1; continue; }
    if (_mockPicker(_mock.pick, _mock.teams) === _mock.you) break;
    _mockCpuPick(_mockPicker(_mock.pick, _mock.teams));
  }
  _mockRender();
}

//: The best legal starting lineup, slot by slot — the judged eleven.
//: Kept as ONE function so the final screen's starters list and the
//: PPG it is scored on can never disagree.
function _mockLineup(roster) {
  const by = { QB: [], RB: [], WR: [], TE: [] };
  roster.forEach((p) => (by[p.position] || []).push(p));
  Object.values(by).forEach((l) => l.sort((a, b) => (b.proj || 0) - (a.proj || 0)));
  const starters = [];
  for (const [pos, want] of Object.entries(_mockFmt().slots)) {
    if (pos === "FLEX" || pos === "SFLEX") continue;
    for (let i = 0; i < want; i++) {
      starters.push([want > 1 ? pos + (i + 1) : pos, by[pos].shift() || null]);
    }
  }
  const flexPool = [...by.RB, ...by.WR, ...by.TE]
    .sort((a, b) => (b.proj || 0) - (a.proj || 0));
  for (let i = 0; i < (_mockFmt().slots.FLEX || 0); i++) {
    starters.push(["FLEX" + (i + 1), flexPool.shift() || null]);
  }
  // Superflex last, and it takes a quarterback if one is spare — the slot
  // is QB-eligible, which is the point of the format.
  for (let i = 0; i < (_mockFmt().slots.SFLEX || 0); i++) {
    const spare = [...by.QB, ...flexPool]
      .sort((a, b) => (b.proj || 0) - (a.proj || 0))[0] || null;
    if (spare) {
      const fi = flexPool.indexOf(spare);
      if (fi >= 0) flexPool.splice(fi, 1); else by.QB.shift();
    }
    starters.push(["SFLEX", spare]);
  }
  const chosen = new Set(starters.map(([, p]) => p).filter(Boolean));
  const bench = roster.filter((p) => !chosen.has(p));
  return { starters, bench,
           ppg: starters.reduce((s, [, p]) => s + (p ? p.proj || 0 : 0), 0) };
}

function _mockStartersPPG(roster) {
  return _mockLineup(roster).ppg;
}

/* THE ADVICE BAR ONLY EARNS ITS ROW WHEN IT DISAGREES WITH THE CARD.

   Ethan, 2026-08-20, circling the band under the hero: "it feels very
   crouded in the area i slecected." He was right and the cause was
   duplication rather than spacing. At pick 1.01 the bar read "Best value
   on the board: Christian McCaffrey (RB, VORP +13.6, Tier 1)" while the
   card two inches to its right showed McCaffrey, RB, +13.6, Tier 1. Two
   full-width bands were being spent saying one thing.

   So the bar is now about the DIFFERENCE. If you are looking at the best
   value and it also fills your thinnest slot, there is nothing to add and
   it does not render at all — the card is the answer. It reappears the
   moment you click somebody else, or when the board's best and your
   roster's need point at different men, which is exactly when a drafter
   wants a second opinion.

   Returns null for "nothing to say", which the caller renders as
   nothing rather than as an empty box. */
function _mockAdvice(selected) {
  const roster = _mock.rosters[_mock.you];
  const best = _mock.pool[0];
  if (!best) return null;
  const count = (pos) => roster.filter((p) => p.position === pos).length;
  const thin = ["RB", "WR", "TE", "QB"].find((pos) =>
    count(pos) < (_mockFmt().slots[pos] || 1));
  const bestThin = thin && _mock.pool.find((p) => p.position === thin);
  const parts = [];
  const looking = selected && selected.player !== best.player;
  if (looking) {
    const gap = (best.vorp || 0) - (selected.vorp || 0);
    parts.push(`You are looking at <b>${escapeHtml(selected.player)}</b>. The
      board’s best is <b>${escapeHtml(best.player)}</b>
      (${escapeHtml(best.position)}, +${(best.vorp || 0).toFixed(1)})${
      gap > 0.05 ? `, worth ${gap.toFixed(1)} more over replacement` : ""}.`);
  }
  if (bestThin && bestThin.player !== best.player
      && (!selected || bestThin.player !== selected.player)) {
    parts.push(`Your thinnest spot is ${thin} — best left there:
      <b>${escapeHtml(bestThin.player)}</b> (+${(bestThin.vorp || 0).toFixed(1)}).`);
  }
  return parts.length ? parts.join(" ") : null;
}

/* The keeper editor, in the setup panel. A player, the room that keeps
   him, and the round it costs — those three facts are the whole feature,
   and the round is the one people forget, which is why it is not
   optional here. */
function _mockKeeperHTML(teams) {
  const kit = _mockKit || {};
  const board = (kit.board || []);
  const rows = _mockKeepers.map((k, i) => {
    const p = board.find((x) => x.player === k.player);
    return `<div class="mk-keep-row">
      <span class="mk-keep-who"><b>${escapeHtml(k.player)}</b>${p
        ? ` <i>${escapeHtml(p.position)} · ${escapeHtml(p.team)}</i>`
        : ` <i class="mk-keep-gone">not on this board</i>`}</span>
      <span class="mk-keep-at">${k.team === 0 ? "You" : "Room " + (k.team + 1)}
        · round ${k.round}</span>
      <button class="btn ghost mk-keep-del" data-kdel="${i}"
        aria-label="Remove ${escapeAttr(k.player)}">Remove</button></div>`;
  }).join("");
  return `<details class="mk-keepers"${_mockKeepers.length ? " open" : ""}>
    <summary>Keepers${_mockKeepers.length ? ` (${_mockKeepers.length})` : ""}</summary>
    <p class="mk-keep-note">A keeper costs the round you name: that room
      does not pick in it, and the draft moves straight past the slot.
      That is the half a keeper toggle usually leaves out, and it is the
      half that changes when players come off the board.</p>
    ${rows ? `<div class="mk-keep-list">${rows}</div>` : ""}
    <div class="mk-keep-add">
      <input list="mk-keep-names" id="mk-keep-name" class="mk-sel"
             placeholder="Player" autocomplete="off">
      <datalist id="mk-keep-names">${board.slice(0, 150).map((p) =>
        `<option value="${escapeAttr(p.player)}">`).join("")}</datalist>
      <select id="mk-keep-team" class="mk-sel">
        <option value="0">You</option>
        ${Array.from({ length: Math.max(0, teams - 1) }, (_, i) =>
          `<option value="${i + 1}">Room ${i + 2}</option>`).join("")}
      </select>
      <select id="mk-keep-round" class="mk-sel">
        ${Array.from({ length: Math.max(1, _mockCfgRounds(_mockCfg,
            ((_mockKit || {}).board || []).length, teams).drafted) }, (_, i) =>
          `<option value="${i + 1}">Round ${i + 1}</option>`).join("")}
      </select>
      <button class="btn" id="mk-keep-add">Add</button>
    </div>
  </details>`;
}

/* What the keepers did to the draft, said once at the top of the room —
   a reader who set them up should not have to infer it from a board that
   is quietly four players shorter. */
function _mockKeeperNote(m) {
  const n = (m.keepers || []).length;
  if (!n) return "";
  const mine = m.keepers.filter((k) => k.team === m.you).length;
  const rounds = [...new Set(m.keepers.filter((k) => k.team === m.you)
    .map((k) => k.round))].sort((a, b) => a - b);
  return `<div class="mk-keep-banner">${n} keeper${n === 1 ? "" : "s"} off the
    board${mine ? ` — ${mine} of them yours, costing you round${
      rounds.length === 1 ? "" : "s"} ${rounds.join(", ")}` : ""}.</div>`;
}

/* ---- Byes -----------------------------------------------------------
   The one fact on the board. Everything else in the kit is a projection
   and can be argued with; the schedule is published. It decides whether
   the roster you just drafted has three starters missing in week eleven,
   and until now the room had no idea the concept existed.

   THE WARNING IS ABOUT STARTERS, not about the roster. Two backup tight
   ends sharing a bye costs nothing — you were never starting them. The
   count that matters is how many of your best eleven go dark at once, so
   that is what is counted. */
function _mockByeClash(roster) {
  const lineup = _mockLineup(roster);
  const weeks = {};
  for (const [, p] of lineup.starters) {
    if (p && p.bye) weeks[p.bye] = (weeks[p.bye] || 0) + 1;
  }
  return Object.entries(weeks)
    .map(([wk, n]) => ({ wk: +wk, n }))
    .filter((x) => x.n >= 3)
    .sort((a, b) => b.n - a.n);
}

function _mockByeHTML(roster) {
  const clash = _mockByeClash(roster);
  if (!clash.length) return "";
  return `<div class="mk-bye-warn">${clash.map((c) => `
    <span class="chip ${c.n >= 4 ? "down" : ""}"
      title="Starters sharing a bye. Measured in the season simulator on
             matched rosters, stacking three costs about a tenth of a win
             over fourteen weeks and roughly two points of play-off odds —
             worth avoiding at the margin, not worth reaching for.">
      Week ${c.wk}: <b>${c.n}</b> starters out</span>`).join("")}</div>`;
}

/* Cached per pick: the board only changes when somebody drafts, so
   re-running twenty thousand drafts on every re-render would burn a
   phone's battery to produce the identical number. */
function _mockSim() {
  if (!_mock) return null;
  if (_mock.sim && _mock.simAt === _mock.pick) return _mock.sim;
  _mock.sim = mockSurvival(_mock, MOCK_SIMS);
  _mock.simAt = _mock.pick;
  return _mock.sim;
}

/* ---- The cliff --------------------------------------------------------
   Every simulator worth copying flags a tier break, and for a good
   reason: inside a tier the differences are noise (the kit's own notes
   say so), so the only pick that ever really costs you is the last one
   before a step down. "Three tight ends left in tier two" is the sentence
   that changes a draft.

   OURS SAYS HOW LONG IT HAS, not just how many are left, because a count
   on its own does not answer the question being asked. Two left is
   comfortable if nobody takes one before your turn and an emergency if
   three rooms are about to. The Monte Carlo already knows which — it is
   the same run that produced the survival odds — so the cliff is reported
   as a count AND the chance it survives to you. */
function _mockTierCliff(sim) {
  if (!_mock) return [];
  const out = [];
  for (const pos of ["RB", "WR", "TE", "QB"]) {
    const left = _mock.pool.filter((p) => p.position === pos);
    if (!left.length) continue;
    const tier = left[0].tier;
    if (tier == null) continue;
    const inTier = left.filter((p) => p.tier === tier);
    // A tier with plenty in it is not a cliff, it is a shelf.
    if (inTier.length > 4) continue;
    // How likely is ANY of them to reach you? Independent is wrong —
    // rooms take at most one each — so the honest summary is the best
    // single survival chance in the tier, which is a floor on "something
    // is left" rather than a product that would read far too low.
    let best = null;
    if (sim) {
      for (const p of inTier) {
        const q = sim.survive.get(p.player);
        if (q != null && (best == null || q > best)) best = q;
      }
    }
    out.push({ pos, tier, n: inTier.length, survives: best });
  }
  return out.sort((a, b) => a.n - b.n);
}

function _mockCliffHTML(sim) {
  const rows = _mockTierCliff(sim).filter((c) => c.n <= 3);
  if (!rows.length) return "";
  return `<div class="mk-cliff">
    <div class="mk-plan-head">Tier about to break</div>
    ${rows.map((c) => `<span class="mk-plan-row">
      <b>${escapeHtml(c.pos)} tier ${c.tier}</b>
      <i>${c.n} left${c.n === 1 ? " — the last one" : ""}</i>
      <span class="mk-plan-q ${c.survives != null && c.survives < 0.35 ? "gone" : ""}">${
        c.survives == null ? "—" : Math.round(c.survives * 100) + "%"}</span></span>`).join("")}
    <p class="mk-wait-foot">Inside a tier the differences are noise, so the
      only pick that costs you is the last one before the step down. The
      percentage is the best chance any of them is still there at your next
      turn.</p>
  </div>`;
}

/* WHO TO PLAN ON, which is the answer the simulation exists to give.
   From the 1.01 seat every name on the best-available list is gone by
   your next turn, so a column of 0% is honest and useless on its own.
   The useful half is the other end of the same distribution: the best
   players who are actually likely to still be sitting there. */
function _mockPlanHTML(sim) {
  if (!sim || !_mock) return "";
  const likely = _mock.pool
    .map((p) => ({ p, q: sim.survive.get(p.player) || 0 }))
    .filter((x) => x.q >= 0.4)
    .slice(0, 5);
  if (!likely.length) return "";
  return `<div class="mk-plan">
    <div class="mk-plan-head">Likely still there</div>
    ${likely.map(({ p, q }) => `<span class="mk-plan-row">
      <b>${escapeHtml(p.player)}</b>
      <i>${escapeHtml(p.position)} · +${(p.vorp || 0).toFixed(1)}</i>
      <span class="mk-plan-q">${Math.round(q * 100)}%</span></span>`).join("")}
  </div>`;
}

/* THE RUN WARNING, which is the one output that changes what you do about
   a POSITION rather than about a player. Expected departures before your
   turn, from the same simulation. */
function _mockRunHTML(sim) {
  if (!sim) return "";
  const rows = Object.entries(sim.goneBy)
    .filter(([, v]) => v >= 0.8)
    .sort((a, b) => b[1] - a[1]);
  if (!rows.length) return "";
  return `<div class="mk-runs">${rows.map(([pos, v]) => `
    <span class="chip ${v >= 3 ? "down" : ""}" title="Expected number of ${escapeHtml(pos)}s taken across ${sim.sims.toLocaleString()} simulated drafts of the picks between now and your turn.">
      ${escapeHtml(pos)} <b>−${v.toFixed(1)}</b> before you</span>`).join("")}</div>`;
}

/* What the board is worth when it comes back to you. A range, not a
   point: the median alone reads as a promise about one draft. */
function _mockWaitHTML(sim) {
  if (!sim) return "";
  const spread = sim.bestP90 - sim.bestP10;
  return `<div class="card mk-wait">
    <div class="mk-wait-head">If you wait
      <span class="sub">— ${sim.sims.toLocaleString()} simulated drafts of the
      ${sim.gap} pick${sim.gap === 1 ? "" : "s"} between now and your turn</span></div>
    <div class="mk-wait-body">
      <span>Best value still on the board when it comes back:
        <b>+${sim.bestP50.toFixed(1)}</b> VORP typically${spread > 0.4
          ? `, between <b>+${sim.bestP10.toFixed(1)}</b> and
             <b>+${sim.bestP90.toFixed(1)}</b>` : ""}.</span>
    </div>
    ${_mockPlanHTML(sim)}
    ${_mockCliffHTML(sim)}
    ${_mockRunHTML(sim)}
    <p class="mk-wait-foot">Every room in this draft has its own build, and
      they keep it — the spread above is what those builds do to the board,
      not a random number. The percentages beside each player are how often
      he was still there.</p>
  </div>`;
}

/* ---- The season the roster plays -------------------------------------
   The draft Monte Carlo answers "who will be there". This answers the
   question that follows it and is the reason anyone drafts at all: SO
   WHAT? A starters-PPG number and a finish rank say the roster is good on
   the average week, and fantasy is not played on the average week — it is
   played fourteen times, head to head, with byes.

   BYES ARE WHY THIS IS WORTH SIMULATING RATHER THAN ADDING UP. A roster
   whose points are concentrated in three men who all sit in week eleven
   is a different team from one with the same total spread evenly, and no
   season-long average can tell them apart. Now that the board carries
   byes, the simulator can: a starter on his bye is replaced by the best
   bench player who is playing, exactly as a manager would.

   THE VARIANCE IS AN ASSUMPTION AND IS LABELLED AS ONE. We hold no weekly
   distributions here, so a week is drawn as the player's projection times
   a lognormal shock with a per-position spread. The numbers below are the
   received shape of fantasy scoring — quarterbacks are the steadiest
   thing on a roster, tight ends the least — and they are the one input
   here that is not measured. They are stated rather than buried because
   the win totals move with them. */
const MOCK_WEEK_CV = { QB: 0.35, RB: 0.55, WR: 0.60, TE: 0.65 };
const MOCK_SEASON_WEEKS = 14;
const MOCK_SEASON_SIMS = 4000;

/* A lognormal draw with the right mean: exp(N(mu, s)) has mean
   exp(mu + s^2/2), so mu is shifted down by half the variance. Without
   that correction every simulated week comes out ABOVE the projection and
   the whole league scores more than it should. */
function _mockWeekPoints(proj, cv, rnd) {
  if (!(proj > 0)) return 0;
  const s = Math.sqrt(Math.log(1 + cv * cv));
  // Box-Muller from two uniforms.
  const u1 = Math.max(1e-9, rnd()), u2 = rnd();
  const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  return proj * Math.exp(-0.5 * s * s + s * z);
}

/* The best legal line-up for ONE week, with the byes taken out. Reuses
   _mockLineup so the week's rules and the final screen's rules are the
   same rules — a season scored on a line-up the page never shows would
   be answering about a different team. */
function _mockWeekScore(roster, week, rnd) {
  const active = roster.filter((p) => p.bye !== week);
  const drawn = active.map((p) => ({
    ...p, proj: _mockWeekPoints(p.proj || 0,
                                MOCK_WEEK_CV[p.position] || 0.55, rnd),
  }));
  return _mockLineup(drawn).ppg;
}

/* Every room's season, head to head, many times over. Returns your record
   distribution rather than a single number: "9-5" is a story about one
   season and the same roster plays a range. */
function mockSeason(m, sims) {
  const rosters = m.rosters;
  const n = rosters.length;
  if (!rosters[m.you] || !rosters[m.you].length) return null;
  const wins = [];
  const rnd = _mockRng(0x5eed ^ (m.pick * 2654435761));
  let ran = 0;
  const t0 = (typeof performance === "object" ? performance.now() : Date.now());
  for (let s = 0; s < sims; s++) {
    let w = 0;
    for (let week = 1; week <= MOCK_SEASON_WEEKS; week++) {
      // A round-robin rotation, so every room plays a different opponent
      // each week rather than the same one fourteen times.
      const opp = (m.you + week) % n;
      if (opp === m.you) continue;
      const mine = _mockWeekScore(rosters[m.you], week, rnd);
      const theirs = _mockWeekScore(rosters[opp], week, rnd);
      if (mine > theirs) w += 1;
    }
    wins.push(w);
    ran = s + 1;
    if ((s & 127) === 0) {
      const dt = (typeof performance === "object" ? performance.now() : Date.now()) - t0;
      if (dt > MOCK_SIM_BUDGET_MS) break;
    }
  }
  if (!ran) return null;
  wins.sort((a, b) => a - b);
  const q = (f) => wins[Math.min(wins.length - 1, Math.floor(f * wins.length))];
  const mean = wins.reduce((a, b) => a + b, 0) / wins.length;
  // A play-off spot is the top half of the league, which is the ordinary
  // shape. Counted as "would this record usually make it" rather than
  // simulated bracket-by-bracket, and said that way on the page.
  const bar = Math.ceil(MOCK_SEASON_WEEKS * 0.55);
  const made = wins.filter((x) => x >= bar).length / wins.length;
  const hist = {};
  for (const x of wins) hist[x] = (hist[x] || 0) + 1;
  return { sims: ran, weeks: MOCK_SEASON_WEEKS, mean, p10: q(0.10),
           p50: q(0.50), p90: q(0.90), bar, made, hist };
}

function _mockSeasonHTML(m) {
  const r = mockSeason(m, MOCK_SEASON_SIMS);
  if (!r) return "";
  const top = Math.max(...Object.values(r.hist));
  const bars = Object.keys(r.hist).map(Number).sort((a, b) => a - b).map((w) => `
    <span class="mk-hist-col" title="${r.hist[w]} of ${r.sims.toLocaleString()} seasons finished ${w}-${r.weeks - w}">
      <i style="height:${(r.hist[w] / top * 100).toFixed(1)}%"></i>
      <b class="${w >= r.bar ? "in" : ""}">${w}</b></span>`).join("");
  return `<div class="section-title minor">The season this roster plays
      <span class="sub">— ${r.sims.toLocaleString()} simulated seasons of
      ${r.weeks} weeks, head to head against the rooms that just drafted,
      with byes taken out and the bench filling in.</span></div>
    <div class="card mk-season">
      <div class="mk-season-line">Typically <b>${r.p50}‑${r.weeks - r.p50}</b>,
        between <b>${r.p10}‑${r.weeks - r.p10}</b> and
        <b>${r.p90}‑${r.weeks - r.p90}</b>.
        <span class="mk-season-odds">${Math.round(r.made * 100)}% of seasons
        reach ${r.bar} wins</span></div>
      <div class="mk-hist">${bars}</div>
      <p class="mk-wait-foot">Weekly scoring is drawn around each player’s
        projection with a per-position spread — quarterbacks steadiest,
        tight ends least — which is the one input here that is not measured.
        The win totals move with it, so treat the shape as the finding and
        the exact percentage as an estimate.</p>
    </div>`;
}

/* ---- The grade ------------------------------------------------------
   Round-weighted value against where a player actually went, with the
   steals and the reaches named. Every simulator worth copying ends on
   this and ours ended on a PPG number with nothing to compare it to.

   VALUE IS MEASURED AGAINST THE BOARD, not against a letter somebody
   fitted: a pick is a steal by however far it outran the best player
   still available when it was made, in VORP. That is a fact about this
   draft rather than a grade about taste. */
function _mockGrade(m) {
  const board = new Map((_mockKit.board || []).map((p, i) => [p.player, i]));
  const mine = m.log.filter((e) => e.team === m.you);
  const marks = mine.map((e) => {
    const at = board.get(e.player.player);
    // Where he was on the board vs where he was taken overall.
    const edge = at == null ? 0 : (e.pick - at);
    return { ...e, at, edge };
  });
  const steals = marks.filter((x) => x.edge >= 8)
    .sort((a, b) => b.edge - a.edge).slice(0, 3);
  const reaches = marks.filter((x) => x.edge <= -8)
    .sort((a, b) => a.edge - b.edge).slice(0, 3);
  const net = marks.reduce((s, x) => s + x.edge, 0) / Math.max(1, marks.length);
  return { marks, steals, reaches, net };
}

function _mockGradeHTML(m) {
  const g = _mockGrade(m);
  if (!g.marks.length) return "";
  const row = (x, kind) => `<div class="mk-log-row">
    <span class="chip ${kind === "steal" ? "up" : "down"}">${
      kind === "steal" ? "+" : ""}${x.edge}</span>
    <span class="mk-id"><b>${escapeHtml(x.player.player)}</b>
      <span class="mk-meta">${escapeHtml(x.player.position)} · taken
        ${Math.floor(x.pick / m.teams) + 1}.${String(x.pick % m.teams + 1).padStart(2, "0")}
        · board rank ${x.at == null ? "—" : x.at + 1}</span></span></div>`;
  return `<div class="section-title minor">Where you won and lost value
      <span class="sub">— each pick against where that player sat on the
      kit’s own board. Positive means he was still there later than his
      rank said he should be.</span></div>
    <div class="card mk-panel">
      <div class="mk-log-row"><span class="mk-meta">Average
        <b style="color:${g.net >= 0 ? "var(--good)" : "var(--warn)"}">${
          g.net >= 0 ? "+" : ""}${g.net.toFixed(1)}</b> slots of value per pick
        across ${g.marks.length}.</span></div>
      ${g.steals.map((x) => row(x, "steal")).join("")}
      ${g.reaches.map((x) => row(x, "reach")).join("")}
      ${!g.steals.length && !g.reaches.length ? `<div class="mk-log-row">
        <span class="mk-meta">No pick ran more than eight slots from its board
        rank — a draft taken straight off the board.</span></div>` : ""}
    </div>`;
}

/* ============================ THE DRAFT ROOM ============================
   Ethan sent a render for this page on 2026-08-20 and asked for it to be
   matched. Most of it is built below. Three things in it are not, and the
   reasons are worth keeping next to the code that would otherwise grow
   them back:

   * A COUNTDOWN CLOCK ("00:47"). Our rooms are not people — a CPU pick is
     computed in under a millisecond. A ticking clock would be an
     animation pretending there is somebody on the other end, and the
     first time a reader let it run out and nothing happened they would
     know. The seat on the clock is real and is shown; the countdown is
     not.
   * "MATCHUP VS OPPONENT" — a panel of opposing-defence ranks. There is
     no opponent in a draft. That panel belongs to a start/sit screen in
     October, and filling it here would mean inventing a Week 1 defence
     for a player nobody has drafted yet. Its slot is given to the
     question a drafter actually has: will he still be there next turn.
   * "CONFIDENCE 9.2/10 — LOCK". No. The site's own standing copy is that
     every number here is a probability and not a promise, and "LOCK" is
     the exact word that sentence exists to keep off the page. There is no
     fitted confidence scale behind a fantasy projection, so a 9.2 would
     be a decoration with a decimal point.

   Everything else in the render is here and every number in it is
   computed: the pick, the seat, the tier, the market's own slot for him,
   our disagreement with it, and a floor and ceiling drawn from the SAME
   lognormal the season simulator runs on. */

//: Position tone, matching the render's chips. Own tokens rather than
//: reusing the good/bad semantic pair — a running back is not "good" and
//: a quarterback is not "a warning".
const MOCK_POS_TONE = { QB: "qb", RB: "rb", WR: "wr", TE: "te" };

function _mockPosChip(pos) {
  return `<span class="mk-pos mk-pos-${MOCK_POS_TONE[pos] || "x"}">${
    escapeHtml(pos || "—")}</span>`;
}

/* A pick number as a drafter says it: round dot slot, zero-padded. */
function _mockPickNo(i, teams) {
  return `${Math.floor(i / teams) + 1}.${String(i % teams + 1).padStart(2, "0")}`;
}

/* WHAT A SEASON OF HIM LOOKS LIKE, not just its average. Same lognormal
   and the same per-position spread the season simulator uses — one rule,
   two callers, so a floor shown on this card cannot describe a different
   player from the one the season sim plays. Seeded off the name so the
   card does not flicker a new floor on every re-render.

   `weeks` is the fantasy regular season, so these are comparable with the
   season panel's win totals rather than with a 17-game total. */
const MOCK_SPREAD_SIMS = 1200;
function _mockSpread(p, weeks = MOCK_SEASON_WEEKS) {
  const proj = +p.proj || 0;
  if (!(proj > 0)) return null;
  const cv = MOCK_WEEK_CV[p.position] || 0.55;
  let seed = 0;
  for (const ch of String(p.player || "")) seed = (seed * 31 + ch.charCodeAt(0)) | 0;
  const rnd = _mockRng(seed ^ 0x9e37);
  const totals = [];
  let goodWeeks = 0, allWeeks = 0;
  for (let s = 0; s < MOCK_SPREAD_SIMS; s++) {
    let t = 0;
    for (let w = 0; w < weeks; w++) {
      const pts = _mockWeekPoints(proj, cv, rnd);
      t += pts;
      allWeeks += 1;
      // "Consistency" with a stated meaning: how often a week clears
      // three-quarters of his own projection. A percentage with no
      // definition is the kind of number this site does not print.
      if (pts >= proj * 0.75) goodWeeks += 1;
    }
    totals.push(t);
  }
  totals.sort((a, b) => a - b);
  const at = (q) => totals[Math.min(totals.length - 1,
    Math.max(0, Math.round(q * (totals.length - 1))))];
  return {
    weeks,
    season: proj * weeks,
    floor: at(0.10),
    ceiling: at(0.90),
    consistency: allWeeks ? goodWeeks / allWeeks : 0,
  };
}

/* OUR BOARD AGAINST THE ROOM'S. `_mockMarketOrder` is not a decoration
   here — it is the order the CPU rooms actually draft in, so the gap
   between it and our VORP order is a real disagreement rather than a
   comparison with a number nobody uses. Positive means we rate him above
   where this room will take him. */
function _mockEdge(m, p) {
  // m.market is a Map of player -> market slot, built once in _mockStart.
  // It is NOT an array: reading it with findIndex returns -1 for
  // everybody, which silently deletes this whole panel rather than
  // failing, so the shape is asserted by using the Map's own accessor.
  const mkt = m.market && typeof m.market.get === "function"
    ? m.market.get(p.player) : undefined;
  const mine = _mockOurRank(m, p);
  if (mine == null || mkt == null) return null;
  return { ours: mine, market: mkt, slots: mkt - mine };
}

/* Our own board position for a player — his index in the VORP order the
   kit publishes, which is what m.pool is sorted by. Computed against the
   FULL board rather than what is left, so the number does not improve
   every time somebody else is drafted. */
function _mockOurRank(m, p) {
  const all = m.all || m.pool;
  const i = all.findIndex((x) => x.player === p.player);
  return i < 0 ? null : i;
}

/* The reasons, derived. Every line is a number off this player's own row
   or off the simulation — nothing here is a sentence somebody wrote about
   a player they liked. Lines whose input is missing are absent rather
   than filled with a plausible default. */
function _mockWhy(m, p, sim, spread) {
  const out = [];
  const fmt = _mockFmt();
  if (p.vorp != null) {
    out.push(`<b>+${(+p.vorp).toFixed(1)} over replacement</b> — the best
      ${escapeHtml(p.position)} your league-mates can have for nothing scores
      that much less, in ${escapeHtml(fmt.name)}.`);
  }
  if (p.tier != null) {
    const left = m.pool.filter((x) => x.position === p.position
      && x.tier === p.tier).length;
    out.push(`<b>Tier ${p.tier}</b> at the position, with ${left} of that tier
      still on the board — inside a tier the differences are noise, so the
      cost is the last one before the step down.`);
  }
  const e = _mockEdge(m, p);
  if (e && Math.abs(e.slots) >= 3) {
    out.push(e.slots > 0
      ? `<b>We rate him ${e.slots} slots above the room</b> — our board has
         him ${e.ours + 1}, the rooms draft him around ${e.market + 1}.`
      : `<b>The room rates him ${-e.slots} slots above us</b> — they draft him
         around ${e.market + 1}, our board has him ${e.ours + 1}. Taking him
         here is paying their price, not ours.`);
  }
  if (spread) {
    out.push(`<b>${Math.round(spread.consistency * 100)}% of weeks</b> clear
      three-quarters of his projection across ${MOCK_SPREAD_SIMS.toLocaleString()}
      simulated seasons — ${escapeHtml(p.position)}s carry a
      ${MOCK_WEEK_CV[p.position] || 0.55} weekly spread, which is an assumption
      and the only one on this card.`);
  }
  if (sim) {
    const sv = sim.survive.get(p.player);
    if (sv != null) {
      out.push(sv >= 0.75
        ? `<b>${Math.round(sv * 100)}% to still be here next turn</b> across
           ${sim.sims.toLocaleString()} simulated drafts — this pick can wait.`
        : `<b>Only ${Math.round(sv * 100)}% to survive to your next turn</b>
           across ${sim.sims.toLocaleString()} simulated drafts — a later round
           probably cannot give him back.`);
    }
  }
  if (p.source === "market") {
    out.push(`<b>No last-season usage.</b> He sits at the market’s own draft
      rank and carries the points our board shows there, so this row is the
      room’s read rather than ours.`);
  }
  if (p.bye) out.push(`<b>Bye week ${p.bye}</b>, off the published schedule.`);
  return out;
}

/* The card the render puts at the centre of the page. */
function _mockPlayerCardHTML(m, p, sim) {
  if (!p) return "";
  const spread = _mockSpread(p);
  const e = _mockEdge(m, p);
  const inj = injFind("nfl", p.player);
  const tierName = p.tier === 1 ? "Elite" : p.tier === 2 ? "Strong"
    : p.tier === 3 ? "Solid" : "Depth";
  const why = _mockWhy(m, p, sim, spread);
  const sv = sim ? sim.survive.get(p.player) : null;
  const metric = (k, v, sub) => `<div class="mk-metric"><span class="k">${k}</span>
    <span class="v">${v}</span>${sub ? `<span class="s">${sub}</span>` : ""}</div>`;
  return `
  <div class="card mk-card">
    <div class="mk-card-top">
      ${playerAvatar(p.player, p.team, { size: 92, map: nflMap(), headshot: p.headshot })}
      <div class="mk-card-id">
        <h3>${escapeHtml(p.player)}</h3>
        <div class="mk-card-sub">${escapeHtml(p.position)} · ${nflName(p.team)}
          ${teamMark(p.team, 18, nflMap(), "nfl")}</div>
        <div class="mk-badges">
          <span class="mk-badge mk-pos-${MOCK_POS_TONE[p.position] || "x"}">${
            escapeHtml(tierName)} ${escapeHtml(p.position)}</span>
          ${p.source === "market" ? `<span class="mk-badge mk-badge-mut">market’s number</span>` : ""}
          ${inj ? `<span class="mk-badge mk-badge-warn">${escapeHtml(inj.status)}</span>` : ""}
        </div>
        <div class="mk-card-nums">
          ${metric("Room takes him", e ? _mockPickNo(e.market, m.teams) : "—",
                   "at this league size")}
          ${metric("Projection", spread
            ? `${Math.round(spread.season)}` : `${(+p.proj || 0).toFixed(1)}`,
            spread ? `points over ${spread.weeks} weeks` : "per game")}
          ${metric("Tier", p.tier != null ? `Tier ${p.tier}` : "—",
                   `${escapeHtml(p.position)}${p.pos_rank || ""} on our board`)}
        </div>
      </div>
      ${e ? `<div class="mk-edge ${e.slots >= 0 ? "up" : "down"}">
        <span class="k">QELLYS EDGE</span>
        <span class="v">${e.slots >= 0 ? "+" : "−"}${Math.abs(e.slots)}</span>
        <span class="s">slots ${e.slots >= 0 ? "above" : "below"} where this
          room drafts him</span></div>` : ""}
    </div>
  </div>
  <div class="mk-detail">
    <div class="card mk-panel mk-outlook">
      <div class="mk-h">Key numbers</div>
      <div class="mk-kv"><span>Projected</span><b>${(+p.proj || 0).toFixed(1)} PPG</b></div>
      ${spread ? `
      <div class="mk-kv"><span>Floor · 10th pct</span><b>${Math.round(spread.floor)}</b></div>
      <div class="mk-kv"><span>Ceiling · 90th pct</span><b>${Math.round(spread.ceiling)}</b></div>
      <div class="mk-kv"><span>Weeks at 75%+</span><b>${Math.round(spread.consistency * 100)}%</b></div>` : ""}
      <div class="mk-kv"><span>Over replacement</span><b>+${(+p.vorp || 0).toFixed(1)}</b></div>
      ${p.rec_pg != null ? `<div class="mk-kv"><span>Receptions</span><b>${p.rec_pg}/gm</b></div>` : ""}
      ${p.bye ? `<div class="mk-kv"><span>Bye</span><b>Week ${p.bye}</b></div>` : ""}
      <p class="mk-fine">Floor and ceiling are the 10th and 90th percentile of
        ${MOCK_SPREAD_SIMS.toLocaleString()} simulated seasons, drawn from the same
        weekly spread the season panel runs on.</p>
    </div>
    <div class="card mk-panel mk-survive">
      <div class="mk-h">Will he last?</div>
      ${sv != null ? `
        <div class="mk-svbig ${sv >= 0.75 ? "up" : sv >= 0.4 ? "warn" : "down"}">${
          Math.round(sv * 100)}%</div>
        <div class="mk-svsub">still on the board at your next turn, across
          ${sim.sims.toLocaleString()} simulated drafts of the picks in between</div>
        <div class="mk-svbar"><i style="width:${(sv * 100).toFixed(1)}%"></i></div>`
      : `<p class="mk-fine">The survival model runs on your own picks. It has
          nothing to say while another room is on the clock.</p>`}
      <p class="mk-fine">The render this page was built from had an
        opposing-defence panel here. There is no opponent in a draft, so this
        answers the question a drafter actually has instead.</p>
    </div>
    <div class="card mk-panel mk-trend" id="mk-trend"
         data-mktrend="${escapeAttr(p.player)}">
      <div class="mk-h">Last season, week by week</div>
      <p class="mk-fine">Loading his game log\u2026</p>
    </div>
    <div class="card mk-panel mk-why">
      <div class="mk-h">Why he is worth the pick</div>
      <ul class="mk-whylist">${why.map((w) => `<li>${iconMark("check", 14)}<span>${w}</span></li>`).join("")}</ul>
      ${inj ? `<div class="mk-injline" style="color:${injTone(inj.status)}">
        ${escapeHtml(inj.status)}${inj.note ? ` — ${escapeHtml(inj.note)}` : ""}</div>`
        : `<div class="mk-injline mk-injok">No designation on the injury report.</div>`}
    </div>
  </div>`;
}

function mockDraftHTML() {
  const kit = _mockKit || {};
  if (!(kit.board || []).length) {
    return `<div class="empty">The mock draft drafts from the kit\u2019s own
      board, and this build has none yet — it fills with the season\u2019s
      first projections.</div>`;
  }
  if (!_mock) return _mockSetupHTML(kit);
  const m = _mock;
  const total = m.teams * m.rounds;
  const round = Math.floor(m.pick / m.teams) + 1;
  const yourTurn = m.pick < total && _mockPicker(m.pick, m.teams) === m.you;
  const face = (p, size) => playerAvatar(p.player, p.team,
    { size, map: nflMap(), headshot: p.headshot });
  const idBlock = (p, meta) => `
    <span class="mk-id" data-dossier="${escapeAttr(p.player)}"><b>${escapeHtml(p.player)}</b>${injTag("nfl", p.player)}
      <span class="mk-meta">${teamMark(p.team, 14, nflMap(), "nfl")}
        ${escapeHtml(p.team)} · ${escapeHtml(p.position)}${
        p.bye ? ` · <span class="mk-bye">bye ${p.bye}</span>` : ""}${meta}</span></span>`;

  if (m.pick >= total) {
    const scores = m.rosters.map((r, i) => ({ i, ppg: _mockStartersPPG(r) }))
      .sort((a, b) => b.ppg - a.ppg);
    const place = scores.findIndex((s) => s.i === m.you) + 1;
    const yours = scores.find((s) => s.i === m.you);
    const lineup = _mockLineup(m.rosters[m.you]);
    const starterRow = ([slot, p]) => `
      <div class="mk-log-row">
        <span class="chip mk-slotchip">${escapeHtml(slot)}</span>
        ${p ? face(p, 28) + idBlock(p, ` · proj ${p.proj}`)
            : `<span class="mk-meta">— nobody drafted for this slot</span>`}
      </div>`;
    return `<div class="section-title">Draft complete</div>
      <div class="stats">
        <div class="tile"><div class="k">Your starters</div>
          <div class="v">${yours.ppg.toFixed(1)}</div>
          <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">projected PPG</div></div>
        <div class="tile"><div class="k">Finish</div>
          <div class="v">${place} of ${m.teams}</div>
          <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">by projected starters</div></div>
      </div>
      ${_mockByeHTML(m.rosters[m.you])}
      <div class="section-title minor">Your starting lineup</div>
      <div class="card mk-panel">${lineup.starters.map(starterRow).join("")}</div>
      ${lineup.bench.length ? `<div class="section-title minor">Bench</div>
      <div class="card mk-panel">${lineup.bench.map((p) => `
        <div class="mk-log-row">${face(p, 28)}${idBlock(p, ` · proj ${p.proj}`)}</div>`).join("")}</div>` : ""}
      ${_mockSeasonHTML(m)}
      ${_mockGradeHTML(m)}
      <button class="btn" id="mk-again" style="margin-top:12px">Draft again</button>`;
  }

  const sim = _mockSim();
  // THE CHEAT SHEET ORDERS THE POOL. Our board (VORP) or the market's
  // order (what the room pays) — the reader chose which list to draft
  // from, and the list, the default card and the auto-pick all read it.
  const sheet = _mockSheet(m);
  /* `avail` (the top twelve with a Draft button) and `recent` (the last
     round's picks) were built here every render and never placed. They
     are the pre-redesign versions of `poolList` and `boardList` below —
     the three-column draft room replaced both and left these computing
     face images and survival odds for twelve players, per keystroke,
     into a string nobody read. Drafting itself was never affected: the
     live button is `mk-draftbtn` on the selected-player card and the
     click handler matches on `data-mkp`, which both lists carry. */
  const roster = m.rosters[m.you].map((p) => `
    <div class="mk-log-row">${face(p, 28)}${idBlock(p, ` · proj ${p.proj}`)}
      <span class="chip">${escapeHtml(p.position)}</span></div>`).join("");
  // A draft room reads left to right: what is on the clock, what is
  // available, what you already have. Three columns on a desktop, one
  // stack on a phone — the board first either way, because that is the
  // thing you are choosing from.
  const onClock = yourTurn ? "You are on the clock"
    : `${_mockRoomName(m, _mockPicker(m.pick, m.teams))} is picking`;

  /* THE SELECTED PLAYER. Defaults to the best available, so the card is
     never empty and the page opens on the pick it would recommend.
     Falls back the moment the selection is drafted by somebody else —
     a card describing a man who is off the board is worse than no card. */
  let selected = m.pool.find((x) => x.player === _mockSel) || sheet[0];
  const until = _mockPicksUntil(m);
  const advice = yourTurn ? _mockAdvice(selected) : null;

  /* EVERY PICK MADE, newest last, as a drafter reads a board. The render
     showed a scrolling list of the round in progress; this is the same
     list, and it keeps going. */
  const boardList = m.log.length ? m.log.slice().reverse().map((e) => `
    <div class="mk-brow${e.team === m.you ? " you" : ""}">
      <span class="mk-bpick">${_mockPickNo(e.pick, m.teams)}</span>
      <span class="mk-bteam" title="${escapeAttr(_mockRoomTitle(m, e.team))}">${
        escapeHtml(_mockRoomName(m, e.team))}</span>
      ${teamMark(e.player.team, 16, nflMap(), "nfl")}
      <span class="mk-bname" data-mksel="${escapeAttr(e.player.player)}">${
        escapeHtml(e.player.player)}</span>
      ${_mockPosChip(e.player.position)}
    </div>`).join("")
    : `<div class="mk-brow"><span class="mk-meta">No picks yet — the board
        fills as the room drafts.</span></div>`;

  const poolList = sheet.slice(0, 40).map((pl) => {
    const sv = sim ? sim.survive.get(pl.player) : null;
    return `<div class="mk-brow mk-poolrow${pl.player === selected.player ? " sel" : ""}"
        data-mksel="${escapeAttr(pl.player)}">
      ${playerAvatar(pl.player, pl.team, { size: 24, map: nflMap(), headshot: pl.headshot })}
      <span class="mk-bname">${escapeHtml(pl.player)}${injTag("nfl", pl.player)}</span>
      ${_mockPosChip(pl.position)}
      <span class="mk-bvorp">+${(pl.vorp || 0).toFixed(1)}</span>
      ${sv != null ? `<span class="mk-bsv ${sv >= 0.75 ? "up" : sv >= 0.4 ? "warn" : "down"}">${
        Math.round(sv * 100)}%</span>` : ""}
    </div>`;
  }).join("");

  const rosterList = m.rosters[m.you].length ? m.rosters[m.you].map((pl) => `
    <div class="mk-brow" data-mksel="${escapeAttr(pl.player)}">
      ${playerAvatar(pl.player, pl.team, { size: 24, map: nflMap(), headshot: pl.headshot })}
      <span class="mk-bname">${escapeHtml(pl.player)}</span>
      ${_mockPosChip(pl.position)}
      <span class="mk-bvorp">${(pl.proj || 0).toFixed(1)}</span>
    </div>`).join("")
    : `<div class="mk-brow"><span class="mk-meta">Empty until your first pick.</span></div>`;

  const tab = (key, label) => `<button class="mk-tab${
    _mockTab === key ? " active" : ""}" data-mktab="${key}" type="button">${label}</button>`;
  const panel = _mockTab === "pool" ? poolList
    : _mockTab === "roster" ? rosterList : boardList;

  return `
    <div class="mk-hero">
      <div class="mk-hero-id">
        <div class="mk-hero-title">${iconMark("trophy", 26)} Mock draft</div>
        <div class="mk-hero-sub">${m.teams} teams · ${escapeHtml(_mockFmt().name)}
          · ${escapeHtml(MOCK_DRAFT_TYPES[m.type] || "Snake")}
          · ${m.rounds} rounds${m.roundsInfo && m.roundsInfo.skipped
            ? ` of ${m.roundsInfo.league}` : ""} · seat ${m.you + 1}</div>
      </div>
      <div class="mk-hero-stats">
        <div class="mk-hs"><span class="k">Pick</span>
          <span class="v">${_mockPickNo(m.pick, m.teams)}</span></div>
        <div class="mk-hs"><span class="k">Round</span>
          <span class="v">${round}<i>/${m.rounds}</i></span></div>
        <div class="mk-hs"><span class="k">Overall</span>
          <span class="v">${m.pick + 1}<i>/${total}</i></span></div>
        <div class="mk-hs ${yourTurn ? "you" : ""}"><span class="k">On the clock</span>
          <span class="v">${escapeHtml(_mockRoomName(m, _mockPicker(m.pick, m.teams)))}</span>
          <span class="s">${
            until.onClock ? (m.cfg && m.cfg.clock
              ? `<span id="mk-clock" class="mk-clock">${m.cfg.clock}s left</span>`
              : "it is your pick")
            : until.picks == null ? "no turn left this draft"
            : until.picks === 1 ? `you are up next \u2014 at ${_mockPickNo(until.next, m.teams)}`
            : `${until.picks} picks until you \u2014 at ${_mockPickNo(until.next, m.teams)}`}</span></div>
      </div>
      <div class="mk-prog"><i style="width:${(m.pick / total * 100).toFixed(1)}%"></i></div>
    </div>
    ${_mockKeeperNote(m)}
    ${yourTurn && advice ? `<div class="card mk-advice">
      <div class="mk-advice-head">Worth a second look</div>
      <div>${advice}</div></div>` : ""}
    <div class="mk-stage">
      <div class="mk-left">
        <div class="mk-tabs">${tab("pool", "Player pool")}${
          tab("board", "Draft board")}${tab("roster", "My roster")}</div>
        <div class="card mk-panel mk-list">${panel}</div>
      </div>
      <div class="mk-right">
        ${_mockPlayerCardHTML(m, selected, sim)}
        <button class="btn primary mk-draftbtn" data-mkp="${escapeAttr(selected.player)}"
          ${yourTurn ? "" : "disabled"}>${yourTurn
            ? `Draft ${escapeHtml(selected.player)}`
            : until.picks == null
              ? `${escapeHtml(onClock)} — your draft is done`
              : `${escapeHtml(onClock)} — ${until.picks} pick${
                  until.picks === 1 ? "" : "s"} until you`}</button>
      </div>
    </div>
    ${yourTurn ? _mockWaitHTML(sim) : ""}
    ${_mockByeHTML(m.rosters[m.you])}
    <button class="btn" id="mk-reset" style="margin-top:12px">Abandon this draft</button>`;
}

/* THE SETUP PANEL — two cards, the way FantasyPros lays its own out
   (Ethan, 2026-09-08): LEAGUE SETTINGS, then MOCK DRAFT SETTINGS, then
   keepers, then the button. Every control writes `_mockCfg` and survives
   a reload; the draft reads a frozen copy when it starts. */
function _mockStep(key, value, lo, hi, opts) {
  const o = opts || {};
  return `<span class="mk-step" data-mkstep="${key}">
    <button type="button" class="mk-step-btn" data-mkd="-1" aria-label="Fewer"
      ${value <= lo ? "disabled" : ""}>\u2212</button>
    <b>${o.label ? o.label(value) : value}</b>
    <button type="button" class="mk-step-btn" data-mkd="1" aria-label="More"
      ${value >= hi ? "disabled" : ""}>+</button></span>`;
}

function _mockSelect(id, options, value) {
  return `<select id="${id}" class="mk-sel mk-sel-row">${options.map(([v, label]) =>
    `<option value="${escapeAttr(String(v))}"${String(v) === String(value) ? " selected" : ""}>${
      escapeHtml(label)}</option>`).join("")}</select>`;
}

function _mockSetupHTML(kit) {
  const c = _mockCfg;
  const board = (kit || _mockKit || {}).board || [];
  const rounds = _mockCfgRounds(c, board.length, c.teams);
  const ordinal = (n) => `${n}${n % 10 === 1 && n !== 11 ? "st"
    : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"}`;
  const row = (ic, label, control, sub) => `<div class="mk-row">
    <span class="mk-row-k">${icon(ic, 15)} <span>${label}${
      sub ? `<i class="mk-row-sub">${sub}</i>` : ""}</span></span>
    <span class="mk-row-v">${control}</span></div>`;
  const slotWord = { QB: "Quarterback", RB: "Running back", WR: "Wide receiver",
                     TE: "Tight end", FLEX: "Flex (WR/RB/TE)",
                     SFLEX: "Superflex (QB/WR/RB/TE)", K: "Kicker", DST: "Defence",
                     BN: "Bench" };
  const rosterRows = Object.keys(slotWord).map((k) => `<div class="mk-row mk-row-slot">
    <span class="mk-row-k"><span>${slotWord[k]}${k === "K" || k === "DST"
      ? `<i class="mk-row-sub">on the line, not drafted here</i>` : ""}</span></span>
    <span class="mk-row-v">${_mockStep("roster." + k, c.roster[k], 0, MOCK_ROSTER_MAX[k])}</span>
  </div>`).join("");
  const presets = Object.entries(MOCK_PRESETS).map(([k, p]) =>
    `<button type="button" class="chip mk-preset${
      c.scoring === p.scoring && c.tePrem === p.tePrem
      && Object.keys(p.roster).every((s) => c.roster[s] === p.roster[s]) ? " active" : ""}"
      data-mkpreset="${k}">${escapeHtml(p.name)}</button>`).join("");
  const sleeper = (typeof localStorage !== "undefined" && localStorage.getItem("ff_user"))
    ? `<button type="button" class="btn mk-league-btn" id="mk-use-league">${
        icon("trophy", 14)} Use my Sleeper league</button>
       <span class="mk-row-sub" id="mk-league-note">${
        _mockLeagueNote ? escapeHtml(_mockLeagueNote) : "settings, seat and draft type from your league"}</span>`
    : `<span class="mk-row-sub">Link your Sleeper account on the Account page and
        the league\u2019s own settings, seat and draft type fill this in.</span>`;
  return `<div class="section-title">Mock draft
      <span class="sub">— against ${c.teams - 1} CPU rooms with builds of their
      own, drafted from the kit\u2019s own ${board.length}-player board</span></div>
    <div class="mk-settings">
      <div class="card mk-setcard">
        <div class="mk-setcard-head">League settings</div>
        <div class="mk-row mk-row-league"><span class="mk-row-k">${icon("trophy", 15)}
          <span>Select league</span></span><span class="mk-row-v mk-row-v-wrap">${sleeper}</span></div>
        ${_mockMatesHTML(c)}
        <div class="mk-presets">${presets}</div>
        ${row("list", "Scoring", _mockSelect("mk-scoring",
          Object.entries(MOCK_SCORING).map(([k, s]) => [k, s.name]), c.scoring))}
        ${row("list", "TE premium", _mockSelect("mk-teprem",
          [[0, "None"], [0.5, "+0.5 per catch"], [1, "+1.0 per catch"]], c.tePrem),
          "on the tight end\u2019s real receptions")}
        ${row("target", "Draft type", _mockSelect("mk-type",
          Object.entries(MOCK_DRAFT_TYPES), c.draftType))}
        ${row("calendar", "Teams", _mockStep("teams", c.teams, MOCK_TEAMS_RANGE[0], MOCK_TEAMS_RANGE[1]))}
        <details class="mk-roster"${c.roster.K || c.roster.DST ? "" : " open"}>
          <summary class="mk-row"><span class="mk-row-k">${icon("book", 15)}
            <span>Roster<i class="mk-row-sub">${escapeHtml(_mockRosterLine(c))}</i></span></span>
            <span class="mk-row-v mk-row-chev">\u203a</span></summary>
          ${rosterRows}
          <p class="mk-keep-note">${rounds.league} rounds in this league, ${
            rounds.drafted} drafted here${rounds.skipped
              ? ` — the kit\u2019s board projects no kickers or defences, so those
                 ${rounds.skipped} round${rounds.skipped === 1 ? "" : "s"} are not
                 simulated rather than drafted as blanks`
              : ""}${rounds.drafted < rounds.wanted
              ? `; the board is ${board.length} deep, which at ${c.teams} teams
                 carries ${rounds.drafted} rounds` : ""}.</p>
        </details>
      </div>
      <div class="card mk-setcard">
        <div class="mk-setcard-head">Mock draft settings</div>
        ${row("target", "Draft position", _mockStep("slot", c.slot, 1, c.teams,
          { label: ordinal }))}
        ${row("book", "Cheat sheet", _mockSelect("mk-sheet",
          Object.entries(MOCK_SHEETS), c.sheet),
          c.sheet === "market" ? "the pool sorts the way the room drafts"
            : "the pool sorts by value over replacement")}
        ${row("clock", "Pick clock", _mockSelect("mk-clock",
          MOCK_CLOCKS.map((s) => [s, s ? `${s} seconds` : "No clock"]), c.clock),
          c.clock ? "runs on your picks; the cheat sheet drafts for you at zero"
            : "your picks wait for you")}
        ${row("people", "Room chaos", _mockSelect("mk-chaos",
          [[10, "Chalk"], [35, "Realistic"], [65, "Wild"], [100, "Chaos"]], c.chaos),
          "how far the rooms stray from the board")}
        ${_mockKeeperHTML(c.teams)}
      </div>
    </div>
    <button class="btn primary mk-startbtn" id="mk-start">Start the draft
      <span class="mk-startsub">${c.teams} teams · ${escapeHtml(_mockCfgLabel(c))} ·
        ${escapeHtml(MOCK_DRAFT_TYPES[c.draftType])} · pick ${c.slot} · ${rounds.drafted} rounds</span></button>
    <div class="card" style="padding:14px 18px;margin-top:14px">
      <p style="color:var(--text-mute);font-size:var(--fs-sm);margin:0 0 8px">
        Every rival room is dealt one of ${MOCK_ARCHETYPES.length} builds and
        keeps it all draft — Zero RB, Hero RB, WR hoarder, early QB, elite
        TE and the rest — so the board falls differently every time and a
        run on a position is sometimes real. <b>Room chaos</b> sets how far
        they will stray from the board to do it. With your Sleeper league
        read, each room is dealt the build its manager actually drafted
        last time \u2014 measured from their picks, not declared \u2014 and
        sits in the seat the league\u2019s draft order gives them.</p>
      <p style="color:var(--text-mute);font-size:var(--fs-sm);margin:0 0 8px">
        <b>Scoring</b> and the <b>roster</b> are set apart, the way a league
        sets them. A superflex slot starts a second quarterback, so the
        position stops having a free replacement and goes in the first
        round instead of the tenth. A TE premium pays per tight-end catch,
        computed from real receptions rather than a guessed catch rate.
        Half PPR and standard take the same catches back off the board\u2019s
        PPR numbers. Each setting re-derives every projection, every VORP
        and the order the rooms draft in — nothing here is a re-skin.</p>
      <p style="color:var(--text-mute);font-size:var(--fs-sm);margin:0">
        On every one of your picks the draft ahead of you is simulated
        ${MOCK_SIMS.toLocaleString()} times, and each available player
        carries how often he was still there when it came back to you.
        Your finished roster is judged on its starters\u2019 projected PPG
        against the room, and on where each pick beat or missed the board
        — not on a letter grade nobody fitted.</p>
    </div>`;
}

/* ---- "Select league": the settings from YOUR Sleeper league ------------
   The screenshot's top row, and the line under it: "More realistic mock
   drafts using your league's settings." A league object carries the team
   count, the roster slots and the scoring; its draft object carries the
   type, the reversal round, the round count, the pick timer and your
   seat. `_mockApplyLeague` is the mapping and is pure, so the suite can
   run it on a fixture; `_mockUseLeague` is the fetch around it.

   WHAT IS NOT MAPPED IS SAID. IDP, IR and taxi slots have no counterpart
   here and are dropped; an auction draft is mocked as a snake, because
   this room bids nothing; a TE bonus of some odd size rounds to the
   nearest the panel offers. Every one of those is in the note the button
   prints, so the reader knows what the room did with their league. */
let _mockLeagueNote = "";

function _mockApplyLeague(league, draft, userId, cfg) {
  const c = cfg || _mockCfg;
  const notes = [];
  const lg = league || {};
  const teams = parseInt(lg.total_rosters, 10);
  if (teams >= MOCK_TEAMS_RANGE[0] && teams <= MOCK_TEAMS_RANGE[1]) {
    c.teams = teams; notes.push(`${teams} teams`);
  } else if (teams) {
    notes.push(`${teams} teams is outside the ${MOCK_TEAMS_RANGE[0]}\u2013${MOCK_TEAMS_RANGE[1]} this room runs`);
  }
  const positions = Array.isArray(lg.roster_positions) ? lg.roster_positions : [];
  if (positions.length) {
    const roster = { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SFLEX: 0, K: 0, DST: 0, BN: 0 };
    const dropped = new Set();
    for (const raw of positions) {
      const slot = MOCK_SLEEPER_SLOT[String(raw || "").toUpperCase()];
      if (slot) roster[slot] = Math.min(MOCK_ROSTER_MAX[slot], roster[slot] + 1);
      else dropped.add(String(raw || "").toUpperCase());
    }
    c.roster = roster;
    notes.push(`roster ${_mockRosterLine(c)}`);
    if (dropped.size) notes.push(`${[...dropped].join("/")} slots have no place here and were dropped`);
  }
  const sc = lg.scoring_settings || {};
  if (sc.rec != null) {
    const rec = Number(sc.rec);
    c.scoring = rec >= 0.75 ? "ppr" : rec >= 0.25 ? "half" : "std";
    notes.push(MOCK_SCORING[c.scoring].name);
  }
  const teb = Number(sc.bonus_rec_te || 0);
  c.tePrem = teb >= 0.75 ? 1 : teb >= 0.25 ? 0.5 : 0;
  if (c.tePrem) notes.push(`TE +${c.tePrem} a catch`);
  const d = draft || {};
  const ds = d.settings || {};
  if (d.type === "auction") {
    c.draftType = "snake"; notes.push("an auction league, mocked here as a snake");
  } else if (d.type === "linear") {
    c.draftType = "linear"; notes.push("linear order");
  } else if (d.type === "snake") {
    c.draftType = Number(ds.reversal_round) === 3 ? "3rr" : "snake";
    notes.push(c.draftType === "3rr" ? "3rd-round reversal" : "snake");
  }
  const timer = parseInt(ds.pick_timer, 10);
  if (Number.isFinite(timer)) {
    c.clock = timer <= 0 ? 0
      : MOCK_CLOCKS.filter((s) => s > 0).reduce((best, s) =>
          Math.abs(s - timer) < Math.abs(best - timer) ? s : best, MOCK_CLOCKS[1]);
    notes.push(c.clock ? `${c.clock}s clock` : "no clock");
  }
  const order = d.draft_order || {};
  const seat = userId != null ? parseInt(order[String(userId)], 10) : NaN;
  if (Number.isFinite(seat) && seat >= 1 && seat <= c.teams) {
    c.slot = seat; notes.push(`your seat is ${seat}`);
  }
  return notes;
}

async function _mockUseLeague() {
  const say = (msg) => { _mockLeagueNote = msg; _mockRender(); };
  const username = localStorage.getItem("ff_user");
  if (!username) { say("Link your Sleeper account on the Account page first."); return; }
  say("Reading your league\u2026");
  try {
    const user = window._slUser
      || await sleeperGet(`user/${encodeURIComponent(username)}`);
    if (!user || !user.user_id) throw new Error(`No Sleeper user named \u201c${username}\u201d`);
    let leagueId = localStorage.getItem("ff_league");
    if (!leagueId) {
      let season = new Date().getFullYear();
      let leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${season}`) || [];
      if (!leagues.length) {
        season -= 1;
        leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${season}`) || [];
      }
      if (!leagues.length) throw new Error("No NFL leagues found on that account");
      leagueId = leagues[0].league_id;
    }
    const league = await sleeperGet(`league/${leagueId}`);
    let drafts = [];
    try { drafts = await sleeperGet(`league/${leagueId}/drafts`) || []; } catch (e) { drafts = []; }
    const current = drafts[0] || null;
    const applied = _mockApplyLeague(league, current, user.user_id, _mockCfg);
    _mockSaveCfg();
    // THE ROOM: who sits where, and how each of them drafted last time.
    // The users for their names; the roster list only when the draft has
    // no order yet; last season's league for the drafts to measure from.
    let users = [], rosters = [], prevDrafts = [];
    try { users = await sleeperGet(`league/${leagueId}/users`) || []; } catch (e) { users = []; }
    if (!current || !Object.keys(current.draft_order || {}).length) {
      try { rosters = await sleeperGet(`league/${leagueId}/rosters`) || []; } catch (e) { rosters = []; }
    }
    if (league.previous_league_id) {
      try { prevDrafts = await sleeperGet(`league/${league.previous_league_id}/drafts`) || []; }
      catch (e) { prevDrafts = []; }
    }
    // This season's draft first if it has happened, then last season's:
    // the most recent draft a manager appears in decides their build.
    const samples = [];
    for (const d of [...drafts, ...prevDrafts]) {
      if (!d || d.status !== "complete" || !d.draft_id) continue;
      try { samples.push({ draft: d, picks: await sleeperGet(`draft/${d.draft_id}/picks`) || [] }); }
      catch (e) { /* a draft that will not read is a draft not measured */ }
      if (samples.length >= 2) break;
    }
    _mockLeague = _mockCleanLeague(_mockBuildLeague(league, current, users, rosters,
                                                    samples, user.user_id));
    _mockSaveLeague();
    applied.push(_mockLeagueSummary(_mockLeague));
    say(`${league.name || "Your league"}: ${applied.join(" · ") || "nothing to read"}.`);
  } catch (e) {
    say(String(e.message || e));
  }
}

/* ---- "Leaguemates' draft tendencies" -------------------------------------
   The second half of the screenshot's line under "Select League": "More
   realistic mock drafts using your league's settings and leaguemates'
   draft tendencies." A room of builds drawn from a weight table is a
   room of strangers. Your league is eleven particular people, and the
   one thing known about how each of them drafts is HOW THEY DRAFTED:
   Sleeper keeps every pick of every past draft keyed by the manager who
   made it, and the league object points at last season's league.

   MEASURED, NOT DECLARED. Each manager's picks in the most recent
   completed draft are read for the shapes the builds above describe —
   no back in the first five rounds, three backs in five, three
   receivers in four, one back early and nothing after, a quarterback
   or a tight end early or late — and the room that manager sits in is
   dealt the matching build instead of a draw from the table. The two
   timing tells (quarterback, tight end) are read AGAINST THE ROOM'S OWN
   MEDIAN, so a superflex league, where every quarterback goes early,
   does not read as twelve early-QB managers. A manager with fewer than
   five picks, or absent from every draft read, is unmeasured and draws
   from the table as before; the panel says how many were measured and
   from which draft, and lists the six rounds that decided each one.

   KEEPER PICKS ARE NOT PICKS and are skipped: a round-one keeper is a
   contract, not a tendency. A pick with no `picked_by` (a commissioner
   or auto-pick) is charged to the seat that was on the clock.

   The read is pure and the fetch is around it, the same split as the
   settings above, so the suite runs the read on a fixture draft. */
//: The shape is read from the first six rounds; fewer than five picks
//: in the draft and the manager is unmeasured.
const MOCK_TELL_ROUNDS = 6;
const MOCK_TELL_MIN_PICKS = 5;
//: The panel and the store keep this many characters of a Sleeper name.
const MOCK_MATE_NAME_MAX = 28;

//: One manager's picks → the numbers the tells are read from.
function _mockShapeOf(picks) {
  const own = (Array.isArray(picks) ? picks : [])
    .filter((p) => p && !p.keeper && p.round >= 1)
    .sort((a, b) => a.round - b.round);
  const firstAt = (pos) => {
    const p = own.find((x) => x.position === pos);
    return p ? p.round : Infinity;
  };
  const countTo = (pos, r) => own.filter((p) => p.position === pos && p.round <= r).length;
  return { picks: own.length, firstQB: firstAt("QB"), firstTE: firstAt("TE"),
           firstRB: firstAt("RB"), rb4: countTo("RB", 4), rb5: countTo("RB", 5),
           wr4: countTo("WR", 4),
           line: own.filter((p) => p.round <= MOCK_TELL_ROUNDS)
                    .map((p) => p.position || "?").join("-") };
}

//: The room's median first-QB and first-TE round, over the managers
//: with enough picks to measure; null with fewer than three of them,
//: because a median of two is one of them.
function _mockRoomMedians(shapes) {
  const med = (xs) => {
    const v = xs.filter(Number.isFinite).sort((a, b) => a - b);
    if (v.length < 3) return null;
    const h = v.length >> 1;
    return v.length % 2 ? v[h] : (v[h - 1] + v[h]) / 2;
  };
  const measured = shapes.filter((s) => s.picks >= MOCK_TELL_MIN_PICKS);
  return { qb: med(measured.map((s) => s.firstQB)), te: med(measured.map((s) => s.firstTE)) };
}

//: A shape, against the room → a build key from MOCK_ARCHETYPES, or
//: null when the manager cannot be measured. The order is the order of
//: how much a tell says: a quarterback two rounds before the room says
//: more than a balanced first four, and the first five rounds' backs
//: say more than a late quarterback.
function _mockTendency(s, room) {
  if (!s || s.picks < MOCK_TELL_MIN_PICKS) return null;
  const qbMed = room && Number.isFinite(room.qb) ? room.qb : null;
  const teMed = room && Number.isFinite(room.te) ? room.te : null;
  if (qbMed != null && s.firstQB <= qbMed - 2 && s.firstQB <= 6) return "early_qb";
  if (teMed != null && s.firstTE <= teMed - 2 && s.firstTE <= 5) return "elite_te";
  if (s.rb5 === 0) return "zero_rb";
  if (s.rb5 === 1 && s.firstRB <= 2) return "hero_rb";
  if (s.rb5 >= 3) return "robust_rb";
  if (s.wr4 >= 3) return "wr_room";
  if (qbMed != null && teMed != null
      && s.firstQB >= qbMed + 2 && s.firstTE >= teMed + 2) return "late_round";
  if (s.rb4 === 2 && s.wr4 === 2) return "balanced";
  return "bpa";
}

//: One Sleeper draft with its picks → every manager's build and line.
function _mockReadDraft(draft, picks) {
  const d = draft || {};
  const slotUser = {};
  for (const [uid, slot] of Object.entries(d.draft_order || {})) slotUser[String(slot)] = String(uid);
  const byUser = {};
  for (const p of (Array.isArray(picks) ? picks : [])) {
    if (!p) continue;
    const who = String(p.picked_by || slotUser[String(p.draft_slot)] || "");
    if (!who) continue;
    (byUser[who] = byUser[who] || []).push({
      round: parseInt(p.round, 10) || 0,
      position: String((p.metadata || {}).position || "").toUpperCase(),
      keeper: !!p.is_keeper });
  }
  const shapes = {};
  for (const [uid, list] of Object.entries(byUser)) shapes[uid] = _mockShapeOf(list);
  const room = _mockRoomMedians(Object.values(shapes));
  const managers = {};
  for (const [uid, sh] of Object.entries(shapes)) {
    managers[uid] = { key: _mockTendency(sh, room), line: sh.line, picks: sh.picks };
  }
  return { season: String(d.season || ""), draftId: d.draft_id || null, managers, room };
}

//: The league, its current draft, its users, its rosters and the sample
//: drafts (most recent first) → the seating the mock starts from.
function _mockBuildLeague(league, draft, users, rosters, samples, userId) {
  const lg = league || {};
  const teams = parseInt(lg.total_rosters, 10) || 0;
  const names = {};
  for (const u of (Array.isArray(users) ? users : [])) {
    if (!u || !u.user_id) continue;
    const meta = u.metadata || {};
    names[String(u.user_id)] = String(meta.team_name || u.display_name || u.username || "").trim();
  }
  // Seats from the draft's order; from the roster list until there is one.
  const seatOf = {};
  const order = (draft || {}).draft_order || {};
  if (Object.keys(order).length) {
    for (const [uid, slot] of Object.entries(order)) seatOf[String(uid)] = parseInt(slot, 10);
  } else {
    for (const r of (Array.isArray(rosters) ? rosters : [])) {
      if (r && r.owner_id && r.roster_id) seatOf[String(r.owner_id)] = parseInt(r.roster_id, 10);
    }
  }
  // The most recent draft a manager could be measured in decides.
  const reads = (samples || []).map((x) => _mockReadDraft(x.draft, x.picks));
  const seats = [];
  for (const [uid, slot] of Object.entries(seatOf)) {
    if (!(slot >= 1 && slot <= teams)) continue;
    let tell = null, from = "";
    for (const r of reads) {
      const m = r.managers[uid];
      if (m && m.key) { tell = m; from = r.season; break; }
    }
    seats.push({ slot, userId: uid, name: names[uid] || "", key: tell ? tell.key : null,
                 line: tell ? tell.line : "", from });
  }
  seats.sort((a, b) => a.slot - b.slot);
  const you = String(userId || "");
  return { id: lg.league_id ? String(lg.league_id) : null, name: lg.name || "", teams, you, seats,
           measured: seats.filter((s) => s.key && s.userId !== you).length,
           from: reads.map((r) => r.season).filter(Boolean) };
}

/* The seating survives a reload, like the keepers and the settings: the
   league is read once and mocked against a dozen times. */
const MOCK_LEAGUE_KEY = "qb_mock_league";

function _mockCleanLeague(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.seats)) return null;
  const keys = new Set(MOCK_ARCHETYPES.map((a) => a.key));
  const teams = parseInt(raw.teams, 10) || 0;
  const you = String(raw.you || "");
  const seats = raw.seats.map((s) => s && typeof s === "object" ? {
    slot: parseInt(s.slot, 10) || 0, userId: String(s.userId || ""),
    name: String(s.name || "").slice(0, MOCK_MATE_NAME_MAX),
    key: keys.has(s.key) ? s.key : null,
    line: String(s.line || "").slice(0, 40), from: String(s.from || "").slice(0, 8) } : null)
    .filter((s) => s && s.slot >= 1 && s.slot <= teams);
  return { id: raw.id ? String(raw.id) : null, name: String(raw.name || "").slice(0, 60),
           teams, you, seats,
           measured: seats.filter((s) => s.key && s.userId !== you).length,
           from: Array.isArray(raw.from) ? raw.from.map(String).slice(0, 4) : [] };
}

let _mockLeague = (() => {
  try { return _mockCleanLeague(JSON.parse(localStorage.getItem(MOCK_LEAGUE_KEY) || "null")); }
  catch (e) { return null; }
})();

function _mockSaveLeague() {
  try {
    if (_mockLeague) localStorage.setItem(MOCK_LEAGUE_KEY, JSON.stringify(_mockLeague));
    else localStorage.removeItem(MOCK_LEAGUE_KEY);
  } catch (e) {}
}

//: "the 2025 draft" / "the 2026 and 2025 drafts".
function _mockLeagueFrom(lg) {
  const seasons = [...new Set((lg && lg.from) || [])];
  if (!seasons.length) return "no completed draft";
  return seasons.length === 1 ? `the ${seasons[0]} draft` : `the ${seasons.join(" and ")} drafts`;
}

function _mockLeagueSummary(lg) {
  if (!lg || !lg.seats.length) return "no seats to read";
  const rivals = lg.seats.filter((s) => s.userId !== lg.you).length;
  return lg.from.length
    ? `${lg.measured} of ${rivals} leaguemates measured from ${_mockLeagueFrom(lg)}`
    : "no completed draft to measure your leaguemates from";
}

//: The personas for a draft of `teams` rooms: the table's draw for every
//: room, then the league's measured build over it for every seated
//: manager — but only when the league is the size being drafted, because
//: a seat in a twelve-team order means nothing in a ten-team room.
function _mockSeatRooms(teams, league) {
  const personas = Array.from({ length: teams }, () => _mockDrawArchetype());
  if (!league || league.teams !== teams || !Array.isArray(league.seats)) return personas;
  for (const s of league.seats) {
    const i = s.slot - 1;
    if (!(i >= 0 && i < teams)) continue;
    const arch = s.key ? MOCK_ARCHETYPES.find((a) => a.key === s.key) : null;
    personas[i] = Object.assign({}, arch || personas[i], {
      who: s.name || "", line: s.line || "", measured: !!arch, from: s.from || "" });
  }
  return personas;
}

//: What a room is called in the log and on the clock: the manager's
//: name when the league gave one, "Room N" otherwise, "You" for yours.
function _mockRoomName(m, ti) {
  if (ti === m.you) return "You";
  const p = (m.personas || [])[ti];
  return p && p.who ? p.who : "Room " + (ti + 1);
}

function _mockRoomTitle(m, ti) {
  if (ti === m.you) return "Your pick";
  const p = (m.personas || [])[ti] || {};
  if (!p.name) return "";
  if (p.measured) return `${p.name} — measured from their ${p.from || "last"} draft: ${p.line}`;
  return p.who ? `${p.name} — drawn, not measured` : p.name;
}

//: The panel's list: seat, name, measured build and the rounds behind it.
function _mockMatesHTML(c) {
  const lg = _mockLeague;
  if (!lg || !Array.isArray(lg.seats) || !lg.seats.length) return "";
  const rivals = lg.seats.filter((s) => s.userId !== lg.you).length;
  // `note`, not `sub`: the file-wide guard against escaping an assembled
  // markup string reads for a `sub` handed to escapeHtml, and this one
  // is plain text.
  const note = lg.teams === c.teams
    ? `${lg.measured} of ${rivals} measured from ${_mockLeagueFrom(lg)}`
    : `seated at ${lg.teams} teams — set ${lg.teams} teams to use them`;
  const rows = lg.seats.map((s) => {
    const you = s.userId === lg.you;
    const arch = s.key ? MOCK_ARCHETYPES.find((a) => a.key === s.key) : null;
    return `<div class="mk-row mk-row-slot">
      <span class="mk-mate-name"><span class="mk-mate-seat">${s.slot}.</span>${
        you ? `<span class="mk-mate-you">You</span>` : escapeHtml(s.name || "Room " + s.slot)}</span>
      <span class="mk-row-v">${you ? "" : arch
        ? `<span class="mk-mate-build">${escapeHtml(arch.name)}</span><span class="mk-mate-line">${
            escapeHtml(s.line)}</span>`
        : `<span class="mk-mate-draw">unmeasured — drawn</span>`}</span></div>`;
  }).join("");
  return `<details class="mk-roster mk-mates">
          <summary class="mk-row"><span class="mk-row-k">${icon("people", 15)}
            <span>Your leaguemates<i class="mk-row-sub">${escapeHtml(note)}</i></span></span>
            <span class="mk-row-v mk-row-chev">›</span></summary>
          ${rows}
        </details>`;
}

/* THE ONE PANEL ON THIS CARD MADE OF THINGS THAT ALREADY HAPPENED.

   The render had a "Fantasy Points Trend" bar chart, and it is the best
   idea in it: everything else on the card is a projection or a
   simulation, and a drafter deciding between two men wants to see the
   shape of the season behind the average. 24.5 a game off six good weeks
   and eleven quiet ones is a different player from 24.5 every Sunday, and
   no mean can tell them apart.

   Loaded after the card renders rather than with it, because it is a
   fetch and the card must not wait on the network to appear — the same
   pattern the fantasy dossier uses. A player with no logs says so
   plainly, and says WHICH kind of nothing it is: a rookie has never
   played, and that is not the same as a machine that has not ingested
   him. */
const MK_TREND_WEEKS = 18;
async function _mockTrend(name) {
  const zone = document.getElementById("mk-trend");
  if (!zone || zone.dataset.mktrend !== name) return;
  const row = (_mock && _mock.all || []).find((x) => x.player === name) || {};
  const stats = await leagueLogs(name, "nfl");   // a mock draft is football

  // The card may have moved on while the fetch was in flight.
  const z = document.getElementById("mk-trend");
  if (!z || z.dataset.mktrend !== name) return;
  const series = stats["Fantasy Points"] || stats["fp_ppr"]
    || stats[Object.keys(stats).find((k) => /fantasy|ppr/i.test(k)) || ""] || [];
  const vals = series.slice(-MK_TREND_WEEKS)
    .map((v) => (typeof v === "object" ? +v.value : +v))
    .filter((v) => Number.isFinite(v));
  const head = `<div class="mk-h">Last season, week by week</div>`;
  if (!vals.length) {
    z.innerHTML = head + `<p class="mk-fine">${row.source === "market"
      ? `No game log — he has not played an NFL snap${
          row.rookie ? " (rookie)" : ""}, which is why his projection is the
         market’s draft rank rather than a read of ours.`
      : `No game log on this machine. The droplet and the laptop fill these
         in; the projection above does not depend on it.`}</p>`;
    return;
  }
  const max = Math.max(...vals, 1);
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const bars = vals.map((v, i) => `<span class="mk-bar" style="height:${
    Math.max(3, v / max * 100).toFixed(1)}%" title="Week ${i + 1}: ${
    v.toFixed(1)}"></span>`).join("");
  const best = Math.max(...vals), worst = Math.min(...vals);
  z.innerHTML = head
    + `<div class="mk-bars" style="--mk-mean:${(mean / max * 100).toFixed(1)}%">${bars}</div>`
    + `<div class="mk-kv"><span>Best week</span><b>${best.toFixed(1)}</b></div>`
    + `<div class="mk-kv"><span>Worst week</span><b>${worst.toFixed(1)}</b></div>`
    + `<div class="mk-kv"><span>Weeks played</span><b>${vals.length}</b></div>`
    + `<p class="mk-fine">Actual scoring, not a projection — the dashed
       line is his own average. The floor and ceiling above are simulated
       forward; this is what already happened.</p>`;
}

function _mockRender() {
  const room = document.getElementById("mock-room");
  if (!room) return;
  room.innerHTML = mockDraftHTML();
  const z = room.querySelector("#mk-trend");
  if (z) _mockTrend(z.dataset.mktrend);
  _mockArmClock();
}

/* THE CHEAT SHEET: the pool in the order the reader chose to draft
   from. Our board is value over replacement; the market's is what the
   room pays, which is the order a drafter used to ADP expects. */
function _mockSheet(m) {
  const key = (m && m.cfg && m.cfg.sheet) || "board";
  return key === "market" ? _mockByMarket(m) : m.pool;
}

/* ---- The pick clock -----------------------------------------------------
   Yours, and only yours. A CPU pick is computed in under a millisecond
   and a clock on it would be an animation; a clock on YOUR pick is the
   pressure a real room puts on, and it is real because something happens
   at zero: the cheat sheet's best available that your roster still has
   room for is drafted for you, which is what every draft host does. Off
   by default (`MOCK_DEFAULT_CFG.clock`), armed once per pick, and
   stopped the moment the room is gone from the page. */
let _mockClockTimer = null;
let _mockClockPick = -1;

function _mockStopClock() {
  if (_mockClockTimer) { clearInterval(_mockClockTimer); _mockClockTimer = null; }
  _mockClockPick = -1;
}

function _mockArmClock() {
  const m = _mock;
  if (!m || !m.cfg || !m.cfg.clock) { _mockStopClock(); return; }
  const total = m.teams * m.rounds;
  const yours = m.pick < total && _mockPicker(m.pick, m.teams) === m.you
    && !_mockSkipped(m, m.pick);
  if (!yours) { _mockStopClock(); return; }
  if (_mockClockPick === m.pick && _mockClockTimer) return;   // already running for this pick
  _mockStopClock();
  _mockClockPick = m.pick;
  let left = m.cfg.clock;
  _mockClockTimer = setInterval(() => {
    const el = document.getElementById("mk-clock");
    // The room left the page, or the draft moved on without us.
    if (!el || _mock !== m || m.pick !== _mockClockPick) { _mockStopClock(); return; }
    left -= 1;
    if (left > 0) {
      el.textContent = `${left}s left`;
      el.classList.toggle("mk-clock-low", left <= 10);
      return;
    }
    _mockStopClock();
    _mockAutoPick();
  }, 1000);
}

//: The cheat sheet's best available your roster has room for — the
//: same legality the rooms answer to, so a clock that ran out cannot
//: hand you a third quarterback.
function _mockAutoPick() {
  const m = _mock;
  if (!m) return;
  const roster = m.rosters[m.you];
  const counts = { QB: 0, RB: 0, WR: 0, TE: 0 };
  for (const p of roster) if (counts[p.position] != null) counts[p.position] += 1;
  const round = Math.floor(m.pick / m.teams);
  const sheet = _mockSheet(m);
  const pick = sheet.find((p) => _mockNeedCounts(counts, p.position, round) > 0)
    || sheet[0];
  if (!pick) return;
  _mockSel = null;
  _mockTake(m.you, pick);
  _mockAdvance();
}

function _mockBind(host) {
  const room = host.querySelector("#mock-room");
  if (!room) return;
  // Delegated, because the room's innerHTML is replaced on every pick.
  // EVERY SETTING WRITES THE CONFIG AND RE-RENDERS, so the roster line,
  // the round count and the button's summary are never a step behind
  // the control that changed them.
  const setCfg = (fn) => { fn(_mockCfg); _mockSaveCfg(); _mockRender(); };
  room.addEventListener("change", (e) => {
    const t = e.target;
    if (t.id === "mk-scoring") setCfg((c) => { c.scoring = t.value; });
    else if (t.id === "mk-teprem") setCfg((c) => { c.tePrem = Number(t.value); });
    else if (t.id === "mk-type") setCfg((c) => { c.draftType = t.value; });
    else if (t.id === "mk-sheet") setCfg((c) => { c.sheet = t.value; });
    else if (t.id === "mk-clock") setCfg((c) => { c.clock = Number(t.value); });
    else if (t.id === "mk-chaos") setCfg((c) => { c.chaos = Number(t.value); });
  });
  room.addEventListener("click", (e) => {
    const t = e.target;
    if (t.id === "mk-keep-add") {
      const name = (document.getElementById("mk-keep-name") || {}).value || "";
      const team = parseInt((document.getElementById("mk-keep-team") || {}).value, 10) || 0;
      const round = parseInt((document.getElementById("mk-keep-round") || {}).value, 10) || 1;
      const who = name.trim();
      // A room cannot keep two players in the same round — it only has
      // the one pick to give up — and the same man cannot be kept twice.
      const clash = _mockKeepers.some((k) =>
        k.player === who || (k.team === team && k.round === round));
      if (who && !clash) {
        _mockKeepers.push({ player: who, team, round });
        _mockSaveKeepers();
        _mockRender();
      }
      return;
    }
    if (t.dataset && t.dataset.kdel != null) {
      _mockKeepers.splice(parseInt(t.dataset.kdel, 10), 1);
      _mockSaveKeepers();
      _mockRender();
      return;
    }
    const stepEl = t.closest && t.closest("[data-mkstep]");
    if (stepEl && t.dataset && t.dataset.mkd) {
      // Steppers: teams, your seat, and every roster slot. The seat
      // follows the league size — a ten-team league has no pick eleven,
      // and silently clamping a stale choice would start the reader
      // from a seat they never chose, so the clean-up clamps it in the
      // open and the panel shows the result.
      const key = stepEl.dataset.mkstep;
      const d = parseInt(t.dataset.mkd, 10) || 0;
      setCfg((c) => {
        if (key === "teams") c.teams += d;
        else if (key === "slot") c.slot += d;
        else if (key.startsWith("roster.")) {
          const s = key.slice(7);
          if (c.roster[s] != null) c.roster[s] += d;
        }
      });
      return;
    }
    const presetEl = t.closest && t.closest("[data-mkpreset]");
    if (presetEl && MOCK_PRESETS[presetEl.dataset.mkpreset]) {
      const p = MOCK_PRESETS[presetEl.dataset.mkpreset];
      setCfg((c) => { c.scoring = p.scoring; c.tePrem = p.tePrem;
                      c.roster = { ...p.roster }; });
      return;
    }
    if (t.id === "mk-use-league" || (t.closest && t.closest("#mk-use-league"))) {
      _mockUseLeague();
      return;
    }
    if (t.id === "mk-start" || (t.closest && t.closest("#mk-start"))) {
      _mockSaveCfg();
      _mockChaos = _mockCfg.chaos;
      _mockStart(_mockCfg.teams, Math.min(_mockCfg.teams, _mockCfg.slot));
    } else if (t.id === "mk-reset" || t.id === "mk-again") {
      _mockStopClock();
      _mock = null; _mockSel = null; _mockTab = "pool"; _mockRender();
    } else if (t.dataset && t.dataset.mkp) {
      const p = _mock.pool.find((x) => x.player === t.dataset.mkp);
      // The selection must not survive the man it names. Drafting him
      // takes him out of the pool, so the card falls back to the new best
      // available rather than describing somebody nobody can pick.
      if (p) { _mockStopClock(); _mockSel = null; _mockTake(_mock.you, p); _mockAdvance(); }
    } else {
      // Selection and tabs are delegated off the closest carrier so a
      // click anywhere in a row works, including on the avatar.
      const tabEl = e.target.closest("[data-mktab]");
      if (tabEl) { _mockTab = tabEl.dataset.mktab; _mockRender(); return; }
      const selEl = e.target.closest("[data-mksel]");
      if (selEl && _mock) {
        const name = selEl.dataset.mksel;
        // Only a player still ON THE BOARD can be inspected: the card
        // prices a decision (his edge, whether he lasts) and neither
        // question means anything about a player already drafted.
        if (_mock.pool.some((x) => x.player === name)) {
          _mockSel = name; _mockRender();
        }
      }
    }
  });
}

/* Live draft sync. One poll loop, keyed off the fantasy view being open —
   navigating away stops it, reconnecting resumes it. */
const dkState = { timer: null, kit: null, adp: {} };

function dkStop(msg) {
  if (dkState.timer) { clearInterval(dkState.timer); dkState.timer = null; }
  const st = document.getElementById("dk-status");
  if (st) { st.textContent = msg || "NOT CONNECTED"; st.style.color = "var(--text-mute)"; }
  const dis = document.getElementById("dk-disconnect");
  if (dis) dis.classList.add("ff-hidden");
  // Drop the pick order with the connection. A disconnected draft's
  // column would otherwise sit there labelled "Your draft" long after it
  // stopped being live, which is the same lie as a stale price.
  dkState.adp = {};
  if (typeof renderRankBoard === "function") renderRankBoard();
}

function initDraftKit(kit) {
  const btn = document.getElementById("dk-connect");
  if (!btn || !kit) return;
  dkState.kit = kit;
  dkBindMore(kit);
  initAuction(kit);
  const input = document.getElementById("dk-draft-id");
  const saved = localStorage.getItem("ff_draft_id");
  if (saved) input.value = saved;
  btn.addEventListener("click", () => {
    // Accept a full draft-room URL or a bare numeric ID.
    const m = String(input.value).match(/(\d{10,25})/);
    if (!m) {
      document.getElementById("dk-status").textContent = "NEED A DRAFT LINK OR ID";
      return;
    }
    localStorage.setItem("ff_draft_id", m[1]);
    acctTouch("fantasy");
    dkStart(m[1]);
  });
  document.getElementById("dk-disconnect")
    .addEventListener("click", () => dkStop());
}

function dkStart(draftId) {
  dkStop();
  const st = document.getElementById("dk-status");
  st.textContent = "CONNECTING…"; st.style.color = "var(--warn)";
  document.getElementById("dk-disconnect").classList.remove("ff-hidden");
  const tick = async () => {
    // The page owns the loop, so leaving the view must end it.
    if (state.view !== "fantasy") { dkStop(); return; }
    let picks;
    try {
      picks = await sleeperGet("draft/" + draftId + "/picks");
    } catch (e) {
      st.textContent = "DRAFT UNREACHABLE"; st.style.color = "var(--bad)";
      return;                            // transient — next tick retries
    }
    const taken = new Set((picks || []).map((p) =>
      ffNorm(`${(p.metadata || {}).first_name || ""} ${(p.metadata || {}).last_name || ""}`))
      .filter((n) => n));
    // THE PICK ORDER IS A RANKING, and it is the only one that is about
    // YOUR league rather than a national average of strangers. Recorded
    // here so the side-by-side board gains a "Your draft" column the
    // moment picks start.
    dkState.adp = {};
    (picks || []).forEach((p, i) => {
      const meta = p.metadata || {};
      const name = `${meta.first_name || ""} ${meta.last_name || ""}`.trim();
      const key = ffNorm(name);
      if (!key || dkState.adp[key]) return;
      dkState.adp[key] = { rank: p.pick_no > 0 ? p.pick_no : i + 1, player: name };
    });
    if (typeof renderRankBoard === "function") renderRankBoard();
    st.textContent = `LIVE · ${taken.size} PICKED`; st.style.color = "var(--good)";
    // KEPT, not just applied: flipping the board into auction dollars
    // re-renders every row, and a strikeout that only exists in the DOM
    // would put twenty drafted players back on the board until the next
    // twelve-second tick.
    dkState.taken = taken;
    dkCrossOff();
    dkBestAvailable(taken);
    dkAdvice(draftId);
  };
  tick();
  dkState.timer = setInterval(tick, 12000);
}

/* PICK-BY-PICK ADVICE. Ethan, 2026-08-15: "We need to show pick by pick
   advice."

   The arithmetic lives in engine/fantasy_pick.py and is served by
   /api/draftadvice — it reads the SAME cached pick feed this loop is
   already polling, so it costs no extra request, and it stays unit
   tested rather than becoming another hundred lines of untested
   JavaScript deciding what to do with a first-round pick.

   What it adds over "best available" is the only question that actually
   decides a pick: which of these men will NOT be here at my next turn. */
async function dkAdvice(draftId) {
  const host = document.getElementById("dk-advice");
  if (!host) return;
  const me = (window._slUser && window._slUser.user_id) || "";
  let a;
  try {
    const r = await fetch(`/api/draftadvice?draft=${encodeURIComponent(draftId)}`
      + `&user=${encodeURIComponent(me)}`);
    a = await r.json();
    if (!r.ok) throw new Error(a && a.error);
  } catch (e) { host.innerHTML = ""; return; }
  if (!a || a.slot == null) {
    // No seat in this draft means we are watching, not drafting. Saying
    // so beats inventing advice for a team that is not yours.
    host.innerHTML = `<div class="dk-advice-note">Connected as a spectator —
      no seat in this draft, so there is no "your next pick" to advise on.
      ${me ? "" : "Connect your Sleeper username above to claim your seat."}</div>`;
    return;
  }
  const pct = pctRound;
  const tone = { gone: "down", "toss-up": "warn", safe: "up" };
  const take = a.take;
  host.innerHTML = `
    <div class="dk-advice">
      <div class="dk-advice-head">
        Seat ${a.slot} of ${a.teams} · ${a.on_the_clock ? "ON THE CLOCK"
          : `next pick ${a.next_pick} — ${plural(a.picks_until, "pick")} away`}
        <span class="dk-window">room reach ${a.window} deep${
          a.window_fitted ? "" : " (prior — too few picks to fit yet)"}</span>
      </div>
      ${take ? `<div class="dk-take">
        <b>${escapeHtml(take.player)}</b>${injTag("nfl", take.player)}
        <span class="chip">${escapeHtml(take.position)}</span>
        <span class="chip ${tone[take.verdict] || ""}">${
          take.verdict === "gone" ? "won’t last" :
          take.verdict === "safe" ? "will last" : "toss-up"} · ${
          pct(take.survives)} to be here at ${a.next_pick || "your next pick"}</span>
        ${take.fills_need ? `<span class="chip up">fills a starting slot</span>` : ""}
        ${mkt(take) ? `<span class="chip" title="No last-season usage to project from, so he sits at the market\u2019s own draft rank and takes the points our board shows there. This is the room\u2019s read, not ours.">market\u2019s number, not ours</span>` : ""}
      </div>` : ""}
      ${a.can_wait && a.can_wait.length ? `<div class="dk-wait">
        <span class="dk-bl">Can wait</span>
        ${a.can_wait.slice(0, 4).map((r) => `<span class="chip">${
          escapeHtml(r.player)}${mkt(r)} · ${
          pct(r.survives)}</span>`).join("")}</div>` : ""}
      <div class="dk-advice-note">${escapeHtml(a.note || "")}</div>
    </div>`;
}

function dkBestAvailable(taken) {
  const host = document.getElementById("dk-best");
  if (!host || !dkState.kit) return;
  host.classList.remove("ff-hidden");
  const avail = dkState.kit.board.filter((r) => !taken.has(ffNorm(r.player)));
  const top = avail.slice(0, 5);
  const byPos = {};
  for (const r of avail) if (!byPos[r.position]) byPos[r.position] = r;
  host.innerHTML = `
    <div class="dk-bestrow"><span class="dk-bl">Best available</span>
      ${top.map((r) => `<span class="chip up">${escapeHtml(r.player)}${mkt(r)} · +${r.vorp}${injTag("nfl", r.player)}</span>`).join("")}</div>
    <div class="dk-bestrow"><span class="dk-bl">By position</span>
      ${["QB", "RB", "WR", "TE"].map((p) => byPos[p]
        ? `<span class="chip">${p}: ${escapeHtml(byPos[p].player)}${mkt(byPos[p])} (+${byPos[p].vorp})${injTag("nfl", byPos[p].player)}</span>` : "")
        .join("")}</div>`;
}

/* ON THE FANTASY PAGE, ESPN IS DESK ONLY.
   This used to be a second copy of the connect form, complete with its
   own Disconnect — so the league could be linked in one place and
   unlinked in another, with neither redrawing the other. The form and
   the Disconnect now live once, on the Account page (renderFflEspn).
   What is left here is the only question this page actually asks: is
   there a league to draw. */
function renderEspnZone() {
  const desk = document.getElementById("espn-desk");
  if (!desk) return;
  const league = localStorage.getItem(ESPN_LEAGUE_KEY);
  if (!league) { desk.innerHTML = ""; return; }
  renderLeagueDesk(league, localStorage.getItem(ESPN_TEAM_KEY) || "",
                   "espn", "espn-desk");
}
