/* Qellys Book — Carry chart (js/carrychart.js): every run a player made.
   ==========================================================================
   Ethan, 2026-10-13, with the league's Next Gen Stats carry chart for Josh
   Allen at the Rams on the screen: "one feature too add for nfl and CFB is
   a carry chart exactly in the screenshot for every player ... Users
   should be able too look at a Carry chart for past games and also just a
   kinda 'average' carry chart showing where they run."

   WHAT IS DRAWN IS WHAT THE PLAY-BY-PLAY SAYS. The league's own chart
   traces the runner's tracked path; that tracking is not published. The
   public NFL play-by-play does record the hole every run hit (left end to
   right end), how far it went, the down, the field position, scrambles,
   touchdowns and lost fumbles — engine/carries.py stores all of it and
   /api/players/carries serves it. So an NFL line runs from the backfield,
   through the hole the play-by-play names, straight to where the carry
   ended: the hole and the length are the record, the bend into the hole
   is drawn, and the note under the chart says so.

   COLLEGE RECORDS NO HOLE. A college game spreads its carries across the
   field in the order they happened, each a straight run from behind the
   line to where it ended, so no line points anywhere it did not go. The
   season view does the same shortest to longest.

   THE SEASON VIEW is the "average" chart: every carry faint, and for the
   NFL one bold ray per hole — as thick as his share of carries there and
   as long as his average gain there.

   THE ROUTE CHART (the same day, with the league's route chart for Sam
   LaPorta: "We can add route charts for wr and shit too") is this
   module's second kind (S.kind "routes", /api/players/routes,
   engine/targets.py). Every pass thrown to him: how far past the line
   and to which third of the field, caught or not, the yards after the
   catch. Where the league charted the route (nflverse publishes it a
   season behind, through 2025) it is drawn in that route's shape to
   where the ball arrived; this season it is drawn as the throw, from the
   pocket, because a guessed route was measured wrong more often than
   right. The note under each chart says which.

   EVERY CHART SINCE (Ethan, the same evening, on the list of charts the
   data could carry: "Yes do all of them and don’t stop till they are all
   done") registers in DRAW below the same parts — a game's drawing, the
   season's, the numbers beside each, every play in order, the season's
   splits and a note on how it is drawn — so a quarterback's chart, a
   hitter's or a goalie's reads exactly like a back's: the same games
   row, the same By game | season tabs, the same folds. The first is the
   passing chart (S.kind "passes", engine/passes.py): every throw a
   passer made, from the pocket to where the ball arrived, and the sacks
   he took.

   Loaded on first use (app.js openCarryChart) and drawn in the page's
   global scope beside app.js, using its helpers by name (escapeHtml,
   teamMarkIn, teamNameIn, lockScroll). No inline handlers: the page's CSP
   forbids them. */
(function () {
  "use strict";
  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const HOLES = ["LE", "LT", "LG", "M", "RG", "RT", "RE"];
  const HOLE_NAME = { LE: "Left end", LT: "Left tackle", LG: "Left guard", M: "Middle",
                      RG: "Right guard", RT: "Right tackle", RE: "Right end" };
  //: Where each hole sits across the field, in the chart's lane units
  //: (the sidelines are at ±SIDE). Spread wider than an offensive line is
  //: so seven lanes read apart on a phone; the labels under the line say
  //: which is which.
  const LANE = { LE: -16, LT: -10, LG: -4.6, M: 0, RG: 4.6, RT: 10, RE: 16 };
  const SIDE = 26;
  //: The drawing: a field seen from behind the offence, nearer yards wider.
  const W = 640, H = 390, CX = W / 2, BOT = H - 34, TOP = 30, HALF = 262, RATIO = 0.58, YMIN = -10;
  const ROUNDS = { 19: "Wild Card", 20: "Divisional", 21: "Conference", 22: "Super Bowl" };
  const ROUND_TAG = { 19: "WC", 20: "DIV", 21: "CONF", 22: "SB" };
  //: The route chart's thirds of the field (the play-by-play's pass
  //: location) as bands across the drawing, in yards from the middle.
  const BAND = { L: [-21, -11], M: [-6, 6], R: [11, 21] };
  const THIRD = { L: [-SIDE, -8.9], M: [-8.9, 8.9], R: [8.9, SIDE] };
  const SIDE_WORD = { L: "left", M: "middle", R: "right" };
  //: Depth bands, as engine/targets.DEPTHS.
  const DEPTH = [["behind", "Behind the line"], ["short", "0–9 yards"], ["mid", "10–19 yards"], ["deep", "20+ yards"]];
  const ROUTE_NAME = { "GO": "Go", "SLANT": "Slant", "QUICK OUT": "Quick out", "HITCH/CURL": "Hitch/curl",
                       "IN/DIG": "In/dig", "DEEP OUT": "Deep out", "POST": "Post", "CORNER": "Corner",
                       "SHALLOW CROSS/DRAG": "Shallow cross", "SCREEN": "Screen", "SWING": "Swing",
                       "WHEEL": "Wheel", "TEXAS/ANGLE": "Angle" };
  //: Where a throw leaves from, and where a back's route starts: behind the line.
  const POCKET = -5;

  /* ONE DRAWING, MORE THAN ONE CHART. The overlay is one chart; since
     2026-10-13 a pick page carries its own (`mount`, below), and a page
     can hold several. Each is a {root, S, seq, inline, kinds, key} hung
     on its root element; `use` points the drawing at one, so the
     functions that draw read S as they always have. */
  let S = null;            // the state being drawn: {sport, kind, player, data, view, gi, sel}
  let C = null;            // the chart being drawn
  const use = (c) => { C = c || null; S = c ? c.S : null; return C; };
  //: Answers already fetched, by address, for ten minutes: a pick page
  //: is redrawn every minute and opened again and again, and a chart
  //: changes once a night.
  const CACHE = new Map();
  const CACHE_MS = 10 * 60 * 1000;
  //: The chart a reader switched to on a pick, for the rest of the visit.
  const MEM = new Map();
  let io = null;
  /* EVERY CHART'S NAMES: the switch's chip, the eyebrow, what it counts,
     where its rows are read from (for "still being filled"), the season
     tab and the section's line on a pick page. */
  const KIND = {
    carries: { chip: "Carries", title: "Carry chart", noun: "carries", one: "carry", where: "where he runs",
               dist: "Carry distribution", all: "All runs" },
    routes: { chip: "Targets", title: "Route chart", noun: "targets", one: "target", where: "where he’s thrown to",
              dist: "Target distribution", all: "All routes" },
    passes: { chip: "Passes", title: "Passing chart", noun: "throws", one: "throw", where: "where he throws",
              dist: "Throw distribution", all: "All throws",
              sec: "every throw he made: how far, which side, complete or not, and the sacks he took" },
    spray: { chip: "Hits", title: "Hit tracker", noun: "plate appearances", one: "plate appearance",
             where: "where he hits it", dist: "Hit distribution", all: "All balls",
             sec: "every ball he put in play: how hard, how high, how far and where it landed" },
    pitches: { chip: "Pitches", title: "Pitch chart", noun: "pitches", one: "pitch", where: "how he attacks",
               dist: "Pitch locations", all: "All pitches",
               sec: "every pitch he threw: where it crossed the plate, what it was and what the batter did with it" },
    shots: { chip: "Shots", title: "Shot chart", noun: "shots", one: "shot", where: "where he shoots",
             dist: "Shot distribution", all: "All shots",
             sec: "every shot he took: where from, made or missed, and how" },
    shotmap: { chip: "Shots", title: "Shot map", noun: "shot attempts", one: "shot attempt", where: "where he shoots from",
               dist: "Shot distribution", all: "All shots",
               sec: "every shot he took: where from, on goal, missed or blocked, and the goals" },
    saves: { chip: "Saves", title: "Save map", noun: "shots faced", one: "shot faced", where: "where he’s beaten",
             dist: "Shots faced", all: "All shots",
             sec: "every shot on goal he faced: where from, saved or scored" },
    role: { chip: "Role", title: "Role chart", noun: "games", one: "number", where: "his role",
            dist: "Usage, game by game",
            sec: "how much he’s used, game by game, beside his season" },
    kicks: { chip: "Kicks", title: "Kicker chart", noun: "kicks", one: "kick", where: "his range",
             dist: "Kick distribution", all: "All kicks",
             sec: "every field goal and extra point he tried: how far, made or missed, and in what weather" },
    fights: { chip: "Fights", title: "Fight history", noun: "fights", one: "number", where: "his fights", by: "By fight",
              dist: "The fight",
              sec: "every fight on his record: who, how it ended, the round and the time, and both men’s numbers",
              fill: "every fight is read from ESPN’s fight records a few fighters at a time" },
    /* Tonight's opponent beside his chart (2026-10-14, engine/matchview):
       one view, no games row; its chip names the opponent. */
    matchup: { chip: "Matchup", title: "Matchup", noun: "matchup", one: "zone", where: "tonight",
               dist: "Where he goes · what they allow",
               sec: "tonight’s opponent beside his chart: where he goes, and what they allow there" },
  };
  /* Every league's role chart says what it counts (engine/role). */
  Object.entries({
    nfl: "his snaps, targets and carries game by game, and his share of his team’s",
    cfb: "his carries, catches and attempts game by game, and his share of his team’s",
    nba: "his minutes, starts and shots, game by game", wnba: "her minutes and starts, game by game",
    mlb: "his plate appearances and spot in the order, or his pitch count and rest, game by game",
    nhl: "his ice time and shots, or the shots he faced, game by game",
  }).forEach(([lg, sec]) => { KIND[`role@${lg}`] = Object.assign({}, KIND.role, { sec }); });
  /* A league whose file says less than the NFL's gets its own names for
     the same chart: college targets have no air yards, no side of the
     field and no route, so they are a target chart, not a route chart. */
  KIND["routes@cfb"] = { chip: "Targets", title: "Target chart", noun: "targets", one: "target",
                         where: "every target", dist: "Target distribution",
                         sec: "every pass thrown his way that the play file names: caught or not, the yards, the down and where on the field" };
  const kindOf = (kind, sport) => KIND[`${kind}@${sport}`] || KIND[kind] || KIND.carries;
  //: The charts drawn by registered parts (`plugView`), by kind.
  const DRAW = {};
  /* A LEAGUE'S CHARTS IN A MODULE OF THEIR OWN, loaded the first time one
     is drawn (a football page never downloads baseball's drawing): the
     module registers its parts through `QBCarry.plug`. Listeners, not
     handler properties: the page's CSP forbids inline handlers. */
  const PLUG = { spray: "mlb", pitches: "mlb", shots: "hoops", shotmap: "nhl", saves: "nhl", role: "role",
                 kicks: "kicks", fights: "ufc", matchup: "matchup" };
  const plugs = {};
  function need(kind) {
    const f = PLUG[kind];
    if (!f || DRAW[kind]) return Promise.resolve(true);
    plugs[f] = plugs[f] || new Promise((ok) => {
      const el = document.createElement("script");
      el.src = `js/chart-${f}.js`;
      el.addEventListener("load", () => ok(true));
      el.addEventListener("error", () => { plugs[f] = null; ok(false); });
      document.head.appendChild(el);
    });
    return plugs[f];
  }

  /* ---------------- geometry ---------------- */
  function proj(x, y, ymax) {
    const d = (y - YMIN) / (ymax - YMIN);
    const k = 1 / RATIO - 1;
    const s = 1 / (1 + k * d);
    const yh = (TOP - BOT * RATIO) / (1 - RATIO);
    return [CX + x * (HALF / SIDE) * s, yh + (BOT - yh) * s];
  }
  const pt = (p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`;
  function bez(p0, p1, p2, p3, t) {
    const u = 1 - t;
    return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]];
  }
  /* A field path, projected point by point. A straight field line stays
     straight under a perspective, so only the curve needs sampling. */
  function pathD(pts, ymax) {
    return "M" + pts.map((p) => pt(proj(p[0], p[1], ymax))).join(" L");
  }
  function runPoints(hx, end, scramble) {
    const ey = end;
    let sy = scramble ? -7 : -5;
    if (ey <= sy + 1) sy = Math.max(YMIN + 0.3, ey - 2);
    const p0 = [0, sy], p3 = [hx, Math.min(0, ey)];
    const p1 = [0, sy + (p3[1] - sy) * 0.55], p2 = [hx, sy + (p3[1] - sy) * 0.45];
    const pts = [];
    for (let i = 0; i <= 14; i++) pts.push(bez(p0, p1, p2, p3, i / 14));
    if (ey > 0) pts.push([hx, ey]);
    return pts;
  }
  const clampY = (y, ymax) => Math.max(YMIN + 0.4, Math.min(ymax, y));
  function yMaxFor(ys) {
    const top = Math.max(0, ...ys);
    return Math.min(50, Math.max(20, Math.ceil((top + 3) / 10) * 10));
  }
  /* Several runs through one hole: fanned a little either side of it. */
  function fan(items, laneOf, width) {
    const by = {};
    items.forEach((c, i) => { const k = laneOf(c); (by[k] = by[k] || []).push(i); });
    const off = new Array(items.length).fill(0);
    Object.values(by).forEach((idx) => {
      const n = idx.length, step = Math.min(1.5, width / Math.max(1, n));
      idx.forEach((i, j) => { off[i] = (j - (n - 1) / 2) * step; });
    });
    return off;
  }

  /* ---------------- the route chart's geometry ---------------- */
  /* Where each ball arrived across the field: its third is the record;
     inside the third, the targets are spread in the order they were
     thrown so no two sit on one another. */
  function catchXs(ts) {
    const by = {};
    ts.forEach((t, i) => { const k = BAND[t.s] ? t.s : "M"; (by[k] = by[k] || []).push(i); });
    const xs = new Array(ts.length).fill(0);
    Object.keys(by).forEach((k) => {
      const [a, b] = BAND[k], idx = by[k];
      idx.forEach((i, j) => { xs[i] = a + (b - a) * (j + 0.5) / idx.length; });
    });
    return xs;
  }
  //: The sideline a target worked toward: the side its ball went to, and
  //: for the middle third alternately, so a crowd of middle targets reads
  //: as both directions rather than one.
  const outward = (x, i) => (x > 0.5 ? 1 : x < -0.5 ? -1 : (i % 2 ? 1 : -1));
  const yacOf = (t) => (t.c ? (t.yac != null ? t.yac : t.y - (t.ay || 0)) : 0);
  /* A charted route's shape, ending where the ball arrived (cx, cy). The
     kind of route is the league's charting; its stem and its break are
     drawn, not tracked. `o` is the sideline he works toward. */
  function routePoints(rt, cx, cy, o) {
    const X = (x) => Math.max(-SIDE + 0.8, Math.min(SIDE - 0.8, x));
    const P = (...ps) => ps.map(([x, y]) => [X(x), y]);
    const up = Math.max(cy, 0.5);
    switch (rt) {
      case "GO": return P([cx - o, 0], [cx, cy]);
      case "SLANT": { const w = Math.max(2.5, Math.min(9, (cy - 1.5) * 0.9));
        return P([cx + o * w, 0], [cx + o * w, Math.min(1.5, up)], [cx, cy]); }
      case "POST": { const stem = Math.max(5, Math.min(13, cy * 0.5)), w = Math.max(3, (cy - stem) * 0.55);
        return P([cx + o * w, 0], [cx + o * w, stem], [cx, cy]); }
      case "CORNER": { const stem = Math.max(5, Math.min(13, cy * 0.5)), w = Math.max(3, (cy - stem) * 0.55);
        return P([cx - o * w, 0], [cx - o * w, stem], [cx, cy]); }
      case "IN/DIG": return P([cx + o * 7, 0], [cx + o * 7, up], [cx, cy]);
      case "DEEP OUT": return P([cx - o * 6, 0], [cx - o * 6, up], [cx, cy]);
      case "QUICK OUT": return P([cx - o * 4, 0], [cx - o * 4, up], [cx, cy]);
      case "HITCH/CURL": return P([cx + o * 0.6, 0], [cx + o * 0.6, cy + 1.6], [cx, cy]);
      case "SHALLOW CROSS/DRAG": return P([cx - o * 13, 0], [cx - o * 11, up], [cx, cy]);
      case "SCREEN": return P([cx - o * 1.5, 1], [cx, cy]);
      case "SWING": return P([o * 2, POCKET], [cx * 0.6, (POCKET + cy) / 2 - 0.5], [cx, cy]);
      case "WHEEL": return P([o * 2, POCKET], [cx, Math.min(2, up)], [cx, cy]);
      case "TEXAS/ANGLE": return P([o * 2, POCKET], [cx + o * 5, cy * 0.4], [cx, cy]);
      default: return null;
    }
  }

  /* ---------------- words ---------------- */
  const ord = (n) => ({ 1: "1st", 2: "2nd", 3: "3rd", 4: "4th" }[n] || "");
  const signed = (y) => `${y > 0 ? "+" : y < 0 ? "−" : ""}${Math.abs(Math.round(y))}`;
  function spot(c, g) {
    const yl = c.yl;
    if (yl == null) return "";
    if (yl === 50) return "midfield";
    return yl > 50 ? `${g.team || "own"} ${100 - yl}` : `${g.opp || "opp"} ${yl}`;
  }
  function downDist(c) {
    if (!c.dn) return "";
    return `${ord(c.dn)} & ${c.yl != null && c.ds != null && c.yl <= c.ds ? "Goal" : (c.ds != null ? c.ds : "?")}`;
  }
  function qLabel(c) {
    const q = c.q > 4 ? "OT" : c.q ? `Q${c.q}` : "";
    return [q, c.clk].filter(Boolean).join(" ");
  }
  function gameName(g, sport) {
    const opp = teamNameIn(sport, g.opp);
    return `${g.home ? "vs" : "at"} ${opp}`;
  }
  function chipLabel(g, sport) {
    if (sport === "nfl" && g.week) {
      const wk = ROUND_TAG[g.week] || `W${g.week}`;
      return `${wk} ${g.home ? "vs" : "@"} ${g.opp}`;
    }
    const d = g.date ? new Date(g.date + "T12:00:00") : null;
    const md = d && !isNaN(d) ? d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
    return `${md} ${g.home ? "vs" : "@"} ${g.opp}`.trim();
  }
  function gameTitle(g, sport, season) {
    const when = sport === "nfl" && g.week ? (ROUNDS[g.week] || `Week ${g.week}`) : "";
    const d = g.date ? new Date(g.date + "T12:00:00") : null;
    const day = d && !isNaN(d) ? d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
    return `${season} ${gameName(g, sport)}` + [when, day].filter(Boolean).map((t) => ` · ${t}`).join("");
  }
  const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  //: A game's chip: "5-88" for five for 88 yards. A game he lost yards
  //: in read "1--2"; it says "1 for −2".
  const tally = (n, yds) => { const y = Math.round(yds); return y < 0 ? `${n} for −${-y}` : `${n}-${y}`; };
  const num1 = (v) => (v == null ? "—" : Number(v).toFixed(1));
  //: A season that spans two years is named for both: the NBA's and the NHL's 2025 is "2025-26".
  //: A fighter has no seasons: his record is his career.
  const seasonName = (sport, y) => (sport === "ufc" ? "Career"
    : /^(nba|nhl)$/.test(sport) ? `${y}-${String((+y + 1) % 100).padStart(2, "0")}` : `${y}`);

  /* ---------------- the field ---------------- */
  /* Drawn the way Ethan's renders draw it (2026-10-14): a dark turf with
     its mowing stripes every five yards, brighter toward the line; the
     sidelines and the hash marks in perspective; the yard numbers both
     sides, the line of scrimmage in gold, and the lanes or thirds named
     under the field, clear of the plays. No gradient or filter of the
     SVG's own: a page can hold two charts, and an id one of them defines
     would paint the other's only while the first is on screen. */
  const P1 = (p) => `${p[0].toFixed(1)}`, P2 = (p) => `${p[1].toFixed(1)}`;
  //: Where the names under the field sit: below its near edge.
  const UNDER = BOT + 24;
  function fieldSVG(ymax, laneLabels, ticks) {
    const L = (x, y) => proj(x, y, ymax);
    const tl = L(-SIDE, ymax), tr = L(SIDE, ymax), bl = L(-SIDE, YMIN), br = L(SIDE, YMIN);
    const out = [`<polygon class="cc-turf" points="${pt(bl)} ${pt(br)} ${pt(tr)} ${pt(tl)}"/>`];
    for (let y = YMIN, k = 0; y < ymax; y += 5, k++) {
      const y1 = Math.min(ymax, y + 5), near = 1 - (y - YMIN) / (ymax - YMIN);
      out.push(`<polygon class="cc-mow${k % 2 ? " alt" : ""}" points="${pt(L(-SIDE, y))} ${pt(L(SIDE, y))} ${pt(L(SIDE, y1))} ${pt(L(-SIDE, y1))}" style="fill-opacity:${(0.02 + 0.07 * near).toFixed(3)}"/>`);
    }
    let hash = "";
    for (let y = YMIN + 1; y < ymax; y++) {
      if (y % 5 === 0) continue;
      for (const [a, b] of [[-SIDE, -SIDE + 1.1], [SIDE - 1.1, SIDE], [-3.9, -2.7], [2.7, 3.9]]) {
        hash += `M${pt(L(a, y))} L${pt(L(b, y))}`;
      }
    }
    out.push(`<path class="cc-hash" d="${hash}"/>`);
    for (let y = YMIN + 5; y <= ymax; y += 5) {
      if (y === 0) continue;
      const a = L(-SIDE, y), b = L(SIDE, y);
      out.push(`<line class="cc-yd${y % 10 ? " minor" : ""}" x1="${P1(a)}" y1="${P2(a)}" x2="${P1(b)}" y2="${P2(b)}"/>`);
      if (y > 0 && y % 10 === 0) {
        out.push(`<text class="cc-ydl" x="${(a[0] - 10).toFixed(1)}" y="${(a[1] + 5).toFixed(1)}" text-anchor="end">+${y}</text>
          <text class="cc-ydl" x="${(b[0] + 10).toFixed(1)}" y="${(b[1] + 5).toFixed(1)}">+${y}</text>`);
      }
    }
    out.push(`<path class="cc-sl" d="M${pt(bl)} L${pt(tl)} M${pt(br)} L${pt(tr)} M${pt(bl)} L${pt(br)}"/>
      <text class="cc-ydl" x="${(bl[0] - 10).toFixed(1)}" y="${(bl[1] + 5).toFixed(1)}" text-anchor="end">−10</text>
      <text class="cc-ydl" x="${(br[0] + 10).toFixed(1)}" y="${(br[1] + 5).toFixed(1)}">−10</text>`);
    const l0 = L(-SIDE, 0), r0 = L(SIDE, 0);
    out.push(`<line class="cc-los-h" x1="${P1(l0)}" y1="${P2(l0)}" x2="${P1(r0)}" y2="${P2(r0)}"/>
      <line class="cc-los" x1="${P1(l0)}" y1="${P2(l0)}" x2="${P1(r0)}" y2="${P2(r0)}"/>
      <text class="cc-losl" x="${(l0[0] - 10).toFixed(1)}" y="${(l0[1] + 5).toFixed(1)}" text-anchor="end">LOS</text>
      <text class="cc-losl" x="${(r0[0] + 10).toFixed(1)}" y="${(r0[1] + 5).toFixed(1)}">LOS</text>`);
    (laneLabels || []).forEach(([x, t]) => {
      out.push(`<text class="cc-lane" x="${P1(L(x, YMIN))}" y="${UNDER}" text-anchor="middle">${esc(t)}</text>`);
    });
    (ticks || []).forEach(([x, t]) => {
      out.push(`<text class="cc-lane" x="${P1(L(x, YMIN))}" y="${UNDER}">${esc(t)}</text>`);
    });
    return out.join("");
  }

  /* One carry's line and its marks. `i` is the carry's index in the
     list under the chart, so a tap on either finds the other. Under the
     line, the same path wide and faint: the glow the renders give every
     run, without a filter for a phone to rasterise. */
  function runSVG(i, pts, c, ymax, extra) {
    const end = proj(pts[pts.length - 1][0], pts[pts.length - 1][1], ymax);
    const cls = `cc-run ${c.band}${extra || ""}${S && S.sel === i ? " sel" : ""}`;
    const delay = Math.min(i * 45, 900), d = pathD(pts, ymax);
    let marks = `<circle class="cc-end ${c.band}" cx="${P1(end)}" cy="${P2(end)}" r="2.6"/>`;
    if (c.td) marks += `<circle class="cc-td" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="6"/>`;
    if (c.fl) marks += `<g class="cc-fum"><circle cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="6"/>
      <path d="M${(end[0] - 3).toFixed(1)} ${(end[1] - 3).toFixed(1)} l6 6 m0 -6 l-6 6"/></g>`;
    return `<g class="cc-carry" data-i="${i}">
      <path class="cc-hit" d="${d}"/>
      <path class="cc-halo ${c.band}${extra || ""}" d="${d}" pathLength="1" style="animation-delay:${delay}ms"/>
      <path class="${cls}" d="${d}" pathLength="1" style="animation-delay:${delay}ms"/>
      ${marks}</g>`;
  }
  //: Where a back's run starts: behind the line, in the backfield.
  function originMark(ymax) {
    const p = proj(0, POCKET, ymax);
    return `<circle class="cc-origin" cx="${P1(p)}" cy="${P2(p)}" r="5.5"/>`;
  }

  function gameChart(g, sport, holes) {
    const cs = g.carries || [];
    const ymax = yMaxFor(cs.map((c) => c.y));
    let body = "";
    if (holes) {
      const off = fan(cs, (c) => c.h || "M", 4.2);
      cs.forEach((c, i) => {
        const hx = LANE[c.h || "M"] + off[i];
        const pts = runPoints(hx, clampY(c.y, ymax), c.sc);
        body += runSVG(i, pts, c, ymax, c.h ? "" : " nohole");
        if (c.y > ymax) body += longTag(hx, ymax, c.y);
      });
      return svgWrap(fieldSVG(ymax, HOLES.map((h) => [LANE[h], h])) + originMark(ymax) + body, g, sport, cs.length);
    }
    const n = cs.length;
    const ticks = [];
    let lastQ = null;
    cs.forEach((c, i) => {
      const x = -20 + 40 * (i + 0.5) / Math.max(1, n);
      if (c.q !== lastQ) { ticks.push([x - 1.2, c.q > 4 ? "OT" : `Q${c.q || "?"}`]); lastQ = c.q; }
      const ey = clampY(c.y, ymax);
      body += runSVG(i, [[x, Math.min(-2, ey - 2)], [x, ey]], c, ymax, "");
      if (c.y > ymax) body += longTag(x, ymax, c.y);
    });
    return svgWrap(fieldSVG(ymax, [], ticks) + body, g, sport, n);
  }

  function longTag(x, ymax, y) {
    const p = proj(x, ymax, ymax);
    return `<text class="cc-long" x="${p[0].toFixed(1)}" y="${(p[1] - 6).toFixed(1)}" text-anchor="middle">${Math.round(y)}</text>`;
  }

  function svgWrap(inner, g, sport, n, noun) {
    const what = `${n} ${noun || "carries"} ${g ? gameName(g, sport) : "this season"}`;
    // The chart's own name, the league's where it has one (college targets
    // are a target chart, not a route chart).
    const ks = Object.keys(KIND).filter((k) => KIND[k].noun === (noun || "carries"));
    const key = ks.find((k) => k.endsWith(`@${sport}`)) || ks.find((k) => !k.includes("@"));
    const kind = (KIND[key] || KIND.carries).title;
    return `<svg class="cc-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${kind}: ${what}.${g ? " Each one is listed below." : ""}`)}">${inner}</svg>`;
  }

  function seasonChart(d) {
    const every = [];
    d.games.forEach((g) => g.carries.forEach((c) => every.push(c)));
    if (!every.length) return "";
    if (d.holes) {
      const ymax = yMaxFor(d.by_hole.map((h) => h.ypc || 0).concat(every.map((c) => Math.min(c.y, 30))));
      const off = fan(every, (c) => c.h || "M", 5);
      let faint = "";
      every.forEach((c, i) => {
        const hx = LANE[c.h || "M"] + off[i];
        faint += `<path class="cc-faint ${c.band}" d="${pathD(runPoints(hx, clampY(c.y, ymax), c.sc), ymax)}"/>`;
      });
      let rays = "";
      d.by_hole.forEach((h) => {
        if (!h.n) return;
        const ypc = h.ypc || 0, band = ypc >= 5 ? "gain" : ypc < 0 ? "loss" : "short";
        const pts = runPoints(LANE[h.hole], clampY(Math.max(ypc, 0.6), ymax), false);
        const tip = proj(LANE[h.hole], clampY(Math.max(ypc, 0.6), ymax), ymax);
        const wpx = (2.5 + 15 * (h.share || 0)).toFixed(1);
        rays += `<path class="cc-ray ${band}" d="${pathD(pts, ymax)}" style="stroke-width:${wpx}px"/>`;
        // A hole he rarely uses keeps its ray and loses its label, so two
        // thin neighbours never print over each other; the table has both.
        if ((h.share || 0) < 0.06) return;
        rays += `<text class="cc-raylbl" x="${tip[0].toFixed(1)}" y="${(tip[1] - 20).toFixed(1)}" text-anchor="middle">${pct(h.share)}</text>
          <text class="cc-raysub" x="${tip[0].toFixed(1)}" y="${(tip[1] - 5).toFixed(1)}" text-anchor="middle">${num1(ypc)}</text>`;
      });
      return svgWrap(fieldSVG(ymax, HOLES.map((h) => [LANE[h], h])) + faint + rays, null, d.sport, every.length);
    }
    const sorted = every.slice().sort((a, b) => a.y - b.y);
    const ymax = yMaxFor(sorted.map((c) => c.y));
    const n = sorted.length;
    let body = "";
    sorted.forEach((c, i) => {
      const x = -22 + 44 * (i + 0.5) / n;
      const ey = clampY(c.y, ymax);
      body += `<path class="cc-faint strong ${c.band}" d="${pathD([[x, Math.min(-2, ey - 2)], [x, ey]], ymax)}"/>`;
    });
    const avg = d.season_line.ypc || 0;
    const a = proj(-SIDE, clampY(avg, ymax), ymax), b = proj(SIDE, clampY(avg, ymax), ymax);
    body += `<line class="cc-avg" x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}"/>
      <text class="cc-raylbl" x="${(b[0] - 4).toFixed(1)}" y="${(b[1] - 6).toFixed(1)}" text-anchor="end">avg ${num1(avg)}</text>`;
    return svgWrap(fieldSVG(ymax, [], [[-22, "Shortest"], [17, "Longest"]]) + body, null, d.sport, n);
  }

  /* ---------------- the route chart's drawings ---------------- */
  /* One target: the route the league charted or, where it charted none,
     the throw; then the run after the catch in green, and its marks. */
  function targetSVG(i, t, cx, ymax, o) {
    const cy = clampY(t.ay == null ? 0 : t.ay, ymax);
    const route = t.rt ? routePoints(t.rt, cx, cy, o) : null;
    const pts = route || [[0, POCKET], [cx, cy]];
    const cls = `${route ? "rc-route" : "rc-throw"}${t.c ? "" : " miss"}${t.int ? " int" : ""}${S && S.sel === i ? " sel" : ""}`;
    const delay = Math.min(i * 60, 900);
    const c = proj(cx, cy, ymax);
    let after = "", end = c, marks = "";
    if (t.c) {
      const ey = clampY(cy + yacOf(t), ymax);
      if (Math.abs(ey - cy) > 0.3) {
        const yd = pathD([[cx, cy], [cx, ey]], ymax);
        after = `<path class="rc-halo yac" d="${yd}" pathLength="1" style="animation-delay:${delay + 420}ms"/>
          <path class="rc-yac" d="${yd}" pathLength="1" style="animation-delay:${delay + 420}ms"/>`;
        end = proj(cx, ey, ymax);
      }
      marks += `<circle class="rc-catch" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="3.4"/>`;
    } else if (t.int) {
      marks += `<g class="rc-int"><path d="M${(c[0] - 5).toFixed(1)} ${(c[1] - 5).toFixed(1)} l10 10 m0 -10 l-10 10"/></g>`;
    } else {
      marks += `<circle class="rc-miss" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="4"/>`;
    }
    if (t.td) marks += `<circle class="cc-td" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="7"/>`;
    const d = pathD(pts, ymax);
    return `<g class="cc-carry" data-i="${i}">
      <path class="cc-hit" d="${d}"/>
      ${t.c && !t.int ? `<path class="rc-halo" d="${d}" pathLength="1" style="animation-delay:${delay}ms"/>` : ""}
      <path class="${cls}" d="${d}" pathLength="1" style="animation-delay:${delay}ms"/>
      ${after}${marks}</g>`;
  }
  const THIRDS = [[-17, "Left"], [0, "Middle"], [17, "Right"]];
  function routeGameChart(g) {
    const ts = g.targets || [];
    const ymax = yMaxFor(ts.map((t) => (t.ay || 0) + Math.max(0, yacOf(t))));
    const xs = catchXs(ts);
    let body = ts.some((t) => !t.rt) ? qbMark(ymax) : "";
    ts.forEach((t, i) => {
      body += targetSVG(i, t, xs[i], ymax, outward(xs[i], i));
      const far = (t.ay || 0) + Math.max(0, yacOf(t));
      if (far > ymax) body += longTag(xs[i], ymax, far);
    });
    return svgWrap(fieldSVG(ymax, THIRDS) + body, g, "nfl", ts.length, "targets");
  }
  function qbMark(ymax) {
    const p = proj(0, POCKET, ymax);
    return `<circle class="rc-qb" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="5"/>
      <text class="cc-lane" x="${(p[0] + 9).toFixed(1)}" y="${(p[1] + 5).toFixed(1)}">QB</text>`;
  }
  /* The season, where his targets go: the field in thirds and depth
     bands, each shaded by its share of his targets and labelled with it,
     and every target a dot where its ball arrived. */
  function routeSeasonChart(d) {
    const every = [];
    d.games.forEach((g) => (g.targets || []).forEach((t) => every.push(t)));
    if (!every.length) return "";
    const ymax = yMaxFor(every.map((t) => Math.min(t.ay || 0, 38)).concat([22]));
    const rows = { behind: [-7, 0], short: [0, 10], mid: [10, 20], deep: [20, ymax] };
    const most = Math.max(1, ...d.by_zone.map((z) => z.tgt));
    let cells = "", labels = "";
    d.by_zone.forEach((z) => {
      const [y0, y1] = rows[z.depth] || [0, 0], [x0, x1] = THIRD[z.side] || THIRD.M;
      const yb = Math.max(YMIN + 0.4, y0), yt = Math.min(ymax, y1);
      if (yt <= yb) return;
      const poly = [proj(x0, yb, ymax), proj(x1, yb, ymax), proj(x1, yt, ymax), proj(x0, yt, ymax)];
      const op = z.tgt ? (0.1 + 0.45 * z.tgt / most).toFixed(2) : "0";
      cells += `<polygon class="rc-cell" points="${poly.map(pt).join(" ")}" style="fill-opacity:${op}"/>`;
      if (!z.tgt) return;
      const m = proj((x0 + x1) / 2, (yb + yt) / 2, ymax);
      labels += `<text class="cc-raylbl rc-lbl" x="${m[0].toFixed(1)}" y="${(m[1] - 2).toFixed(1)}" text-anchor="middle">${pct(z.tgt / every.length)}</text>
        <text class="cc-raysub rc-lbl" x="${m[0].toFixed(1)}" y="${(m[1] + 14).toFixed(1)}" text-anchor="middle">${z.rec}/${z.tgt}</text>`;
    });
    const xs = catchXs(every);
    let dots = "";
    every.forEach((t, i) => {
      // A screen thrown 9 behind the line sits at the drawing's foot, not
      // under the third's label.
      const c = proj(xs[i], Math.max(-8.2, clampY(t.ay == null ? 0 : t.ay, ymax)), ymax);
      dots += `<circle class="rc-dot ${t.int ? "i" : t.c ? "c" : "m"}" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="2.8"/>`;
    });
    return svgWrap(fieldSVG(ymax, THIRDS) + cells + dots + labels, null, "nfl", every.length, "targets");
  }

  /* ---------------- the page ---------------- */
  /* Every number tile wears one of the site's own line icons (app.js
     `icon`), by its label, as the renders' "GAME STATS" row does. */
  const TILE_ICON = { "Carries": "football", "Targets": "target", "Receptions": "glove", "Yards": "rising",
                      "Yds/carry": "gauge", "Yds/target": "gauge", "Yds/catch": "gauge", "Yds/att": "gauge",
                      "TD": "star", "TD–INT": "star", "RYOE": "signal", "1st downs": "chev", "YAC": "bolt",
                      "aDOT": "angle", "Separation": "scale", "Cmp/Att": "target", "Throw time": "clock",
                      "Sacked": "warn", "Catch rate": "glove", "Completion": "check", "Success": "check",
                      "Long": "rising", "10+ yd runs": "bolt", "Stuffed (0 or less)": "octagon", "Drops": "cross",
                      "Contested won": "shield", "Throwaways": "dash", "Deep (20+)": "angle",
                      "Red zone targets": "target", "Targets a game": "list",
                      /* every other league's tiles (2026-10-14), so a guard's or a goalie's numbers wear
                         icons as a back's do; a label two leagues share in different senses is keyed by
                         its league ("nfl:FG") */
                      "Games": "calendar", "Points": "trophy", "FG": "basketball", "3PT": "target", "FT": "dot",
                      "Assisted": "people", "In the paint": "shield", "Minutes": "clock", "Rebounds": "glove",
                      "Assists": "people", "Steals": "bolt", "Blocks": "octagon", "Turnovers": "warn",
                      "H–AB": "baseball", "Total bases": "chart", "HR": "star", "RBI": "people", "BB–K": "scale",
                      "Hard hit": "hot", "AVG": "gauge", "SLG": "rising", "Exit velocity": "bolt",
                      "Launch angle": "angle", "Sweet spot": "target", "Pitches": "baseball", "Strikeouts": "target",
                      "Walks": "dash", "Hits": "glove", "Whiffs": "bolt", "CSW": "check", "Whiff rate": "bolt",
                      "In the zone": "target", "Batters faced": "people", "Top speed": "gauge",
                      "On goal": "hockey", "Goals": "star", "Attempts": "target", "Missed": "dash", "Blocked": "octagon",
                      "xG": "signal", "Shooting": "gauge", "Shots": "hockey", "Saves": "shield", "GA": "warn",
                      "Save %": "gauge", "GSAx": "signal", "xGA": "signal",
                      "nfl:FG": "football", "XP": "check", "50+": "bolt", "Conditions": "cloud",
                      "Snaps": "people", "Target share": "target", "Carry share": "football", "Catches": "glove",
                      "Catch share": "glove", "Red zone": "hot", "Air yards": "angle", "FGA": "basketball",
                      "3PA": "target", "FTA": "dot", "PA": "baseball", "Spot": "list", "Seen": "search",
                      "Batters": "people", "Outs": "check", "Rest": "moon", "Ice time": "clock", "SOG": "hockey",
                      "PP attempts": "bolt", "Shots faced": "shield", "Last 3": "rising", "Last 5": "rising",
                      "High": "trophy", "Highest": "trophy", "Role": "people",
                      "Result": "trophy", "Method": "bolt", "Round": "clock", "Time": "clock", "Fight lasted": "clock",
                      "Scheduled": "calendar", "Record": "trophy", "Won by finish": "bolt", "Stopped": "octagon",
                      "Distance": "scale", "Average fight": "clock", "Round 1": "bolt",
                      "Fit": "scale", "Their rank": "chart", "They allow": "shield", "Staff allows": "shield",
                      "They do": "shield", "Top zone": "target", "Their sample": "list", "Tonight’s starter": "baseball",
                      "Season": "calendar",
                      /* the hit page's (2026-10-14) */
                      "OPS": "gauge", "Pitches seen": "search",
                      "Fastball %": "bolt", "Avg exit velo": "gauge", "Hardest hit": "rising", "Hard hits": "hot" };
  const ico = (k) => {
    const n = (S && TILE_ICON[`${S.sport}:${k}`]) || TILE_ICON[k];
    return typeof icon === "function" && n ? icon(n, 13) : "";
  };
  function tile(k, v, sub) {
    return `<div class="cc-tile"><span class="cc-k">${ico(k)}${esc(k)}</span><b>${esc(v)}</b>${sub ? `<i>${esc(sub)}</i>` : ""}</div>`;
  }
  /* RYOE where the league published it (running backs, 10+ carries);
     first downs where it did not — never an estimate in its place. */
  function tilesFor(line, ryoe) {
    const t = [tile("Carries", line.n), tile("Yards", Math.round(line.yds)),
               tile("Yds/carry", num1(line.ypc)), tile("TD", line.td)];
    if (ryoe != null) t.push(tile("RYOE", `${ryoe > 0 ? "+" : ""}${Math.round(ryoe)}`, "NGS"));
    else t.push(tile("1st downs", line.first));
    return `<div class="cc-tiles">${t.join("")}</div>`;
  }
  function legendHTML(sport, anyNoHole) {
    const f = sport === "nfl" ? "Fumble lost" : "Fumbled";
    return `<div class="cc-legend" aria-hidden="true">
      <span><i class="sw loss"></i>Tackled for loss</span><span><i class="sw short"></i>0–4 yds</span>
      <span><i class="sw gain"></i>5+ yds / TD</span><span><i class="mk td"></i>Touchdown</span>
      <span><i class="mk fum"></i>${f}</span>${anyNoHole ? `<span><i class="sw nohole"></i>Hole not recorded</span>` : ""}</div>`;
  }
  /* EVERY CARRY AS A TABLE (the render's "EVERY CARRY (16)"): its number,
     the quarter and clock, the yard line with the down under it, the
     hole, the yards and how it ended. A row is one button, so a tap on
     it finds its line on the field; its label reads the whole play in
     words, the way the cells read it at a glance. `data-f` is what the
     table's filter matches. A run that ended short of a first down is a
     gain, no gain or a loss, never "tackle": the play-by-play does not
     say how it ended beyond the yards. */
  function carryResult(c, sport) {
    const out = [];
    if (c.td) out.push(["Touchdown", "good"]);
    if (c.fl) out.push([sport === "nfl" ? "Fumble lost" : "Fumbled", "bad"]);
    if (c.fd && !c.td) out.push(["1st down", "gold"]);
    if (!out.length) out.push(c.y < 0 ? ["Loss", "bad"] : c.y === 0 ? ["No gain", "mute"] : ["Gain", "mute"]);
    return out;
  }
  const carryFlags = (c) => [c.y >= 5 ? "big" : "", c.y < 0 ? "loss" : "", c.fd || c.td ? "fd" : "", c.td ? "td" : "",
                             c.sc ? "sc" : "", c.fl ? "fum" : ""].filter(Boolean).join(" ");
  const pills = (xs) => xs.map(([w, k]) => `<em class="cc-pill ${k}">${esc(w)}</em>`).join("");
  function listHTML(g, sport) {
    return `<div class="cc-list cc-table cc-runs" role="list">
      <div class="cc-lh" aria-hidden="true"><span>#</span><span>Qtr</span><span>Yard line</span><span>Dir</span><span class="r">Yards</span><span>Result</span></div>
      ${(g.carries || []).map((c, i) => {
      const res = carryResult(c, sport).concat(c.sc ? [["Scramble", "tag"]] : []);
      const hole = c.h ? HOLE_NAME[c.h] : (sport === "nfl" ? "Hole not recorded" : "");
      const said = [qLabel(c), [downDist(c), spot(c, g)].filter(Boolean).join(" · "), hole, `${signed(c.y)} yds`,
                    ...res.map(([w]) => w)].filter(Boolean).join(", ");
      return `<button type="button" role="listitem" class="cc-row cc-tr${S && S.sel === i ? " sel" : ""}" data-i="${i}" data-f="${carryFlags(c)}" aria-label="${esc(said)}">
        <span class="cc-c-n">${i + 1}</span>
        <span class="cc-c-q">${esc(qLabel(c) || "—")}</span>
        <span class="cc-c-yl">${esc(spot(c, g) || "—")}<small>${esc(downDist(c))}</small></span>
        <span class="cc-c-dir">${c.h ? `<span class="lg">${esc(hole)}</span><span class="sh">${esc(c.h)}</span>` : "—"}</span>
        <b class="cc-c-y ${c.band}">${signed(c.y)}</b>
        <span class="cc-c-res">${pills(res)}</span>
      </button>`;
    }).join("")}</div>`;
  }
  /* EVERY PLAY AS THE RENDERS' TABLE, in every league (2026-10-14): a
     league's module names its columns — each a heading, its cell's class,
     its width on a phone (`p`) and on a wide card (`w`), and none where it
     is not shown — and hands a row per play: its cells (markup it has
     already escaped; [markup, class] for a coloured one), the words its
     label reads the whole play in, and the tokens its filter matches. The
     widths ride the table as two custom properties, so each league's
     columns are written once, beside the cells that fill them; every row
     is one button, as the carry and target tables' are. */
  //: A row's `more` is a line under its cells, across the row (an at-bat's pitches).
  function gridHTML(name, cols, rows) {
    const where = (c) => `${c.p ? "" : " cc-wo"}${c.w ? "" : " cc-po"}`;
    const tpl = (k) => cols.filter((c) => c[k]).map((c) => c[k]).join(" ");
    return `<div class="cc-list cc-table cc-grid cc-g-${name}" role="list" style="--cc-p:${tpl("p")};--cc-w:${tpl("w")}">
      <div class="cc-lh" aria-hidden="true">${cols.map((c) => `<span class="${c.r ? "r" : ""}${where(c)}">${esc(c.h)}</span>`).join("")}</div>
      ${rows.map((r) => `<button type="button" role="listitem" class="cc-row cc-tr${S && S.sel === r.i ? " sel" : ""}" data-i="${r.i}"${r.f == null ? "" : ` data-f="${esc(r.f)}"`} aria-label="${esc(r.said)}">${r.cells.map((x, j) => {
        const [html, more] = Array.isArray(x) ? x : [x, ""];
        return `<span class="${cols[j].c}${more ? ` ${more}` : ""}${where(cols[j])}">${html}</span>`;
      }).join("")}${r.more ? `<span class="cc-c-more">${r.more}</span>` : ""}</button>`).join("")}</div>`;
  }
  //: A cell of two lines: the play, and under it its detail.
  const two = (main, sub) => `<b>${esc(main || "—")}</b>${sub ? `<small>${esc(sub)}</small>` : ""}`;
  function tableHTML(cap, head, rows) {
    return `<div class="cc-tbl-wrap"><table class="cc-tbl"><caption>${esc(cap)}</caption>
      <thead><tr>${head.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((r) => `<tr>${r.map((v, j) => j ? `<td>${esc(v)}</td>` : `<th scope="row">${esc(v)}</th>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function seasonTables(d) {
    const out = [];
    const L = (x) => [x.n, num1(x.ypc), pct(x.success), x.explosive, x.td];
    if (d.holes && d.by_hole.length) {
      out.push(tableHTML("Where he runs — by hole", ["Hole", "Carries", "Share", "Yds/carry", "Success", "10+ yds", "TD"],
        d.by_hole.filter((h) => h.n).map((h) => [h.name, h.n, pct(h.share), num1(h.ypc), pct(h.success), h.explosive, h.td])));
    }
    if (d.kinds && d.kinds.designed) {
      out.push(tableHTML("Designed runs and scrambles", ["Kind", "Carries", "Yds/carry", "Success", "10+ yds", "TD"],
        [["Designed runs", ...L(d.kinds.designed)], ["Scrambles", ...L(d.kinds.scramble)]]));
    }
    if (d.by_down.length) {
      out.push(tableHTML("By down", ["Down", "Carries", "Yds/carry", "Success", "10+ yds", "TD"],
        d.by_down.map((x) => [ord(x.down), ...L(x)])));
    }
    const zones = d.by_zone.filter((z) => z.n);
    if (zones.length) {
      out.push(tableHTML("By field position", ["Where", "Carries", "Yds/carry", "Success", "10+ yds", "TD"],
        zones.map((z) => [z.name, ...L(z)])));
    }
    return out.join("");
  }
  function ngsLine(d) {
    const n = d.ngs || {};
    if (n.ryoe == null) return "";
    const bits = [`${n.ryoe > 0 ? "+" : ""}${Math.round(n.ryoe)} rushing yards over expected (${n.ryoe_per_att > 0 ? "+" : ""}${num1(n.ryoe_per_att)} a carry)`];
    if (n.eight_box != null) bits.push(`8+ in the box on ${Math.round(n.eight_box)}% of his carries`);
    if (n.time_to_los != null) bits.push(`${Number(n.time_to_los).toFixed(2)}s to the line`);
    return `<p class="cc-ngs"><b>Next Gen Stats, ${esc(d.season)}:</b> ${esc(bits.join(" · "))}.</p>`;
  }
  function noteHTML(d) {
    return d.holes
      ? `<p class="cc-note">Each line runs from the backfield through the hole the NFL’s play-by-play records to where the carry ended — the hole and the yards are the record. The league’s player-tracking paths aren’t published, so the bend into the hole is drawn, not tracked. Scrambles start from the pocket. RYOE is the NFL’s Next Gen Stats number, published for running backs with 10+ carries in a game.</p>`
      : `<p class="cc-note">College play-by-play doesn’t record which hole a run went through, so each carry is drawn straight from behind the line to where it ended — across the field in the order they happened (a game) or shortest to longest (the season). A college fumble is marked fumbled: the file doesn’t say who recovered it.</p>`;
  }

  /* ---------------- the route chart's page ---------------- */
  function routeTiles(line, ngs) {
    const t = [tile("Targets", line.tgt), tile("Receptions", line.rec), tile("Yards", Math.round(line.yds)),
               tile("TD", line.td), tile("YAC", Math.round(line.yac)), tile("aDOT", num1(line.adot))];
    // Separation where the league published it (5+ targets in a game);
    // first downs where it did not — never an estimate in its place.
    if (ngs && ngs.separation != null) t.push(tile("Separation", `${num1(ngs.separation)}`, "NGS · yds"));
    else t.push(tile("1st downs", line.first));
    return `<div class="cc-tiles cc-tiles-7">${t.join("")}</div>`;
  }
  function routeLegend(charted, season) {
    if (season) {
      return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Caught</span>
        <span><i class="dt m"></i>Incomplete</span><span><i class="dt i"></i>Intercepted</span>
        <span><i class="sw cell"></i>Share of his targets</span></div>`;
    }
    return `<div class="cc-legend" aria-hidden="true">
      <span><i class="sw ${charted ? "route" : "throw"}"></i>${charted ? "Route" : "Throw"}</span>
      <span><i class="sw miss"></i>Incomplete</span><span><i class="sw yac"></i>After the catch</span>
      <span><i class="mk td"></i>Touchdown</span><span><i class="mk int">×</i>Interception</span></div>`;
  }
  function airWords(t) {
    if (t.ay == null) return SIDE_WORD[t.s] || "";
    const a = Math.round(t.ay);
    return `${a < 0 ? "−" + Math.abs(a) : a} air yds${t.s ? `, ${SIDE_WORD[t.s]}` : ""}`;
  }
  const FTN_TAG = { "screen": "Screen", "play action": "Play action", "contested": "Contested", "drop": "Drop",
                    "created": "Made the catch", "not catchable": "Not catchable" };
  function covWords(t) {
    return [t.cov ? (t.cov === "man" ? "Man" : "Zone") : "", t.sh].filter(Boolean).join(" · ");
  }
  /* EVERY TARGET AS A TABLE (the render's "EVERY TARGET (8)"): its
     number, the quarter, the route the league charted, how far past the
     line, which third, caught or not, the yards and the yards after. A
     college target has no depth or side on file, so its table has
     neither column. On a phone the route, depth and side read as one
     cell over the quarter and the yard line. */
  const targetFlags = (t) => [t.int ? "int" : t.c ? "c" : "inc", t.fd || t.td ? "fd" : "", t.td ? "td" : ""]
    .filter(Boolean).join(" ");
  function routeList(g) {
    const ts = g.targets || [];
    const air = ts.some((t) => t.ay != null || BAND[t.s]), routed = ts.some((t) => t.rt);
    return `<div class="cc-list cc-table cc-tgts${air ? "" : " noair"}" role="list">
      <div class="cc-lh" aria-hidden="true"><span>#</span><span>Qtr</span><span>${air ? (routed ? "Route" : "Down") : "Yard line"}</span>${air
        ? '<span class="r">Depth</span><span>Side</span>' : ""}<span>Result</span><span class="r">Yds</span><span class="r">YAC</span></div>
      ${ts.map((t, i) => {
      const yac = t.c ? Math.round(yacOf(t)) : 0;
      const band = t.int ? "loss" : t.c ? "gain" : "miss";
      const res = [t.int ? ["INT", "bad"] : t.c ? ["Catch", "good"] : ["Inc", "mute"]]
        .concat(t.td ? [["TD", "good"]] : [], t.fd && !t.td ? [["1st down", "gold"]] : [],
                (t.fl || []).filter((w) => FTN_TAG[w]).map((w) => [FTN_TAG[w], "tag"]));
      const how = [ROUTE_NAME[t.rt] || "", airWords(t)].filter(Boolean).join(" · ") || zoneWord(t);
      const where = [downDist(t), spot(t, g)].filter(Boolean).join(" · ");
      const said = [qLabel(t), where, how, covWords(t), t.int ? "intercepted" : t.c ? `caught, ${signed(t.y)} yds` : "incomplete",
                    t.c && yac ? `${yac} yd${Math.abs(yac) === 1 ? "" : "s"} after catch` : "",
                    ...res.slice(1).map(([w]) => w)].filter(Boolean).join(", ");
      const depth = t.ay == null ? "—" : `${Math.round(t.ay)}`;
      return `<button type="button" role="listitem" class="cc-row cc-tr${S && S.sel === i ? " sel" : ""}" data-i="${i}" data-f="${targetFlags(t)}" aria-label="${esc(said)}">
        <span class="cc-c-n">${i + 1}</span>
        <span class="cc-c-q">${esc(qLabel(t) || "—")}</span>
        <span class="cc-c-rt">${!air
          ? `${esc(spot(t, g) || "—")}<small>${esc([downDist(t), zoneWord(t)].filter(Boolean).join(" · "))}</small>`
          : routed ? `${esc(ROUTE_NAME[t.rt] || t.rt || "—")}<small>${esc(covWords(t) || where)}</small>`
            : `${esc(downDist(t) || "—")}<small>${esc(spot(t, g))}</small>`}</span>
        ${air ? `<span class="cc-c-dp">${esc(depth)}</span><span class="cc-c-sd">${esc(cap(SIDE_WORD[t.s]) || "—")}</span>` : ""}
        <span class="cc-c-res">${pills(res)}</span>
        <b class="cc-c-y ${band}">${t.c ? signed(t.y) : "—"}</b>
        <span class="cc-c-yac">${t.c ? yac : "—"}</span>
        <span class="cc-c-m"><b>${esc(how || where || "—")}</b><small>${esc([qLabel(t), how ? where : ""].filter(Boolean).join(" · "))}</small></span>
      </button>`;
    }).join("")}</div>`;
  }
  /* Sums of engine/targets._line rows — a depth band across its thirds,
     or a third down its depths. */
  function sumLines(xs) {
    const o = { tgt: 0, rec: 0, yds: 0, td: 0, yac: 0 };
    xs.forEach((x) => { o.tgt += x.tgt; o.rec += x.rec; o.yds += x.yds; o.td += x.td; o.yac += x.yac; });
    o.catch = o.tgt ? o.rec / o.tgt : null;
    o.ypt = o.tgt ? o.yds / o.tgt : null;
    return o;
  }
  function routeTables(d) {
    const out = [];
    const total = d.season_line.tgt || 0;
    const L = (x) => [x.tgt, pct(total ? x.tgt / total : null), pct(x.catch), num1(x.ypt), x.td];
    const head = (first) => [first, "Tgts", "Share", "Catch", "Yds/tgt", "TD"];
    const depth = DEPTH.map(([k, name]) => [name, sumLines(d.by_zone.filter((z) => z.depth === k))]).filter(([, x]) => x.tgt);
    if (depth.length) out.push(tableHTML("How far past the line", head("Air yards"), depth.map(([n, x]) => [n, ...L(x)])));
    const sides = ["L", "M", "R"].map((k) => [k, sumLines(d.by_zone.filter((z) => z.side === k))]).filter(([, x]) => x.tgt);
    if (sides.length) out.push(tableHTML("Which third of the field", head("Third"),
      sides.map(([k, x]) => [SIDE_WORD[k][0].toUpperCase() + SIDE_WORD[k].slice(1), ...L(x)])));
    if (d.by_route && d.by_route.length) {
      out.push(tableHTML("By route — the league’s charting", head("Route"),
        d.by_route.map((x) => [ROUTE_NAME[x.route] || x.route, ...L(x)])));
    }
    if (d.by_cov && d.by_cov.length) {
      out.push(tableHTML("Against man and zone", head("Coverage"),
        d.by_cov.map((x) => [x.coverage === "man" ? "Man" : "Zone", ...L(x)])));
    }
    if (d.by_shell && d.by_shell.length) {
      out.push(tableHTML("By coverage shell", head("Shell"), d.by_shell.map((x) => [x.shell, ...L(x)])));
    }
    if (d.by_down && d.by_down.length) {
      out.push(tableHTML("By down", head("Down"), d.by_down.map((x) => [ord(x.down), ...L(x)])));
    }
    if (d.by_field && d.by_field.length) {
      out.push(tableHTML("By field position", head("Where"), d.by_field.map((x) => [x.name, ...L(x)])));
    }
    return out.join("");
  }
  function routeNgs(d) {
    const n = d.ngs || {};
    if (n.separation == null) return "";
    const bits = [`${num1(n.separation)} yds of separation when the ball arrived`];
    if (n.cushion != null) bits.push(`${num1(n.cushion)} yds of cushion at the snap`);
    if (n.intended_air != null) bits.push(`${num1(n.intended_air)} intended air yards a target`);
    if (n.air_share != null) bits.push(`${Math.round(n.air_share)}% of his team’s air yards`);
    if (n.yac_over != null) bits.push(`${n.yac_over > 0 ? "+" : ""}${num1(n.yac_over)} yards after the catch over expected a catch`);
    return `<p class="cc-ngs"><b>Next Gen Stats, ${esc(d.season)}:</b> ${esc(bits.join(" · "))}.</p>`;
  }
  function routeNote(d) {
    const where = "How far past the line the ball went (air yards) and which third of the field it went to are the NFL play-by-play’s record; where inside that third is spread so no two sit on one another. Green is the run after the catch, as long as the record says, drawn straight upfield.";
    const how = d.routes
      ? "Each route is the one the NFL charted for that target (nflverse’s participation data), drawn in that route’s shape to where the ball arrived — the kind of route is the record; its stem and break are drawn, not tracked."
      : `Each line is the throw, from the pocket to where the ball arrived. The league’s route charting for ${esc(d.season)} isn’t published yet (nflverse publishes it a season behind — through 2025 so far), and we don’t guess routes: the likeliest route for a target’s depth and side matched the league’s charting 43% of the time.`;
    return `<p class="cc-note">${how} ${where} Separation is the NFL’s Next Gen Stats number, published for receivers with 5+ targets in a game. Screen, play action, contested, drop and catchable are FTN’s charting.</p>`;
  }

  /* ---------------- college targets (2026-10-13) ----------------
     The college play file names who was thrown at, whether he caught it,
     the yards, the down and the yards to the goal — and nothing about how
     far the ball travelled or to which side. So a college target is drawn
     the way a college carry is: straight upfield from the line, across
     the field in the order they were thrown (a game) or shortest to
     longest (the season); a catch as long as its yards, a miss a ring at
     the line. */
  const zoneWord = (t) => (t.yl == null ? "" : t.yl <= 5 ? "Goal line" : t.yl <= 20 ? "Red zone" : "");
  function cfbTargetMarks(ts, xOf, ymax) {
    let body = "";
    ts.forEach(([t, i], j) => {
      const x = xOf(j), cls = S && S.sel === i ? " sel" : "";
      if (!t.c) {
        const c = proj(x, 0.6, ymax);
        body += `<g class="cc-carry" data-i="${i}"><path class="cc-hit" d="M${c[0].toFixed(1)} ${(c[1] - 6).toFixed(1)} v12"/>
          <circle class="rc-miss cx-mark${cls}" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="4"/></g>`;
        return;
      }
      const ey = clampY(t.y, ymax), pts = [[x, 0], [x, ey]];
      const end = proj(x, ey, ymax);
      body += `<g class="cc-carry" data-i="${i}"><path class="cc-hit" d="${pathD(pts, ymax)}"/>
        <path class="rc-route${cls}" d="${pathD(pts, ymax)}" pathLength="1" style="animation-delay:${Math.min(j * 45, 900)}ms"/>
        <circle class="rc-catch" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="3.4"/>
        ${t.td ? `<circle class="cc-td" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="7"/>` : ""}</g>`;
      if (t.y > ymax) body += longTag(x, ymax, t.y);
    });
    return body;
  }
  function cfbTargetGame(g) {
    const ts = (g.targets || []).map((t, i) => [t, i]);
    const ymax = yMaxFor(ts.map(([t]) => (t.c ? t.y : 0)));
    const n = ts.length, ticks = [];
    let lastQ = null;
    ts.forEach(([t], j) => {
      const x = -20 + 40 * (j + 0.5) / Math.max(1, n);
      if (t.q !== lastQ) { ticks.push([x - 1.2, t.q > 4 ? "OT" : `Q${t.q || "?"}`]); lastQ = t.q; }
    });
    return svgWrap(fieldSVG(ymax, [], ticks) + cfbTargetMarks(ts, (j) => -20 + 40 * (j + 0.5) / Math.max(1, n), ymax),
                   g, "cfb", n, "targets");
  }
  function cfbTargetSeason(d) {
    const every = [];
    d.games.forEach((g) => (g.targets || []).forEach((t) => every.push(t)));
    if (!every.length) return "";
    const sorted = every.map((t, i) => [t, -1 - i]).sort((a, b) => (a[0].c ? a[0].y : -99) - (b[0].c ? b[0].y : -99));
    const ymax = yMaxFor(sorted.map(([t]) => (t.c ? t.y : 0)));
    const n = sorted.length;
    let body = cfbTargetMarks(sorted, (j) => -22 + 44 * (j + 0.5) / n, ymax);
    const L = d.season_line, avg = L.rec ? L.yds / L.rec : 0;
    const a = proj(-SIDE, clampY(avg, ymax), ymax), b = proj(SIDE, clampY(avg, ymax), ymax);
    // The average on the left, over the misses, where no catch is drawn.
    body += `<line class="cc-avg" x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}"/>
      <text class="cc-raylbl" x="${(a[0] + 6).toFixed(1)}" y="${(a[1] - 6).toFixed(1)}">${num1(avg)} a catch</text>`;
    return svgWrap(fieldSVG(ymax, [], [[-22, "Misses"], [15, "Longest"]]) + body, null, "cfb", n, "targets");
  }
  function cfbTargetTiles(line) {
    const t = [tile("Targets", line.tgt), tile("Receptions", line.rec), tile("Yards", Math.round(line.yds)),
               tile("TD", line.td), tile("Yds/catch", line.rec ? num1(line.yds / line.rec) : "—"),
               tile("Catch rate", pct(line.catch)), tile("1st downs", line.first)];
    return `<div class="cc-tiles cc-tiles-7">${t.join("")}</div>`;
  }
  const redZone = (d) => (d.by_field || []).filter((z) => z.zone === "rz" || z.zone === "gl").reduce((a, z) => a + z.tgt, 0);
  function cfbTargetLegend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="sw route"></i>Caught, to where he was down</span>
      <span><i class="dt m"></i>Incomplete</span><span><i class="mk td"></i>Touchdown</span></div>`;
  }
  function cfbTargetNote(d) {
    return `<p class="cc-note">The college play file records who was thrown at, whether he caught it, the yards, the down and where the play started — not how far the ball travelled or to which side of the field — so each target is drawn straight upfield from the line: a catch as long as the yards it gained, an incompletion as a ring at the line. A game runs left to right in the order they were thrown; the season, shortest to longest. The file names the intended receiver on 92% of 2026’s incompletions and 78% of 2025’s; a miss it doesn’t name, and every interception (it never names that receiver), isn’t here, so his true target count can run a little higher. Seasons before 2025 name too few misses to draw, and a week the file lost its scoring plays from is left out, as it is from his game log.</p>`;
  }

  /* ---------------- the passing chart (2026-10-13) ----------------
     A passer's throws, the route chart turned round: each from the
     pocket to where the ball arrived — its third of the field and its
     air yards are the play-by-play's record — the run after the catch in
     green, and the sacks he took marked behind him. A spiked ball is an
     incomplete attempt, as in the box score: listed, not drawn. */
  const PASS_TAG = { "play action": "Play action", "screen": "Screen", "out of pocket": "Out of pocket",
                     "throwaway": "Throwaway", "should have been picked": "Should’ve been picked",
                     "drop": "Dropped", "blitz": "Blitzed" };
  const passBand = (t) => (t.k === "sack" || t.int ? "loss" : t.k === "pass" && t.c ? "gain" : "miss");
  const passRes = (t) => (t.k === "sack" ? `Sack ${signed(t.y)}` : t.k === "spike" ? "Spike"
    : t.int ? "INT" : t.c ? signed(t.y) : "Inc");
  const slash = (a, b) => `${a}/${b}`;
  const passChip = (g) => `${slash(g.line.cmp, g.line.att)} · ${Math.round(g.line.yds)}`;
  function passGameChart(g) {
    const ts = g.throws || [];
    const thrown = ts.map((t, i) => [t, i]).filter(([t]) => t.k === "pass");
    const ymax = yMaxFor(thrown.map(([t]) => (t.ay || 0) + Math.max(0, yacOf(t))));
    const xs = catchXs(thrown.map(([t]) => t));
    let body = qbMark(ymax);
    thrown.forEach(([t, i], j) => {
      body += targetSVG(i, t, xs[j], ymax, outward(xs[j], j));
      const far = (t.ay || 0) + Math.max(0, yacOf(t));
      if (far > ymax) body += longTag(xs[j], ymax, far);
    });
    /* The sacks in a row behind him, to his left — clear of his label on
       the right and the thirds' names under the field. */
    const sacks = ts.map((t, i) => [t, i]).filter(([t]) => t.k === "sack");
    sacks.forEach(([t, i], j) => {
      const c = proj(-3.4 - (j % 6) * 3.2, POCKET - 1.4 - Math.floor(j / 6) * 1.6, ymax);
      const d = `M${(c[0] - 5).toFixed(1)} ${(c[1] - 5).toFixed(1)} l10 10 m0 -10 l-10 10`;
      body += `<g class="cc-carry" data-i="${i}"><path class="cc-hit" d="${d}"/>
        <path class="rc-sack cx-mark${S && S.sel === i ? " sel" : ""}" d="${d}"/></g>`;
    });
    return svgWrap(fieldSVG(ymax, THIRDS) + body, g, "nfl", thrown.length, "throws");
  }
  /* The season, where he throws: the field in thirds and depth bands,
     each shaded by its share of his attempts and labelled with his
     completions in it, and every throw a dot where its ball arrived. */
  function passSeasonChart(d) {
    const every = [];
    d.games.forEach((g) => (g.throws || []).forEach((t) => { if (t.k === "pass") every.push(t); }));
    if (!every.length) return "";
    const ymax = yMaxFor(every.map((t) => Math.min(t.ay || 0, 38)).concat([22]));
    const rows = { behind: [-7, 0], short: [0, 10], mid: [10, 20], deep: [20, ymax] };
    const most = Math.max(1, ...d.by_zone.map((z) => z.att));
    let cells = "", labels = "";
    d.by_zone.forEach((z) => {
      const [y0, y1] = rows[z.depth] || [0, 0], [x0, x1] = THIRD[z.side] || THIRD.M;
      const yb = Math.max(YMIN + 0.4, y0), yt = Math.min(ymax, y1);
      if (yt <= yb) return;
      const poly = [proj(x0, yb, ymax), proj(x1, yb, ymax), proj(x1, yt, ymax), proj(x0, yt, ymax)];
      const op = z.att ? (0.1 + 0.45 * z.att / most).toFixed(2) : "0";
      cells += `<polygon class="rc-cell" points="${poly.map(pt).join(" ")}" style="fill-opacity:${op}"/>`;
      if (!z.att) return;
      const m = proj((x0 + x1) / 2, (yb + yt) / 2, ymax);
      labels += `<text class="cc-raylbl rc-lbl" x="${m[0].toFixed(1)}" y="${(m[1] - 2).toFixed(1)}" text-anchor="middle">${pct(z.att / every.length)}</text>
        <text class="cc-raysub rc-lbl" x="${m[0].toFixed(1)}" y="${(m[1] + 14).toFixed(1)}" text-anchor="middle">${z.cmp}/${z.att}</text>`;
    });
    const xs = catchXs(every);
    let dots = "";
    every.forEach((t, i) => {
      const c = proj(xs[i], Math.max(-8.2, clampY(t.ay == null ? 0 : t.ay, ymax)), ymax);
      dots += `<circle class="rc-dot ${t.int ? "i" : t.c ? "c" : "m"}" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="2.8"/>`;
    });
    return svgWrap(fieldSVG(ymax, THIRDS) + cells + dots + labels, null, "nfl", every.length, "throws");
  }
  /* Time to throw where the league published it (a passer past its
     minimum in a game); the sacks he took where it did not. */
  function passTiles(line, ngs) {
    const t = [tile("Cmp/Att", slash(line.cmp, line.att)), tile("Yards", Math.round(line.yds)),
               tile("TD–INT", `${line.td}–${line.int}`), tile("Yds/att", num1(line.ypa)), tile("aDOT", num1(line.adot))];
    if (ngs && ngs.time_to_throw != null) t.push(tile("Throw time", `${Number(ngs.time_to_throw).toFixed(2)}s`, "NGS"));
    else t.push(tile("Sacked", line.sk ? `${line.sk} (${signed(line.sk_yds)})` : "0"));
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function passLegend(season) {
    if (season) {
      return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Complete</span>
        <span><i class="dt m"></i>Incomplete</span><span><i class="dt i"></i>Intercepted</span>
        <span><i class="sw cell"></i>Share of his attempts</span></div>`;
    }
    return `<div class="cc-legend" aria-hidden="true"><span><i class="sw throw"></i>Throw</span>
      <span><i class="sw miss"></i>Incomplete</span><span><i class="sw yac"></i>After the catch</span>
      <span><i class="mk td"></i>Touchdown</span><span><i class="mk int">×</i>Interception · sack</span></div>`;
  }
  function passWords(t) {
    if (t.k === "sack") return "Sacked";
    if (t.k === "spike") return "Spiked to stop the clock";
    const air = t.ay == null ? (SIDE_WORD[t.s] || "") : airWords(t);
    return [air, t.to ? `to ${t.to}` : "nobody targeted"].filter(Boolean).join(" · ");
  }
  function passTags(t) {
    const yac = t.k === "pass" && t.c ? Math.round(yacOf(t)) : 0;
    return [t.td ? "TD" : "", t.fd && !t.td ? "1st down" : "",
            yac ? `${yac} yd${Math.abs(yac) === 1 ? "" : "s"} after catch` : "",
            t.hit && t.k === "pass" ? "Hit" : "", t.fum ? "Fumble lost" : "",
            ...(t.fl || []).map((w) => PASS_TAG[w] || "")].filter(Boolean);
  }
  function passList(g) {
    return `<div class="cc-list" role="list">${(g.throws || []).map((t, i) => {
      const band = passBand(t), tags = passTags(t);
      return `<button type="button" role="listitem" class="cc-row${S && S.sel === i ? " sel" : ""}" data-i="${i}">
        <i class="dot ${band}"></i>
        <span class="cc-r-q">${esc(qLabel(t))}</span>
        <span class="cc-r-dd">${esc([downDist(t), spot(t, g)].filter(Boolean).join(" · "))}</span>
        <span class="cc-r-h">${esc(passWords(t))}</span>
        <b class="cc-r-y ${band}">${esc(passRes(t))}</b>
        ${tags.length ? `<span class="cc-r-tags">${tags.map((x) => `<em>${esc(x)}</em>`).join("")}</span>` : ""}
      </button>`;
    }).join("")}</div>`;
  }
  //: Sums of engine/passes._line rows — a depth band across its thirds, or a third down its depths.
  function sumPass(xs) {
    const o = { att: 0, cmp: 0, yds: 0, td: 0, int: 0, sk: 0 };
    xs.forEach((x) => { o.att += x.att; o.cmp += x.cmp; o.yds += x.yds; o.td += x.td; o.int += x.int; o.sk += x.sk; });
    o.pct = o.att ? o.cmp / o.att : null;
    o.ypa = o.att ? o.yds / o.att : null;
    return o;
  }
  function passTables(d) {
    const out = [], total = d.season_line.att || 0;
    const L = (x) => [x.att, pct(total ? x.att / total : null), pct(x.pct), num1(x.ypa), x.td, x.int];
    const head = (first) => [first, "Att", "Share", "Cmp %", "Yds/att", "TD", "INT"];
    const depth = DEPTH.map(([k, name]) => [name, sumPass(d.by_zone.filter((z) => z.depth === k))]).filter(([, x]) => x.att);
    if (depth.length) out.push(tableHTML("How far past the line", head("Air yards"), depth.map(([n, x]) => [n, ...L(x)])));
    const sides = ["L", "M", "R"].map((k) => [k, sumPass(d.by_zone.filter((z) => z.side === k))]).filter(([, x]) => x.att);
    if (sides.length) out.push(tableHTML("Which third of the field", head("Third"),
      sides.map(([k, x]) => [SIDE_WORD[k][0].toUpperCase() + SIDE_WORD[k].slice(1), ...L(x)])));
    const P = (x) => [x.att, pct(x.pct), num1(x.ypa), x.td, x.int, x.sk];
    const head2 = (first) => [first, "Att", "Cmp %", "Yds/att", "TD", "INT", "Sacked"];
    if (d.by_pressure && d.by_pressure.length) {
      out.push(tableHTML("Kept clean, hit, blitzed, play action", head2("When"),
        d.by_pressure.filter((x) => x.att || x.sk).map((x) => [x.when, ...P(x)])));
    }
    if (d.by_down && d.by_down.length) out.push(tableHTML("By down", head2("Down"), d.by_down.map((x) => [ord(x.down), ...P(x)])));
    if (d.by_target && d.by_target.length) {
      out.push(tableHTML("Who he threw to", ["Receiver", "Tgts", "Rec", "Yds", "TD", "INT"],
        d.by_target.map((x) => [x.to, x.tgt, x.rec, Math.round(x.yds), x.td, x.int])));
    }
    return out.join("");
  }
  function passNgs(d) {
    const n = d.ngs || {};
    if (n.time_to_throw == null) return "";
    const bits = [`${Number(n.time_to_throw).toFixed(2)}s to throw`];
    if (n.cpoe != null) bits.push(`${n.cpoe > 0 ? "+" : ""}${num1(n.cpoe)}% completion over expected`);
    if (n.aggressiveness != null) bits.push(`${num1(n.aggressiveness)}% of throws into a tight window`);
    if (n.intended_air != null) bits.push(`${num1(n.intended_air)} intended air yards a throw`);
    return `<p class="cc-ngs"><b>Next Gen Stats, ${esc(d.season)}:</b> ${esc(bits.join(" · "))}.</p>`;
  }
  function passNote() {
    return `<p class="cc-note">Each line is a throw, from the pocket to where the ball arrived. How far past the line it went (air yards) and which third of the field it went to are the NFL play-by-play’s record; where inside that third is spread so no two sit on one another. Green is the run after the catch, as long as the record says. Sacks are marked behind him with the yards lost. A spiked ball counts as an incomplete attempt, as in the box score, and isn’t drawn. Play action, screens, out of the pocket, throwaways, drops, blitzes (5+ rushers) and balls that should have been intercepted are FTN’s charting (2022 on). Time to throw and completion over expected are the NFL’s Next Gen Stats, published for passers past the league’s minimum in a game.</p>`;
  }
  DRAW.passes = {
    one: "dropback", splitsTitle: "Every split · depth, side, pressure, down, receiver",
    items: (g) => g.throws || [],
    count: (L) => `${L.att} attempts`,
    chip: passChip,
    game: (g) => passGameChart(g),
    season: (d) => passSeasonChart(d),
    gameSide: (g) => `${passLegend(false)}${passTiles(g.line, g.ngs)}`,
    seasonSide: (d) => {
      const L = d.season_line;
      return `${passLegend(true)}${passTiles(L, d.ngs)}
        <div class="cc-tiles cc-tiles-2">${tile("Completion", pct(L.pct))}${tile("Deep (20+)", `${L.deep_cmp} of ${L.deep}`)}${tile("Sacked", `${L.sk} (${signed(L.sk_yds)})`)}${tile("Throwaways", L.away)}</div>
        ${passNgs(d)}`;
    },
    list: (g) => passList(g),
    splits: (d) => passTables(d),
    note: () => passNote(),
    tip: (t, g) => `<b class="${passBand(t)}">${t.k === "sack" ? `Sacked, ${signed(t.y)} yds` : t.k === "spike" ? "Spiked"
      : t.int ? "Intercepted" : t.c ? `${signed(t.y)} yds` : "Incomplete"}</b>${t.td ? " · TD" : ""}
      <span>${esc([qLabel(t), downDist(t), spot(t, g), passWords(t)].filter(Boolean).join(" · "))}</span>`,
  };

  /* ---------------- the page's frame (2026-10-14) ----------------
     Ethan, with two renders of this page (a back's carries, a receiver's
     targets): "I like how it has the stadium art behind the team logos.
     And I like how much better the charts and shit look in this page
     look. So follow these renders for how our pages should look." Every
     chart now sits in that frame: the game over its stadium with both
     teams' logos and colours, his charts as chips with their counts, the
     views as tabs, the games in a row with arrows, the drawing in a card
     with its side-of-the-field filter and counts, the numbers as icon
     tiles, and every play in a table that filters and downloads. */
  const HEX = /^#[0-9a-fA-F]{3,8}$/;
  function teamOf(sport, a) {
    const T = typeof teamsIn === "function" && a ? teamsIn(sport) : null;
    return (T && T[a]) || {};
  }
  //: A team's colour, only as the team data spells one (it goes in a style).
  const inkOf = (sport, a) => { const p = teamOf(sport, a).primary; return HEX.test(p || "") ? p : ""; };
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  //: One side of the game: the logo, the city over the name, the record.
  function heroTeam(sport, a, rec, right) {
    const t = teamOf(sport, a);
    const nick = t.nick || teamNameIn(sport, a) || a;
    const loc = t.loc || (t.name && t.name !== nick && t.name.endsWith(nick) ? t.name.slice(0, -nick.length).trim() : "");
    const mark = `<span class="cc-hero-logo">${teamMarkIn(sport, a, 56)}</span>`;
    const words = `<span class="cc-hero-name">${loc ? `<small>${esc(loc)}</small>` : ""}<b>${esc(nick)}</b>${rec
      ? `<i>${esc(rec)}</i>` : ""}</span>`;
    return `<div class="cc-hero-team${right ? " r" : ""}">${right ? words + mark : mark + words}</div>`;
  }
  /* The week and the day between them, and the final where the games
     table has one (engine/carries.scoreboard): his team's score first. */
  function heroMid(g) {
    // Tonight's opponent (the matchup view): no day, no final yet.
    if (g.tonight) {
      return `<div class="cc-hero-mid"><small>Tonight</small><b class="cc-hero-vs">VS</b>${g.label
        ? `<span>${esc(g.label)}</span>` : ""}</div>`;
    }
    const when = g.week ? (ROUNDS[g.week] || `Week ${g.week}`) : "";
    const dt = g.date ? new Date(g.date + "T12:00:00") : null;
    const day = dt && !isNaN(dt) ? dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
    const sc = Array.isArray(g.score) && g.score.length === 2 && g.score.every((x) => x != null) ? g.score : null;
    const won = sc ? (sc[0] > sc[1] ? "w" : sc[0] < sc[1] ? "l" : "t") : "";
    return `<div class="cc-hero-mid">${when ? `<small>${esc(when)}</small>` : ""}${day ? `<span>${esc(day)}</span>` : ""}${sc
      ? `<b class="cc-hero-score ${won}"><em>${Math.round(sc[0])}</em><i>–</i><em>${Math.round(sc[1])}</em></b><small class="cc-hero-fin">Final · ${won.toUpperCase()}</small>`
      : `<b class="cc-hero-vs">${g.home === false ? "AT" : "VS"}</b>`}</div>`;
  }
  /* THE GAME OVER ITS STADIUM: his team on the left, the opponent on the
     right, each over its own colour, the home team's building behind
     (the family render every game card uses, venuePhotoTag). A season's
     view has his team and the season's count. A fighter has no team and
     no building: his chart opens on its title instead. */
  function heroHTML(g, d, sport, sum) {
    const mine = (g && g.team) || d.team;
    if (!mine || (g && !g.opp)) return "";
    // A game the table could not place home or away (a rink's, now and
    // then) is drawn over his own team's building.
    const home = !g || g.home !== false ? mine : g.opp;
    const a = inkOf(sport, mine), b = g ? inkOf(sport, g.opp) : a;
    const ink = [a ? `--ta:${a}` : "", b ? `--tb:${b}` : ""].filter(Boolean).join(";");
    const art = typeof venuePhotoTag === "function" ? venuePhotoTag(sport, home, teamOf(sport, home)) : "";
    const n = d.games.length;
    const mid = g ? heroMid(g)
      : `<div class="cc-hero-mid"><small>${esc(seasonName(sport, d.season))}</small><b class="cc-hero-vs">Season</b><span>${n} game${n === 1 ? "" : "s"}</span></div>`;
    const right = g ? heroTeam(sport, g.opp, g.orec, true)
      : `<div class="cc-hero-team r"><span class="cc-hero-name cc-hero-sum"><small>${esc(sum[1])}</small><b>${esc(sum[0])}</b></span></div>`;
    return heroShell(ink, art, heroTeam(sport, mine, g ? g.rec : "", false), mid, right, g ? "" : "season");
  }
  /* The frame every hero shares — the building (or the arena) behind, a
     glow from each side in its own colour, three columns — so a fight's
     hero (js/chart-ufc.js) is drawn in the same one as a game's. */
  function heroShell(ink, art, left, mid, right, cls) {
    return `<div class="cc-hero${cls ? ` ${cls}` : ""}"${ink ? ` style="${ink}"` : ""}>${art}
      <div class="cc-hero-in">${left}${mid}${right}</div></div>`;
  }
  //: The games, newest first, with an arrow either end (the render's carousel).
  function gamesRow(d, sport, chipOf) {
    const n = d.games.length;
    return `<div class="cc-car">
      <button type="button" class="cc-step" data-step="-1" aria-label="Newer game"${S.gi <= 0 ? " disabled" : ""}>‹</button>
      <div class="cc-games" role="tablist" aria-label="Games">${d.games.map((x, i) =>
        `<button type="button" role="tab" class="cc-chip${i === S.gi ? " on" : ""}" data-gi="${i}" aria-selected="${i === S.gi}"><b>${esc(chipLabel(x, sport))}</b><small>${esc(chipOf(x))}</small></button>`).join("")}</div>
      <button type="button" class="cc-step" data-step="1" aria-label="Older game"${S.gi >= n - 1 ? " disabled" : ""}>›</button></div>`;
  }

  /* WHICH SIDE OF THE FIELD (the render's "All Runs | Left | Middle |
     Right" and the counts under its field): a run's hole, as the
     play-by-play splits it (left end to left guard, the middle, right
     guard to right end); a target's or a throw's third. A play the file
     gives no side is counted in the whole and in no side. */
  const SIDE_OF_HOLE = { LE: "L", LT: "L", LG: "L", M: "M", RG: "R", RT: "R", RE: "R" };
  /* EVERY LEAGUE HAS ITS OWN THIRDS (2026-10-14, Ethan: "go match it with
     all the other sports too, but obviously make sense and correlate it
     with that sport"). Football's are the sides of the field; a league's
     own module names its own in `zones` — a guard's paint, mid-range and
     threes, a hitter's pull side, middle and opposite field, a pitcher's
     fastballs, breaking balls and offspeed, a skater's slot, high slot and
     point, a kicker's distances — each [key, the filter's word, the
     count's name], how a play is sorted into one, and which plays are
     counted (a free throw has no spot on the floor). */
  const FIELD = { label: "Side of the field",
                  list: [["L", "Left", "Left side"], ["M", "Middle", "Middle"], ["R", "Right", "Right side"]] };
  const zonesOf = (kind) => (DRAW[kind] && DRAW[kind].zones) || (/^(carries|routes|passes)$/.test(kind) ? FIELD : null);
  function sideOf(kind, x) {
    if (!x) return "";
    if (kind === "carries") return SIDE_OF_HOLE[x.h] || "";
    if (kind === "routes" || (kind === "passes" && x.k === "pass")) return BAND[x.s] ? x.s : "";
    const Z = DRAW[kind] && DRAW[kind].zones;
    return Z ? Z.of(x) || "" : "";
  }
  //: A game's plays, in the order its drawing and its table number them.
  const playsOf = (kind, g) => (!g ? [] : kind === "carries" ? g.carries || []
    : kind === "routes" ? g.targets || [] : kind === "passes" ? g.throws || [] : []);
  //: What the counts under a drawing count: football's plays, or the ones a league's zones name.
  function poolOf(kind, g, d) {
    const Z = DRAW[kind] && DRAW[kind].zones;
    if (!Z) return playsOf(kind, g);
    return !g ? [] : Z.pool ? Z.pool(g, d) : DRAW[kind].items(g, d);
  }
  function segHTML(K, Z) {
    const zs = (Z || FIELD).list, cur = (S && S.side) || "";
    return `<div class="cc-seg" role="group" aria-label="${esc((Z || FIELD).label || "Where")}">${[["", K.all || "All"]].concat(zs).map(([k, name]) =>
      `<button type="button" data-side="${k}"${cur === k ? ' class="on"' : ""} aria-pressed="${cur === k}">${esc(name)}</button>`).join("")}</div>`;
  }
  function sidesHTML(kind, items, K, live) {
    const Z = zonesOf(kind) || FIELD, by = {};
    Z.list.forEach(([k]) => { by[k] = 0; });
    let n = 0;
    items.forEach((x) => {
      if (kind === "passes" && x.k !== "pass") return;
      n += 1;
      const s = sideOf(kind, x);
      if (s in by) by[s] += 1;
    });
    if (!Z.list.some(([k]) => by[k])) return "";
    const [one, many] = Z.noun || [K.one, K.noun];
    return `<div class="cc-sides">${Z.list.map(([s, , name]) => {
      const inner = `<span>${esc(name)}</span><b>${by[s]} <small>${esc(by[s] === 1 ? one : many)}</small></b><i>${n ? Math.round(100 * by[s] / n) : 0}%</i>`;
      return live ? `<button type="button" class="cc-sd" data-sd="${s}" data-side="${s}">${inner}</button>`
        : `<div class="cc-sd" data-sd="${s}">${inner}</div>`;
    }).join("")}</div>`;
  }

  /* THE CARDS: the drawing (its name, an "i" that opens how it is drawn,
     the side filter), the numbers, and every play. */
  function distCard(K, title, seg, fig, after, note, ink) {
    return `<section class="cc-card cc-dist"${ink ? ` style="--tm:${ink}"` : ""}><header class="cc-card-h"><h3 class="cc-card-t">${esc(title || K.dist || K.title)}${note
      ? '<button type="button" class="cc-info" data-info aria-expanded="false" aria-label="How it’s drawn">i</button>' : ""}</h3>${seg}</header>
      ${note ? `<div class="cc-pop" hidden>${note}</div>` : ""}${fig}${after}</section>`;
  }
  const statsCard = (title, html) => (html ? `<section class="cc-card cc-stats"><h3 class="cc-card-t">${esc(title)}</h3>${html}</section>` : "");
  function playsCard(title, n, tools, body) {
    if (C && C.inline) {
      return `<section class="cc-card cc-plays">${fold("list", n == null ? title : `${title} (${n})`,
        (tools ? `<div class="cc-tools">${tools}</div>` : "") + body)}</section>`;
    }
    return `<section class="cc-card cc-plays"><header class="cc-card-h"><h3 class="cc-card-t">${esc(title)}${n == null ? ""
      : ` <span class="cc-n">(${n})</span>`}</h3>${tools ? `<div class="cc-tools">${tools}</div>` : ""}</header>${body}</section>`;
  }
  const splitsCard = (title, html) => (html ? `<section class="cc-card cc-splits">${fold("splits", title, html)}</section>` : "");

  /* THE TABLE'S FILTER AND ITS DOWNLOAD: which plays show (each choice
     with its count, and only the ones this game has), and the game's
     plays as a spreadsheet. */
  const FILTERS = {
    carries: [["", "All carries"], ["big", "5+ yards"], ["loss", "Losses"], ["fd", "First downs"], ["td", "Touchdowns"],
              ["sc", "Scrambles"], ["fum", "Fumbles"]],
    routes: [["", "All targets"], ["c", "Catches"], ["inc", "Incomplete"], ["int", "Interceptions"], ["fd", "First downs"],
             ["td", "Touchdowns"]],
  };
  const DL_ICON = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M8 2.5v8M4.6 7.3 8 10.7l3.4-3.4M3 13.5h10"/></svg>`;
  /* `list` is the league's own filter where it draws its own chart (its
     module's `filters`), and a chart with no filter keeps the download. */
  function toolsHTML(kind, items, flagsOf, list) {
    const n = {};
    if (flagsOf) items.forEach((x) => flagsOf(x).split(" ").forEach((f) => { if (f) n[f] = (n[f] || 0) + 1; }));
    const opts = (list || FILTERS[kind] || []).filter(([v]) => !v || n[v]);
    if (S && !opts.some(([v]) => v === (S.filt || ""))) S.filt = "";
    const cur = (S && S.filt) || "", P = DRAW[kind];
    const what = P ? (P.file || kindOf(kind, S && S.sport).noun) : kind === "carries" ? "carries" : "targets";
    const dl = typeof Blob === "function" && (!P || P.csv)
      ? `<button type="button" class="cc-dl" data-dl="${kind}" aria-label="Download ${esc(P && P.fileWhat ? P.fileWhat : `this game’s ${what}`)} as a spreadsheet">${DL_ICON}</button>` : "";
    const filt = opts.length > 1 ? `<span class="cc-filt"><select data-filt aria-label="Which plays to show">${opts.map(([v, name]) =>
      `<option value="${v}"${v === cur ? " selected" : ""}>${esc(name)}${v ? ` (${n[v]})` : ""}</option>`).join("")}</select></span>` : "";
    return dl + filt;
  }
  function csvOf(kind, g, d) {
    const q = (v) => { const s = String(v == null ? "" : v); return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const P = DRAW[kind];
    const rows = P ? P.csv(g, d || (S && S.data) || {}) : kind === "carries"
      ? [["#", "Quarter", "Clock", "Down", "To go", "Yard line", "Hole", "Yards", "Touchdown", "Fumble", "First down", "Scramble"]]
        .concat((g.carries || []).map((c, i) => [i + 1, c.q, c.clk, c.dn, c.ds, spot(c, g), c.h ? HOLE_NAME[c.h] : "", c.y,
          +!!c.td, +!!c.fl, +!!c.fd, +!!c.sc]))
      : [["#", "Quarter", "Clock", "Down", "To go", "Yard line", "Route", "Air yards", "Side", "Caught", "Yards",
          "After the catch", "Touchdown", "Interception", "First down", "Coverage", "Shell"]]
        .concat((g.targets || []).map((t, i) => [i + 1, t.q, t.clk, t.dn, t.ds, spot(t, g), ROUTE_NAME[t.rt] || t.rt || "",
          t.ay, SIDE_WORD[t.s] || "", +!!t.c, t.c ? t.y : 0, t.c ? Math.round(yacOf(t)) : "", +!!t.td, +!!t.int, +!!t.fd,
          t.cov || "", t.sh || ""]));
    return rows.map((r) => r.map(q).join(",")).join("\r\n") + "\r\n";
  }
  function download(kind) {
    const d = S && S.data, g = d && d.games && d.games[S.gi];
    if (!g || typeof Blob !== "function" || typeof URL === "undefined" || !URL.createObjectURL) return;
    const P = DRAW[kind];
    if (P && !P.csv) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csvOf(kind, g, d)], { type: "text/csv;charset=utf-8" }));
    const what = P ? (P.file || kindOf(kind, d.sport).noun) : kind === "carries" ? "carries" : "targets";
    a.download = `${[d.player, what, d.sport === "ufc" ? "" : d.season, P && P.fileWhat ? "" : chipLabel(g, d.sport)].join(" ")
      .replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  /* THE ROUTE CHART'S OTHER VIEWS (the render's "Route Type | Depth |
     Coverage" tabs): the season's targets by each, as bars — the route
     and the coverage only for a season the league has charted. */
  function routeViews(d) {
    if (d.air === false) return [];
    const v = [];
    if ((d.by_route || []).length) v.push(["route", "Route type"]);
    v.push(["depth", "Depth"]);
    if ((d.by_cov || []).length || (d.by_shell || []).length) v.push(["cov", "Coverage"]);
    return v;
  }
  const BAR_TITLE = { route: "Targets by route", depth: "Targets by depth", cov: "Targets against coverage" };
  function barRows(rows) {
    return barList(rows.filter(([, x]) => x && x.tgt).map(([name, x]) =>
      [name, x.tgt, `${x.rec}/${x.tgt} caught · ${num1(x.ypt)} yds a target${x.td ? ` · ${x.td} TD` : ""}`]));
  }
  /* ONE BAR A ROW, in every league's other views: [name, how many, what
     came of them, and a pill where a rate is set beside the league's].
     The bar is the count against the most of any row; the share beside
     it is of every row's. A row with none is left out. */
  function barList(rows) {
    const live = rows.filter((r) => r && r[1] > 0);
    if (!live.length) return "";
    const total = live.reduce((a, r) => a + r[1], 0), most = Math.max(...live.map((r) => r[1]));
    return `<div class="cc-bars">${live.map(([name, n, said, pill]) => `<div class="cc-brow">
        <span class="cc-bn">${esc(name)}</span>
        <span class="cc-bt"><i style="width:${(100 * n / most).toFixed(1)}%"></i></span>
        <b class="cc-bv">${n}<small>${pct(n / total)}</small></b>
        <span class="cc-bx">${esc(said)}${pill ? ` ${pills([pill])}` : ""}</span></div>`).join("")}</div>`;
  }
  function routeBars(d, view) {
    if (view === "depth") return barRows(DEPTH.map(([k, name]) => [name, sumLines(d.by_zone.filter((z) => z.depth === k))]));
    if (view === "route") return barRows((d.by_route || []).map((x) => [ROUTE_NAME[x.route] || x.route, x]));
    const man = barRows((d.by_cov || []).map((x) => [x.coverage === "man" ? "Man" : "Zone", x]));
    const shell = barRows((d.by_shell || []).map((x) => [x.shell, x]));
    return (man ? `<h4 class="cc-bh">Man or zone</h4>${man}` : "") + (shell ? `<h4 class="cc-bh">Coverage shell</h4>${shell}` : "");
  }

  function render() {
    const ov = C && C.root;
    if (!ov || !S) return;
    const d = S.data;
    const box = ov.querySelector(".cc-body");
    const R = S.kind === "routes";
    const K = kindOf(S.kind, S.sport), P = DRAW[S.kind];
    if (!d || (P && P.only ? !(d.zones || []).length : !d.games || !d.games.length)) {
      /* No one in the league has a row yet: the charts are being filled
         (engine/chartfill), which is not the same as none for him. The
         switch stays above it on a pick page, so the other chart is a
         tap away. */
      box.innerHTML = kindBar() + (d && d.filling
        ? `<div class="cc-empty">${esc(K.title)}s are still being filled: ${esc(K.fill || `every ${K.one} is read from the ${S.sport === "cfb" ? "college" : "league’s"} play-by-play`)}, which takes a few minutes. Check back shortly.</div>`
        : R
          ? `<div class="cc-empty">No targets on file for ${esc(S.player)}.</div>`
          : P ? `<div class="cc-empty">No ${esc(K.noun)} on file for ${esc(S.player)}.</div>`
            : `<div class="cc-empty">No carries on file for ${esc(S.player)}${S.sport === "cfb" ? " in the college play-by-play" : ""}.</div>`);
      return;
    }
    const sport = d.sport;
    const seasons = d.seasons.length > 1 ? `<div class="cc-seasons" role="group" aria-label="Season">${d.seasons.map((y) =>
      `<button type="button" class="cc-chip${y === d.season ? " on" : ""}" data-season="${y}" aria-pressed="${y === d.season}">${esc(seasonName(sport, y))}</button>`).join("")}</div>` : "";
    /* On a pick page the page above already says who he is, so the chart
       opens on its switches (his charts, the seasons) and then the game;
       the overlay (a door that asked for his chart) opens on his face and
       name, the game, and his charts under it — each render's order. */
    const kb = kindBar();
    const bar = C.inline ? kb + seasons : kb;
    /* A league's own other views (its module's `views`) sit after its
       two, as the route chart's Route type | Depth | Coverage do. */
    const more = P && P.views ? P.views(d) || [] : [];
    const views = P && P.only ? [] : [["game", K.by || "By game"], ["season", cap(K.where)]].concat(R ? routeViews(d) : more);
    if (views.length && !views.some(([k]) => k === S.view)) S.view = S.view === "game" ? "game" : "season";
    const head = C.inline ? "" : `<header class="cc-head">
        ${faceHTML(d, S)}
        <div class="cc-who">
          <span class="cc-eyebrow">${esc(d.position && S.kind !== "fights" ? `${d.position} ${K.chip}` : K.title)}</span>
          <h2 class="cc-name">${esc(d.player)}</h2>
          <span class="cc-sub">${[d.jersey ? `#${esc(d.jersey)}` : "", esc(d.position || ""), d.team
            ? `${teamMarkIn(sport, d.team, 16)} ${esc(teamNameIn(sport, d.team))}` : ""].filter(Boolean).join(" · ")}</span>
        </div>
        ${seasons}
      </header>
      <p class="cc-desc">${esc(cap(descOf(S.kind, sport)))}.</p>`;
    const tabs = views.length ? `<div class="cc-tabs" role="tablist">${views.map(([k, name]) =>
      `<button type="button" role="tab" class="cc-tab${S.view === k ? " on" : ""}" data-view="${k}" aria-selected="${S.view === k}">${esc(name)}</button>`).join("")}</div>` : "";
    /* The parts every view fills: the games row, the drawing's card, the
       numbers' card and the long tail. A pick page's card, when it is
       wide, sets the drawing beside its numbers (.cc-split) so the field
       is not drawn a screen tall across a desktop. */
    const note = P ? P.note(d) : R ? (d.air === false ? cfbTargetNote(d) : routeNote(d)) : noteHTML(d);
    const L = d.season_line || {};
    const game = S.view === "game" && !(P && P.only);
    const g = game ? d.games[Math.min(S.gi, d.games.length - 1)] : null;
    /* A LEAGUE THAT LAYS ITS OWN PAGE OUT (2026-10-14, Ethan's four
       renders of the MLB hit page): its module draws everything under the
       switch — its hero, the tabs, the view — and the frame keeps what it
       does for every chart: the switch, how it is drawn, the side filter,
       the table's filter, the selection and the tip. */
    if (P && P.page) {
      box.innerHTML = (kb ? `<div class="cc-bar">${kb}</div>` : "")
        + P.page({ d, g, sport, view: S.view, tabs, note, inline: !!C.inline,
                   ink: inkOf(sport, (g && g.team) || d.team) })
        + fold("note", "How it’s drawn", note);
      return settle(box);
    }
    const items = poolOf(S.kind, g, d);
    const every = [].concat(...(d.games || []).map((x) => poolOf(S.kind, x, d)));
    const sided = (game ? items : every).some((x) => sideOf(S.kind, x));
    const count = P && P.only ? ["", "", ""]
      : String(P ? P.count(L, d) || "" : `${R ? L.tgt : L.n} ${K.noun}`).match(/^(\S+)\s*(.*)$/) || ["", "", ""];
    /* The game over its building; a fighter's fight over the arena (his
       module's own `hero`); tonight's matchup over his team's colours and
       the opponent's, where the charts he has named his team. */
    const hero = P && P.hero ? P.hero(g, d, [count[1], count[2]])
      : P && P.only ? (C.team ? heroHTML({ team: C.team, opp: d.opp, tonight: true, home: true,
                                           label: String(d.season_label || d.season || "") },
                                         Object.assign({}, d, { team: C.team }), sport, ["", ""]) : "")
        : heroHTML(g, d, sport, [count[1], count[2]]);
    /* A pass is drawn in his team's colour (the render's blue routes for
       a Bill), and so is every league's own surface (a guard's paint, a
       hitter's wall, a kicker's end zone); a run in the three gain
       colours. */
    const ink = inkOf(sport, (g && g.team) || d.team || (P && P.only ? C.team : ""));
    const stage = (svg, tip) => `<div class="cc-stage">${svg}${tip ? '<div class="cc-tip" hidden></div>' : ""}</div>`;
    const sides = sided ? sidesHTML(S.kind, game ? items : every, K, game) : "";
    const seg = game && sided ? segHTML(K, zonesOf(S.kind)) : "";
    let rows = "", title = "", dist, stats, tail;
    if (P && P.only) {
      const v = P.only(d, sport);
      title = v.top;
      dist = distCard(K, "", "", v.fig, "", note, ink);
      stats = statsCard("Tonight’s numbers", v.side);
      tail = v.tail;
    } else if (P && P.bars && more.some(([k]) => k === S.view)) {
      dist = distCard(K, P.barTitle ? P.barTitle(S.view, d) : "", "", P.bars(d, S.view), "", "", ink);
      stats = statsCard(S.kind === "fights" ? "Career" : "Season stats", P.seasonSide(d));
      tail = splitsCard(P.splitsTitle, P.splits(d));
    } else if (P) {
      const v = plugView(P, d, sport);
      rows = v.rows;
      title = v.title;
      dist = distCard(K, P.distTitle ? P.distTitle(S.view, d) : "", seg, v.fig, sides + (P.legend ? P.legend(g, d) : ""), note, ink);
      stats = statsCard(S.kind === "fights" ? (game ? "Fight stats" : "Career") : game ? "Game stats" : "Season stats", v.side);
      tail = v.tail;
    } else if (R && BAR_TITLE[S.view]) {
      dist = distCard(K, BAR_TITLE[S.view], "", routeBars(d, S.view), "", "", ink);
      stats = statsCard("Season stats", routeTiles(L, d.ngs));
      tail = splitsCard("Every split · depth, side, route, coverage, down", routeTables(d));
    } else if (S.view === "season" && R && d.air === false) {
      title = `<div class="cc-title">${esc(`${d.season} season · ${L.tgt} targets in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      dist = distCard(K, "", "", stage(cfbTargetSeason(d)), cfbTargetLegend(), note, ink);
      stats = statsCard("Season stats", `${cfbTargetTiles(L)}
        <div class="cc-tiles cc-tiles-2">${tile("Yds/target", num1(L.ypt))}${tile("Targets a game", num1(L.tgt / d.games.length))}${tile("Red zone targets", redZone(d))}${tile("Long", L.long == null ? "—" : Math.round(L.long))}</div>`);
      tail = splitsCard("Every split · down, field position", routeTables(d));
    } else if (S.view === "season" && R) {
      title = `<div class="cc-title">${esc(`${d.season} season · ${L.tgt} targets in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      dist = distCard(K, "", "", stage(routeSeasonChart(d)), sides + routeLegend(d.routes, true), note, ink);
      stats = statsCard("Season stats", `${routeTiles(L, d.ngs)}
        <div class="cc-tiles cc-tiles-2">${tile("Catch rate", pct(L.catch))}${tile("Yds/target", num1(L.ypt))}${tile("Contested won", `${L.contested_won}/${L.contested}`)}${tile("Drops", L.drops)}</div>
        ${routeNgs(d)}`);
      tail = splitsCard("Every split · depth, side, route, coverage, down", routeTables(d));
    } else if (S.view === "season") {
      const any = d.games.some((x) => x.carries.some((c) => !c.h)) && d.holes;
      title = `<div class="cc-title">${esc(`${d.season} season · ${L.n} carries in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      dist = distCard(K, "", "", stage(seasonChart(d)), sides + legendHTML(sport, any), note, ink);
      stats = statsCard("Season stats", `${tilesFor(L, (d.ngs || {}).ryoe)}
        <div class="cc-tiles cc-tiles-2">${tile("Success", pct(L.success))}${tile("Stuffed (0 or less)", pct(L.stuffed))}${tile("10+ yd runs", L.explosive)}${tile("Long", L.long == null ? "—" : Math.round(L.long))}</div>
        ${ngsLine(d)}`);
      tail = splitsCard(`Every split · ${d.holes ? "hole, " : ""}down, field position`, seasonTables(d));
    } else {
      rows = gamesRow(d, sport, (x) => tally(R ? x.line.rec : x.line.n, x.line.yds));
      title = `<div class="cc-title">${esc(gameTitle(g, sport, d.season))}</div>`;
      if (R && d.air === false) {
        dist = distCard(K, "", "", stage(cfbTargetGame(g), true), cfbTargetLegend(), note, ink);
        stats = statsCard("Game stats", cfbTargetTiles(g.line));
        tail = playsCard("Every target", g.targets.length, toolsHTML("routes", g.targets, targetFlags), routeList(g));
      } else if (R) {
        dist = distCard(K, "", seg, stage(routeGameChart(g), true), sides + routeLegend(g.targets.some((t) => t.rt), false), note, ink);
        stats = statsCard("Game stats", routeTiles(g.line, g.ngs));
        tail = playsCard("Every target", g.targets.length, toolsHTML("routes", g.targets, targetFlags), routeList(g));
      } else {
        const any = d.holes && g.carries.some((c) => !c.h);
        dist = distCard(K, "", seg, stage(gameChart(g, sport, d.holes), true), sides + legendHTML(sport, any), note, ink);
        stats = statsCard("Game stats", tilesFor(g.line, g.ryoe));
        tail = playsCard("Every carry", g.carries.length, toolsHTML("carries", g.carries, carryFlags), listHTML(g, sport));
      }
    }
    const barRow = bar ? `<div class="cc-bar">${bar}</div>` : "";
    const main = C.inline ? `<div class="cc-split"><div class="cc-fig">${dist}</div><div class="cc-side">${stats}</div></div>` : dist + stats;
    // The game over its stadium says what the title line said; a chart
    // with no team to draw (a fighter's) keeps its title.
    box.innerHTML = (C.inline ? barRow + hero : head + hero + barRow) + tabs + rows + (hero ? "" : title) + main + tail
      + fold("note", "How it’s drawn", note);
    settle(box);
  }
  function settle(box) {
    /* The chosen game's chip is brought to the middle of its row by
       scrolling the ROW. scrollIntoView would also scroll the page to it,
       and a chart drawn halfway down a pick page would pull the reader
       down to it the moment it loaded. */
    const chip = box.querySelector(".cc-games .cc-chip.on");
    const row = chip && chip.parentElement;
    if (row && chip.getBoundingClientRect) {
      const a = chip.getBoundingClientRect(), b = row.getBoundingClientRect();
      row.scrollLeft += a.left + a.width / 2 - (b.left + b.width / 2);
    }
    /* A tile's name a narrow card would cut ("They allow", "Fight
       lasted" three to a row on a phone) drops its icon and closes its
       spacing instead: read once, in the same layout as the chip row's
       measure, so a name is never cut. */
    box.querySelectorAll(".cc-k").forEach((k) => { if (k.scrollWidth > k.clientWidth + 1) k.classList.add("tight"); });
    applySide();
    applyFilt();
  }

  /* The side filter: the other sides' plays fade on the field, the
     chosen side's count lights; the table's filter: the rows that do not
     match go. Both are read off S, so a redraw keeps them. */
  function applySide() {
    const ov = C && C.root;
    if (!ov || !S) return;
    const side = S.side || "";
    ov.querySelectorAll(".cc-seg [data-side]").forEach((b) => {
      const on = (b.dataset.side || "") === side;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    ov.querySelectorAll(".cc-sd").forEach((x) => {
      x.classList.toggle("on", !!side && x.dataset.sd === side);
      if (x.tagName === "BUTTON") x.dataset.side = side === x.dataset.sd ? "" : x.dataset.sd;
    });
    const g = S.view === "game" && S.data && S.data.games ? S.data.games[S.gi] : null;
    const items = playsOf(S.kind, g);
    // A league whose zones say so (`season`) filters its season's drawing
    // as well as a game's: a hitter's pull side, middle and opposite field.
    const Z = zonesOf(S.kind), lit = !!g || !!(Z && Z.season);
    // A league's own marks say their zone (`data-z`): a pitch is drawn
    // under the batter it was thrown to, not counted as him.
    ov.querySelectorAll(".cc-stage .cc-carry").forEach((el) => {
      const z = el.dataset.z != null ? el.dataset.z : sideOf(S.kind, items[+el.dataset.i]);
      el.classList.toggle("off", !!side && lit && z !== side);
    });
  }
  function applyFilt() {
    const ov = C && C.root;
    if (!ov || !S) return;
    const f = S.filt || "";
    ov.querySelectorAll(".cc-row[data-f]").forEach((r) => { r.hidden = !!f && !r.dataset.f.split(" ").includes(f); });
  }

  /* ON A PICK PAGE THE LONG TAIL FOLDS: every carry or target in order,
     and the season's split tables, one tap away under the chart and its
     numbers, so the page around them stays readable. The overlay is the
     chart and nothing else, so it shows them open, as before. A fold
     the reader opened stays open while he moves between games. */
  function fold(key, title, html) {
    if (!C || !C.inline || !html) return html;
    return `<details class="cc-more" data-fold="${key}"${S.open && S.open[key] ? " open" : ""}>
      <summary>${esc(title)}</summary>${html}</details>`;
  }

  /* A REGISTERED CHART'S VIEWS, in the carry and route charts' frame: the
     season's title, drawing, numbers and splits; or the games row (each
     chip with the game's own tally), the game's drawing with its tip,
     its numbers and every play in order. */
  function plugView(P, d, sport) {
    if (S.view === "season") {
      const n = d.games.length;
      return { rows: "",
               title: `<div class="cc-title">${esc(P.seasonTitle ? P.seasonTitle(d)
                 : `${seasonName(sport, d.season)} season · ${P.count(d.season_line, d)} in ${n} game${n === 1 ? "" : "s"}`)}</div>`,
               fig: `<div class="cc-stage">${P.season(d)}</div>`,
               side: P.seasonSide(d),
               tail: splitsCard(P.splitsTitle, P.splits(d)) };
    }
    const g = d.games[Math.min(S.gi, d.games.length - 1)];
    return { rows: gamesRow(d, sport, (x) => P.chip(x, d)),
             title: `<div class="cc-title">${esc(P.gameTitle ? P.gameTitle(g, d) : gameTitle(g, sport, seasonName(sport, d.season)))}</div>`,
             fig: `<div class="cc-stage">${P.game(g, d)}<div class="cc-tip" hidden></div></div>`,
             side: P.gameSide(g, d),
             tail: playsCard(P.listTitle ? P.listTitle(g, d) : `Every ${P.one}`, P.listTitle ? null : P.items(g, d).length,
                             P.flags || P.csv ? toolsHTML(S.kind, P.items(g, d), P.flags, P.filters) : "", P.list(g, d)) };
  }

  /* ---------------- selection and the tip ---------------- */
  function select(i) {
    const ov = C && C.root;
    if (!ov || !S) return;
    S.sel = S.sel === i ? -1 : i;
    ov.querySelectorAll(".cc-carry").forEach((g) => {
      const on = +g.dataset.i === S.sel;
      const p = g.querySelector(".cc-run, .rc-route, .rc-throw, .cx-mark");
      if (p) p.classList.toggle("sel", on);
      g.classList.toggle("dim", S.sel >= 0 && !on);
    });
    ov.querySelectorAll(".cc-row").forEach((r) => r.classList.toggle("sel", +r.dataset.i === S.sel));
    tip(S.sel);
  }
  function tip(i) {
    const ov = C && C.root;
    const el = ov && ov.querySelector(".cc-tip");
    if (!el) return;
    const d = S.data, g = d && d.games[S.gi];
    const P = DRAW[S.kind];
    if (P) {
      const t = g && P.items(g, d)[i];
      if (!t || S.view !== "game") { el.hidden = true; return; }
      el.innerHTML = P.tip(t, g, d);
      el.hidden = false;
      return;
    }
    if (S.kind === "routes") {
      const t = g && (g.targets || [])[i];
      if (!t || S.view !== "game") { el.hidden = true; return; }
      const yac = t.c ? Math.round(yacOf(t)) : 0;
      el.innerHTML = `<b class="${t.int ? "loss" : t.c ? "gain" : "miss"}">${t.int ? "Intercepted" : t.c ? `${signed(t.y)} yds` : "Incomplete"}</b>${t.td ? " · TD" : ""}${t.c && yac ? ` · ${yac} after the catch` : ""}
        <span>${esc([qLabel(t), downDist(t), spot(t, g), ROUTE_NAME[t.rt] || "", airWords(t) || zoneWord(t), covWords(t)].filter(Boolean).join(" · "))}</span>`;
      el.hidden = false;
      return;
    }
    const c = g && g.carries[i];
    if (!c || S.view !== "game") { el.hidden = true; return; }
    el.innerHTML = `<b class="${c.band}">${signed(c.y)} yds</b>${c.td ? " · TD" : ""}${c.sc ? " · scramble" : ""}
      <span>${esc([qLabel(c), downDist(c), spot(c, g), c.h ? HOLE_NAME[c.h] : ""].filter(Boolean).join(" · "))}</span>`;
    el.hidden = false;
  }

  /* ---------------- the face ----------------
     Ethan, 2026-10-13: "Make sure we are showing headshots in this new
     page." The photo the server found, then the one the page he came from
     was showing (the door hands it over), each as the site's small copy
     and then the full one — and under them his initials, which is what
     shows when every photo fails instead of an empty ring. A headshot is
     a cut-out on a clear ground, so the initials step aside once a photo
     has loaded (`on`). Both outcomes are kept in S, so a redraw (a season,
     a tab, a game) neither flashes the initials back nor asks again for a
     photo that is not there. */
  function faces(d, hint) {
    const out = [];
    for (const u of [d.face, hint]) {
      if (u) out.push(typeof facePreview === "function" ? facePreview(u, 58) : u, u);
    }
    return [...new Set(out.filter(Boolean))];
  }
  function inits(name) {
    const w = String(name || "").replace(/[.,']/g, "").split(/\s+/)
      .filter((x) => x && !/^(jr|sr|ii|iii|iv|v)$/i.test(x));
    return ((w[0] || "?")[0] + (w.length > 1 ? w[w.length - 1][0] : "")).toUpperCase();
  }
  function faceHTML(d, st) {
    const list = faces(d, st.hint);
    if (st.faceKey !== list.join(" ")) Object.assign(st, { faceKey: list.join(" "), faces: list, fi: 0, faceOk: false });
    const url = st.faces[st.fi];
    const t = typeof teamsForSport === "function" && d.team ? (teamsForSport(d.sport) || {})[d.team] : null;
    const ink = t && t.primary && typeof idealText === "function"
      ? ` style="background:${esc(t.primary)};color:${esc(idealText(t.primary))}"` : "";
    return `<span class="cc-face${url && st.faceOk ? " on" : ""}"><span class="cc-init" aria-hidden="true"${ink}>${esc(inits(d.player))}</span>${url
      ? `<img src="${esc(url)}" alt="" decoding="async">` : ""}</span>`;
  }
  /* A photo loaded: the initials step aside. One failed: the next one,
     and when there is none, the initials alone. */
  function faceStep(type, img, st) {
    if (!st || !st.faces || !img || img.tagName !== "IMG" || !img.closest(".cc-face")) return;
    if (type === "load") {
      st.faceOk = true;
      img.parentNode.classList.add("on");
    } else if (st.faces[++st.fi]) {
      img.src = st.faces[st.fi];
    } else {
      img.remove();
    }
  }
  const faceEvent = (e) => faceStep(e.type, e.target, (e.currentTarget._cc || {}).S);

  /* ---------------- loading ---------------- */
  /* One of his charts, as the server answers it. A chart that chose
     among his charts (a pick page's, or an overlay a door opened on
     "his chart") reads the answer kept from the last ten minutes first,
     so the page's redraw every minute, a switch between his charts or a
     reader going back and forth between picks costs nothing; an overlay
     opened on one named chart asks every time, as it always has. A chart
     still being filled is never kept. */
  function ask(kind, sport, player, season, cached) {
    const api = kind === "routes" ? "/api/players/routes?sport="
      : kind === "carries" ? "/api/players/carries?sport=" : `/api/players/chart?kind=${kind}&sport=`;
    const q = `${api}${encodeURIComponent(sport)}&player=${encodeURIComponent(player)}${season ? `&season=${season}` : ""}${kind === "matchup"
      ? `&opp=${encodeURIComponent(S.opp || "")}&fam=${encodeURIComponent(S.fam || "")}` : ""}`;
    const hit = cached && CACHE.get(q);
    if (hit && Date.now() - hit.t < CACHE_MS) return Promise.resolve(hit.data);
    return fetch(q).then((r) => (r.ok ? r.json() : null)).catch(() => null).then((data) => {
      if (data && !data.filling) CACHE.set(q, { t: Date.now(), data });
      return data;
    });
  }
  //: How much of his season a chart holds: carries, or passes thrown to him
  //: (every other chart's server answer counts its own in `season_line.n`:
  //: a passer's attempts).
  const vol = (kind, d) => (d && ((d.games && d.games.length) || (kind === "matchup" && (d.zones || []).length))
    ? Number((d.season_line || {})[kind === "routes" ? "tgt" : "n"]) || 0 : 0);
  //: Never the chart a pick leads with: his role, then tonight's matchup.
  const LATE = { role: 1, matchup: 2 };
  //: A second chart is offered when he has this many in the same season.
  const SECOND_MIN = 3;
  /* Only the newest request a chart made is drawn, and none once the
     chart is gone. */
  function load(c, season) {
    use(c);
    const seq = ++c.seq;
    ask(S.kind, S.sport, S.player, season, !!c.cand).then((data) => land(c, seq, data));
  }
  function land(c, seq, data) {
    if (seq !== c.seq || c.root._cc !== c) return;
    use(c);
    if (data === null) {
      const box = c.root.querySelector(".cc-body");
      if (box) box.innerHTML = `<div class="cc-empty">The ${esc(kindOf(S.kind, S.sport).title.toLowerCase())} didn’t load. Try again in a moment.</div>`;
      return;
    }
    S.data = data;
    S.gi = 0;
    S.sel = -1;
    if (c.counts && vol(S.kind, data)) c.counts[S.kind] = vol(S.kind, data);
    if (!PLUG[S.kind] || DRAW[S.kind]) return render();
    need(S.kind).then(() => {
      if (seq !== c.seq || c.root._cc !== c) return;
      use(c);
      render();
    });
  }
  /* HIS OWN CHART FIRST, MEASURED ON HIS OWN SEASON (Ethan, 2026-10-13,
     the same day: "we are showing only receptions for RBs and only
     carries for WR and TE"). The chart had been picked from the bet: a
     back's receptions over drew only where he is thrown to, and a pick
     page could open a receiver on his carries. Both of his charts are
     asked for at once, and the one he does more of leads — a back's
     carries, a receiver's or a tight end's targets, read off the numbers
     rather than a position label that can be missing. The other is a tap
     away whenever he has a real share of it (SECOND_MIN in the same
     season); one he barely has is not offered. With neither on file, the
     bet's own chart says so. */
  function probe(c) {
    use(c);
    const seq = ++c.seq;
    Promise.all(c.cand.map((k) => ask(k, S.sport, S.player, null, true))).then((ds) => {
      if (seq !== c.seq || c.root._cc !== c) return;
      // His role (games played) never leads a chart of what he did in them.
      const got = c.cand.map((k, i) => ({ k, d: ds[i], v: vol(k, ds[i]) })).filter((x) => x.v > 0)
        .sort((a, b) => (LATE[a.k] || 0) - (LATE[b.k] || 0) || b.v - a.v);
      const lead = got[0];
      // Tonight's matchup is offered whatever season it reads: it says which.
      const shown = got.filter((x) => x === lead || (x.v >= SECOND_MIN && (x.k === "matchup" || x.d.season === lead.d.season)));
      c.kinds = shown.length ? shown.map((x) => x.k) : [c.cand[0]];
      c.counts = {};
      shown.forEach((x) => { c.counts[x.k] = x.v; });
      // His team, from his own charts: tonight's matchup does not name it,
      // and its hero sets his colours beside the opponent's.
      const own = got.find((x) => x.d && x.d.team);
      c.team = own ? own.d.team : "";
      const want = MEM.get(c.key);
      const kind = c.kinds.includes(want) ? want : c.kinds[0];
      c.S = fresh(c.S.sport, kind, c.S.player, c.S);
      use(c);
      const sec = c.root.querySelector(".cc-sec");
      if (sec) sec.innerHTML = secHTML(c);
      land(c, seq, ds[c.cand.indexOf(kind)]);
    });
  }

  function close() {
    const ov = document.getElementById("cc-overlay");
    if (!ov) return;
    ov.classList.remove("open");
    ov.innerHTML = "";
    ov._cc = null;
    use(null);
    if (typeof lockScroll === "function") lockScroll(false);
    document.removeEventListener("keydown", onKey);
  }
  function onKey(e) { if (e.key === "Escape") close(); }

  /* Every chart's taps, bound once to its root and read off the chart
     hung on it. A match has to be INSIDE the chart: on a pick page the
     chart sits in the site's own markup, and an ancestor carrying one of
     these attributes would otherwise answer a tap on the field. */
  function bind(ov) {
    const hit = (e, sel) => {
      const x = e.target.closest && e.target.closest(sel);
      return x && ov.contains(x) ? x : null;
    };
    ov.addEventListener("click", (e) => {
      const c = use(ov._cc);
      if (!c) return;
      if (!c.inline && (e.target === ov || hit(e, ".cc-x"))) return close();
      const k = hit(e, "[data-ck]");
      if (k) return pick(c, k.dataset.ck);
      const s = hit(e, "[data-season]");
      if (s) return load(c, +s.dataset.season);
      const v = hit(e, "[data-view]");
      if (v) { S.view = v.dataset.view; S.sel = -1; return render(); }
      const gi = hit(e, "[data-gi]");
      if (gi) { S.gi = +gi.dataset.gi; S.sel = -1; return render(); }
      // The games row's arrows: the next game either way, never past the ends.
      const step = hit(e, "[data-step]");
      if (step && S.data && S.data.games) {
        S.gi = Math.max(0, Math.min(S.data.games.length - 1, S.gi + Number(step.dataset.step)));
        S.sel = -1;
        return render();
      }
      /* A league's own page's choices (its module's `page`): one among
         buttons (`data-opt`, the value it sets in `data-v`) or a switch
         (`data-tog`), kept in S so every redraw keeps them. */
      const opt = hit(e, "[data-opt][data-v]");
      if (opt) { S.opt = Object.assign({}, S.opt, { [opt.dataset.opt]: opt.dataset.v }); S.sel = -1; return render(); }
      const tog = hit(e, "[data-tog]");
      if (tog) { S.opt = Object.assign({}, S.opt, { [tog.dataset.tog]: !(S.opt || {})[tog.dataset.tog] }); return render(); }
      const side = hit(e, "[data-side]");
      if (side) { S.side = side.dataset.side || ""; return applySide(); }
      const info = hit(e, "[data-info]");
      if (info) {
        const pop = info.closest(".cc-card") && info.closest(".cc-card").querySelector(".cc-pop");
        if (pop) { pop.hidden = !pop.hidden; info.setAttribute("aria-expanded", String(!pop.hidden)); }
        return;
      }
      const dl = hit(e, "[data-dl]");
      if (dl) return download(dl.dataset.dl);
      const row = hit(e, ".cc-row, .cc-carry");
      if (row && S.view === "game") return select(+row.dataset.i);
    });
    // The table's filter: which plays it shows. A page's own season
    // picker asks for that season; its own menus redraw it.
    ov.addEventListener("change", (e) => {
      const c = use(ov._cc);
      if (!c) return;
      const sp = hit(e, "[data-season-pick]");
      if (sp) return load(c, +sp.value);
      const o = hit(e, "select[data-opt]");
      if (o) { S.opt = Object.assign({}, S.opt, { [o.dataset.opt]: o.value }); return render(); }
      const f = hit(e, "[data-filt]");
      if (!f) return;
      S.filt = f.value;
      applyFilt();
    });
    ov.addEventListener("pointerover", (e) => {
      const g = hit(e, ".cc-carry");
      if (g && use(ov._cc) && S.sel < 0 && e.pointerType === "mouse") tip(+g.dataset.i);
    });
    ov.addEventListener("pointerout", (e) => {
      const g = hit(e, ".cc-carry");
      if (g && use(ov._cc) && S.sel < 0 && e.pointerType === "mouse") tip(-1);
    });
    // A fold opened stays open across a redraw. `toggle` does not bubble.
    ov.addEventListener("toggle", (e) => {
      const c = ov._cc, k = e.target.dataset && e.target.dataset.fold;
      if (c && k) c.S.open = Object.assign({}, c.S.open, { [k]: e.target.open });
    }, true);
    // The face's photo: load and error do not bubble, but a listener in
    // the capture phase sees them — and the CSP allows no inline one.
    ov.addEventListener("load", faceEvent, true);
    ov.addEventListener("error", faceEvent, true);
  }

  /* Every chart a league has, for a door that knows neither his position
     nor a bet the charts read (a player page's head, a leg the parlay
     checker priced): probe asks for each and draws what he has. */
  const ALL = { nfl: ["carries", "routes", "passes", "kicks", "role"], cfb: ["carries", "routes", "role"],
                nba: ["shots", "role"], wnba: ["role"], nhl: ["shotmap", "saves", "role"],
                mlb: ["spray", "pitches", "role"], ufc: ["fights"] };
  function doorKinds(lg, mkt, pos, opp) {
    const hint = kindsFor(lg, mkt, pos);
    const cand = (hint.length ? hint : ALL[lg] || ALL.nfl).slice();
    if (opp && cand.some((k) => MATCHED.has(k))) cand.push("matchup");
    return { cand, fam: hint[0] || "" };
  }
  function open(player, sport, kind, face, mkt, pos, opp) {
    if (!player) return;
    let ov = document.getElementById("cc-overlay");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "cc-overlay";
      document.body.appendChild(ov);
      bind(ov);
    }
    /* "auto" is a door to HIS charts, in every league (a player page, a
       parlay leg): the ones his bet and position point to, as on a pick
       page (kindsFor), or every one the league has; each is asked for,
       his own leads (probe), his role after it, and tonight's matchup
       last wherever the door names the opponent. The matchup's family is
       the bet's chart, or the server's choice by what he does most. */
    const auto = kind === "auto", lg = String(sport || "nfl").toLowerCase();
    const D = auto ? doorKinds(lg, mkt, pos, opp) : { cand: null, fam: "" }, cand = D.cand;
    const k0 = KIND[kind] ? kind : cand ? cand[0] : "carries", K = kindOf(k0, lg);
    ov._cc = use({ root: ov, inline: false, seq: 0, kinds: null, key: "", cand,
                   S: { sport: lg, kind: k0, player, data: null, view: "game", gi: 0, sel: -1,
                        hint: face || "", opp: opp || "", fam: D.fam } });
    ov.innerHTML = `<div class="cc" role="dialog" aria-modal="true" aria-label="${esc(`${auto ? "Charts" : K.title} — ${player}`)}">
      <button class="cc-x" type="button" aria-label="Close">×</button>
      <div class="cc-body"><div class="cc-empty">Loading ${esc(player)}’s ${esc(K.noun)}…</div></div></div>`;
    ov.classList.add("open");
    if (typeof lockScroll === "function") lockScroll(true);
    document.addEventListener("keydown", onKey);
    const x = ov.querySelector(".cc-x");
    if (x) x.focus({ preventScroll: true });
    if (auto) probe(ov._cc); else load(ov._cc, null);
  }

  /* ---------------- the chart on a pick page ----------------
     Ethan, 2026-10-13: "We should show the route checker on the most
     likely bets as well like when you click on the player in the most
     likely bets it will automatically show the charts in that area with
     all the other info." Every door to a football pick — a Most Likely
     row or card, an Edge pick, a bet on the Live tab, a read on the game
     page — lands on the pick page, and the player page carries the same
     sections; app.js leaves a `.cc-slot` there and this draws the chart
     into it, with no tap.

     WHICH CHARTS are his, not the bet's (Ethan, the same day: "we are
     showing only receptions for RBs and only carries for WR and TE").
     A bet the charts speak to (rushing, receiving, rush + rec yards, an
     anytime touchdown, a quarterback's passing plus rushing yards) asks
     for every chart he could have, and probe() leads with the one he
     does more of. A quarterback's throws lead his runs (the passing
     chart). College has its carries and, from 2025, the targets its
     play file names (a target chart: no air yards, no side of the
     field), so a college receiver leads with his targets as an NFL one
     does; a college quarterback has his runs. The order here only breaks
     a tie and names the chart when he has neither. */
  function kindsFor(sport, mkt, pos) {
    const m = String(mkt || ""), p = String(pos || "").toUpperCase();
    const runs = /rush|anytime/.test(m), catches = /rec|anytime/.test(m);
    const wide = p === "WR" || p === "TE";
    /* HIS ROLE beside every league's own chart (2026-10-14): how much he
       is used, game by game (engine/role). Offered after the chart of
       what he did with it, never ahead of it (probe), and only where a
       player bet has a chart at all. */
    const role = (ks) => ks.concat("role");
    /* Baseball's chart is the bet's side of the ball: a pitcher's
       strikeouts or outs draw every pitch he threw, a hitter's bet every
       ball he put in play (engine/mlb/charts). */
    if (sport === "mlb") return m ? role(/^(strikeouts|outs)$|pitcher|earned_runs|_allowed/.test(m) ? ["pitches"] : ["spray"]) : [];
    /* A basketball player's chart is his shots, whatever the bet: his
       points, threes and the combos are made there, and his rebounds and
       assists ride the same minutes (engine/nba/shots). The WNBA has no
       play file stored: her role. */
    if (sport === "nba") return m ? role(["shots"]) : [];
    if (sport === "wnba") return m ? ["role"] : [];
    /* A fighter's chart is every fight on his record (engine/ufc/history). */
    if (sport === "ufc") return ["fights"];
    /* Hockey's is the bet's side of the puck: a goalie's saves or goals
       against draw every shot he faced, a skater's bet every shot he took
       (engine/nhl/charts). */
    if (sport === "nhl") return m ? role(/save|goals_against|goalie/.test(m) ? ["saves"] : ["shotmap"]) : [];
    if (sport !== "nfl" && sport !== "cfb") return [];
    /* A quarterback's own chart is his throws, whatever the bet; his runs
       are the other (2026-10-13). A passing bet with no position on the
       row asks for both too, and the numbers decide. College has no
       passing chart: a college quarterback has his runs and his role. */
    /* A kicker's chart is every kick he tried (engine/kicks), 2026-10-14. */
    if (sport === "nfl" && (p === "K" || /^(kick_pts|fg_made)$|kicking|field_goal/.test(m))) return ["kicks"];
    if (sport === "cfb" && p === "QB") return runs ? role(["carries"]) : ["role"];
    if (sport === "nfl" && (p === "QB" || (!p && /^pass/.test(m)))) return role(["passes", "carries"]);
    if (!runs && !catches) return sport === "cfb" && /^pass/.test(m) ? ["role"] : [];
    const back = p === "RB" || p === "FB" || p === "HB";
    return role(wide || (!back && !runs) ? ["routes", "carries"] : ["carries", "routes"]);
  }
  //: The charts whose zones the matchup view reads tonight's opponent on.
  const MATCHED = new Set(["carries", "routes", "passes", "shots", "shotmap", "saves", "spray", "pitches"]);
  function kindBar() {
    if (!C || !C.kinds || C.kinds.length < 2) return "";
    const n = C.counts || {};
    return `<div class="cc-kinds" role="group" aria-label="Which chart">${C.kinds.map((k) =>
      `<button type="button" class="cc-chip${k === S.kind ? " on" : ""}" data-ck="${k}" aria-pressed="${k === S.kind}">${esc(kindOf(k, S.sport).chip)}${k === "matchup" ? `<small>vs ${esc(S.opp || "")}</small>` : n[k] ? `<small>${n[k]}</small>` : ""}</button>`).join("")}</div>`;
  }
  //: What a chart shows, in a line: the pick page's section heading, the overlay's line under his name.
  function descOf(kind, sport) {
    const K = kindOf(kind, sport);
    if (K.sec) return K.sec;
    return kind === "routes" ? "every pass thrown to him: how far, which side, caught or not, and the yards after"
      : sport === "cfb" ? "every run he made: how far it went, and when in the game"
        : "every run he made: the hole, how far it went, and where on the field";
  }
  //: The section's own heading, kept short of the page's "why?" fold.
  function secHTML(c) {
    const R = c.S.kind === "routes", K = kindOf(c.S.kind, c.S.sport);
    return `${esc(K.sec ? K.title : R ? "Route chart" : "Carry chart")} <span class="sub">— ${esc(descOf(c.S.kind, c.S.sport))}.</span>`;
  }
  const waitHTML = () => `<div class="cc-empty">Loading ${esc(S.player)}’s ${esc(kindOf(S.kind, S.sport).noun)}…</div>`;
  //: A chart's state; a switch keeps the view, the face and tonight's opponent.
  const fresh = (sport, kind, player, from) => ({ sport, kind, player, data: null, view: from ? from.view : "game", gi: 0,
                                                 sel: -1, hint: from ? from.hint : "", opp: from ? from.opp : "",
                                                 fam: from ? from.fam : "" });

  function pick(c, kind) {
    if (!c.kinds || !c.kinds.includes(kind) || kind === c.S.kind) return;
    if (c.key) MEM.set(c.key, kind);
    c.S = fresh(c.S.sport, kind, c.S.player, c.S);
    use(c);
    const sec = c.root.querySelector(".cc-sec");
    if (sec) sec.innerHTML = secHTML(c);
    c.root.querySelector(".cc-body").innerHTML = kindBar() + waitHTML();
    load(c, null);
  }

  /* The slot names the player, the league, the market and his position.
     Drawn once per slot: a page redrawn around it hands the same element
     back (app.js keeps it), so the game he picked and the folds he opened
     survive the minute's refresh. The data is asked for as the chart
     comes within a screen or so of view — a pick page read only at its
     top costs the server nothing. */
  function mount(el) {
    if (!el || !el.dataset || el.dataset.on) return;
    el.dataset.on = "1";
    const d = el.dataset, sport = String(d.lg || "nfl").toLowerCase();
    const kinds = kindsFor(sport, d.mkt, d.pos);
    if (!kinds.length || !d.cc) { el.hidden = true; return; }
    /* Tonight's opponent beside his chart, wherever the pick names one and
       his chart has zones to read it on (not a kick or a role alone). */
    if (d.opp && kinds.some((k) => MATCHED.has(k))) kinds.push("matchup");
    const key = [sport, d.cc, d.mkt].join("|");
    const c = { root: el, inline: true, seq: 0, cand: kinds, kinds: null, key,
                S: fresh(sport, kinds[0], d.cc, { view: "game", hint: "", opp: d.opp || "", fam: kinds[0] }) };
    el._cc = use(c);
    el.innerHTML = `<div class="section-title minor cc-sec">${secHTML(c)}</div>
      <div class="card cc-inline"><div class="cc-body">${kindBar()}${waitHTML()}</div></div>`;
    bind(el);
    if (typeof IntersectionObserver !== "function") return probe(c);
    io = io || new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      const k = e.target._cc;
      if (k && k.root === e.target && !k.seq) probe(k);
    }), { rootMargin: "800px 0px" });
    io.observe(el);
  }

  /* What a league's own module draws with: the page's helpers and the
     chart being drawn (its selection), and the call that registers it. */
  const plug = { draw: (kind, spec) => { DRAW[kind] = spec; },
                 h: { esc, tile, tableHTML, pct, num1, signed, ord, fold, state: () => S,
                      grid: gridHTML, two, pills, bars: barList, hero: heroShell, cap,
                      /* a league's own page (`page`) builds with the frame's parts */
                      face: (d) => faceHTML(d, S), team: teamOf, ink: inkOf, seasonName,
                      seg: (Z) => segHTML(kindOf(S.kind, S.sport), Z),
                      tools: (items, flags, filters) => toolsHTML(S.kind, items, flags, filters),
                      stats: statsCard, splits: splitsCard } };
  window.QBCarry = { open, close, mount, plug, _t: { proj, runPoints, yMaxFor, fan, chipLabel, gameTitle, spot, downDist,
                                         gameChart, seasonChart, listHTML, noteHTML, tilesFor,
                                         catchXs, routePoints, routeGameChart, routeSeasonChart, routeList,
                                         routeTiles, routeTables, routeNote, routeLegend,
                                         faceHTML, faceStep, inits, kindsFor, doorKinds, tally,
                                         KIND, DRAW, passGameChart, passSeasonChart, passTiles, passList,
                                         passTables, passChip, kindOf, cfbTargetGame, cfbTargetSeason,
                                         cfbTargetTiles, cfbTargetNote, heroHTML, sideOf, sidesHTML, carryResult,
                                         carryFlags, targetFlags, csvOf, routeViews, routeBars, descOf,
                                         gridHTML, barList, segHTML, poolOf, zonesOf, toolsHTML, heroShell } };
})();
