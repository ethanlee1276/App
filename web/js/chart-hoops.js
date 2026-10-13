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

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, state } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const QUAL = { fastbreak: "Fast break", "2ndchance": "Second chance", fromturnover: "Off a turnover",
                 pointsinthepaint: "In the paint" };
  const kindWord = (s) => (s.k === "3pt" ? "3" : s.k === "2pt" ? "2" : "free throw");
  const period = (p) => (!p ? "" : p <= 4 ? `Q${p}` : p === 5 ? "OT" : `${p - 4}OT`);
  const when = (s) => [period(s.p), s.c].filter(Boolean).join(" ");
  const what = (s) => (s.k === "ft" ? `Free throw${s.t ? ` ${s.t}` : ""}`
    : [s.t, s.ds].filter(Boolean).join(" · ") || "Shot");
  const result = (s) => (s.k === "ft" ? (s.m ? "Made FT" : "Missed FT") : `${s.m ? "Made" : "Missed"} ${kindWord(s)}`);
  const tags = (s) => [s.m && s.a ? `Assisted by ${s.a}` : "", s.b ? "Blocked" : "",
                       ...String(s.q || "").split(",").filter((q) => q && q !== "pointsinthepaint").map((q) => QUAL[q] || "")]
    .filter(Boolean);
  const feet = (d) => (d == null ? "" : `${Math.round(d)} ft`);

  /* ---------------- the court ---------------- */
  /* The league's court coordinates: tenths of a foot, the middle of the
     basket at 0, 0, the baseline at -47.5. Drawn with the basket at the
     top, out to 36 feet from it: a heave from farther sits on the edge
     (the list has its distance). */
  const X = (x) => Math.max(4, Math.min(496, 250 + x));
  const Y = (y) => Math.max(4, Math.min(406, y + 47.5));
  function courtSVG() {
    return `<rect class="nb-floor" x="0" y="0" width="500" height="410"/>
      <rect class="nb-paint" x="170" y="0" width="160" height="190"/>
      <path class="nb-line" d="M190 190 A60 60 0 0 0 310 190"/>
      <path class="nb-line dash" d="M190 190 A60 60 0 0 1 310 190"/>
      <path class="nb-line" d="M210 47.5 A40 40 0 0 0 290 47.5"/>
      <path class="nb-arc" d="M30 0 V137 A237.5 237.5 0 0 0 470 137 V0"/>
      <line class="nb-board" x1="220" y1="40" x2="280" y2="40"/>
      <circle class="nb-rim" cx="250" cy="47.5" r="7.5"/>`;
  }
  const svg = (body, label) =>
    `<svg class="cc-svg nb-svg" viewBox="0 0 500 410" role="img" aria-label="${esc(label)}">${body}</svg>`;
  function shotMark(s, i) {
    if (s.k === "ft" || s.x == null || s.y == null) return "";
    const x = X(s.x).toFixed(1), y = Y(s.y).toFixed(1);
    return `<g class="cc-carry" data-i="${i}"><circle class="nb-hit" cx="${x}" cy="${y}" r="12"/>
      <circle class="nb-shot cx-mark ${s.m ? "m" : "x"}${sel(i)}" cx="${x}" cy="${y}" r="${s.k === "3pt" ? 7 : 6}"/></g>`;
  }
  function shotGame(g) {
    const shots = g.shots || [];
    const fga = shots.filter((s) => s.k !== "ft").length;
    return svg(courtSVG() + shots.map(shotMark).join(""),
      `Shot chart: ${fga} shot${fga === 1 ? "" : "s"} from the floor. Every shot and free throw is listed below.`);
  }
  /* The season: every shot faint, and each zone's own number on it — two
     corners each their own, the rest down the middle of the floor. */
  const PILLS = { ra: [250, 72], paint: [250, 150], mid: [250, 238], above3: [250, 345] };
  function pill(x, y, made, att) {
    if (!att) return "";
    return `<g class="nb-pill"><rect x="${x - 34}" y="${y - 19}" width="68" height="36" rx="9"/>
      <text class="nb-pct" x="${x}" y="${y - 1}" text-anchor="middle">${pct(made / att)}</text>
      <text class="nb-att" x="${x}" y="${y + 12}" text-anchor="middle">${made} of ${att}</text></g>`;
  }
  function shotSeason(d) {
    const every = [];
    d.games.forEach((g) => (g.shots || []).forEach((s) => { if (s.k !== "ft" && s.x != null) every.push(s); }));
    let body = courtSVG() + every.map((s) =>
      `<circle class="nb-shot faint ${s.m ? "m" : "x"}" cx="${X(s.x).toFixed(1)}" cy="${Y(s.y).toFixed(1)}" r="3.6"/>`).join("");
    const tally = {};
    every.forEach((s) => {
      const k = s.z === "corner3" ? (s.x < 0 ? "c3a" : "c3b") : s.z;
      const t = tally[k] = tally[k] || [0, 0];
      t[0] += s.m; t[1] += 1;
    });
    Object.entries(PILLS).forEach(([k, [x, y]]) => { if (tally[k]) body += pill(x, y, tally[k][0], tally[k][1]); });
    if (tally.c3a) body += pill(46, 28, tally.c3a[0], tally.c3a[1]);
    if (tally.c3b) body += pill(454, 28, tally.c3b[0], tally.c3b[1]);
    return svg(body, `Shot chart: ${every.length} shots from the floor this season, by zone.`);
  }
  function legend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Made</span>
      <span><i class="dt nb-x"></i>Missed</span></div>`;
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
  function shotList(g) {
    return `<div class="cc-list" role="list">${(g.shots || []).map((s, i) => {
      const b = s.m ? "gain" : "loss", tg = tags(s);
      return `<button type="button" role="listitem" class="cc-row${sel(i)}" data-i="${i}">
        <i class="dot ${b}"></i>
        <span class="cc-r-q">${esc(when(s))}</span>
        <span class="cc-r-dd">${esc(feet(s.d) || (s.k === "ft" ? "Line" : ""))}</span>
        <span class="cc-r-h">${esc(what(s))}</span>
        <b class="cc-r-y ${b}">${esc(result(s))}</b>
        ${tg.length ? `<span class="cc-r-tags">${tg.map((x) => `<em>${esc(x)}</em>`).join("")}</span>` : ""}
      </button>`;
    }).join("")}</div>`;
  }
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
    if (d.by_period && d.by_period.length) out.push(tableHTML("By quarter", ["Quarter", "FGA", "Made", "FG%"], splitRows(d.by_period)));
    if (d.by_dist && d.by_dist.length) out.push(tableHTML("By distance", ["Distance", "FGA", "Made", "FG%"], splitRows(d.by_dist)));
    return out.join("");
  }

  Q.draw("shots", {
    one: "shot", splitsTitle: "Every split · zone beside the league, kind of shot, quarter, distance",
    items: (g) => g.shots || [],
    count: (L) => `${(L.fga || 0).toLocaleString()} shots`,
    chip: (g) => `${g.line.pts} pts · ${g.line.fgm}-${g.line.fga}`,
    game: (g) => shotGame(g),
    season: (d) => shotSeason(d),
    gameSide: (g) => `${legend()}${gameTiles(g)}`,
    seasonSide: (d) => `${legend()}${seasonTiles(d)}`,
    list: (g) => shotList(g),
    splits: (d) => tables(d),
    note: () => `<p class="cc-note">Each dot is a shot from the floor, where it was taken, from the NBA’s own play-by-play (its court coordinates, drawn with the basket at the top); the box score names the shooter. Green went in, red rings missed. A free throw has no spot on the floor: it is listed, not drawn; a heave from past 36 feet sits on the far edge. The zones are the league’s own (the restricted area is the four feet around the basket, the paint the rest of the lane, the corner three the straight part of the line), and the league’s percentage in each is every shot of that season on file. Minutes, rebounds, assists, steals, blocks and turnovers are his box score that night.</p>`,
    tip: (s) => `<b class="${s.m ? "gain" : "loss"}">${esc(result(s))}</b>${s.d != null ? ` · ${esc(feet(s.d))}` : ""}
      <span>${esc([when(s), what(s), ...tags(s)].filter(Boolean).join(" · "))}</span>`,
  });
})();
