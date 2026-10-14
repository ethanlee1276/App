/* Qellys Book — hockey's charts (js/chart-nhl.js): the shot map and the save map.
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done, then make sure they are all routed correctly like nfl." Loaded by
   js/carrychart.js the first time a hockey chart is drawn, and drawn in
   its frame (the games row, the By game | season tabs, the numbers beside
   the drawing, every shot in order, the splits and how it is drawn).

   THE SHOT MAP (kind "shotmap", engine/nhl/charts.shot_map): every shot a
   skater took, where from, on goal, missed or blocked, and the goals.
   THE SAVE MAP (kind "saves", engine/nhl/charts.save_map): every shot on
   goal a goalie faced, saved or scored. Both turned to face the same net,
   drawn at the top of the attacking zone. Expected goals are the site's
   own model (engine/nhl/xg) and are said to be ours where they show.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, state } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const KIND = { goal: "Goal", sog: "On goal", miss: "Missed", block: "Blocked" };
  const STR = { EV: "", PP: "Power play", SH: "Shorthanded" };
  const per = (p) => (!p ? "" : p <= 3 ? `P${p}` : p === 4 ? "OT" : `${p - 3}OT`);
  const feet = (d) => (d == null ? "" : `${Math.round(d)} ft`);
  const shotType = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1).replace("-", " ") : "Shot");
  const xgWord = (s) => (s.xg == null ? "" : `${num1(s.xg * 100)}% chance (our xG)`);
  const svPct = (v) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));

  /* ---------------- the rink ---------------- */
  /* Feet from centre ice, the net at x = 89: drawn five pixels a foot,
     the end boards at the top, the blue line (x = 25) at the foot. */
  const S = 5;
  const X = (y) => Math.max(3, Math.min(422, 212.5 - S * y));
  const Y = (x) => Math.max(3, Math.min(377, S * (100 - x)));
  function rinkSVG() {
    return `<path class="nh-ice" d="M0 380 V140 A140 140 0 0 1 140 0 H285 A140 140 0 0 1 425 140 V380 Z"/>
      <line class="nh-goal" x1="28.8" y1="55" x2="396.2" y2="55"/>
      <path class="nh-crease" d="M182.5 55 A30 30 0 0 0 242.5 55 Z"/>
      <rect class="nh-net" x="197.5" y="38.3" width="30" height="16.7"/>
      <circle class="nh-circle" cx="102.5" cy="155" r="75"/><circle class="nh-circle" cx="322.5" cy="155" r="75"/>
      <circle class="nh-dot" cx="102.5" cy="155" r="4"/><circle class="nh-dot" cx="322.5" cy="155" r="4"/>
      <line class="nh-blue" x1="0" y1="376" x2="425" y2="376"/>`;
  }
  const svg = (body, label) =>
    `<svg class="cc-svg nh-svg" viewBox="0 0 425 380" role="img" aria-label="${esc(label)}">${body}</svg>`;
  function mark(s, i, goalie) {
    if (s.x == null || s.y == null) return "";
    const x = X(s.y).toFixed(1), y = Y(s.x).toFixed(1);
    const cls = goalie ? (s.g ? "ga" : "sv") : s.k;
    const shape = s.k === "block" && !goalie
      ? `<path class="nh-mark cx-mark block${sel(i)}" d="M${x - 4} ${y - 4} L${+x + 4} ${+y + 4} M${+x + 4} ${y - 4} L${x - 4} ${+y + 4}"/>`
      : `<circle class="nh-mark cx-mark ${cls}${sel(i)}" cx="${x}" cy="${y}" r="${s.g ? 7 : 5}"/>`;
    return `<g class="cc-carry" data-i="${i}"><circle class="nh-hit" cx="${x}" cy="${y}" r="11"/>${shape}</g>`;
  }
  const drawGame = (goalie) => (g) => {
    const shots = g.shots || [];
    return svg(rinkSVG() + shots.map((s, i) => mark(s, i, goalie)).join(""),
      `${goalie ? "Save map" : "Shot map"}: ${shots.length} shot${shots.length === 1 ? "" : "s"}. Every one is listed below.`);
  };
  /* The season: every shot faint, and each distance band's own number on
     it, down the middle of the ice. */
  const PILLS = { crease: 82, slot: 140, high: 222, point: 330 };
  function pill(y, big, small) {
    return `<g class="nh-pill"><rect x="160.5" y="${y - 19}" width="104" height="36" rx="9"/>
      <text class="nh-pct" x="212.5" y="${y - 1}" text-anchor="middle">${big}</text>
      <text class="nh-att" x="212.5" y="${y + 12}" text-anchor="middle">${small}</text></g>`;
  }
  const drawSeason = (goalie) => (d) => {
    const every = [];
    d.games.forEach((g) => (g.shots || []).forEach((s) => every.push(s)));
    let body = rinkSVG() + every.map((s) => {
      if (s.x == null) return "";
      const cls = goalie ? (s.g ? "ga" : "sv") : s.k;
      return `<circle class="nh-mark faint ${cls}" cx="${X(s.y).toFixed(1)}" cy="${Y(s.x).toFixed(1)}" r="${s.g ? 4.4 : 3.2}"/>`;
    }).join("");
    (d.zones || []).forEach((z) => {
      const y = PILLS[z.key];
      if (!y || !z.n) return;
      body += goalie ? pill(y, pct(z.on ? 1 - z.goals / z.on : null), `${z.on - z.goals} of ${z.on} saved`)
        : pill(y, pct(z.pct), `${z.goals} of ${z.on} scored`);
    });
    return svg(body, `${goalie ? "Save map" : "Shot map"}: ${every.length} shots this season, by distance.`);
  };
  function legend(goalie) {
    return goalie
      ? `<div class="cc-legend" aria-hidden="true"><span><i class="dt nh-sv"></i>Saved</span><span><i class="dt nh-ga"></i>Goal</span></div>`
      : `<div class="cc-legend" aria-hidden="true"><span><i class="dt nh-goal"></i>Goal</span><span><i class="dt c"></i>On goal</span>
         <span><i class="dt m"></i>Missed</span><span><i class="dt nh-block">×</i>Blocked</span></div>`;
  }
  /* Short labels so three fit across a phone; the note spells them out. */
  const xgTile = (label, v, sub) => tile(label, v == null ? "—" : num1(v), sub || "our model");
  function skaterTiles(L, season) {
    const t = season
      ? [tile("Games", L.games), tile("On goal", num1(L.sog_pg), "a game"), tile("Goals", L.goals),
         tile("Shooting", pct(L.sh_pct), "of shots on goal"), xgTile("xG", L.ixg, "expected · our model"),
         tile("Attempts", L.att, `${L.pp} on the PP`)]
      : [tile("On goal", L.sog), tile("Goals", L.goals), tile("Attempts", L.att),
         tile("Missed", L.miss), tile("Blocked", L.blocked), xgTile("xG", L.ixg, "expected · our model")];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function goalieTiles(L, season) {
    const t = season
      ? [tile("Games", L.games), tile("Shots", num1(L.shots_pg), "faced a game"), tile("Save %", svPct(L.sv_pct)),
         tile("GA", L.ga, "goals against"), xgTile("GSAx", L.gsax, "saved above xG"), xgTile("xGA", L.xga, "expected · our model")]
      : [tile("Shots", L.shots, "on goal faced"), tile("Saves", L.saves), tile("GA", L.ga, "goals against"),
         tile("Save %", svPct(L.sv_pct)), xgTile("xGA", L.xga, "expected · our model"), xgTile("GSAx", L.gsax, "saved above xG")];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function list(g, goalie) {
    return `<div class="cc-list" role="list">${(g.shots || []).map((s, i) => {
      const good = goalie ? !s.g : s.g || s.k === "sog";
      const b = goalie ? (s.g ? "loss" : "gain") : s.g ? "gain" : s.k === "sog" ? "short" : "miss";
      const tags = [STR[s.st] || "", s.reb ? "Rebound" : "", s.rush ? "Off the rush" : "",
                    !goalie && s.a && s.a.length ? `Assists ${s.a.join(", ")}` : "",
                    goalie && s.by ? `by ${s.by}` : "", !goalie && s.vs && s.k !== "block" ? `on ${s.vs}` : ""].filter(Boolean);
      return `<button type="button" role="listitem" class="cc-row${sel(i)}" data-i="${i}">
        <i class="dot ${b}"></i>
        <span class="cc-r-q">${esc(per(s.p))}</span>
        <span class="cc-r-dd">${esc(feet(s.d))}</span>
        <span class="cc-r-h">${esc([shotType(s.t), xgWord(s)].filter(Boolean).join(" · "))}</span>
        <b class="cc-r-y ${good ? "gain" : b}">${esc(goalie ? (s.g ? "Goal" : "Saved") : KIND[s.k] || s.k)}</b>
        ${tags.length ? `<span class="cc-r-tags">${tags.map((x) => `<em>${esc(x)}</em>`).join("")}</span>` : ""}
      </button>`;
    }).join("")}</div>`;
  }
  function tables(d, goalie) {
    const head = goalie ? ["Shots", "Goals", "Save %"] : ["Attempts", "On goal", "Goals", "Shooting"];
    const row = (x) => (goalie ? [x.name, x.on, x.goals, pct(x.on ? 1 - x.goals / x.on : null)]
      : [x.name, x.n, x.on, x.goals, pct(x.pct)]);
    const out = [];
    if (d.zones && d.zones.length) out.push(tableHTML("By distance from the net", ["Where", ...head], d.zones.map(row)));
    if (d.by_type && d.by_type.length) out.push(tableHTML("By kind of shot", ["Shot", ...head], d.by_type.map(row)));
    if (d.by_strength && d.by_strength.length) out.push(tableHTML("By strength", ["Strength", ...head], d.by_strength.map(row)));
    return out.join("");
  }
  const note = (goalie) => `<p class="cc-note">Every ${goalie ? "shot on goal he faced" : "shot he took"} from the NHL’s own play-by-play, where it was taken, turned so every shot faces the net at the top (a half turn, so his left stays his left); a shot from beyond the blue line sits on it. ${goalie ? "Green was saved, red went in; an empty net is not his." : "Gold went in, green was on goal, a ring missed the net and a cross was blocked before it got there."} Expected goals (xG) are our own model, fitted on every stored shot by distance, angle, shot type, rebound, rush and strength${goalie ? "; xGA is the expected goals of the shots he faced, GSAx the goals he saved above it (xGA minus the goals against, GA)" : ""}.</p>`;

  const spec = (goalie) => ({
    one: goalie ? "shot faced" : "shot attempt",
    splitsTitle: "Every split · distance, kind of shot, strength",
    items: (g) => g.shots || [],
    count: (L) => (goalie ? `${L.shots.toLocaleString()} shots faced` : `${L.att.toLocaleString()} attempts`),
    chip: (g) => (goalie ? `${g.line.saves}/${g.line.shots} saved` : `${g.line.sog} SOG${g.line.goals ? `, ${g.line.goals} G` : ""}`),
    game: drawGame(goalie),
    season: drawSeason(goalie),
    gameSide: (g) => `${legend(goalie)}${goalie ? goalieTiles(g.line) : skaterTiles(g.line)}`,
    seasonSide: (d) => `${legend(goalie)}${goalie ? goalieTiles(d.season_line, true) : skaterTiles(d.season_line, true)}`,
    list: (g) => list(g, goalie),
    splits: (d) => tables(d, goalie),
    note: () => note(goalie),
    tip: (s) => `<b class="${goalie ? (s.g ? "loss" : "gain") : s.g ? "gain" : "miss"}">${esc(goalie ? (s.g ? "Goal" : "Saved") : KIND[s.k] || s.k)}</b>${s.d != null ? ` · ${esc(feet(s.d))}` : ""}
      <span>${esc([per(s.p), shotType(s.t), xgWord(s), goalie ? (s.by ? `by ${s.by}` : "") : (s.vs && s.k !== "block" ? `on ${s.vs}` : "")].filter(Boolean).join(" · "))}</span>`,
  });
  Q.draw("shotmap", spec(false));
  Q.draw("saves", spec(true));
})();
