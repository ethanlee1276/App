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
    carries: { chip: "Carries", title: "Carry chart", noun: "carries", one: "carry", where: "where he runs" },
    routes: { chip: "Targets", title: "Route chart", noun: "targets", one: "target", where: "where he’s thrown to" },
    passes: { chip: "Passes", title: "Passing chart", noun: "throws", one: "throw", where: "where he throws",
              sec: "every throw he made: how far, which side, complete or not, and the sacks he took" },
  };
  /* A league whose file says less than the NFL's gets its own names for
     the same chart: college targets have no air yards, no side of the
     field and no route, so they are a target chart, not a route chart. */
  KIND["routes@cfb"] = { chip: "Targets", title: "Target chart", noun: "targets", one: "target",
                         where: "every target",
                         sec: "every pass thrown his way that the play file names: caught or not, the yards, the down and where on the field" };
  const kindOf = (kind, sport) => KIND[`${kind}@${sport}`] || KIND[kind] || KIND.carries;
  //: The charts drawn by registered parts (`plugView`), by kind.
  const DRAW = {};

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

  /* ---------------- the field ---------------- */
  function fieldSVG(ymax, laneLabels, ticks) {
    const lines = [];
    for (let y = YMIN; y <= ymax; y += 5) {
      if (y === 0) continue;
      const a = proj(-SIDE, y, ymax), b = proj(SIDE, y, ymax);
      lines.push(`<line class="cc-yd${y % 10 ? " minor" : ""}" x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}"
        x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}"/>`);
      if (y > 0 && y % 10 === 0) {
        lines.push(`<text class="cc-ydl" x="${(a[0] - 8).toFixed(1)}" y="${(a[1] + 5).toFixed(1)}" text-anchor="end">+${y}</text>
          <text class="cc-ydl" x="${(b[0] + 8).toFixed(1)}" y="${(b[1] + 5).toFixed(1)}">+${y}</text>`);
      }
    }
    const tl = proj(-SIDE, ymax, ymax), tr = proj(SIDE, ymax, ymax);
    const bl = proj(-SIDE, YMIN, ymax), br = proj(SIDE, YMIN, ymax);
    const l0 = proj(-SIDE, 0, ymax), r0 = proj(SIDE, 0, ymax);
    const lanes = (laneLabels || []).map(([x, t]) => {
      const p = proj(x, -9.2, ymax);
      return `<text class="cc-lane" x="${p[0].toFixed(1)}" y="${p[1].toFixed(1)}" text-anchor="middle">${esc(t)}</text>`;
    }).join("");
    const tk = (ticks || []).map(([x, t]) => {
      const p = proj(x, -9.2, ymax);
      return `<text class="cc-lane" x="${p[0].toFixed(1)}" y="${p[1].toFixed(1)}">${esc(t)}</text>`;
    }).join("");
    return `<polygon class="cc-turf" points="${pt(bl)} ${pt(br)} ${pt(tr)} ${pt(tl)}"/>
      ${lines.join("")}
      <line class="cc-los" x1="${l0[0].toFixed(1)}" y1="${l0[1].toFixed(1)}" x2="${r0[0].toFixed(1)}" y2="${r0[1].toFixed(1)}"/>
      <text class="cc-losl" x="${(l0[0] - 8).toFixed(1)}" y="${(l0[1] + 4).toFixed(1)}" text-anchor="end">LOS</text>
      <text class="cc-losl" x="${(r0[0] + 8).toFixed(1)}" y="${(r0[1] + 4).toFixed(1)}">LOS</text>
      ${lanes}${tk}`;
  }

  /* One carry's line and its marks. `i` is the carry's index in the
     list under the chart, so a tap on either finds the other. */
  function runSVG(i, pts, c, ymax, extra) {
    const end = proj(pts[pts.length - 1][0], pts[pts.length - 1][1], ymax);
    const cls = `cc-run ${c.band}${extra || ""}${S && S.sel === i ? " sel" : ""}`;
    const delay = Math.min(i * 45, 900);
    let marks = "";
    if (c.td) marks += `<circle class="cc-td" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="6"/>`;
    if (c.fl) marks += `<g class="cc-fum"><circle cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="6"/>
      <path d="M${(end[0] - 3).toFixed(1)} ${(end[1] - 3).toFixed(1)} l6 6 m0 -6 l-6 6"/></g>`;
    return `<g class="cc-carry" data-i="${i}">
      <path class="cc-hit" d="${pathD(pts, ymax)}"/>
      <path class="${cls}" d="${pathD(pts, ymax)}" pathLength="1" style="animation-delay:${delay}ms"/>
      ${marks}</g>`;
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
      return svgWrap(fieldSVG(ymax, HOLES.map((h) => [LANE[h], h])) + body, g, sport, cs.length);
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
        after = `<path class="rc-yac" d="${pathD([[cx, cy], [cx, ey]], ymax)}" pathLength="1" style="animation-delay:${delay + 420}ms"/>`;
        end = proj(cx, ey, ymax);
      }
      marks += `<circle class="rc-catch" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="3.4"/>`;
    } else if (t.int) {
      marks += `<g class="rc-int"><path d="M${(c[0] - 5).toFixed(1)} ${(c[1] - 5).toFixed(1)} l10 10 m0 -10 l-10 10"/></g>`;
    } else {
      marks += `<circle class="rc-miss" cx="${c[0].toFixed(1)}" cy="${c[1].toFixed(1)}" r="4"/>`;
    }
    if (t.td) marks += `<circle class="cc-td" cx="${end[0].toFixed(1)}" cy="${end[1].toFixed(1)}" r="7"/>`;
    return `<g class="cc-carry" data-i="${i}">
      <path class="cc-hit" d="${pathD(pts, ymax)}"/>
      <path class="${cls}" d="${pathD(pts, ymax)}" pathLength="1" style="animation-delay:${delay}ms"/>
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
  function tile(k, v, sub) {
    return `<div class="cc-tile"><span class="cc-k">${esc(k)}</span><b>${esc(v)}</b>${sub ? `<i>${esc(sub)}</i>` : ""}</div>`;
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
  function listHTML(g, sport) {
    return `<div class="cc-list" role="list">${(g.carries || []).map((c, i) => {
      const tags = [c.sc ? "Scramble" : "", c.td ? "TD" : "", c.fl ? (sport === "nfl" ? "Fumble lost" : "Fumbled") : "",
                    c.fd && !c.td ? "1st down" : ""].filter(Boolean);
      return `<button type="button" role="listitem" class="cc-row${S && S.sel === i ? " sel" : ""}" data-i="${i}">
        <i class="dot ${c.band}"></i>
        <span class="cc-r-q">${esc(qLabel(c))}</span>
        <span class="cc-r-dd">${esc([downDist(c), spot(c, g)].filter(Boolean).join(" · "))}</span>
        <span class="cc-r-h">${esc(c.h ? HOLE_NAME[c.h] : (sport === "nfl" ? "Hole not recorded" : ""))}</span>
        <b class="cc-r-y ${c.band}">${signed(c.y)}</b>
        ${tags.length ? `<span class="cc-r-tags">${tags.map((t) => `<em>${esc(t)}</em>`).join("")}</span>` : ""}
      </button>`;
    }).join("")}</div>`;
  }
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
    const t = [tile("Targets–Rec", `${line.tgt}-${line.rec}`), tile("Yards", Math.round(line.yds)), tile("TD", line.td),
               tile("YAC", Math.round(line.yac)), tile("aDOT", num1(line.adot))];
    // Separation where the league published it (5+ targets in a game);
    // first downs where it did not — never an estimate in its place.
    if (ngs && ngs.separation != null) t.push(tile("Separation", `${num1(ngs.separation)}`, "NGS · yds"));
    else t.push(tile("1st downs", line.first));
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
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
  function routeList(g) {
    return `<div class="cc-list" role="list">${(g.targets || []).map((t, i) => {
      const res = t.int ? "INT" : t.c ? signed(t.y) : "Inc";
      const band = t.int ? "loss" : t.c ? "gain" : "miss";
      const yac = t.c ? Math.round(yacOf(t)) : 0;
      const tags = [t.td ? "TD" : "", t.fd && !t.td ? "1st down" : "",
                    t.c && yac ? `${yac} yd${Math.abs(yac) === 1 ? "" : "s"} after catch` : "",
                    ...(t.fl || []).map((w) => FTN_TAG[w] || ""), covWords(t)].filter(Boolean);
      return `<button type="button" role="listitem" class="cc-row${S && S.sel === i ? " sel" : ""}" data-i="${i}">
        <i class="dot ${band}"></i>
        <span class="cc-r-q">${esc(qLabel(t))}</span>
        <span class="cc-r-dd">${esc([downDist(t), spot(t, g)].filter(Boolean).join(" · "))}</span>
        <span class="cc-r-h">${esc([ROUTE_NAME[t.rt] || "", airWords(t)].filter(Boolean).join(" · ") || zoneWord(t))}</span>
        <b class="cc-r-y ${band}">${esc(res)}</b>
        ${tags.length ? `<span class="cc-r-tags">${tags.map((x) => `<em>${esc(x)}</em>`).join("")}</span>` : ""}
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
    const t = [tile("Targets–Rec", `${line.tgt}-${line.rec}`), tile("Yards", Math.round(line.yds)), tile("TD", line.td),
               tile("Yds/catch", line.rec ? num1(line.yds / line.rec) : "—"), tile("Catch rate", pct(line.catch)),
               tile("1st downs", line.first)];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
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

  function render() {
    const ov = C && C.root;
    if (!ov || !S) return;
    const d = S.data;
    const box = ov.querySelector(".cc-body");
    const R = S.kind === "routes";
    const K = kindOf(S.kind, S.sport), P = DRAW[S.kind];
    if (!d || !d.games || !d.games.length) {
      /* No one in the league has a row yet: the charts are being filled
         (engine/chartfill), which is not the same as none for him. The
         switch stays above it on a pick page, so the other chart is a
         tap away. */
      box.innerHTML = kindBar() + (d && d.filling
        ? `<div class="cc-empty">${esc(K.title)}s are still being filled: every ${esc(K.one)} is read from the ${S.sport === "cfb" ? "college" : "league’s"} play-by-play, which takes a few minutes. Check back shortly.</div>`
        : R
          ? `<div class="cc-empty">No targets on file for ${esc(S.player)}.</div>`
          : P ? `<div class="cc-empty">No ${esc(K.noun)} on file for ${esc(S.player)}.</div>`
            : `<div class="cc-empty">No carries on file for ${esc(S.player)}${S.sport === "cfb" ? " in the college play-by-play" : ""}.</div>`);
      return;
    }
    const sport = d.sport;
    const seasons = d.seasons.length > 1 ? `<div class="cc-seasons" role="group" aria-label="Season">${d.seasons.map((y) =>
      `<button type="button" class="cc-chip${y === d.season ? " on" : ""}" data-season="${y}" aria-pressed="${y === d.season}">${y}</button>`).join("")}</div>` : "";
    /* On a pick page the page above already says who he is, so the chart
       opens on its switches instead of a second header with his face. */
    /* His two charts' switch: on a pick page beside the seasons, in the
       overlay (a door that asked for his chart) under his name. */
    const kb = kindBar();
    const bar = C.inline ? kb + seasons : kb;
    const head = (C.inline ? "" : `<header class="cc-head">
        ${faceHTML(d, S)}
        <div class="cc-who">
          <span class="cc-eyebrow">${esc(K.title)}</span>
          <h2 class="cc-name">${esc(d.player)}</h2>
          <span class="cc-sub">${[d.jersey ? `#${esc(d.jersey)}` : "", esc(d.position || ""), d.team
            ? `${teamMarkIn(sport, d.team, 16)} ${esc(teamNameIn(sport, d.team))}` : ""].filter(Boolean).join(" · ")}</span>
        </div>
        ${seasons}
      </header>`) + (bar ? `<div class="cc-bar">${bar}</div>` : "") + `
      <div class="cc-tabs" role="tablist">
        <button type="button" role="tab" class="cc-tab${S.view === "game" ? " on" : ""}" data-view="game" aria-selected="${S.view === "game"}">By game</button>
        <button type="button" role="tab" class="cc-tab${S.view === "season" ? " on" : ""}" data-view="season" aria-selected="${S.view === "season"}">${d.season} · ${esc(K.where)}</button>
      </div>`;
    /* Four parts in every view: what sits above the drawing (the games,
       the title), the drawing, what reads it (the legend, the numbers)
       and the long tail. The overlay stacks them as it always has; a
       pick page's card, when it is wide, sets the drawing and its
       numbers side by side (.cc-split) so the field is not drawn a
       screen tall across a desktop. */
    let top, fig, side, tail;
    if (P) {
      ({ top, fig, side, tail } = plugView(P, d, sport));
    } else if (S.view === "season" && R && d.air === false) {
      const L = d.season_line;
      top = `<div class="cc-title">${esc(`${d.season} season · ${L.tgt} targets in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      fig = `<div class="cc-stage">${cfbTargetSeason(d)}</div>`;
      side = `${cfbTargetLegend()}
        ${cfbTargetTiles(L)}
        <div class="cc-tiles cc-tiles-2">${tile("Yds/target", num1(L.ypt))}${tile("Targets a game", num1(L.tgt / d.games.length))}${tile("Red zone targets", redZone(d))}${tile("Long", L.long == null ? "—" : Math.round(L.long))}</div>`;
      tail = fold("splits", "Every split · down, field position", routeTables(d));
    } else if (S.view === "season" && R) {
      const L = d.season_line;
      top = `<div class="cc-title">${esc(`${d.season} season · ${L.tgt} targets in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      fig = `<div class="cc-stage">${routeSeasonChart(d)}</div>`;
      side = `${routeLegend(d.routes, true)}
        ${routeTiles(L, d.ngs)}
        <div class="cc-tiles cc-tiles-2">${tile("Catch rate", pct(L.catch))}${tile("Yds/target", num1(L.ypt))}${tile("Contested won", `${L.contested_won}/${L.contested}`)}${tile("Drops", L.drops)}</div>
        ${routeNgs(d)}`;
      tail = fold("splits", "Every split · depth, side, route, coverage, down", routeTables(d));
    } else if (S.view === "season") {
      const any = d.games.some((g) => g.carries.some((c) => !c.h)) && d.holes;
      top = `<div class="cc-title">${esc(`${d.season} season · ${d.season_line.n} carries in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>`;
      fig = `<div class="cc-stage">${seasonChart(d)}</div>`;
      side = `${legendHTML(sport, any)}
        ${tilesFor(d.season_line, (d.ngs || {}).ryoe)}
        <div class="cc-tiles cc-tiles-2">${tile("Success", pct(d.season_line.success))}${tile("Stuffed (0 or less)", pct(d.season_line.stuffed))}${tile("10+ yd runs", d.season_line.explosive)}${tile("Long", d.season_line.long == null ? "—" : Math.round(d.season_line.long))}</div>
        ${ngsLine(d)}`;
      tail = fold("splits", `Every split · ${d.holes ? "hole, " : ""}down, field position`, seasonTables(d));
    } else {
      const g = d.games[Math.min(S.gi, d.games.length - 1)];
      top = `<div class="cc-games" role="tablist" aria-label="Games">${d.games.map((x, i) =>
          `<button type="button" role="tab" class="cc-chip${i === S.gi ? " on" : ""}" data-gi="${i}" aria-selected="${i === S.gi}">${esc(chipLabel(x, sport))}<small>${esc(tally(R ? x.line.rec : x.line.n, x.line.yds))}</small></button>`).join("")}</div>
        <div class="cc-title">${esc(gameTitle(g, sport, d.season))}</div>`;
      if (R && d.air === false) {
        fig = `<div class="cc-stage">${cfbTargetGame(g)}<div class="cc-tip" hidden></div></div>`;
        side = `${cfbTargetLegend()}
          ${cfbTargetTiles(g.line)}`;
        tail = fold("list", `Every target, in order · ${g.targets.length}`, routeList(g));
      } else if (R) {
        fig = `<div class="cc-stage">${routeGameChart(g)}<div class="cc-tip" hidden></div></div>`;
        side = `${routeLegend(g.targets.some((t) => t.rt), false)}
          ${routeTiles(g.line, g.ngs)}`;
        tail = fold("list", `Every target, in order · ${g.targets.length}`, routeList(g));
      } else {
        const any = d.holes && g.carries.some((c) => !c.h);
        fig = `<div class="cc-stage">${gameChart(g, sport, d.holes)}<div class="cc-tip" hidden></div></div>`;
        side = `${legendHTML(sport, any)}
          ${tilesFor(g.line, g.ryoe)}`;
        tail = fold("list", `Every carry, in order · ${g.carries.length}`, listHTML(g, sport));
      }
    }
    const main = top + (C.inline ? `<div class="cc-split"><div class="cc-fig">${fig}</div><div class="cc-side">${side}</div></div>` : fig + side) + tail;
    box.innerHTML = head + main + fold("note", "How it’s drawn",
      P ? P.note(d) : R ? (d.air === false ? cfbTargetNote(d) : routeNote(d)) : noteHTML(d));
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
  }

  /* ON A PICK PAGE THE LONG TAIL FOLDS: every carry or target in order,
     and the season's split tables, one tap away under the chart and its
     numbers, so the page around them stays readable. The overlay is the
     chart and nothing else, so it shows them open, as before. A fold
     the reader opened stays open while he moves between games. */
  function fold(key, title, html) {
    if (!C.inline || !html) return html;
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
      return { top: `<div class="cc-title">${esc(`${d.season} season · ${P.count(d.season_line)} in ${n} game${n === 1 ? "" : "s"}`)}</div>`,
               fig: `<div class="cc-stage">${P.season(d)}</div>`,
               side: P.seasonSide(d),
               tail: fold("splits", P.splitsTitle, P.splits(d)) };
    }
    const g = d.games[Math.min(S.gi, d.games.length - 1)];
    return { top: `<div class="cc-games" role="tablist" aria-label="Games">${d.games.map((x, i) =>
                `<button type="button" role="tab" class="cc-chip${i === S.gi ? " on" : ""}" data-gi="${i}" aria-selected="${i === S.gi}">${esc(chipLabel(x, sport))}<small>${esc(P.chip(x))}</small></button>`).join("")}</div>
              <div class="cc-title">${esc(gameTitle(g, sport, d.season))}</div>`,
             fig: `<div class="cc-stage">${P.game(g, d)}<div class="cc-tip" hidden></div></div>`,
             side: P.gameSide(g, d),
             tail: fold("list", `Every ${P.one}, in order · ${P.items(g).length}`, P.list(g, d)) };
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
      const t = g && P.items(g)[i];
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
    const q = `${api}${encodeURIComponent(sport)}&player=${encodeURIComponent(player)}${season ? `&season=${season}` : ""}`;
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
  const vol = (kind, d) => (d && d.games && d.games.length
    ? Number((d.season_line || {})[kind === "routes" ? "tgt" : "n"]) || 0 : 0);
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
    render();
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
      const got = c.cand.map((k, i) => ({ k, d: ds[i], v: vol(k, ds[i]) })).filter((x) => x.v > 0)
        .sort((a, b) => b.v - a.v);
      const lead = got[0];
      const shown = got.filter((x) => x === lead || (x.v >= SECOND_MIN && x.d.season === lead.d.season));
      c.kinds = shown.length ? shown.map((x) => x.k) : [c.cand[0]];
      c.counts = {};
      shown.forEach((x) => { c.counts[x.k] = x.v; });
      const want = MEM.get(c.key);
      const kind = c.kinds.includes(want) ? want : c.kinds[0];
      c.S = Object.assign(fresh(c.S.sport, kind, c.S.player), { view: c.S.view, hint: c.S.hint });
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
      const row = hit(e, ".cc-row, .cc-carry");
      if (row && S.view === "game") return select(+row.dataset.i);
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

  function open(player, sport, kind, face) {
    if (!player) return;
    let ov = document.getElementById("cc-overlay");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "cc-overlay";
      document.body.appendChild(ov);
      bind(ov);
    }
    /* "auto" is a door that does not know his position (the parlay
       checker's legs): both of his charts are asked for and his own
       leads, as on a pick page (probe). */
    const auto = kind === "auto", lg = String(sport || "nfl").toLowerCase();
    const k0 = KIND[kind] ? kind : "carries", K = kindOf(k0, lg);
    ov._cc = use({ root: ov, inline: false, seq: 0, kinds: null, key: "",
                   cand: auto ? (lg === "nfl" ? ["carries", "routes", "passes"] : ["carries", "routes"]) : null,
                   S: { sport: lg, kind: k0, player, data: null,
                        view: "game", gi: 0, sel: -1, hint: face || "" } });
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
    if (sport !== "nfl" && sport !== "cfb") return [];
    /* A quarterback's own chart is his throws, whatever the bet; his runs
       are the other (2026-10-13). A passing bet with no position on the
       row asks for both too, and the numbers decide. College has no
       passing chart: a college quarterback has his runs. */
    if (sport === "cfb" && p === "QB") return runs ? ["carries"] : [];
    if (sport === "nfl" && (p === "QB" || (!p && /^pass/.test(m)))) return ["passes", "carries"];
    if (!runs && !catches) return [];
    const back = p === "RB" || p === "FB" || p === "HB";
    return wide || (!back && !runs) ? ["routes", "carries"] : ["carries", "routes"];
  }
  function kindBar() {
    if (!C || !C.kinds || C.kinds.length < 2) return "";
    const n = C.counts || {};
    return `<div class="cc-kinds" role="group" aria-label="Which chart">${C.kinds.map((k) =>
      `<button type="button" class="cc-chip${k === S.kind ? " on" : ""}" data-ck="${k}" aria-pressed="${k === S.kind}">${esc(kindOf(k, S.sport).chip)}${n[k] ? `<small>${n[k]}</small>` : ""}</button>`).join("")}</div>`;
  }
  //: The section's own heading, kept short of the page's "why?" fold.
  function secHTML(c) {
    const R = c.S.kind === "routes", K = kindOf(c.S.kind, c.S.sport);
    if (K.sec) return `${esc(K.title)} <span class="sub">— ${esc(K.sec)}.</span>`;
    return `${R ? "Route chart" : "Carry chart"} <span class="sub">— ${R
      ? "every pass thrown to him: how far, which side, caught or not, and the yards after"
      : c.S.sport === "cfb" ? "every run he made: how far it went, and when in the game"
        : "every run he made: the hole, how far it went, and where on the field"}.</span>`;
  }
  const waitHTML = () => `<div class="cc-empty">Loading ${esc(S.player)}’s ${esc(kindOf(S.kind, S.sport).noun)}…</div>`;
  const fresh = (sport, kind, player) => ({ sport, kind, player, data: null, view: "game", gi: 0, sel: -1, hint: "" });

  function pick(c, kind) {
    if (!c.kinds || !c.kinds.includes(kind) || kind === c.S.kind) return;
    if (c.key) MEM.set(c.key, kind);
    c.S = Object.assign(fresh(c.S.sport, kind, c.S.player), { view: c.S.view, hint: c.S.hint });
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
    const key = [sport, d.cc, d.mkt].join("|");
    const c = { root: el, inline: true, seq: 0, cand: kinds, kinds: null, key, S: fresh(sport, kinds[0], d.cc) };
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

  window.QBCarry = { open, close, mount, _t: { proj, runPoints, yMaxFor, fan, chipLabel, gameTitle, spot, downDist,
                                         gameChart, seasonChart, listHTML, noteHTML, tilesFor,
                                         catchXs, routePoints, routeGameChart, routeSeasonChart, routeList,
                                         routeTiles, routeTables, routeNote, routeLegend,
                                         faceHTML, faceStep, inits, kindsFor, tally,
                                         KIND, DRAW, passGameChart, passSeasonChart, passTiles, passList,
                                         passTables, passChip, kindOf, cfbTargetGame, cfbTargetSeason,
                                         cfbTargetTiles, cfbTargetNote } };
})();
