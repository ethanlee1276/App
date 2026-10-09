/* Qellys Book — Gamecast: the live game page's rooms, in ESPN's layout.
   ==========================================================================
   Ethan, 2026-10-08, with three screenshots of ESPN's app on a live
   Bucs–Cowboys game: "I want the page to look like ESPN's app looks … see
   the game and stadium like I have now then scroll down and see the live
   game leaders and shit and see the actual play by play and all of that.
   We should have the box score and all of that."

   WHAT IS HERE: the panels under the tabs — Gamecast (the drive in
   progress, the last play with the players in it and their lines so far,
   the game leaders), Box score (every group ESPN's box carries, by team),
   Play-by-play (drive by drive, newest first, how each ended), Team stats
   (the two sides' totals as a comparison), Odds & picks. The hero, the
   field and the tabs stay in app.js (renderPbpPage), which loads this the
   first time a live game is opened (loadGamecast), like the Feed.

   THE NUMBERS, NEVER THE WRITING. Every line is composed from the deep
   file's fields — a play's type, yards, down and distance, the names the
   builder matched against the box score, a box row's stats under ESPN's
   own column labels, a team stat's label and value. ESPN's sentences are
   not in the file (livescore_build.pbp_doc) and could not be drawn if they
   were. The win percentage on the last play is OUR model's (live.win_prob),
   never a number read off somebody else's page.

   Runs in the page's global scope beside app.js and uses its helpers
   (escapeHtml, escapeAttr, icon, teamMarkIn, teamNameIn, playsHTML,
   pbpGroups, pbpOrd, pbpAgo, pbpPropsHTML, lineTrackHTML …) by name. */
(function () {
  "use strict";
  const FOOTBALL = new Set(["nfl", "cfb"]);
  //: ESPN's own headshot folders, by league — the same CDN path
  //: engine/sources/nflverse.ESPN_HEADSHOT draws NFL faces from. A face is
  //: the board's own first (the deep file's `faces`), this second, blank
  //: third.
  const FACE_DIR = { nfl: "nfl", cfb: "college-football", nba: "nba", wnba: "wnba", nhl: "nhl" };
  //: The box score's open side (the team toggle), kept across redraws.
  let _team = "";

  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const num = (s) => { const m = /-?\d+(\.\d+)?/.exec(String(s == null ? "" : s)); return m ? Number(m[0]) : NaN; };
  const plain = (s) => /^-?\d+(\.\d+)?$/.test(String(s == null ? "" : s).trim());
  const lower = (s) => String(s || "").toLowerCase();
  const titleCase = (v) => String(v || "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  /* ---------------- faces ---------------- */
  function faceURL(league, row, faces) {
    const own = row && row.name ? (faces || {})[lower(row.name)] : "";
    if (own) return own;
    const dir = FACE_DIR[league];
    return dir && row && row.id
      ? `https://a.espncdn.com/i/headshots/${dir}/players/full/${encodeURIComponent(row.id)}.png` : "";
  }
  /* The blank mark sits UNDER the photograph, so a face that fails to load
     (alt is empty, so nothing is drawn) leaves the mark showing — no inline
     handler, which the page's CSP forbids. */
  function faceHTML(league, row, faces) {
    const src = faceURL(league, row, faces);
    return `<span class="gc-face">${icon("user", 16)}${
      src ? `<img src="${escapeAttr(src)}" alt="" loading="lazy" decoding="async">` : ""}</span>`;
  }

  /* ---------------- the box score, read ----------------
     The deep file's `box` is ESPN's own box score with its own column
     labels (livescore_build.pbp_doc → espnplays.summary_box): one entry
     per side, one group per table ("passing", "rushing", "defensive" …),
     each with its `labels` and its rows of stat strings. Nothing here
     knows what a column MEANS beyond its label — a line is "value label"
     under the group's labels, and a leader is the most of one column —
     so a group ESPN adds next week draws as a table on its own, and a
     column it renames reads under the new name. That is the same stance
     the Player stats room took with `marketWord`: the record's own
     vocabulary labels the numbers, never a mapping of ours. */
  const teamBox = (d, team) => (((d || {}).box || []).find((b) => b.team === team) || {}).groups || [];
  const col = (g, label) => (g.labels || []).findIndex((l) => String(l).toUpperCase() === String(label).toUpperCase());
  const cell = (g, row, label) => { const i = col(g, label); return i >= 0 ? (row.stats || [])[i] : undefined; };
  const groupNamed = (groups, name) => groups.find((g) => lower(g.name) === lower(name)) || null;
  const rowOf = (g, name) => (g.rows || []).find((r) => lower(r.name) === lower(name)) || null;

  /* The columns a line is made of, per group, in ESPN's labels. "C/ATT"
     stands alone ("3/4"); everything else reads value then label ("26
     YDS"), and a zero is said ("0 TD") the way ESPN's chips say it. */
  const LINE_LABELS = {
    passing: ["C/ATT", "YDS", "TD", "INT"], rushing: ["CAR", "YDS", "TD"],
    receiving: ["REC", "YDS", "TD"], defensive: ["TOT", "SOLO", "SACKS"],
    interceptions: ["INT", "YDS", "TD"], kicking: ["FG", "XP", "PTS"], punting: ["NO", "AVG"],
    kickreturns: ["NO", "YDS", "TD"], puntreturns: ["NO", "YDS", "TD"], fumbles: ["FUM", "LOST"],
    goalies: ["SV", "GA"], skaters: ["G", "A", "SOG"],
  };
  const BARE = new Set(["C/ATT", "FG", "XP"]);
  function lineFor(g, row) {
    const want = LINE_LABELS[lower(g.name).replace(/\s+/g, "")] || (g.labels || []).slice(0, 3);
    const bits = [];
    want.forEach((label) => {
      const v = cell(g, row, label);
      if (v == null || v === "" || v === "--") return;
      bits.push(BARE.has(String(label).toUpperCase()) ? esc(v) : `${esc(v)} ${esc(label)}`);
    });
    return bits.join(", ");
  }
  /* A player's line so far, from the first group he has a row in — the
     group his role on the play points at first (a passer's passing line,
     a receiver's receiving line), the rest in the order a football reader
     expects. "" when the box has not seen him. */
  const ROLE_ORDER = {
    pass0: ["passing", "rushing", "receiving", "defensive"],
    pass1: ["receiving", "rushing", "passing", "defensive"],
    any: ["rushing", "receiving", "passing", "defensive", "interceptions", "kicking", "punting",
          "kickReturns", "puntReturns"],
  };
  function playerLine(d, name, role) {
    const groups = [...teamBox(d, d.away), ...teamBox(d, d.home)];
    const order = ROLE_ORDER[role] || ROLE_ORDER.any;
    const ranked = order.map((n) => groups.filter((g) => lower(g.name) === lower(n))).flat()
      .concat(groups.filter((g) => !order.some((n) => lower(n) === lower(g.name))));
    for (const g of ranked) {
      const r = rowOf(g, name);
      if (r) return { line: lineFor(g, r), row: r, group: g };
    }
    return { line: "", row: null, group: null };
  }
  const teamOf = (d, name) => (teamBox(d, d.away).some((g) => rowOf(g, name)) ? d.away
    : teamBox(d, d.home).some((g) => rowOf(g, name)) ? d.home : "");

  /* ---------------- the spot, in words ----------------
     ESPN writes "TB 4"; the deep file carries the yard as the site's own
     number, 0-100 from the home goal line (engine/models.py, the strip's
     convention — see pbpFieldPosHTML for why the raw `yardLine` is never
     drawn). The word is derived here once and used by the tiles and the
     last play alike, so the two can never disagree about which half of
     the field a number names. */
  /* `yard` counts up from the home goal line (engine/models.py): under
     fifty is home's half, over is away's, and the number a person says
     counts back from midfield — the strip's own arithmetic. */
  function spotWord(d, yard) {
    const y = Number(yard);
    if (!isFinite(y) || y < 0 || y > 100) return "";
    if (y === 50) return "50";
    const side = y < 50 ? (d.home || "") : (d.away || "");
    return `${side} ${Math.round(y > 50 ? 100 - y : y)}`.trim();
  }
  const downWord = (p) => p && p.down
    ? `${pbpOrd(Number(p.down))} & ${p.distance == null ? "?" : (Number(p.distance) === 0 ? "Goal" : p.distance)}` : "";

  /* ---------------- the drive in progress ----------------
     ESPN's card: the mark, "9 plays, 70 yards, 4:09", then DOWN and BALL
     ON. The drive comes from the summary's `drives.current`
     (espnplays.current_drive) when the builder saw one, and otherwise
     from the last drive on file while the game is live — a deep file
     written before `drive` existed still gets the card. The tiles read
     the SCOREBOARD's words for the next snap (`live.detail`, "2nd & Goal
     at TB 4"), split at " at " — not the last play's down, which is the
     snap that already happened. With no words, the ball-on tile falls
     back to the strip's own spot, and a tile with nothing is not drawn:
     a dash where ESPN has a number is the honest version of "we do not
     know", and two empty tiles are furniture. */
  function currentDrive(d) {
    const lv = d.live || {};
    if (d.drive && d.drive.team) return d.drive;
    const drives = d.drives || [];
    const last = drives[drives.length - 1];
    if (lv.state === "live" && last && last.team) {
      return { team: last.team, plays: last.offensive_plays || (last.plays || []).length,
               yards: last.yards || 0, elapsed: last.elapsed || "", period: last.period };
    }
    return null;
  }
  function driveWords(dr) {
    const n = Number(dr.plays || 0);
    return [`${n} play${n === 1 ? "" : "s"}`, `${Number(dr.yards || 0)} yard${Number(dr.yards) === 1 ? "" : "s"}`,
            dr.elapsed || ""].filter(Boolean).join(", ");
  }
  function situationTiles(d, lastPlay) {
    const lv = d.live || {};
    // The scoreboard's own words for the NEXT snap ("2nd & 6 at BUF 38"),
    // split on " at "; the strip's spot when the words are missing.
    const detail = String(lv.detail || "");
    let down = "", on = "";
    const m = /^(.*?)\s+at\s+(.+)$/.exec(detail);
    if (m) { down = m[1]; on = m[2]; } else if (detail) { down = detail; }
    if (!on) on = spotWord(d, lv.yard_line);
    if (!down && lastPlay) down = "";          // the last play's down is the LAST snap's, not the next
    if (!down && !on) return "";
    return `<div class="gc-tiles">
      <div class="gc-tile"><span class="gc-k">Down</span><b>${esc(down || "—")}</b></div>
      <div class="gc-tile"><span class="gc-k">Ball on</span><b>${esc(on || "—")}</b></div></div>`;
  }
  function currentDriveHTML(d, league, lastPlay) {
    const lv = d.live || {};
    const dr = currentDrive(d);
    if (!dr || lv.state !== "live") return "";
    return `<div class="card gc-drive">
      <div class="gc-drive-head">${teamMarkIn(league, dr.team, 28)}
        <div><div class="gc-k">Current drive</div><b>${esc(driveWords(dr))}</b></div>
        ${dr.period ? `<span class="gc-q">Q${esc(dr.period)}</span>` : ""}</div>
      ${situationTiles(d, lastPlay)}</div>`;
  }

  /* ---------------- the last play ----------------
     ESPN's card under the field: the title ("1-yd Touchdown Run"), the
     win percentage, the sentence, the two players with their lines so
     far, and the snap it came from ("2nd & Goal at TB 1").

     OURS HAS NO SENTENCE, BY DESIGN. ESPN's `text` is their writing and
     is not in the file (docs/LAUNCH.md; test_prose_never_reaches_a_deep_
     file). What the row carries is the type, the yards, the down and
     distance, the snap spot and the NAMES the builder matched against the
     box score's roster (espnplays._football_players) — so the card is the
     type and the yards as its title, the names as chips, and each man's
     line from the box score under his name. A pass resolves to thrower
     then catcher, so the first chip reads his passing line and the second
     his receiving line; a run reads the rushing line first. Ethan,
     2026-09-10, on the rail: "show what player got what reception or
     yard" — this is that, with the player's whole game beside it.

     THE WIN PERCENTAGE IS OURS. ESPN prints theirs; the site's own live
     model writes `live.win_prob` for every game in progress
     (livescore_build._win_prob), and that is the number drawn, with the
     mark of the side it favours. No reading is no badge. */
  function newestPlay(d, league) {
    const plays = d.plays || [];
    if (FOOTBALL.has(league)) return plays.slice().reverse().find((p) => p && p.kind === "football") || null;
    return plays.slice().reverse().find((p) => p && p.event) || null;
  }
  /* "1-yd Touchdown Run" is ESPN's title; ours is the type and the yards
     ("Rushing Touchdown · 1 yd"), composed from the two fields and
     nothing else. */
  function playTitle(p) {
    const y = Number(p.yards || 0);
    const yds = y ? `${y > 0 ? "" : trueMinus("-")}${Math.abs(y)} yd${Math.abs(y) === 1 ? "" : "s"}` : "";
    return [esc(p.event || "Play"), yds ? esc(yds) : ""].filter(Boolean).join(" · ");
  }
  function winPct(d, league) {
    const wp = (d.live || {}).win_prob;
    if (!wp || wp.home_win_prob == null) return "";
    const home = Number(wp.home_win_prob), away = wp.away_win_prob != null ? Number(wp.away_win_prob) : 1 - home;
    const [team, p] = home >= away ? [d.home, home] : [d.away, away];
    return `<span class="gc-win"><span class="gc-k">Win % (our model)</span>${teamMarkIn(league, team, 18)} <b>${(p * 100).toFixed(1)}</b></span>`;
  }
  function lastPlayHTML(d, league, faces) {
    const p = newestPlay(d, league);
    if (!p) return "";
    const foot = p.kind === "football";
    const when = foot ? `${p.period ? `Q${p.period}` : ""}${p.clock ? ` ${p.clock}` : ""}`.trim()
      : `${p.period ? (league === "nhl" ? hockeyPeriod(p.period) : (p.period <= 4 ? `Q${p.period}` : `OT${p.period - 4}`)) : ""}${p.clock ? ` ${p.clock}` : ""}`.trim();
    const tag = p.turnover ? `<span class="gc-tag turnover">Turnover</span>`
      : p.scoring ? `<span class="gc-tag">${foot ? "Score" : (league === "nhl" ? "Goal" : `+${p.points || ""}`)}</span>` : p.penalty ? `<span class="gc-tag">Penalty</span>` : "";
    const names = foot ? (p.players || []).filter(Boolean) : [p.player].filter(Boolean);
    const pass = foot && /pass|reception/i.test(String(p.event || ""));
    const chips = names.map((name, i) => {
      const got = playerLine(d, name, foot ? (pass ? (i === 0 ? "pass0" : "pass1") : "any") : "any");
      const team = (got.row && teamOf(d, name)) || p.team || "";
      const pos = got.row && got.row.pos ? ` ${esc(got.row.pos)}` : "";
      return `<div class="gc-chip">${faceHTML(league, got.row || { name }, faces)}
        <div class="gc-chip-t"><b>${esc(name)}</b><span class="mini">${esc(team)}${pos}</span>
          ${got.line ? `<span class="gc-chip-line">${got.line}</span>` : ""}</div></div>`;
    }).join("");
    const snap = foot && p.down ? `${esc(downWord(p))}${p.spot != null ? ` at ${esc(spotWord(d, p.spot))}` : ""}` : "";
    const score = (p.away_score != null && p.home_score != null)
      ? `<span class="gc-score">${esc(d.away)} ${esc(p.away_score)} – ${esc(p.home_score)} ${esc(d.home)}</span>` : "";
    return `<div class="card gc-last">
      <div class="gc-last-head"><div><div class="gc-k">Last play${when ? ` · ${esc(when)}` : ""}</div>
        <b class="gc-last-title">${foot ? playTitle(p) : esc(p.event || "Play")}</b>${tag}</div>
        ${winPct(d, league)}</div>
      ${foot && p.team ? `<div class="gc-last-team">${teamMarkIn(league, p.team, 18)} ${esc(teamNameIn(league, p.team))}${
        p.penalty ? " · penalty" : ""}</div>` : ""}
      ${chips ? `<div class="gc-chips">${chips}</div>` : ""}
      <div class="gc-last-foot">${snap ? `<span>${snap}</span>` : ""}${score}</div></div>`;
  }

  /* ---------------- the game leaders ----------------
     ESPN's GAME LEADERS: five rows for football (passing, rushing,
     receiving, sacks, tackles), the away side's man on the left and the
     home side's on the right, each with his face, the big number and his
     line. The rows are composed from the box score above, not read off a
     `leaders` block: a leader IS the row with the most of one column, and
     the box score is already on the page. Hoops reads points, rebounds
     and assists; hockey goals, assists, shots and saves. A category with
     nobody over zero on either side is left out (no sacks in the first
     quarter is not a row of two dashes), and a side with nobody shows a
     blank mark and "None", which is what ESPN draws. */
  /* Each category reads one group's one column; the leader is the row
     with the most of it, and the line beside him is his group line. A
     category with nobody over zero on either side is not drawn. */
  const LEADERS = {
    football: [["Passing", "passing", "YDS"], ["Rushing", "rushing", "YDS"], ["Receiving", "receiving", "YDS"],
               ["Sacks", "defensive", "SACKS"], ["Tackles", "defensive", "TOT"]],
    hoops: [["Points", "", "PTS"], ["Rebounds", "", "REB"], ["Assists", "", "AST"]],
    hockey: [["Goals", "", "G"], ["Assists", "", "A"], ["Shots", "", "SOG"], ["Saves", "", "SV"]],
  };
  function leaderOf(d, team, groupName, label) {
    const groups = teamBox(d, team).filter((g) => (!groupName || lower(g.name) === lower(groupName)) && col(g, label) >= 0);
    let best = null;
    groups.forEach((g) => (g.rows || []).forEach((r) => {
      const v = num(cell(g, r, label));
      if (isFinite(v) && v > 0 && (!best || v > best.v)) best = { v, row: r, group: g };
    }));
    return best;
  }
  function leadersHTML(d, league, faces) {
    const set = FOOTBALL.has(league) ? LEADERS.football : league === "nhl" ? LEADERS.hockey : LEADERS.hoops;
    const side = (team, best, right) => best
      ? `<div class="gc-lead${right ? " right" : ""}">${faceHTML(league, best.row, faces)}
          <div class="gc-lead-t"><b class="gc-lead-v">${esc(best.v % 1 ? best.v.toFixed(1) : best.v)}</b>
            <span class="gc-lead-n">${esc(best.row.name)}${best.row.pos ? ` <span class="mini">${esc(best.row.pos)}</span>` : ""}</span>
            <span class="mini">${lineFor(best.group, best.row)}</span></div></div>`
      : `<div class="gc-lead${right ? " right" : ""} none"><span class="gc-face">${icon("user", 16)}</span><div class="gc-lead-t"><span class="mini">None</span></div></div>`;
    const rows = set.map(([label, group, stat]) => {
      const a = leaderOf(d, d.away, group, stat), h = leaderOf(d, d.home, group, stat);
      if (!a && !h) return "";
      return `<div class="gc-lead-row">${side(d.away, a, false)}<span class="gc-lead-k">${esc(label)}</span>${side(d.home, h, true)}</div>`;
    }).filter(Boolean).join("");
    if (!rows) return "";
    return `<div class="card gc-leaders">
      <div class="gc-head">Game leaders</div>
      <div class="gc-lead-teams"><span>${teamMarkIn(league, d.away, 22)} ${esc(d.away)}</span>
        <span>${esc(d.home)} ${teamMarkIn(league, d.home, 22)}</span></div>${rows}</div>`;
  }

  /* ---------------- the box score ----------------
     ESPN's BOX SCORE tab: one side at a time behind a team toggle, every
     group as its own table under ESPN's labels, a face beside each name.
     The toggle's choice lives in this module (`_team`), so a redraw on
     the twelve-second clock keeps the side the reader chose. A deep file
     from before `box` existed falls back to the Player stats room's own
     table (pbpPlayersHTML), which read the four markets the tracker
     grades on — thinner, never wrong. */
  function boxHTML(d, league, faces) {
    const box = d.box || [];
    if (!box.length) return typeof pbpPlayersHTML === "function" ? pbpPlayersHTML(d, league)
      : `<p class="rail-quiet">No box score on file yet.</p>`;
    const sides = [d.away, d.home].filter((t) => box.some((b) => b.team === t));
    if (!sides.length) return `<p class="rail-quiet">No box score on file yet.</p>`;
    if (!sides.includes(_team)) _team = sides[0];
    const toggle = `<div class="gc-toggle">${sides.map((t) => `<button type="button" class="gc-tog${t === _team ? " active" : ""}" data-gc-team="${escapeAttr(t)}">${
      teamMarkIn(league, t, 18)} ${esc(teamNameIn(league, t))}</button>`).join("")}</div>`;
    const groups = teamBox(d, _team);
    const tables = groups.map((g) => {
      const rows = (g.rows || []).filter((r) => (r.stats || []).some((s) => s && s !== "--"));
      if (!rows.length) return "";
      return `<div class="pbp-bx-wrap"><table class="pbp-bx gc-bx">
        <thead><tr><th scope="col" class="pbp-bx-who">${esc(titleCase(g.name))}</th>${
          (g.labels || []).map((l) => `<th scope="col">${esc(l)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr><th scope="row" class="pbp-bx-who">${faceHTML(league, r, faces)}<span>${esc(r.name)}${
          r.pos ? ` <span class="mini">${esc(r.pos)}</span>` : ""}</span></th>${
          (g.labels || []).map((_l, i) => `<td>${esc((r.stats || [])[i] == null ? "—" : (r.stats || [])[i])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }).join("");
    return `${toggle}${tables || `<p class="rail-quiet">Nothing logged for this club yet.</p>`}
      <p class="mini" style="opacity:.6">Box score ${esc(pbpAgo(d.generated_at))}.</p>`;
  }

  /* ---------------- team stats ----------------
     ESPN's TEAM STATS tab: the two sides' totals as a comparison — the
     away value, the stat's name, the home value, and a split bar under
     the plain numbers (first downs, total yards) showing the share each
     side has. A bar is drawn only where both values are a bare number: a
     "5-12" third-down line or a "31:12" possession clock is shown as it
     is, not parsed into a fraction and drawn as if it were yards. Rows
     are the away side's order, with anything only the home side lists
     appended, so the two never drift apart. A deep file without
     `team_stats` falls back to the totals the page adds up from its own
     drives (pbpTotalsHTML). */
  function teamStatsHTML(d, league) {
    const ts = d.team_stats || {};
    const A = ts[d.away] || [], H = ts[d.home] || [];
    if (!A.length && !H.length) return typeof pbpTotalsHTML === "function" ? (pbpTotalsHTML(d, league)
      || `<p class="rail-quiet">Team totals fill in as the game is played.</p>`) : "";
    const byKey = (rows) => { const m = {}; rows.forEach((r) => { m[r.name || r.label] = r; }); return m; };
    const h = byKey(H), seen = new Set();
    const order = [...A, ...H.filter((r) => !A.some((a) => (a.name || a.label) === (r.name || r.label)))];
    const rows = order.map((r) => {
      const key = r.name || r.label;
      if (seen.has(key)) return "";
      seen.add(key);
      const a = A.find((x) => (x.name || x.label) === key), b = h[key];
      const av = a ? a.value : "—", hv = b ? b.value : "—";
      let bar = "";
      if (plain(av) && plain(hv)) {
        const x = Number(av), y = Number(hv), tot = x + y;
        const left = tot > 0 ? Math.round((x / tot) * 100) : 50;
        bar = `<div class="gc-bar"><span style="width:${left}%"></span><span style="width:${100 - left}%"></span></div>`;
      }
      return `<div class="gc-ts"><div class="gc-ts-row"><b>${esc(av)}</b><span class="gc-ts-k">${esc(r.label || key)}</span><b>${esc(hv)}</b></div>${bar}</div>`;
    }).join("");
    return `<div class="card gc-tstats"><div class="gc-ts-head"><span>${teamMarkIn(league, d.away, 20)} ${esc(d.away)}</span>
      <span class="gc-head">Team stats</span><span>${esc(d.home)} ${teamMarkIn(league, d.home, 20)}</span></div>${rows}</div>`;
  }

  /* ---------------- play by play, drive by drive ----------------
     ESPN's PLAY-BY-PLAY tab: each drive a card, newest first, headed by
     the mark, the team, "7 plays · 66 yd · 3:23 · Q1", how it ended
     ("Touchdown", "Punt" — the summary's `displayResult`, read by
     espnplays as a label and refused as a sentence) and the score it
     left, with every play of it under the head in the order it was
     played (a drive reads forwards; playsHTML draws the rows the rail
     draws, so a row is the same row in both places). A drive from a file
     without `result` falls back to the rail's derived tag — Score,
     Turnover, In progress. The other sports draw their periods the way
     the rail groups them (pbpGroups), every play of each. */
  function drivesHTML(d, league) {
    const lv = d.live || {};
    const drives = (d.drives || []).slice().reverse();
    if (!drives.length) return `<div class="card">${panelEmpty("Nothing has happened yet.")}</div>`;
    return drives.map((dr, i) => {
      const rows = dr.plays || [];
      const n = dr.offensive_plays || rows.length;
      const result = dr.result || (dr.scoring ? "Score" : rows.some((p) => p.turnover) ? "Turnover"
        : (i === 0 && lv.state === "live") ? "In progress" : "");
      const last = rows[rows.length - 1] || {};
      const score = (last.away_score != null && last.home_score != null) ? `${last.away_score}–${last.home_score}` : "";
      return `<div class="card gc-dr${dr.scoring ? " scoring" : ""}">
        <div class="gc-dr-head">${teamMarkIn(league, dr.team, 22)}
          <div><b>${esc(dr.team || "—")}</b><span class="mini"> · ${n} play${n === 1 ? "" : "s"} · ${dr.yards || 0} yd${
            dr.elapsed ? ` · ${esc(dr.elapsed)}` : ""}${dr.period ? ` · Q${esc(dr.period)}` : ""}</span></div>
          ${result ? `<span class="gc-tag${/turnover/i.test(result) ? " turnover" : ""}">${esc(result)}</span>` : ""}
          ${score ? `<span class="gc-dr-score">${esc(score)}</span>` : ""}</div>
        ${playsHTML({ plays: rows }) || `<p class="rail-quiet" style="margin:0 0 8px">No plays yet.</p>`}</div>`;
    }).join("");
  }
  function playsTabHTML(d, league) {
    if (FOOTBALL.has(league)) return drivesHTML(d, league);
    const groups = pbpGroups(d);
    if (!groups.length) return `<div class="card">${panelEmpty("Nothing has happened yet.")}</div>`;
    return groups.map((g) => `<div class="card gc-dr"><div class="gc-dr-head"><div><b>${esc(g.head)}</b>${
      g.sub ? `<span class="mini"> — ${esc(g.sub)}</span>` : ""}</div>${g.tag ? `<span class="gc-tag">${esc(g.tag)}</span>` : ""}</div>
      ${playsHTML({ plays: g.rows }) || `<p class="rail-quiet" style="margin:0 0 8px">No plays yet.</p>`}</div>`).join("");
  }

  /* ---------------- odds & picks ----------------
     ESPN's ODDS tab is a sportsbook's lines; ours is the site's own
     reading of this game — the live line track off the board (the
     opened → now chart the game page draws) and the two boards' picks on
     the game as the Live tab words them (pbpPropsHTML: Pick of the Day,
     Most Likely, Edge, each with the tracker's word), with the door to
     the full game page for the lines, the props and the long shots. */
  function oddsHTML(d, league, boardGame) {
    const picks = typeof pbpPropsHTML === "function" ? pbpPropsHTML(d, league) : "";
    const track = boardGame && boardGame.line_track && typeof lineTrackHTML === "function"
      ? `<div class="card">${lineTrackHTML(boardGame)}</div>` : "";
    const door = boardGame ? `<button type="button" class="btn ghost" id="pbp-game-door" data-gid="${escapeAttr(gameId(boardGame))}">Full game page — lines, props, long shots →</button>` : "";
    return `${track}${picks}${door}`;
  }

  /* ---------------- the Gamecast tab ----------------
     ESPN's first tab, top to bottom: the drive in progress, the field
     (app.js draws it above the tabs, on the park card, so it is on every
     tab), the last play, the leaders. A final has no drive and says so in
     one line over the leaders; a scheduled game draws nothing here, and
     the page's own empty state covers it. */
  function gamecastHTML(d, league, faces) {
    const last = newestPlay(d, league);
    const lv = d.live || {};
    const quiet = lv.state === "live" ? "" : lv.state === "final"
      ? `<p class="rail-quiet">Final. The leaders, the box score and every drive are below.</p>` : "";
    return `${currentDriveHTML(d, league, last)}${lastPlayHTML(d, league, faces)}${leadersHTML(d, league, faces)}${quiet}`;
  }

  function panel(tab, ctx) {
    const { d, league, faces, boardGame } = ctx || {};
    if (!d) return "";
    switch (tab) {
      case "box": return boxHTML(d, league, faces || {});
      case "plays": return playsTabHTML(d, league);
      case "team": return teamStatsHTML(d, league);
      case "odds": return oddsHTML(d, league, boardGame);
      default: return gamecastHTML(d, league, faces || {});
    }
  }

  window.QBGamecast = {
    panel, setTeam: (t) => { _team = String(t || ""); }, team: () => _team,
    // Exposed for the tests and for Ask: the readers, not the markup.
    spotWord, playerLine, leaderOf, currentDrive, newestPlay, lineFor, faceURL,
  };
})();
