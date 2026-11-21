/* Qellys Book — basketball's parts of the live game page (js/hoopscast.js).
   ==========================================================================
   Ethan, 2026-10-15, with two renders — the arena (ours, the crown at centre
   court) and the page: "the live play by play screen for nba looks like shit
   ... figure out what live data we can get too make it look like an actual
   play by play screen like ball tracking or possessions". The old page drew
   the vector court at its own size inside a box built for photographs: a
   small court in the corner of an empty card.

   ONE PAGE FOR EVERY SPORT (2026-11-21; Ethan: "all sports in all aspects
   should be trying to match nfl and that should be automatic when we do any
   visual changes"). This file drew a whole page of its own until then: its
   own scoreboard, play list, stats card and odds cards, in a layout the
   football page did not share. The page is detail.js's now (gpPageHTML), the
   same one football draws, and this file hands it basketball's parts
   (`parts`): the arena with its four views (Live, Shots, Players, Flow) for
   the place football's field has; the newest play, said in a sentence, for
   the last-play card; each play's sentence for the period cards; the bonus,
   team fouls and timeouts under each side's score (only when ESPN's
   scorer's-table block carries them, livescore_build.pbp_doc `situation`);
   which side has the ball; and the shot chart and the trends for the Stats
   tab. It writes none of the page's own markup: the cards are made by the
   page's builders (gpStageHTML, gpCardHTML, QBGamecast.playNow), so a change
   to the page's look is a change here too.

   WHAT IS TRACKED, AND HOW FAR IT CAN BE TRUSTED. Nobody publishes ball
   tracking to us; the league's own feed is the closest thing and it answers
   the box 403. ESPN's game file carries where every shot went up, by whom,
   made or not, and every play in order — so the ball flies from the last
   shot's spot to the basket, the last few shots stay on the floor behind
   it, and the rest is worked out from the plays alone, in the open:
     · THE BALL after the last play, only where the play settles it (a
       make, a rebound, a turnover, a foul, the last free throw of a trip);
       anything else leaves no arrow rather than a guess. ESPN's own block,
       when it carries the ball, wins.
     · RUNS, LEADS, TIES and DROUGHTS off the running score.
     · WHO IS ON THE FLOOR from the box score's starters and the
       substitutions — and only when every substitution in the game is
       possible under one order of ESPN's two names (hoopsprobe.py checks
       the order on the box). One impossible step and the tracker says it
       cannot tell, rather than show the wrong five.
   ESPN's written sentences are not in the file and are not drawn: a play
   reads as its type label, the names and the score. A name's role (the
   assist, the block, the steal, who drew the foul) is said only when the
   box score puts him on the side that role belongs to.

   THE COURT ON THE PICTURE. The four corners of the floor were read off the
   render at full size (1672 × 941): the far sideline at y = 594 between
   x = 440 and 1233, the near one at y = 830 between 189 and 1482 (where the
   wood meets the front row; the centre circle says the true line may sit
   ten pixels lower, behind the heads — under six pixels at centre court).
   A perspective map through those four puts a spot in feet on the picture.
   The render's own lines are drawn about a tenth larger than a regulation
   court (its arc sits 26 feet from the rim, not 23.75), so a shot's
   distance from its basket is stretched by ART_STRETCH before it is mapped:
   a three lands outside the painted arc, a layup in the paint. The rims are
   where the render draws them, (372, 566) and (1300, 566).

   Loaded by detail.js (gpSportMod) the first time a basketball game opens;
   uses app.js's helpers by name. No inline handlers. */
(function () {
  "use strict";
  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const num = (v) => { const n = Number(v); return v === null || v === "" || !Number.isFinite(n) ? null : n; };
  const lower = (s) => String(s || "").toLowerCase();
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const still = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* What the reader chose on the arena, kept across the page's redraws, and
     the game it was chosen on (`game`: another game starts its run again). */
  const S = { view: "live", shots: "both", run: null, replay: false, game: "" };

  /* ---------------- the clock ---------------- */
  /* A regulation period's seconds: the NBA's and the WNBA's quarters, and
     college's halves (2026-11-13: two of twenty minutes, five-minute
     overtimes like everyone's). */
  const QUARTER_S = { nba: 720, wnba: 600, cbb: 1200 };
  const REG_PERIODS = { cbb: 2 };
  const regN = (league) => REG_PERIODS[league] || 4;
  const OT_S = 300;
  const periodLen = (league, p) => (p > regN(league) ? OT_S : (QUARTER_S[league] || 720));
  function clockSecs(c) {
    const s = String(c == null ? "" : c).trim();
    if (!s) return null;
    const m = /^(\d+):(\d{1,2}(?:\.\d+)?)$/.exec(s);
    if (m) return Number(m[1]) * 60 + Number(m[2]);
    const f = Number(s);
    return Number.isFinite(f) ? f : null;
  }
  /* Seconds since the tip at this play. */
  function elapsed(league, p) {
    const per = Math.max(1, Number(p && p.period) || 1);
    let t = 0;
    for (let i = 1; i < per; i++) t += periodLen(league, i);
    const left = clockSecs(p && p.clock);
    return t + (left == null ? 0 : clamp(periodLen(league, per) - left, 0, periodLen(league, per)));
  }
  /* The league `render` is drawing, for the period's words: a quarter's
     "1st" and "Q1", or a college half's "1st half" and "H1". */
  let LG = "";
  const periodWord = (p, lg = LG) => {
    const n = regN(lg);
    return !p ? "" : p <= n ? (n === 2 ? ["1st half", "2nd half"] : ["1st", "2nd", "3rd", "4th"])[p - 1]
      : p === n + 1 ? "OT" : `${p - n}OT`;
  };
  const periodShort = (p, lg = LG) => {
    const n = regN(lg);
    return !p ? "" : p <= n ? `${n === 2 ? "H" : "Q"}${p}` : p === n + 1 ? "OT" : `${p - n}OT`;
  };
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

  /* ---------------- sides and the box ---------------- */
  const sideOf = (d, team) => (team && team === d.home ? "home" : team && team === d.away ? "away" : "");
  const other = (side) => (side === "home" ? "away" : side === "away" ? "home" : "");
  /* One side's box rows (ESPN's basketball box is one table a side). */
  function boxOf(d, team) {
    const groups = (((d.box || []).find((b) => b.team === team)) || {}).groups || [];
    const g = groups[0] || { labels: [], rows: [] };
    return { labels: g.labels || [], rows: g.rows || [] };
  }
  function cellOf(box, row, label) {
    const i = (box.labels || []).findIndex((l) => String(l).toUpperCase() === label);
    return i >= 0 ? (row.stats || [])[i] : undefined;
  }
  /* Which side a name plays for, by the box score — "" when neither lists him. */
  function rosterSide(d) {
    const by = {};
    for (const side of ["away", "home"]) boxOf(d, d[side]).rows.forEach((r) => { if (r.name) by[r.name] = side; });
    return (name) => by[name] || "";
  }

  /* ---------------- the ball, the runs, the five ---------------- */
  /* Whose ball it is after the last play — "home", "away" or "" when the
     plays do not settle it. Walks back over what does not move the ball
     (substitutions, timeouts, reviews, technicals) to the first play that
     does; the end of a period settles nothing. */
  function ballAfter(d) {
    const plays = d.plays || [];
    for (let i = plays.length - 1; i >= 0; i--) {
      const p = plays[i] || {}, ev = lower(p.event);
      if (/end (of )?(period|game|quarter)|end period|end game/.test(ev)) return "";
      if (/substitution|timeout|review|challenge|delay of game|ejection|technical|goaltending/.test(ev)) continue;
      const own = sideOf(d, p.team);
      if (!own) return "";
      if (/rebound/.test(ev)) return own;
      if (/turnover|traveling/.test(ev)) return other(own);
      if (/free throw/.test(ev)) {
        const m = /(\d+)\s*of\s*(\d+)/.exec(ev);
        if (!m) return "";
        if (Number(m[1]) < Number(m[2])) return own;
        return p.scoring ? other(own) : "";
      }
      if (p.shot) return p.scoring ? other(own) : "";
      if (/foul|violation/.test(ev)) return other(own);
      return "";
    }
    return "";
  }

  /* The running score as a series: `{t, m, h, a}` with `m` home minus away. */
  function flow(d, league) {
    const out = [{ t: 0, m: 0, h: 0, a: 0, p: 1 }];
    for (const p of d.plays || []) {
      if (!p || p.home_score == null || p.away_score == null) continue;
      const last = out[out.length - 1];
      if (p.home_score === last.h && p.away_score === last.a) continue;
      out.push({ t: elapsed(league, p), m: p.home_score - p.away_score, h: p.home_score, a: p.away_score,
                 p: Number(p.period) || 1 });
    }
    return out;
  }
  /* Lead changes, ties, each side's largest lead, the run in progress (the
     last scorer's points since the other side last scored, from six) and
     the game's longest such run. */
  function leads(d, league) {
    const f = flow(d, league);
    let changes = 0, ties = 0, sign = 0;
    const big = { home: 0, away: 0 };
    let cur = { side: "", pts: 0 }, best = { side: "", pts: 0 };
    for (let i = 1; i < f.length; i++) {
      const s = Math.sign(f[i].m);
      if (s === 0) { if (f[i - 1].m !== 0) ties++; } else { if (sign && s !== sign) changes++; sign = s; }
      big.home = Math.max(big.home, f[i].m);
      big.away = Math.max(big.away, -f[i].m);
      const dh = f[i].h - f[i - 1].h, da = f[i].a - f[i - 1].a;
      const side = dh > 0 && da <= 0 ? "home" : da > 0 && dh <= 0 ? "away" : "";
      const pts = side === "home" ? dh : side === "away" ? da : 0;
      cur = side && side === cur.side ? { side, pts: cur.pts + pts } : { side, pts };
      if (cur.pts > best.pts) best = { ...cur };
    }
    return { changes, ties, big, run: cur.side && cur.pts >= 6 ? cur : null, best: best.pts ? best : null };
  }
  /* Seconds since each side's last field goal, at the last play. */
  function droughts(d, league) {
    const plays = d.plays || [];
    if (!plays.length) return { home: 0, away: 0 };
    const now = elapsed(league, plays[plays.length - 1]);
    const last = { home: 0, away: 0 };
    plays.forEach((p) => {
      const side = sideOf(d, p.team);
      if (side && p.shot && p.scoring && (p.points_attempted || 0) >= 2) last[side] = elapsed(league, p);
    });
    return { home: now - last.home, away: now - last.away };
  }
  /* Who is on the floor: the starters, then every substitution played
     forward under one order of ESPN's two names. `null` when the box marks
     no five or neither order is possible end to end. */
  function onFloor(d) {
    const start = {};
    for (const side of ["home", "away"]) {
      start[side] = boxOf(d, d[side]).rows.filter((r) => r.starter).map((r) => r.name);
      if (start[side].length !== 5) return null;
    }
    const subs = (d.plays || []).filter((p) => /substitution/i.test(String(p.event || "")));
    for (const inFirst of [true, false]) {
      const floor = { home: new Set(start.home), away: new Set(start.away) };
      let ok = true;
      for (const p of subs) {
        const side = sideOf(d, p.team), two = p.players || [];
        const enter = inFirst ? two[0] : two[1], leave = inFirst ? two[1] : two[0];
        if (!side || two.length !== 2 || !enter || !leave || floor[side].has(enter) || !floor[side].has(leave)) {
          ok = false;
          break;
        }
        floor[side].delete(leave);
        floor[side].add(enter);
      }
      if (ok) return { home: [...floor.home], away: [...floor.away], inFirst };
    }
    return null;
  }

  /* ---------------- the shots and the court ---------------- */
  function shotsOf(d) {
    return (d.plays || []).filter((p) => p && p.shot && (p.points_attempted || 0) >= 2).map((p, i) => ({
      id: String(p.id || i), team: p.team, side: sideOf(d, p.team), made: !!p.scoring,
      pts: p.points_attempted, player: p.player || "", x: num(p.x), y: num(p.y),
      period: p.period, clock: p.clock || "", event: p.event || "", second: (p.players || [])[1] || "",
    }));
  }
  //: The league's zones (engine/nba/shots.zone), in feet from the rim.
  const ZONES = [["ra", "At the rim"], ["paint", "In the paint"], ["mid", "Mid-range"], ["corner3", "Corner 3"],
                 ["above3", "Above the break 3"]];
  function zoneOf(s) {
    if (s.x == null || s.y == null) return "";
    const dx = s.x - 25, dy = s.y;
    if (s.pts === 3) return dy <= 9.25 ? "corner3" : "above3";
    if (Math.hypot(dx, dy) <= 4) return "ra";
    return Math.abs(dx) <= 8 && dy <= 14.25 ? "paint" : "mid";
  }
  //: Feet from the baseline to the middle of the rim.
  const HOOP = 5.25;
  /* A shot's spot on our full court, `{u, v}` in feet: `u` along the floor
     from the left baseline, `v` across from the far sideline. ESPN's spot
     is the shooting side's own half (x across, y out from the rim at
     (25, 0)); the away side shoots at the left basket, the home side at
     the right — a drawing convention, as ESPN's full-court chart has one. */
  function courtSpot(s) {
    if (s.x == null || s.y == null || !s.side) return null;
    const dx = s.x - 25, dy = Math.max(0, s.y);
    const away = s.side === "away";
    return { u: clamp(away ? HOOP + dy : 94 - HOOP - dy, 0, 94), v: clamp(away ? 25 + dx : 25 - dx, 0, 50) };
  }

  /* THE RENDER'S PERSPECTIVE: four floor corners (court feet → pixels on
     the 1672 × 941 render), the map solved once. */
  const ART = { w: 1672, h: 941 };
  const CORNERS = [[[0, 0], [440, 594]], [[94, 0], [1233, 594]], [[0, 50], [189, 830]], [[94, 50], [1482, 830]]];
  const RIMS = { away: [372, 566], home: [1300, 566] };
  const ART_STRETCH = 1.1;
  function solve(A, b) {
    const n = b.length, M = A.map((row, i) => row.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = 0; r < n; r++) {
        if (r === c) continue;
        const f = M[r][c] / M[c][c];
        for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    return M.map((row, i) => row[n] / row[i]);
  }
  function homography(pairs) {
    const A = [], b = [];
    pairs.forEach(([[u, v], [x, y]]) => {
      A.push([u, v, 1, 0, 0, 0, -x * u, -x * v]); b.push(x);
      A.push([0, 0, 0, u, v, 1, -y * u, -y * v]); b.push(y);
    });
    const h = solve(A, b);
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  }
  const H = homography(CORNERS);
  function toArt(u, v) {
    const w = H[2][0] * u + H[2][1] * v + 1;
    return [(H[0][0] * u + H[0][1] * v + H[0][2]) / w, (H[1][0] * u + H[1][1] * v + H[1][2]) / w];
  }
  /* A court spot on the render: stretched about its basket to the render's
     own lines, kept on the floor, then mapped. */
  function artSpot(c, side) {
    const hu = side === "away" ? HOOP : 94 - HOOP;
    return toArt(clamp(hu + (c.u - hu) * ART_STRETCH, 0.5, 93.5), clamp(25 + (c.v - 25) * ART_STRETCH, 0.5, 49.5));
  }

  /* ---------------- colour ---------------- */
  function rgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function luminance(c) {
    const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  /* Each side's colour as the page draws it: the first of the club's own
     three that reads on a dark floor, and the away side takes its next one
     when the two would be hard to tell apart. The floor (0.065) is where the
     Lakers' purple gives way to their gold, as Ethan's render draws them;
     the Heat's red still clears it. */
  const READS_ON_DARK = 0.065;
  function colours(league, d) {
    const table = typeof teamsIn === "function" ? (teamsIn(league) || {}) : {};
    const reads = (abbr) => { const t = table[abbr] || {}; return [t.primary, t.secondary, t.tertiary].filter((c) => rgb(c) && luminance(rgb(c)) >= READS_ON_DARK); };
    const apart = (a, b) => { const x = rgb(a), y = rgb(b); return !x || !y || Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) >= 90; };
    const home = reads(d.home)[0] || "var(--text-mute)";
    const away = reads(d.away).find((c) => apart(c, home)) || reads(d.away)[0] || "var(--brand)";
    return { home, away };
  }

  /* ---------------- faces ---------------- */
  function faceHTML(league, row, faces, size) {
    const G = window.QBGamecast;
    const src = G && G.faceURL ? G.faceURL(league, row || {}, faces || {}) : "";
    if (!src) return `<span class="hc-face">${icon("people", 14)}</span>`;
    const small = typeof facePreview === "function" ? facePreview(src, size || 40) : src;
    // A face that misses waits and comes back (visuals.js FACES COME BACK).
    if (typeof faceImg === "function") {
      return `<span class="hc-face">${icon("people", 14)}<img ${faceImg(small, src).attrs} alt="" data-onerr="swapFull"></span>`;
    }
    const fall = small !== src ? ` data-full="${escapeAttr(src)}" data-onerr="swapFull"` : "";
    return `<span class="hc-face">${icon("people", 14)}<img src="${escapeAttr(small)}" alt="" loading="lazy" decoding="async"${fall}></span>`;
  }

  /* ---------------- on the score ----------------
     The score is the page's own (detail.js pbpBoardHTML), the same for every
     sport. Basketball's part of it: the ball beside the side that has it
     (`parts`), and under each side's record the scorer's table when ESPN's
     block carries it (livescore_build.pbp_doc `situation`): the bonus, the
     team fouls, the timeouts left. */
  function marksHTML(d, ha) {
    const sit = d.situation || {};
    const marks = [
      sit.bonus && sit.bonus[ha] ? `<span class="hc-bonus">Bonus</span>` : "",
      sit.fouls && sit.fouls[ha] != null ? `<span class="hc-k">Fouls <b>${esc(sit.fouls[ha])}</b></span>` : "",
      sit.timeouts && sit.timeouts[ha] != null ? `<span class="hc-k">Timeouts <b>${esc(sit.timeouts[ha])}</b></span>` : "",
    ].join("");
    return marks ? `<span class="hc-marks-row">${marks}</span>` : "";
  }

  //: A side by its club's name; a school the table does not know (keyed "espn:<id>") by the scoreboard's own letters, never its key.
  function sideName(d, league, ha) {
    const name = teamNameIn(league, d[ha]) || "";
    return name && !String(name).startsWith("espn:") ? name : (d[`${ha}_abbr`] || d[ha] || "");
  }
  //: A run in words: the side by its short name, and "an 8–0 run" where the number is said with a vowel.
  const runSide = (d, run) => d[`${run.side}_abbr`] || d[run.side] || "";
  const anRun = (pts) => (/^(8|11|18)/.test(String(pts)) ? "an" : "a");

  /* ---------------- the arena ---------------- */
  const PICTURE = `<picture data-gp-hold="arena">
      <source type="image/webp" srcset="img/arena/nba-arena@640.webp 640w, img/arena/nba-arena.webp 1280w" sizes="(max-width: 720px) 190vw, 100vw">
      <img class="hc-photo" src="img/arena/nba-arena.jpg" srcset="img/arena/nba-arena@640.jpg 640w, img/arena/nba-arena.jpg 1280w"
        sizes="(max-width: 720px) 190vw, 100vw" alt="" decoding="async"></picture>`;
  //: The four corners of a full-screen button, drawn the way app.js's icons are.
  const EXPAND = `<svg class="ic" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/></svg>`;
  //: Replay's mark, in the same stroke grid.
  const REPLAY = `<svg class="ic" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3.2 8a4.8 4.8 0 1 0 1.4-3.4"/><path d="M3 2.6v3h3"/></svg>`;
  const cross = (x, y, r) => `M${(x - r).toFixed(1)} ${(y - r).toFixed(1)} l${2 * r} ${2 * r} m0 ${-2 * r} l${-2 * r} ${2 * r}`;
  function shotMark(s, alpha, k) {
    const c = courtSpot(s);
    if (!c) return "";
    const [x, y] = artSpot(c, s.side);
    const col = s.side === "home" ? "var(--ch)" : "var(--ca)";
    const r = 9;
    // A miss is drawn over a dark edge of itself, as a make is ringed in
    // one: a club in gold still reads on the wood.
    return s.made
      ? `<circle class="hc-shot made" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" style="fill:${col};opacity:${alpha.toFixed(2)}"/>`
      : `<g style="opacity:${alpha.toFixed(2)}"><path class="hc-halo" d="${cross(x, y, r - 2)}"/>`
        + `<path class="hc-shot miss" d="${cross(x, y, r - 2)}" style="stroke:${col}"/></g>`;
  }
  /* The ball's side, as an arrow at centre court pointing at the basket it
     attacks. */
  function arrowSVG(side) {
    if (!side) return "";
    const [x, y] = toArt(47, 25);
    const dir = side === "away" ? -1 : 1, col = side === "home" ? "var(--ch)" : "var(--ca)";
    return `<path class="hc-arrow" style="fill:${col}" d="M${(x + dir * 46).toFixed(1)} ${y.toFixed(1)} l${-dir * 30} -16 v32 z"/>`;
  }
  /* THE BALL'S RUN (2026-10-15; Ethan, of the hockey page's puck: "a
     hockey puck moving back and forth across the ice when we show the
     switching of positions" — the ball does it here). The ball goes
     through the newest shots in order: from where the last one ended to
     where the next went up (across the court when the other side shoots
     next, a step when the same side has it again), then up to the rim on
     the shot's arc, through on a make and off the iron on a miss. Its
     glow is the shooting side's colour on the way to each shot. No feed
     has the ball between shots, so the run joins where shots went up, in
     order, and the plays down the side say what came between. The first
     look plays the newest six; a refresh with new shots moves the ball on
     from where it stopped; Replay plays the six again (js/gamecast.js
     `track` keeps the time; less motion asked for, the end of the run). */
  const RUN = 6;
  //: Which run the page is in: a new one when the game, the point the ball
  //: ends on or Replay says so; otherwise the same one, further on.
  function runFor(d, end, keys) {
    const now = Date.now(), r = S.run;
    if (S.replay || !r || r.game !== d.event_id) {
      S.run = { game: d.event_id, upto: end, from: null, start: now };
    } else if (r.upto !== end) {
      S.run = { game: d.event_id, upto: end, from: keys.includes(r.upto) ? r.upto : null, start: now };
    }
    S.replay = false;
    return { from: S.run.from, elapsed: (now - S.run.start) / 1000 };
  }
  //: The top of a shot's arc from its spot to the rim.
  const apex = (x, y, rx, ry) => [(x + rx) / 2, Math.min(y, ry) - 120];
  //: The basket a run of shots stays at ("left", "right"), or null when it
  //: goes end to end — a phone shows the whole court for that.
  function runSpan(k) {
    const win = k.shots.filter((s) => courtSpot(s)).slice(-RUN);
    if (!win.length) return null;
    if (win.every((s) => s.side === "away")) return "left";
    if (win.every((s) => s.side === "home")) return "right";
    return null;
  }
  function liveMarks(d, k) {
    const on = (d.live || {}).state === "live";
    const win = k.shots.filter((s) => courtSpot(s)).slice(-RUN);
    const last = win[win.length - 1];
    if (!last) return on ? arrowSVG(k.ballSide) : "";
    const W = [];
    win.forEach((s, n) => {
      const [x, y] = artSpot(courtSpot(s), s.side);
      const [rx, ry] = RIMS[s.side] || RIMS.home;
      W.push({ key: String(s.id), x, y, jump: n > 0 && win[n - 1].period !== s.period, s, side: s.side, hold: 0.15 });
      W.push({ key: `${s.id}>rim`, x: rx, y: ry, via: apex(x, y, rx, ry), s, side: s.side, leg: 0.6, hold: s.made ? 0.35 : 0.05, rim: true });
      if (!s.made) W.push({ key: `${s.id}>off`, x: rx + (s.side === "home" ? -70 : 70), y: ry + 45, s, side: "", leg: 0.3, hold: 0.3 });
    });
    const run = runFor(d, W[W.length - 1].key, W.map((p) => p.key));
    const from = run.from == null ? 0 : Math.max(0, W.findIndex((p) => p.key === run.from));
    const pts = W.slice(from).map((p, n) => (n ? p : Object.assign({}, p, { jump: false, via: null })));
    const G = window.QBGamecast;
    const T = G && G.track ? G.track(pts, { elapsed: run.elapsed }) : null;
    const moving = !!(T && !T.still);
    const when = (list, n) => (moving && n > from ? list[n - from] : null);
    const pop = (t, inner) => (t == null || T.past(t) ? inner
      : `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.2s" begin="${T.begin(t)}" fill="freeze"/>${inner}</g>`);
    // Each shot's mark shows as its ball reaches the rim: that is where it is decided.
    const rimAt = (s) => W.findIndex((p) => p.s === s && p.rim);
    const marks = win.slice(0, -1).map((s, i) => pop(when(T ? T.at : [], rimAt(s)),
      shotMark(s, 0.3 + 0.55 * (i + 1) / Math.max(1, win.length - 1), k))).join("");
    // The newest shot: the ring where it went up, its flight as the ball
    // takes off on it, its mark and a swish as it gets to the rim.
    const si = W.findIndex((p) => p.s === last), ri = rimAt(last);
    const { x, y } = W[si], [rx, ry] = [W[ri].x, W[ri].y], [cx, cy] = W[ri].via;
    const d2 = `M${x.toFixed(1)} ${y.toFixed(1)} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${rx} ${ry}`;
    const ring = pop(when(T ? T.at : [], si), `<circle class="hc-halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="22"/>
      <circle class="hc-spot-ring" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="22"/>`);
    const flight = pop(when(T ? T.go : [], ri), `<path class="hc-halo" d="${d2}"/><path class="hc-flight${last.made ? " made" : ""}" d="${d2}"/>`);
    const done = pop(when(T ? T.at : [], ri), `${shotMark(last, 1, k)}${last.made ? `<circle class="hc-swish" cx="${rx}" cy="${ry}" r="18"/>` : ""}`);
    // The ball, on top: its glow the shooting side's on the way to each
    // shot; at rest, the side the plays give it to, while the game is on.
    const rest = on ? k.ballSide : "";
    const glow = (side) => {
      const lit = (v) => (v === side ? "0.5" : "0");
      const anim = moving ? T.steps("opacity", pts.map((p, n) => lit(n && !p.jump ? p.side : "")), lit(rest)) : "";
      return `<circle class="hc-ball-side" r="28" style="fill:${side === "home" ? "var(--ch)" : "var(--ca)"}" opacity="${lit(rest)}">${anim}</circle>`;
    };
    const end = W[W.length - 1];
    const ball = `<g class="hc-ball-g" transform="translate(${end.x.toFixed(1)} ${end.y.toFixed(1)})">${glow("away")}${glow("home")}
      <circle class="hc-ball-glow" r="18"/><circle class="hc-ball-dot" r="12"/>${moving ? T.motion : ""}</g>`;
    const arrow = on ? arrowSVG(k.ballSide) : "";
    return `${marks}${ring}${flight}${done}${ball}${moving && arrow ? pop(T.dur, arrow) : arrow}`;
  }
  function shotsMarks(k) {
    return k.shots.filter((s) => courtSpot(s) && (S.shots === "both" || s.side === S.shots))
      .map((s) => shotMark(s, 0.92, k)).join("");
  }
  function trackerHTML(d, league, k) {
    const floor = k.floor;
    const col = (ha) => {
      const box = boxOf(d, d[ha]);
      let rows = floor ? floor[ha].map((n) => box.rows.find((r) => r.name === n)).filter(Boolean) : [];
      if (!floor) rows = box.rows.slice().sort((a, b) => (num(cellOf(box, b, "PTS")) || 0) - (num(cellOf(box, a, "PTS")) || 0)).slice(0, 5);
      const line = (r) => [["PTS", "PTS"], ["REB", "REB"], ["AST", "AST"]].map(([l, w]) => {
        const v = cellOf(box, r, l);
        return v != null && v !== "" ? `${esc(v)} ${w}` : "";
      }).filter(Boolean).join(" · ");
      const pf = (r) => { const v = num(cellOf(box, r, "PF")); return v == null ? "" : `<span class="hc-pf${v >= 5 ? " hot" : ""}">PF ${v}</span>`; };
      return `<div class="hc-trk-col"><div class="hc-trk-head">${teamMarkIn(league, d[ha], 22)} ${esc(sideName(d, league, ha))}</div>
        ${rows.length ? rows.map((r) => `<div class="hc-trk-row">${faceHTML(league, r, k.faces, 34)}
          <div class="hc-trk-t"><b>${esc(r.name)}</b><span>${line(r) || "&nbsp;"}</span></div>${pf(r)}</div>`).join("")
          : `<p class="rail-quiet">No box score yet.</p>`}</div>`;
    };
    const head = floor ? "On the floor" : "Leading scorers";
    const note = floor ? "From the starters and every substitution since."
      : "Who is on the floor is not in this game's feed yet, so these are the leading scorers.";
    return `<div class="hc-pane-head"><b>${head}</b><span class="mini">${esc(note)}</span></div>
      <div class="hc-trk">${col("away")}${col("home")}</div>`;
  }
  /* The margin over the game, home above the line and away below. */
  function flowSVG(d, league, k, h) {
    const f = flow(d, league);
    if (f.length < 2) return `<p class="rail-quiet">The game flow draws itself from the first basket.</p>`;
    const reg = regN(league) * (QUARTER_S[league] || 720);
    const end = Math.max(reg, f[f.length - 1].t);
    const W = 1000, H2 = h || 240, mid = H2 / 2;
    const top = Math.max(10, ...f.map((r) => Math.abs(r.m)));
    const X = (t) => (t / end) * W, Y = (m) => mid - (m / top) * (mid - 12);
    let line = `M0 ${mid}`;
    f.forEach((r, i) => { if (i) line += ` H${X(r.t).toFixed(1)} V${Y(r.m).toFixed(1)}`; });
    const tail = ` H${X(end === reg && (d.live || {}).state === "final" ? end : f[f.length - 1].t).toFixed(1)}`;
    const area = `${line}${tail} V${mid} Z`;
    let quarters = "";
    for (let p = 1, t = 0; t < end; p++) {
      t += periodLen(league, p);
      if (t < end) quarters += `<line class="hc-q-line" x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="0" y2="${H2}"/>`;
    }
    return `<svg class="hc-flow" viewBox="0 0 ${W} ${H2}" preserveAspectRatio="none" role="img" aria-label="Score margin over the game">
      <defs><clipPath id="hcf-top"><rect x="0" y="0" width="${W}" height="${mid}"/></clipPath>
        <clipPath id="hcf-bot"><rect x="0" y="${mid}" width="${W}" height="${mid}"/></clipPath></defs>
      ${quarters}<line class="hc-zero" x1="0" x2="${W}" y1="${mid}" y2="${mid}"/>
      <path class="hc-area home" clip-path="url(#hcf-top)" d="${area}"/>
      <path class="hc-area away" clip-path="url(#hcf-bot)" d="${area}"/>
      <path class="hc-line" d="${line}${tail}"/></svg>`;
  }
  function flowPaneHTML(d, league, k) {
    const L = k.leads;
    const big = (ha) => (L.big[ha] ? `+${L.big[ha]}` : "—");
    return `<div class="hc-pane-head"><b>Game flow</b><span class="mini">${esc(sideName(d, league, "home"))} above the line, ${esc(sideName(d, league, "away"))} below.</span></div>
      ${flowSVG(d, league, k, 220)}
      <div class="hc-flow-stats">
        <span><b>${L.changes}</b> lead changes</span><span><b>${L.ties}</b> ties</span>
        <span>${teamMarkIn(league, d.away, 16)} largest lead <b>${big("away")}</b></span>
        <span>${teamMarkIn(league, d.home, 16)} largest lead <b>${big("home")}</b></span></div>`;
  }
  /* A FINISHED GAME HAS NO LIVE PICTURE (Ethan, 2026-10-30: a past game's
     page is "just supposed to be the espn page with the past game data"):
     its arena opens on the shot chart, as ESPN's does, and Live is not offered. */
  const viewFor = (d) => (S.view === "live" && (d.live || {}).state === "final" ? "shots" : S.view);
  function stageHTML(d, league, k) {
    const view = viewFor(d);
    const last = k.shots.filter((s) => courtSpot(s)).slice(-1)[0];
    // A phone crops the live view to the basket the ball's run stays at,
    // and shows the whole court when the run goes end to end.
    const side = view === "live" && last ? (runSpan(k) || "none") : "none";
    const svg = view === "live" ? liveMarks(d, k) : view === "shots" ? shotsMarks(k) : "";
    const pane = view === "tracker" ? trackerHTML(d, league, k) : view === "flow" ? flowPaneHTML(d, league, k) : "";
    const v = d.venue || {};
    const where = v.name ? `<div class="hc-venue"><b>${esc(v.name)}</b>${v.city ? `<span>${esc([v.city, v.state].filter(Boolean).join(", "))}</span>` : ""}</div>` : "";
    const run = k.leads.run && (d.live || {}).state === "live" ? `<div class="hc-run" style="--rc:${k.leads.run.side === "home" ? "var(--ch)" : "var(--ca)"}">${icon("hot", 12)} ${esc(runSide(d, k.leads.run))} on ${anRun(k.leads.run.pts)} ${k.leads.run.pts}–0 run</div>` : "";
    const legend = view === "shots" ? shotLegendHTML(d, league, k) : "";
    // A phone reads the short word, so the four fit across it.
    const tabs = [["live", "Live", "Live", "basketball"], ["shots", "Shot Chart", "Shots", "target"],
                  ["tracker", "Player Tracker", "Players", "people"], ["flow", "Game Flow", "Flow", "chart"]]
      .filter(([key]) => key !== "live" || (d.live || {}).state !== "final").map(([key, label, short, ic]) =>
      `<button type="button" class="hc-view${view === key ? " on" : ""}" data-hc-view="${key}" aria-pressed="${view === key}" aria-label="${label}">${icon(ic, 13)}<span class="hc-vl">${label}</span><span class="hc-vs">${short}</span></button>`).join("");
    // The picture box holds the picture and what is pinned to it (the
    // building, the run); the caption, the legend, a pane and the views sit
    // over it on a wide screen and under it on a phone (css/hoopscast.css).
    // The arena's own screens lit with the game, and a big moment's banner
    // for a phone (detail.js pbpArenaSVG, the live page's file).
    const lit = typeof pbpArenaSVG === "function" ? pbpArenaSVG(d, league) : "";
    const shout = typeof pbpMomentBannerHTML === "function" ? pbpMomentBannerHTML(d, league) : "";
    // The card is the page's own (detail.js gpStageHTML); what is in it is this file's.
    return gpStageHTML(`hc-stage v-${view}`, `--ca:${k.colors.away};--ch:${k.colors.home}`, `
      <div class="hc-art" data-side="${side}">
        <div class="hc-frame">${PICTURE}
          <svg class="hc-svg" viewBox="0 0 ${ART.w} ${ART.h}" preserveAspectRatio="none" aria-hidden="true">${lit}${svg}</svg></div>
        ${shout}${where}${view === "live" ? run : ""}</div>
      ${legend}
      ${pane ? `<div class="hc-pane" data-gp-scroll="hc-${view}">${pane}</div>` : ""}
      <div class="hc-views" role="toolbar" aria-label="What the arena shows">${tabs}
        ${view === "live" && last ? `<button type="button" class="hc-replay" data-hc-replay aria-label="Replay the last shots">${REPLAY}<span>Replay</span></button>` : ""}<button type="button" class="hc-full" data-hc-full aria-label="Full screen">${EXPAND}</button></div>`);
  }
  function shotLegendHTML(d, league, k) {
    const tally = (side) => { const s = k.shots.filter((r) => r.side === side); return `${s.filter((r) => r.made).length}/${s.length}`; };
    const chip = (key, label) => `<button type="button" class="hc-chip${S.shots === key ? " on" : ""}" data-hc-shots="${key}">${label}</button>`;
    return `<div class="hc-legend">${chip("both", "Both")}${chip("away", `${esc(d.away_abbr || d.away)} ${tally("away")}`)}${chip("home", `${esc(d.home_abbr || d.home)} ${tally("home")}`)}
      <span class="hc-key"><i class="made"></i>Made <i class="miss"></i>Missed</span></div>`;
  }

  /* ---------------- the plays ---------------- */
  //: A play's type label with its words apart: college's run together ("JumpShot", "MadeFreeThrow").
  const labelOf = (p) => String((p && p.event) || "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\s+/g, " ").trim();
  function playKind(p) {
    const ev = lower(labelOf(p));
    if (/free throw/.test(ev)) return p.scoring ? "ft" : "ftmiss";
    if (/^block/.test(ev)) return "block";
    if (/^steal/.test(ev)) return "steal";
    if (p.shot) return p.scoring ? "made" : "miss";
    if (/rebound/.test(ev)) return "reb";
    if (/turnover|traveling/.test(ev)) return "to";
    if (/foul/.test(ev)) return "foul";
    if (/substitution/.test(ev)) return "sub";
    if (/time ?out/.test(ev)) return "time";
    if (/^end /.test(ev)) return "end";
    if (/jump ?ball/.test(ev)) return "jump";
    return "other";
  }
  //: The play's name on its card ("Three-pointer", "Rebound"); a kind with none is its own label.
  const KIND_WORD = { miss: "Missed shot", ft: "Free throw", ftmiss: "Missed free throw", reb: "Rebound", to: "Turnover", foul: "Foul",
                      sub: "Substitution", time: "Timeout", block: "Block", steal: "Steal", jump: "Jump ball" };
  const kindWord = (p) => (playKind(p) === "made" ? (Number(p.points_attempted) === 3 ? "Three-pointer" : /dunk/i.test(labelOf(p)) ? "Dunk" : "Basket")
    : KIND_WORD[playKind(p)] || labelOf(p) || "Play");
  /* A shot's label as words: "Driving Floating Jump Shot" → "driving floating
     jump shot", "Alley Oop Dunk Shot" → "alley-oop dunk", "Lay Up Shot" →
     "layup"; a three says so ("3-point pull-up jump shot"). */
  const SHOT_WORDS = [[/\blay up\b/g, "layup"], [/\balley oop\b/g, "alley-oop"], [/\bfade away\b/g, "fadeaway"], [/\bpullup\b/g, "pull-up"],
                      [/\bstep back\b/g, "step-back"], [/^layup shot putback$/, "putback layup"], [/^layup driving reverse$/, "driving reverse layup"],
                      [/^jump shot bank$/, "bank shot"], [/\b(layup|dunk) shot\b/g, "$1"], [/^tip shot$/, "tip-in"]];
  function shotWords(p) {
    let w = lower(labelOf(p)) || "shot";
    SHOT_WORDS.forEach(([re, to]) => { w = w.replace(re, to); });
    return `${Number(p.points_attempted) === 3 && !/three|3-point/.test(w) ? "3-point " : ""}${w}`;
  }
  /* WHO DID WHAT, IN OUR OWN WORDS (2026-11-21, when the page became every
     sport's; football's is app.js footballLine). A row read as a label and
     its facts ("Jump Shot · made 3 · assist Paul Reed"); it reads as a line
     now ("Isaiah Joe makes a 3-point jump shot, assist Paul Reed"), from the
     same facts: the play's type label, made or missed, and the second name's
     part only where the box score puts that player on the side the part
     belongs to. ESPN's own sentence is not in the file and is not drawn.
     Returned as the line's pieces, a string or a name ({b}), so a row sets
     the names in bold (`sayPlay`) and a card says them plain (`sayText`);
     null for a moment in the game, which `momentOf` names. */
  function said(p, d, k) {
    const kind = playKind(p), ev = labelOf(p), own = sideOf(d, p.team);
    if (kind === "end" || kind === "time") return null;
    const club = p.team && !String(p.team).startsWith("espn:") ? (teamNameIn(LG, p.team) || "") : "";
    const who = p.player ? { b: p.player } : club;
    const second = (p.players || [])[1] || "", theirs = second ? k.sideOfName(second) : "";
    const mate = second && theirs === own, foe = second && theirs === other(own);
    if (kind === "made") return [who, ` makes a ${shotWords(p)}`, ...(mate ? [", assist ", { b: second }] : [])];
    if (kind === "miss") return [who, ` misses a ${shotWords(p)}`, ...(foe ? [", blocked by ", { b: second }] : [])];
    if (kind === "ft" || kind === "ftmiss") {
      const n = /(\d+) of (\d+)/.exec(ev);
      return [who, ` ${kind === "ft" ? "makes" : "misses"} ${n ? `free throw ${n[1]} of ${n[2]}` : "a free throw"}`];
    }
    if (kind === "reb") {
      const which = /offensive/i.test(ev) ? "an offensive rebound" : /defensive/i.test(ev) ? "a defensive rebound" : "a rebound";
      // A rebound no player is credited with is the team's (the row and the card name the side).
      return p.player ? [who, ` grabs ${which}`] : ["Team rebound"];
    }
    if (kind === "to") {
      const why = lower(ev.replace(/\s*turnover\s*/i, " ").replace(/\s+/g, " ").trim());
      // A shot clock or an eight-second count is the team's turnover, nobody's.
      if (!p.player) return [why ? `${why.charAt(0).toUpperCase()}${why.slice(1)} turnover` : "Turnover"];
      return [who, " turns it over", why ? `: ${why}` : "", ...(foe ? [", stolen by ", { b: second }] : [])];
    }
    if (kind === "foul") return [`${ev.charAt(0)}${lower(ev.slice(1))}`, ...(who ? [" on ", who] : []), ...(foe ? [", drawn by ", { b: second }] : [])];
    if (kind === "block") return [who, " blocks the shot"];
    if (kind === "steal") return [who, " with the steal"];
    if (kind === "sub") {
      const [a, b] = p.players || [];
      // Who came in is said only when every substitution in the game fits one order of the two names (onFloor).
      if (k.floor && a && b) return [{ b: k.floor.inFirst ? a : b }, " in for ", { b: k.floor.inFirst ? b : a }];
      return ["Substitution", ...(who ? [": ", who] : [])];
    }
    if (kind === "jump") {
      const [a, b] = p.players || [];
      return a && b ? ["Jump ball: ", { b: a }, " and ", { b: b }] : ["Jump ball"];
    }
    return [...(who ? [who, ": "] : []), lower(ev) || "play"];
  }
  //: A moment in the game, as a quiet line of its own: a period's end, a timeout.
  function momentOf(p) {
    const kind = playKind(p), ev = labelOf(p);
    if (kind === "end") return `End of the ${periodWord(Number(p.period))}${regN(LG) === 4 && Number(p.period) <= 4 ? " quarter" : ""}`;
    if (kind !== "time") return "";
    const club = p.team && !String(p.team).startsWith("espn:") ? (teamNameIn(LG, p.team) || "") : "";
    const what = /tv|official/i.test(ev) ? "Media timeout" : /full/i.test(ev) ? "Full timeout" : /short|20/i.test(ev) ? "Short timeout" : "Timeout";
    return club && !/media/i.test(what) ? `${what}, ${club}` : what;
  }
  /* A row's words for the page's play list (app.js playsHTML `say`). */
  function sayPlay(p, d, k) {
    const m = momentOf(p);
    if (m) return { moment: m };
    const bits = said(p, d, k);
    return bits ? { html: bits.map((x) => (x && x.b ? `<b>${esc(x.b)}</b>` : esc(x))).join("") } : null;
  }
  /* THE PLAY RIGHT NOW, on the card every sport's is drawn on (js/gamecast.js
     playNow): the newest play in words, the score it left when it scored, and
     the people in it with their game so far. The caption under the arena
     said this, in a layout of its own. A run is said once, on the arena
     above it (stageHTML). */
  function nowHTML(d, league, k) {
    const G = window.QBGamecast;
    const plays = d.plays || [];
    // The newest play that is one. What has happened since that is not (a
    // timeout, a period's end, a substitution) is said under it, as
    // football's card says a timeout under its last snap.
    const aside = (r) => !!momentOf(r) || playKind(r) === "sub";
    const p = plays.slice().reverse().find((r) => r && r.event && !aside(r));
    const bits = p ? said(p, d, k) : null;
    if (!bits || !G || !G.playNow) return "";
    const text = (r) => momentOf(r) || (said(r, d, k) || []).map((x) => (x && x.b ? x.b : x)).join("");
    const score = p.scoring && p.away_score != null && p.home_score != null
      ? ` ${d.away_abbr || d.away} ${p.away_score}, ${d.home_abbr || d.home} ${p.home_score}.` : "";
    return G.playNow(d, league, k.faces, { team: p.team && !String(p.team).startsWith("espn:") ? p.team : "",
      when: [periodShort(p.period), p.clock].filter(Boolean).join(" "), kind: kindWord(p),
      said: `${bits.map((x) => (x && x.b ? x.b : x)).join("")}.${score}`,
      people: bits.filter((x) => x && x.b).map((x) => ({ name: x.b })),
      since: plays.slice(plays.indexOf(p) + 1).filter((r) => r && r.event).map(text).filter(Boolean).slice(-4) });
  }

  /* ---------------- the stats ---------------- */
  //: The rows the render lists, found by ESPN's own stat name or label.
  const TEAM_ROWS = [["Field goals", /^fieldGoalsMade-fieldGoalsAttempted$|^fg$|^field goals$/i],
                     ["3-pointers", /^threePointFieldGoalsMade-threePointFieldGoalsAttempted$|^3pt$|^three pointers$/i],
                     ["Free throws", /^freeThrowsMade-freeThrowsAttempted$|^ft$|^free throws$/i],
                     ["Rebounds", /^totalRebounds$|^rebounds$|^reb$/i], ["Assists", /^assists$|^ast$/i],
                     ["Turnovers", /^totalTurnovers$|^turnovers$|^to$/i], ["Steals", /^steals$|^stl$/i],
                     ["Blocks", /^blocks$|^blk$/i], ["Fast break points", /fastBreakPoints|fast break/i],
                     ["Points in the paint", /pointsInPaint|in paint/i], ["Points off turnovers", /turnoverPoints|off turnovers/i],
                     ["Largest lead", /largestLead|largest lead/i]];
  /* Each side's totals: ESPN's team stats where it lists them, else the box
     score added up — never a number of ours. */
  function teamTotals(d) {
    const ts = d.team_stats || {};
    const out = {};
    for (const side of ["away", "home"]) {
      const rows = ts[d[side]] || [];
      const pick = {};
      TEAM_ROWS.forEach(([label, re]) => {
        const r = rows.find((x) => re.test(String(x.name || "")) || re.test(String(x.label || "")));
        if (r && r.value != null && r.value !== "") pick[label] = String(r.value);
      });
      if (!Object.keys(pick).length) {
        const box = boxOf(d, d[side]);
        const sum = (label) => box.rows.reduce((a, r) => a + (num(cellOf(box, r, label)) || 0), 0);
        const pair = (label) => box.rows.reduce((a, r) => {
          const m = /^(\d+)-(\d+)$/.exec(String(cellOf(box, r, label) || ""));
          return m ? [a[0] + Number(m[1]), a[1] + Number(m[2])] : a;
        }, [0, 0]);
        if (box.rows.length) {
          [["Field goals", "FG"], ["3-pointers", "3PT"], ["Free throws", "FT"]].forEach(([w, l]) => { const p = pair(l); if (p[1]) pick[w] = `${p[0]}-${p[1]}`; });
          [["Rebounds", "REB"], ["Assists", "AST"], ["Turnovers", "TO"], ["Steals", "STL"], ["Blocks", "BLK"]].forEach(([w, l]) => { pick[w] = String(sum(l)); });
        }
      }
      out[side] = pick;
    }
    return out;
  }
  /* Every shot on a flat court, the away side at the left basket, and each
     side's makes by the league's zones. */
  function flatCourtHTML(d, league, k) {
    const shots = k.shots.filter((s) => courtSpot(s));
    const marks = shots.map((s) => {
      const c = courtSpot(s), x = c.u * 10, y = c.v * 10, col = s.side === "home" ? "var(--ch)" : "var(--ca)";
      return s.made ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7" class="hc-fs made" style="fill:${col}"/>`
        : `<path d="${cross(x, y, 5)}" class="hc-fs miss" style="stroke:${col}"/>`;
    }).join("");
    const half = (flip) => {
      const bx = flip ? 940 - 52.5 : 52.5, s = flip ? -1 : 1, base = flip ? 940 : 0;
      const a = Math.asin(220 / 237.5), cxr = bx + s * 237.5 * Math.cos(a);
      return `<rect x="${flip ? 940 - 190 : 0}" y="170" width="190" height="160" class="hc-fc-lane"/>
        <path d="M${base} 30 H${cxr.toFixed(1)} A237.5 237.5 0 0 ${flip ? 0 : 1} ${cxr.toFixed(1)} 470 H${base}" class="hc-fc-line"/>
        <circle cx="${base + s * 190}" cy="250" r="60" class="hc-fc-line"/><circle cx="${bx}" cy="250" r="7.5" class="hc-fc-rim"/>`;
    };
    const zones = (side) => {
      const mine = k.shots.filter((s) => s.side === side && courtSpot(s));
      return ZONES.map(([z, label]) => {
        const zz = mine.filter((s) => zoneOf(s) === z), m = zz.filter((s) => s.made).length;
        return zz.length ? `<div class="hc-zone"><span>${esc(label)}</span><b>${m}/${zz.length}</b><span class="mini">${Math.round((100 * m) / zz.length)}%</span></div>` : "";
      }).join("");
    };
    return `<svg class="hc-fcourt" viewBox="0 0 940 500" role="img" aria-label="Every shot from the floor">
        <rect x="0" y="0" width="940" height="500" class="hc-fc-floor"/>
        <rect x="0" y="0" width="940" height="500" class="hc-fc-line"/><line x1="470" y1="0" x2="470" y2="500" class="hc-fc-line"/>
        <circle cx="470" cy="250" r="60" class="hc-fc-line"/>${half(false)}${half(true)}${marks}</svg>
      <div class="hc-zones"><div>${teamMarkIn(league, d.away, 18)} <b>${esc(d.away_abbr || d.away)}</b>${zones("away") || `<p class="rail-quiet">No shots yet.</p>`}</div>
        <div>${teamMarkIn(league, d.home, 18)} <b>${esc(d.home_abbr || d.home)}</b>${zones("home") || `<p class="rail-quiet">No shots yet.</p>`}</div></div>`;
  }
  /* The trends, read off the plays: the pace against the board's total, each
     side's shooting, a run or a drought on now, how often the lead changed,
     the longest run of the game. */
  function trendsHTML(d, league, k) {
    const out = [];
    const lv = d.live || {}, plays = d.plays || [];
    const last = plays[plays.length - 1];
    const t = last ? elapsed(league, last) : 0, reg = regN(league) * (QUARTER_S[league] || 720);
    const h = num(lv.home_score), a = num(lv.away_score);
    const tot = num((k.boardGame || {}).total);
    if (lv.state === "live" && t >= 240 && t < reg && h != null && a != null) {
      const proj = Math.round(((h + a) * reg) / t);
      out.push(["gauge", `On pace for <b>${proj}</b> points${tot != null ? ` — the board's total is ${esc(tot)} (${proj > tot ? "over" : proj < tot ? "under" : "on"} it)` : ""}.`]);
    }
    const T = teamTotals(d);
    const pct = (s) => { const m = /^(\d+)-(\d+)$/.exec(String(s || "")); return m && Number(m[2]) ? Math.round((100 * Number(m[1])) / Number(m[2])) : null; };
    const fa = pct(T.away["Field goals"]), fh = pct(T.home["Field goals"]);
    if (fa != null && fh != null) out.push(["target", `Shooting: ${esc(d.away_abbr || d.away)} <b>${fa}%</b>, ${esc(d.home_abbr || d.home)} <b>${fh}%</b> from the floor.`]);
    const ta = pct(T.away["3-pointers"]), th = pct(T.home["3-pointers"]);
    if (ta != null && th != null) out.push(["target", `From three: ${esc(d.away_abbr || d.away)} <b>${ta}%</b>, ${esc(d.home_abbr || d.home)} <b>${th}%</b>.`]);
    if (k.leads.run && lv.state === "live") out.push(["hot", `${esc(runSide(d, k.leads.run))} on ${anRun(k.leads.run.pts)} <b>${k.leads.run.pts}–0</b> run.`]);
    ["away", "home"].forEach((ha) => { if (lv.state === "live" && k.droughts[ha] >= 180) out.push(["cold", `${esc(d[ha])}: no field goal in <b>${mmss(k.droughts[ha])}</b>.`]); });
    if (k.leads.changes || k.leads.ties) out.push(["rising", `<b>${k.leads.changes}</b> lead change${k.leads.changes === 1 ? "" : "s"} and <b>${k.leads.ties}</b> tie${k.leads.ties === 1 ? "" : "s"}${lv.state === "final" ? "" : " so far"}.`]);
    if (k.leads.best) out.push(["bolt", `Longest run: <b>${esc(d[k.leads.best.side])} ${k.leads.best.pts}–0</b>.`]);
    return out.length ? `<div class="hc-facts">${out.map(([ic, text]) => `<div class="hc-fact">${icon(ic, 14)}<span>${text}</span></div>`).join("")}</div>` : "";
  }
  /* What basketball adds to the page's Stats room, after the box scores: every
     shot from above with each side's makes by zone, and the trends. The cards
     are the page's own (detail.js gpCardHTML). */
  function statsExtraHTML(d, league, k) {
    const card = (title, sub, body) => gpCardHTML(title, sub, body, "hc-card", `--ca:${k.colors.away};--ch:${k.colors.home}`);
    const shots = k.shots.some((s) => courtSpot(s));
    return `${card("Shot chart", "every shot, from above", shots ? flatCourtHTML(d, league, k) : "")}${card("Trends", "", trendsHTML(d, league, k))}`;
  }

  /* ---------------- the parts of the page ----------------
     The page is every sport's now (detail.js gpPageHTML, 2026-11-21; Ethan:
     "all sports in all aspects should be trying to match nfl and that should
     be automatic when we do any visual changes"): the bar that stays when you
     scroll, the score on the clubs' colours, the line score, the rooms. This
     file drew a page of its own beside it, and nothing done there reached
     it. It brings what is basketball's (gpKit): the arena under the score,
     the newest play in words, the plays period by period in its own words,
     the shot chart and the trends, and on the score the ball and the scorer's
     table. Before the tip there is no arena, as there is no field. */
  function facts(d, league, ctx) {
    const sideOfName = rosterSide(d);
    const allRows = ["away", "home"].flatMap((ha) => boxOf(d, d[ha]).rows);
    const shots = shotsOf(d);
    const ball = ballAfter(d);
    return {
      colors: colours(league, d), shots, ball, ballSide: (d.situation || {}).possession || ball,
      leads: leads(d, league), droughts: droughts(d, league), floor: onFloor(d), sideOfName,
      findRow: (name) => allRows.find((r) => r.name === name) || null,
      faces: (ctx && ctx.faces) || {}, boardGame: (ctx && ctx.boardGame) || null,
    };
  }
  function parts(ctx) {
    const d = ctx.d, league = String(ctx.league || d.league || "");
    LG = league;
    if (S.game !== String(d.event_id)) { S.game = String(d.event_id); S.run = null; }
    const k = facts(d, league, ctx);
    const lv = d.live || {}, sit = d.situation || {};
    const live = lv.state === "live", on = live || lv.state === "final";
    return {
      stage: on ? stageHTML(d, league, k) : "",
      // The play right now, the ball and the scorer's table are a game being played's.
      now: live ? nowHTML(d, league, k) : "",
      say: (p) => sayPlay(p, d, k),
      statsExtra: on ? statsExtraHTML(d, league, k) : "",
      ball: live ? (k.ballSide || "") : "", ballIcon: "basketball",
      ballTitle: sit.possession ? "Ball" : "Ball — from the last play",
      marks: live ? { away: marksHTML(d, "away"), home: marksHTML(d, "home") } : null,
      wire,
    };
  }
  /* The arena's own buttons (the views, the shot chart's sides, Replay, full
     screen); a choice draws the page again (detail.js renderPbpPage), which
     keeps the picture already painted. Bound once to the page's host. */
  function wire(host) {
    if (!host || host.dataset.hcWired) return;
    host.dataset.hcWired = "1";
    host.addEventListener("click", (e) => {
      const t = e.target.closest("[data-hc-view],[data-hc-shots],[data-hc-full],[data-hc-replay]");
      if (!t || !host.contains(t)) return;
      if (t.hasAttribute("data-hc-full")) {
        const st = host.querySelector(".hc-stage");
        if (st && st.requestFullscreen) st.requestFullscreen().catch(() => {});
        return;
      }
      if (t.hasAttribute("data-hc-replay")) S.replay = true;
      if (t.dataset.hcView) S.view = t.dataset.hcView;
      if (t.dataset.hcShots) S.shots = t.dataset.hcShots;
      if (typeof renderPbpPage === "function") renderPbpPage();
    });
  }

  window.QBHoops = {
    parts,
    // The readers, for the tests and for Ask.
    ballAfter, flow, leads, droughts, onFloor, shotsOf, zoneOf, courtSpot, artSpot, toArt, homography,
    elapsed, clockSecs, colours, teamTotals, playKind, sayPlay, said, momentOf,
  };
})();
