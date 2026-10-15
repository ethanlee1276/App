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

   IN THE FRAME OF ETHAN'S NFL RENDERS (2026-10-14): the ice dark with its
   lines lit, a goal a lit gold mark, the slot, the high slot and the point
   as the render's Left | Middle | Right with their counts, Distance | Shot
   type | Strength as the route chart's other views, and every shot in the
   render's table, filtered and downloadable.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, state, grid, two, pills, bars } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const KIND = { goal: "Goal", sog: "On goal", miss: "Missed", block: "Blocked" };
  const STR = { EV: "", PP: "Power play", SH: "Shorthanded" };
  const per = (p) => (!p ? "" : p <= 3 ? `P${p}` : p === 4 ? "OT" : `${p - 3}OT`);
  const feet = (d) => (d == null ? "" : `${Math.round(d)} ft`);
  const shotType = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1).replace("-", " ") : "Shot");
  const xgWord = (s) => (s.xg == null ? "" : `${num1(s.xg * 100)}% chance (our xG)`);
  const xg2 = (s) => (s.xg == null ? "—" : Number(s.xg).toFixed(2));
  const svPct = (v) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));
  const plus1 = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}`);
  const how = (s) => [s.reb ? "Rebound" : "", s.rush ? "Off the rush" : ""].filter(Boolean);

  /* ---------------- the zones ----------------
     The render's Left | Middle | Right, on the ice: the slot (the crease
     and the twenty feet in front of the net), the high slot and the
     circles, and the point — the league's own distance bands, the crease
     folded into the slot. */
  const ZONE_OF = { crease: "S", slot: "S", high: "H", point: "P" };
  const zones = {
    label: "Where on the ice",
    list: [["S", "Slot", "The slot"], ["H", "High slot", "High slot"], ["P", "Point", "The point"]],
    of: (s) => ZONE_OF[s.z] || "",
    noun: ["shot", "shots"],
  };

  /* ---------------- the rink ---------------- */
  /* Feet from centre ice, the net at x = 89: drawn five pixels a foot,
     the end boards at the top, the blue line (x = 25) at the foot. Dark
     ice, the lines lit (a faint wide copy under each, no filter). */
  const SC = 5;
  const X = (y) => Math.max(3, Math.min(422, 212.5 - SC * y));
  const Y = (x) => Math.max(3, Math.min(377, SC * (100 - x)));
  function rinkSVG() {
    return `<path class="nh-ice" d="M0 380 V140 A140 140 0 0 1 140 0 H285 A140 140 0 0 1 425 140 V380 Z"/>
      <g class="nh-glow red"><line x1="28.8" y1="55" x2="396.2" y2="55"/>
        <circle cx="102.5" cy="155" r="75"/><circle cx="322.5" cy="155" r="75"/></g>
      <line class="nh-blue-glow" x1="0" y1="376" x2="425" y2="376"/>
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
      : `${s.g ? `<circle class="nh-halo ${cls}" cx="${x}" cy="${y}" r="12"/>` : ""}<circle class="nh-mark cx-mark ${cls}${sel(i)}" cx="${x}" cy="${y}" r="${s.g ? 7 : 5}"/>`;
    return `<g class="cc-carry" data-i="${i}" data-z="${zones.of(s)}"><circle class="nh-hit" cx="${x}" cy="${y}" r="11"/>${shape}</g>`;
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

  /* EVERY SHOT AS THE RENDERS' TABLE: its number, the period, the shot
     (its kind and distance, and under it who it was on or who set it up),
     its expected goals, and how it ended — a skater's from his side, a
     goalie's from his. On a phone the period and the chance read under
     the shot. */
  const COLS = [{ h: "#", c: "cc-c-n", p: "18px", w: "26px" },
                { h: "Per", c: "cc-c-q", w: "40px" },
                { h: "Shot", c: "cc-c-m", p: "minmax(0,1fr)" },
                { h: "Shot", c: "cc-c-m", w: "minmax(0,1fr)" },
                { h: "Result", c: "cc-c-res", p: "92px", w: "170px" },
                { h: "Dist", c: "cc-c-v", p: "30px", w: "52px", r: 1 },
                { h: "xG", c: "cc-c-v", w: "48px", r: 1 }];
  function list(g, goalie) {
    return grid(goalie ? "saves" : "shotmap", COLS, (g.shots || []).map((s, i) => {
      const word = goalie ? (s.g ? "Goal" : "Saved") : KIND[s.k] || s.k;
      const tone = goalie ? (s.g ? "bad" : "good") : s.g ? "gold" : s.k === "sog" ? "good" : "mute";
      const res = [[word, tone]].concat(STR[s.st] ? [[STR[s.st], "tag"]] : []);
      const who = goalie ? (s.by ? `by ${s.by}` : "")
        : [s.vs && s.k !== "block" ? `on ${s.vs}` : "", s.a && s.a.length ? `Assists ${s.a.join(", ")}` : ""].filter(Boolean).join(" · ");
      const xgs = s.xg == null ? "" : `xG ${xg2(s)}`;
      return {
        i, f: goalie ? goalieFlags(s) : skaterFlags(s),
        said: [per(s.p), shotType(s.t), feet(s.d), word, STR[s.st] || "", ...how(s), xgWord(s), who].filter(Boolean).join(", "),
        cells: [`${i + 1}`, esc(per(s.p) || "—"),
                two(`${shotType(s.t)}${s.d != null ? ` · ${feet(s.d)}` : ""}`, [per(s.p), xgs, ...how(s), who].filter(Boolean).join(" · ")),
                two(goalie ? s.by || "—" : shotType(s.t), [goalie ? shotType(s.t) : "", ...how(s), goalie ? "" : who].filter(Boolean).join(" · ")),
                pills(res), esc(s.d == null ? "—" : `${Math.round(s.d)}`), esc(xg2(s))],
      };
    }));
  }
  const skaterFlags = (s) => [s.g ? "g" : "", s.g || s.k === "sog" ? "on" : "", s.k === "miss" ? "miss" : "",
                              s.k === "block" ? "blk" : "", s.st === "PP" ? "pp" : "", s.reb ? "reb" : "", s.rush ? "rush" : ""]
    .filter(Boolean).join(" ");
  const goalieFlags = (s) => [s.g ? "ga" : "sv", s.st === "PP" ? "pp" : "", s.reb ? "reb" : "", s.rush ? "rush" : ""]
    .filter(Boolean).join(" ");
  const FILTERS = {
    skater: [["", "Every attempt"], ["g", "Goals"], ["on", "On goal"], ["miss", "Missed the net"], ["blk", "Blocked"],
             ["pp", "Power play"], ["reb", "Rebounds"], ["rush", "Off the rush"]],
    goalie: [["", "Every shot faced"], ["sv", "Saved"], ["ga", "Goals against"], ["pp", "On the power play"],
             ["reb", "Rebounds"], ["rush", "Off the rush"]],
  };
  const csv = (goalie) => (g) => [goalie
    ? ["#", "Period", "Shooter", "Shot", "Distance (ft)", "Result", "Strength", "Rebound", "Off the rush", "xG"]
    : ["#", "Period", "Shot", "Distance (ft)", "Result", "Strength", "Rebound", "Off the rush", "xG", "Goalie", "Assists"]]
    .concat((g.shots || []).map((s, i) => (goalie
      ? [i + 1, per(s.p), s.by || "", shotType(s.t), s.d == null ? "" : Math.round(s.d), s.g ? "Goal" : "Saved",
         s.st || "", s.reb ? 1 : 0, s.rush ? 1 : 0, s.xg == null ? "" : s.xg]
      : [i + 1, per(s.p), shotType(s.t), s.d == null ? "" : Math.round(s.d), KIND[s.k] || s.k, s.st || "",
         s.reb ? 1 : 0, s.rush ? 1 : 0, s.xg == null ? "" : s.xg, s.vs || "", (s.a || []).join("; ")])));
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
  /* THE OTHER VIEWS: his shots, or the shots he faced, by distance, by
     kind of shot and by strength, as bars. */
  const VIEWS = [["dist", "Distance", "zones"], ["type", "Shot type", "by_type"], ["str", "Strength", "by_strength"]];
  const TITLE = { dist: "by distance from the net", type: "by kind of shot", str: "by strength" };
  function shotBars(d, view, goalie) {
    const rows = d[(VIEWS.find(([k]) => k === view) || [])[2]] || [];
    return bars(rows.map((x) => (goalie
      ? [x.name, x.on, `${x.on - x.goals} saved · ${x.goals} against · ${pct(x.on ? 1 - x.goals / x.on : null)} saved`]
      : [x.name, x.n, `${x.on} on goal · ${x.goals} goal${x.goals === 1 ? "" : "s"} · ${pct(x.pct)} shooting`])));
  }
  const note = (goalie) => `<p class="cc-note">Every ${goalie ? "shot on goal he faced" : "shot he took"} from the NHL’s own play-by-play, where it was taken, turned so every shot faces the net at the top (a half turn, so his left stays his left); a shot from beyond the blue line sits on it. ${goalie ? "Green was saved, red went in; an empty net is not his." : "Gold went in, green was on goal, a ring missed the net and a cross was blocked before it got there."} The slot is the crease and the twenty feet in front of the net, the high slot twenty to thirty-five feet out, the point the rest. Expected goals (xG) are our own model, fitted on every stored shot by distance, angle, shot type, rebound, rush and strength${goalie ? "; xGA is the expected goals of the shots he faced, GSAx the goals he saved above it (xGA minus the goals against, GA)" : ""}.</p>`;

  const spec = (goalie) => ({
    one: goalie ? "shot faced" : "shot attempt",
    splitsTitle: "Every split · distance, kind of shot, strength",
    items: (g) => g.shots || [],
    count: (L) => (goalie ? `${L.shots.toLocaleString()} shots faced` : `${L.att.toLocaleString()} attempts`),
    chip: (g) => (goalie ? `${g.line.saves}/${g.line.shots} saved` : `${g.line.sog} SOG${g.line.goals ? `, ${g.line.goals} G` : ""}`),
    zones,
    game: drawGame(goalie),
    season: drawSeason(goalie),
    legend: () => legend(goalie),
    gameSide: (g) => (goalie ? goalieTiles(g.line) : skaterTiles(g.line)),
    seasonSide: (d) => (goalie ? goalieTiles(d.season_line, true) : skaterTiles(d.season_line, true)),
    //: His card's five (carrychart.js `playerHero`): a goalie's saves, a skater's shots.
    heroTiles: (d) => { const L = d.season_line || {};
      return goalie ? [["Games", L.games], ["SV%", svPct(L.sv_pct)], ["GA", L.ga], ["GSAx", plus1(L.gsax)], ["Shots/gm", num1(L.shots_pg)]]
        : [["Games", L.games], ["Goals", L.goals], ["SOG/gm", num1(L.sog_pg)], ["SH%", pct(L.sh_pct)], ["xG", num1(L.ixg)]]; },
    list: (g) => list(g, goalie),
    flags: goalie ? goalieFlags : skaterFlags, filters: FILTERS[goalie ? "goalie" : "skater"], csv: csv(goalie),
    views: (d) => VIEWS.filter(([, , k]) => (d[k] || []).length).map(([k, name]) => [k, name]),
    barTitle: (v) => `${goalie ? "Shots faced" : "Shot attempts"} ${TITLE[v]}`,
    bars: (d, v) => shotBars(d, v, goalie),
    splits: (d) => tables(d, goalie),
    note: () => note(goalie),
    tip: (s) => `<b class="${goalie ? (s.g ? "loss" : "gain") : s.g ? "gain" : "miss"}">${esc(goalie ? (s.g ? "Goal" : "Saved") : KIND[s.k] || s.k)}</b>${s.d != null ? ` · ${esc(feet(s.d))}` : ""}
      <span>${esc([per(s.p), shotType(s.t), xgWord(s), goalie ? (s.by ? `by ${s.by}` : "") : (s.vs && s.k !== "block" ? `on ${s.vs}` : "")].filter(Boolean).join(" · "))}</span>`,
  });
  Q.draw("shotmap", spec(false));
  Q.draw("saves", spec(true));
})();
