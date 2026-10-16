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

  /* Section drawers, in the order the page shows them. */
  const PICK = [["curve", curveHTML], ["recipe", recipeHTML], ["menu", (s) => menuHTML(s, "pick")]];
  const GAME = [["menu", (s) => menuHTML(s, "game")]];

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

  window.QBLab = { pickLab, gameLab, pickHTML, gameHTML, menuHTML, curveHTML, recipeHTML, badge };
})();
