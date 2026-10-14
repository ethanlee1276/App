/* Qellys Book — a fighter's fight history (js/chart-ufc.js).
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done, then make sure they are all routed correctly like nfl." Loaded by
   js/carrychart.js the first time a fight history is drawn, in its frame
   (the fights row, the By fight | career tabs, the numbers beside the
   drawing, the long tail folded).

   THE FIGHT HISTORY (kind "fights", engine/ufc/history.chart): every
   bout on his record that ESPN has, newest first — who, won or lost, how
   it ended, the round and the time in it. By fight draws the fight's
   clock (the rounds it was scheduled for, filled to where it ended) and
   both men's numbers side by side; the career view draws every fight's
   length on one clock, so how his fights end — early, late or on the
   cards — reads at a glance.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, state } = Q.h;
  const sel = (i) => { const S = state(); return S && S.sel === i ? " sel" : ""; };

  /* ---------------- words ---------------- */
  const RES = { W: "Won", L: "Lost", D: "Draw or no contest" };
  const CLS = { W: "gain", L: "loss", D: "short" };
  const METHOD = { "KO/TKO": "KO/TKO", SUB: "Submission", DEC: "Decision" };
  const SHORT = { "KO/TKO": "KO", SUB: "SUB", DEC: "DEC" };
  const clock = (s) => (s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
  const ended = (g) => (g.method === "DEC" ? `Decision after ${g.rounds}` : g.method
    ? `${METHOD[g.method] || g.method}${g.rnd ? ` · R${g.rnd} ${g.clock || ""}` : ""}` : "how it ended is not on file");
  const day = (iso) => {
    const t = iso ? new Date(iso + "T12:00:00") : null;
    return t && !isNaN(t) ? t.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
  };
  const record = (L) => `${L.w}-${L.l}${L.d ? `-${L.d}` : ""}`;
  const of = (a, b) => (a == null ? "—" : b != null ? `${a} of ${b}` : `${a}`);

  /* ---------------- the fight's clock ---------------- */
  const W = 420, X0 = 12, X1 = 408, RS = 300;
  function fightClock(g) {
    const rounds = g.rounds || 3, total = rounds * RS, span = X1 - X0;
    const x = (s) => X0 + Math.min(1, Math.max(0, s / total)) * span;
    let s = `<rect class="uf-track" x="${X0}" y="26" width="${span}" height="22" rx="6"/>`;
    s += `<rect class="uf-fill ${CLS[g.result] || "short"}" x="${X0}" y="26" width="${(x(g.secs || 0) - X0).toFixed(1)}" height="22" rx="6"/>`;
    for (let r = 1; r <= rounds; r++) {
      const a = x((r - 1) * RS), b = x(r * RS);
      if (r > 1) s += `<line class="uf-tick" x1="${a.toFixed(1)}" x2="${a.toFixed(1)}" y1="22" y2="52"/>`;
      s += `<text class="uf-r" x="${((a + b) / 2).toFixed(1)}" y="16" text-anchor="middle">R${r}</text>`;
    }
    const ex = x(g.secs || 0);
    s += `<circle class="uf-end ${CLS[g.result] || "short"}" cx="${ex.toFixed(1)}" cy="37" r="7"/>`;
    const anchor = ex > W - 120 ? "end" : ex < 120 ? "start" : "middle";
    s += `<text class="uf-endl" x="${ex.toFixed(1)}" y="72" text-anchor="${anchor}">${esc(`${RES[g.result] || ""} · ${ended(g)}`)}</text>`;
    return s;
  }
  /* Both men's numbers, his to the left of the middle and his
     opponent's to the right, each row's longer bar the full half. */
  function statRows(g, y0) {
    let s = "", y = y0;
    const mid = W / 2, half = 168;
    (g.stats || []).forEach((st, i) => {
      const top = Math.max(1, st.me || 0, st.opp || 0);
      const a = ((st.me || 0) / top) * half, b = ((st.opp || 0) / top) * half;
      s += `<g class="cc-carry" data-i="${i}"><rect class="uf-hit" x="0" y="${y - 16}" width="${W}" height="44"/>
        <text class="uf-sn" x="${mid}" y="${y - 3}" text-anchor="middle">${esc(st.name)}</text>
        <rect class="uf-bar me cx-mark${sel(i)}" x="${(mid - 6 - a).toFixed(1)}" y="${y + 3}" width="${a.toFixed(1)}" height="14" rx="3"/>
        <rect class="uf-bar opp" x="${mid + 6}" y="${y + 3}" width="${b.toFixed(1)}" height="14" rx="3"/>
        <text class="uf-v" x="${(mid - 12 - a).toFixed(1)}" y="${y + 14}" text-anchor="end">${esc(st.me == null ? "—" : String(st.me))}</text>
        <text class="uf-v" x="${(mid + 12 + b).toFixed(1)}" y="${y + 14}">${esc(st.opp == null ? "—" : String(st.opp))}</text></g>`;
      y += 46;
    });
    return { s, y };
  }
  function fightSVG(g) {
    let body = fightClock(g);
    const rows = statRows(g, 112);
    if ((g.stats || []).length) {
      body += `<text class="uf-who" x="${W / 2 - 10}" y="92" text-anchor="end">him</text>
        <text class="uf-who" x="${W / 2 + 10}" y="92">${esc(g.opp)}</text>` + rows.s;
    } else {
      body += `<text class="uf-none" x="${W / 2}" y="104" text-anchor="middle">ESPN tracked no numbers for this fight</text>`;
    }
    // A band under the numbers for the tip (css: it sits at the foot of a
    // fight's drawing), so a tapped row's tip never covers the rows.
    const h = (g.stats || []).length ? rows.y + 64 : 120;
    return `<svg class="cc-svg uf-svg" viewBox="0 0 ${W} ${h}" role="img" aria-label="${esc(`${RES[g.result] || ""} against ${g.opp}: ${ended(g)}.`)}">${body}</svg>`;
  }
  /* How a fight ended, after its bar; a bar that runs the clock's width
     (a five-round decision) has it on the line above, at the end. */
  function mLabel(g, end, y) {
    const t = esc(g.method === "DEC" ? "DEC" : `${SHORT[g.method] || "?"}${g.rnd ? ` R${g.rnd} ${g.clock || ""}` : ""}`);
    return end > X1 - 70 ? `<text class="uf-m" x="${X1}" y="${y + 9}" text-anchor="end">${t}</text>`
      : `<text class="uf-m" x="${(end + 6).toFixed(1)}" y="${y + 22}">${t}</text>`;
  }
  /* The career: every fight's length on one 25-minute clock, newest at
     the top, the end of three rounds marked. */
  function careerSVG(d) {
    const gs = d.games, span = X1 - 44, full = 25 * 60;
    const x = (s) => 44 + Math.min(1, (s || 0) / full) * span;
    let body = `<line class="uf-tick" x1="${x(900).toFixed(1)}" x2="${x(900).toFixed(1)}" y1="18" y2="${18 + gs.length * 34}"/>
      <text class="uf-r" x="${x(900).toFixed(1)}" y="12" text-anchor="middle">15:00</text>
      <text class="uf-r" x="${X1}" y="12" text-anchor="end">25:00</text>`;
    gs.forEach((g, i) => {
      const y = 22 + i * 34, c = CLS[g.result] || "short";
      body += `<text class="uf-res ${c}" x="14" y="${y + 20}" text-anchor="middle">${esc(g.result)}</text>
        <text class="uf-opp" x="44" y="${y + 9}">${esc(`${g.opp} · ${day(g.date)}`)}</text>
        <rect class="uf-fill ${c}" x="44" y="${y + 14}" width="${(x(g.secs) - 44).toFixed(1)}" height="9" rx="3"/>
        ${mLabel(g, x(g.secs), y)}`;
    });
    return `<svg class="cc-svg uf-svg" viewBox="0 0 ${W} ${24 + gs.length * 34}" role="img" aria-label="${esc(`His last ${gs.length} fights, how long each lasted and how it ended.`)}">${body}</svg>`;
  }
  function legend() {
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt c"></i>Won</span>
      <span><i class="dt i"></i>Lost</span><span><i class="dt uf-d"></i>Draw or no contest</span></div>`;
  }

  /* ---------------- the numbers ---------------- */
  function gameTiles(g) {
    return `<div class="cc-tiles cc-tiles-6">${[
      tile("Result", RES[g.result] || "—"), tile("Method", METHOD[g.method] || "—"),
      tile("Round", g.method === "DEC" ? "—" : g.rnd || "—", g.method === "DEC" ? "went the distance" : ""),
      tile("Time", g.method === "DEC" ? "—" : g.clock || "—", "in the round"),
      tile("Fight lasted", clock(g.secs)), tile("Scheduled", `${g.rounds || 3} rounds`)].join("")}</div>`;
  }
  function seasonTiles(d) {
    const L = d.season_line;
    return `<div class="cc-tiles cc-tiles-6">${[
      tile("Record", record(L), `last ${L.n} fights`),
      tile("Won by finish", `${L.ko_w + L.sub_w} of ${L.w}`, pct(L.finish_w)),
      tile("Stopped", `${L.ko_l + L.sub_l} of ${L.l}`, "his losses"),
      tile("Distance", pct(L.distance), "went to the cards"),
      tile("Average fight", clock(L.avg_secs)), tile("Round 1", L.r1, "finishes, either way")].join("")}</div>`;
  }
  function statList(g) {
    if (!(g.stats || []).length) return `<p class="cc-note">ESPN tracked no numbers for this fight.</p>`;
    return `<div class="cc-list" role="list">${g.stats.map((st, i) => {
      const b = st.me == null || st.opp == null || st.me === st.opp ? "short" : st.me > st.opp ? "gain" : "loss";
      return `<button type="button" role="listitem" class="cc-row uf-row${sel(i)}" data-i="${i}">
        <i class="dot ${b}"></i>
        <span class="cc-r-h">${esc(st.name)}</span>
        <b class="cc-r-y ${b}">${esc(of(st.me, st.me_att))}</b>
        <span class="uf-o">${esc(of(st.opp, st.opp_att))}</span>
      </button>`;
    }).join("")}</div>`;
  }
  function tables(d) {
    const out = [tableHTML("How he wins and loses", ["", "Won", "Lost"],
      (d.by_method || []).map((m) => [m.name, m.w, m.l]))];
    if ((d.by_rounds || []).length) {
      out.push(tableHTML("Three rounds and five", ["Scheduled", "Fights", "Record", "Distance", "Average"],
        d.by_rounds.map((r) => [`${r.rounds} rounds`, r.n, record(r), pct(r.distance), clock(r.avg_secs)])));
    }
    if ((d.by_finish || []).length) out.push(tableHTML("When it ended", ["", "Fights"], d.by_finish.map((f) => [f.name, f.n])));
    return out.join("");
  }

  Q.draw("fights", {
    one: "number", splitsTitle: "Every split · how he wins and loses, three rounds and five, when it ended",
    listTitle: (g) => `That fight’s numbers · his, then ${g.opp}’s`,
    items: (g) => g.stats || [],
    count: (L) => `${L.n} fights`,
    seasonTitle: (d) => `His last ${d.games.length} fights · ${record(d.season_line)}`,
    gameTitle: (g) => [`vs ${g.opp}`, day(g.date), (g.division || "").toLowerCase()].filter(Boolean).join(" · "),
    chip: (g) => `${g.result} ${g.method === "DEC" ? "DEC" : `${SHORT[g.method] || ""}${g.rnd ? ` R${g.rnd}` : ""}`}`.trim(),
    game: (g) => fightSVG(g),
    season: (d) => careerSVG(d),
    gameSide: (g) => `${legend()}${gameTiles(g)}`,
    seasonSide: (d) => `${legend()}${seasonTiles(d)}`,
    list: (g) => statList(g),
    splits: (d) => tables(d),
    note: () => `<p class="cc-note">Every fight on ESPN’s record of his last fights (up to fifteen), newest first: the result, how it ended, the round and the time in it, and how long it lasted on the rounds it was scheduled for. Both men’s numbers are ESPN’s, where it tracked the bout; a regional fight often has none. Nothing here moves a price.</p>`,
    tip: (st, g) => `<b>${esc(st.name)} ${esc(of(st.me, st.me_att))}</b>
      <span>${esc(`${g.opp}: ${of(st.opp, st.opp_att)}`)}</span>`,
  });
})();
