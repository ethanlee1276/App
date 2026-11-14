/* Qellys Book — basketball's chart (js/chart-hoops.js): the shot chart.
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done, then make sure they are all routed correctly like nfl." Loaded by
   js/carrychart.js the first time a basketball chart is drawn, and drawn
   in its frame (the games row, the By game | season tabs, the numbers
   beside the drawing, every shot in order, the splits and how it is
   drawn), so a guard's chart reads like a back's.

   THE SHOT CHART (kind "shots", engine/nba/shots.chart): every shot he
   took, where it was taken on the half court (the league's own court
   coordinates), made or missed, with the kind of shot, its distance, the
   assist and the block. A free throw has no spot on the floor: listed,
   not drawn. The season view shades nothing it did not count: each zone's
   own percentage, beside the league's in the same zone.

   IN THE FRAME OF ETHAN'S NFL RENDERS (2026-10-14: "go match it with all
   the other sports too, but obviously make sense and correlate it with
   that sport"): the court drawn dark with its lines lit and the paint in
   his team's colour, a make a lit dot and a miss a cross (the league's own
   shot-chart marks), the paint, mid-range and threes as the render's
   Left | Middle | Right with their counts, his zones shaded hot or cold
   against the league's, Zones | Shot type | Distance as the route chart's
   other views, and every shot in the render's table, filtered and
   downloadable.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, state, grid, two, pills, bars } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const QUAL = { fastbreak: "Fast break", "2ndchance": "Second chance", fromturnover: "Off a turnover",
                 pointsinthepaint: "In the paint" };
  const ZONE = { ra: "Restricted area", paint: "In the paint", mid: "Mid-range", corner3: "Corner 3",
                 above3: "Above the break 3" };
  const kindWord = (s) => (s.k === "3pt" ? "3" : s.k === "2pt" ? "2" : "free throw");
  /* College plays two halves (2026-11-13): H1, H2, then overtime. */
  const isCollege = (d) => !!(d && d.sport === "cbb");
  const period = (p, d) => {
    const reg = isCollege(d) ? 2 : 4, mark = isCollege(d) ? "H" : "Q";
    return !p ? "" : p <= reg ? `${mark}${p}` : p === reg + 1 ? "OT" : `${p - reg}OT`;
  };
  const when = (s, d) => [period(s.p, d), s.c].filter(Boolean).join(" ");
  const what = (s) => (s.k === "ft" ? `Free throw${s.t ? ` ${s.t}` : ""}`
    : [s.t, s.ds].filter(Boolean).join(" · ") || "Shot");
  const result = (s) => (s.k === "ft" ? (s.m ? "Made FT" : "Missed FT") : `${s.m ? "Made" : "Missed"} ${kindWord(s)}`);
  const quals = (s) => String(s.q || "").split(",").filter((q) => q && q !== "pointsinthepaint").map((q) => QUAL[q] || "")
    .filter(Boolean);
  const assist = (s) => (s.m && s.a ? `Assisted by ${s.a}` : "");
  const tags = (s) => [assist(s), s.b ? "Blocked" : "", ...quals(s)].filter(Boolean);
  const feet = (d) => (d == null ? "" : `${Math.round(d)} ft`);
  const points = (s) => (!s.m ? 0 : s.k === "3pt" ? 3 : s.k === "2pt" ? 2 : 1);

  /* ---------------- the zones ----------------
     The render's Left | Middle | Right, for a shooter: the paint (the
     restricted area and the rest of the lane), mid-range and threes. A
     free throw has no spot on the floor, so it is in none of them and is
     not counted under the court. */
  const ZONE_OF = { ra: "P", paint: "P", mid: "M", corner3: "3", above3: "3" };
  const zones = {
    label: "Where on the floor",
    list: [["P", "Paint", "In the paint"], ["M", "Mid-range", "Mid-range"], ["3", "3PT", "Threes"]],
    of: (s) => (s.k === "ft" ? "" : ZONE_OF[s.z] || ""),
    pool: (g) => (g.shots || []).filter((s) => s.k !== "ft"),
  };

  /* ---------------- the court ---------------- */
  /* The league's court coordinates: tenths of a foot, the middle of the
     basket at 0, 0, the baseline at -47.5. Drawn with the basket at the
     top, out to 36 feet from it: a heave from farther sits on the edge
     (the list has its distance). Dark boards, the lines lit — a faint
     wide copy under each, no filter — and the lane in his colour. */
  const X = (x) => Math.max(4, Math.min(496, 250 + x));
  const Y = (y) => Math.max(4, Math.min(406, y + 47.5));
  /* EACH LEAGUE'S OWN COURT. The NBA's: a 16-foot lane, the three-point
     line 23 feet 9 inches out and 22 feet in the corners. College's
     (2026-11-13): a 12-foot lane and the line at 22 feet 1.75 inches, its
     straight corners 21 feet 7.75 inches out, meeting the arc 4.7 feet
     above the basket. The restricted arc, the free-throw line and its
     circle are the same on both. */
  const COURT = {
    nba: { lane: [170, 330], arc: "M30 0 V137 A237.5 237.5 0 0 0 470 137 V0", cx: [30, 470], cy: 137 },
    cbb: { lane: [190, 310], arc: "M33.5 0 V94.3 A221.5 221.5 0 0 0 466.5 94.3 V0", cx: [33.5, 466.5], cy: 94.3 },
  };
  const courtOf = (d) => COURT[isCollege(d) ? "cbb" : "nba"];
  const lines = (c) => `<path d="M${c.lane[0]} 190 V0 M${c.lane[1]} 0 V190 H${c.lane[0]}"/>
      <path d="M190 190 A60 60 0 0 0 310 190"/>
      <path d="M210 47.5 A40 40 0 0 0 290 47.5"/>
      <path d="${c.arc}"/>`;
  function courtSVG(d) {
    const c = courtOf(d);
    let planks = "";
    for (let x = 0, k = 0; x < 500; x += 25, k++) planks += `<rect class="nb-plank${k % 2 ? " alt" : ""}" x="${x}" y="0" width="25" height="410"/>`;
    return `<rect class="nb-floor" x="0" y="0" width="500" height="410"/>${planks}
      <rect class="nb-paint" x="${c.lane[0]}" y="0" width="${c.lane[1] - c.lane[0]}" height="190"/>
      <g class="nb-glow">${lines(c)}</g>
      <path class="nb-line" d="M190 190 A60 60 0 0 0 310 190"/>
      <path class="nb-line dash" d="M190 190 A60 60 0 0 1 310 190"/>
      <path class="nb-line" d="M210 47.5 A40 40 0 0 0 290 47.5"/>
      <path class="nb-arc" d="${c.arc}"/>
      <line class="nb-board" x1="220" y1="40" x2="280" y2="40"/>
      <circle class="nb-rim-glow" cx="250" cy="47.5" r="7.5"/>
      <circle class="nb-rim" cx="250" cy="47.5" r="7.5"/>`;
  }
  const svg = (body, label) =>
    `<svg class="cc-svg nb-svg" viewBox="0 0 500 410" role="img" aria-label="${esc(label)}">${body}</svg>`;
  //: A miss is a cross, as the league's own shot charts draw one.
  const cross = (x, y, r) => `M${(x - r).toFixed(1)} ${(y - r).toFixed(1)} l${2 * r} ${2 * r} m0 ${-2 * r} l${-2 * r} ${2 * r}`;
  function shotMark(s, i) {
    if (s.k === "ft" || s.x == null || s.y == null) return "";
    const x = X(s.x), y = Y(s.y), r = s.k === "3pt" ? 7 : 6;
    const mark = s.m
      ? `<circle class="nb-halo" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r + 5}"/><circle class="nb-shot cx-mark m${sel(i)}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}"/>`
      : `<path class="nb-shot cx-mark x${sel(i)}" d="${cross(x, y, r - 1)}"/>`;
    return `<g class="cc-carry" data-i="${i}" data-z="${zones.of(s)}"><circle class="nb-hit" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="12"/>${mark}</g>`;
  }
  function shotGame(g, d) {
    const shots = g.shots || [];
    const fga = shots.filter((s) => s.k !== "ft").length;
    return svg(courtSVG(d) + shots.map(shotMark).join(""),
      `Shot chart: ${fga} shot${fga === 1 ? "" : "s"} from the floor. Every shot and free throw is listed below.`);
  }
  /* THE SEASON, HOT AND COLD: each of the league's zones shaded by his
     percentage there against the league's (green hotter, red colder, as
     deep as his share of shots there), every shot faint over it, and each
     zone's own number on it — two corners each their own, the rest down
     the middle of the floor. */
  /* The zones as shapes on each league's own court (`COURT`). */
  function areas(d) {
    const c = courtOf(d), [l, r] = c.lane, [a, b] = c.cx, h = c.cy;
    return {
      ra: '<circle cx="250" cy="47.5" r="40"/>',
      paint: `<path d="M${l} 0 H${r} V190 H${l} Z M290 47.5 A40 40 0 1 0 210 47.5 A40 40 0 1 0 290 47.5 Z"/>`,
      mid: `<path d="${c.arc} Z M${l} 0 H${r} V190 H${l} Z"/>`,
      corner3: `<path d="M0 0 H${a} V${h} H0 Z M${b} 0 H500 V${h} H${b} Z"/>`,
      above3: `<path d="M0 0 H500 V410 H0 Z ${c.arc} Z M0 0 H${a} V${h} H0 Z M${b} 0 H500 V${h} H${b} Z"/>`,
    };
  }
  const temp = (z) => (!z || z.pct == null || z.league == null ? "even"
    : z.pct - z.league >= 0.02 ? "hot" : z.pct - z.league <= -0.02 ? "cold" : "even");
  const PILLS = { ra: [250, 72], paint: [250, 150], mid: [250, 238], above3: [250, 345] };
  function pill(x, y, made, att, t) {
    if (!att) return "";
    return `<g class="nb-pill"><rect x="${x - 34}" y="${y - 19}" width="68" height="36" rx="9"/>
      <text class="nb-pct ${t}" x="${x}" y="${y - 1}" text-anchor="middle">${pct(made / att)}</text>
      <text class="nb-att" x="${x}" y="${y + 12}" text-anchor="middle">${made} of ${att}</text></g>`;
  }
  function shotSeason(d) {
    const every = [];
    d.games.forEach((g) => (g.shots || []).forEach((s) => { if (s.k !== "ft" && s.x != null) every.push(s); }));
    const by = {};
    (d.zones || []).forEach((z) => { by[z.key] = z; });
    const most = Math.max(0.01, ...(d.zones || []).map((z) => z.share || 0));
    let body = courtSVG(d);
    const AREA = areas(d);
    Object.keys(AREA).forEach((k) => {
      const z = by[k];
      if (!z || !z.fga) return;
      body += `<g class="nb-zone ${temp(z)}" style="fill-opacity:${(0.1 + 0.32 * (z.share || 0) / most).toFixed(2)}">${AREA[k]}</g>`;
    });
    body += every.map((s) => {
      const x = X(s.x), y = Y(s.y);
      return s.m ? `<circle class="nb-shot faint m" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.6"/>`
        : `<path class="nb-shot faint x" d="${cross(x, y, 2.8)}"/>`;
    }).join("");
    const tally = {};
    every.forEach((s) => {
      const k = s.z === "corner3" ? (s.x < 0 ? "c3a" : "c3b") : s.z;
      const t = tally[k] = tally[k] || [0, 0];
      t[0] += s.m; t[1] += 1;
    });
    Object.entries(PILLS).forEach(([k, [x, y]]) => { if (tally[k]) body += pill(x, y, tally[k][0], tally[k][1], temp(by[k])); });
    if (tally.c3a) body += pill(46, 28, tally.c3a[0], tally.c3a[1], temp(by.corner3));
    if (tally.c3b) body += pill(454, 28, tally.c3b[0], tally.c3b[1], temp(by.corner3));
    return svg(body, `Shot chart: ${every.length} shots from the floor this season, by zone, against the league.`);
  }
  function legend(g) {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Made</span>
      <span><i class="dt nb-x">×</i>Missed</span>${g ? "" : `<span><i class="sw nb-hot"></i>Above the league</span>
      <span><i class="sw nb-cold"></i>Below the league</span>`}</div>`;
  }
  function gameTiles(g) {
    const L = g.line, B = g.box || {}, v = (x) => (x == null ? "—" : Math.round(x));
    const t = [tile("Points", L.pts), tile("FG", `${L.fgm}-${L.fga}`, pct(L.fg_pct)),
               tile("3PT", `${L.fg3m}-${L.fg3a}`, pct(L.fg3_pct)), tile("FT", `${L.ftm}-${L.fta}`, pct(L.ft_pct)),
               tile("Assisted", `${L.assisted} of ${L.fgm}`, "his makes"), tile("In the paint", L.paint, "shots")];
    if (Object.keys(B).length) {
      t.push(tile("Minutes", v(B.min)), tile("Rebounds", v(B.reb)), tile("Assists", v(B.ast)),
             tile("Steals", v(B.stl)), tile("Blocks", v(B.blk)), tile("Turnovers", v(B.tov)));
    }
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function seasonTiles(d) {
    const L = d.season_line;
    const t = [tile("Games", L.games), tile("Points", num1(L.ppg), "a game"), tile("FG", pct(L.fg_pct), `${num1(L.fga_pg)} a game`),
               tile("3PT", pct(L.fg3_pct), `${num1(L.fg3a_pg)} a game`), tile("FT", pct(L.ft_pct), `${L.ftm}-${L.fta}`),
               tile("Assisted", pct(L.fgm ? L.assisted / L.fgm : null), "of his makes")];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }

  /* EVERY SHOT AS THE RENDERS' TABLE: its number, the clock, the shot (its
     kind, and under it where and who set it up), the distance, how it
     ended and the points. On a phone the clock and the distance read
     under the shot. */
  const COLS = [{ h: "#", c: "cc-c-n", p: "18px", w: "26px" },
                { h: "Time", c: "cc-c-q", w: "64px" },
                { h: "Shot", c: "cc-c-m", p: "minmax(0,1fr)" },
                { h: "Shot", c: "cc-c-m", w: "minmax(0,1fr)" },
                { h: "Dist", c: "cc-c-v", w: "52px", r: 1 },
                { h: "Result", c: "cc-c-res", p: "92px", w: "190px" },
                { h: "Pts", c: "cc-c-y", p: "30px", w: "40px", r: 1 }];
  function shotList(g, d) {
    return grid("shots", COLS, (g.shots || []).map((s, i) => {
      const zone = s.k === "ft" ? "Free throw line" : ZONE[s.z] || "";
      const res = [[result(s), s.m ? "good" : "bad"]].concat(s.b ? [["Blocked", "bad"]] : []);
      return {
        i, f: flags(s),
        said: [when(s, d), what(s), feet(s.d), zone, result(s), ...tags(s)].filter(Boolean).join(", "),
        cells: [`${i + 1}`, esc(when(s, d) || "—"),
                two(what(s), [when(s, d), feet(s.d) || (s.k === "ft" ? "Line" : ""), assist(s), ...quals(s)].filter(Boolean).join(" · ")),
                two(what(s), [zone, assist(s), ...quals(s)].filter(Boolean).join(" · ")),
                esc(feet(s.d) || "—"), pills(res), [points(s) ? `+${points(s)}` : "—", s.m ? "gain" : "miss"]],
      };
    }));
  }
  const flags = (s) => (s.k === "ft" ? `ft ${s.m ? "m" : "x"}`
    : [s.m ? "m" : "x", s.k === "3pt" ? "3" : "", ZONE_OF[s.z] === "P" ? "paint" : "", s.m && s.a ? "ast" : "", s.b ? "blk" : ""]
      .filter(Boolean).join(" "));
  const FILTERS = [["", "All shots"], ["m", "Makes"], ["x", "Misses"], ["3", "Threes"], ["paint", "In the paint"],
                   ["ft", "Free throws"], ["ast", "Assisted"], ["blk", "Blocked"]];
  const csv = (g, d) => [["#", "Period", "Clock", "Kind", "Shot", "Descriptor", "Distance (ft)", "Zone", "Made", "Points",
                       "Assisted by", "Blocked", "Court x", "Court y"]]
    .concat((g.shots || []).map((s, i) => [i + 1, period(s.p, d), s.c, s.k === "ft" ? "FT" : s.k === "3pt" ? "3PT" : "2PT",
      s.t, s.ds, s.d == null ? "" : Math.round(s.d), s.k === "ft" ? "" : ZONE[s.z] || "", s.m ? 1 : 0, points(s),
      s.m ? s.a || "" : "", s.b ? 1 : 0, s.x == null ? "" : s.x, s.y == null ? "" : s.y]));

  function splitRows(rows) {
    return rows.map((x) => [x.name, x.fga, x.fgm, pct(x.pct)]);
  }
  function tables(d) {
    const out = [];
    if (d.zones && d.zones.some((z) => z.fga)) {
      out.push(tableHTML("By zone, beside the league", ["Zone", "FGA", "Made", "FG%", "Share", "League"],
        d.zones.filter((z) => z.fga).map((z) => [z.name, z.fga, z.fgm, pct(z.pct), pct(z.share), pct(z.league)])));
    }
    if (d.by_type && d.by_type.length) out.push(tableHTML("By kind of shot", ["Shot", "FGA", "Made", "FG%"], splitRows(d.by_type)));
    if (d.by_period && d.by_period.length) {
      out.push(isCollege(d) ? tableHTML("By half", ["Half", "FGA", "Made", "FG%"], splitRows(d.by_period))
        : tableHTML("By quarter", ["Quarter", "FGA", "Made", "FG%"], splitRows(d.by_period)));
    }
    if (d.by_dist && d.by_dist.length) out.push(tableHTML("By distance", ["Distance", "FGA", "Made", "FG%"], splitRows(d.by_dist)));
    return out.join("");
  }

  /* THE OTHER VIEWS (the route chart's Route type | Depth | Coverage):
     his shots by the league's zones beside its percentage there, by kind
     of shot and by distance, as bars. */
  const VIEWS = [["zone", "Zones", "zones"], ["type", "Shot type", "by_type"], ["dist", "Distance", "by_dist"]];
  const BAR_TITLE = { zone: "Shots by zone, beside the league", type: "Shots by kind of shot", dist: "Shots by distance" };
  function vsLeague(z) {
    if (z.pct == null || z.league == null || Math.abs(z.pct - z.league) < 0.005) return null;
    const pts = Math.round(Math.abs(z.pct - z.league) * 100);
    return pts ? [`${z.pct > z.league ? "+" : "−"}${pts}% vs league`, z.pct > z.league ? "good" : "bad"] : null;
  }
  function shotBars(d, view) {
    if (view === "zone") {
      return bars((d.zones || []).map((z) => [z.name, z.fga, `${z.fgm} of ${z.fga} made · ${pct(z.pct)}${z.league == null ? "" : ` · league ${pct(z.league)}`}`,
        vsLeague(z)]));
    }
    const rows = view === "type" ? d.by_type : d.by_dist;
    return bars((rows || []).map((x) => [x.name, x.fga, `${x.fgm} of ${x.fga} made · ${pct(x.pct)}`]));
  }

  Q.draw("shots", {
    one: "shot", splitsTitle: "Every split · zone beside the league, kind of shot, quarter, distance",
    items: (g) => g.shots || [],
    count: (L) => `${(L.fga || 0).toLocaleString()} shots`,
    chip: (g) => `${g.line.pts} pts · ${g.line.fgm}-${g.line.fga}`,
    zones,
    game: (g, d) => shotGame(g, d),
    season: (d) => shotSeason(d),
    legend: (g) => legend(g),
    gameSide: (g) => gameTiles(g),
    seasonSide: (d) => seasonTiles(d),
    //: His card's five (carrychart.js `playerHero`).
    heroTiles: (d) => { const L = d.season_line || {};
      return [["Games", L.games], ["PPG", num1(L.ppg)], ["FG%", pct(L.fg_pct)], ["3PT%", pct(L.fg3_pct)], ["FT%", pct(L.ft_pct)]]; },
    list: (g, d) => shotList(g, d),
    flags, filters: FILTERS, csv,
    views: (d) => VIEWS.filter(([, , k]) => (d[k] || []).some((x) => x.fga)).map(([k, name]) => [k, name]),
    barTitle: (v) => BAR_TITLE[v],
    bars: (d, v) => shotBars(d, v),
    splits: (d) => tables(d),
    note: (d) => `<p class="cc-note">Each mark is a shot from the floor, where it was taken, from ${isCollege(d)
      ? "ESPN’s play-by-play of the game (its court coordinates, to the foot, drawn with the basket at the top on the college court: a 12-foot lane and the three-point line at 22 feet 1¾ inches)"
      : "the NBA’s own play-by-play (its court coordinates, drawn with the basket at the top)"}; the box score names the shooter. A lit green dot went in, a red cross missed. A free throw has no spot on the floor: it is listed, not drawn, and counted in no zone; a heave from past 36 feet sits on the far edge. The zones are the league’s own (the restricted area is the four feet around the basket, the paint the rest of the lane, the corner three the straight part of the line), and the league’s percentage in each is every shot of that season on file; the season view shades a zone green where he shoots two points or more better than the league there and red where two or more worse, deeper the more of his shots it takes. Minutes, rebounds, assists, steals, blocks and turnovers are his box score that night.</p>`,
    tip: (s, g, d) => `<b class="${s.m ? "gain" : "loss"}">${esc(result(s))}</b>${s.d != null ? ` · ${esc(feet(s.d))}` : ""}
      <span>${esc([when(s, d), what(s), ...tags(s)].filter(Boolean).join(" · "))}</span>`,
  });
})();
