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

   IN THE FRAME OF ETHAN'S NFL RENDERS (2026-10-14): where a game has its
   stadium, a fight has the arena — the site's own octagon render — with
   both fighters either side of it, the winner's side lit, and the result
   between them; the legend under the drawing, both men's numbers in the
   render's table, How he wins | Rounds | Finishes as the route chart's
   other views, and his fight history one tap away as a spreadsheet.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, state, grid, two, pills, bars, hero } = Q.h;
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
  /* THAT FIGHT'S NUMBERS AS THE RENDERS' TABLE: each stat, his, then his
     opponent's, and who was ahead in it (on a wide card; a phone colours
     his number instead). */
  const last = (name) => { const w = String(name || "").trim().split(/\s+/); return w[w.length - 1] || "Opponent"; };
  function statList(g) {
    if (!(g.stats || []).length) return `<p class="cc-note">ESPN tracked no numbers for this fight.</p>`;
    const cols = [{ h: "Stat", c: "cc-c-m", p: "minmax(0,1fr)", w: "minmax(0,1fr)" },
                  { h: "Him", c: "cc-c-y", p: "76px", w: "110px", r: 1 },
                  { h: last(g.opp), c: "uf-o", p: "76px", w: "110px", r: 1 },
                  { h: "Ahead", c: "cc-c-res", w: "110px" }];
    return grid("fight", cols, g.stats.map((st, i) => {
      const b = st.me == null || st.opp == null || st.me === st.opp ? "short" : st.me > st.opp ? "gain" : "loss";
      const pill = b === "gain" ? ["Him", "good"] : b === "loss" ? [last(g.opp), "bad"] : ["Even", "mute"];
      return {
        i, said: `${st.name}: his ${of(st.me, st.me_att)}, ${g.opp}’s ${of(st.opp, st.opp_att)}`,
        cells: [two(st.name, ""), [esc(of(st.me, st.me_att)), b], esc(of(st.opp, st.opp_att)), pills([pill])],
      };
    }));
  }
  //: His fight history, a fight a row, as a spreadsheet.
  const csv = (g, d) => [["Date", "Opponent", "Result", "Method", "Round", "Time", "Fight lasted", "Scheduled rounds", "Division"]]
    .concat((d.games || []).map((x) => [x.date || "", x.opp || "", RES[x.result] || x.result || "", METHOD[x.method] || x.method || "",
      x.rnd || "", x.clock || "", clock(x.secs), x.rounds || "", x.division || ""]));
  /* THE FIGHT OVER THE ARENA (the render's game over its stadium): him on
     the left, his opponent on the right, the winner's side lit, and
     between them the result and how it ended; his career in the same
     frame. No team, no building: the site's octagon render behind. */
  const inits = (name) => String(name || "").replace(/[.,']/g, "").split(/\s+/).filter(Boolean)
    .map((w, i, a) => (i === 0 || i === a.length - 1 ? w[0] : "")).join("").toUpperCase().slice(0, 2) || "?";
  function side(name, sub, right, me) {
    const w = String(name || "").trim().split(/\s+/), lastName = w.length > 1 ? w.pop() : w[0] || "", first = w.length && w[0] !== lastName ? w.join(" ") : "";
    const mark = `<span class="cc-hero-logo"><span class="uf-ring${me ? " me" : ""}" aria-hidden="true">${esc(inits(name))}</span></span>`;
    const words = `<span class="cc-hero-name">${first ? `<small>${esc(first)}</small>` : ""}<b style="--nl:${Q.h.nameLen(lastName)}">${esc(lastName)}</b>${sub ? `<i>${esc(sub)}</i>` : ""}</span>`;
    return `<div class="cc-hero-team${right ? " r" : ""}">${right ? words + mark : mark + words}</div>`;
  }
  function fightHero(g, d) {
    const art = typeof venueSrc === "function"
      ? `<img class="venue-photo" alt="" loading="lazy" decoding="async" src="${esc(venueSrc("img/venues/ufc-hero.jpg"))}" data-onerr="remove"/>` : "";
    const L = d.season_line || {};
    if (!g) {
      return hero("--ta:var(--brand);--tb:var(--brand)", art, side(d.player, d.position || "", false, true),
        `<div class="cc-hero-mid"><small>Career</small><b class="cc-hero-score"><em>${esc(record(L))}</em></b><span>${esc(`last ${L.n} fight${L.n === 1 ? "" : "s"}`)}</span></div>`,
        `<div class="cc-hero-team r"><span class="cc-hero-name cc-hero-sum"><small>won by finish</small><b>${esc(String((L.ko_w || 0) + (L.sub_w || 0)))}</b></span></div>`,
        "season uf-hero");
    }
    const won = g.result === "W", lost = g.result === "L";
    const ink = `--ta:${won ? "var(--brand)" : "var(--text-mute)"};--tb:${lost ? "var(--brand)" : "var(--text-mute)"}`;
    const mid = `<div class="cc-hero-mid">${g.date ? `<small>${esc(day(g.date))}</small>` : ""}
      <b class="cc-hero-vs uf-${CLS[g.result] || "short"}">${esc(won ? "Won" : lost ? "Lost" : "Draw / NC")}</b>
      <span>${esc(ended(g))}</span></div>`;
    return hero(ink, art, side(d.player, record(L), false, true), mid, side(g.opp, (g.division || "").toLowerCase(), true, false), "uf-hero");
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
    hero: (g, d) => fightHero(g, d),
    distTitle: (v) => (v === "game" ? "The fight" : "How his fights end"),
    legend: () => legend(),
    gameSide: (g) => gameTiles(g),
    seasonSide: (d) => seasonTiles(d),
    //: His card (carrychart.js `playerHero`): no club, so his record stands where its mark would.
    heroSide: (d) => `<span class="cc-hero-name"><small>Record</small><b>${esc(record(d.season_line || {}))}</b></span>`,
    heroTiles: (d) => { const L = d.season_line || {};
      return [["Fights", L.n], ["KO/TKO", L.ko_w], ["Subs", L.sub_w], ["Decisions", L.w - L.ko_w - L.sub_w]]; },
    list: (g) => statList(g),
    csv, file: "fights", fileWhat: "his fight history",
    views: (d) => [["method", "How he wins", (d.by_method || []).some((m) => m.w + m.l)],
                   ["rounds", "Rounds", (d.by_rounds || []).length], ["finish", "Finishes", (d.by_finish || []).length]]
      .filter((v) => v[2]).map(([k, name]) => [k, name]),
    barTitle: (v) => ({ method: "How he wins and loses", rounds: "Three rounds and five", finish: "When his fights ended" }[v]),
    bars: (d, v) => (v === "method"
      ? bars((d.by_method || []).map((m) => [m.name, m.w + m.l, `${m.w} won · ${m.l} lost`]))
      : v === "rounds"
        ? bars((d.by_rounds || []).map((r) => [`${r.rounds} rounds`, r.n, `${record(r)} · ${pct(r.distance)} went the distance · ${clock(r.avg_secs)} on average`]))
        : bars((d.by_finish || []).map((f) => [f.name, f.n, f.name === "Decision" ? "went to the cards" : "finished in that round, either way"]))),
    splits: (d) => tables(d),
    note: () => `<p class="cc-note">Every fight on ESPN’s record of his last fights (up to fifteen), newest first: the result, how it ended, the round and the time in it, and how long it lasted on the rounds it was scheduled for. Both men’s numbers are ESPN’s, where it tracked the bout; a regional fight often has none. Nothing here moves a price.</p>`,
    tip: (st, g) => `<b>${esc(st.name)} ${esc(of(st.me, st.me_att))}</b>
      <span>${esc(`${g.opp}: ${of(st.opp, st.opp_att)}`)}</span>`,
  });
})();
