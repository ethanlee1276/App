/* Qellys Book — tonight's opponent beside his chart (js/chart-matchup.js).
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done", the list's seventh: "Matchup view. Tonight's defense next to his
   chart ... This is context only." And the same message: "All sports
   screens should basically be identical". Loaded by js/carrychart.js the
   first time a matchup is drawn; one view, no games row (`only`).

   ONE PICTURE IN EVERY LEAGUE (engine/matchview): his chart's own zones,
   a row each — on the left how much of the volume goes there, on the
   right the zone's rate beside the league's, green where it is better
   for him and red where it is worse — then the fit (the difference
   weighted by the share), where the opponent ranks, and every number in
   the table. Nothing on it moves a price, and the note says so.

   In the frame of Ethan's NFL renders (2026-10-14): tonight's game over
   his team's colours and the opponent's (the frame draws it from the
   team his own charts name), the zones in a card with how they are read
   one tap away, the numbers as icon tiles.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, fold } = Q.h;

  /* ---------------- numbers ---------------- */
  const FMT = {
    yds: { v: (x) => Number(x).toFixed(1), d: (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(1)}` },
    pct: { v: (x) => `${(x * 100).toFixed(1)}%`, d: (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(1)}` },
    slg: { v: (x) => Number(x).toFixed(3).replace(/^0/, ""), d: (x) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(3).replace(/^0/, "")}` },
  };
  const fmt = (d) => FMT[d.fmt] || FMT.yds;
  const tone = (d, x) => (x * d.good > 0.0005 ? "gain" : x * d.good < -0.0005 ? "loss" : "");
  const pct = (x) => `${Math.round(x * 100)}%`;
  const nth = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th")}`;
  //: What each family's fit is read in, and where.
  const FIT = {
    routes: "yds/target where he’s thrown to", passes: "yds/attempt where he throws",
    carries: "yds/carry where he runs", runs: "yds/carry where he runs", catches: "yds/target where he’s thrown to",
    shots: "FG% points where he shoots", skater: "shooting % points where he shoots",
    goalie: "their shooting % points where they shoot", hitter: "slugging where he’ll be pitched",
    pitcher: "their slugging where he pitches",
  };
  const NOUN = { routes: "targets", passes: "throws", carries: "carries", runs: "carries", catches: "targets",
                 shots: "shots", skater: "shots", goalie: "shots on goal", hitter: "at bats", pitcher: "at bats" };
  const opp = (d, sport) => (typeof teamNameIn === "function" ? teamNameIn(sport, d.opp) : d.opp) || d.opp;

  /* ---------------- the rows ---------------- */
  const W = 420, NAME = 8, SH0 = 148, SHW = 58, MID = 308, HALF = 60, VX = 416, ROW = 34, TOP = 40;
  function zonesSVG(d) {
    const zs = d.zones, F = fmt(d);
    const top = Math.max(0.01, ...zs.map((z) => z.share));
    const span = Math.max(...zs.map((z) => Math.abs(z.diff)), d.fmt === "pct" ? 0.02 : d.fmt === "slg" ? 0.03 : 0.5);
    const h = TOP + zs.length * ROW + 6;
    // Two heading lines, so neither runs into the other on a phone: the
    // rate's over its bars and figures, the share's over its bars.
    let s = `<text class="mv-h" x="${VX}" y="12" text-anchor="end">${esc(d.right)} · against the league</text>
      <text class="mv-h" x="${SH0}" y="28">${esc(d.left)}</text>
      <line class="mv-mid" x1="${MID}" x2="${MID}" y1="${TOP - 4}" y2="${h - 4}"/>`;
    zs.forEach((z, i) => {
      const y = TOP + i * ROW, w = (z.share / top) * SHW, t = tone(d, z.diff);
      const dx = (z.diff / span) * HALF;
      s += `<g class="mv-row${z.share >= 0.15 ? " hot" : ""}">
        <text class="mv-z" x="${NAME}" y="${y + 18}">${esc(z.name)}</text>
        <rect class="mv-track" x="${SH0}" y="${y + 7}" width="${SHW}" height="14" rx="4"/>
        <rect class="mv-share" x="${SH0}" y="${y + 7}" width="${w.toFixed(1)}" height="14" rx="4"/>
        <text class="mv-pct" x="${SH0 + SHW + 5}" y="${y + 18}">${pct(z.share)}</text>
        <rect class="mv-diff ${t}" x="${(dx < 0 ? MID + dx : MID).toFixed(1)}" y="${y + 7}" width="${Math.abs(dx).toFixed(1)}" height="14" rx="3"/>
        <text class="mv-v ${t}" x="${VX}" y="${y + 18}" text-anchor="end">${esc(F.d(z.diff))}</text></g>`;
    });
    return `<svg class="cc-svg mv-svg" viewBox="0 0 ${W} ${h}" role="img" aria-label="${esc(`${d.left} by zone, and ${d.right.toLowerCase()} beside the league's.`)}">${s}</svg>`;
  }
  function legend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="sw mv-sw"></i>Share of the volume</span>
      <span><i class="sw gain"></i>Better for him than the league</span><span><i class="sw loss"></i>Worse for him</span></div>`;
  }

  /* ---------------- the numbers ---------------- */
  function tiles(d, sport) {
    const F = fmt(d), o = d.overall || {}, t = tone(d, d.fit || 0);
    const best = d.zones.slice().sort((a, b) => b.share - a.share)[0];
    const out = [
      // The site's own tile (its icon too), coloured by which way the fit leans.
      tile("Fit", d.fit == null ? "—" : F.d(d.fit), FIT[d.family] || d.unit).replace('class="cc-tile"', `class="cc-tile mv-fit ${t}"`),
      tile("Their rank", o.rank ? `${nth(o.rank)} of ${o.of}` : "—", "1st is the best for him"),
      tile(d.family === "hitter" ? "Staff allows" : d.family === "goalie" || d.family === "pitcher" ? "They do" : "They allow",
           o.rate == null ? "—" : F.v(o.rate), o.league == null ? "" : `league ${F.v(o.league)}`),
      tile("Top zone", best ? best.name : "—", best ? `${pct(best.share)} of it` : ""),
      tile("Their sample", o.n == null ? "—" : String(o.n), NOUN[d.family] || ""),
    ];
    if (d.starter) out.push(tile("Tonight’s starter", d.starter, "the board’s probable"));
    else out.push(tile("Season", String(d.season_label || d.season), d.season !== d.newest ? "last season: too little this one" : "this season"));
    return `<div class="cc-tiles cc-tiles-6">${out.join("")}</div>`;
  }
  function table(d) {
    const F = fmt(d), goalie = d.family === "goalie";
    const head = ["Zone", "Share", goalie ? "Their shots" : "His", "Rate", "League", "Diff"].concat(goalie ? ["His save %"] : []);
    return tableHTML("Zone by zone", head, d.zones.map((z) => [z.name, pct(z.share), z.n, `${F.v(z.rate)}${z.rn ? ` (${z.rn})` : ""}`,
      F.v(z.league), F.d(z.diff)].concat(goalie ? [z.mine == null ? "—" : `${(z.mine * 100).toFixed(1)}%`] : [])));
  }
  function noteHTML(d, sport) {
    const who = opp(d, sport);
    const right = d.family === "hitter" ? "his own slugging on the pitch that ended each plate appearance"
      : d.family === "goalie" || d.family === "pitcher" ? `what ${who} does there` : `what ${who} allows there`;
    const tested = d.tested
      ? "Context only: on the 2022-2025 seasons, where a defence allows yards by depth, side and run gap did not make our picks better on their own, so nothing here moves a price."
      : "Context only, and not measured as a pick signal: nothing here moves a price.";
    return `<p class="cc-note">Each row is a zone of his own chart. The left bar is the share of the volume that goes there (${esc(d.left.toLowerCase())}); the right is ${esc(right)}, beside the league’s, green where it is better for him and red where it is worse. The fit is that difference weighted by the share. Each zone’s rate is pulled toward the league’s by ${d.k} plays, so a zone seen a handful of times reads near the league; the counts are in the table, in brackets.${d.his_season && d.his_season !== d.season ? ` His shares are from his ${esc(String(d.his_season))} season.` : ""} ${tested}</p>`;
  }

  Q.draw("matchup", {
    one: "zone", items: () => [], chip: () => "", count: (L) => `${L.n}`,
    only: (d, sport) => ({
      top: `<div class="cc-title">${esc(`Tonight: ${opp(d, sport)} · ${d.season_label || d.season}`)}</div>`,
      // The legend under the drawing, as every chart's is.
      fig: `<div class="cc-stage">${zonesSVG(d)}</div>${legend()}`,
      side: tiles(d, sport),
      tail: fold("zones", `Zone by zone · ${d.zones.length}`, table(d)),
    }),
    note: (d) => noteHTML(d, d.sport),
    tip: () => "",
  });
})();
