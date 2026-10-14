/* Qellys Book — baseball's charts (js/chart-mlb.js): the hit tracker and the pitch chart.
   ==========================================================================
   Ethan, 2026-10-13: "Can we do a hit tracker for mlb?", then "Yes do all
   of them ... make sure they are all routed correctly like nfl." Loaded
   by js/carrychart.js the first time a baseball chart is drawn, and drawn
   in its frame — the games row, the By game | season tabs, the numbers
   beside the drawing, every plate appearance in order, the splits and how
   it is drawn — so a hitter's chart reads like a back's.

   THE HIT TRACKER (kind "spray", engine/mlb/charts.hits_chart): every ball
   he put in play, where it landed on the field (MLB's Stats API hit
   coordinates), coloured by what it became, with its exit velocity,
   launch angle and distance. A walk or a strikeout has no ball in play:
   listed, never drawn.

   THE PITCH CHART (kind "pitches", engine/mlb/charts.pitches_chart):
   every pitch a pitcher threw, where it crossed the plate from the
   catcher's view, coloured by what came of it; his mix, his zones and his
   fastball's speed start by start.

   IN THE FRAME OF ETHAN'S NFL RENDERS (2026-10-14): the field dark with
   its mowing rings, the chalk lit and the wall in his team's colour, the
   pull side, the middle and the opposite field as the render's Left |
   Middle | Right with their counts; a pitcher's fastballs, breaking balls
   and offspeed the same way over the zone; Batted ball | Direction |
   Pitcher hand and Pitch mix | Zones | Velocity as the route chart's other
   views; and every plate appearance, or every batter faced, in the
   render's table, filtered and downloadable.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, ord, state, grid, two, pills, bars } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const SHORT = { single: "1B", double: "2B", triple: "3B", home_run: "HR", walk: "BB", intent_walk: "IBB",
                  hit_by_pitch: "HBP", strikeout: "K", strikeout_double_play: "K", field_out: "Out",
                  force_out: "Out", grounded_into_double_play: "GIDP", double_play: "DP", triple_play: "TP",
                  sac_fly: "SF", sac_bunt: "SAC", field_error: "E", fielders_choice: "FC",
                  fielders_choice_out: "FC", catcher_interf: "CI", sac_fly_double_play: "SF" };
  const HITS = { single: 1, double: 2, triple: 3, home_run: 4 };
  const TYPE = { ground_ball: "ground ball", line_drive: "line drive", fly_ball: "fly ball", popup: "popup" };
  const DIR = { pull: "Pulled", center: "Up the middle", oppo: "Opposite field" };
  const PITCH = { FF: "Four-seam", SI: "Sinker", FC: "Cutter", SL: "Slider", ST: "Sweeper", SV: "Slurve",
                  CU: "Curveball", KC: "Knuckle curve", CS: "Slow curve", CH: "Changeup", FS: "Splitter",
                  FO: "Forkball", SC: "Screwball", KN: "Knuckleball", EP: "Eephus", PO: "Pitchout", FA: "Fastball" };
  const pitchName = (t) => PITCH[t] || t || "Unknown";
  const avg3 = (v) => (v == null ? "—" : Number(v).toFixed(3).replace(/^0/, ""));
  const innLabel = (inn, half) => (inn ? `${half === "T" ? "▲" : half === "B" ? "▼" : ""}${ord(inn) || `${inn}th`}` : "");
  const band = (et) => (et === "home_run" || HITS[et] ? "gain" : /strikeout/.test(et) ? "loss"
    : /walk|hit_by_pitch|catcher/.test(et) ? "short" : "miss");
  function ballWords(p) {
    return [p.ls != null ? `${Math.round(p.ls)} mph` : "", p.la != null ? `${Math.round(p.la)}°` : "",
            p.d != null ? `${Math.round(p.d)} ft` : "", TYPE[p.tr] || ""].filter(Boolean).join(" · ");
  }
  const vsWho = (p) => `vs ${p.p || "?"}${p.ph ? ` (${p.ph})` : ""}`;
  //: What a plate appearance became, as a pill: a home run in gold, a hit green, a strikeout red.
  const hitPill = (et, ev) => [SHORT[et] || ev || "—", et === "home_run" ? "gold" : HITS[et] ? "good"
    : /strikeout/.test(et) ? "bad" : "mute"];

  /* ---------------- the field ---------------- */
  /* The Stats API's hit coordinates, home plate at (125.42, 198.27), y
     growing toward home; drawn top-down with home at the foot. The grass
     dark with its mowing rings out from the plate, the chalk lit (a faint
     wide copy under each line, no filter), the wall in his colour. */
  const HX = 200, HY = 336, K = 1.45;
  const fx = (x) => HX + (x - 125.42) * K;
  const fy = (y) => HY - (198.27 - y) * K;
  //: A point r out from the plate, `a` degrees off straightaway centre.
  const at = (r, a) => [HX + r * Math.sin(a * Math.PI / 180), HY - r * Math.cos(a * Math.PI / 180)];
  const xy = (p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`;
  function rings() {
    let s = "";
    for (let r = 40, k = 0; r < 190; r += 25, k++) {
      const r2 = Math.min(190, r + 25);
      s += `<path class="mb-mow${k % 2 ? " alt" : ""}" d="M${xy(at(r, -45))} A${r} ${r} 0 0 1 ${xy(at(r, 45))} L${xy(at(r2, 45))} A${r2} ${r2} 0 0 0 ${xy(at(r2, -45))} Z"/>`;
    }
    return s;
  }
  function fieldSVG() {
    const poleL = [65, 201], poleR = [335, 201];
    const chalk = `<line x1="${HX}" y1="${HY}" x2="23" y2="159"/><line x1="${HX}" y1="${HY}" x2="377" y2="159"/>
      <path d="M${HX} ${HY} L236.8 299.2 L200 262.5 L163.2 299.2 Z"/>`;
    return `<path class="mb-grass" d="M${HX} ${HY} L${poleL[0]} ${poleL[1]} Q200 7 ${poleR[0]} ${poleR[1]} Z"/>${rings()}
      <path class="mb-dirt" d="M${HX} ${HY} L136.4 272.4 A90 90 0 0 1 263.6 272.4 Z"/>
      <g class="mb-glow">${chalk}</g>
      <path class="mb-base" d="M${HX} ${HY} L236.8 299.2 L200 262.5 L163.2 299.2 Z"/>
      <line class="mb-foul" x1="${HX}" y1="${HY}" x2="23" y2="159"/><line class="mb-foul" x1="${HX}" y1="${HY}" x2="377" y2="159"/>
      <path class="mb-wall-glow" d="M${poleL[0]} ${poleL[1]} Q200 7 ${poleR[0]} ${poleR[1]}"/>
      <path class="mb-wall" d="M${poleL[0]} ${poleL[1]} Q200 7 ${poleR[0]} ${poleR[1]}"/>
      <text class="cc-lane" x="40" y="352">LF line</text><text class="cc-lane" x="360" y="352" text-anchor="end">RF line</text>`;
  }
  function ballMark(p, i, faint) {
    if (p.x == null || p.y == null) return "";
    const x = fx(p.x), y = fy(p.y), kind = p.et === "home_run" ? "hr" : HITS[p.et] ? "h" : "o";
    const r = kind === "hr" ? 6 : 4.5;
    if (faint) return `<circle class="mb-ball ${kind} faint" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r - 1}"/>`;
    return `<g class="cc-carry" data-i="${i}" data-z="${p.dir || ""}">
      <line class="cc-hit" x1="${HX}" y1="${HY}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>
      ${kind === "o" ? "" : `<line class="mb-glow-arc ${kind}" x1="${HX}" y1="${HY}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`}
      <line class="mb-arc ${kind}${sel(i)}" x1="${HX}" y1="${HY}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>
      ${kind === "o" ? "" : `<circle class="mb-halo ${kind}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r + 5}"/>`}
      <circle class="mb-ball cx-mark ${kind}${sel(i)}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}"/></g>`;
  }
  const svg = (body, label, h = 360) =>
    `<svg class="cc-svg mb-svg" viewBox="0 0 400 ${h}" role="img" aria-label="${esc(label)}">${body}</svg>`;

  function sprayGame(g) {
    const pas = g.pas || [];
    const marks = pas.map((p, i) => ballMark(p, i, false)).join("");
    const bip = pas.filter((p) => p.x != null).length;
    return svg(fieldSVG() + marks, `Hit tracker: ${bip} ball${bip === 1 ? "" : "s"} in play. Every plate appearance is listed below.`);
  }
  /* The season: every ball faint, the two lines 15° either side of
     straightaway centre that split the field in three, and the share he
     pulled, hit up the middle and went the other way written under each
     third (under it, so no label ever sits on a ball). */
  function spraySeason(d) {
    const every = [];
    d.games.forEach((g) => (g.pas || []).forEach((p) => every.push(p)));
    let body = fieldSVG() + `<line class="mb-ray" x1="${HX}" y1="${HY}" x2="142.5" y2="121.6"/><line class="mb-ray" x1="${HX}" y1="${HY}" x2="257.4" y2="121.6"/>`
      + every.map((p) => ballMark(p, -1, true)).join("");
    const dirs = d.by_dir || [], tot = dirs.reduce((a, x) => a + x.n, 0);
    const left = d.side === "L" ? "oppo" : "pull", right = d.side === "L" ? "pull" : "oppo";
    [[left, 70], ["center", 200], [right, 330]].forEach(([k, x]) => {
      const row = dirs.find((r) => r.key === k);
      if (!row || !tot) return;
      body += `<text class="cc-raylbl" x="${x}" y="380" text-anchor="middle">${pct(row.n / tot)}</text>
        <text class="cc-raysub" x="${x}" y="397" text-anchor="middle">${esc(DIR[k])}</text>`;
    });
    return svg(body, `Hit tracker: ${every.filter((p) => p.x != null).length} balls in play this season.`, 402);
  }
  function sprayLegend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt mb-hr"></i>Home run</span>
      <span><i class="dt c"></i>Hit</span><span><i class="dt m"></i>Out</span></div>`;
  }
  function sprayTiles(L) {
    const t = [tile("H–AB", `${L.h}-${L.ab}`), tile("Total bases", L.tb), tile("HR", L.hr), tile("RBI", L.rbi),
               tile("BB–K", `${L.bb}-${L.k}`), tile("Hard hit", L.bip ? `${L.hard}/${L.bip}` : "—", "95+ mph")];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  /* The render's Left | Middle | Right, for a hitter: where his balls in
     play went, read off where each landed and which side he stood on. */
  const sprayZones = {
    label: "Where he hit it",
    list: [["pull", "Pull", "Pulled"], ["center", "Center", "Up the middle"], ["oppo", "Oppo", "Opposite field"]],
    of: (p) => p.dir || "",
    pool: (g) => (g.pas || []).filter((p) => p.x != null),
    noun: ["ball", "balls"],
  };
  /* EVERY PLATE APPEARANCE AS THE RENDERS' TABLE: its number, the inning,
     the pitcher, how hard, how high and how far the ball went, what it
     became and the runs it drove in. On a phone the inning and the ball's
     numbers read under the pitcher. */
  const SPRAY_COLS = [{ h: "#", c: "cc-c-n", p: "18px", w: "26px" },
                      { h: "Inn", c: "cc-c-q", w: "52px" },
                      { h: "Pitcher", c: "cc-c-m", p: "minmax(0,1fr)" },
                      { h: "Pitcher", c: "cc-c-m", w: "minmax(0,1fr)" },
                      { h: "EV", c: "cc-c-v", w: "52px", r: 1 },
                      { h: "LA", c: "cc-c-v", w: "44px", r: 1 },
                      { h: "Dist", c: "cc-c-v", w: "52px", r: 1 },
                      { h: "Result", c: "cc-c-res", p: "96px", w: "150px" },
                      { h: "RBI", c: "cc-c-y", w: "40px", r: 1 }];
  function sprayList(g) {
    return grid("spray", SPRAY_COLS, (g.pas || []).map((p, i) => {
      const hard = p.ls != null && p.ls >= 95;
      const res = [hitPill(p.et, p.ev)].concat(hard ? [["Hard hit", "tag"]] : []);
      return {
        i, f: sprayFlags(p),
        said: [innLabel(p.inn, p.half), vsWho(p), p.ev, ballWords(p), p.rbi ? `${p.rbi} RBI` : "", hard ? "hard hit" : ""]
          .filter(Boolean).join(", "),
        cells: [`${i + 1}`, esc(innLabel(p.inn, p.half) || "—"),
                two(vsWho(p), [innLabel(p.inn, p.half), p.rbi ? `${p.rbi} RBI` : "", ballWords(p)].filter(Boolean).join(" · ")),
                two(vsWho(p), [p.ev, TYPE[p.tr] || "", p.dir && p.dir !== "center" ? DIR[p.dir] : ""].filter(Boolean).join(" · ")),
                esc(p.ls == null ? "—" : `${Math.round(p.ls)}`), esc(p.la == null ? "—" : `${Math.round(p.la)}°`),
                esc(p.d == null ? "—" : `${Math.round(p.d)}`), pills(res), [p.rbi ? `${p.rbi}` : "—", p.rbi ? "gain" : "miss"]],
      };
    }));
  }
  const sprayFlags = (p) => [HITS[p.et] ? "h" : "", p.et === "home_run" ? "hr" : "", p.x != null ? "bip" : "",
                             p.ls != null && p.ls >= 95 ? "hard" : "", /strikeout/.test(p.et) ? "k" : "",
                             /walk|hit_by_pitch/.test(p.et) ? "bb" : "", p.rbi ? "rbi" : ""].filter(Boolean).join(" ");
  const SPRAY_FILTERS = [["", "Every plate appearance"], ["h", "Hits"], ["hr", "Home runs"], ["bip", "Balls in play"],
                         ["hard", "Hard hit"], ["k", "Strikeouts"], ["bb", "Walks"], ["rbi", "Drove in a run"]];
  const sprayCsv = (g) => [["#", "Inning", "Pitcher", "Throws", "Result", "Event", "Exit velocity (mph)", "Launch angle",
                            "Distance (ft)", "Batted ball", "Direction", "RBI", "Pitches", "xBA"]]
    .concat((g.pas || []).map((p, i) => [i + 1, innLabel(p.inn, p.half), p.p, p.ph, SHORT[p.et] || "", p.ev,
      p.ls == null ? "" : p.ls, p.la == null ? "" : p.la, p.d == null ? "" : p.d, TYPE[p.tr] || "", DIR[p.dir] || "",
      p.rbi || 0, p.np == null ? "" : p.np, p.xh == null ? "" : p.xh]));
  /* Our expected average and slugging (engine/mlb/xstats), and what the
     held-out test (engine/mlb/xstatsfit) said of them, if it has run. */
  function xNote(d) {
    if (!d || !d.season_line || d.season_line.xba == null) return "";
    const m = d.x_measured;
    const said = !m ? "It has not yet been measured as a pick signal"
      : m.hits || m.bases ? `Measured on games it never saw${m.at ? ` (${m.at})` : ""}, it read a hitter’s next game better than his own ${m.hits && m.bases ? "average and slugging" : m.hits ? "average" : "slugging"} did; it is still context`
      : `Measured on games it never saw${m.at ? ` (${m.at})` : ""}, it did not read a hitter’s next game better than his own average and slugging did`;
    return ` xBA and xSLG are ours: each ball’s chance of a hit and the bases it was worth, from how hard and at what angle it left the bat, over every ball in play we have stored; a strikeout counts nothing, and an at bat with no reading counts what it was. ${said}, so nothing here moves a price.`;
  }
  function sprayTables(d) {
    const out = [];
    const xs = d.season_line && d.season_line.xba != null;
    const C = (x) => [x.bip || x.n, x.h, x.hr, pct(x.n ? x.h / x.n : null)].concat(xs ? [avg3(x.xba)] : []);
    const H = (first) => [first, "In play", "Hits", "HR", "Hit rate"].concat(xs ? ["xBA"] : []);
    if (d.by_type && d.by_type.length) {
      out.push(tableHTML("By how he hit it", H("Batted ball"), d.by_type.map((x) => [x.name, ...C(x)])));
    }
    if (d.by_dir && d.by_dir.length) {
      out.push(tableHTML("By where he hit it", H("Direction"), d.by_dir.map((x) => [x.name, ...C(x)])));
    }
    if (d.by_hand && d.by_hand.length) {
      out.push(tableHTML("Against right- and left-handers", ["Pitcher", "PA", "H", "HR", "BB", "K", "AVG"],
        d.by_hand.map((x) => [x.name, x.pa, x.h, x.hr, x.bb, x.k, avg3(x.avg)])));
    }
    return out.join("");
  }
  /* THE OTHER VIEWS: his balls in play by how he hit them and where they
     went, and his plate appearances against each hand, as bars. */
  const SPRAY_VIEWS = [["type", "Batted ball", "by_type"], ["dir", "Direction", "by_dir"], ["hand", "Pitcher hand", "by_hand"]];
  const SPRAY_TITLE = { type: "Balls in play by how he hit them", dir: "Balls in play by direction",
                        hand: "Plate appearances against each hand" };
  function sprayBars(d, view) {
    if (view === "hand") {
      return bars((d.by_hand || []).map((x) => [x.name, x.pa, `${x.h} H · ${x.hr} HR · ${x.bb} BB · ${x.k} K · AVG ${avg3(x.avg)}`]));
    }
    return bars(((view === "type" ? d.by_type : d.by_dir) || []).map((x) => [x.name, x.bip || x.n,
      `${x.h} hit${x.h === 1 ? "" : "s"} · ${x.hr} HR · ${pct(x.n ? x.h / x.n : null)} hit rate${x.xba == null ? "" : ` · xBA ${avg3(x.xba)}`}`]));
  }

  Q.draw("spray", {
    one: "plate appearance", splitsTitle: "Every split · batted ball, direction, pitcher's hand",
    items: (g) => g.pas || [],
    count: (L) => `${L.pa} plate appearances`,
    chip: (g) => `${g.line.h}-${g.line.ab}${g.line.hr ? `, ${g.line.hr} HR` : ""}`,
    zones: sprayZones,
    game: (g) => sprayGame(g),
    season: (d) => spraySeason(d),
    legend: () => sprayLegend(),
    gameSide: (g) => sprayTiles(g.line),
    seasonSide: (d) => {
      const L = d.season_line;
      return `${sprayTiles(L)}
        <div class="cc-tiles cc-tiles-2">${tile("AVG", avg3(L.avg), L.xba == null ? "" : `xBA ${avg3(L.xba)}`)}${tile("SLG", avg3(L.slg), L.xslg == null ? "" : `xSLG ${avg3(L.xslg)}`)}${tile("Exit velocity", L.ev == null ? "—" : `${num1(L.ev)} mph`, "average")}${tile("Launch angle", L.la == null ? "—" : `${num1(L.la)}°`, "average")}${tile("Hard hit", pct(L.bip ? L.hard / L.bip : null))}${tile("Sweet spot", pct(L.bip ? L.sweet / L.bip : null), "8–32°")}</div>`;
    },
    list: (g) => sprayList(g),
    flags: sprayFlags, filters: SPRAY_FILTERS, csv: sprayCsv,
    views: (d) => SPRAY_VIEWS.filter(([, , k]) => (d[k] || []).length).map(([k, name]) => [k, name]),
    barTitle: (v) => SPRAY_TITLE[v],
    bars: (d, v) => sprayBars(d, v),
    splits: (d) => sprayTables(d),
    note: (d) => `<p class="cc-note">Each dot is where a ball he put in play landed, from MLB’s Stats API play-by-play (its hit coordinates); exit velocity, launch angle and distance are the league’s own numbers as that feed carries them. Hard hit is 95 mph or harder; the sweet spot is a launch angle of 8 to 32 degrees. Pulled, up the middle and opposite field are read off where the ball landed and which side of the plate he stood on (within 15° of straightaway centre is up the middle). A walk, a hit by pitch or a strikeout has no ball in play: listed, not drawn.${xNote(d)}</p>`,
    tip: (p) => `<b class="${band(p.et)}">${esc(p.ev)}</b>${p.rbi ? ` · ${p.rbi} RBI` : ""}
      <span>${esc([innLabel(p.inn, p.half), `off ${p.p || "?"}${p.ph ? ` (${p.ph})` : ""}`, ballWords(p),
                   p.xh != null ? `xBA ${avg3(p.xh)}` : ""].filter(Boolean).join(" · "))}</span>`,
  });

  /* ---------------- the strike zone ---------------- */
  /* Feet across the plate (pX, from the catcher's view) and up from the
     ground (pZ), to the drawing: 62 px a foot, the ground at the foot. The
     zone lit, as the render lights its line of scrimmage. */
  const ZX = 150, ZG = 310, F = 62;
  const zx = (px) => ZX + px * F, zy = (pz) => ZG - pz * F;
  const HALF_PLATE = 17 / 24;                 // 17 inches, half of it, in feet
  //: A pitch's outcome, by the umpire's call code (engine/mlb/charts).
  const WHIFF = new Set(["S", "W", "M", "Q"]), FOUL = new Set(["F", "T", "L", "O", "R"]), PLAY = new Set(["X", "D", "E"]);
  const outcome = (code) => (code === "C" ? "c" : WHIFF.has(code) ? "w" : PLAY.has(code) ? "x" : FOUL.has(code) ? "f" : "b");
  const OUTCOME = { c: "Called strike", w: "Whiff", x: "In play", f: "Foul", b: "Ball" };
  /* The render's Left | Middle | Right, for a pitcher: his fastballs, his
     breaking balls and his offspeed (the league's own grouping of its
     pitch types; a pitchout is none of them). */
  const GROUP = { FF: "F", SI: "F", FC: "F", FA: "F", SL: "B", ST: "B", SV: "B", CU: "B", KC: "B", CS: "B",
                  CH: "O", FS: "O", FO: "O", SC: "O", EP: "O", KN: "O" };
  const pitchZones = {
    label: "Which pitches",
    list: [["F", "Fastballs", "Fastballs"], ["B", "Breaking", "Breaking"], ["O", "Offspeed", "Offspeed"]],
    of: (p) => GROUP[p[0]] || "",
    pool: (g) => g.p || [],
    noun: ["pitch", "pitches"],
  };
  function zoneBox(ps) {
    const tops = ps.map((p) => p[6]).filter((v) => v != null), bots = ps.map((p) => p[7]).filter((v) => v != null);
    const top = tops.length ? tops.reduce((a, b) => a + b, 0) / tops.length : 3.4;
    const bot = bots.length ? bots.reduce((a, b) => a + b, 0) / bots.length : 1.6;
    return { top, bot, x0: zx(-HALF_PLATE), x1: zx(HALF_PLATE), y0: zy(top), y1: zy(bot) };
  }
  function zoneSVG(z) {
    const w = (z.x1 - z.x0) / 3, h = (z.y1 - z.y0) / 3;
    let grid9 = "";
    for (let i = 1; i < 3; i++) {
      grid9 += `<line class="mp-grid" x1="${(z.x0 + w * i).toFixed(1)}" y1="${z.y0.toFixed(1)}" x2="${(z.x0 + w * i).toFixed(1)}" y2="${z.y1.toFixed(1)}"/>
        <line class="mp-grid" x1="${z.x0.toFixed(1)}" y1="${(z.y0 + h * i).toFixed(1)}" x2="${z.x1.toFixed(1)}" y2="${(z.y0 + h * i).toFixed(1)}"/>`;
    }
    const plate = `M${zx(-HALF_PLATE).toFixed(1)} 314 L${zx(HALF_PLATE).toFixed(1)} 314 L${zx(HALF_PLATE).toFixed(1)} 320 L${ZX} 326 L${zx(-HALF_PLATE).toFixed(1)} 320 Z`;
    const box = `x="${z.x0.toFixed(1)}" y="${z.y0.toFixed(1)}" width="${(z.x1 - z.x0).toFixed(1)}" height="${(z.y1 - z.y0).toFixed(1)}"`;
    return `<rect class="mp-zone-glow" ${box}/><rect class="mp-zone" ${box}/>
      ${grid9}<path class="mp-plate" d="${plate}"/>
      <text class="cc-lane" x="8" y="20">Catcher’s view</text>`;
  }
  const zsvg = (body, label) =>
    `<svg class="cc-svg mp-svg" viewBox="0 0 300 330" role="img" aria-label="${esc(label)}">${body}</svg>`;
  function pitchGame(g) {
    const ps = g.p || [], faced = g.faced || [];
    const ix = {};
    faced.forEach((x, i) => { ix[x.ab] = i; });
    const z = zoneBox(ps);
    let dots = "";
    ps.forEach((p) => {
      if (p[2] == null || p[3] == null) return;
      const i = ix[p[9]] == null ? -1 : ix[p[9]];
      const x = Math.max(4, Math.min(296, zx(p[2]))), y = Math.max(4, Math.min(306, zy(p[3])));
      dots += `<g class="cc-carry" data-i="${i}" data-z="${pitchZones.of(p)}"><circle class="mp cx-mark ${outcome(p[4])}${sel(i)}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.5"/></g>`;
    });
    return zsvg(zoneSVG(z) + dots, `Pitch chart: ${ps.length} pitches. Every batter he faced is listed below.`);
  }
  /* The season: the share of his pitches in each of the zone's nine boxes
     and in the four corners outside it, and his whiffs there. */
  function pitchSeason(d) {
    const every = [];
    d.games.forEach((g) => (g.p || []).forEach((p) => every.push(p)));
    const z = zoneBox(every);
    const w = (z.x1 - z.x0) / 3, h = (z.y1 - z.y0) / 3;
    const ox0 = z.x0 - w * 1.4, ox1 = z.x1 + w * 1.4, oy0 = z.y0 - h * 1.4, oy1 = z.y1 + h * 1.4;
    const mx = (ox0 + ox1) / 2, my = (oy0 + oy1) / 2;
    const by = {};
    (d.zones || []).forEach((r) => { by[r.zone] = r; });
    const most = Math.max(0.0001, ...(d.zones || []).map((r) => r.share || 0));
    const cell = (r, x, y, ww, hh, lx, ly) => {
      if (!r) return "";
      const op = r.n ? (0.08 + 0.55 * (r.share || 0) / most).toFixed(2) : "0";
      return `<rect class="mp-cell" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${ww.toFixed(1)}" height="${hh.toFixed(1)}" style="fill-opacity:${op}"/>
        ${r.n ? `<text class="cc-raylbl mp-lbl" x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle">${pct(r.share)}</text>` : ""}`;
    };
    let body = "";
    [[11, ox0, oy0], [12, mx, oy0], [13, ox0, my], [14, mx, my]].forEach(([k, x, y]) => {
      const lx = k === 11 || k === 13 ? ox0 + 16 : ox1 - 16, ly = k <= 12 ? oy0 + 18 : oy1 - 8;
      body += cell(by[k], x, y, mx - ox0, my - oy0, lx, ly);
    });
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        const k = r * 3 + c + 1, x = z.x0 + w * c, y = z.y0 + h * r;
        body += cell(by[k], x, y, w, h, x + w / 2, y + h / 2 + 5);
      }
    }
    return zsvg(body + zoneSVG(z), `Pitch chart: ${every.length} pitches this season, by zone.`);
  }
  function velo(d) {
    const v = d.velo || [];
    if (v.length < 2) return "";
    const lo = Math.min(...v.map((x) => x.avg)) - 0.5, hi = Math.max(...v.map((x) => x.avg)) + 0.5;
    const X = (i) => 16 + (268 * i) / (v.length - 1), Y = (a) => 78 - ((a - lo) / Math.max(0.1, hi - lo)) * 62;
    const pts = v.map((x, i) => `${X(i).toFixed(1)},${Y(x.avg).toFixed(1)}`).join(" ");
    return `<div class="mp-velo"><div class="mp-velo-h">${esc(pitchName(d.velo_type))} speed, start by start</div>
      <svg class="cc-svg" viewBox="0 0 300 96" role="img" aria-label="${esc(`${pitchName(d.velo_type)} average speed by start, ${num1(v[0].avg)} to ${num1(v[v.length - 1].avg)} mph`)}">
        <polyline class="mp-line-glow" points="${pts}"/>
        <polyline class="mp-line" points="${pts}"/>
        ${v.map((x, i) => `<circle class="mp-pt" cx="${X(i).toFixed(1)}" cy="${Y(x.avg).toFixed(1)}" r="3"/>`).join("")}
        <text class="cc-lane" x="4" y="12">${num1(hi - 0.5)}</text><text class="cc-lane" x="4" y="92">${num1(lo + 0.5)}</text>
      </svg></div>`;
  }
  function pitchLegend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt mp-c"></i>Called strike</span>
      <span><i class="dt mp-w"></i>Whiff</span><span><i class="dt mp-f"></i>Foul</span>
      <span><i class="dt mp-x"></i>In play</span><span><i class="dt mp-b"></i>Ball</span></div>`;
  }
  function pitchTiles(L) {
    const t = [tile("Pitches", L.pitches), tile("Strikeouts", L.k), tile("Walks", L.bb), tile("Hits", L.h),
               tile("Whiffs", L.whiffs), tile("CSW", pct(L.csw), "called + whiffs")];
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  /* Six columns, so the table fits beside the drawing on a desktop and
     across a phone without scrolling sideways. */
  function mixTable(mix, cap) {
    return mix && mix.length ? tableHTML(cap, ["Pitch", "Thrown", "Share", "mph", "Whiff", "CSW"],
      mix.map((m) => [pitchName(m.type), m.n, pct(m.share), num1(m.velo), pct(m.whiff), pct(m.csw)])) : "";
  }
  /* EVERY BATTER HE FACED AS THE RENDERS' TABLE: the inning, the batter
     and the side he hit from, the pitches it took, and how it ended — seen
     from the mound, so a strikeout is green and a hit red. */
  const FACED_COLS = [{ h: "#", c: "cc-c-n", p: "18px", w: "26px" },
                      { h: "Inn", c: "cc-c-q", w: "52px" },
                      { h: "Batter", c: "cc-c-m", p: "minmax(0,1fr)" },
                      { h: "Batter", c: "cc-c-m", w: "minmax(0,1fr)" },
                      { h: "Pitches", c: "cc-c-v", w: "64px", r: 1 },
                      { h: "Result", c: "cc-c-res", p: "96px", w: "160px" }];
  const mound = (et, ev) => {
    const b = band(et);
    return [SHORT[et] || ev || "—", b === "loss" ? "good" : b === "gain" || b === "short" ? "bad" : "mute"];
  };
  const batter = (x) => `${x.b || "?"}${x.bs ? ` (${x.bs})` : ""}`;
  function facedList(g) {
    return grid("faced", FACED_COLS, (g.faced || []).map((x, i) => {
      const res = [mound(x.et, x.ev)].concat(x.rbi ? [[`${x.rbi} RBI`, "bad"]] : []);
      return {
        i, f: facedFlags(x),
        said: [innLabel(x.inn, x.half), batter(x), `${x.np} pitch${x.np === 1 ? "" : "es"}`, x.ev, x.rbi ? `${x.rbi} RBI` : ""]
          .filter(Boolean).join(", "),
        cells: [`${i + 1}`, esc(innLabel(x.inn, x.half) || "—"),
                two(batter(x), [innLabel(x.inn, x.half), `${x.np} pitch${x.np === 1 ? "" : "es"}`].filter(Boolean).join(" · ")),
                two(batter(x), x.ev || ""), esc(x.np == null ? "—" : `${x.np}`), pills(res)],
      };
    }));
  }
  const facedFlags = (x) => [/strikeout/.test(x.et) ? "k" : "", /walk|hit_by_pitch/.test(x.et) ? "bb" : "",
                             HITS[x.et] ? "h" : "", x.et === "home_run" ? "hr" : "",
                             band(x.et) === "miss" ? "out" : "", x.rbi ? "rbi" : ""].filter(Boolean).join(" ");
  const FACED_FILTERS = [["", "Every batter"], ["k", "Strikeouts"], ["out", "Outs in play"], ["bb", "Walks"],
                         ["h", "Hits"], ["hr", "Home runs"], ["rbi", "Runs driven in"]];
  //: The spreadsheet is every pitch, with the batter it was thrown to.
  function pitchCsv(g) {
    const by = {};
    (g.faced || []).forEach((x) => { by[x.ab] = x; });
    return [["#", "Inning", "Batter", "Bats", "Pitch", "Speed (mph)", "Result", "Zone", "Across the plate (ft)", "Height (ft)"]]
      .concat((g.p || []).map((p, i) => {
        const x = by[p[9]] || {};
        return [i + 1, p[8] || "", x.b || "", p[10] || x.bs || "", pitchName(p[0]), p[1] == null ? "" : p[1],
                OUTCOME[outcome(p[4])], p[5] == null ? "" : p[5], p[2] == null ? "" : p[2], p[3] == null ? "" : p[3]];
      }));
  }
  /* THE OTHER VIEWS: his mix, where in and around the zone his pitches
     went (grouped as a scout reads it), and his fastball start by start. */
  const AREAS = [["Heart of the zone", [5]], ["Up in the zone", [1, 2, 3]], ["Down in the zone", [7, 8, 9]],
                 ["In or away, mid-height", [4, 6]], ["Above the zone", [11, 12]], ["Below the zone", [13, 14]]];
  function pitchBars(d, view) {
    if (view === "mix") {
      return bars((d.mix || []).map((m) => [pitchName(m.type), m.n,
        `${num1(m.velo)} mph · whiff ${pct(m.whiff)} · CSW ${pct(m.csw)}`]));
    }
    if (view === "zones") {
      const by = {};
      (d.zones || []).forEach((r) => { by[r.zone] = r; });
      return bars(AREAS.map(([name, ks]) => {
        const rs = ks.map((k) => by[k]).filter(Boolean);
        const n = rs.reduce((a, r) => a + (r.n || 0), 0), wh = rs.reduce((a, r) => a + (r.whiffs || 0), 0);
        const sw = rs.reduce((a, r) => a + (r.swings || 0), 0);
        return [name, n, `${wh} whiff${wh === 1 ? "" : "s"} · ${sw ? pct(wh / sw) : "—"} of swings missed`];
      }));
    }
    return velo(d) + bars((d.velo || []).slice().reverse().map((v) => {
      const t = v.date ? new Date(`${v.date}T12:00:00`) : null;
      const day = t && !isNaN(t) ? t.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : v.date;
      return [`${day} vs ${v.opp}`, v.n, `${num1(v.avg)} mph average`];
    }));
  }
  const PITCH_TITLE = { mix: "Pitches by type", zones: "Pitches by where they crossed", velo: "His fastball, start by start" };

  Q.draw("pitches", {
    one: "batter faced", splitsTitle: "Every split · pitch mix",
    items: (g) => g.faced || [],
    count: (L) => `${L.pitches.toLocaleString()} pitches`,
    chip: (g) => `${g.line.k} K · ${g.line.pitches}p`,
    zones: pitchZones,
    game: (g) => pitchGame(g),
    season: (d) => pitchSeason(d),
    legend: (g) => (g ? pitchLegend() : `<div class="cc-legend" aria-hidden="true"><span><i class="sw cell"></i>Share of his pitches</span></div>`),
    gameSide: (g) => `${pitchTiles(g.line)}${mixTable(g.mix, "This game’s mix")}`,
    seasonSide: (d) => {
      const L = d.season_line;
      return `${pitchTiles(L)}
        <div class="cc-tiles cc-tiles-2">${tile("Whiff rate", pct(L.whiff), "per swing")}${tile("In the zone", pct(L.zone))}${tile("Batters faced", L.bf)}${tile("Top speed", L.top == null ? "—" : `${num1(L.top)} mph`)}</div>
        ${velo(d)}`;
    },
    list: (g) => facedList(g),
    flags: facedFlags, filters: FACED_FILTERS, csv: pitchCsv,
    views: (d) => [["mix", "Pitch mix", (d.mix || []).length], ["zones", "Zones", (d.zones || []).some((r) => r.n)],
                   ["velo", "Velocity", (d.velo || []).length > 1]].filter((v) => v[2]).map(([k, name]) => [k, name]),
    barTitle: (v, d) => (v === "velo" ? `His ${pitchName(d.velo_type).toLowerCase()}, start by start` : PITCH_TITLE[v]),
    bars: (d, v) => pitchBars(d, v),
    splits: (d) => mixTable(d.mix, "His pitch mix"),
    note: () => `<p class="cc-note">Each dot is a pitch where it crossed the plate, seen from behind the catcher (MLB’s Stats API: feet from the middle of the plate and up from the ground); the box is his average strike zone in those games, split in nine. Called strike and whiff are the umpire’s call and the swing as the feed records them; CSW is called strikes plus whiffs over every pitch, the whiff rate is misses over swings (a foul tip is contact). Fastballs are his four-seamers, sinkers and cutters; breaking balls his sliders, sweepers and curves; offspeed his changeups, splitters and the rest. The season view shades the zone’s nine boxes and the four corners outside it by the share of his pitches there. Speed is the release speed; mph is his average for that pitch.</p>`,
    tip: (x) => `<b>${esc(x.ev)}</b>${x.rbi ? ` · ${x.rbi} RBI` : ""}
      <span>${esc([innLabel(x.inn, x.half), `${x.b || "?"}${x.bs ? ` (${x.bs})` : ""}`, `${x.np} pitch${x.np === 1 ? "" : "es"}`].join(" · "))}</span>`,
  });
})();
