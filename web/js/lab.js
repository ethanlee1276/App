/* Qellys Book — the inventions (engine/ideas), on the pick and game pages.
   ==========================================================================
   Ethan, 2026-10-16: "add everything now. 1-13 and dont stop till
   everything is done." Thirteen ideas from a brainstorm of things no
   betting app he could name was doing. Each is built and measured in its
   own engine module; the builds write one private file per board
   (engine/ideas), the server hands a member one pick's or one game's slice
   of it (/api/ideas), and this draws it.

   THE RULE EVERY SECTION KEEPS: a reading is labelled a reading. A section
   whose measurement has not cleared its bar says so in its own words, and
   nothing here changes a pick.

   LOADED BY js/extras.js on first use (pickLab / gameLab), with
   css/lab.css. The drawing functions take the slice as data and return
   HTML, so the tests run them alone in Node. */
(function () {
  "use strict";

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 1) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d).replace(/\.0+$/, ""));
  const signed = (v, d = 2) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`);
  const pct = (p, d = 0) => (p == null || !Number.isFinite(p) ? "—" : `${(p * 100).toFixed(d)}%`);
  const am = (n) => (n == null ? "—" : n > 0 ? `+${n}` : `−${Math.abs(n)}`);

  /* The badge every section wears: what its measurement says. */
  function badge(state) {
    const t = { holds: ["Measured · holds", "ok"], fails: ["Measured · does not hold", "no"],
                pending: ["Reading · not measured yet", "wait"], info: ["Context", "info"] }[state] || ["Reading", "wait"];
    return `<i class="lb-badge lb-${t[1]}">${esc(t[0])}</i>`;
  }
  function card(title, sub, state, body, foot) {
    return `<section class="lb-card"><header><div><h3>${esc(title)}</h3>${sub ? `<p>${esc(sub)}</p>` : ""}</div>${badge(state)}</header>
      ${body}${foot ? `<p class="lb-fine">${foot}</p>` : ""}</section>`;
  }

  // ---- 1. the books checked against themselves (engine/bookmenu) ----------
  function menuState(sec) {
    const v = (sec && sec.verdict) || {};
    const sides = Object.values(v).flatMap((s) => Object.values(s || {}));
    if (!sides.length) return "pending";
    return sides.some((s) => s && s.holds) ? "holds" : "fails";
  }
  function menuRow(r) {
    const legs = (r.parts || []).map((p) => `${esc(p.player)}${p.market ? ` (${esc(p.market.replace(/_/g, " "))})` : ""} ${num(p.line, r.check === "td_total" ? 2 : 1)}`).join(" · ");
    const lean = r.lean ? `<b class="lb-lean">${esc(r.lean.replace("parent", r.check === "td_total" ? "points" : "the total").replace("parts", "the pieces"))}</b>` : "";
    const z = r.z == null ? "normal not measured yet" : `${signed(r.z, 1)} spreads from normal`;
    const what = r.check === "td_total"
      ? `TD prices add to <b>${num(r.sum, 2)}</b> touchdowns; ${esc(r.parent.player)} (${num(r.points, 1)}) imply <b>${num(r.parent.line, 2)}</b>`
      : `${esc(r.parent.player)} <b>${num(r.parent.line)}</b> vs the pieces adding to <b>${num(r.sum)}</b> ${esc(r.unit)}`;
    return `<li class="${r.lean ? "flag" : ""}"><div class="lb-m-h"><span class="lb-book">${esc(r.book)}</span>
      <span>${esc(r.label)}</span></div><div class="lb-m-b">${what} · <span class="lb-z">${esc(z)}</span>${lean ? ` · ${lean}` : ""}</div>
      <div class="lb-m-legs">${legs}</div></li>`;
  }
  function menuHTML(sec, whose) {
    if (!sec || !(sec.rows || []).length) return "";
    const s = sec.summary || {};
    const state = menuState(sec);
    const sub = whose === "game"
      ? `${s.checked || 0} menus at this game checked · ${s.flagged || 0} flagged`
      : "Every menu at every book that prices him, checked: do its own numbers add up?";
    const foot = state === "holds"
      ? "A flagged menu’s lean has beaten its fair price on held-out seasons; it is still not on the board without a yes."
      : `A menu is flagged ${num(sec.flag_z || 2)} spreads from what this box measured as normal for that book’s menu. Which side a gap points to is a reading: nothing on the board uses it until the measurement clears its bar.`;
    return card("Do the books add up?", sub, state, `<ul class="lb-menu">${sec.rows.map(menuRow).join("")}</ul>`, esc(foot));
  }

  // ---- 2. the market's whole curve against ours (engine/altcurve) ---------
  function curveSVG(rungs) {
    const W = 320, H = 150, L = 34, R = 10, T = 10, B = 24;
    const xs = rungs.map((r) => r.line), x0 = Math.min(...xs), x1 = Math.max(...xs);
    const x = (v) => L + (x1 === x0 ? 0.5 : (v - x0) / (x1 - x0)) * (W - L - R);
    const y = (p) => T + (1 - p) * (H - T - B);
    const path = (k) => rungs.map((r, i) => `${i ? "L" : "M"}${x(r.line).toFixed(1)},${y(r[k]).toFixed(1)}`).join("");
    const dots = (k, c) => rungs.map((r) => `<circle class="${c}" cx="${x(r.line).toFixed(1)}" cy="${y(r[k]).toFixed(1)}" r="3"/>`).join("");
    const grid = [0, 0.5, 1].map((p) => `<line class="lb-g" x1="${L}" x2="${W - R}" y1="${y(p)}" y2="${y(p)}"/>
      <text class="lb-ax" x="${L - 4}" y="${y(p) + 3}" text-anchor="end">${p * 100}%</text>`).join("");
    const ticks = rungs.map((r) => `<text class="lb-ax" x="${x(r.line).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(num(r.line))}</text>`).join("");
    return `<svg class="lb-curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Chance of going over each number: the market's curve and ours, ${rungs.length} rungs`)}">
      ${grid}<path class="lb-mk" d="${path("market")}"/><path class="lb-us" d="${path("ours")}"/>${dots("market", "lb-mk-d")}${dots("ours", "lb-us-d")}${ticks}</svg>`;
  }
  function curveHTML(sec) {
    if (!sec || !(sec.rungs || []).length) return "";
    const v = sec.verdict || {};
    const state = v.holds ? "holds" : v.settled ? "fails" : "pending";
    const rows = sec.rungs.map((r) => `<tr><td>Over ${esc(num(r.line))}</td><td>${pct(r.market)}</td><td>${pct(r.ours)}</td>
      <td class="${Math.abs(r.gap) >= 0.06 ? (r.gap > 0 ? "pos" : "neg") : ""}">${r.gap >= 0 ? "+" : "−"}${(Math.abs(r.gap) * 100).toFixed(0)}</td><td>${r.books}</td></tr>`).join("");
    const read = sec.ends_disagree
      ? `<p class="lb-read">The middle agrees; the <b>${sec.tail_side === "over" ? "high" : "low"} end</b> does not — we make
        over ${esc(num(sec.tail_line))} ${sec.tail_gap > 0 ? "likelier" : "less likely"} than the market by ${(Math.abs(sec.tail_gap) * 100).toFixed(0)} points.</p>`
      : `<p class="lb-read">The market’s middle sits at ${esc(num(sec.market_median))}${sec.market_spread ? `, give or take ${esc(num(sec.market_spread))}` : ""}.</p>`;
    return card("The market’s whole curve", "Every rung of the alternate ladder, de-vigged, beside our chance at the same number.", state,
      `${curveSVG(sec.rungs)}<div class="lb-key"><span class="mk">Market</span><span class="us">Ours</span></div>${read}
       <div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Number</th><th>Market</th><th>Ours</th><th>Gap</th><th>Books</th></tr></thead>
       <tbody>${rows}</tbody></table></div>`,
      "Only rungs a book prices both ways are used, each de-vigged on its own two prices. Where the two curves part at the ends is a reading; it is being scored on every settled game before anything uses it.");
  }

  // ---- 3. how each book sets his line (engine/bookrecipe) -----------------
  function recipeHTML(sec) {
    if (!sec || !(sec.books || []).length) return "";
    const v = sec.verdict || {};
    const state = v.holds ? "holds" : v.n ? "fails" : "pending";
    const f = sec.form || {};
    const rows = sec.books.map((b) => `<tr><td>${esc(b.book)}</td><td>${esc(num(b.line))}</td><td>${esc(num(b.recipe))}</td>
      <td>${pct(b.last1)}</td></tr>`).join("");
    return card("How the books set his line", `Last game ${num(f.last1)} · last three ${num(f.last3)} · season ${num(f.season)} · career ${num(f.career)}`, state,
      `<div class="lb-stats"><div class="lb-stat"><span>Results expect</span><b>${esc(num(sec.expect))}</b></div>
       <div class="lb-stat"><span>Results weigh last game</span><b>${pct(sec.last1)}</b></div></div>
       <div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Book</th><th>Hung</th><th>Its recipe</th><th>Last-game weight</th></tr></thead>
       <tbody>${rows}</tbody></table></div>`,
      "Each book’s recipe is fitted from the lines it hung on past games; the results recipe from what players actually did. Where they lean differently is a habit worth knowing — and a reading until the held-out test says otherwise.");
  }

  // ---- 4. which books copy which (engine/bookclusters) ---------------------
  function copiesHTML(sec) {
    if (!sec || !sec.books) return "";
    const c = sec.consensus || {};
    const state = !sec.measured ? "pending" : c.holds ? "holds" : c.n ? "fails" : "pending";
    const gap = sec.by_group != null && sec.by_book != null ? sec.by_group - sec.by_book : null;
    const stale = (sec.stale || []).map((s) => `<li><b>${esc(s.leader)}</b> moved to ${esc(num(s.line))}; still at the old number:
      ${Object.entries(s.behind).map(([b, l]) => `${esc(b)} ${esc(num(l))}`).join(", ")} <span class="lb-z">(its copies usually follow in ~${esc(num(s.lag_min, 0))} min)</span></li>`).join("");
    const groups = (sec.groups || []).map((g) => `<li>${g.map(esc).join(" · ")}</li>`).join("");
    return card("Which books copy which", `${sec.books} books price ${esc(num(sec.line))} — ${sec.opinions} independent opinion${sec.opinions === 1 ? "" : "s"}`, state,
      `<div class="lb-stats"><div class="lb-stat"><span>Fair over, by book</span><b>${pct(sec.by_book, 1)}</b></div>
       <div class="lb-stat"><span>Fair over, by opinion</span><b>${pct(sec.by_group, 1)}</b></div>
       <div class="lb-stat ${gap != null && Math.abs(gap) >= 0.02 ? (gap > 0 ? "good" : "bad") : ""}"><span>Difference</span><b>${gap == null ? "—" : `${gap >= 0 ? "+" : "−"}${Math.abs(gap * 100).toFixed(1)}`}</b></div></div>
       ${stale ? `<ul class="lb-list">${stale}</ul>` : ""}
       ${groups ? `<details class="lb-more"><summary>Books that hang the same number (one opinion each)</summary><ul class="lb-list">${groups}</ul></details>` : ""}`,
      sec.measured ? "Groups come from how often two books hung the identical line on every stored close. Whether counting each opinion once beats counting each book is measured on held-out seasons; until it holds, the board keeps counting books."
        : "Which books copy which is measured on the box’s stored closes first; until then every book counts as its own opinion here.");
  }

  // ---- 5. the injury report: how he practised, who filed it (engine/practice)
  const PRACTISED = { DNP: "did not practise", Limited: "was limited in practice", Full: "practised fully", None: "has no practice note" };
  function practiceState(sec) {
    const h = sec.held_out || {};
    return !sec.measured ? "pending" : h.holds ? "holds" : h.n ? "fails" : "pending";
  }
  function practiceHTML(sec) {
    if (!sec || !sec.designation) return "";
    const stats = sec.league == null ? "" : `<div class="lb-stats">
      <div class="lb-stat"><span>${esc(sec.designation)} + ${esc(sec.practice)}: played</span><b>${pct(sec.league)}</b></div>
      ${sec.club != null ? `<div class="lb-stat"><span>With ${esc(sec.team)}’s record</span><b>${pct(sec.club)}</b></div>` : ""}
      ${sec.ratio != null ? `<div class="lb-stat"><span>Snaps when he plays</span><b>${pct(sec.ratio)}</b></div>` : ""}</div>`;
    return card("The injury report, read closely", `${esc(sec.designation)}${sec.injury ? ` (${esc(sec.injury)})` : ""} — he ${esc(PRACTISED[sec.practice] || PRACTISED.None)}.`,
      practiceState(sec), stats || `<p class="lb-read">How often a man listed like this plays is measured on every stored report first.</p>`,
      `How often players listed and practising like this have played, from every report since the box’s first season${sec.club_n ? `, and how often this club’s questionable players did (${sec.club_n} listings, pulled toward the league)` : ""}. A reading: the board’s injury hold is unchanged.`);
  }
  function practiceGameHTML(sec) {
    if (!sec || !(sec.rows || []).length) return "";
    const rows = sec.rows.map((r) => `<tr><td>${esc(r.player)} <small>${esc(r.team)}</small></td><td>${esc(r.designation)}</td>
      <td>${esc(r.practice)}</td><td>${pct(r.league)}</td><td>${pct(r.club)}</td></tr>`).join("");
    return card("Who is on the injury report", "Every listed player in this game, how he practised, and how often men listed like him have played.",
      practiceState(sec), `<div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Player</th><th>Listed</th><th>Practice</th><th>Played</th><th>Club-adjusted</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`, "A reading: the board’s injury hold is unchanged.");
  }

  // ---- 6. how much the public is reading about him (engine/attention) -------
  function spark(days) {
    const vs = (days || []).filter((v) => Number.isFinite(v));
    if (vs.length < 2) return "";
    const W = 300, H = 50, max = Math.max(...vs, 1);
    const pts = vs.map((v, i) => `${(i / (vs.length - 1) * W).toFixed(1)},${(H - 4 - v / max * (H - 8)).toFixed(1)}`).join(" ");
    return `<svg class="lb-spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Daily Wikipedia views, last ${vs.length} days`)}"><polyline points="${pts}"/></svg>`;
  }
  function attentionHTML(sec) {
    if (!sec || sec.ratio == null) return "";
    const v = sec.verdict || {};
    const state = v.holds ? "holds" : v.closes ? "fails" : "pending";
    return card("How much the public is reading about him", `Wikipedia: ${num(sec.recent, 0)} views a day lately against ${num(sec.usual, 0)} usually`, state,
      `<div class="lb-stats"><div class="lb-stat ${sec.spike ? "bad" : ""}"><span>Attention</span><b>${esc(num(sec.ratio, 1))}×</b></div></div>
       ${spark(sec.days)}${sec.spike ? `<p class="lb-read">He is being read about <b>far more than usual</b>. Public money follows public attention, and a book that knows it may lean his over.</p>` : ""}`,
      "Daily human views of his Wikipedia page (Wikimedia’s own public count). Whether a spike means his over is overpriced is being measured on every past close; until it holds, nothing on the board reads it.");
  }

  // ---- 7. the air a kick flies through (engine/kickphysics) ------------------
  function kicksHTML(sec) {
    if (!sec || sec.density == null) return "";
    const f = sec.fit || {};
    const state = f.holds ? "holds" : f.n ? "fails" : "pending";
    const dev = sec.density_dev;
    const air = `${Math.abs(dev * 100).toFixed(0)}% ${dev < 0 ? "thinner" : "thicker"} than sea-level air`;
    const wp = sec.wind_parts;
    const wind = sec.dome ? "Indoors: no wind."
      : sec.wind_mph == null ? "No wind reading yet."
      : `${num(sec.wind_mph, 0)} mph${sec.wind_dir ? ` from the ${esc(sec.wind_dir)}` : ""}${wp ? ` — ${num(Math.abs(wp.along), 0)} mph down the field, ${num(wp.across, 0)} across it` : ""}.`;
    return card("The air a kick flies through", `${sec.dome ? "Indoors" : `${num(sec.temp_f, 0)}°F`} at ${num(sec.altitude_ft, 0)} ft — ${air}`, state,
      `<div class="lb-stats"><div class="lb-stat ${dev < -0.05 ? "good" : dev > 0.05 ? "bad" : ""}"><span>Air density</span><b>${esc(num(sec.density, 3))}</b></div>
       ${sec.plays_like_50 != null ? `<div class="lb-stat"><span>A 50-yard try plays like</span><b>${esc(num(sec.plays_like_50, 1))}</b></div>` : ""}</div>
       <p class="lb-read">${wind}</p>`,
      sec.plays_like_50 != null ? "Thinner air means less drag. How much that moves a make was measured on every stored field goal and held up on held-out seasons."
        : `Thinner air means less drag, so a kick carries farther. How many yards that is gets measured on every stored field goal first; until then this is the air, not a number.${wp ? "" : " The wind’s angle to the uprights needs this stadium’s bearing, which is recorded from a source one stadium at a time."}`);
  }

  // ---- 8. rookies and transfers from the college line (engine/rookies) ------
  function rookieHTML(sec) {
    if (!sec || sec.college_pg == null) return "";
    const rookie = sec.kind === "rookie";
    const h = sec.held_out || {};
    const state = !rookie ? "info" : h.holds ? "holds" : h.n ? "fails" : "pending";
    const sub = rookie
      ? `Last college season at ${esc(sec.school)}: ${num(sec.college_pg, 1)} a game over ${sec.college_games} games · drafted ${sec.pick >= 260 ? "undrafted" : `#${sec.pick}`}`
      : `Last season at ${esc(sec.school)}: ${num(sec.college_pg, 1)} a game over ${sec.college_games} games`;
    const stat = rookie
      ? `<div class="lb-stat"><span>His college line, translated</span><b>${esc(num(sec.translated, 1))}</b></div>`
      : `<div class="lb-stat"><span>Transfers keep</span><b>${pct(sec.keep)}</b></div><div class="lb-stat"><span>His line, carried over</span><b>${esc(num(sec.translated, 1))}</b></div>`;
    return card(rookie ? "His college line, translated" : "A transfer’s line, carried over", sub, state, `<div class="lb-stats">${stat}</div>`,
      rookie ? "A first NFL month projected from his last college season and where he was drafted, fitted on past rookie classes. Whether it beats the draft slot alone and his position’s rookie mean is tested on the two newest classes; until it does, nothing on the board reads it."
        : `How much of their old production college transfers kept in their first four games at the new school (${sec.keep_n} transfers). Context: nothing on the board reads it.`);
  }

  // ---- 9. players inside the simulated game (engine/playsim) --------------
  const MKT = (m) => String(m || "").replace(/_/g, " ").replace("rec yds", "receiving yards").replace("rush yds", "rushing yards")
    .replace("pass yds", "passing yards").replace("rush att", "carries").replace("pass att", "attempts").replace("pass cmp", "completions");
  function simState(v) {
    return v && v.holds ? "holds" : v && v.pairs ? "fails" : "pending";
  }
  function simFoot(v) {
    const p = (v && v.vs_pricer) || {};
    return "Each team’s game played pass by pass and carry by carry, from each man’s share of the throws and carries over the team’s last eight games, with one shared shock each for the number of plays, the game script and the passer’s day. "
      + (v && v.pairs ? `Measured on ${v.pairs.toLocaleString()} past pairs: against the parlay pricer’s number for that kind of pair it is ${p.gain > 0 ? "better" : "no better"} by ${num(p.gain, 4)} a pair (t ${num(p.t, 1)}). ` : "")
      + "Until it beats the pricer on held-out seasons, nothing on a ticket reads it.";
  }
  function simHTML(sec) {
    if (!sec || !(sec.links || []).length) return "";
    const rows = sec.links.map((l) => {
      const lift = l.their_over_given_his != null && l.their_over != null ? l.their_over_given_his - l.their_over : null;
      return `<tr><td>${esc(l.player)}</td><td>${esc(MKT(l.market))} ${esc(num(l.line))}</td><td>${pct(l.their_over)}</td>
        <td class="${lift == null ? "" : lift >= 0.03 ? "good" : lift <= -0.03 ? "bad" : ""}">${pct(l.their_over_given_his)}</td><td>${signed(l.rho)}</td><td>${signed(l.pricer_rho)}</td></tr>`;
    }).join("");
    return card("The same simulated games", `His over hits in ${pct(sec.sim_over)} of ${Number(sec.trials || 0).toLocaleString()} simulated games at ${num(sec.line)}`, simState(sec.verdict),
      `<div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Teammate</th><th>Leg</th><th>Hits</th><th>When his hits</th><th>Sim link</th><th>Pricer’s</th></tr></thead>
       <tbody>${rows}</tbody></table></div>`, simFoot(sec.verdict));
  }
  function simGameHTML(sec) {
    if (!sec || !(sec.pairs || []).length) return "";
    const rows = sec.pairs.map((p) => `<tr><td>${esc(p.a)}</td><td>${esc(p.b)}</td><td>${signed(p.rho)}</td><td>${signed(p.pricer_rho)}</td></tr>`).join("");
    return card("Where the simulation and the parlay pricer disagree", "Teammates’ legs on tonight’s board, joined in the same simulated games", simState(sec.verdict),
      `<div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Leg</th><th>With</th><th>Sim link</th><th>Pricer’s</th></tr></thead><tbody>${rows}</tbody></table></div>`,
      simFoot(sec.verdict));
  }

  // ---- 10. a role change spotted early (engine/rolechange) -----------------
  function roleBars(rd) {
    const vs = (rd.values || []).filter((v) => Number.isFinite(v));
    if (vs.length < 2) return "";
    const W = 300, H = 56, max = Math.max(...vs, 0.05), bw = W / vs.length;
    const cut = rd.games_ago ? vs.length - rd.games_ago : null;
    const bars = vs.map((v, i) => {
      const h = Math.max(1, v / max * (H - 6));
      return `<rect class="${cut != null && i >= cut ? "new" : ""}" x="${(i * bw + 1).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${h.toFixed(1)}"/>`;
    }).join("");
    const mark = cut != null ? `<line x1="${(cut * bw).toFixed(1)}" x2="${(cut * bw).toFixed(1)}" y1="0" y2="${H}"/>` : "";
    return `<svg class="lb-role" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`His share, game by game, ${vs.length} games`)}">${bars}${mark}</svg>`;
  }
  const ROLE_NAMES = { tgt: "Target share", car: "Carry share", snap: "Snap share" };
  function roleState(rd) {
    const v = rd.verdict || {};
    return v.holds ? "holds" : v.series ? "fails" : "pending";
  }
  function roleHTML(sec) {
    const reads = (sec && sec.reads) || {};
    const keys = Object.keys(reads);
    if (!keys.length) return "";
    const lead = reads[sec.lead] ? sec.lead : keys[0];
    const rd = reads[lead];
    const sub = rd.games_ago && rd.flag
      ? `${ROLE_NAMES[lead]} ${pct(rd.before)} → ${pct(rd.after)} over his last ${rd.games_ago} game${rd.games_ago === 1 ? "" : "s"}`
      : `${ROLE_NAMES[lead]}: no clear change in his role`;
    const others = keys.filter((k) => k !== lead).map((k) => {
      const o = reads[k];
      return `<li><b>${esc(ROLE_NAMES[k])}</b> ${pct(o.forecast)} next game${o.flag && o.games_ago ? ` — changed ${o.games_ago} game${o.games_ago === 1 ? "" : "s"} ago (${pct(o.before)} → ${pct(o.after)})` : ""}</li>`;
    }).join("");
    return card("His role, watched for a change", sub, roleState(rd),
      `<div class="lb-stats"><div class="lb-stat ${rd.flag ? "good" : ""}"><span>Chance it changed in the last 3 games</span><b>${pct(rd.changed)}</b></div>
       <div class="lb-stat"><span>Detector’s next game</span><b>${pct(rd.forecast, 1)}</b></div>
       <div class="lb-stat"><span>Four-week average</span><b>${pct(rd.four_week, 1)}</b></div></div>
       ${roleBars(rd)}${others ? `<ul class="lb-list">${others}</ul>` : ""}`,
      "A Bayesian changepoint detector reads his share game by game and weighs every possible start of his current role by how well it explains the games since. The board reads volume as his last four weeks; whether the detector forecasts the next game closer is measured on held-out seasons, and until it does, the board’s number is unchanged.");
  }
  function roleGameHTML(sec) {
    if (!sec || !(sec.rows || []).length) return "";
    const rows = sec.rows.map((r) => `<tr><td>${esc(r.player)}</td><td>${esc(r.label)}</td><td>${pct(r.before)}</td><td>${pct(r.after)}</td><td>${esc(r.games_ago)}</td><td>${pct(r.changed)}</td></tr>`).join("");
    return card("Roles that just changed", "Players in this game whose share of the work jumped or fell", "pending",
      `<div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Player</th><th>Share</th><th>Before</th><th>Since</th><th>Games</th><th>Sure</th></tr></thead><tbody>${rows}</tbody></table></div>`,
      "Read by a Bayesian changepoint detector on each man’s share game by game. A reading: the board’s volume is unchanged.");
  }

  // ---- 11. honest ranges (engine/conformal) ---------------------------------
  function rangeBar(sec) {
    const r50 = (sec.ranges || {})["0.5"], r80 = (sec.ranges || {})["0.8"];
    if (!r50 || !r80) return "";
    const lo = Math.min(r80[0], sec.line, sec.projection), hi = Math.max(r80[1], sec.line, sec.projection);
    const pad = (hi - lo) * 0.08 || 1, a = lo - pad, b = hi + pad, W = 300;
    const x = (v) => ((v - a) / (b - a) * W).toFixed(1);
    return `<svg class="lb-range" viewBox="0 0 ${W} 44" role="img" aria-label="${esc(`80% range ${num(r80[0])} to ${num(r80[1])}, 50% range ${num(r50[0])} to ${num(r50[1])}, line ${num(sec.line)}`)}">
      <rect class="r80" x="${x(r80[0])}" y="14" width="${(x(r80[1]) - x(r80[0])).toFixed(1)}" height="14" rx="3"/>
      <rect class="r50" x="${x(r50[0])}" y="14" width="${(x(r50[1]) - x(r50[0])).toFixed(1)}" height="14" rx="3"/>
      <line class="proj" x1="${x(sec.projection)}" x2="${x(sec.projection)}" y1="10" y2="32"/>
      <line class="line" x1="${x(sec.line)}" x2="${x(sec.line)}" y1="4" y2="40"/>
      <text x="${x(sec.line)}" y="10" text-anchor="middle">${esc(num(sec.line))}</text></svg>`;
  }
  function rangeHTML(sec) {
    if (!sec || !sec.ranges) return "";
    const v = sec.verdict || {};
    const state = v.holds ? "holds" : v.coverage ? "fails" : "pending";
    const r50 = sec.ranges["0.5"], r80 = sec.ranges["0.8"];
    const mr = sec.model_range || [];
    const cov = v.coverage ? ` On the newest ${v.n} graded picks the 50% range covered ${pct(v.coverage["0.5"])} and the 80% range ${pct(v.coverage["0.8"])}.` : "";
    return card("How wide it really is", `Half his games like this land ${num(r50[0])}–${num(r50[1])}; four in five ${num(r80[0])}–${num(r80[1])}`, state,
      `${rangeBar(sec)}<div class="lb-stats">
       <div class="lb-stat"><span>His ${esc(sec.side || "pick")} by the range</span><b>${pct(sec.range_chance)}</b></div>
       <div class="lb-stat"><span>The model’s chance</span><b>${pct(sec.model_chance)}</b></div>
       ${mr[0] != null && mr[1] != null ? `<div class="lb-stat"><span>The model’s own range</span><b>${esc(num(mr[0]))}–${esc(num(mr[1]))}</b></div>` : ""}</div>`,
      `Built from how far ${Number(sec.n || 0).toLocaleString()} graded picks landed from the number we published (conformal prediction: no assumption about the shape of the misses).${cov} A reading: nothing on the board reads it.`);
  }

  // ---- 12. the loss autopsy (engine/autopsy) --------------------------------
  const TAG_ORDER = ["volume", "efficiency", "script", "left early", "both"];
  const STEP_NAMES = { volume: "Usage (how much he is used)", efficiency: "Per touch (what he does with each)", script: "Game script", left_early: "Availability (left early)" };
  function autopsyHTML(sec) {
    const s = sec && sec.summary;
    if (!s || !s.losses) return "";
    const tags = TAG_ORDER.filter((t) => s.tags[t]).map((t) => `<span class="lb-tag t-${t.replace(" ", "-")}" style="flex:${s.tags[t]}">${esc(t)} ${Math.round(s.tags[t] / s.losses * 100)}%</span>`).join("");
    const steps = Object.entries(s.steps || {}).map(([k, v]) => `<tr><td>${esc(STEP_NAMES[k] || k)}</td><td>${pct(v.losses)}</td><td>${pct(v.wins)}</td>
      <td class="${v.z >= 2 && v.excess > 0 ? "bad" : ""}">${v.excess >= 0 ? "+" : "−"}${Math.abs(v.excess * 100).toFixed(0)}</td></tr>`).join("");
    const his = (sec.his || []).map((h) => `<li><b>${esc(h.date)}</b> ${esc(h.side)} ${esc(num(h.line))}: we said ${esc(num(h.projection))}, he did ${esc(num(h.actual))} — ${h.won ? "won" : `lost (${esc(h.tag)})`}; volume ${signed(h.parts.volume, 1)}, per touch ${signed(h.parts.efficiency, 1)}</li>`).join("");
    return card("When picks like this lose", `${s.losses} graded ${MKT(sec.market)} losses, each miss split into usage and per-touch`, "info",
      `<div class="lb-tags">${tags}</div>
       <div class="lb-scroll"><table class="lb-tbl"><thead><tr><th>Step</th><th>Against us in losses</th><th>In wins</th><th>Excess</th></tr></thead><tbody>${steps}</tbody></table></div>
       <p class="lb-read">${s.wrong_most_label ? `The step wrong most: <b>${esc(s.wrong_most_label)}</b>.` : "No step stands out from the wins yet."}</p>
       ${his ? `<details class="lb-more"><summary>His last graded picks in this market</summary><ul class="lb-list">${his}</ul></details>` : ""}`,
      "Each miss is split exactly into how much he was used against his four games before (usage) and what he did with each touch. A step is named only when it goes against our picks in losses clearly more often than in wins (z ≥ 2, 100 losses). Context: nothing on the board reads it.");
  }

  /* Section drawers, in the order the page shows them. */
  const PICK = [["range", rangeHTML], ["practice", practiceHTML], ["role", roleHTML], ["rookie", rookieHTML], ["kicks", kicksHTML], ["attention", attentionHTML], ["curve", curveHTML], ["sim", simHTML], ["copies", copiesHTML], ["recipe", recipeHTML], ["menu", (s) => menuHTML(s, "pick")], ["autopsy", autopsyHTML]];
  const GAME = [["kicks", kicksHTML], ["practice", practiceGameHTML], ["sim", simGameHTML], ["role", roleGameHTML], ["menu", (s) => menuHTML(s, "game")]];

  function draw(order, slice) {
    const secs = (slice && slice.sections) || {};
    const html = order.map(([k, fn]) => { try { return secs[k] ? fn(secs[k], slice) : ""; } catch (e) { return ""; } })
      .filter(Boolean).join("");
    if (!html) return "";
    return `<div class="section-title">Deeper reads <span class="sub">— new readings of this ${slice.home ? "game" : "pick"},
      each labelled with what its measurement says</span></div><div class="lb-grid">${html}</div>`;
  }
  const pickHTML = (slice) => draw(PICK, slice);
  const gameHTML = (slice) => draw(GAME, slice);

  const KEEP = new Map();
  function ask(el, q, render) {
    if (!el) return;
    const hit = KEEP.get(q);
    if (hit && Date.now() - hit.at < 60000) { el.innerHTML = hit.html; return; }
    fetch(q, { credentials: "same-origin" })
      .then((r) => (r.status === 401 || r.status === 402 ? { locked: true } : r.ok ? r.json() : null))
      .then((d) => {
        if (!d || d.locked) return;              // the books' table already says what a member gets
        const html = render(d);
        KEEP.set(q, { at: Date.now(), html });
        if (el.isConnected) el.innerHTML = html;
      }).catch(() => {});
  }
  function pickLab(el, sport, r) {
    if (!el || !sport || !r || !r.player || !r.market) return;
    const p = new URLSearchParams({ sport, player: r.player, market: r.market, side: r.side || "", line: r.line == null ? "" : r.line });
    ask(el, `/api/ideas?${p}`, pickHTML);
  }
  function gameLab(el, sport, g) {
    if (!el || !sport || !g || !g.home || !g.away) return;
    const p = new URLSearchParams({ sport, home: g.home, away: g.away });
    ask(el, `/api/ideas?${p}`, gameHTML);
  }

  window.QBLab = { pickLab, gameLab, pickHTML, gameHTML, menuHTML, curveHTML, recipeHTML, copiesHTML, practiceHTML, practiceGameHTML, attentionHTML, kicksHTML, rookieHTML, simHTML, simGameHTML, roleHTML, roleGameHTML, rangeHTML, autopsyHTML, badge };
})();
