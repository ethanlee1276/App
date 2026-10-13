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

  let S = null;            // {sport, player, data, view, gi, sel}
  let _seq = 0;

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

  function svgWrap(inner, g, sport, n) {
    const what = g ? `${n} carries ${gameName(g, sport)}` : `${n} carries this season`;
    return `<svg class="cc-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Carry chart: ${what}. Each carry is listed below.`)}">${inner}</svg>`;
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

  function render() {
    const ov = document.getElementById("cc-overlay");
    if (!ov || !S) return;
    const d = S.data;
    const box = ov.querySelector(".cc-body");
    if (!d || !d.games || !d.games.length) {
      box.innerHTML = `<div class="cc-empty">No carries on file for ${esc(S.player)}${S.sport === "cfb" ? " in the college play-by-play" : ""}.</div>`;
      return;
    }
    const sport = d.sport;
    const head = `<header class="cc-head">
        <span class="cc-face">${d.face ? `<img src="${esc(d.face)}" alt="" loading="lazy" decoding="async">` : ""}</span>
        <div class="cc-who">
          <span class="cc-eyebrow">Carry chart</span>
          <h2 class="cc-name">${esc(d.player)}</h2>
          <span class="cc-sub">${[d.jersey ? `#${esc(d.jersey)}` : "", esc(d.position || ""), d.team
            ? `${teamMarkIn(sport, d.team, 16)} ${esc(teamNameIn(sport, d.team))}` : ""].filter(Boolean).join(" · ")}</span>
        </div>
        ${d.seasons.length > 1 ? `<div class="cc-seasons" role="group" aria-label="Season">${d.seasons.map((y) =>
          `<button type="button" class="cc-chip${y === d.season ? " on" : ""}" data-season="${y}" aria-pressed="${y === d.season}">${y}</button>`).join("")}</div>` : ""}
      </header>
      <div class="cc-tabs" role="tablist">
        <button type="button" role="tab" class="cc-tab${S.view === "game" ? " on" : ""}" data-view="game" aria-selected="${S.view === "game"}">By game</button>
        <button type="button" role="tab" class="cc-tab${S.view === "season" ? " on" : ""}" data-view="season" aria-selected="${S.view === "season"}">${d.season} · where he runs</button>
      </div>`;
    let main;
    if (S.view === "season") {
      const any = d.games.some((g) => g.carries.some((c) => !c.h)) && d.holes;
      main = `<div class="cc-title">${esc(`${d.season} season · ${d.season_line.n} carries in ${d.games.length} game${d.games.length === 1 ? "" : "s"}`)}</div>
        <div class="cc-stage">${seasonChart(d)}</div>
        ${legendHTML(sport, any)}
        ${tilesFor(d.season_line, (d.ngs || {}).ryoe)}
        <div class="cc-tiles cc-tiles-2">${tile("Success", pct(d.season_line.success))}${tile("Stuffed (0 or less)", pct(d.season_line.stuffed))}${tile("10+ yd runs", d.season_line.explosive)}${tile("Long", d.season_line.long == null ? "—" : Math.round(d.season_line.long))}</div>
        ${ngsLine(d)}${seasonTables(d)}`;
    } else {
      const g = d.games[Math.min(S.gi, d.games.length - 1)];
      const any = d.holes && g.carries.some((c) => !c.h);
      main = `<div class="cc-games" role="tablist" aria-label="Games">${d.games.map((x, i) =>
          `<button type="button" role="tab" class="cc-chip${i === S.gi ? " on" : ""}" data-gi="${i}" aria-selected="${i === S.gi}">${esc(chipLabel(x, sport))}<small>${x.line.n}-${Math.round(x.line.yds)}</small></button>`).join("")}</div>
        <div class="cc-title">${esc(gameTitle(g, sport, d.season))}</div>
        <div class="cc-stage">${gameChart(g, sport, d.holes)}<div class="cc-tip" hidden></div></div>
        ${legendHTML(sport, any)}
        ${tilesFor(g.line, g.ryoe)}
        ${listHTML(g, sport)}`;
    }
    box.innerHTML = head + main + noteHTML(d);
    const chip = box.querySelector(".cc-games .cc-chip.on");
    if (chip && chip.scrollIntoView) chip.scrollIntoView({ block: "nearest", inline: "center" });
  }

  /* ---------------- selection and the tip ---------------- */
  function select(i) {
    const ov = document.getElementById("cc-overlay");
    if (!ov || !S) return;
    S.sel = S.sel === i ? -1 : i;
    ov.querySelectorAll(".cc-carry").forEach((g) => {
      const on = +g.dataset.i === S.sel;
      const p = g.querySelector(".cc-run");
      if (p) p.classList.toggle("sel", on);
      g.classList.toggle("dim", S.sel >= 0 && !on);
    });
    ov.querySelectorAll(".cc-row").forEach((r) => r.classList.toggle("sel", +r.dataset.i === S.sel));
    tip(S.sel);
  }
  function tip(i) {
    const ov = document.getElementById("cc-overlay");
    const el = ov && ov.querySelector(".cc-tip");
    if (!el) return;
    const d = S.data, g = d && d.games[S.gi];
    const c = g && g.carries[i];
    if (!c || S.view !== "game") { el.hidden = true; return; }
    el.innerHTML = `<b class="${c.band}">${signed(c.y)} yds</b>${c.td ? " · TD" : ""}${c.sc ? " · scramble" : ""}
      <span>${esc([qLabel(c), downDist(c), spot(c, g), c.h ? HOLE_NAME[c.h] : ""].filter(Boolean).join(" · "))}</span>`;
    el.hidden = false;
  }

  /* ---------------- loading ---------------- */
  async function load(season) {
    const seq = ++_seq;
    const q = `/api/players/carries?sport=${encodeURIComponent(S.sport)}&player=${encodeURIComponent(S.player)}${season ? `&season=${season}` : ""}`;
    let data = null;
    try {
      const r = await fetch(q);
      if (r.ok) data = await r.json();
    } catch (e) { data = null; }
    if (seq !== _seq || !S) return;
    if (data === null) {
      const box = document.querySelector("#cc-overlay .cc-body");
      if (box) box.innerHTML = `<div class="cc-empty">The carry chart didn’t load. Try again in a moment.</div>`;
      return;
    }
    S.data = data;
    S.gi = 0;
    S.sel = -1;
    render();
  }

  function close() {
    const ov = document.getElementById("cc-overlay");
    if (!ov) return;
    ov.classList.remove("open");
    ov.innerHTML = "";
    S = null;
    _seq++;
    if (typeof lockScroll === "function") lockScroll(false);
    document.removeEventListener("keydown", onKey);
  }
  function onKey(e) { if (e.key === "Escape") close(); }

  function open(player, sport) {
    if (!player) return;
    let ov = document.getElementById("cc-overlay");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "cc-overlay";
      document.body.appendChild(ov);
      ov.addEventListener("click", (e) => {
        if (e.target === ov || e.target.closest(".cc-x")) return close();
        const s = e.target.closest("[data-season]");
        if (s && S) return load(+s.dataset.season);
        const v = e.target.closest("[data-view]");
        if (v && S) { S.view = v.dataset.view; S.sel = -1; return render(); }
        const gi = e.target.closest("[data-gi]");
        if (gi && S) { S.gi = +gi.dataset.gi; S.sel = -1; return render(); }
        const row = e.target.closest(".cc-row, .cc-carry");
        if (row && S && S.view === "game") return select(+row.dataset.i);
      });
      ov.addEventListener("pointerover", (e) => {
        const g = e.target.closest && e.target.closest(".cc-carry");
        if (g && S && S.sel < 0 && e.pointerType === "mouse") tip(+g.dataset.i);
      });
      ov.addEventListener("pointerout", (e) => {
        const g = e.target.closest && e.target.closest(".cc-carry");
        if (g && S && S.sel < 0 && e.pointerType === "mouse") tip(-1);
      });
    }
    S = { sport: String(sport || "nfl").toLowerCase(), player, data: null, view: "game", gi: 0, sel: -1 };
    ov.innerHTML = `<div class="cc" role="dialog" aria-modal="true" aria-label="${esc(`Carry chart — ${player}`)}">
      <button class="cc-x" type="button" aria-label="Close">×</button>
      <div class="cc-body"><div class="cc-empty">Loading ${esc(player)}’s carries…</div></div></div>`;
    ov.classList.add("open");
    if (typeof lockScroll === "function") lockScroll(true);
    document.addEventListener("keydown", onKey);
    const x = ov.querySelector(".cc-x");
    if (x) x.focus({ preventScroll: true });
    load(null);
  }

  window.QBCarry = { open, close, _t: { proj, runPoints, yMaxFor, fan, chipLabel, gameTitle, spot, downDist,
                                         gameChart, seasonChart, listHTML, noteHTML, tilesFor } };
})();
