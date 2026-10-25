/* Qellys Book — the basketball live page (js/hoopscast.js), in Ethan's render.
   ==========================================================================
   Ethan, 2026-10-15, with two renders — the arena (ours, the crown at centre
   court) and the page: "the live play by play screen for nba looks like shit
   ... figure out what live data we can get too make it look like an actual
   play by play screen like ball tracking or possessions". The old page drew
   the vector court at its own size inside a box built for photographs: a
   small court in the corner of an empty card.

   THE PAGE, TOP TO BOTTOM, as the render lays it out: the scoreboard (the
   clubs, their records, the score, the quarter and the clock — timeouts,
   team fouls and the bonus only when ESPN's scorer's-table block carries
   them, livescore_build.pbp_doc `situation`), the arena with four views
   (Live, Shot Chart, Player Tracker, Game Flow), then three panels: every
   play by quarter; the stats (Team | Players | Shots | Flow); the odds (the
   board's lines, our picks on the game with how each is going, the trends).

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

   Loaded by js/gamecast.js (QBGamecast.hoops) the first time a basketball
   game opens; uses app.js's helpers by name. No inline handlers. */
(function () {
  "use strict";
  const HOOPS = new Set(["nba", "wnba"]);
  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const num = (v) => { const n = Number(v); return v === null || v === "" || !Number.isFinite(n) ? null : n; };
  const lower = (s) => String(s || "").toLowerCase();
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const still = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* What the reader chose, kept across the twelve-second redraws. `q` null
     follows the quarter being played; 0 is every play. */
  const S = { view: "live", stats: "team", odds: "odds", q: null, shots: "both", run: null, replay: false, ctx: null };

  /* ---------------- the clock ---------------- */
  const QUARTER_S = { nba: 720, wnba: 600 };
  const OT_S = 300;
  const periodLen = (league, p) => (p > 4 ? OT_S : (QUARTER_S[league] || 720));
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
  const periodWord = (p) => (!p ? "" : p <= 4 ? ["1st", "2nd", "3rd", "4th"][p - 1] : p === 5 ? "OT" : `${p - 4}OT`);
  const periodShort = (p) => (!p ? "" : p <= 4 ? `Q${p}` : p === 5 ? "OT" : `${p - 4}OT`);
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
    const fall = small !== src ? ` data-full="${escapeAttr(src)}" data-onerr="swapFull"` : "";
    return `<span class="hc-face">${icon("people", 14)}<img src="${escapeAttr(small)}" alt="" loading="lazy" decoding="async"${fall}></span>`;
  }

  /* ---------------- the scoreboard ---------------- */
  function scoreboardHTML(d, league, k) {
    const lv = d.live || {}, sit = d.situation || {};
    const ball = sit.possession || k.ball;
    const table = typeof teamsIn === "function" ? (teamsIn(league) || {}) : {};
    const side = (ha) => {
      const abbr = d[ha], t = table[abbr] || {};
      const score = ha === "home" ? lv.home_score : lv.away_score;
      const rec = (d.records || {})[abbr];
      const marks = [
        sit.bonus && sit.bonus[ha] ? `<span class="hc-bonus">Bonus</span>` : "",
        sit.fouls && sit.fouls[ha] != null ? `<span class="hc-k">Fouls <b>${esc(sit.fouls[ha])}</b></span>` : "",
        sit.timeouts && sit.timeouts[ha] != null ? `<span class="hc-k">Timeouts <b>${esc(sit.timeouts[ha])}</b></span>` : "",
      ].join("");
      const has = lv.state === "live" && ball === ha
        ? `<span class="hc-ball" title="${sit.possession ? "Ball" : "Ball — from the last play"}">${icon("basketball", 14)}</span>` : "";
      return `<div class="hc-side ${ha}">
          <span class="hc-crest">${teamMarkIn(league, abbr, 56)}</span>
          <div class="hc-team"><span class="hc-loc">${esc(t.loc || "")}</span>
            <b class="hc-nick">${esc(t.nick || teamNameIn(league, abbr) || abbr)}</b>
            ${rec ? `<span class="hc-rec">${esc(rec)}</span>` : ""}${marks ? `<span class="hc-marks-row">${marks}</span>` : ""}</div>
          <b class="hc-pts">${has}${score != null ? esc(score) : "–"}</b></div>`;
    };
    const hold = lv.state === "live" && typeof liveHoldWord === "function" ? liveHoldWord(lv) : "";
    const per = /^Q(\d+)$/.exec(String(lv.period || ""));
    const pnum = per ? Number(per[1]) : 0;
    let mid;
    if (lv.state === "live") {
      mid = `<span class="hc-per">${esc(hold ? hold.split(/\s[—-]\s/)[0] : (periodWord(pnum) || lv.period || ""))}</span>
        <b class="hc-clock">${esc(hold ? "" : (lv.clock || ""))}</b>
        <span class="hc-live">${icon("dot", 8)} Live</span>`;
    } else if (lv.state === "final") {
      mid = `<span class="hc-per">Final</span><b class="hc-clock">${esc(pnum > 4 ? periodShort(pnum) : "")}</b>`;
    } else {
      const tip = typeof pbpTime === "function" ? pbpTime(lv.start_time) : "";
      mid = `<span class="hc-per">Tip-off</span><b class="hc-clock">${esc(tip || "—")}</b>`;
    }
    const ago = typeof pbpAgo === "function" ? pbpAgo(d.generated_at) : "";
    // The watch buttons are the card's last row, under the clock and both
    // sides. Inside the clock's column they set that column's width, and on
    // a phone that left each side 32px for a 56px crest and the score
    // (Ethan, 2026-10-20, 76ers @ Knicks: the crest under the "54").
    const watch = lv.state === "live" && typeof watchHTML === "function" ? watchHTML(d, league, "pbp-watch hc-watch") : "";
    return `<div class="card hc-score" style="--ca:${k.colors.away};--ch:${k.colors.home}">
      ${side("away")}
      <div class="hc-mid">${mid}${ago ? `<span class="hc-ago">${esc(ago)}</span>` : ""}</div>
      ${side("home")}${watch}</div>`;
  }

  /* ---------------- the arena ---------------- */
  const PICTURE = `<picture>
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
  /* The last play, in words the plays carry — the caption under the art. */
  function captionHTML(d, league, k) {
    const p = (d.plays || []).slice().reverse().find((r) => r && r.event && !/^end /i.test(String(r.event)));
    if (!p) return "";
    const row = k.findRow(p.player);
    return `<div class="hc-caption">
      ${p.player ? faceHTML(league, row || { name: p.player }, k.faces, 36) : (p.team ? teamMarkIn(league, p.team, 28) : "")}
      <div class="hc-cap-t"><span class="hc-cap-k">Last play · ${esc([periodShort(p.period), p.clock].filter(Boolean).join(" "))}</span>
        <b>${esc(p.player || teamNameIn(league, p.team) || "")}</b><span>${playWords(p, d, k)}</span></div>
      ${p.away_score != null ? `<span class="hc-cap-sc">${esc(d.away)} ${esc(p.away_score)} – ${esc(p.home_score)} ${esc(d.home)}</span>` : ""}</div>`;
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
      return `<div class="hc-trk-col"><div class="hc-trk-head">${teamMarkIn(league, d[ha], 22)} ${esc(teamNameIn(league, d[ha]) || d[ha])}</div>
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
    const reg = 4 * (QUARTER_S[league] || 720);
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
    return `<div class="hc-pane-head"><b>Game flow</b><span class="mini">${esc(teamNameIn(league, d.home) || d.home)} above the line, ${esc(teamNameIn(league, d.away) || d.away)} below.</span></div>
      ${flowSVG(d, league, k, 220)}
      <div class="hc-flow-stats">
        <span><b>${L.changes}</b> lead changes</span><span><b>${L.ties}</b> ties</span>
        <span>${teamMarkIn(league, d.away, 16)} largest lead <b>${big("away")}</b></span>
        <span>${teamMarkIn(league, d.home, 16)} largest lead <b>${big("home")}</b></span></div>`;
  }
  function stageHTML(d, league, k) {
    const view = S.view;
    const last = k.shots.filter((s) => courtSpot(s)).slice(-1)[0];
    // A phone crops the live view to the basket the ball's run stays at,
    // and shows the whole court when the run goes end to end.
    const side = view === "live" && last ? (runSpan(k) || "none") : "none";
    const svg = view === "live" ? liveMarks(d, k) : view === "shots" ? shotsMarks(k) : "";
    const pane = view === "tracker" ? trackerHTML(d, league, k) : view === "flow" ? flowPaneHTML(d, league, k) : "";
    const v = d.venue || {};
    const where = v.name ? `<div class="hc-venue"><b>${esc(v.name)}</b>${v.city ? `<span>${esc([v.city, v.state].filter(Boolean).join(", "))}</span>` : ""}</div>` : "";
    const run = k.leads.run && (d.live || {}).state === "live" ? `<div class="hc-run" style="--rc:${k.leads.run.side === "home" ? "var(--ch)" : "var(--ca)"}">${icon("hot", 12)} ${esc(d[k.leads.run.side])} on a ${k.leads.run.pts}–0 run</div>` : "";
    const legend = view === "shots" ? shotLegendHTML(d, league, k) : "";
    // A phone reads the short word, so the four fit across it.
    const tabs = [["live", "Live", "Live", "basketball"], ["shots", "Shot Chart", "Shots", "target"],
                  ["tracker", "Player Tracker", "Players", "people"], ["flow", "Game Flow", "Flow", "chart"]].map(([key, label, short, ic]) =>
      `<button type="button" class="hc-view${view === key ? " on" : ""}" data-hc-view="${key}" aria-pressed="${view === key}" aria-label="${label}">${icon(ic, 13)}<span class="hc-vl">${label}</span><span class="hc-vs">${short}</span></button>`).join("");
    // The picture box holds the picture and what is pinned to it (the
    // building, the run); the caption, the legend, a pane and the views sit
    // over it on a wide screen and under it on a phone (css/hoopscast.css).
    // The arena's own screens lit with the game, and a big moment's banner
    // for a phone (detail.js pbpArenaSVG, the live page's file).
    const lit = typeof pbpArenaSVG === "function" ? pbpArenaSVG(d, league) : "";
    const shout = typeof pbpMomentBannerHTML === "function" ? pbpMomentBannerHTML(d, league) : "";
    return `<div class="card hc-stage v-${view}" style="--ca:${k.colors.away};--ch:${k.colors.home}">
      <div class="hc-art" data-side="${side}">
        <div class="hc-frame">${PICTURE}
          <svg class="hc-svg" viewBox="0 0 ${ART.w} ${ART.h}" preserveAspectRatio="none" aria-hidden="true">${lit}${svg}</svg></div>
        ${shout}${where}${view === "live" ? run : ""}</div>
      ${legend}${view === "live" ? captionHTML(d, league, k) : ""}
      ${pane ? `<div class="hc-pane">${pane}</div>` : ""}
      <div class="hc-views" role="toolbar" aria-label="What the arena shows">${tabs}
        ${view === "live" && last ? `<button type="button" class="hc-replay" data-hc-replay aria-label="Replay the last shots">${REPLAY}<span>Replay</span></button>` : ""}<button type="button" class="hc-full" data-hc-full aria-label="Full screen">${EXPAND}</button></div></div>`;
  }
  function shotLegendHTML(d, league, k) {
    const tally = (side) => { const s = k.shots.filter((r) => r.side === side); return `${s.filter((r) => r.made).length}/${s.length}`; };
    const chip = (key, label) => `<button type="button" class="hc-chip${S.shots === key ? " on" : ""}" data-hc-shots="${key}">${label}</button>`;
    return `<div class="hc-legend">${chip("both", "Both")}${chip("away", `${esc(d.away)} ${tally("away")}`)}${chip("home", `${esc(d.home)} ${tally("home")}`)}
      <span class="hc-key"><i class="made"></i>Made <i class="miss"></i>Missed</span></div>`;
  }

  /* ---------------- the plays ---------------- */
  function playKind(p) {
    const ev = lower(p.event);
    if (/free throw/.test(ev)) return p.scoring ? "ft" : "ftmiss";
    if (p.shot) return p.scoring ? "made" : "miss";
    if (/rebound/.test(ev)) return "reb";
    if (/turnover|traveling/.test(ev)) return "to";
    if (/foul/.test(ev)) return "foul";
    if (/substitution/.test(ev)) return "sub";
    if (/timeout/.test(ev)) return "time";
    return "other";
  }
  const KIND = { made: "+", miss: "×", ft: "FT", ftmiss: "FT", reb: "R", to: "TO", foul: "PF", sub: "⇄", time: "T", other: "·" };
  /* The play in the plays' own words: the type label, made or missed, and
     the second man's role only where the box score puts him on that
     role's side. */
  function playWords(p, d, k) {
    const ev = String(p.event || "Play");
    const kind = playKind(p), own = sideOf(d, p.team);
    const second = (p.players || [])[1] || "", his = second ? k.sideOfName(second) : "";
    const bits = [esc(ev)];
    if (kind === "made" || kind === "miss") bits.push(`${kind === "made" ? "made" : "missed"} ${p.points_attempted || ""}`.trim());
    if (kind === "ftmiss") bits.push("missed");
    if (second && his) {
      if (kind === "made" && his === own) bits.push(`assist ${esc(second)}`);
      else if (kind === "miss" && his === other(own)) bits.push(`blocked by ${esc(second)}`);
      else if (kind === "to" && his === other(own)) bits.push(`stolen by ${esc(second)}`);
      else if (kind === "foul" && his === other(own)) bits.push(`drawn by ${esc(second)}`);
    }
    if (kind === "sub" && k.floor && (p.players || []).length === 2) {
      const [a, b] = p.players;
      bits.push(`${esc(k.floor.inFirst ? a : b)} in, ${esc(k.floor.inFirst ? b : a)} out`);
    }
    return bits.join(" · ");
  }
  function playsCardHTML(d, league, k) {
    const plays = d.plays || [];
    const periods = [...new Set(plays.map((p) => Number(p.period)).filter(Boolean))].sort((a, b) => a - b);
    const cur = periods[periods.length - 1] || 0;
    const q = S.q == null ? cur : S.q;
    const shown = plays.filter((p) => p && p.event && (q === 0 || Number(p.period) === q)).slice().reverse();
    const live = (d.live || {}).state === "live";
    const opts = [`<option value=""${S.q == null ? " selected" : ""}>${live ? "Now" : "Latest"}${cur ? ` — ${periodWord(cur)}` : ""}</option>`]
      .concat(periods.map((p) => `<option value="${p}"${S.q === p ? " selected" : ""}>${periodWord(p)}${p <= 4 ? " quarter" : ""}</option>`))
      .concat([`<option value="0"${S.q === 0 ? " selected" : ""}>Every play</option>`]).join("");
    const rows = shown.map((p) => {
      const kind = playKind(p), side = sideOf(d, p.team);
      const who = p.player || (p.team && !String(p.team).startsWith("espn:") ? teamNameIn(league, p.team) : "") || "";
      return `<div class="hc-play k-${kind}${p.scoring ? " scored" : ""}">
          <span class="hc-pclock">${esc(p.clock || "")}</span>
          <span class="hc-pmark">${side ? teamMarkIn(league, p.team, 22) : ""}</span>
          <span class="hc-pkind">${esc(KIND[kind])}</span>
          <span class="hc-pwhat">${who ? `<b>${esc(who)}</b>` : ""}<span>${playWords(p, d, k)}</span></span>
          <span class="hc-psc${p.scoring && side ? ` ${side}` : ""}">${p.away_score != null ? `${esc(p.away_score)}–${esc(p.home_score)}` : ""}</span>${
          typeof chatPlayBadge === "function" && d.event_id ? chatPlayBadge(`${league}_${d.event_id}`, p) : ""}</div>`;
    }).join("");
    return `<div class="card hc-card hc-plays">
      <div class="hc-card-head"><b>${live ? "Live Play by Play" : "Play by Play"}</b>${live ? `<span class="hc-pill">${icon("dot", 8)} Live</span>` : ""}
        <select class="hc-q" data-hc-q aria-label="Which quarter">${opts}</select></div>
      <div class="hc-play-list">${rows || `<p class="rail-quiet">No plays yet${cur ? " this quarter" : ""}.</p>`}</div></div>`;
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
  function teamStatsHTML(d, league, k) {
    const T = teamTotals(d), lv = d.live || {};
    const rows = [["Points", lv.away_score != null ? String(lv.away_score) : "", lv.home_score != null ? String(lv.home_score) : ""]]
      .concat(TEAM_ROWS.map(([label]) => [label, T.away[label], T.home[label]]))
      .filter(([, a, h]) => a != null && a !== "" && h != null && h !== "");
    if (rows.length <= 1) return `<p class="rail-quiet">The team stats fill in from the tip.</p>`;
    const val = (s) => { const m = /^(\d+)-(\d+)$/.exec(s); return m ? (Number(m[2]) ? Number(m[1]) / Number(m[2]) : 0) : (num(s) || 0); };
    // A shooting line reads as its rate, the makes and tries under it.
    const shown = (s) => { const m = /^(\d+)-(\d+)$/.exec(s); return m ? `${Number(m[2]) ? Math.round((100 * Number(m[1])) / Number(m[2])) : 0}%<small>${m[1]}/${m[2]}</small>` : esc(s); };
    return `<div class="hc-ts-head"><span>${teamMarkIn(league, d.away, 22)} <b>${esc(d.away)}</b></span><span><b>${esc(d.home)}</b> ${teamMarkIn(league, d.home, 22)}</span></div>
      ${rows.map(([label, a, h]) => {
        const x = val(a), y = val(h), top = Math.max(x, y) || 1;
        return `<div class="hc-ts"><b class="hc-ts-v">${shown(a)}</b>
          <span class="hc-bar away"><i style="width:${Math.round((x / top) * 100)}%"></i></span>
          <span class="hc-ts-k">${esc(label)}</span>
          <span class="hc-bar home"><i style="width:${Math.round((y / top) * 100)}%"></i></span>
          <b class="hc-ts-v r">${shown(h)}</b></div>`;
      }).join("")}`;
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
      <div class="hc-zones"><div>${teamMarkIn(league, d.away, 18)} <b>${esc(d.away)}</b>${zones("away") || `<p class="rail-quiet">No shots yet.</p>`}</div>
        <div>${teamMarkIn(league, d.home, 18)} <b>${esc(d.home)}</b>${zones("home") || `<p class="rail-quiet">No shots yet.</p>`}</div></div>`;
  }
  function linescoreHTML(d) {
    const ls = d.linescores || {};
    const A = ls[d.away] || [], Hh = ls[d.home] || [];
    const n = Math.max(A.length, Hh.length);
    if (!n) return "";
    const head = Array.from({ length: n }, (_, i) => `<th scope="col">${esc(periodShort(i + 1))}</th>`).join("");
    const row = (abbr, xs, total) => `<tr><th scope="row">${esc(abbr)}</th>${Array.from({ length: n }, (_, i) =>
      `<td>${xs[i] == null ? "" : esc(xs[i])}</td>`).join("")}<td class="t">${total == null ? "" : esc(total)}</td></tr>`;
    const lv = d.live || {};
    return `<table class="hc-ls"><thead><tr><th></th>${head}<th scope="col">T</th></tr></thead>
      <tbody>${row(d.away, A, lv.away_score)}${row(d.home, Hh, lv.home_score)}</tbody></table>`;
  }
  function flowTabHTML(d, league, k) {
    const L = k.leads, dr = k.droughts;
    const line = (ic, text) => `<div class="hc-fact">${icon(ic, 14)}<span>${text}</span></div>`;
    const facts = [
      line("rising", `<b>${L.changes}</b> lead change${L.changes === 1 ? "" : "s"}, <b>${L.ties}</b> tie${L.ties === 1 ? "" : "s"}`),
      L.big.away ? line("bolt", `${esc(d.away)}'s largest lead: <b>${L.big.away}</b>`) : "",
      L.big.home ? line("bolt", `${esc(d.home)}'s largest lead: <b>${L.big.home}</b>`) : "",
      L.best ? line("hot", `Longest run: <b>${esc(d[L.best.side])} ${L.best.pts}–0</b>`) : "",
      L.run ? line("hot", `Right now: <b>${esc(d[L.run.side])} on a ${L.run.pts}–0 run</b>`) : "",
      ...["away", "home"].map((ha) => ((d.live || {}).state === "live" && dr[ha] >= 180
        ? line("cold", `${esc(d[ha])}: no field goal in <b>${mmss(dr[ha])}</b>`) : "")),
    ].filter(Boolean).join("");
    return `${linescoreHTML(d)}<div class="hc-facts">${facts}</div>`;
  }
  function statsCardHTML(d, league, k) {
    const tab = S.stats;
    const body = tab === "players" ? (window.QBGamecast ? window.QBGamecast.panel("box", { d, league, faces: k.faces }) : "")
      : tab === "shots" ? flatCourtHTML(d, league, k)
      : tab === "flow" ? flowTabHTML(d, league, k)
      : teamStatsHTML(d, league, k);
    const tabs = [["team", "Team Stats"], ["players", "Player Stats"], ["shots", "Shot Chart"], ["flow", "Game Flow"]]
      .map(([key, label]) => `<button type="button" class="hc-tab${tab === key ? " on" : ""}" data-hc-stats="${key}">${label}</button>`).join("");
    return `<div class="card hc-card hc-stats" style="--ca:${k.colors.away};--ch:${k.colors.home}">
      <div class="hc-tabs" role="tablist">${tabs}</div><div class="hc-card-body">${body}</div></div>`;
  }

  /* ---------------- the odds ---------------- */
  const signed = (n) => (n > 0 ? `+${n}` : typeof trueMinus === "function" ? trueMinus(String(n)) : String(n));
  const price = (v) => (v == null || v === "" || !Number(v) ? "" : (typeof oddsTxt === "function" ? oddsTxt(v) : String(v)));
  function gameOddsHTML(d, league, k) {
    const g = k.boardGame || {};
    const sp = num(g.spread), tot = num(g.total);
    const rows = [];
    if (sp != null) rows.push(["Spread", `${esc(d.away)} ${esc(signed(-sp))}`, `${esc(d.home)} ${esc(signed(sp))}`]);
    if (num(g.away_ml) || num(g.home_ml)) rows.push(["Moneyline", `${esc(d.away)} ${esc(price(g.away_ml) || "—")}`, `${esc(d.home)} ${esc(price(g.home_ml) || "—")}`]);
    if (tot != null) rows.push(["Total", `Over ${esc(tot)}`, `Under ${esc(tot)}`]);
    const lines = rows.length ? `<div class="hc-lines">${rows.map(([k2, a, h]) =>
      `<div class="hc-line-row"><span class="hc-line-k">${k2}</span><span class="hc-line-v">${a}</span><span class="hc-line-v">${h}</span></div>`).join("")}</div>
      <p class="mini hc-note">The board's best price across the books, from its last pull before the tip.</p>`
      : `<p class="rail-quiet">${k.boardGame ? "No game lines on the board for this game." : `Open the ${esc(LEAGUE_LABEL[league] || league.toUpperCase())} board for its lines on this game.`}</p>`;
    const wp = (d.live || {}).win_prob;
    let win = "";
    if (wp && wp.home_win_prob != null) {
      const h = Number(wp.home_win_prob), a = wp.away_win_prob != null ? Number(wp.away_win_prob) : 1 - h;
      win = `<div class="hc-win"><span class="hc-line-k">Win chance (our model)</span>
        <div class="hc-winbar"><i class="away" style="width:${Math.round(a * 100)}%"></i><i class="home" style="width:${Math.round(h * 100)}%"></i></div>
        <div class="hc-win-v"><span>${esc(d.away)} <b>${Math.round(a * 100)}%</b></span><span><b>${Math.round(h * 100)}%</b> ${esc(d.home)}</span></div></div>`;
    }
    const track = k.boardGame && k.boardGame.line_track && typeof lineTrackHTML === "function" ? lineTrackHTML(k.boardGame) : "";
    return `${lines}${win}${track}`;
  }
  function trendsHTML(d, league, k) {
    const out = [];
    const lv = d.live || {}, plays = d.plays || [];
    const last = plays[plays.length - 1];
    const t = last ? elapsed(league, last) : 0, reg = 4 * (QUARTER_S[league] || 720);
    const h = num(lv.home_score), a = num(lv.away_score);
    const tot = num((k.boardGame || {}).total);
    if (lv.state === "live" && t >= 240 && t < reg && h != null && a != null) {
      const proj = Math.round(((h + a) * reg) / t);
      out.push(["gauge", `On pace for <b>${proj}</b> points${tot != null ? ` — the board's total is ${esc(tot)} (${proj > tot ? "over" : proj < tot ? "under" : "on"} it)` : ""}.`]);
    }
    const T = teamTotals(d);
    const pct = (s) => { const m = /^(\d+)-(\d+)$/.exec(String(s || "")); return m && Number(m[2]) ? Math.round((100 * Number(m[1])) / Number(m[2])) : null; };
    const fa = pct(T.away["Field goals"]), fh = pct(T.home["Field goals"]);
    if (fa != null && fh != null) out.push(["target", `Shooting: ${esc(d.away)} <b>${fa}%</b>, ${esc(d.home)} <b>${fh}%</b> from the floor.`]);
    const ta = pct(T.away["3-pointers"]), th = pct(T.home["3-pointers"]);
    if (ta != null && th != null) out.push(["target", `From three: ${esc(d.away)} <b>${ta}%</b>, ${esc(d.home)} <b>${th}%</b>.`]);
    if (k.leads.run) out.push(["hot", `${esc(d[k.leads.run.side])} on a <b>${k.leads.run.pts}–0</b> run.`]);
    ["away", "home"].forEach((ha) => { if (lv.state === "live" && k.droughts[ha] >= 180) out.push(["cold", `${esc(d[ha])}: no field goal in <b>${mmss(k.droughts[ha])}</b>.`]); });
    if (k.leads.changes || k.leads.ties) out.push(["rising", `<b>${k.leads.changes}</b> lead changes and <b>${k.leads.ties}</b> ties so far.`]);
    return out.length ? `<div class="hc-facts">${out.map(([ic, text]) => `<div class="hc-fact">${icon(ic, 14)}<span>${text}</span></div>`).join("")}</div>`
      : `<p class="rail-quiet">The trends read themselves from the plays once the game is a few minutes old.</p>`;
  }
  function oddsCardHTML(d, league, k) {
    const tab = S.odds;
    const body = tab === "props" ? (typeof pbpPropsHTML === "function" ? pbpPropsHTML(d, league) : "")
      : tab === "trends" ? trendsHTML(d, league, k) : gameOddsHTML(d, league, k);
    const tabs = [["odds", "Game Odds"], ["props", "Live Props"], ["trends", "Trends"]]
      .map(([key, label]) => `<button type="button" class="hc-tab${tab === key ? " on" : ""}" data-hc-odds="${key}">${label}</button>`).join("");
    const door = k.boardGame && typeof gameId === "function"
      ? `<button type="button" class="btn ghost hc-door" id="pbp-game-door" data-gid="${escapeAttr(gameId(k.boardGame))}">Full game page — lines, props, long shots →</button>` : "";
    return `<div class="card hc-card hc-odds" style="--ca:${k.colors.away};--ch:${k.colors.home}">
      <div class="hc-tabs" role="tablist">${tabs}</div><div class="hc-card-body">${body}</div>${door}</div>`;
  }

  /* ---------------- the page ---------------- */
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
  function pageHTML(d, league, ctx) {
    const k = facts(d, league, ctx);
    return `<div class="hc" data-league="${escapeAttr(league)}">
      ${scoreboardHTML(d, league, k)}<div class="gch-entry-slot"></div>${stageHTML(d, league, k)}${(ctx && ctx.callit) || ""}
      <div class="hc-row">${playsCardHTML(d, league, k)}${statsCardHTML(d, league, k)}${oddsCardHTML(d, league, k)}</div></div>`;
  }
  function wire(host) {
    if (host.dataset.hcWired) return;
    host.dataset.hcWired = "1";
    host.addEventListener("click", (e) => {
      const t = e.target.closest("[data-hc-view],[data-hc-stats],[data-hc-odds],[data-hc-shots],[data-hc-full],[data-hc-replay]");
      if (!t || !host.contains(t)) return;
      if (t.hasAttribute("data-hc-full")) {
        const st = host.querySelector(".hc-stage");
        if (st && st.requestFullscreen) st.requestFullscreen().catch(() => {});
        return;
      }
      if (t.hasAttribute("data-hc-replay")) S.replay = true;
      if (t.dataset.hcView) S.view = t.dataset.hcView;
      if (t.dataset.hcStats) S.stats = t.dataset.hcStats;
      if (t.dataset.hcOdds) S.odds = t.dataset.hcOdds;
      if (t.dataset.hcShots) S.shots = t.dataset.hcShots;
      if (S.ctx) render(host, S.ctx, true);
    });
    host.addEventListener("change", (e) => {
      const t = e.target.closest("[data-hc-q]");
      if (!t) return;
      S.q = t.value === "" ? null : Number(t.value);
      if (S.ctx) render(host, S.ctx, true);
    });
  }
  /* The whole page into `host`: the strip of the night's games and the
     way back are app.js's, wired by its own `wire`. The redraw that follows
     every refresh keeps the arena's picture as it was (a new one paints
     black until it decodes, a blink every few seconds) and, unless the
     reader just chose something (`chose`), where the plays and the pane
     were scrolled to. */
  function render(host, ctx, chose) {
    if (!host || !ctx || !ctx.d) return false;
    if (!S.ctx || !S.ctx.d || S.ctx.d.event_id !== ctx.d.event_id) { S.run = null; S.q = null; }
    const same = !!(S.ctx && S.ctx.d && S.ctx.d.event_id === ctx.d.event_id);
    S.ctx = ctx;
    const pic = same ? host.querySelector(".hc-frame > picture") : null;
    const scrolled = same && !chose ? [".hc-play-list", ".hc-pane"].map((sel) => [sel, (host.querySelector(sel) || {}).scrollTop || 0]) : [];
    host.innerHTML = `${ctx.stripHTML || ""}${pageHTML(ctx.d, ctx.league, ctx)}${ctx.back || ""}`;
    const fresh = pic ? host.querySelector(".hc-frame > picture") : null;
    if (fresh) fresh.replaceWith(pic);
    scrolled.forEach(([sel, top]) => { const el = host.querySelector(sel); if (el && top) el.scrollTop = top; });
    wire(host);
    if (typeof ctx.wire === "function") ctx.wire();
    return true;
  }

  window.QBHoops = {
    render, HOOPS,
    // The readers, for the tests and for Ask.
    ballAfter, flow, leads, droughts, onFloor, shotsOf, zoneOf, courtSpot, artSpot, toArt, homography,
    elapsed, clockSecs, colours, teamTotals, playWords, playKind,
  };
})();
