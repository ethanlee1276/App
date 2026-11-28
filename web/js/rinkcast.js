/* Qellys Book — hockey's parts of the live game page (js/rinkcast.js).
   ==========================================================================
   Ethan, 2026-10-15, with two renders — the arena (ours, the crown at centre
   ice) and the page: "figure out what data we can use for the live play by
   play screen for nhl like live posetions and puck tracking". The old page
   drew a small vector rink in the corner of an empty card.

   ONE PAGE FOR EVERY SPORT (2026-11-21; Ethan: "all sports in all aspects
   should be trying to match nfl and that should be automatic when we do any
   visual changes"). This file drew a whole page of its own until then: its
   own scoreboard, a play list down the right, and its own stats, lineup and
   odds cards. The page is detail.js's now (gpPageHTML), the same one football
   draws, and this file hands it hockey's parts (`parts`): the arena with its
   five views (Live, Shots, Ice, Players, Flow) for the place football's
   field has; the newest event, said in a sentence, for the last-play card;
   the league's own events as the rows of the period cards; the power play
   and shots on goal under the score; which side has the puck; the team
   stats and both sides' box scores in the page's own cards; and the shot
   chart and the trends for the Stats tab. It writes none of the page's own
   markup: the cards are made by the page's builders (gpStageHTML,
   gpCardHTML, gpTsCardHTML, gpBoxCardHTML, QBGamecast.playNow), so a change
   to the page's look is a change here too.

   THE DATA is the league's own play-by-play (`d.rink`, written by
   livescore_build.nhl_rink_pass through engine/sources/nhlrink): every
   event placed on the ice in feet from centre — faceoffs, hits, takeaways,
   giveaways, shots, blocks, goals, penalties — who was in it, and how many
   skaters each side had. Every row is already turned so the HOME team
   attacks the right-hand net and the away team the left.

   WHAT IS TRACKED, AND HOW FAR IT CAN BE TRUSTED. Nobody publishes the
   puck's position between events, live. The Live view draws the events
   where they happened, in order — the play's path — with the newest
   brightest. Whose puck it is is said only after an event that settles it
   (a faceoff won, a takeaway, a giveaway); a shot, a hit or a block leaves
   it loose and the page says nothing. The power play is the feed's own
   when it carries one; otherwise the penalty clock is worked out from the
   penalties on the sheet, and the page shows "PP" with no time when it
   cannot. Who is on the ice is not in the feed, so the lineups are every
   skater's game so far. Expected goals are our model's, labelled so.

   THE RINK ON THE PICTURE. The art is a panorama, not a plan: its end
   zones are drawn short and its near boards bow. A smooth map
   (thin-plate spline) runs through twenty-five points read off the render
   at full size — the eight faceoff dots, both nets, centre ice, the blue
   lines and the red line at five depths, the boards — so an event at a
   dot lands on the art's dot and a shot from the slot lands in the art's
   slot.

   Loaded by detail.js (gpSportMod) the first time a hockey game with the
   league's events opens (a game without them is drawn from the game file
   alone, gpPlainKit); uses app.js's helpers by name. No inline handlers. */
(function () {
  "use strict";
  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const still = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const words = (code) => String(code || "").replace(/-/g, " ");
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

  /* What the reader chose on the arena, kept across the page's redraws, and
     the game it was chosen on (`game`: another game starts its run again). */
  const S = { view: "live", shots: "both", ice: "all", run: null, replay: false, flowBy: "att", game: "" };

  /* ---------------- the clock ---------------- */
  const PERIOD_S = 1200;
  function secs(c) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(c == null ? "" : c).trim());
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  }
  const mmss = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.round(Math.max(0, s) % 60)).padStart(2, "0")}`;
  const periodWord = (p) => (!p ? "" : p <= 3 ? ["1st", "2nd", "3rd"][p - 1] : p === 4 ? "OT" : `${p - 3}OT`);
  const periodShort = (p) => (!p ? "" : p <= 3 ? `P${p}` : p === 4 ? "OT" : `${p - 3}OT`);
  /* Seconds since the opening faceoff, now: the league's clock when the
     file carries it, else the scoreboard's, else the newest event's. */
  function nowElapsed(d) {
    const ev = events(d), r = d.rink || {}, c = r.clock || {};
    const lastT = ev.length ? Number(ev[ev.length - 1].elapsed) || 0 : 0;
    let per = Number(c.period) || 0, left = secs(c.left);
    if (!per) {
      const m = /^P?(\d)/i.exec(String((d.live || {}).period || ""));
      per = m ? Number(m[1]) : /OT/i.test(String((d.live || {}).period || "")) ? 4 : 0;
      left = secs((d.live || {}).clock);
    }
    if (!per || left == null) return lastT;
    // Regular-season overtime is five minutes; a playoff's (game type 3)
    // is a full twenty.
    const len = per >= 4 && Number(r.game_type || 2) !== 3 ? 300 : PERIOD_S;
    return Math.max(lastT, (per - 1) * PERIOD_S + clamp(len - left, 0, len));
  }

  /* ---------------- reading the events ---------------- */
  const events = (d) => ((d.rink || {}).events || []).filter((e) => e && typeof e === "object");
  const sideOf = (d, team) => (team && team === d.home ? "home" : team && team === d.away ? "away" : "");
  const other = (side) => (side === "home" ? "away" : side === "away" ? "home" : "");
  /* Skaters a side, the side on the power play and the side with its net
     empty, from the four-digit code (away goalie, away skaters, home
     skaters, home goalie) — engine/sources/nhlrink.situation. */
  function sitOf(code) {
    const c = String(code || "");
    if (!/^\d{4}$/.test(c)) return null;
    const [ag, ask, hsk, hg] = c.split("").map(Number);
    if (ask < 3 || ask > 6 || hsk < 3 || hsk > 6 || ag > 1 || hg > 1) return null;
    const a = ask - (ag === 0 ? 1 : 0), h = hsk - (hg === 0 ? 1 : 0);
    return { away: ask, home: hsk, pp: h > a ? "home" : a > h ? "away" : "", en: ag === 0 ? "away" : hg === 0 ? "home" : "" };
  }
  const ATTEMPTS = new Set(["sog", "miss", "goal", "block"]);
  /* Whose puck it is after the newest event — "home", "away", or "" when
     the event leaves it loose (a shot, a hit, a block) or dead. */
  function puckAfter(d) {
    const ev = events(d);
    const e = ev[ev.length - 1];
    if (!e) return "";
    const own = sideOf(d, e.team);
    if (e.kind === "faceoff" || e.kind === "takeaway") return own;
    if (e.kind === "giveaway") return other(own);
    return "";
  }
  /* Whose end a spot is in: the right-hand end is the away team's (the
     home team attacks it). */
  function endOf(d, e) {
    if (!e || e.x == null) return "";
    return e.x > 25 ? "away" : e.x < -25 ? "home" : "neutral";
  }
  /* The power play now: the side, and the seconds left when they can be
     told — the feed's own block first, else the penalties on the sheet. */
  function powerPlay(d) {
    const ev = events(d), r = d.rink || {}, now = nowElapsed(d);
    const lastSit = ev.length ? sitOf(ev[ev.length - 1].sc) : null;
    const feed = r.situation || {};
    if (feed.pp) {
      const side = sideOf(d, feed.pp);
      return side ? { side, left: secs(feed.left) } : null;
    }
    if (!lastSit || !lastSit.pp) return null;
    const side = lastSit.pp, them = other(side);
    let soonest = null;
    ev.forEach((e, i) => {
      if (e.kind !== "penalty" || sideOf(d, e.team) !== them || !e.minutes || e.minutes > 5) return;
      const start = Number(e.elapsed) || 0, end = start + e.minutes * 60;
      if (start > now || end <= now) return;
      // A minor ends at the first goal the other side scores on it.
      const cut = e.minutes === 2 && ev.slice(i + 1).some((g) => g.kind === "goal" && sideOf(d, g.team) === side && (Number(g.elapsed) || 0) >= start);
      if (!cut && (soonest == null || end < soonest)) soonest = end;
    });
    return { side, left: soonest == null ? null : soonest - now };
  }
  /* Each side's game so far, off the events alone. */
  function teamStats(d) {
    const z = () => ({ goals: 0, sog: 0, att: 0, hits: 0, blocks: 0, take: 0, give: 0, fow: 0, fo: 0, pim: 0, ppo: 0, ppg: 0, xg: 0, xgn: 0 });
    const t = { away: z(), home: z() };
    events(d).forEach((e) => {
      const s = sideOf(d, e.team);
      if (!s) return;
      if (ATTEMPTS.has(e.kind)) t[s].att++;
      if (e.kind === "sog" || e.kind === "goal") t[s].sog++;
      if (e.kind === "goal") {
        t[s].goals++;
        const sit = sitOf(e.sc);
        if (sit && sit.pp === s) t[s].ppg++;
      }
      if (e.kind === "hit") t[s].hits++;
      if (e.kind === "block") { const b = sideOf(d, e.team2) || other(s); if (b) t[b].blocks++; }
      if (e.kind === "takeaway") t[s].take++;
      if (e.kind === "giveaway") t[s].give++;
      if (e.kind === "faceoff") { t[s].fow++; t.away.fo++; t.home.fo++; }
      if (e.kind === "penalty") { t[s].pim += Number(e.minutes) || 0; if (e.minutes && e.minutes <= 5) t[other(s)].ppo++; }
      if (e.xg != null) { t[s].xg += Number(e.xg) || 0; t[s].xgn++; }
    });
    return t;
  }
  /* The running count of attempts a side, and the goals, over the game;
     beside them the running expected goals (`xa`, `xh`) — the xG RACE
     (Ethan, 2026-10-15) — and the game's biggest single chance. */
  function flow(d) {
    const pts = [{ t: 0, a: 0, h: 0, xa: 0, xh: 0 }], goals = [];
    let a = 0, h = 0, xa = 0, xh = 0, best = null;
    events(d).forEach((e) => {
      const s = sideOf(d, e.team);
      if (!s || !ATTEMPTS.has(e.kind)) return;
      const x = e.xg != null ? Number(e.xg) || 0 : 0;
      if (s === "away") { a++; xa += x; } else { h++; xh += x; }
      pts.push({ t: Number(e.elapsed) || 0, a, h, xa, xh });
      if (x && (!best || x > best.xg)) best = { xg: x, e, side: s };
      if (e.kind === "goal") goals.push({ t: Number(e.elapsed) || 0, side: s, n: s === "away" ? a : h });
    });
    return { pts, goals, best };
  }
  /* Attempts a side over the last `win` seconds — who is pressing. */
  function pressure(d, win) {
    const now = nowElapsed(d), w = win || 300;
    const out = { away: 0, home: 0 };
    events(d).forEach((e) => {
      const s = sideOf(d, e.team);
      if (s && ATTEMPTS.has(e.kind) && now - (Number(e.elapsed) || 0) <= w) out[s]++;
    });
    return out;
  }
  /* Seconds since each side's last shot on goal. */
  function quiet(d) {
    const now = nowElapsed(d), last = { away: 0, home: 0 };
    events(d).forEach((e) => {
      const s = sideOf(d, e.team);
      if (s && (e.kind === "sog" || e.kind === "goal")) last[s] = Number(e.elapsed) || 0;
    });
    return { away: now - last.away, home: now - last.home };
  }

  /* ---------------- the rink on the picture ---------------- */
  const ART = { w: 1672, h: 941 };
  //: Rink feet (x along the ice, home attacking +x; y across, +y the far
  //: boards) → pixels on the 1672 × 941 render, read off the art.
  const CP = [[[-69, 22], [504.1, 634.8]], [[69, 22], [1166.1, 635.4]], [[-20, 22], [714.1, 634.1]], [[20, 22], [957.2, 634.2]],
              [[-69, -22], [345.0, 766.0]], [[69, -22], [1325.0, 765.5]], [[-20, -22], [642.9, 778.3]], [[20, -22], [1028.0, 779.0]],
              [[-89, 0], [294.2, 681.7]], [[89, 0], [1391.0, 681.7]], [[0, 0], [836.0, 700.0]],
              [[0, 42.5], [836.0, 597.0]], [[0, -42.5], [836.0, 854.0]], [[-100, 0], [169.0, 677.0]], [[100, 0], [1503.0, 677.0]]];
  // The blue lines at five depths: x = 688.5 − 0.6129 (y − 620) on the
  // left, mirrored about centre ice (x = 836) on the right.
  [[597, 42.5], [634.4, 22], [698, 0], [777.5, -22], [837.4, -42.5]].forEach(([y, v]) => {
    const x = 688.5 - 0.6129 * (y - 620);
    CP.push([[-25, v], [x, y]], [[25, v], [ART.w - x, y]]);
  });
  function solve(A, b) {
    const n = b.length, M = A.map((row, i) => row.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = 0; r < n; r++) {
        if (r === c || !M[c][c]) continue;
        const f = M[r][c] / M[c][c];
        for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    return M.map((row, i) => row[n] / row[i]);
  }
  const phi = (r) => (r > 0 ? r * r * Math.log(r) : 0);
  function spline(cp) {
    const n = cp.length, A = [];
    for (let i = 0; i < n + 3; i++) A.push(new Array(n + 3).fill(0));
    cp.forEach(([[ui, vi]], i) => {
      cp.forEach(([[uj, vj]], j) => { A[i][j] = phi(Math.hypot(ui - uj, vi - vj)); });
      A[i][n] = 1; A[i][n + 1] = ui; A[i][n + 2] = vi;
      A[n][i] = 1; A[n + 1][i] = ui; A[n + 2][i] = vi;
    });
    return { x: solve(A.map((r) => r.slice()), cp.map(([, q]) => q[0]).concat([0, 0, 0])),
             y: solve(A.map((r) => r.slice()), cp.map(([, q]) => q[1]).concat([0, 0, 0])) };
  }
  const W = spline(CP);
  function toArt(u, v) {
    u = clamp(Number(u) || 0, -99, 99);
    v = clamp(Number(v) || 0, -42, 42);
    const n = CP.length;
    let x = W.x[n] + W.x[n + 1] * u + W.x[n + 2] * v, y = W.y[n] + W.y[n + 1] * u + W.y[n + 2] * v;
    for (let i = 0; i < n; i++) {
      const k = phi(Math.hypot(u - CP[i][0][0], v - CP[i][0][1]));
      x += W.x[i] * k;
      y += W.y[i] * k;
    }
    return [x, y];
  }
  //: The net each side shoots at.
  const NET = { home: [89, 0], away: [-89, 0] };

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
  /* Each side's colour, as Ethan's render draws them: the Rangers in their
     blue and the Bruins in their gold. A club's first colour when it reads
     on the dark panels; a first colour a little too dark to read (the
     Rangers' and the Blues' royal blue, Colorado's burgundy, the Wild's
     green) lifted until it does, same hue; one far too dark (a navy) or
     no colour at all (black) gives way to the club's next colour that
     reads — Edmonton's orange, Washington's red, Pittsburgh's gold — and a
     club with only white or silver behind a navy (Toronto, Tampa Bay)
     lifts its navy. The away side takes another of its colours when the
     two would look alike. On the white ice every mark carries a dark edge,
     so a light colour reads there too. (The basketball page keeps its
     simpler rule, js/hoopscast.js: its render drew the Lakers in gold.) */
  const READS_ON_DARK = 0.065, LIFT_FROM = 0.03, LIFT_TO = 0.1, HUED = 0.04;
  const toLin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const toByte = (v) => Math.round(clamp(v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055, 0, 1) * 255);
  function oklab(c) {
    const [r, g, b] = c.map(toLin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
  }
  function fromOklab([L, a, b]) {
    const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
    const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
    const s = Math.pow(L - 0.0894841775 * a - 1.291485548 * b, 3);
    return [toByte(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s), toByte(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            toByte(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)];
  }
  const hex = (c) => "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  const hued = (c) => { const [, a, b] = oklab(c); return Math.hypot(a, b) >= HUED; };
  /* The same hue, lighter, until it reads. */
  function lift(c) {
    const [L, a, b] = oklab(c);
    for (let l = L; l <= 0.96; l += 0.02) { const out = fromOklab([l, a, b]); if (luminance(out) >= LIFT_TO) return hex(out); }
    return hex(c);
  }
  /* A club's colours in the order the page would use them. */
  function clubColours(t) {
    const cs = [t.primary, t.secondary, t.tertiary].map(rgb).filter(Boolean);
    if (!cs.length) return [];
    const [first, ...rest] = cs;
    const reads = (c) => luminance(c) >= READS_ON_DARK;
    const out = [];
    if (reads(first)) out.push(hex(first));
    else if (hued(first) && luminance(first) >= LIFT_FROM) out.push(lift(first));
    rest.filter((c) => hued(c) && reads(c)).forEach((c) => out.push(hex(c)));
    if (!reads(first) && hued(first) && luminance(first) < LIFT_FROM) out.push(lift(first));
    rest.filter((c) => !hued(c) && reads(c)).forEach((c) => out.push(hex(c)));
    return out.filter((c, i) => out.indexOf(c) === i);
  }
  function colours(d) {
    const table = typeof teamsIn === "function" ? (teamsIn("nhl") || {}) : {};
    const apart = (a, b) => { const x = rgb(a), y = rgb(b); return !x || !y || Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) >= 90; };
    const homes = clubColours(table[d.home] || {}), aways = clubColours(table[d.away] || {});
    const home = homes[0] || "var(--text-mute)";
    const away = aways.find((c) => apart(c, home)) || aways[0] || "var(--brand)";
    return { home, away };
  }

  /* ---------------- men ---------------- */
  /* {name: player} off the league's roster, for numbers and faces. */
  function menOf(d) {
    const out = {};
    Object.values((d.rink || {}).players || {}).forEach((p) => { if (p && p.name) out[p.name] = p; });
    return out;
  }
  const tag = (name, k) => { if (!name) return ""; const p = k.men[name]; return p && p.num != null ? `#${p.num} ${name}` : name; };
  function faceHTML(name, k, size) {
    const p = k.men[name] || {};
    const src = String(p.face || "");
    if (!/^https:\/\//.test(src)) return `<span class="rc-face">${icon("people", 14)}</span>`;
    // A face that will not load waits out of sight with the mark under it,
    // and comes back (visuals.js FACES COME BACK).
    const attrs = typeof faceImg === "function" ? faceImg(src, src).attrs
      : `src="${escapeAttr(src)}" loading="lazy" decoding="async"`;
    return `<span class="rc-face">${icon("people", 14)}<img ${attrs} alt="" width="${size}" height="${size}" data-onerr="remove"></span>`;
  }

  /* ---------------- glyphs ---------------- */
  const svg = (d, size) => `<svg class="ic" viewBox="0 0 16 16" width="${size || 14}" height="${size || 14}" fill="none" stroke="currentColor"
    stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${d}</svg>`;
  const GLYPH = {
    goal: '<path d="M2 13V5h12v8"/><path d="M2 5l3-2h6l3 2"/><path d="M5 13V8h6v5"/>',
    sog: '<circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="1.8"/>',
    miss: '<circle cx="8" cy="8" r="5.5"/><path d="M4.5 4.5l7 7"/>',
    block: '<path d="M8 2l5 2v4c0 3-2.2 5-5 6-2.8-1-5-3-5-6V4z"/>',
    hit: '<path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3M3.4 3.4l2.1 2.1M10.5 10.5l2.1 2.1M3.4 12.6l2.1-2.1M10.5 5.5l2.1-2.1"/>',
    faceoff: '<path d="M3 3l7 9h3M13 3l-7 9H3"/>',
    takeaway: '<path d="M8 13V3M4 7l4-4 4 4"/>',
    giveaway: '<path d="M8 3v10M4 9l4 4 4-4"/>',
    penalty: '<rect x="3" y="2" width="10" height="12" rx="2"/><path d="M6 6h4M6 9h4"/>',
    stoppage: '<path d="M6 4v8M10 4v8"/>',
    delayed: '<path d="M8 2v6l3 2"/><circle cx="8" cy="8" r="6"/>',
    start: '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
    end: '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
    other: '<circle cx="8" cy="8" r="1.5"/>',
    replay: '<path d="M3.2 8a4.8 4.8 0 1 0 1.4-3.4"/><path d="M3 2.6v3h3"/>',
  };
  const EXPAND = svg('<path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/>', 14);

  /* ---------------- the words of a play ---------------- */
  const STOP = { icing: "Icing", offside: "Offside", "puck-in-netting": "Puck in the netting", "puck-frozen": "Puck frozen",
                 "goalie-stopped-after-sog": "Goalie freezes it", "tv-timeout": "Media timeout", "home-timeout": "Timeout",
                 "visitor-timeout": "Timeout", "puck-in-benches": "Puck in the bench", "high-stick": "High stick",
                 "hand-pass": "Hand pass", "net-dislodged-defensive-skater": "Net off its moorings", "puck-in-crowd": "Puck in the crowd" };
  const clockOf = (e) => String((e && e.clock) || "").replace(/^0(\d:)/, "$1");
  /* {title, sub} — the play in the feed's own codes and names, never a
     sentence of anybody's. The title is the play's name on its card. */
  function playWords(e, d, k) {
    const sit = sitOf(e.sc), own = sideOf(d, e.team);
    const strength = (s) => (!sit ? "" : sit.en && sit.en !== s ? " (EN)" : sit.pp === s ? " (PP)" : sit.pp && sit.pp !== s ? " (SH)" : "");
    const who = tag(e.player, k), who2 = tag(e.player2, k), shot = e.shot ? words(e.shot) : "";
    switch (e.kind) {
      case "goal": return { title: "Goal", sub: [`${who}${strength(own)}`, shot, (e.assists || []).length ? `assist ${(e.assists || []).map((n) => tag(n, k)).join(", ")}` : "unassisted"].filter(Boolean).join(" · ") };
      case "sog": return { title: "Shot on goal", sub: [who, shot, who2 ? `saved by ${who2}` : ""].filter(Boolean).join(" · ") };
      case "miss": return { title: "Missed shot", sub: [who, shot, words(e.reason)].filter(Boolean).join(" · ") };
      case "block": return { title: "Blocked shot", sub: [who ? `shot by ${who}` : "", who2 ? `blocked by ${who2}` : ""].filter(Boolean).join(" · ") };
      case "hit": return { title: "Hit", sub: who2 ? `${who} on ${who2}` : who };
      case "faceoff": return { title: "Faceoff", sub: [`Won by ${who || esc(e.team)}`, who2 ? `over ${who2}` : ""].filter(Boolean).join(" ") };
      case "takeaway": return { title: "Takeaway", sub: who };
      case "giveaway": return { title: "Giveaway", sub: who };
      case "penalty": return { title: "Penalty", sub: [cap(words(e.penalty)) || "Penalty", e.minutes ? `${e.minutes} min` : "", who, who2 ? `drawn by ${who2}` : ""].filter(Boolean).join(" · ") };
      case "stoppage": return { title: STOP[e.reason] || cap(words(e.reason)) || "Stoppage", sub: "" };
      case "delayed": return { title: "Delayed penalty", sub: e.team ? `on ${esc(e.team)}` : "" };
      case "start": return { title: `Start of the ${periodWord(e.period)}`, sub: "" };
      case "end": return { title: `End of the ${periodWord(e.period)}`, sub: "" };
      default: return { title: "Play", sub: who };
    }
  }
  /* WHO DID WHAT, IN OUR OWN WORDS (2026-11-21, when the page became every
     sport's; football's is app.js footballLine). A row read as a title and
     its facts ("Blocked shot · shot by #28 Zach Whitecloud · blocked by #12
     Matt Boldy"); it reads as a line now ("Zach Whitecloud's shot is blocked
     by Matt Boldy"), from the same codes: the event's kind, who was in it,
     the shot's type, the strength the situation code gives. Returned as the
     line's pieces, a string or a name ({b}), so a row sets the names in bold
     (`sayPlay`) and a card says them plain; null for a moment in the game
     (a period's start or end, a whistle), which `momentOf` names. */
  function said(e, d) {
    const own = sideOf(d, e.team), sit = sitOf(e.sc);
    const strength = !sit ? "" : sit.en && sit.en !== own ? " into the empty net" : sit.pp === own ? " on the power play"
      : sit.pp && sit.pp !== own ? " shorthanded" : "";
    const A = e.player ? { b: e.player } : (e.team || ""), B = e.player2 ? { b: e.player2 } : null;
    const kind = (...xs) => { const w = xs.map(words).filter(Boolean).join(", "); return w ? ` (${w})` : ""; };
    switch (e.kind) {
      case "goal": {
        const from = (e.assists || []).filter(Boolean).flatMap((n, i) => (i ? [" and ", { b: n }] : [{ b: n }]));
        return [A, ` scores${strength}${kind(e.shot)}`, ...(from.length ? [", from ", ...from] : [", unassisted"])];
      }
      case "sog": return [A, ` shoots${kind(e.shot)}`, ...(B ? [", saved by ", B] : [])];
      case "miss": return [A, ` misses${kind(e.shot, e.reason)}`];
      case "block": return [A, "’s shot is blocked", ...(B ? [" by ", B] : [])];
      case "hit": return B ? [A, " hits ", B] : [A, " with a hit"];
      case "faceoff": return [A, " wins the faceoff", ...(B ? [" over ", B] : [])];
      case "takeaway": return ["Takeaway by ", A];
      case "giveaway": return ["Giveaway by ", A];
      case "penalty": return [`${cap(words(e.penalty)) || "Penalty"}${e.minutes ? `, ${e.minutes} min` : ""}`,
                              ...(A ? [" on ", A] : []), ...(B ? [", drawn by ", B] : [])];
      default: return null;
    }
  }
  function momentOf(e, d) {
    const per = () => { const n = typeof gpPeriodName === "function" ? gpPeriodName("nhl", e.period, d) : `${periodWord(e.period)} period`;
      return /^\d/.test(n) ? `the ${n}` : n.toLowerCase(); };
    switch (e.kind) {
      case "start": return `Start of ${per()}`;
      case "end": return `End of ${per()}`;
      case "stoppage": return STOP[e.reason] || cap(words(e.reason)) || "Stoppage";
      case "delayed": return `Delayed penalty${e.team ? ` on ${e.team}` : ""}`;
      default: return "";
    }
  }
  /* An event as a row of the page's play list (detail.js gpPeriodsHTML → app.js
     playsHTML): its period and clock, its side, a goal with the score it
     left, and the event itself for its words (`sayPlay`). */
  const rowOf = (e) => ({ kind: "hockey", id: e.id, period: e.period, clock: clockOf(e), team: e.team || "", player: e.player || "",
    event: e.kind || "play", scoring: e.kind === "goal", shot: false,
    away_score: e.kind === "goal" && e.score ? e.score[0] : null, home_score: e.kind === "goal" && e.score ? e.score[1] : null, rink: e });
  function sayPlay(e, d) {
    const m = momentOf(e, d);
    if (m) return { moment: m };
    const bits = said(e, d);
    return bits ? { html: bits.map((x) => (x && x.b ? `<b>${esc(x.b)}</b>` : esc(x))).join("") } : null;
  }
  /* THE LIVE TAB'S CARD, IN THE SAME WORDS (2026-11-24; Ethan: "We want all
     the live pages to match each other"). A hockey card carries the league's
     newest few events (`rink_plays`, livescore_build.card_rink): its rows are
     those events as this page's rows, said as this page says them. A card
     the league's feed has not reached keeps ESPN's rows (null). */
  function cardRows(g) {
    const ev = ((g || {}).rink_plays || []).filter((e) => e && e.kind);
    return ev.length ? { rows: ev.map(rowOf), say: (p) => (p && p.rink ? sayPlay(p.rink, g) : null) } : null;
  }

  /* ---------------- on the score ----------------
     The score is the page's own (detail.js pbpBoardHTML), the same for every
     sport, and a goal flashes on it as a touchdown does (detail.js
     gpGoalSeen: it was this file's until the page became every sport's).
     Hockey's part of it, under the clock: the side on the power play with
     the time left where it can be told, and the shots on goal. */
  function midHTML(d, k) {
    const T = k.stats, pp = k.pp;
    // The chip and the note are the page's own (detail.js gpChipHTML, gpNoteHTML).
    return `${pp ? gpChipHTML(`PP ${d[pp.side]}${pp.left != null && pp.left > 0 ? ` ${mmss(pp.left)}` : ""}`, k.colors[pp.side]) : ""}${
      (T.away.sog || T.home.sog) ? gpNoteHTML(`SOG ${T.away.sog} – ${T.home.sog}`) : ""}`;
  }

  /* ---------------- the arena ---------------- */
  const PICTURE = `<picture data-gp-hold="arena">
      <source type="image/webp" srcset="img/arena/nhl-arena@640.webp 640w, img/arena/nhl-arena.webp 1280w" sizes="(max-width: 720px) 190vw, 100vw">
      <img class="rc-photo" src="img/arena/nhl-arena.jpg" srcset="img/arena/nhl-arena@640.jpg 640w, img/arena/nhl-arena.jpg 1280w"
        sizes="(max-width: 720px) 190vw, 100vw" alt="" decoding="async"></picture>`;
  const at = (e) => toArt(e.x, e.y).map((v) => v.toFixed(1));
  const colOf = (d, e, k) => (sideOf(d, e.team) === "home" ? "var(--ch)" : "var(--ca)");
  const cross = (x, y, r) => `M${(x - r).toFixed(1)} ${(y - r).toFixed(1)} l${2 * r} ${2 * r} m0 ${-2 * r} l${-2 * r} ${2 * r}`;
  /* One attempt on the ice: a goal ringed, a shot on goal filled, a miss
     hollow, a block crossed — each on a dark edge so any club's colour
     reads on white ice. */
  function shotMark(d, e, k, alpha) {
    const [x, y] = toArt(e.x, e.y), col = colOf(d, e, k), o = (alpha == null ? 0.95 : alpha).toFixed(2);
    if (e.kind === "goal") return `<g style="opacity:${o}"><circle class="rc-goal-ring" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="16"/><circle class="rc-shot made" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="10" style="fill:${col}"/></g>`;
    if (e.kind === "sog") return `<circle class="rc-shot made" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8" style="fill:${col};opacity:${o}"/>`;
    if (e.kind === "miss") return `<g style="opacity:${o}"><circle class="rc-halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7"/><circle class="rc-shot miss" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7" style="stroke:${col}"/></g>`;
    return `<g style="opacity:${o}"><path class="rc-halo" d="${cross(x, y, 7)}"/><path class="rc-shot block" d="${cross(x, y, 7)}" style="stroke:${col}"/></g>`;
  }
  /* One non-shot event: a hit a diamond, a takeaway a triangle up, a
     giveaway a triangle down, a faceoff won a square. */
  function iceMark(d, e, k, alpha) {
    const [x, y] = toArt(e.x, e.y), col = colOf(d, e, k), o = (alpha == null ? 0.95 : alpha).toFixed(2);
    const r = 8;
    const shape = e.kind === "hit" ? `M${x} ${y - r} L${x + r} ${y} L${x} ${y + r} L${x - r} ${y} Z`
      : e.kind === "takeaway" ? `M${x} ${y - r} L${x + r} ${y + r * 0.8} L${x - r} ${y + r * 0.8} Z`
      : e.kind === "giveaway" ? `M${x} ${y + r} L${x + r} ${y - r * 0.8} L${x - r} ${y - r * 0.8} Z`
      : e.kind === "faceoff" ? `M${x - r * 0.8} ${y - r * 0.8} h${r * 1.6} v${r * 1.6} h${-r * 1.6} Z`
      : e.kind === "penalty" ? `M${x - r} ${y - r * 0.6} h${r * 2} v${r * 1.2} h${-r * 2} Z` : "";
    return shape ? `<path class="rc-ice ${e.kind}" d="${shape}" style="fill:${col};opacity:${o}"/>` : "";
  }
  /* THE PUCK'S RUN. Ethan, 2026-10-15, drawing a line across the rink:
     "Are we able too do like a animation of a hockey puck moving back and
     forth across the ice when we show the switching of positions". The
     puck goes through the period's newest events in the order they
     happened: a glide between two events of one sequence, a fade where a
     whistle came between them (the puck went dead and was dropped again),
     a flight to the net on a shot, the lamp on a goal. Its glow, and the
     line it leaves, is the colour of the side moving it on that leg: the
     shooter's on the way to his shot, the giver's to a giveaway, the other
     side's to a takeaway (they had it until then), nobody's after a hit.
     No feed has the puck between events, so the run joins where things
     happened, in order; the caption says what each was.

     The first look at a game plays its newest six. A refresh that brings
     new events moves the puck on from where it stopped. Replay plays the
     six again. js/gamecast.js `track` keeps the time; a reader who asked
     for less motion gets the end of the run, still. */
  const RUN = 6;
  //: The side the puck travels with into an event, or "" when the event
  //: does not say.
  function carrier(d, e) {
    const s = sideOf(d, e.team);
    if (ATTEMPTS.has(e.kind) || e.kind === "giveaway") return s;
    if (e.kind === "takeaway") return other(s);
    return "";
  }
  //: Which run the page is in: a new one when the game, the point the
  //: puck ends on or the reader's Replay says so; otherwise the same one,
  //: further on. `keys` are the window's points; a new run starts where
  //: the last one stopped when that point is still in the window.
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
  function netPoint(d, e) {
    const net = NET[sideOf(d, e.team) || "home"];
    return toArt(net[0], net[1] + (e.kind === "miss" ? (e.y >= 0 ? 6 : -6) : 0));
  }
  const flies = (e) => ATTEMPTS.has(e.kind) && e.kind !== "block";
  //: The half of the rink the run's events all sit in ("left", "right"),
  //: or null when they cross centre ice.
  function runSpan(d) {
    const all = events(d).filter((e) => e.x != null && e.y != null);
    const last = all[all.length - 1];
    if (!last) return null;
    const win = all.filter((e) => e.period === last.period).slice(-RUN);
    if (win.every((e) => e.x < 0)) return "left";
    if (win.every((e) => e.x >= 0)) return "right";
    return null;
  }
  function liveMarks(d, k) {
    const all = events(d);
    let i = all.length - 1;
    while (i >= 0 && (all[i].x == null || all[i].y == null)) i--;
    if (i < 0) return "";
    const last = all[i];
    const idx = [];
    for (let j = i; j >= 0 && idx.length < RUN; j--) {
      if (all[j].period !== last.period) break;
      if (all[j].x != null && all[j].y != null) idx.unshift(j);
    }
    // The window's points: each event where it happened, joined to the one
    // before unless a whistle (or the drop itself) came between them; an
    // unblocked shot goes on to the net, and play goes on from there.
    const W = [];
    idx.forEach((j, n) => {
      const e = all[j], [x, y] = toArt(e.x, e.y);
      const jump = n > 0 && (e.kind === "faceoff" || all.slice(idx[n - 1] + 1, j).some((b) => WHISTLES.has(b.kind)));
      W.push({ key: String(e.id), x, y, jump, e, side: jump ? "" : carrier(d, e) });
      if (flies(e)) {
        const [nx, ny] = netPoint(d, e);
        W.push({ key: `${e.id}>net`, x: nx, y: ny, e, net: true, side: sideOf(d, e.team), leg: 0.45, hold: e === last ? 0.8 : 0.25 });
      }
    });
    const run = runFor(d, W[W.length - 1].key, W.map((p) => p.key));
    const from = run.from == null ? 0 : Math.max(0, W.findIndex((p) => p.key === run.from));
    const pts = W.slice(from).map((p, n) => (n ? p : Object.assign({}, p, { jump: false })));
    const G = window.QBGamecast;
    const T = G && G.track ? G.track(pts, { elapsed: run.elapsed }) : null;
    const moving = !!(T && !T.still);
    // When the mark at window point n arrives: before the run, already.
    const arrive = (n) => (moving && n > from ? T.at[n - from] : null);
    const leaves = (n) => (moving && n > from ? T.go[n - from] : null);
    const pop = (n, inner) => {
      const t = arrive(n);
      return t == null || T.past(t) ? inner : `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.2s" begin="${T.begin(t)}" fill="freeze"/>${inner}</g>`;
    };
    const col = (side) => (side === "home" ? "var(--ch)" : side === "away" ? "var(--ca)" : "var(--text)");
    // The line the puck leaves, leg by leg, the older fainter; drawn as
    // the puck goes when it is moving.
    const legs = W.map((p, n) => {
      if (!n || p.jump) return "";
      const q = W[n - 1], len = Math.hypot(p.x - q.x, p.y - q.y), a = (0.35 + 0.6 * n / Math.max(1, W.length - 1)).toFixed(2);
      // Drawn whole once the puck is past it; drawing itself behind the
      // puck while it is on it (from where it is now, after a redraw).
      const t0 = leaves(n), t1 = arrive(n);
      const on = t0 != null && !T.past(t1);
      const left = on ? len * Math.min(1, (t1 - Math.max(t0, T.elapsed)) / Math.max(0.01, t1 - t0)) : 0;
      const draw = on ? ` stroke-dasharray="${len.toFixed(1)}" stroke-dashoffset="${left.toFixed(1)}"` : "";
      const anim = on ? `<animate attributeName="stroke-dashoffset" from="${left.toFixed(1)}" to="0" begin="${T.begin(t0)}" dur="${Math.max(0.05, t1 - Math.max(t0, T.elapsed)).toFixed(2)}s" fill="freeze"/>` : "";
      const cls = p.net ? `rc-flight${p.e.kind === "goal" ? " goal" : ""}` : "rc-trail";
      const line = (c, style) => `<line class="${c}" x1="${q.x.toFixed(1)}" y1="${q.y.toFixed(1)}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}"${draw}${style}>${anim}</line>`;
      return `<g style="opacity:${a}">${line("rc-trail-halo", "")}${line(cls, p.net ? "" : ` style="stroke:${col(p.side)}"`)}</g>`;
    }).join("");
    // Every event's mark, the older fainter, each showing as the puck gets there.
    const marks = W.map((p, n) => {
      if (p.net || p.e === last) return "";
      const a = 0.35 + 0.5 * (n + 1) / Math.max(1, W.length - 1);
      const e = p.e;
      return pop(n, ATTEMPTS.has(e.kind) ? shotMark(d, e, k, a) : (iceMark(d, e, k, a) || `<circle class="rc-step" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="6" style="fill:${colOf(d, e, k)};opacity:${a.toFixed(2)}"/>`));
    }).join("");
    const ln = W.findIndex((p) => p.e === last && !p.net);
    const { x, y } = W[ln];
    const now = pop(ln, `<circle class="rc-halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="20"/><circle class="rc-ring" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="20"/>${
      ATTEMPTS.has(last.kind) ? shotMark(d, last, k, 1) : iceMark(d, last, k, 1)}`);
    const end = W[W.length - 1];
    const lamp = last.kind === "goal" && end.net ? pop(W.length - 1, `<circle class="rc-lamp" cx="${end.x.toFixed(1)}" cy="${end.y.toFixed(1)}" r="22"/>`) : "";
    // The puck, on top, its glow the side moving it on each leg; at rest,
    // the side the last event gave it to (none after a shot or a hit).
    const rest = (d.live || {}).state === "live" ? k.puck : "";
    const glow = (side) => {
      const on = (s) => (s === side ? "0.55" : "0");
      const anim = moving ? T.steps("opacity", pts.map((p, n) => on(n && !p.jump ? p.side : "")), on(rest)) : "";
      return `<circle class="rc-puck-glow" r="26" style="fill:${col(side)}" opacity="${on(rest)}">${anim}</circle>`;
    };
    const puck = `<g class="rc-puck-run" transform="translate(${end.x.toFixed(1)} ${end.y.toFixed(1)})">${glow("away")}${glow("home")}
      <ellipse class="rc-puck" rx="13" ry="8"/>${moving ? T.motion : ""}</g>`;
    const arrow = arrowSVG(d, k);
    return `${legs}${marks}${now}${lamp}${puck}${moving && arrow ? `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.3s" begin="${T.begin(T.dur)}" fill="freeze"/>${arrow}</g>` : arrow}`;
  }
  const WHISTLES = new Set(["stoppage", "penalty", "goal", "start", "end"]);
  /* Whose puck, as an arrow at centre ice toward the net they attack. */
  function arrowSVG(d, k) {
    if ((d.live || {}).state !== "live" || !k.puck) return "";
    const [x, y] = toArt(0, -30);
    const dir = k.puck === "home" ? 1 : -1, col = k.puck === "home" ? "var(--ch)" : "var(--ca)";
    return `<path class="rc-arrow" style="fill:${col}" d="M${(x + dir * 40).toFixed(1)} ${y.toFixed(1)} l${-dir * 28} -15 v30 z"/>`;
  }
  function shotsMarks(d, k) {
    return events(d).filter((e) => ATTEMPTS.has(e.kind) && e.x != null && (S.shots === "both" || sideOf(d, e.team) === S.shots))
      .map((e) => shotMark(d, e, k, 0.92)).join("");
  }
  const ICE_KINDS = [["all", "All"], ["hit", "Hits"], ["takeaway", "Takeaways"], ["giveaway", "Giveaways"], ["faceoff", "Faceoffs"], ["penalty", "Penalties"]];
  function iceMarks(d, k) {
    return events(d).filter((e) => e.x != null && (S.ice === "all" ? ICE_KINDS.some(([key]) => key === e.kind) : e.kind === S.ice))
      .map((e) => iceMark(d, e, k, 0.88)).join("");
  }
  function trackerHTML(d, k) {
    const box = (d.rink || {}).box || {};
    const col = (ha) => {
      const b = box[d[ha]] || { skaters: [], goalies: [] };
      const sk = b.skaters.slice().sort((a, c) => (secs(c.toi) || 0) - (secs(a.toi) || 0)).slice(0, 9);
      const g = b.goalies[0];
      return `<div class="rc-trk-col"><div class="rc-trk-head">${teamMarkIn("nhl", d[ha], 22)} ${esc(teamNameIn("nhl", d[ha]) || d[ha])}</div>
        ${sk.length ? sk.map((p) => `<div class="rc-trk-row">${faceHTML(p.name, k, 30)}
          <div class="rc-trk-t"><b>${p.num != null ? `#${esc(p.num)} ` : ""}${esc(p.name)}</b>
            <span>${esc(p.g)}G ${esc(p.a)}A · ${esc(p.sog)} SOG · ${p.pm > 0 ? "+" : ""}${esc(p.pm)}</span></div>
          <span class="rc-toi">${esc(p.toi || "")}</span></div>`).join("") : `<p class="rail-quiet">No box score yet.</p>`}
        ${g ? `<div class="rc-trk-row goalie">${faceHTML(g.name, k, 30)}<div class="rc-trk-t"><b>${g.num != null ? `#${esc(g.num)} ` : ""}${esc(g.name)}</b>
          <span>${esc(g.sv)} saves on ${esc(g.sa)}${g.sa ? ` · ${(g.sv / g.sa).toFixed(3).replace(/^0/, "")}` : ""}</span></div><span class="rc-toi">${esc(g.toi || "")}</span></div>` : ""}</div>`;
    };
    return `<div class="rc-pane-head"><b>Ice time</b><span class="mini">Who is on the ice is not in the league's live feed; this is every skater's game so far, most minutes first.</span></div>
      <div class="rc-trk">${col("away")}${col("home")}</div>`;
  }
  /* The attempt race: each side's running count of attempts over the
     game, the goals on it, the periods marked. */
  function flowSVG(d, k, h) {
    const f = flow(d);
    if (f.pts.length < 2) return `<p class="rail-quiet">The game flow draws itself from the first attempt.</p>`;
    const byXg = S.flowBy === "xg" && (d.rink || {}).xg;
    const ka = byXg ? "xa" : "a", kh = byXg ? "xh" : "h";
    const reg = 3 * PERIOD_S, last = f.pts[f.pts.length - 1];
    const end = Math.max(reg, last.t);
    const Wd = 1000, H2 = h || 220;
    const top = byXg ? Math.max(2, last.xa, last.xh) : Math.max(10, last.a, last.h);
    const X = (t) => (t / end) * Wd, Y = (n) => H2 - 10 - (n / top) * (H2 - 24);
    const line = (key) => {
      let p = `M0 ${Y(0)}`;
      f.pts.forEach((r, i) => { if (i) p += ` H${X(r.t).toFixed(1)} V${Y(r[key]).toFixed(1)}`; });
      return p + ` H${X(last.t).toFixed(1)}`;
    };
    let lines = "";
    for (let t = PERIOD_S; t < end; t += PERIOD_S) lines += `<line class="rc-q-line" x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="0" y2="${H2}"/>`;
    // On the xG race a goal sits at its side's running xG at that moment.
    const at = (g) => (byXg ? (f.pts.filter((p) => p.t <= g.t).pop() || {})[g.side === "home" ? "xh" : "xa"] || 0 : g.n);
    const goals = f.goals.map((g) => `<circle class="rc-flow-goal" cx="${X(g.t).toFixed(1)}" cy="${Y(at(g)).toFixed(1)}" r="6" style="fill:${g.side === "home" ? "var(--ch)" : "var(--ca)"}"/>`).join("");
    return `<svg class="rc-flow" viewBox="0 0 ${Wd} ${H2}" preserveAspectRatio="none" role="img" aria-label="${byXg ? "Expected goals" : "Shot attempts"} over the game">
      ${lines}<path class="rc-flow-line away" d="${line(ka)}"/><path class="rc-flow-line home" d="${line(kh)}"/>${goals}</svg>`;
  }
  function flowPaneHTML(d, k) {
    const T = k.stats;
    const has = !!(d.rink || {}).xg;
    const byXg = has && S.flowBy === "xg";
    const xg = has ? `<span>xG <b>${T.away.xg.toFixed(2)}</b> – <b>${T.home.xg.toFixed(2)}</b> <i class="mini">our model</i></span>` : "";
    const chips = has ? `<div class="rc-legend"><button type="button" class="rc-chip${byXg ? "" : " on"}" data-rc-flow="att">Attempts</button>
      <button type="button" class="rc-chip${byXg ? " on" : ""}" data-rc-flow="xg">xG race</button></div>` : "";
    const best = byXg ? flow(d).best : null;
    const big = best ? `<p class="rc-flow-best">Biggest chance: <b>${esc(best.e.player || d[best.side])}</b> (${esc(d[best.side])}), ${best.xg.toFixed(2)} xG
      · ${esc([periodShort(best.e.period), best.e.clock ? String(best.e.clock).replace(/^0(\d:)/, "$1") : ""].filter(Boolean).join(" "))}${best.e.kind === "goal" ? " · scored" : ""}</p>` : "";
    return `<div class="rc-pane-head"><b>${byXg ? "xG race" : "Game flow"}</b><span class="mini">${byXg
      ? "Each side's expected goals as the game goes, our shot model's price on every unblocked attempt; each goal a dot."
      : "Shot attempts over the game, each goal a dot on the scorer's line."}</span></div>
      ${chips}${flowSVG(d, k, 200)}${big}
      <div class="rc-flow-stats"><span class="rc-key away">${esc(d.away)}</span><span class="rc-key home">${esc(d.home)}</span>
        <span>Attempts <b>${T.away.att}</b> – <b>${T.home.att}</b></span><span>Shots on goal <b>${T.away.sog}</b> – <b>${T.home.sog}</b></span>${xg}</div>`;
  }
  /* A FINISHED GAME HAS NO LIVE PICTURE (Ethan, 2026-10-30: a past game's
     page is "just supposed to be the espn page with the past game data"):
     its rink opens on the shot chart, and Live is not offered. */
  const viewFor = (d) => (S.view === "live" && (d.live || {}).state === "final" ? "shots" : S.view);
  function chipsHTML(d, k) {
    const view = viewFor(d);
    if (view === "shots") {
      const T = k.stats;
      const chip = (key, label) => `<button type="button" class="rc-chip${S.shots === key ? " on" : ""}" data-rc-shots="${key}">${label}</button>`;
      const xg = (d.rink || {}).xg ? `<span class="rc-key-note">xG ${T.away.xg.toFixed(2)} – ${T.home.xg.toFixed(2)} · our model</span>` : "";
      return `<div class="rc-legend">${chip("both", "Both")}${chip("away", `${esc(d.away)} ${T.away.goals}/${T.away.sog}`)}${chip("home", `${esc(d.home)} ${T.home.goals}/${T.home.sog}`)}
        <span class="rc-key-note"><i class="goal"></i>Goal <i class="sog"></i>On goal <i class="miss"></i>Missed <i class="block"></i>Blocked</span>${xg}</div>`;
    }
    if (view === "ice") {
      const count = (kind) => events(d).filter((e) => e.kind === kind && e.x != null).length;
      return `<div class="rc-legend">${ICE_KINDS.map(([key, label]) =>
        `<button type="button" class="rc-chip${S.ice === key ? " on" : ""}" data-rc-ice="${key}">${label}${key === "all" ? "" : ` ${count(key)}`}</button>`).join("")}</div>`;
    }
    return "";
  }
  function stageHTML(d, k) {
    const view = viewFor(d);
    const lastSpot = events(d).filter((e) => e.x != null).slice(-1)[0];
    // A phone crops the live view to the half the puck's run stays in, and
    // shows the whole rink when the run crosses centre ice.
    const ran = view === "live" ? runSpan(d) : null;
    const half = view === "live" && lastSpot ? (ran ? ran : "none")
      : view === "shots" && S.shots !== "both" ? (S.shots === "away" ? "left" : "right") : "none";
    const marks = view === "live" ? liveMarks(d, k) : view === "shots" ? shotsMarks(d, k) : view === "ice" ? iceMarks(d, k) : "";
    const pane = view === "tracker" ? trackerHTML(d, k) : view === "flow" ? flowPaneHTML(d, k) : "";
    const v = (d.rink || {}).venue || {};
    const where = v.name ? `<div class="rc-venue"><b>${esc(v.name)}</b>${v.city ? `<span>${esc(v.city)}</span>` : ""}</div>` : "";
    const pp = k.pp && (d.live || {}).state === "live" && view === "live"
      ? `<div class="rc-ppbadge" style="--pc:${k.pp.side === "home" ? "var(--ch)" : "var(--ca)"}">${esc(d[k.pp.side])} power play${k.pp.left != null && k.pp.left > 0 ? ` · ${mmss(k.pp.left)}` : ""}</div>` : "";
    const tabs = [["live", "Live", "Live", "hockey"], ["shots", "Shot Chart", "Shots", "target"], ["ice", "Ice Tracker", "Ice", "stadium"],
                  ["tracker", "Player Tracker", "Players", "people"], ["flow", "Game Flow", "Flow", "chart"]]
      .filter(([key]) => key !== "live" || (d.live || {}).state !== "final").map(([key, label, short, ic]) =>
      `<button type="button" class="rc-view${view === key ? " on" : ""}" data-rc-view="${key}" aria-pressed="${view === key}" aria-label="${label}">${icon(ic, 13)}<span class="rc-vl">${label}</span><span class="rc-vs">${short}</span></button>`).join("");
    // The scene is the art and what sits over it; the views are a bar under
    // it, as in Ethan's render.
    // Replay plays the newest events again (the puck's run, liveMarks).
    const replay = view === "live" && lastSpot
      ? `<button type="button" class="rc-replay" data-rc-replay aria-label="Replay the last plays">${svg(GLYPH.replay, 13)}<span>Replay</span></button>` : "";
    // The arena's own screens lit with the game (its power play the one this
    // page shows), and a big moment's banner for a phone (detail.js
    // pbpArenaSVG, the live page's file).
    const lit = typeof pbpArenaSVG === "function"
      ? pbpArenaSVG(d, "nhl", { pp: k.pp ? k.pp.side : "", ppLeft: k.pp && k.pp.left > 0 ? k.pp.left : null }) : "";
    const shout = typeof pbpMomentBannerHTML === "function" ? pbpMomentBannerHTML(d, "nhl") : "";
    // The card is the page's own (detail.js gpStageHTML); what is in it is this file's.
    return gpStageHTML(`rc-stage v-${view}`, `--ca:${k.colors.away};--ch:${k.colors.home}`, `
      <div class="rc-scene"><div class="rc-art" data-half="${half}">
        <div class="rc-frame">${PICTURE}
          <svg class="rc-svg" viewBox="0 0 ${ART.w} ${ART.h}" preserveAspectRatio="none" aria-hidden="true">${lit}${marks}</svg></div>
        ${shout}${where}${pp}</div>
      ${chipsHTML(d, k)}
      ${pane ? `<div class="rc-pane" data-gp-scroll="rc-${view}">${pane}</div>` : ""}</div>
      <div class="rc-views" role="toolbar" aria-label="What the arena shows">${tabs}
        ${replay}<button type="button" class="rc-full" data-rc-full aria-label="Full screen">${EXPAND}</button></div>`);
  }

  /* ---------------- the play right now ----------------
     On the card every sport's is drawn on (js/gamecast.js playNow): the
     newest event in words, where on the ice, the score a goal left, and the
     people in it with the league's own faces and their game so far. A
     whistle or a period's end since is said under it. The caption under the
     arena said this, in a layout of its own. */
  const ASIDE = new Set(["start", "end", "stoppage", "delayed"]);
  function nowHTML(d, k) {
    const G = window.QBGamecast;
    const ev = events(d);
    const e = ev.slice().reverse().find((r) => !ASIDE.has(r.kind));
    const bits = e ? said(e, d) : null;
    if (!bits || !G || !G.playNow) return "";
    const end = endOf(d, e);
    const where = end === "neutral" ? " in the neutral zone" : end ? ` in the ${d[end]} end` : "";
    const score = e.kind === "goal" && e.score ? ` ${d.away} ${e.score[0]}, ${d.home} ${e.score[1]}.` : "";
    const box = (d.rink || {}).box || {};
    const lines = {};
    Object.values(box).forEach((b) => {
      ((b || {}).skaters || []).forEach((p) => { lines[p.name] = `${p.g} G, ${p.a} A, ${p.sog} SOG`; });
      ((b || {}).goalies || []).forEach((g) => { lines[g.name] = `${g.sv} saves on ${g.sa}`; });
    });
    const faces = {};
    Object.values(k.men).forEach((m) => { if (m.face) faces[String(m.name).toLowerCase()] = m.face; });
    const person = (name) => {
      const m = k.men[name] || {};
      return { name, row: { name }, where: [m.team, m.pos, m.num != null ? `#${m.num}` : ""].filter(Boolean).join(" · "), line: lines[name] || "" };
    };
    // The power play and whose puck it is are the score's to say (parts `mid`, `ball`), once.
    return G.playNow(d, "nhl", faces, { team: e.team || "", when: [periodShort(e.period), clockOf(e)].filter(Boolean).join(" "),
      kind: playWords(e, d, k).title, said: `${bits.map((x) => (x && x.b ? x.b : x)).join("")}${where}.${score}`,
      people: bits.filter((x) => x && x.b).map((x) => person(x.b)),
      since: ev.slice(ev.indexOf(e) + 1).map((r) => momentOf(r, d)).filter(Boolean).slice(-4) });
  }

  /* ---------------- in the Stats room ----------------
     Hockey counts its own game off the league's events, so the page's team
     stats and box scores are these (the same row, the same card: detail.js
     gpTsRowHTML, gpTsCardHTML, gpBoxCardHTML); and after them what only it
     has: every attempt from above, the shots period by period and the
     trends. */
  function teamStatsHTML(d, k) {
    const T = k.stats, foPct = (s) => (T.away.fo ? Math.round((100 * T[s].fow) / T.away.fo) : null);
    // Nothing counted yet: the summary's own team stats, when it has any, stand (null).
    if (!(T.away.att + T.home.att + T.away.fo) || typeof gpTsCardHTML !== "function") return null;
    const rows = [["Shots on goal", T.away.sog, T.home.sog], ["Shot attempts", T.away.att, T.home.att],
                  ["Faceoff %", foPct("away"), foPct("home")], ["Hits", T.away.hits, T.home.hits], ["Blocked shots", T.away.blocks, T.home.blocks],
                  ["Takeaways", T.away.take, T.home.take], ["Giveaways", T.away.give, T.home.give], ["Penalty minutes", T.away.pim, T.home.pim],
                  ["Power plays", `${T.away.ppg}/${T.away.ppo}`, `${T.home.ppg}/${T.home.ppo}`]];
    if ((d.rink || {}).xg) rows.push(["xG · our model", T.away.xg.toFixed(2), T.home.xg.toFixed(2)]);
    const val = (v) => { const m = /^(\d+)\/(\d+)$/.exec(String(v)); return m ? Number(m[1]) : Number(v) || 0; };
    return gpTsCardHTML(d, "nhl", rows.filter(([, a, h]) => a != null && h != null)
      .map(([label, a, h]) => gpTsRowHTML(label, esc(a), esc(h), val(a), val(h))).join(""), "");
  }
  function boxHTML(d, ha) {
    const b = ((d.rink || {}).box || {})[d[ha]] || {};
    const skaters = b.skaters || [], goalies = b.goalies || [];
    if ((!skaters.length && !goalies.length) || typeof gpBoxCardHTML !== "function") return "";
    const byToi = (a, c) => (secs(c.toi) || 0) - (secs(a.toi) || 0);
    const shirt = (p) => (p.num != null ? `#${p.num}` : "");
    const line = (rows) => rows.slice().sort(byToi).map((p) => ({ name: p.name, pos: shirt(p),
      cells: [p.g, p.a, p.sog, `${p.pm > 0 ? "+" : ""}${p.pm}`, p.hits, p.toi] }));
    const labels = ["G", "A", "SOG", "+/-", "HIT", "TOI"];
    return gpBoxCardHTML("nhl", d[ha], [
      { key: `${ha}-forwards`, title: "Forwards", labels, rows: line(skaters.filter((p) => p.pos !== "D")) },
      { key: `${ha}-defense`, title: "Defense", labels, rows: line(skaters.filter((p) => p.pos === "D")) },
      { key: `${ha}-goalies`, title: "Goalies", labels: ["SA", "SV", "GA", "SV%", "TOI"],
        rows: goalies.map((g) => ({ name: g.name, pos: shirt(g), cells: [g.sa, g.sv, g.ga, g.sa ? (g.sv / g.sa).toFixed(3).replace(/^0/, "") : "–", g.toi] })) },
    ], false);
  }
  /* Every attempt on a flat rink, the away side at the left. */
  function flatRinkHTML(d, k) {
    const shots = events(d).filter((e) => ATTEMPTS.has(e.kind) && e.x != null);
    const X = (x) => (x + 100) * 5, Y = (y) => (42.5 - y) * 5;
    const marks = shots.map((e) => {
      const x = X(e.x), y = Y(e.y), col = colOf(d, e, k);
      return e.kind === "goal" ? `<circle cx="${x}" cy="${y}" r="9" class="rc-fs goal" style="fill:${col}"/>`
        : e.kind === "sog" ? `<circle cx="${x}" cy="${y}" r="6" class="rc-fs" style="fill:${col}"/>`
        : e.kind === "miss" ? `<circle cx="${x}" cy="${y}" r="6" class="rc-fs miss" style="stroke:${col}"/>`
        : `<path d="${cross(x, y, 5)}" class="rc-fs block" style="stroke:${col}"/>`;
    }).join("");
    const circ = (cx, cy, r, cls) => `<circle cx="${X(cx)}" cy="${Y(cy)}" r="${r * 5}" class="${cls}"/>`;
    return `<svg class="rc-flat" viewBox="0 0 1000 425" role="img" aria-label="Every shot attempt on the ice">
        <rect x="2" y="2" width="996" height="421" rx="140" class="rc-fl-ice"/>
        <line x1="500" y1="0" x2="500" y2="425" class="rc-fl-red"/><line x1="375" y1="0" x2="375" y2="425" class="rc-fl-blue"/><line x1="625" y1="0" x2="625" y2="425" class="rc-fl-blue"/>
        <line x1="55" y1="30" x2="55" y2="395" class="rc-fl-red thin"/><line x1="945" y1="30" x2="945" y2="395" class="rc-fl-red thin"/>
        ${circ(0, 0, 15, "rc-fl-ring")}${[[-69, 22], [-69, -22], [69, 22], [69, -22]].map(([a, b]) => circ(a, b, 15, "rc-fl-ring")).join("")}
        <path d="M55 182 a30 30 0 0 1 0 60" class="rc-fl-crease"/><path d="M945 182 a30 30 0 0 0 0 60" class="rc-fl-crease"/>
        ${marks}</svg>
      <p class="mini rc-flat-note">${esc(d.away)} shoot at the left net, ${esc(d.home)} at the right, every period turned to match.</p>`;
  }
  /* Shots on goal period by period (the goals are the page's line score). */
  function sogByPeriodHTML(d, k) {
    const ev = events(d);
    const periods = [...new Set(ev.map((e) => Number(e.period)).filter(Boolean))].sort((a, b) => a - b);
    if (!periods.length) return "";
    const count = (side, p) => ev.filter((e) => Number(e.period) === p && sideOf(d, e.team) === side && (e.kind === "sog" || e.kind === "goal")).length;
    const row = (side) => `<tr><th scope="row">${esc(d[side])}</th>${periods.map((p) => `<td>${count(side, p)}</td>`).join("")}<td class="t">${k.stats[side].sog}</td></tr>`;
    return `<p class="rc-mini-k">Shots on goal</p><table class="rc-ls"><thead><tr><th></th>${periods.map((p) =>
      `<th scope="col">${esc(periodShort(p))}</th>`).join("")}<th scope="col">T</th></tr></thead><tbody>${row("away")}${row("home")}</tbody></table>`;
  }
  /* The trends, read off the events: who is pressing, the power play, a side
     gone quiet, an empty net, our expected goals, each goalie's night (the
     saves, and the goals saved above what our shot model expected of the
     chances faced), the physical game. */
  function trendsHTML(d, k) {
    const out = [];
    const lv = d.live || {}, T = k.stats;
    if (lv.state === "live") {
      const p = pressure(d, 300);
      if (p.away || p.home) out.push([GLYPH.sog, `Last five minutes: ${esc(d.away)} <b>${p.away}</b> attempts, ${esc(d.home)} <b>${p.home}</b>.`]);
      if (k.pp) out.push([GLYPH.penalty, `${esc(d[k.pp.side])} on the power play${k.pp.left != null && k.pp.left > 0 ? `, <b>${mmss(k.pp.left)}</b> left` : ""}.`]);
      const q = quiet(d);
      ["away", "home"].forEach((s) => { if (q[s] >= 300) out.push([GLYPH.stoppage, `${esc(d[s])}: no shot on goal in <b>${mmss(q[s])}</b>.`]); });
      const ev = events(d), sit = ev.length ? sitOf(ev[ev.length - 1].sc) : null;
      if (sit && sit.en) out.push([GLYPH.goal, `${esc(d[sit.en])} have pulled their goalie.`]);
    }
    if ((d.rink || {}).xg && (T.away.xgn || T.home.xgn)) out.push([GLYPH.goal, `Expected goals (our model): ${esc(d.away)} <b>${T.away.xg.toFixed(2)}</b>, ${esc(d.home)} <b>${T.home.xg.toFixed(2)}</b>.`]);
    const box = (d.rink || {}).box || {};
    ["away", "home"].forEach((s) => {
      ((box[d[s]] || {}).goalies || []).filter((g) => g && g.sa).forEach((g) => {
        const faced = events(d).filter((e) => sideOf(d, e.team) === other(s) && (e.kind === "sog" || e.kind === "goal") && e.player2 === g.name);
        const xga = faced.reduce((a, e) => a + (Number(e.xg) || 0), 0);
        const gsax = (d.rink || {}).xg && faced.length ? xga - faced.filter((e) => e.kind === "goal").length : null;
        out.push([GLYPH.block, `${esc(g.name)}: <b>${g.sv}</b> saves on ${g.sa}${gsax != null
          ? `, <b>${gsax > 0 ? "+" : gsax < 0 ? "\u2212" : ""}${Math.abs(gsax).toFixed(2)}</b> goals saved above expected (our model)` : ""}.`]);
      });
    });
    if (T.away.att + T.home.att) out.push([GLYPH.hit, `Hits ${esc(d.away)} <b>${T.away.hits}</b>, ${esc(d.home)} <b>${T.home.hits}</b>; takeaways ${T.away.take} – ${T.home.take}, giveaways ${T.away.give} – ${T.home.give}.`]);
    return out.length ? `<div class="rc-facts">${out.map(([g, text]) => `<div class="rc-fact">${svg(g)}<span>${text}</span></div>`).join("")}</div>` : "";
  }
  function statsExtraHTML(d, k) {
    // The cards are the page's own (detail.js gpCardHTML).
    const card = (title, sub, body) => gpCardHTML(title, sub, body, "rc-icecard", `--ca:${k.colors.away};--ch:${k.colors.home}`);
    const any = events(d).some((e) => ATTEMPTS.has(e.kind) && e.x != null);
    return `${card("Shot chart", "every attempt, from above", any ? flatRinkHTML(d, k) : "")}${
      card("Trends", "", `${sogByPeriodHTML(d, k)}${trendsHTML(d, k)}`)}`;
  }

  /* ---------------- the parts of the page ----------------
     The page is every sport's now (detail.js gpPageHTML, 2026-11-21; Ethan:
     "all sports in all aspects should be trying to match nfl and that should
     be automatic when we do any visual changes"): the bar that stays when you
     scroll, the score on the clubs' colours with a goal flashed on it, the
     line score, the rooms. This file drew a page of its own beside it, and
     nothing done there reached it. It brings what is hockey's (gpKit): the
     arena under the score, the newest play in words, the plays period by
     period off the league's own events, its own count of the game for the
     Stats room, and on the score the puck, the power play, the shots on
     goal and the league's own clock. Before the puck drops there is no
     arena, as there is no field. */
  function facts(d, ctx) {
    return { colors: colours(d), men: menOf(d), stats: teamStats(d), puck: puckAfter(d), pp: (d.live || {}).state === "live" ? powerPlay(d) : null,
             faces: (ctx && ctx.faces) || {}, boardGame: (ctx && ctx.boardGame) || null };
  }
  function parts(ctx) {
    const d = ctx.d;
    if (S.game !== String(d.event_id)) { S.game = String(d.event_id); S.run = null; }
    const k = facts(d, ctx);
    const lv = d.live || {}, c = (d.rink || {}).clock || {};
    const on = lv.state === "live" || lv.state === "final";
    const per = Number(c.period) || 0;
    const boxes = `${boxHTML(d, "away")}${boxHTML(d, "home")}`;
    const ev = events(d);
    return {
      stage: on ? stageHTML(d, k) : "",
      now: lv.state === "live" ? nowHTML(d, k) : "",
      // The league's own events as the page's rows; until the first of them lands, the game file's.
      rows: ev.length ? ev.map(rowOf) : null, say: (p) => (p && p.rink ? sayPlay(p.rink, d) : null),
      teamStats: teamStatsHTML(d, k), boxes: boxes || null,
      statsExtra: on ? statsExtraHTML(d, k) : "",
      ball: lv.state === "live" ? (k.puck || "") : "", ballIcon: "hockey", ballTitle: "Puck — from the last play",
      mid: on ? midHTML(d, k) : "",
      down: k.pp ? `PP ${d[k.pp.side]}${k.pp.left != null && k.pp.left > 0 ? ` ${mmss(k.pp.left)}` : ""}` : "",
      // The league's own clock, where the file carries it: the period, the time left, an intermission.
      live: lv.state === "live" && per ? { period: `P${per}`, clock: String(c.left || lv.clock || "").replace(/^0(\d:)/, "$1"),
                                           ...(c.intermission && !lv.hold ? { hold: "Intermission" } : {}) } : null,
      wire,
    };
  }
  /* The arena's own buttons (the views, the chips over them, Replay, full
     screen); a choice draws the page again (detail.js renderPbpPage), which
     keeps the picture already painted. Bound once to the page's host. */
  function wire(host) {
    if (!host || host.dataset.rcWired) return;
    host.dataset.rcWired = "1";
    host.addEventListener("click", (e) => {
      const t = e.target.closest("[data-rc-view],[data-rc-shots],[data-rc-ice],[data-rc-full],[data-rc-replay],[data-rc-flow]");
      if (!t || !host.contains(t)) return;
      if (t.hasAttribute("data-rc-full")) {
        const st = host.querySelector(".rc-stage");
        if (st && st.requestFullscreen) st.requestFullscreen().catch(() => {});
        return;
      }
      const ds = t.dataset;
      if (t.hasAttribute("data-rc-replay")) S.replay = true;
      if (ds.rcView) S.view = ds.rcView;
      if (ds.rcShots) S.shots = ds.rcShots;
      if (ds.rcIce) S.ice = ds.rcIce;
      if (ds.rcFlow) S.flowBy = ds.rcFlow;
      if (typeof renderPbpPage === "function") renderPbpPage();
    });
  }

  window.QBRink = {
    parts,
    // The readers, for the tests and for Ask.
    events, sitOf, puckAfter, endOf, powerPlay, teamStats, flow, pressure, quiet, nowElapsed, toArt, colours, playWords, CP,
    said, momentOf, sayPlay, rowOf,
    // The Live tab's cards (app.js liveWords).
    cardRows,
  };
})();
