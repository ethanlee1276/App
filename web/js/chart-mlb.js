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

   THE HIT PAGE TO ETHAN'S OWN FOUR RENDERS OF IT (2026-10-14: "Also here
   is renders for mlb hit page. Follow these."): the hit tracker lays its
   own page out (`page`, below) — his season over his club's park, By game
   with his recent games, the game's final and every at-bat with its
   pitches, Where he hits it over the park with his season against any
   kind of pitch.

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
  //: An inning as a hitter's table says it: his own half, so no arrow.
  const nth = (n) => {
    if (!n) return "—";
    const v = n % 100, s = ["th", "st", "nd", "rd"];
    return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
  };
  const band = (et) => (et === "home_run" || HITS[et] ? "gain" : /strikeout/.test(et) ? "loss"
    : /walk|hit_by_pitch|catcher/.test(et) ? "short" : "miss");
  function ballWords(p) {
    return [p.ls != null ? `${Math.round(p.ls)} mph` : "", p.la != null ? `${Math.round(p.la)}°` : "",
            p.d != null ? `${Math.round(p.d)} ft` : "", TYPE[p.tr] || ""].filter(Boolean).join(" · ");
  }
  const vsWho = (p) => `vs ${p.p || "?"}${p.ph ? ` (${p.ph})` : ""}`;

  /* ---------------- the hit page (2026-10-14) ----------------
     Ethan, with four renders of this page: "Also here is renders for mlb
     hit page. Follow these." His season over his club's park — the logo,
     his name, his position and number, the season to pick and five
     numbers — then the views as tabs:
       BY GAME: his recent games in a row (the last 10, 20 or 30, and what
       he did over them), the game's final, its numbers, every at-bat as
       the renders' table (the pitch it ended on and how fast, what it
       became and where it went, how hard and how far) with each at-bat's
       pitches a tap away, the game's summary, and where its balls went
       over his season's;
       WHERE HE HITS IT: every ball he put in play over the park, lit by
       what it became, the pull side, the middle and the other way with
       their shares, and his season's numbers against any kind of pitch;
       BATTED BALL, DIRECTION and PITCH: his season by each, as bars.
     THE SEVEN THINGS THE RENDERS SHOWED THAT IT DID NOT (Ethan, the same
     day: "do the first 7 page items"), each off MLB's own record: his runs
     and stolen bases game by game (his own game log), both clubs' records
     on the day (the league's schedule, shown only where a count of the
     finals stored agrees with it), the park and a button to MLB's own page
     of the game, barrels (MLB's published rule, on MLB's own exit velocity
     and launch angle) beside MLB's own barrel rate, MLB's own expected
     average and slugging beside ours (Baseball Savant), and his action
     photo in place of his headshot. A number not on file yet is left out,
     never guessed. Every at-bat's video on Baseball Savant was the seventh,
     and is gone (Ethan, 2026-10-14, on MLB's non-commercial terms: "drop
     the video link"). */
  const FIELDER = { 1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF" };
  const NOT_AB = new Set(["walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf",
                          "sac_fly_double_play", "sac_bunt_double_play"]);
  const SAC_FLY = new Set(["sac_fly", "sac_fly_double_play"]);
  const plays = (gs) => [].concat(...(gs || []).map((g) => g.pas || []));
  //: The pitch a plate appearance ended on: [type, mph, call], or null.
  const lastPitch = (p) => (p.ps && p.ps.length ? p.ps[p.ps.length - 1] : null);
  const when = (iso, o) => {
    const t = iso ? new Date(`${iso}T12:00:00`) : null;
    return t && !isNaN(t) ? t.toLocaleDateString("en-US", o) : iso || "";
  };
  const mark = (sport, a, n) => (a && typeof teamMarkIn === "function" ? teamMarkIn(sport, a, n) : "");
  /* MLB'S OWN PAGE OF THE GAME, opened beside ours on MLB.com. */
  const GAMEDAY = (pk) => `https://www.mlb.com/gameday/${encodeURIComponent(pk)}`;
  const ext = (href, html, cls, said) => `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener noreferrer"${said
    ? ` aria-label="${esc(said)}"` : ""}>${html}</a>`;
  const ARROW = '<span aria-hidden="true">↗</span>';
  /* A count over games that every one of them has: his runs or his stolen
     bases over a stretch, or null when a game of it has none on file. */
  const sumOf = (gs, k) => (gs.length && gs.every((g) => g[k] != null) ? gs.reduce((a, g) => a + g[k], 0) : null);
  /* HIS LINE OVER ANY STRETCH, the box score's way and the server's
     (engine/mlb/charts _hline, line for line): ten games, a kind of pitch,
     a hand. On base is hits, walks and hit-by-pitches over at-bats,
     walks, hit-by-pitches and sacrifice flies; xBA and xSLG only where
     the model has read his balls. */
  function line(pas) {
    const o = { pa: pas.length, ab: 0, h: 0, tb: 0, hr: 0, bb: 0, k: 0, hbp: 0, sf: 0, rbi: 0, bip: 0, hard: 0,
                sweet: 0, nla: 0, max: null, brl: 0 };
    let evs = 0, las = 0, xs = 0, xb = 0, any = false;
    pas.forEach((p) => {
      const ab = !NOT_AB.has(p.et), h = HITS[p.et] || 0;
      if (ab) o.ab += 1;
      if (h) { o.h += 1; o.tb += h; if (p.et === "home_run") o.hr += 1; }
      if (p.et === "walk" || p.et === "intent_walk") o.bb += 1;
      if (/^strikeout/.test(p.et)) o.k += 1;
      if (p.et === "hit_by_pitch") o.hbp += 1;
      if (SAC_FLY.has(p.et)) o.sf += 1;
      o.rbi += p.rbi || 0;
      if (p.br) o.brl += 1;
      if (p.ls != null) {
        o.bip += 1;
        evs += p.ls;
        if (p.ls >= 95) o.hard += 1;
        o.max = o.max == null ? p.ls : Math.max(o.max, p.ls);
      }
      if (p.la != null) {
        o.nla += 1;
        las += p.la;
        if (p.la >= 8 && p.la <= 32) o.sweet += 1;
      }
      if (ab) {
        if (p.xh != null) any = true;
        xs += p.xh != null ? p.xh : (h ? 1 : 0);
        xb += p.xh != null ? p.xtb : h;
      }
    });
    const on = o.ab + o.bb + o.hbp + o.sf;
    o.ev = o.bip ? evs / o.bip : null;
    o.la = o.nla ? las / o.nla : null;
    o.avg = o.ab ? o.h / o.ab : null;
    o.obp = on ? (o.h + o.bb + o.hbp) / on : null;
    o.slg = o.ab ? o.tb / o.ab : null;
    o.ops = o.obp != null && o.slg != null ? o.obp + o.slg : null;
    o.xba = any && o.ab ? xs / o.ab : null;
    o.xslg = any && o.ab ? xb / o.ab : null;
    return o;
  }
  /* What became of an at-bat, the renders' way: "Single (LF)". The
     fielder is the one the feed names; a home run it names none for is
     given the field it left over. */
  function fieldOf(p) {
    const f = FIELDER[String(p.loc == null ? "" : p.loc).trim()];
    if (f) return f;
    if (p.et !== "home_run" || p.x == null || p.y == null) return "";
    const a = Math.atan2(p.x - 125.42, 198.27 - p.y) * 180 / Math.PI;
    return a < -15 ? "LF" : a > 15 ? "RF" : "CF";
  }
  const result = (p) => `${p.ev || SHORT[p.et] || "—"}${fieldOf(p) ? ` (${fieldOf(p)})` : ""}`;
  //: Its colour: a home run gold, a hit green, a strikeout red, a walk quiet.
  const tone = (et) => (et === "home_run" ? "hr" : HITS[et] ? "h" : /^strikeout/.test(et) ? "k"
    : /walk|hit_by_pitch/.test(et) ? "bb" : "");

  /* ---------------- his season over his park ---------------- */
  /* The renders' head: his club's logo and name over its park, the season
     to pick, his face, his name with his position and number, and his
     season in five numbers. A season the play-by-play is still being read
     for says how far it has got, so it never passes for his whole year. */
  function hero(d, sport) {
    const S = state(), team = d.team || "", t = Q.h.team(sport, team);
    /* HIS ACTION PHOTO (MLB's own) in front of his headshot: it takes the
       headshot's place once it has loaded, and a man with none keeps his
       headshot (js/carrychart.js faceStep keeps which in the chart). */
    const act = d.action && !(S && S.act === false)
      ? `<span class="cc-act${S && S.act ? " on" : ""}"><img src="${esc(d.action)}" alt="" decoding="async"></span>` : "";
    const nick = t.nick || (typeof teamNameIn === "function" ? teamNameIn(sport, team) : "") || team;
    const loc = t.loc || (t.name && t.name !== nick && t.name.endsWith(nick) ? t.name.slice(0, -nick.length).trim() : "");
    const ink = Q.h.ink(sport, team);
    const art = team && typeof venuePhotoTag === "function" ? venuePhotoTag(sport, team, t) : "";
    const words = String(d.player || "").trim().split(/\s+/);
    const first = words.length > 1 ? words[0] : "", last = words.length > 1 ? words.slice(1).join(" ") : words[0];
    const tag = [d.position || "", d.jersey ? `#${d.jersey}` : ""].filter(Boolean);
    const year = Q.h.seasonName(sport, d.season);
    const pick = d.seasons.length > 1
      ? `<span class="mb-pick"><select data-season-pick aria-label="Season">${d.seasons.map((y) =>
        `<option value="${y}"${y === d.season ? " selected" : ""}>${esc(Q.h.seasonName(sport, y))} season</option>`).join("")}</select></span>`
      : `<span class="mb-pick one">${esc(year)} season</span>`;
    const L = line(plays(d.games));
    const tiles = [["Games", d.games.length], ["AVG", avg3(L.avg)], ["HR", L.hr], ["RBI", L.rbi], ["OPS", avg3(L.ops)]];
    const n = d.games.length, logged = Number(d.logged) || 0;
    const cover = logged > n
      ? `<p class="mb-cover">${n} of his ${logged} games this season are charted so far: the rest are read from MLB’s play-by-play a few hundred games a night, newest first.</p>` : "";
    return `<div class="cc-hero mb-hero"${ink ? ` style="--ta:${ink};--tb:${ink}"` : ""}>${art}
      <div class="mb-hero-in">
        <div class="mb-hero-top">${pick}</div>
        <div class="mb-hero-team"><span class="cc-hero-logo">${mark(sport, team, 60)}</span>
          <span class="cc-hero-name">${loc ? `<small>${esc(loc)}</small>` : ""}<b style="--nl:${Q.h.nameLen(nick)}">${esc(nick)}</b></span></div>
        <div class="mb-hero-face${act ? " has-act" : ""}">${act}${Q.h.face(d)}</div>
        <div class="mb-hero-who">${first ? `<small>${esc(first)}</small>` : ""}<b style="--nl:${Q.h.nameLen(last)}">${esc(last)}</b>${tag.length
          ? `<span>${tag.map(esc).join("  ")}</span>` : ""}</div>
        <div class="mb-hero-tiles">${tiles.map(([k, v]) => `<div class="mb-ht"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join("")}</div>
      </div></div>${cover}`;
  }

  /* ---------------- the park ---------------- */
  /* The Stats API's hit coordinates, home plate at (125.42, 198.27), y
     growing toward home, about 2.5 feet a unit; drawn top-down with home
     at the foot, 1.45 px a unit. The wall is the drawing's, not his
     park's: 330 feet down the lines, 375 in the gaps and 400 to centre,
     and the numbers on it say so. The grass with its mowing rings, the
     warning track, the infield, the chalk lit; every ball where it
     landed — a home run gold, a hit green, an out grey. */
  const HX = 200, HY = 336, K = 1.45, FT = K / 2.5;
  const fx = (x) => HX + (x - 125.42) * K;
  const fy = (y) => HY - (198.27 - y) * K;
  //: A point r out from the plate, `a` degrees off straightaway centre.
  const at = (r, a) => [HX + r * Math.sin(a * Math.PI / 180), HY - r * Math.cos(a * Math.PI / 180)];
  const xy = (p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`;
  //: The drawing's wall, in feet: 400 to centre, 375 in the gaps, 330 down the lines.
  const wallFt = (a) => { const u = (a / 45) * (a / 45); return 400 - 110 * u + 40 * u * u; };
  function arcPts(r, from, to) {
    const out = [];
    for (let a = from; a <= to + 0.001; a += 2.5) out.push(at(Math.min(typeof r === "function" ? r(a) : r, wallFt(a) * FT), a));
    return out;
  }
  const poly = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${xy(p)}`).join(" ");
  function parkSVG(d, g, sport) {
    const wall = arcPts((a) => wallFt(a) * FT, -45, 45);
    const track = arcPts((a) => (wallFt(a) - 14) * FT, -45, 45);
    let s = `<path class="mb-grass" d="M${HX} ${HY} ${poly(wall).replace(/^M/, "L")} Z"/>`;
    for (let r = 60, k = 0; r < 240; r += 22, k++) {
      if (k % 2) continue;
      const a0 = arcPts(r, -45, 45), a1 = arcPts(r + 22, -45, 45).reverse();
      s += `<path class="mb-mow" d="${poly(a0.concat(a1))} Z"/>`;
    }
    s += `<path class="mb-track" d="${poly(wall)} ${poly(track.slice().reverse()).replace(/^M/, "L")} Z"/>`;
    // The infield: the dirt to the grass's lip, the grass inside the
    // bases, the mound, the bags and the plate.
    const lip = arcPts(90, -45, 45);
    s += `<path class="mb-dirt" d="M${HX} ${HY} ${poly(lip).replace(/^M/, "L")} Z"/>`;
    const base = (deg) => at(52.2, deg), c = [HX, HY - 36.9];
    const shrink = (p, f) => [c[0] + (p[0] - c[0]) * f, c[1] + (p[1] - c[1]) * f];
    const sq = [[HX, HY], base(45), [HX, HY - 73.8], base(-45)];
    s += `<path class="mb-ingrass" d="${poly(sq.map((p) => shrink(p, 0.8)))} Z"/>
      <circle class="mb-dirt" cx="${HX}" cy="${(HY - 35.1).toFixed(1)}" r="5.4"/>
      <circle class="mb-dirt" cx="${HX}" cy="${HY}" r="8"/>`;
    const pole = (p) => `<line x1="${HX}" y1="${HY}" x2="${p[0].toFixed(1)}" y2="${p[1].toFixed(1)}"/>`;
    const chalk = pole(wall[0]) + pole(wall[wall.length - 1]);
    s += `<g class="mb-glow">${chalk}</g><g class="mb-chalk">${chalk}</g>
      <path class="mb-wall-glow" d="${poly(wall)}"/><path class="mb-wall" d="${poly(wall)}"/>`;
    [sq[1], sq[2], sq[3]].forEach((p) => {
      s += `<rect class="mb-bag" x="${(p[0] - 2.2).toFixed(1)}" y="${(p[1] - 2.2).toFixed(1)}" width="4.4" height="4.4" transform="rotate(45 ${xy(p)})"/>`;
    });
    s += `<path class="mb-bag" d="M${HX - 2.6} ${HY - 2.4} L${HX + 2.6} ${HY - 2.4} L${HX + 2.6} ${HY} L${HX} ${HY + 2.4} L${HX - 2.6} ${HY} Z"/>`;
    // The distances on the wall: its own, outside it.
    [-45, -22.5, 0, 22.5, 45].forEach((a) => {
      const ft = Math.round(wallFt(a) / 5) * 5, p = at((wallFt(a) + (Math.abs(a) === 45 ? 20 : 16)) * FT, a);
      s += `<text class="mb-wl" x="${p[0].toFixed(1)}" y="${(p[1] + 4).toFixed(1)}" text-anchor="middle">${ft}</text>`;
    });
    s += sideWords(d, g);
    // His season's balls, by where they went (the filter fades the rest);
    // in a game's drawing they sit faint under that game's own.
    const zone = { pull: "", center: "", oppo: "", "": "" };
    plays(d.games).forEach((p) => {
      if (p.x == null || p.y == null) return;
      const kind = p.et === "home_run" ? "hr" : HITS[p.et] ? "h" : "o";
      zone[p.dir in zone ? p.dir : ""] += `<circle class="mb-ball mb-dot ${kind}${g ? " faint" : ""}" cx="${fx(p.x).toFixed(1)}" cy="${fy(p.y).toFixed(1)}" r="${g ? 2.8 : kind === "hr" ? 4.4 : 3.6}"/>`;
    });
    s += Object.entries(zone).map(([z, marks]) => (marks ? `<g class="cc-carry" data-z="${z}">${marks}</g>` : "")).join("");
    if (g) s += (g.pas || []).map((p, i) => ballMark(p, i)).join("");
    const n = plays(d.games).filter((p) => p.x != null).length;
    const label = g ? `This game’s balls in play over his season’s ${n}. Every at-bat is listed above.`
      : `Where he hit it: ${n} balls in play this season.`;
    return `<svg class="cc-svg mb-svg mb-park-svg" viewBox="36 62 328 320" role="img" aria-label="${esc(label)}">${s}</svg>`;
  }
  //: One of the game's balls: its flight from the plate, lit, numbered as its at-bat is in the table.
  function ballMark(p, i) {
    if (p.x == null || p.y == null) return "";
    const x = fx(p.x), y = fy(p.y), kind = p.et === "home_run" ? "hr" : HITS[p.et] ? "h" : "o";
    const r = kind === "hr" ? 6 : 5, S = state(), on = S && S.sel === i ? " sel" : "";
    const c = `${x.toFixed(1)}`, cy = `${y.toFixed(1)}`;
    return `<g class="cc-carry" data-i="${i}" data-z="${p.dir || ""}">
      <line class="cc-hit" x1="${HX}" y1="${HY}" x2="${c}" y2="${cy}"/>
      ${kind === "o" ? "" : `<line class="mb-glow-arc ${kind}" x1="${HX}" y1="${HY}" x2="${c}" y2="${cy}"/>`}
      <line class="mb-arc ${kind}${on}" x1="${HX}" y1="${HY}" x2="${c}" y2="${cy}"/>
      ${kind === "o" ? "" : `<circle class="mb-halo ${kind}" cx="${c}" cy="${cy}" r="${r + 5}"/>`}
      <circle class="mb-ball cx-mark ${kind}${on}" cx="${c}" cy="${cy}" r="${r}"/>
      <text class="mb-num" x="${(x + r + 3).toFixed(1)}" y="${(y - r + 1).toFixed(1)}">${i + 1}</text></g>`;
  }
  /* Each third of the field's share of his balls, written in the foul
     ground beside it (the renders' "LF 38% Pulled"): by where they
     landed, 15° either side of straightaway centre. A hitter who bats
     from one side pulls to one field, and the words say which; a
     switch-hitter's are just the fields. A game's drawing names the
     fields and leaves the shares to the tiles beside it. */
  function sideWords(d, g) {
    const by = { L: 0, C: 0, R: 0 };
    plays(d.games).forEach((p) => {
      if (p.x == null || p.y == null) return;
      const a = Math.atan2(p.x - 125.42, 198.27 - p.y) * 180 / Math.PI;
      by[a < -15 ? "L" : a > 15 ? "R" : "C"] += 1;
    });
    const n = by.L + by.C + by.R, one = (d.sides && d.sides.length ? d.sides : [d.side]).length === 1;
    const lefty = (d.side || (d.sides || [])[0]) === "L";
    const word = (k) => (k === "C" ? "Up the middle" : !one ? (k === "L" ? "Left field" : "Right field")
      : (k === "L") === !lefty ? "Pulled" : "Opposite field");
    if (g || !n) {
      return `<text class="mb-fl" x="86" y="300" text-anchor="middle">LF</text><text class="mb-fl" x="314" y="300" text-anchor="middle">RF</text>`;
    }
    const col = (k, x, y) => `<text class="mb-fl" x="${x}" y="${y}" text-anchor="middle">${k === "L" ? "LF" : "RF"}</text>
      <text class="mb-fp" x="${x}" y="${y + 24}" text-anchor="middle">${pct(by[k] / n)}</text>
      <text class="mb-fw" x="${x}" y="${y + 40}" text-anchor="middle">${esc(word(k))}</text>`;
    return col("L", 86, 290) + col("R", 314, 290)
      + `<text class="mb-fp" x="${HX}" y="362" text-anchor="middle">${pct(by.C / n)}</text>
         <text class="mb-fw" x="${HX}" y="377" text-anchor="middle">${esc(word("C"))}</text>`;
  }
  function parkArt(d, sport) {
    const team = d.team || "";
    return team && typeof venuePhotoTag === "function" ? venuePhotoTag(sport, team, Q.h.team(sport, team)) : "";
  }
  const legend = () => `<div class="cc-legend mb-legend" aria-hidden="true"><span><i class="dt mb-hr"></i>Home run</span>
      <span><i class="dt c"></i>Hit</span><span><i class="dt mb-out"></i>Out</span></div>`;
  /* The render's Left | Middle | Right, for a hitter: where his balls in
     play went, read off where each landed and which side he stood on —
     tiles that filter the drawing (the frame's side filter), each with
     its count, its share and a bar. */
  const sprayZones = {
    label: "Where he hit it",
    list: [["pull", "Pull", "Pulled"], ["center", "Center", "Up the middle"], ["oppo", "Oppo", "Opposite field"]],
    of: (p) => p.dir || "",
    pool: (g) => (g.pas || []).filter((p) => p.x != null),
    noun: ["ball", "balls"],
    season: true,
  };
  function zoneTiles(d) {
    const by = { pull: 0, center: 0, oppo: 0 };
    plays(d.games).forEach((p) => { if (p.dir in by) by[p.dir] += 1; });
    const n = by.pull + by.center + by.oppo;
    if (!n) return "";
    return `<div class="cc-sides mb-zones">${sprayZones.list.map(([k, , name]) => {
      const share = by[k] / n;
      return `<button type="button" class="cc-sd mb-z ${k}" data-sd="${k}" data-side="${k}" aria-label="${esc(`${name}: ${by[k]} of ${n} balls in play, ${pct(share)}`)}">
        <span>${esc(name)}</span><b>${pct(share)}</b><small>${by[k]} ball${by[k] === 1 ? "" : "s"}</small>
        <i class="mb-zbar" aria-hidden="true"><i style="width:${(100 * share).toFixed(1)}%"></i></i></button>`;
    }).join("")}</div>`;
  }
  const INFO = '<button type="button" class="cc-info" data-info aria-expanded="false" aria-label="How it’s drawn">i</button>';
  /* THE HIT DISTRIBUTION CARD: the park over his club's own, the filter,
     the legend and the three thirds. A game's sets the drawing beside its
     tiles on a wide card (the render's By game), his season's draws the
     park across the card. */
  function hitCard(d, g, sport, note, ink) {
    const fig = `<div class="cc-stage mb-park">${parkArt(d, sport)}${parkSVG(d, g, sport)}${g ? '<div class="cc-tip" hidden></div>' : ""}</div>`;
    const side = zoneTiles(d) + legend();
    return `<section class="cc-card cc-dist mb-dist${g ? " mb-dist-g" : ""}"${ink ? ` style="--tm:${ink}"` : ""}>
      <header class="cc-card-h"><h3 class="cc-card-t">Hit distribution${note ? INFO : ""}</h3>${Q.h.seg(sprayZones)}</header>
      ${note ? `<div class="cc-pop" hidden>${note}</div>` : ""}
      ${g ? `<div class="mb-split">${fig}<div class="mb-split-s"><p class="mb-cap">His season’s balls in play, this game’s numbered as its at-bats are.</p>${side}</div></div>`
        : fig + side}</section>`;
  }

  /* ---------------- by game ---------------- */
  /* HIS RECENT GAMES (the renders' row): the last 10, 20 or 30, what he
     did over them, and each game a chip — the day, the opponent and his
     logo, his hits and at-bats, a home run in gold. */
  function recent(d, sport) {
    const S = state(), n = d.games.length;
    const opts = [10, 20, 30].filter((w) => w < n).map((w) => [String(w), `Last ${w}`]).concat([["all", `All ${n}`]]);
    const want = (S.opt && S.opt.win) || "10";
    const cur = opts.some(([v]) => v === want) ? want : opts[0][0];
    const win = cur === "all" ? n : Number(cur);
    const show = Math.max(win, S.gi + 1);
    const L = line(plays(d.games.slice(0, win)));
    const span = win === n ? `${Q.h.seasonName(sport, d.season)} season` : `Last ${win} games`;
    const rs = win === n && d.rs ? d.rs : { r: sumOf(d.games.slice(0, win), "r"), sb: sumOf(d.games.slice(0, win), "sb") };
    const ran = rs.r != null ? ` · ${rs.r} R · ${rs.sb} SB` : "";
    const chips = d.games.slice(0, show).map((x, i) => {
      const on = i === S.gi, G = x.line || line(x.pas || []), dt = when(x.date, { month: "short", day: "numeric" });
      return `<button type="button" role="tab" class="cc-chip mb-chip${on ? " on" : ""}" data-gi="${i}" aria-selected="${on}" aria-label="${esc(`${dt} ${x.home === false ? "at" : "vs"} ${x.opp}: ${G.h} for ${G.ab}${G.hr ? `, ${G.hr} home run${G.hr === 1 ? "" : "s"}` : ""}`)}">
        <span class="mb-chip-t"><small>${esc(dt)}</small><span>${x.home === false ? "@" : "vs"} ${esc(x.opp)}</span><b>${G.h}-${G.ab}</b>${G.hr ? `<em>${G.hr} HR</em>` : ""}</span>
        <span class="mb-chip-m" aria-hidden="true">${mark(sport, x.opp, 26)}</span></button>`;
    }).join("");
    return `<section class="mb-recent">
      <header class="mb-row-h"><h3 class="cc-card-t">Recent games</h3>${opts.length > 1 ? `<div class="cc-seg mb-win" role="group" aria-label="How many games">${opts.map(([v, w]) =>
        `<button type="button" data-opt="win" data-v="${v}"${v === cur ? ' class="on"' : ""} aria-pressed="${v === cur}">${esc(w)}</button>`).join("")}</div>` : ""}</header>
      <p class="mb-last"><span>${esc(span)}</span> <b>${L.h}-${L.ab}</b> · ${avg3(L.avg)} AVG · ${L.hr} HR · ${L.rbi} RBI${ran} · ${L.bb} BB · ${L.k} K · ${avg3(L.ops)} OPS</p>
      <div class="cc-car">
        <button type="button" class="cc-step" data-step="-1" aria-label="Newer game"${S.gi <= 0 ? " disabled" : ""}>‹</button>
        <div class="cc-games mb-chips" role="tablist" aria-label="Games">${chips}</div>
        <button type="button" class="cc-step" data-step="1" aria-label="Older game"${S.gi >= n - 1 ? " disabled" : ""}>›</button></div>
    </section>`;
  }
  /* THE GAME (the renders' card): the day and the opponent, the final
     with both clubs' logos, his numbers, and every at-bat. */
  /* His numbers in the game; his runs and stolen bases beside them once
     his game log has the game (MLB's own, by the game's id). */
  function gameTiles(g) {
    const L = line(g.pas || []), ran = g.r != null;
    const hr = tile("HR", L.hr), t = ran
      ? [tile("H–AB", `${L.h}-${L.ab}`), tile("R", g.r), hr, tile("RBI", L.rbi), tile("Total bases", L.tb),
         tile("SB", g.sb, g.cs ? `${g.cs} caught` : ""), tile("BB–K", `${L.bb}-${L.k}`), tile("SLG", avg3(L.slg))]
      : [tile("H–AB", `${L.h}-${L.ab}`), hr, tile("RBI", L.rbi), tile("Total bases", L.tb),
         tile("BB–K", `${L.bb}-${L.k}`), tile("SLG", avg3(L.slg))];
    if (L.hr) t[t.indexOf(hr)] = hr.replace('class="cc-tile"', 'class="cc-tile hot"');
    return `<div class="cc-tiles ${ran ? "cc-tiles-2" : "cc-tiles-6"}">${t.join("")}</div>`;
  }
  /* The game's place: the park, a doubleheader's second game, the series
     and the game of it in October. */
  function where(g) {
    return [g.venue ? `@ ${g.venue}` : "", g.dh ? `Game ${g.dh} of a doubleheader` : "",
            g.series ? `${g.series}${g.sgame ? `, Game ${g.sgame}` : ""}` : ""].filter(Boolean).join(" · ");
  }
  /* The game's head: the day, the opponent and where it was played, the
     result, and the button to MLB's own page of the game. */
  const scoreOf = (g) => (Array.isArray(g.score) && g.score.length === 2 && g.score.every((x) => x != null) ? g.score.map(Math.round) : null);
  const wonOf = (sc) => (sc ? (sc[0] > sc[1] ? "W" : sc[0] < sc[1] ? "L" : "T") : "");
  function gameHead(g, sport) {
    const sc = scoreOf(g), won = wonOf(sc);
    const o = Q.h.team(sport, g.opp);
    const oppName = o.name || (typeof teamNameIn === "function" ? teamNameIn(sport, g.opp) : "") || g.opp;
    const dt = when(g.date, { weekday: "short", month: "short", day: "numeric", year: "numeric" }), at = where(g);
    return `<header class="mb-game-h"><span class="mb-when"><b>${esc(dt)}</b> ${g.home === false ? "at" : "vs"} ${esc(oppName)}${at
        ? `<small class="mb-at">${esc(at)}</small>` : ""}</span><span class="mb-game-r">${sc
        ? `<em class="mb-res ${won.toLowerCase()}">${won} ${sc[0]}-${sc[1]}</em>` : ""}${g.id
        ? ext(GAMEDAY(g.id), `View game ${ARROW}`, "mb-btn mb-ext", "View the game on MLB.com") : ""}</span></header>`;
  }
  /* The final with both clubs' logos and, in the regular season, each
     club's record through the game as the league's schedule gives it. */
  function scoreBoard(g, sport) {
    const sc = scoreOf(g), won = wonOf(sc);
    if (!sc) return "";
    const rec = (r) => (r ? `<small class="mb-rec">${esc(r)}</small>` : "");
    return `<div class="mb-board">
        <div class="mb-side">${mark(sport, g.team, 44)}<span><b>${esc(g.team)}</b><em>${sc[0]}</em>${rec(g.rec)}</span></div>
        <div class="mb-fin"><small>Final</small><b class="${won.toLowerCase()}">${won}</b></div>
        <div class="mb-side r"><span><b>${esc(g.opp)}</b><em>${sc[1]}</em>${rec(g.orec)}</span>${mark(sport, g.opp, 44)}</div></div>`;
  }
  function gameCard(d, g, sport) {
    const S = state(), seq = !!(S && S.opt && S.opt.pbk), pas = g.pas || [];
    const any = pas.some((p) => (p.ps || []).length);
    return `<section class="cc-card mb-game">
      ${gameHead(g, sport)}
      ${scoreBoard(g, sport)}${gameTiles(g)}
      <div class="mb-sub-h"><h4 class="mb-sub">At bats <span class="cc-n">(${pas.length})</span></h4><div class="cc-tools">${Q.h.tools(pas, sprayFlags, SPRAY_FILTERS)}</div></div>
      ${atBats(g)}
      ${any ? `<div class="mb-foot"><button type="button" class="mb-btn" data-tog="pbk" aria-pressed="${seq}">${seq ? "Hide the pitches" : "View pitch breakdown"} <span aria-hidden="true">→</span></button></div>` : ""}
    </section>`;
  }
  /* EVERY AT-BAT AS THE RENDERS' TABLE: its number, the inning, the pitch
     it ended on and how fast, what it became and where, how hard and how
     far. A phone folds the pitch's speed under its name; a wide card
     gives it a column. The breakdown adds each at-bat's pitches in order,
     coloured by what came of each. */
  const AB_COLS = [{ h: "#", c: "cc-c-n", p: "16px", w: "24px" },
                   { h: "Inn", c: "cc-c-q", p: "30px", w: "44px" },
                   { h: "Pitch", c: "cc-c-m", p: "minmax(0,1fr)" },
                   { h: "Pitch", c: "cc-c-t mb-c-pt", w: "minmax(0,.9fr)" },
                   { h: "MPH", c: "mb-c-mph", w: "64px" },
                   { h: "Result", c: "mb-c-res", p: "minmax(0,1.25fr)", w: "minmax(0,1.4fr)" },
                   { h: "EV", c: "cc-c-v", p: "30px", w: "60px", r: 1 },
                   { h: "Dist", c: "cc-c-v", p: "44px", w: "64px", r: 1 }];
  function seqHTML(p) {
    const ps = p.ps || [];
    if (!ps.length) return "";
    return `<span class="mb-seq"><small>${esc(`${vsWho(p)} · ${ps.length} pitch${ps.length === 1 ? "" : "es"}`)}</small>${ps.map((x, j) => {
      const o = outcome(x[2]), v = x[1] == null ? "" : ` ${Math.round(x[1])}`;
      return `<em class="mb-pc ${o}" title="${esc(`${pitchName(x[0])}${v ? `,${v} mph` : ""}: ${OUTCOME[o]}`)}">${j + 1} ${esc(x[0] || "?")}${v}</em>`;
    }).join("")}</span>`;
  }
  function atBats(g) {
    const S = state(), seq = !!(S && S.opt && S.opt.pbk);
    return grid("ab", AB_COLS, (g.pas || []).map((p, i) => {
      const lp = lastPitch(p), name = lp ? pitchName(lp[0]) : "—", v = lp && lp[1] != null ? Math.round(lp[1]) : null;
      return {
        i, f: sprayFlags(p),
        said: [`${nth(p.inn)} inning`, vsWho(p), lp ? `${name}${v == null ? "" : ` at ${v} mph`}` : "", result(p), ballWords(p),
               p.br ? "a barrel" : "", p.rbi ? `${p.rbi} RBI` : ""].filter(Boolean).join(", "),
        cells: [`${i + 1}`, esc(nth(p.inn)), two(name, v == null ? "" : `${v} mph`), esc(name), esc(v == null ? "—" : v),
                `<b class="mb-rs ${tone(p.et)}">${esc(result(p))}</b>${p.rbi ? `<small>${p.rbi} RBI</small>` : ""}${p.br
                  ? '<small class="mb-brl">Barrel</small>' : ""}`,
                esc(p.ls == null ? "—" : Math.round(p.ls)), esc(p.d == null ? "—" : `${Math.round(p.d)} ft`)],
        more: seq ? seqHTML(p) : "",
      };
    }));
  }
  /* THE GAME'S SUMMARY (the renders' row under the table): the pitches he
     saw and how many were fastballs, how hard he hit the ball and the
     hardest, and the balls at 95 mph or more. */
  function summaryCard(g) {
    const pas = g.pas || [], seen = [].concat(...pas.map((p) => p.ps || []));
    const n = seen.length || pas.reduce((a, p) => a + (p.np || 0), 0);
    const fast = seen.length ? seen.filter((x) => GROUP[x[0]] === "F").length / seen.length : null;
    const L = line(pas);
    const t = [tile("Pitches seen", n || "—"), tile("Fastball %", pct(fast)), tile("Avg exit velo", L.ev == null ? "—" : num1(L.ev), "mph"),
               tile("Hardest hit", L.max == null ? "—" : num1(L.max), "mph"), tile("Hard hits", L.hard, "95+ mph"),
               tile("Barrels", L.brl, "MLB’s rule")];
    return `<section class="cc-card cc-stats mb-sum"><h3 class="cc-card-t">Game summary</h3><div class="cc-tiles cc-tiles-6">${t.join("")}</div></section>`;
  }

  /* ---------------- his season, against any pitch ---------------- */
  /* THE SEASON'S NUMBERS (the renders' SEASON STATS), against every pitch
     or one kind (the pitch the at-bat ended on: the one he put in play,
     struck out or walked on), or one hand. */
  const VS = [["", "All pitches"], ["F", "Fastballs"], ["B", "Breaking balls"], ["O", "Offspeed"],
              ["R", "vs right-handers"], ["L", "vs left-handers"]];
  const inVs = (p, k) => !k || (k === "R" || k === "L" ? p.ph === k : GROUP[(lastPitch(p) || [""])[0]] === k);
  function seasonStats(d, sport) {
    const S = state(), all = plays(d.games);
    const opts = VS.filter(([v]) => !v || all.some((p) => inVs(p, v)));
    const k = opts.some(([v]) => v === ((S && S.opt && S.opt.vs) || "")) ? ((S && S.opt && S.opt.vs) || "") : "";
    const L = line(all.filter((p) => inVs(p, k)));
    const sel = opts.length > 1 ? `<span class="cc-filt"><select data-opt="vs" aria-label="Against which pitches">${opts.map(([v, w]) =>
      `<option value="${v}"${v === k ? " selected" : ""}>${esc(w)}</option>`).join("")}</select></span>` : "";
    // Our expected average and slugging ride beside his own (engine/mlb/xstats).
    // His runs and stolen bases are the season's own (his game log's), so
    // they stand only over every pitch, and only once every game has them.
    const rs = !k && d.rs ? d.rs : null;
    const hits = tile("H–AB", `${L.h}-${L.ab}`, `${avg3(L.avg)} AVG${L.xba == null ? "" : ` · xBA ${avg3(L.xba)}`}`);
    const hr = tile("HR", L.hr, L.pa ? `${(100 * L.hr / L.pa).toFixed(1)}% of PA` : ""), rbi = tile("RBI", L.rbi, `${avg3(L.obp)} OBP`);
    const tb = tile("Total bases", L.tb, `${avg3(L.slg)} SLG${L.xslg == null ? "" : ` · xSLG ${avg3(L.xslg)}`}`);
    const big = rs ? [hits, tile("Runs", rs.r), hr, rbi, tile("Stolen bases", rs.sb, rs.cs ? `${rs.cs} caught` : ""), tb]
      : [hits, hr, rbi, tb];
    // A barrel is MLB's own rule on each ball he put in play.
    const small = [tile("OPS", avg3(L.ops)), tile("BB–K", `${L.bb}-${L.k}`), tile("Exit velocity", L.ev == null ? "—" : num1(L.ev), "mph · average"),
                   tile("Launch angle", L.la == null ? "—" : `${num1(L.la)}°`, "average"),
                   tile("Hard hit", pct(L.bip ? L.hard / L.bip : null), "95+ mph"),
                   tile("Barrel %", pct(L.bip ? L.brl / L.bip : null), `${L.brl} barrel${L.brl === 1 ? "" : "s"}`),
                   tile("Sweet spot", pct(L.nla ? L.sweet / L.nla : null), "8–32°")];
    const vs = VS.find(([v]) => v === k);
    const one = { F: "a fastball", B: "a breaking ball", O: "an offspeed pitch" };
    return `<section class="cc-card cc-stats mb-stats"><header class="cc-card-h"><h3 class="cc-card-t">Season stats (${esc(Q.h.seasonName(sport, d.season))})</h3>${sel}</header>
      <div class="cc-tiles cc-tiles-2 mb-big${rs ? " mb-big6" : ""}">${big.join("")}</div>
      <div class="cc-tiles cc-tiles-7">${small.join("")}</div>
      ${k ? "" : mlbOwn(d)}
      ${k ? `<p class="mb-cap">${esc(one[k] ? `His ${L.pa} plate appearances that ended on ${one[k]}: the pitch he put in play, struck out or walked on.`
        : `His ${L.pa} plate appearances ${vs[1]}.`)}</p>` : ""}
    </section>`;
  }
  /* HOMER IN HOW MANY OF THE 30 PARKS (engine/mlb/fences): each of his
     home runs, and each ball that was not one but would have been
     somewhere, laid over every park's fence. An estimate, and it says so. */
  function fencesCard(d) {
    const f = d.fences, hr = (f && f.hr) || [], near = (f && f.near) || [];
    if (!hr.length && !near.length) return "";
    const P = f.parks || 30, half = Math.floor(P / 2);
    const row = (x, said) => `<div class="cc-brow">
        <span class="cc-bn">${esc([x.date ? when(x.date, { month: "short", day: "numeric" }) : "", x.opp ? `vs ${x.opp}` : ""].filter(Boolean).join(" · "))}</span>
        <span class="cc-bt"><i style="width:${(100 * x.n / P).toFixed(1)}%"></i></span>
        <b class="cc-bv">${x.n}<small>of ${P}</small></b>
        <span class="cc-bx">${esc([said, x.d == null ? "" : `${Math.round(x.d)} ft`, x.ls == null ? "" : `${Math.round(x.ls)} mph`,
                                  (x.held_by || []).length ? `held in ${x.held_by.join(", ")}` : "",
                                  (x.out_of || []).length ? `out only in ${x.out_of.join(", ")}` : ""].filter(Boolean).join(" · "))}</span></div>`;
    // The doubters first: a no-doubter says less than a fly ball only a few parks would not have held.
    const shown = hr.slice().sort((a, b) => a.n - b.n);
    const tiles = [tile("Home runs", hr.length), tile("No-doubters", f.no_doubt || 0, `out of all ${P}`),
                   tile("Doubters", f.doubters || 0, `out of ${half} or fewer`),
                   tile("Gone somewhere", f.near_n || 0, "not a homer here")];
    return `<section class="cc-card mb-fences"><header class="cc-card-h"><h3 class="cc-card-t">A homer in how many of the ${P} parks?</h3><span class="cc-pill mute">Estimate</span></header>
      <div class="cc-tiles cc-tiles-2">${tiles.join("")}</div>
      ${shown.length ? `<h4 class="cc-bh">His home runs</h4><div class="cc-bars">${shown.slice(0, 15).map((x) => row(x, "")).join("")}</div>${shown.length > 15 ? `<p class="mb-cap">And ${shown.length - 15} more out of more parks.</p>` : ""}` : ""}
      ${near.length ? `<h4 class="cc-bh">Not a homer, but gone somewhere</h4><div class="cc-bars">${near.map((x) => row(x, x.ev || "")).join("")}</div>` : ""}
      <p class="mb-cap">An estimate from the fences alone: each ball’s distance (MLB’s own feed) against each park’s fence at the angle it was hit, the distances down the lines and to centre with a straight fence between, plus the wall’s height. No air, altitude or wind, and real outfields curve where these do not. Nothing on the board reads it.</p>
    </section>`;
  }
  /* MLB'S OWN NUMBERS BESIDE OURS (Baseball Savant): its expected average
     and slugging and its barrel rate, as of the day the box last read
     them, over the games Savant's season board counts. */
  function mlbOwn(d) {
    const o = d.savant;
    if (!o || (o.xba == null && o.xslg == null && o.brl_pct == null)) return "";
    const at = o.at ? when(o.at, { month: "short", day: "numeric" }) : "";
    const bits = [o.xba != null ? `<b>${avg3(o.xba)}</b> xBA` : "", o.xslg != null ? `<b>${avg3(o.xslg)}</b> xSLG` : "",
                  o.brl_pct != null ? `<b>${(100 * o.brl_pct).toFixed(1)}%</b> barrels${o.bbe ? ` of ${o.bbe} balls` : ""}` : ""].filter(Boolean);
    return `<p class="mb-own"><span>MLB’s own · Baseball Savant${at ? ` · as of ${esc(at)}` : ""}</span>${bits.join(" · ")}</p>`;
  }

  /* ---------------- the table's tools, the splits ---------------- */
  const sprayFlags = (p) => [HITS[p.et] ? "h" : "", p.et === "home_run" ? "hr" : "", p.x != null ? "bip" : "",
                             p.ls != null && p.ls >= 95 ? "hard" : "", /strikeout/.test(p.et) ? "k" : "",
                             /walk|hit_by_pitch/.test(p.et) ? "bb" : "", p.rbi ? "rbi" : ""].filter(Boolean).join(" ");
  const SPRAY_FILTERS = [["", "Every plate appearance"], ["h", "Hits"], ["hr", "Home runs"], ["bip", "Balls in play"],
                         ["hard", "Hard hit"], ["k", "Strikeouts"], ["bb", "Walks"], ["rbi", "Drove in a run"]];
  const sprayCsv = (g) => [["#", "Inning", "Pitcher", "Throws", "Pitch", "Pitch speed (mph)", "Result", "Event",
                            "Exit velocity (mph)", "Launch angle", "Distance (ft)", "Batted ball", "Direction", "RBI",
                            "Pitches", "Every pitch", "xBA", "Barrel"]]
    .concat((g.pas || []).map((p, i) => {
      const lp = lastPitch(p);
      return [i + 1, nth(p.inn), p.p, p.ph, lp ? pitchName(lp[0]) : "", lp && lp[1] != null ? lp[1] : "", result(p), p.ev,
              p.ls == null ? "" : p.ls, p.la == null ? "" : p.la, p.d == null ? "" : p.d, TYPE[p.tr] || "", DIR[p.dir] || "",
              p.rbi || 0, p.np == null ? "" : p.np,
              (p.ps || []).map((x) => `${x[0] || "?"}${x[1] == null ? "" : ` ${x[1]}`} ${OUTCOME[outcome(x[2])]}`).join("; "),
              p.xh == null ? "" : p.xh, p.br ? "yes" : ""];
    }));
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
      out.push(tableHTML("Against right- and left-handers", ["Pitcher", "PA", "H", "HR", "BB", "K", "AVG", "OPS"],
        d.by_hand.map((x) => [x.name, x.pa, x.h, x.hr, x.bb, x.k, avg3(x.avg), avg3(x.ops)])));
    }
    return out.join("");
  }
  /* THE OTHER VIEWS: his balls in play by how he hit them and where they
     went, and the pitches he saw — each kind, how often he missed it when
     he swung, and what he did when an at-bat ended on it — with his
     plate appearances against each hand under them. */
  const SPRAY_VIEWS = [["type", "Batted ball"], ["dir", "Direction"], ["pitch", "Pitch"]];
  const SPRAY_TITLE = { type: "Balls in play by how he hit them", dir: "Balls in play by direction",
                        pitch: "The pitches he saw" };
  function pitchesSeen(d) {
    const by = {};
    plays(d.games).forEach((p) => (p.ps || []).forEach((x, j, all) => {
      const t = x[0] || "?", o = by[t] = by[t] || { seen: 0, sw: 0, wh: 0, pa: 0, ab: 0, h: 0, hr: 0 };
      const oc = outcome(x[2]);
      o.seen += 1;
      if (oc === "w") o.wh += 1;
      if (oc === "w" || oc === "f" || oc === "x") o.sw += 1;
      if (j === all.length - 1) {
        o.pa += 1;
        if (!NOT_AB.has(p.et)) o.ab += 1;
        if (HITS[p.et]) o.h += 1;
        if (p.et === "home_run") o.hr += 1;
      }
    }));
    return Object.entries(by).sort((a, b) => b[1].seen - a[1].seen);
  }
  function sprayBars(d, view) {
    if (view === "pitch") {
      const seen = bars(pitchesSeen(d).map(([t, o]) => [pitchName(t), o.seen,
        `${o.sw ? pct(o.wh / o.sw) : "—"} of swings missed · ${o.pa} at-bat${o.pa === 1 ? "" : "s"} ended on it · ${o.ab ? avg3(o.h / o.ab) : "—"} AVG${o.hr ? ` · ${o.hr} HR` : ""}`]));
      const hand = bars((d.by_hand || []).map((x) => [x.name, x.pa, `${x.h} H · ${x.hr} HR · ${x.bb} BB · ${x.k} K · ${avg3(x.avg)} AVG · ${avg3(x.ops)} OPS`]));
      return (seen ? `<h4 class="cc-bh">Every pitch he saw, by kind</h4>${seen}` : "")
        + (hand ? `<h4 class="cc-bh">Against right- and left-handers</h4>${hand}` : "");
    }
    return bars(((view === "type" ? d.by_type : d.by_dir) || []).map((x) => [x.name, x.bip || x.n,
      `${x.h} hit${x.h === 1 ? "" : "s"} · ${x.hr} HR · ${pct(x.n ? x.h / x.n : null)} hit rate${x.xba == null ? "" : ` · xBA ${avg3(x.xba)}`}`]));
  }
  const SPLITS = "Every split · batted ball, direction, pitcher's hand";
  function viewsOf(d) {
    return SPRAY_VIEWS.filter(([k]) => (k === "pitch" ? (d.by_hand || []).length || plays(d.games).some((p) => (p.ps || []).length)
      : (d[k === "type" ? "by_type" : "by_dir"] || []).length));
  }
  /* THE PAGE: the hero and the tabs over each view's cards. */
  function page(c) {
    const { d, g, sport, view, tabs, note, ink } = c;
    const top = hero(d, sport) + tabs;
    if (view === "game" && g) return top + recent(d, sport) + gameCard(d, g, sport) + summaryCard(g) + hitCard(d, g, sport, note, ink);
    const splits = Q.h.splits(SPLITS, sprayTables(d));
    if (view === "season") return top + hitCard(d, null, sport, note, ink) + seasonStats(d, sport) + fencesCard(d) + splits;
    return `${top}<section class="cc-card cc-dist"><header class="cc-card-h"><h3 class="cc-card-t">${esc(SPRAY_TITLE[view] || "")}</h3></header>${sprayBars(d, view)}</section>`
      + seasonStats(d, sport) + splits;
  }

  Q.draw("spray", {
    one: "plate appearance", splitsTitle: SPLITS,
    items: (g) => g.pas || [],
    count: (L) => `${L.pa} plate appearances`,
    chip: (g) => `${g.line.h}-${g.line.ab}${g.line.hr ? `, ${g.line.hr} HR` : ""}`,
    zones: sprayZones,
    page,
    // Each part on its own, as the page draws it (and its tests read it).
    game: (g, d) => parkSVG(d || { games: [g] }, g, "mlb"),
    season: (d) => parkSVG(d, null, "mlb"),
    legend: () => legend(),
    gameSide: (g) => gameTiles(g),
    seasonSide: (d) => seasonStats(d, d.sport || "mlb"),
    list: (g) => atBats(g),
    flags: sprayFlags, filters: SPRAY_FILTERS, csv: sprayCsv,
    views: (d) => viewsOf(d),
    barTitle: (v) => SPRAY_TITLE[v],
    bars: (d, v) => sprayBars(d, v),
    splits: (d) => sprayTables(d),
    note: (d) => `<p class="cc-note">Each dot is where a ball he put in play landed, from MLB’s Stats API play-by-play (its hit coordinates, about two and a half feet a unit); exit velocity, launch angle and distance are the league’s own numbers as that feed carries them. The wall is the drawing’s, not his park’s: 330 feet down the lines, 375 in the gaps and 400 to centre. Pulled, up the middle and opposite field are read off where the ball landed and which side of the plate he stood on (within 15° of straightaway centre is up the middle). The pitch beside each at-bat is the one it ended on — the one he put in play, struck out or walked on — and its speed out of the hand; the breakdown is every pitch of it, in order. On base is hits, walks and hit-by-pitches over at-bats, walks, hit-by-pitches and sacrifice flies; OPS is that plus slugging. Hard hit is 95 mph or harder; the sweet spot is a launch angle of 8 to 32 degrees. A walk, a hit by pitch or a strikeout has no ball in play: listed, not drawn. A barrel is MLB’s own rule on MLB’s own numbers: a ball hit 98 mph or harder at 26 to 30 degrees, the window widening with every mph past that until at 116 mph it runs from 8 to 50; the barrel rate is barrels over balls in play. Runs and stolen bases are his own game log’s, game by game; the season’s are shown only when every game on the chart has them. A club’s record is the one through that game, from MLB’s schedule, and shown only where our own count of the season’s finals agrees with it. MLB’s own expected average, slugging and barrel rate are Baseball Savant’s, as of the day shown. The game opens on MLB.com.${xNote(d)}</p>`,
    // The page's own arithmetic, for its tests.
    _t: { line, result, nth, wallFt, inVs, pitchesSeen, where, sumOf, gameTiles, gameHead, scoreBoard, mlbOwn,
          fencesCard, GAMEDAY },
    tip: (p) => {
      const lp = lastPitch(p);
      return `<b class="${band(p.et)}">${esc(result(p))}</b>${p.rbi ? ` · ${p.rbi} RBI` : ""}
      <span>${esc([`${nth(p.inn)} inning`, `off ${p.p || "?"}${p.ph ? ` (${p.ph})` : ""}`,
                   lp ? `${pitchName(lp[0])}${lp[1] == null ? "" : ` ${Math.round(lp[1])} mph`}` : "", ballWords(p),
                   p.xh != null ? `xBA ${avg3(p.xh)}` : "",
                   p.pk != null && (p.pk || p.et === "home_run") ? `out in ${p.pk} of 30 parks (estimate)` : ""].filter(Boolean).join(" · "))}</span>`;
    },
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
