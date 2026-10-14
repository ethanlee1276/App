/* Qellys Book — the NFL kicker chart (js/chart-kicks.js).
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done, then make sure they are all routed correctly like nfl." Loaded by
   js/carrychart.js the first time a kicker chart is drawn, in its frame
   (the games row, the By game | season tabs, the numbers beside the
   drawing, every kick in order, the splits and how it is drawn).

   THE KICKER CHART (kind "kicks", engine/kicks.chart): every field goal
   he tried, at the distance it was kicked from, the posts at the top;
   each ball's line runs to the posts, green made, red dashes missed, a
   cross blocked. The play-by-play records how far, not where across the
   field or between the uprights, so kicks are set side by side in the
   order he tried them. Extra points are listed and counted, not drawn.
   The season view puts each distance band's make rate beside the
   league's.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, state } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const RESULT = { made: "Made", missed: "Missed", blocked: "Blocked", aborted: "Aborted (never got off)" };
  const quarter = (q) => (!q ? "" : q <= 4 ? `Q${q}` : "OT");
  const when = (k) => [quarter(k.q), k.clk].filter(Boolean).join(" ");
  const what = (k) => (k.k === "xp" ? "Extra point" : `${k.d == null ? "?" : k.d}-yd field goal`);
  function score(k) {
    if (k.sd == null) return "";
    return k.sd === 0 ? "tied" : k.sd > 0 ? `up ${k.sd}` : `down ${-k.sd}`;
  }
  function weather(k) {
    if (k.roof === "dome" || k.roof === "closed") return k.roof === "dome" ? "dome" : "roof closed";
    return [k.wind != null ? `${Math.round(k.wind)} mph wind` : "", k.temp != null ? `${Math.round(k.temp)}°F` : ""]
      .filter(Boolean).join(", ");
  }
  const band = (r) => (r === "made" ? "gain" : r === "blocked" ? "short" : "loss");

  /* ---------------- the field ---------------- */
  /* The posts at the top, the field running down from them: a kick d
     yards out sits d yards below the crossbar. The column on the right
     carries the distances, or the season's bands. */
  const L = 10, R = 290, MID = 150, TOP = 30, YD = 6.5, MAXD = 66;
  const Y = (d) => TOP + Math.max(0, Math.min(MAXD, d == null ? MAXD : d)) * YD;
  function fieldSVG(rightLabels) {
    let s = `<rect class="kk-field" x="${L}" y="${TOP}" width="${R - L}" height="${(MAXD * YD).toFixed(0)}"/>
      <rect class="kk-ez" x="${L}" y="${TOP}" width="${R - L}" height="${10 * YD}"/>`;
    for (const d of [20, 30, 40, 50, 60]) {
      s += `<line class="kk-line" x1="${L}" x2="${R}" y1="${Y(d)}" y2="${Y(d)}"/>`;
      if (rightLabels) s += `<text class="kk-yd" x="${R + 10}" y="${Y(d) + 4}">${d} yd</text>`;
    }
    s += `<line class="kk-post" x1="${MID - 16}" x2="${MID + 16}" y1="${TOP}" y2="${TOP}"/>
      <line class="kk-post" x1="${MID - 16}" x2="${MID - 16}" y1="${TOP}" y2="4"/>
      <line class="kk-post" x1="${MID + 16}" x2="${MID + 16}" y1="${TOP}" y2="4"/>
      <line class="kk-post" x1="${MID}" x2="${MID}" y1="${TOP}" y2="${TOP + 12}"/>`;
    return s;
  }
  const H = TOP + MAXD * YD + 12;
  const svg = (body, label) =>
    `<svg class="cc-svg kk-svg" viewBox="0 0 420 ${H.toFixed(0)}" role="img" aria-label="${esc(label)}">${body}</svg>`;
  /* One field goal: its ball at its distance, its flight to the posts. */
  function kickMark(k, x, i, faint) {
    const y = Y(k.d).toFixed(1), cls = `${k.r}${faint ? " faint" : ""}`;
    const flight = k.r === "blocked" ? "" : `<line class="kk-flight ${cls}" x1="${x.toFixed(1)}" y1="${y}" x2="${MID}" y2="${TOP + 2}"/>`;
    const ball = k.r === "blocked"
      ? `<path class="kk-ball cx-mark blocked${faint ? " faint" : ""}${sel(i)}" d="M${(x - 6).toFixed(1)} ${(+y - 6).toFixed(1)}l12 12m0 -12l-12 12"/>`
      : `<circle class="kk-ball cx-mark ${cls}${sel(i)}" cx="${x.toFixed(1)}" cy="${y}" r="${faint ? 4.5 : 7}"/>`;
    if (faint) return flight + ball.replace(" cx-mark", "");
    return `<g class="cc-carry" data-i="${i}"><circle class="kk-hit" cx="${x.toFixed(1)}" cy="${y}" r="16"/>${flight}${ball}
      <text class="kk-d" x="${(x + 11).toFixed(1)}" y="${(+y + 4).toFixed(1)}">${k.d == null ? "" : k.d}</text></g>`;
  }
  function kickGame(g) {
    const ks = g.kicks || [], fg = ks.map((k, i) => [k, i]).filter(([k]) => k.k === "fg");
    const step = (R - L - 40) / Math.max(1, fg.length);
    const body = fieldSVG(true) + fg.map(([k, i], j) => kickMark(k, L + 20 + step * (j + 0.5), i, false)).join("");
    return svg(body, `Kicker chart: ${fg.length} field goal${fg.length === 1 ? "" : "s"} by distance. Every kick is listed below.`);
  }
  /* The season: every field goal faint at its distance, in the order he
     tried them across the field, and each band's rate on the right. */
  function kickSeason(d) {
    const every = [];
    d.games.slice().reverse().forEach((g) => (g.kicks || []).forEach((k) => { if (k.k === "fg") every.push(k); }));
    const step = (R - L - 20) / Math.max(1, every.length);
    let body = fieldSVG(false) + every.map((k, j) => kickMark(k, L + 10 + step * (j + 0.5), -1, true)).join("");
    const MIDS = { u30: 24, "30s": 34.5, "40s": 44.5, "50": 55 };
    (d.by_band || []).forEach((b) => {
      const y = Y(MIDS[b.key] || 40);
      body += `<g class="kk-pill"><rect x="${R + 6}" y="${(y - 25).toFixed(1)}" width="118" height="50" rx="9"/>
        <text class="kk-pn" x="${R + 14}" y="${(y - 9).toFixed(1)}">${esc(b.name)}</text>
        <text class="kk-pct" x="${R + 14}" y="${(y + 8).toFixed(1)}">${b.fgm}/${b.fga} · ${pct(b.pct)}</text>
        <text class="kk-lg" x="${R + 14}" y="${(y + 20).toFixed(1)}">league ${pct(b.league)}</text></g>`;
    });
    return svg(body, `Kicker chart: ${every.length} field goals this season by distance, with each band's rate.`);
  }
  function legend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Made</span>
      <span><i class="dt kk-x"></i>Missed</span><span><i class="dt kk-b">×</i>Blocked</span></div>`;
  }

  /* ---------------- the numbers ---------------- */
  function conditions(g) {
    const k = (g.kicks || [])[0];
    return k ? (weather(k) || (k.roof ? "outdoors" : "—")) : "—";
  }
  function gameTiles(g) {
    const l = g.line;
    return `<div class="cc-tiles cc-tiles-6">${[
      tile("FG", `${l.fgm}/${l.fga}`, pct(l.fg_pct)), tile("XP", `${l.xpm}/${l.xpa}`),
      tile("Points", l.pts), tile("Long", l.long == null ? "—" : l.long, "made"),
      tile("50+", `${l.fg50}/${l.fga50}`), tile("Conditions", conditions(g))].join("")}</div>`;
  }
  function seasonTiles(d) {
    const l = d.season_line, n = d.games.length;
    return `<div class="cc-tiles cc-tiles-6">${[
      tile("FG", pct(l.fg_pct), `${l.fgm} of ${l.fga}`), tile("XP", pct(l.xp_pct), `${l.xpm} of ${l.xpa}`),
      tile("Points", num1(n ? l.pts / n : null), "a game"), tile("Long", l.long == null ? "—" : l.long, "made"),
      tile("50+", `${l.fg50}/${l.fga50}`), tile("Blocked", l.blocked)].join("")}</div>`;
  }
  function kickList(g) {
    return `<div class="cc-list" role="list">${(g.kicks || []).map((k, i) => {
      const b = band(k.r), tg = [score(k) ? `${score(k)}` : "", weather(k)].filter(Boolean);
      return `<button type="button" role="listitem" class="cc-row${sel(i)}" data-i="${i}">
        <i class="dot ${b}"></i>
        <span class="cc-r-q">${esc(when(k))}</span>
        <span class="cc-r-h">${esc(what(k))}</span>
        <b class="cc-r-y ${b}">${esc(RESULT[k.r] || k.r)}</b>
        ${tg.length ? `<span class="cc-r-tags">${tg.map((x) => `<em>${esc(x)}</em>`).join("")}</span>` : ""}
      </button>`;
    }).join("")}</div>`;
  }
  const rows = (xs, lg) => xs.map((x) => (lg ? [x.name, x.fga, x.fgm, pct(x.pct), pct(x.league)] : [x.name, x.fga, x.fgm, pct(x.pct)]));
  function tables(d) {
    const out = [];
    if ((d.by_band || []).length) out.push(tableHTML("By distance, beside the league", ["Distance", "FGA", "Made", "FG%", "League"], rows(d.by_band, true)));
    if ((d.by_place || []).length) out.push(tableHTML("Indoors and outdoors", ["Where", "FGA", "Made", "FG%"], rows(d.by_place)));
    if ((d.by_weather || []).length) out.push(tableHTML("In the weather", ["Conditions", "FGA", "Made", "FG%"], rows(d.by_weather)));
    if ((d.by_moment || []).length) out.push(tableHTML("When it mattered", ["Moment", "FGA", "Made", "FG%"], rows(d.by_moment)));
    return out.join("");
  }

  Q.draw("kicks", {
    one: "kick", splitsTitle: "Every split · distance beside the league, indoors, weather, late and close",
    items: (g) => g.kicks || [],
    count: (l) => `${l.fga} field goal${l.fga === 1 ? "" : "s"}`,
    chip: (g) => `${g.line.fgm}/${g.line.fga} FG`,
    game: (g) => kickGame(g),
    season: (d) => kickSeason(d),
    gameSide: (g) => `${legend()}${gameTiles(g)}`,
    seasonSide: (d) => `${legend()}${seasonTiles(d)}`,
    list: (g) => kickList(g),
    splits: (d) => tables(d),
    note: () => `<p class="cc-note">Each ball is a field goal at the distance it was kicked from, the posts at the top; its line runs to the posts, green made, red dashes missed, and a cross is a kick that was blocked. The NFL’s play-by-play records how far, not where across the field or where between the uprights it went, so kicks are set side by side in the order he tried them. Extra points are listed and counted in his points, not drawn. The league’s rate in each distance band is every field goal of that season on file. Wind and temperature are the play-by-play’s readings for the game (none under a roof).</p>`,
    tip: (k) => `<b class="${band(k.r)}">${esc(what(k))} · ${esc(RESULT[k.r] || k.r)}</b>
      <span>${esc([when(k), score(k), weather(k)].filter(Boolean).join(" · "))}</span>`,
  });
})();
