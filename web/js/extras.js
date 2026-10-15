/* Qellys Book — the Toolbox, and My Bets' report card.
   ==========================================================================
   Ethan, 2026-10-15, after a brainstorm of sixteen things the site could
   grow next: "do every one for every sport. i want every feature and idea
   u listed done and finished and pushed to the site."

   THE RULE EVERY TOOL HERE KEEPS: none of them changes a pick. A tool
   that shows our number shows the number the board already published, and
   anything that would move a number is measured first, somewhere else,
   before it is allowed to. What lives here is arithmetic on prices the
   reader types, the board's own published fields laid out a new way, and
   the reader's own log read back to them.

   LOADED ON FIRST USE (app.js loadExtras), like js/social.js and
   js/slip.js. It runs in the page's global scope beside app.js and uses
   its helpers (escapeHtml, teamMark, state, mbLoad …) by name, only when
   drawing; the math below uses nothing outside this file, so the tests
   run it alone in Node.

   ONE LISTENER PER EVENT for the whole page, on `data-xc` (a calculator's
   inputs: redo its numbers as the reader types) and `data-xt` (a button).
   Every card is redrawn wholesale, so nothing is bound to an element a
   redraw would orphan, and nothing in the markup is code. */
(function () {
  "use strict";

  // ---- odds math --------------------------------------------------------
  /* American odds to the decimal multiplier, or null for anything that is
     not a price (|odds| under 100, blank, text). */
  function dec(a) {
    const n = Number(String(a == null ? "" : a).replace("−", "-").replace(/[\s+]/g, ""));
    if (!Number.isFinite(n) || Math.abs(n) < 100) return null;
    return n > 0 ? 1 + n / 100 : 1 + 100 / Math.abs(n);
  }
  const implied = (a) => { const d = dec(a); return d ? 1 / d : null; };
  /* A chance (0..1) to the American price that pays it fairly. */
  function toAm(p) {
    if (!(p > 0 && p < 1)) return null;
    return p >= 0.5 ? -Math.round((100 * p) / (1 - p)) : Math.round((100 * (1 - p)) / p);
  }
  /* A decimal multiplier to American. */
  function decToAm(d) {
    if (!(d > 1)) return null;
    return d >= 2 ? Math.round((d - 1) * 100) : -Math.round(100 / (d - 1));
  }
  const amTxt = (n) => (n == null ? "—" : n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "EV");
  const pctTxt = (p, d = 1) => (p == null || !Number.isFinite(p) ? "—" : `${(p * 100).toFixed(d)}%`);
  const ptsTxt = (p) => (p == null ? "—" : `${p >= 0 ? "+" : "−"}${Math.abs(p * 100).toFixed(1)}`);
  const money = (v) => `$${Math.abs(v).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}`;

  /* Every side of one market, its hold, and the fair chance of each side
     with the hold taken out — multiplicative (each side shrunk by the same
     share) and power (the exponent that makes them sum to one, which leans
     more of the hold onto the long side). Null if any side is not a price
     or there are fewer than two. */
  function noVig(prices) {
    const ps = (prices || []).map(implied);
    if (ps.length < 2 || ps.some((p) => p == null)) return null;
    const sum = ps.reduce((a, b) => a + b, 0);
    const mult = ps.map((p) => p / sum);
    let lo = 0.5, hi = 3;
    for (let i = 0; i < 80; i++) {
      const k = (lo + hi) / 2;
      if (ps.reduce((a, p) => a + Math.pow(p, k), 0) > 1) lo = k; else hi = k;
    }
    const k = (lo + hi) / 2;
    const power = ps.map((p) => Math.pow(p, k));
    return { implied: ps, overround: sum, hold: 1 - 1 / sum, mult, power };
  }

  /* A parlay of up to twelve legs: what it pays, what the prices say it
     hits, and — where the reader gave a chance for every leg — what they
     think it hits and its value. Legs are treated as independent; the card
     says so, because same-game legs are not. */
  function parlay(legs) {
    const ok = (legs || []).filter((l) => dec(l.odds));
    if (ok.length < 2) return null;
    const d = ok.reduce((a, l) => a * dec(l.odds), 1);
    const priced = ok.reduce((a, l) => a * implied(l.odds), 1);
    const mine = ok.every((l) => l.p > 0 && l.p < 1) ? ok.reduce((a, l) => a * l.p, 1) : null;
    return { legs: ok.length, dec: d, american: decToAm(d), priced, mine,
             ev: mine == null ? null : mine * d - 1 };
  }

  /* Kelly's stake for a chance at a price: the fraction of the bankroll,
     full and at the fraction asked for, and zero for a bet with no edge. */
  function kelly(p, odds, frac, roll) {
    const d = dec(odds);
    if (!d || !(p > 0 && p < 1)) return null;
    const b = d - 1;
    const full = (b * p - (1 - p)) / b;
    const f = Math.max(0, full) * (frac > 0 ? frac : 1);
    return { full, stake: f, dollars: roll > 0 ? roll * f : null, ev: p * d - 1, need: 1 / d };
  }

  // ---- the college upset meter ------------------------------------------
  /* Tonight's college underdogs, from the moneyline cards the board
     already publishes: the dog is the side the market's fair price makes
     less likely; ours is the board's own chance for that side; the gap is
     ours minus the market's. A sharp-anchored card is the sharp book's
     number, not ours, and a game under way has no pre-game read — both are
     left out. Ranked by our chance, so the top is the likeliest upset. */
  function upsets(rows) {
    const out = [], seen = new Set();
    for (const b of rows || []) {
      if (!b || b.market !== "moneyline" || b.sharp_anchored || b.started || b.live) continue;
      const wp = Number(b.win_prob);
      const fair = noVig([b.home_odds, b.away_odds]);
      if (!fair || !(wp > 0 && wp < 1) || !b.home || !b.away) continue;
      const key = `${b.away}@${b.home}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const [fh, fa] = fair.mult;
      if (Math.abs(fh - fa) < 1e-9) continue;
      const home = b.pick_is_home ? wp : 1 - wp;
      const dogHome = fh < fa;
      const ours = dogHome ? home : 1 - home, mkt = dogHome ? fh : fa;
      out.push({ dog: dogHome ? b.home : b.away, fav: dogHome ? b.away : b.home, home: b.home, away: b.away,
                 dogHome, ours, market: mkt, gap: ours - mkt, price: Number(dogHome ? b.home_odds : b.away_odds),
                 kickoff: b.kickoff || "", date: b.date || "" });
    }
    return out.sort((a, b) => b.ours - a.ours || b.gap - a.gap);
  }
  /* The meter's word: our chance and our gap over the market, both. */
  function upsetTier(r) {
    if (r.ours >= 0.4 && r.gap >= 0.05) return ["alert", "Upset alert"];
    if (r.ours >= 0.33) return ["live", "Live dog"];
    return ["long", "Long shot"];
  }

  // ---- the report card --------------------------------------------------
  const BANDS = [["Big favourites", "−200 or shorter", (a) => a <= -200],
                 ["Favourites", "−199 to −101", (a) => a > -200 && a <= -101],
                 ["Near even", "−100 to +149", (a) => a > -101 && a < 150],
                 ["Underdogs", "+150 to +399", (a) => a >= 150 && a < 400],
                 ["Long shots", "+400 and longer", (a) => a >= 400]];
  const MIN_SAY = 20;

  function oddsNum(a) {
    const n = Number(String(a == null ? "" : a).replace("−", "-"));
    return Number.isFinite(n) ? n : null;
  }
  /* The kind of bet, from the log's own words: a ticket of several legs,
     a player prop, or a game line. */
  function kind(b) {
    if (b.src === "slip" && Array.isArray(b.legs) && b.legs.length > 1) return "Parlays";
    const d = String(b.desc || "");
    if (/ \+ |\bparlay\b|\bsgp\b|same game/i.test(d)) return "Parlays";
    if (typeof mbMarket === "function") {
      const m = mbMarket(d);
      if (m) return m.prop ? "Player props" : "Game lines";
    }
    return /\b(over|under|o\d|u\d)/i.test(d) && /[a-z]{3,} [a-z]{3,}/i.test(d) ? "Player props" : "Game lines";
  }

  /* Wins against what the prices needed. Expected wins are the sum of
     each bet's implied chance (vig in: the break-even the price set), so
     beating it means beating the book's own number, not a coin. The
     spread is the binomial's, so the verdict says when a run is still
     inside ordinary luck. */
  function tally(rows) {
    const dec_ = rows.filter((b) => b.result === "win" || b.result === "loss");
    const n = dec_.length;
    if (!n) return { n: 0 };
    const wins = dec_.filter((b) => b.result === "win").length;
    const ps = dec_.map((b) => implied(b.odds));
    const exp = ps.reduce((a, p) => a + p, 0);
    const sd = Math.sqrt(ps.reduce((a, p) => a + p * (1 - p), 0));
    return { n, wins, hit: wins / n, need: exp / n, exp, z: sd > 0 ? (wins - exp) / sd : 0 };
  }
  function verdict(t) {
    if (!t.n) return ["", "Nothing settled yet."];
    if (t.n < MIN_SAY) return ["", `${t.n} settled — too few to tell skill from a run. The card firms up past ${MIN_SAY}.`];
    if (t.z >= 2) return ["good", "Well above what your prices needed — more than two standard deviations. Keep logging: it holds up or it doesn’t."];
    if (t.z >= 1) return ["good", "Above what your prices needed, but inside the range a good run reaches by luck."];
    if (t.z > -1) return ["", "About what your prices needed — the book’s number has been right about you so far."];
    if (t.z > -2) return ["bad", "Below what your prices needed, though still inside the range a cold run reaches."];
    return ["bad", "Well below what your prices needed — more than two standard deviations. Worth a look at what you bet and where."];
  }
  /* Closing-line value in implied points: the close's chance minus the
     chance your price implied. Positive is a better price than the
     market settled on. */
  function clv(odds, close) {
    const a = implied(odds), c = implied(close);
    return a == null || c == null ? null : c - a;
  }
  function report(bets, ours) {
    const settled = (bets || []).filter((b) => b && ["win", "loss", "push"].includes(b.result) && implied(b.odds) != null);
    const all = tally(settled);
    const group = (keyOf) => {
      const m = new Map();
      for (const b of settled) {
        const k = keyOf(b);
        if (!k) continue;
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(b);
      }
      return [...m.entries()].map(([k, rows]) => ({ key: k, ...tally(rows) })).filter((g) => g.n);
    };
    const bands = BANDS.map(([name, range, test]) => ({ key: name, range,
      ...tally(settled.filter((b) => test(oddsNum(b.odds)))) })).filter((g) => g.n);
    const closes = [];
    for (const b of settled) {
      const mine = b.close != null && b.close !== "" ? clv(b.odds, b.close) : null;
      const theirs = ours && ours[b.id] ? clv(b.odds, ours[b.id].close) : null;
      if (mine != null) closes.push({ id: b.id, v: mine, from: "yours" });
      else if (theirs != null) closes.push({ id: b.id, v: theirs, from: "ours", pick: ours[b.id] });
    }
    const beat = closes.filter((c) => c.v > 0).length;
    return { all, verdict: verdict(all), bands,
             sports: group((b) => String(b.sport || "").toUpperCase() || "Other"),
             kinds: group(kind),
             clv: { n: closes.length, beat, avg: closes.length ? closes.reduce((a, c) => a + c.v, 0) / closes.length : null,
                    ours: closes.filter((c) => c.from === "ours").length, rows: closes },
             asked: settled.filter((b) => b.sport && b.date && b.desc && (b.close == null || b.close === "")).length };
  }

  // ---- drawing ------------------------------------------------------------
  const esc = (s) => (typeof escapeHtml === "function" ? escapeHtml(String(s == null ? "" : s))
    : String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const mark = (abbr, sport) => (typeof teamMark === "function" ? teamMark(abbr, 26, null, sport) : "");
  const sportNow = () => (typeof state !== "undefined" && state ? state.sport : "") || "";
  const board = () => (typeof state !== "undefined" && state && state.data) || null;

  /* A calculator card: its title, its one-line purpose, its inputs and the
     box its numbers land in. */
  function calcCard(id, title, sub, inputs) {
    return `<section class="xt-card" data-calc="${id}">
      <header class="xt-card-h"><h3>${title}</h3><p>${sub}</p></header>
      <div class="xt-in">${inputs}</div>
      <div class="xt-out" aria-live="polite"></div>
    </section>`;
  }
  const field = (label, name, value, extra = "") =>
    `<label class="xt-f"><span>${label}</span><input data-xc="${name}" inputmode="decimal" value="${esc(value)}" ${extra}></label>`;

  function calculatorsHTML() {
    const roll = (typeof state !== "undefined" && state && state.bankroll) || 1000;
    return `<div class="xt-grid">
      ${calcCard("conv", "Odds converter", "One price, every way it is written.",
        field("Price", "conv-in", "-110", 'placeholder="−110, 2.50 or 45%"'))}
      ${calcCard("vig", "No-vig and hold", "Every side of one market. What the book keeps, and each side’s fair chance with it taken out.",
        `${field("Side 1", "vig-1", "-115")}${field("Side 2", "vig-2", "-105")}${field("Side 3", "vig-3", "", 'placeholder="optional"')}${field("Side 4", "vig-4", "", 'placeholder="optional"')}`)}
      ${calcCard("parlay", "Parlay", "Up to six legs. What it pays and what the prices say it hits; add your own chances to see its value.",
        [1, 2, 3, 4, 5, 6].map((i) => `<div class="xt-leg">${field(`Leg ${i}`, `pl-o${i}`, i < 3 ? "-110" : "", i > 2 ? 'placeholder="odds"' : "")}${field("Your %", `pl-p${i}`, "", 'placeholder="—"')}</div>`).join(""))}
      ${calcCard("kelly", "Kelly stake", "How much of a bankroll a bet earns at your chance — usually less than it feels like, and sometimes nothing.",
        `${field("Your chance %", "ky-p", "55")}${field("Price", "ky-o", "-110")}${field("Bankroll $", "ky-r", String(roll))}
         <label class="xt-f"><span>Fraction</span><select data-xc="ky-f"><option value="1">Full</option><option value="0.5">Half</option><option value="0.25" selected>Quarter</option><option value="0.1">Tenth</option></select></label>`)}
      ${calcCard("ev", "Break-even and value", "What a price needs to hit, and what it is worth at your chance.",
        `${field("Price", "ev-o", "+150")}${field("Your chance %", "ev-p", "42")}${field("Stake $", "ev-s", "100")}`)}
    </div>`;
  }

  const val = (box, k) => {
    const el = box.querySelector(`[data-xc="${k}"]`);
    return el ? String(el.value || "").trim() : "";
  };
  const num = (s) => { const n = Number(String(s).replace("−", "-").replace(/[%$,\s]/g, "")); return Number.isFinite(n) && String(s).trim() !== "" ? n : null; };
  const stat = (k, v, tone = "") => `<div class="xt-stat${tone ? ` ${tone}` : ""}"><span>${k}</span><b>${v}</b></div>`;

  /* Each calculator's numbers, from its own inputs. */
  const CALC = {
    conv(box) {
      const raw = val(box, "conv-in");
      const s = raw.replace("−", "-");
      let d = null;
      if (/%$/.test(s)) { const p = num(s) / 100; if (p > 0 && p < 1) d = 1 / p; }
      else if (/^[+-]?\d{3,}$/.test(s)) d = dec(s);
      else { const n = num(s); if (n != null && n > 1 && n < 100) d = n; else if (n != null) d = dec(n); }
      if (!d) return `<p class="xt-hint">Type an American price (−110, +250), a decimal (2.50) or a chance (45%).</p>`;
      const am = decToAm(d);
      return `<div class="xt-stats">${stat("American", amTxt(am))}${stat("Decimal", d.toFixed(3))}${stat("Implied chance", pctTxt(1 / d))}
        ${stat("$100 returns", money(100 * d))}</div>`;
    },
    vig(box) {
      const prices = [1, 2, 3, 4].map((i) => val(box, `vig-${i}`)).filter((s) => s !== "");
      const r = noVig(prices);
      if (!r) return `<p class="xt-hint">Type at least two sides as American prices.</p>`;
      const tone = r.hold <= 0 ? "good" : r.hold <= 0.03 ? "good" : r.hold <= 0.06 ? "warn" : "bad";
      const word = r.hold <= 0 ? "Under 100% — the sides disagree enough to lock a margin across books."
        : r.hold <= 0.03 ? "A low-hold market: cheap to bet." : r.hold <= 0.06 ? "Ordinary main-line juice."
        : "Prop-level juice: you need a real edge just to break even.";
      return `<div class="xt-stats">${stat("Adds up to", pctTxt(r.overround))}${stat("Book’s hold", pctTxt(r.hold, 2), tone)}</div>
        <p class="xt-note">${word}</p>
        <table class="xt-tbl"><thead><tr><th>Side</th><th>Price</th><th>Implied</th><th>Fair</th><th>Fair price</th></tr></thead><tbody>
        ${prices.map((p, i) => `<tr><td>${i + 1}</td><td>${amTxt(Math.round(num(p)))}</td><td>${pctTxt(r.implied[i])}</td>
          <td><b>${pctTxt(r.mult[i])}</b><small>${pctTxt(r.power[i])} power</small></td><td>${amTxt(toAm(r.mult[i]))}</td></tr>`).join("")}
        </tbody></table>`;
    },
    parlay(box) {
      const legs = [1, 2, 3, 4, 5, 6].map((i) => ({ odds: val(box, `pl-o${i}`), p: (num(val(box, `pl-p${i}`)) || 0) / 100 }))
        .filter((l) => l.odds !== "");
      const r = parlay(legs);
      if (!r) return `<p class="xt-hint">Type at least two legs’ prices.</p>`;
      const noVigEach = r.priced / Math.pow(1.0476, r.legs);
      return `<div class="xt-stats">${stat("Pays", amTxt(r.american))}${stat("$10 returns", money(10 * r.dec))}
          ${stat("Prices say it hits", pctTxt(r.priced))}${r.mine == null ? "" : stat("You say it hits", pctTxt(r.mine), r.ev >= 0 ? "good" : "bad")}</div>
        ${r.ev == null
          ? `<p class="xt-note">With a standard two-way hold taken out of each leg it is worth about ${pctTxt(noVigEach)} — the hold compounds on every leg you add. Add your own chances to see its value.</p>`
          : `<p class="xt-note">At your chances the ticket is worth <b class="${r.ev >= 0 ? "pos" : "neg"}">${ptsTxt(r.ev)}%</b> per dollar.</p>`}
        <p class="xt-fine">Legs are treated as independent. Two legs from one game are not — a quarterback’s yards and his receiver’s move together — which is why books price same-game parlays on their own.</p>`;
    },
    kelly(box) {
      const r = kelly((num(val(box, "ky-p")) || 0) / 100, val(box, "ky-o"), Number(val(box, "ky-f")) || 0.25, num(val(box, "ky-r")) || 0);
      if (!r) return `<p class="xt-hint">Type your chance (1–99%) and a price.</p>`;
      if (r.full <= 0) {
        return `<p class="xt-note"><b class="neg">No bet.</b> This price needs ${pctTxt(r.need)} and you give it ${pctTxt((num(val(box, "ky-p")) || 0) / 100)}. Kelly’s stake for a bet with no edge is zero.</p>`;
      }
      return `<div class="xt-stats">${stat("Value", `${ptsTxt(r.ev)}%`, "good")}${stat("Full Kelly", pctTxt(r.full, 2))}
        ${stat("Your stake", pctTxt(r.stake, 2))}${r.dollars == null ? "" : stat("In dollars", money(r.dollars))}</div>
        <p class="xt-fine">Full Kelly assumes your chance is exactly right, and it never is — a quarter to a tenth keeps most of the growth and far less of the swing.</p>`;
    },
    ev(box) {
      const d = dec(val(box, "ev-o"));
      if (!d) return `<p class="xt-hint">Type a price.</p>`;
      const p = (num(val(box, "ev-p")) || 0) / 100, s = num(val(box, "ev-s")) || 100;
      const ev = p > 0 && p < 1 ? p * d - 1 : null;
      return `<div class="xt-stats">${stat("Needs to hit", pctTxt(1 / d))}${stat("Wins", money(s * (d - 1)))}
        ${ev == null ? "" : stat("Worth", `${ev >= 0 ? "+" : "−"}${money(s * Math.abs(ev))}`, ev >= 0 ? "good" : "bad")}</div>
        ${ev == null ? "" : `<p class="xt-note">At ${pctTxt(p)} the bet ${ev >= 0 ? "earns" : "loses"} ${pctTxt(Math.abs(ev))} of the stake on average${ev >= 0 ? "" : " — the price wants more than you give it"}.</p>`}`;
    },
  };
  function calc(box) {
    const f = CALC[box.dataset.calc];
    const out = box.querySelector(".xt-out");
    if (f && out) out.innerHTML = f(box);
  }

  /* The college upset meter, from the college board in hand. */
  function upsetsHTML(d) {
    const rows = upsets((d && d.game_bets) || []);
    const head = `<header class="xt-card-h"><h3>Upset meter</h3><p>Every college underdog on the board, ranked by
      our chance he wins outright, beside the chance the market’s price gives him with the hold taken out.</p></header>`;
    if (!rows.length) {
      const locked = d && d.locked && d.locked.game_bets;
      return `<section class="xt-card xt-wide">${head}<p class="xt-hint">${locked
        ? `The meter reads the board’s college game cards, which come with a membership — <a href="#paywall">see the plans</a>.`
        : "No college moneylines on the board yet — the meter fills when the week’s prices post."}</p></section>`;
    }
    const li = rows.slice(0, 25).map((r) => {
      const [tone, word] = upsetTier(r);
      return `<li class="xt-up t-${tone}">
        <div class="xt-up-t">${mark(r.dog, "cfb")}<div><b>${esc(r.dog)}</b><span>${r.dogHome ? "vs" : "at"} ${esc(r.fav)} · ${amTxt(r.price)}</span></div>
          <em class="xt-pill t-${tone}">${word}</em></div>
        <div class="xt-meter" role="img" aria-label="Our chance ${pctTxt(r.ours, 0)}, market ${pctTxt(r.market, 0)}">
          <i style="width:${(r.ours * 100).toFixed(1)}%"></i><u style="left:${(r.market * 100).toFixed(1)}%"></u></div>
        <div class="xt-up-n"><span>Ours <b>${pctTxt(r.ours, 0)}</b></span><span>Market <b>${pctTxt(r.market, 0)}</b></span>
          <span class="${r.gap >= 0 ? "pos" : "neg"}">${ptsTxt(r.gap)} pts</span></div>
      </li>`;
    }).join("");
    return `<section class="xt-card xt-wide">${head}<ul class="xt-ups">${li}</ul>
      <p class="xt-fine">Context, not a pick. College game cards are priced from our ratings and shown, never staked, and the
      meter is that same published number — it moves nothing on the board. The fill is ours; the tick is the market’s.</p></section>`;
  }

  // ---- basketball: tonight's schedule spots, and what if he sits ---------
  /* A spot's words, from the build's flags (engine/nba/schedspots). Tone:
     "bad" for the ones the minutes model already reads as a cost, "warn"
     for the context that moves nothing. */
  function spotChips(t) {
    const out = [];
    for (const f of t.flags || []) {
      if (f === "b2b_home") out.push(["bad", "Back-to-back"]);
      else if (f === "3in4") out.push(["bad", "3 in 4 nights"]);
      else if (f === "4in6_road") out.push(["bad", "4 in 6 nights"]);
      else if (f === "long_trip") out.push(["warn", `${Number(t.miles || 0).toLocaleString("en-US")} mi from ${t.from}`]);
      else if (f === "clock") out.push(["warn", `Clock ${t.tz_shift > 0 ? "+" : "−"}${Math.abs(t.tz_shift)} h`]);
      else if (f === "altitude") out.push(["warn", "Up to altitude"]);
      else if (f === "blowout") out.push(["warn", "Blowout watch"]);
    }
    return out;
  }
  function spotsHTML(d) {
    const sport = sportNow();
    const rows = ((d && d.schedule_spots) || []).slice()
      .sort((a, b) => spotChips(b.teams.home).length + spotChips(b.teams.away).length
                    - spotChips(a.teams.home).length - spotChips(a.teams.away).length);
    const head = `<header class="xt-card-h"><h3>Schedule spots</h3><p>Tonight’s games, each side’s rest, the trip
      from its last arena, the clock it crossed, the altitude and the blowout watch.</p></header>`;
    if (!rows.length) {
      return `<section class="xt-card xt-wide">${head}<p class="xt-hint">No games on the board tonight — the spots fill with the slate.</p></section>`;
    }
    const side = (t) => `<div class="xt-sp-t">${mark(t.team, sport)}<b>${esc(t.team)}</b><span>${esc(t.rest_word || "")}</span>
      <span class="xt-chips">${spotChips(t).map(([tone, w]) => `<em class="xt-chip t-${tone}">${esc(w)}</em>`).join("")}</span></div>`;
    const li = rows.map((g) => `<li class="xt-sp">
      <div class="xt-sp-h"><b>${esc(g.away)} @ ${esc(g.home)}</b><span>${esc(g.arena || "")}${g.feet != null ? ` · ${Number(g.feet).toLocaleString("en-US")} ft` : ""}</span>
        ${g.spread != null ? `<span>${esc(g.home)} ${g.spread > 0 ? "+" : g.spread < 0 ? "−" : ""}${Math.abs(g.spread)}</span>` : ""}</div>
      ${side(g.teams.away)}${side(g.teams.home)}</li>`).join("");
    return `<section class="xt-card xt-wide">${head}<ul class="xt-sps">${li}</ul>
      <p class="xt-fine">Context, not a price. The minutes model already reads the rest it was fitted on (rested, a day
      off, the back-to-back); the trip, the clock, the altitude and the blowout watch move nothing until a measurement
      says they should.</p></section>`;
  }

  const WI_STATS = [["min", "Minutes"], ["pts", "Points"], ["reb", "Rebounds"], ["ast", "Assists"]];
  function whatifHTML(d) {
    const sport = sportNow();
    const tonight = [...new Set(((d && d.schedule_spots) || (d && d.games) || []).flatMap((g) => [g.away, g.home]).filter(Boolean))];
    const every = typeof teamsForSport === "function" ? Object.keys(teamsForSport(sport) || {}) : [];
    const teams = tonight.length ? tonight : every;
    return `<section class="xt-card xt-wide" data-xw-league="${esc(sport)}">
      <header class="xt-card-h"><h3>What if he sits</h3><p>Pick a club and a man in its rotation: in the games he missed for
        this club, how each teammate’s share of the minutes, points, rebounds and assists moved against the games he played.</p></header>
      <div class="xt-in">
        <label class="xt-f"><span>${tonight.length ? "Tonight’s clubs" : "Club"}</span><select data-xw="team"><option value="">Pick a club</option>${
          teams.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}</select></label>
        <label class="xt-f"><span>If this man sits</span><select data-xw="player" disabled><option value="">Pick a club first</option></select></label>
      </div>
      <div class="xt-wi-out" aria-live="polite"></div>
      <p class="xt-fine">Evidence only: the board’s numbers do not move for it. A share is of the team’s total that night,
        so pace cancels; a game he missed is read from the box score, not a report; his games before he joined the club
        don’t count as sitting.</p>
    </section>`;
  }
  function whatifOut(r, stat) {
    if (!r || r.error) return `<p class="xt-hint">${esc((r && r.error) || "Nothing came back.")}</p>`;
    const s = (r.stats || {})[stat];
    if (!s) return "";
    const chips = WI_STATS.map(([k, w]) => `<button type="button" class="xt-tab${k === stat ? " on" : ""}" data-xt="wi-stat" data-arg="${k}">${w}</button>`).join("");
    const warn = s.enough ? "" : `<p class="xt-verdict bad">He has missed ${s.n_out} game${s.n_out === 1 ? "" : "s"} for this club since ${esc(r.since || "")} —
      under ${r.floor}, so what follows is the shape, not evidence.</p>`;
    const rows = (s.rows || []).map((x) => `<tr><td>${esc(x.player)}</td><td>${pctTxt(x.with)}</td><td>${pctTxt(x.without)}</td>
      <td class="${x.delta >= 0 ? "pos" : "neg"}">${ptsTxt(x.delta)}</td><td>${x.n_with}/${x.n_without}</td></tr>`).join("");
    return `<div class="xt-tabs">${chips}</div>
      <p class="xt-note">${esc(r.player)}: ${s.n_played} game${s.n_played === 1 ? "" : "s"} played, ${s.n_out} missed for ${esc(r.team)} since ${esc(r.since || "")}.</p>
      ${warn}${rows ? `<table class="xt-tbl"><thead><tr><th>Teammate</th><th>With him</th><th>Without</th><th>±</th><th>Games</th></tr></thead><tbody>${rows}</tbody></table>`
        : `<p class="xt-hint">No teammate played enough games on both sides to compare.</p>`}`;
  }
  async function whatifAsk(box, player) {
    const league = box.dataset.xwLeague, team = (box.querySelector('[data-xw="team"]') || {}).value || "";
    const out = box.querySelector(".xt-wi-out"), sel = box.querySelector('[data-xw="player"]');
    if (!team) return;
    if (out) out.innerHTML = `<p class="xt-hint">Reading the box scores…</p>`;
    try {
      const q = new URLSearchParams({ league, team, ...(player ? { player } : {}) });
      const res = await fetch(`/api/hoops/whatif?${q}`);
      const r = res.ok ? await res.json() : null;
      if (!r) throw new Error("no answer");
      if (!player) {
        sel.innerHTML = `<option value="">Pick a man</option>${(r.rotation || []).map((p) =>
          `<option value="${esc(p.player)}">${esc(p.player)} · ${p.minutes} min</option>`).join("")}`;
        sel.disabled = !(r.rotation || []).length;
        if (out) out.innerHTML = (r.rotation || []).length ? "" : `<p class="xt-hint">No games stored for ${esc(team)} yet.</p>`;
        return;
      }
      box._wi = r;
      if (out) out.innerHTML = whatifOut(r, box._wiStat || "min");
    } catch (e) {
      if (out) out.innerHTML = `<p class="xt-hint">The box scores could not be read just now.</p>`;
    }
  }

  // ---- hockey: the goalie board and the line matchups --------------------
  const SOURCE_WORD = { confirmed: ["good", "Confirmed"], probable: ["warn", "Probable"], "recent starts": ["", "Our guess"] };
  /* Tonight's starting goalies off each game's tape, best goals saved
     above expected first; a goalie with no number yet sorts last. */
  function goalies(d) {
    const out = [];
    for (const g of (d && d.games) || []) {
      const t = g.nhl_tape;
      if (!t || !t.sides) continue;
      for (const [team, opp] of [[g.away, g.home], [g.home, g.away]]) {
        const s = t.sides[team], o = t.sides[opp];
        if (!s || !s.starter) continue;
        out.push({ team, opp, home: team === g.home, goalie: s.starter, sure: !!s.starter_sure,
                   source: s.starter_source || "", sv: s.starter_sv, gsax: s.starter_gsax, share: s.starter_share,
                   b2b: !!s.b2b, faces: o && o.xg != null ? o.xg : null });
      }
    }
    return out.sort((a, b) => (b.gsax == null ? -1e9 : b.gsax) - (a.gsax == null ? -1e9 : a.gsax));
  }
  function goaliesHTML(d) {
    const sport = sportNow();
    const rows = goalies(d);
    const head = `<header class="xt-card-h"><h3>Goalie board</h3><p>Tonight’s starters, best goals saved above expected
      first: whether his club has named him, his save rate, his share of the starts and what the man shooting at him is
      expected to score.</p></header>`;
    if (!rows.length) {
      return `<section class="xt-card xt-wide">${head}<p class="xt-hint">No starters on the board yet — they fill with the slate.</p></section>`;
    }
    const li = rows.map((r) => {
      const [tone, word] = SOURCE_WORD[r.source] || (r.sure ? ["good", "Expected"] : ["", "Unsure"]);
      return `<tr><td><span class="xt-gk">${mark(r.team, sport)}<span><b>${esc(r.goalie)}</b><small>${esc(r.team)} ${r.home ? "vs" : "at"} ${esc(r.opp)}</small></span></span></td>
        <td><em class="xt-chip t-${tone || "none"}">${word}</em>${r.b2b ? ` <em class="xt-chip t-bad">B2B</em>` : ""}</td>
        <td>${r.gsax == null ? "—" : `<b class="${r.gsax >= 0 ? "pos" : "neg"}">${r.gsax > 0 ? "+" : r.gsax < 0 ? "−" : ""}${Math.abs(r.gsax).toFixed(1)}</b>`}</td>
        <td>${r.sv == null ? "—" : Number(r.sv).toFixed(3).replace(/^0/, "")}</td>
        <td>${r.share == null ? "—" : pctTxt(r.share, 0)}</td>
        <td>${r.faces == null ? "—" : Number(r.faces).toFixed(2)}</td></tr>`;
    }).join("");
    return `<section class="xt-card xt-wide">${head}<div class="xt-scroll"><table class="xt-tbl xt-gk-tbl"><thead><tr><th>Goalie</th><th>Named</th>
      <th>GSAx</th><th>Save %</th><th>Starts</th><th>Faces</th></tr></thead><tbody>${li}</tbody></table></div>
      <p class="xt-fine">GSAx: goals saved above what our shot model expected on the shots he faced, over his recent games.
      Save % is regressed toward the league, as the board prices it. “Faces” is the opponent’s expected goals tonight. The
      board already prices every one of these; this lays them side by side.</p></section>`;
  }
  /* One team's units, its forward lines then its pairs, each with its
     on-ice expected goals at even strength. */
  function unitsHTML(team, lines) {
    const row = (u, i, pre) => {
      const n = (u.att_for || 0) + (u.att_against || 0);
      return `<tr><td><b>${pre}${i + 1}</b> <small>${(u.players || []).map((p) => esc(String(p).split(" ").slice(-1)[0])).join(" · ")}</small></td>
        <td>${u.xgf == null ? "—" : Number(u.xgf).toFixed(2)}</td><td>${u.xga == null ? "—" : Number(u.xga).toFixed(2)}</td>
        <td>${u.xgf_pct == null ? "—" : `<b class="${u.xgf_pct >= 0.5 ? "pos" : "neg"}">${pctTxt(u.xgf_pct, 0)}</b>`}</td>
        <td>${u.att_for == null ? "—" : n}</td><td>${u.together == null ? "—" : pctTxt(u.together, 0)}</td></tr>`;
    };
    const f = (lines.forwards || []).map((u, i) => row(u, i, "F")).join("");
    const dd = (lines.defence || []).map((u, i) => row(u, i, "D")).join("");
    return `<div class="xt-split"><h4>${esc(team)}</h4><div class="xt-scroll"><table class="xt-tbl"><thead><tr><th>Unit</th><th>xGF</th><th>xGA</th>
      <th>xGF%</th><th>Att</th><th>Together</th></tr></thead><tbody>${f}${dd}</tbody></table></div></div>`;
  }
  function linesHTML(d) {
    const lines = (d && d.lines) || {};
    const games = ((d && d.games) || []).filter((g) => lines[g.home] || lines[g.away]);
    const head = `<header class="xt-card-h"><h3>Line matchups</h3><p>Each club’s forward lines and defence pairs from the
      shift charts of its newest games, with what each unit’s shots and its opponents’ shots were worth in expected goals
      while all of it was on the ice at even strength.</p></header>`;
    if (!games.length) {
      return `<section class="xt-card xt-wide">${head}<p class="xt-hint">No lines read yet — they fill once a club’s newest games have shift charts.</p></section>`;
    }
    const body = games.map((g) => `<div class="xt-lm"><div class="xt-sp-h"><b>${esc(g.away)} @ ${esc(g.home)}</b></div>
      <div class="xt-splits">${lines[g.away] ? unitsHTML(g.away, lines[g.away]) : ""}${lines[g.home] ? unitsHTML(g.home, lines[g.home]) : ""}</div></div>`).join("");
    return `<section class="xt-card xt-wide">${head}${body}
      <p class="xt-fine">Context only, and small: two games of one line is a handful of attempts, so the attempt count sits
      beside every rate. “Together” is how much of its members’ ice they spent with each other. The home coach gets the last
      change, so who meets whom tonight is his call.</p></section>`;
  }

  // ---- UFC: each fight's path (drawn on the UFC page, under its card) -----
  /* The model's six-way read of a fight (each man by knockout, submission
     or decision; engine/ufc/model `method`, corner a first) beside how each
     man's own stored fights ended (engine/ufc/fightpath `path`) and, where
     the finishes on file allow, the round it ends in (engine/ufc/rounds). */
  const FP_KEYS = [["ko", "KO/TKO"], ["sub", "Sub"], ["dec", "Dec"]];
  function fightPaths(d) {
    const rows = [].concat((d && d.picks) || [], (d && d.pass_list) || []);
    return rows.filter((r) => r && r.method && (r.fighters || []).length === 2).map((r) => {
      const m = r.method, ends = {};
      for (const c of r.market_board || []) {
        const k = c.market === "exact_round" && /round (\d)/i.exec(c.selection || "");
        if (k) ends[k[1]] = c.p_model;
      }
      const side = (i) => {
        const x = i ? "b" : "a", f = r.fighters[i] || {};
        const how = { ko: m[`${x}_ko`] || 0, sub: m[`${x}_sub`] || 0, dec: m[`${x}_dec`] || 0 };
        return { name: f.name || "", record: f.record || "", path: f.path || null, how, win: how.ko + how.sub + how.dec };
      };
      return { fight: r.fight || "", division: String(r.division || "").replace(/_/g, " "), rounds: r.scheduled_rounds || 3,
               a: side(0), b: side(1), distance: m.distance, ends, pick: r.kind === "pick" ? r.pick || "" : "" };
    });
  }
  const fpCount = (o) => FP_KEYS.map(([k, w]) => `${o[k] || 0} ${w}`).join(" · ");
  function fpSide(s, tone) {
    const p = s.path;
    const won = p ? Object.entries(p.won_in || {}).sort((x, y) => x[0] - y[0]).map(([r, n]) => `R${r} ${n}`).join(" · ") : "";
    const last = p ? (p.last || []).map(([res, how, rnd, opp, date]) => `<em class="xt-fp-l t-${res === "W" ? "good" : res === "L" ? "bad" : "none"}"
        title="${esc(`${date} vs ${opp}`)}">${esc(res)}${how ? ` ${esc(how === "KO/TKO" ? "KO" : how)}` : ""}${rnd ? ` R${rnd}` : ""}</em>`).join("") : "";
    return `<div class="xt-fp-s ${tone}"><h4>${esc(s.name)}${s.record ? ` <small>${esc(s.record)}</small>` : ""}</h4>
      <p><span>Our read</span><i><b>${pctTxt(s.win, 0)}</b> to win · ${FP_KEYS.map(([k, w]) => `${w} ${pctTxt(s.how[k], 0)}`).join(" · ")}</i></p>
      ${p ? `<p><span>Last ${p.n}</span><i>Won: ${fpCount(p.wins)}</i></p><p><span></span><i>Lost: ${fpCount(p.losses)}${p.draws ? ` · ${p.draws} drawn or no contest` : ""}</i></p>
        ${won ? `<p><span>His finishes</span><i>${won}</i></p>` : ""}${last ? `<div class="xt-fp-last">${last}</div>` : ""}`
        : `<p class="xt-hint">His fights are not on file yet.</p>`}</div>`;
  }
  function pathsHTML(d) {
    const rows = fightPaths(d);
    const head = `<header class="xt-card-h"><h3>Fight path</h3><p>How each man wins by our read — knockout, submission or
      decision — beside how his own recent fights ended, and when this one ends.</p></header>`;
    if (!rows.length) {
      const locked = d && d.locked && (d.locked.picks || d.locked.pass_list);
      return `<section class="xt-card xt-wide">${head}<p class="xt-hint">${locked
        ? `The paths read the card’s fight reads, which come with a membership — <a href="#paywall">see the plans</a>.`
        : "No fights read on the card yet — the paths fill when the card’s prices post."}</p></section>`;
    }
    const li = rows.map((r) => {
      const segs = [["a", "ko"], ["a", "sub"], ["a", "dec"], ["b", "dec"], ["b", "sub"], ["b", "ko"]]
        .map(([x, k]) => `<i class="xt-fp-${x} k-${k}" style="width:${(100 * (r[x].how[k] || 0)).toFixed(1)}%"></i>`).join("");
      const ends = Object.keys(r.ends).sort().map((k) => `R${k} ${pctTxt(r.ends[k], 0)}`);
      return `<li class="xt-fp">
        <div class="xt-fp-h"><b>${esc(r.fight)}</b><span>${esc([r.division, `${r.rounds} rounds`].filter(Boolean).join(" · "))}</span>${r.pick ? `<em class="xt-pill t-alert">Pick: ${esc(r.pick)}</em>` : ""}</div>
        <div class="xt-fp-bar" role="img" aria-label="${esc(`${r.a.name} ${pctTxt(r.a.win, 0)}, ${r.b.name} ${pctTxt(r.b.win, 0)}`)}">${segs}</div>
        <div class="xt-fp-key"><span class="xt-fp-a">${esc(r.a.name)}: KO · Sub · Dec</span><span class="xt-fp-b">Dec · Sub · KO: ${esc(r.b.name)}</span></div>
        <div class="xt-fp-cols">${fpSide(r.a, "xt-fp-a")}${fpSide(r.b, "xt-fp-b")}</div>
        <p class="xt-fp-end"><span>When it ends</span>${ends.length ? `${ends.join(" · ")} · ` : ""}Distance ${pctTxt(r.distance, 0)}</p>
      </li>`;
    }).join("");
    return `<section class="xt-card xt-wide">${head}<ul class="xt-fps">${li}</ul>
      <p class="xt-fine">Context, not a pick. The read is the card’s own published number (the same one its picks come from) and the
      record is each man’s stored fights, counted — nothing here moves a price. A round appears only where enough finishes are on file.</p></section>`;
  }

  // ---- every book's line, and the steam (the pick page) -------------------
  /* engine/linebooks through /api/lines/books: each book's own quotes on
     this market, minute by minute as the builds saw them, with a mark
     where several books moved the same way inside a few minutes. A step
     line per book; the line itself when any book moved it, otherwise the
     over's price as a chance. A mark, not a signal: nothing reads it. */
  const BK_KEEP = new Map();
  const bkT = (at) => Date.parse(String(at || "").slice(0, 16) + ":00Z");
  const bkTime = (ms) => new Date(ms).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });
  function bookModel(d) {
    const books = Object.entries((d && d.books) || {}).filter(([, p]) => (p || []).length);
    const all = [].concat(...books.map(([, p]) => p));
    if (!all.length) return null;
    const lines = all.map((p) => p.line).filter((v) => v != null);
    const byLine = lines.length && Math.max(...lines) > Math.min(...lines);
    const val = (p) => (byLine ? p.line : implied(p.over));
    const ts = all.map((p) => bkT(p.at)).filter(Number.isFinite);
    const vs = all.map(val).filter((v) => v != null && Number.isFinite(v));
    if (!ts.length || !vs.length) return null;
    return { books, byLine, val, t0: Math.min(...ts), t1: Math.max(...ts), v0: Math.min(...vs), v1: Math.max(...vs) };
  }
  function bookLinesHTML(d) {
    const m = bookModel(d);
    const head = `<div class="section-title">Every book’s line<span class="sub">— each book’s own number on this market as our
      builds saw it, with the steam marked: three or more books moving the same way within ${(d && d.rule && d.rule.minutes) || 15} minutes.</span></div>`;
    if (!m) return `${head}<div class="card xb-card"><p class="xt-hint">No book-by-book history for this market yet. It is kept,
      on every change, for anyone with an open pick or on an injury report.</p></div>`;
    const W = 640, H = 220, L = 46, R = 12, T = 14, B = 26;
    const span = Math.max(1, m.t1 - m.t0), pad = (m.v1 - m.v0) * 0.12 || (m.byLine ? 0.5 : 0.02);
    const lo = m.v0 - pad, hi = m.v1 + pad;
    const x = (t) => L + (W - L - R) * ((t - m.t0) / span), y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    const fmt = (v) => (m.byLine ? String(Math.round(v * 2) / 2) : pctTxt(v, 0));
    const paths = m.books.map(([b, pts], i) => {
      let dd = "";
      pts.forEach((p, j) => {
        const t = bkT(p.at), v = m.val(p);
        if (!Number.isFinite(t) || v == null) return;
        dd += dd ? `H${x(t).toFixed(1)}V${y(v).toFixed(1)}` : `M${x(t).toFixed(1)} ${y(v).toFixed(1)}`;
        if (j === pts.length - 1) dd += `H${x(m.t1).toFixed(1)}`;
      });
      return `<path class="xb-l xb-c${i % 10}" d="${dd}"><title>${esc(b)}</title></path>`;
    }).join("");
    const marks = ((d && d.steam) || []).map((s) => {
      const t = bkT(s.at);
      if (!Number.isFinite(t)) return "";
      const up = s.sign > 0, xx = x(t).toFixed(1);
      return `<g class="xb-steam ${up ? "up" : "dn"}"><line x1="${xx}" x2="${xx}" y1="${T}" y2="${H - B}"/>
        <text x="${xx}" y="${T + 10}" text-anchor="middle">${up ? "▲" : "▼"}</text>
        <title>${esc(`Steam toward the ${up ? "over" : "under"} at ${bkTime(t)}: ${(s.books || []).join(", ")}`)}</title></g>`;
    }).join("");
    const axis = `<text class="xb-ax" x="${L - 6}" y="${y(m.v1).toFixed(1)}" text-anchor="end">${esc(fmt(m.v1))}</text>
      <text class="xb-ax" x="${L - 6}" y="${y(m.v0).toFixed(1)}" text-anchor="end">${esc(fmt(m.v0))}</text>
      <text class="xb-ax" x="${L}" y="${H - 6}">${esc(bkTime(m.t0))}</text>
      <text class="xb-ax" x="${W - R}" y="${H - 6}" text-anchor="end">${esc(bkTime(m.t1))}</text>`;
    const rows = m.books.map(([b, pts], i) => {
      const a = pts[0], z = pts[pts.length - 1];
      const q = (p) => `${p.line == null ? "" : `${p.line} `}${p.over == null ? "" : amTxt(p.over)}`;
      return `<tr><td><i class="xb-key xb-c${i % 10}"></i>${esc(b)}</td><td>${esc(q(a))}</td><td>${esc(q(z))}</td><td>${pts.length - 1}</td></tr>`;
    }).join("");
    const st = (d.steam || []).map((s) => `<li class="${s.sign > 0 ? "up" : "dn"}">${esc(bkTime(bkT(s.at)))} · toward the ${s.sign > 0 ? "over" : "under"}
      · ${esc((s.books || []).join(", "))}${s.kind === "price" ? " (the price)" : " (the line)"}</li>`).join("");
    return `${head}<div class="card xb-card">
      <svg class="xb-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${m.books.length} books, ${m.byLine ? "the line" : "the over's price as a chance"} over time`)}">
        <line class="xb-g" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>${marks}${paths}${axis}</svg>
      <p class="xt-fine">${m.byLine ? "The line each book hung." : "No book moved the line, so this is the over’s price, as a chance."}
        ${(d.more || []).length ? `Also quoting: ${esc(d.more.join(", "))}.` : ""}</p>
      ${st ? `<ul class="xb-st">${st}</ul>` : ""}
      <div class="xt-scroll"><table class="xt-tbl xb-tbl"><thead><tr><th>Book</th><th>First</th><th>Now</th><th>Moves</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="xt-fine">Steam is a mark, not a signal: it has not been scored against results, and nothing on the board reads it.</p></div>`;
  }
  function bookLines(el, sport, player, market) {
    if (!el || !sport || !player || !market) return;
    const key = [sport, player, market].join("|"), hit = BK_KEEP.get(key);
    if (hit && Date.now() - hit.at < 60000) { el.innerHTML = hit.html; return; }
    const q = `/api/lines/books?sport=${encodeURIComponent(sport)}&player=${encodeURIComponent(player)}&market=${encodeURIComponent(market)}`;
    fetch(q).then((r) => (r.status === 401 || r.status === 402 ? { locked: true } : r.ok ? r.json() : null)).then((d) => {
      if (!d) return;
      const html = d.locked ? `<div class="section-title">Every book’s line</div><div class="card xb-card"><p class="xt-hint">Every book’s
        number on this market, and the steam, come with a membership — <a href="#paywall">see the plans</a>.</p></div>` : bookLinesHTML(d);
      BK_KEEP.set(key, { at: Date.now(), html });
      el.innerHTML = html;
    }).catch(() => {});
  }

  /* Each sport's own tools, drawn above the calculators when that sport
     is the one selected. */
  const SPORT_TOOLS = {
    cfb: [upsetsHTML],
    nba: [spotsHTML, whatifHTML],
    wnba: [spotsHTML, whatifHTML],
    nhl: [goaliesHTML, linesHTML],
  };
  const SPORT_NAME = { nfl: "NFL", cfb: "College football", mlb: "MLB", nba: "NBA", wnba: "WNBA", nhl: "NHL", ufc: "UFC" };

  function tools(host) {
    if (!host) return;
    const sport = sportNow();
    const own = (SPORT_TOOLS[sport] || []).map((f) => f(board())).join("");
    host.innerHTML = `${own ? `<h2 class="xt-sec">${esc(SPORT_NAME[sport] || sport.toUpperCase())}</h2><div class="xt-grid">${own}</div>` : ""}
      <h2 class="xt-sec">Every sport · calculators</h2>${calculatorsHTML()}`;
    host.querySelectorAll("[data-calc]").forEach(calc);
  }

  // ---- My Bets' report card ---------------------------------------------
  const CLOSES_KEY = "qb_rc_closes";
  function loadCloses() {
    try { const o = JSON.parse(localStorage.getItem(CLOSES_KEY) || "{}"); return o && typeof o === "object" ? o : {}; }
    catch (e) { return {}; }
  }
  function saveCloses(o) { try { localStorage.setItem(CLOSES_KEY, JSON.stringify(o)); } catch (e) { /* private window */ } }

  const rowHTML = (g, label) => {
    const diff = g.hit - g.need;
    return `<tr><td>${esc(label || g.key)}${g.range ? `<small>${esc(g.range)}</small>` : ""}</td><td>${g.wins}-${g.n - g.wins}</td>
      <td>${pctTxt(g.hit)}</td><td>${pctTxt(g.need)}</td><td class="${diff >= 0 ? "pos" : "neg"}">${ptsTxt(diff)}</td></tr>`;
  };
  const splitTable = (title, groups) => !groups.length ? "" : `<div class="xt-split"><h4>${title}</h4>
    <table class="xt-tbl"><thead><tr><th></th><th>W-L</th><th>Hit</th><th>Needed</th><th>±</th></tr></thead>
    <tbody>${groups.map((g) => rowHTML(g)).join("")}</tbody></table></div>`;

  function reportHTML(bets, ours) {
    const r = report(bets, ours);
    const a = r.all;
    const [tone, word] = r.verdict;
    if (!a.n) {
      return `<section class="xt-rc"><header class="xt-card-h"><h3>Your report card</h3>
        <p>Grade a few bets won or lost and this fills in: your hit rate against what your prices needed, by sport, kind and price, and your closing-line value.</p></header></section>`;
    }
    const pos = a.hit - a.need;
    const c = r.clv;
    const clvBlock = c.n
      ? `<div class="xt-stats">${stat("Bets with a close", String(c.n))}${stat("Beat the close", pctTxt(c.beat / c.n, 0), c.beat / c.n >= 0.5 ? "good" : "bad")}
          ${stat("Average", `${ptsTxt(c.avg)} pts`, c.avg >= 0 ? "good" : "bad")}</div>
         <p class="xt-fine">${c.ours ? `${c.ours} of these closes are ours — the price the market settled at on a pick we published that your bet matched.` : "These are the closes you logged yourself."}
          Beating the close is the earliest honest sign of skill; it shows up long before a win rate can.</p>`
      : `<p class="xt-note">No closes yet. Log a closing price with a bet, or let us look up the ones that match picks we published.</p>`;
    const ask = r.asked
      ? `<button class="xt-btn" type="button" data-xt="rc-closes">Look up our closes</button>
         <p class="xt-fine">Sends the sport, date and description of your ${r.asked} settled bet${r.asked === 1 ? "" : "s"} without a close — never the stake or the book — and we answer only from picks of ours that are already settled. Nothing is kept.</p>`
      : "";
    return `<section class="xt-rc">
      <header class="xt-card-h"><h3>Your report card</h3><p>Graded against the prices you took, not against a coin.</p></header>
      <div class="xt-rc-top">
        <div class="xt-ring ${pos >= 0 ? "good" : "bad"}"><b>${pctTxt(a.hit)}</b><span>hit rate</span></div>
        <div class="xt-stats">${stat("Record", `${a.wins}-${a.n - a.wins}`)}${stat("Prices needed", pctTxt(a.need))}
          ${stat("Above or below", `${ptsTxt(pos)} pts`, pos >= 0 ? "good" : "bad")}${stat("Wins vs expected", `${a.wins} / ${a.exp.toFixed(1)}`)}</div>
      </div>
      <p class="xt-verdict${tone ? ` ${tone}` : ""}">${word}</p>
      <div class="xt-splits">${splitTable("By sport", r.sports)}${splitTable("By kind", r.kinds)}${splitTable("By price", r.bands)}</div>
      <h4 class="xt-sub">Closing-line value</h4>${clvBlock}${ask}<div class="xt-rc-msg" aria-live="polite"></div>
    </section>`;
  }
  function reportCard(host) {
    if (!host || typeof mbLoad !== "function") return;
    host.innerHTML = reportHTML(mbLoad(), loadCloses());
  }
  async function askCloses(btn) {
    const host = btn.closest(".xt-rc") && btn.closest(".xt-rc").parentElement;
    const msg = host && host.querySelector(".xt-rc-msg");
    const bets = (typeof mbLoad === "function" ? mbLoad() : [])
      .filter((b) => ["win", "loss", "push"].includes(b.result) && b.sport && b.date && b.desc && (b.close == null || b.close === ""))
      .slice(0, 300).map((b) => ({ id: b.id, sport: String(b.sport).toLowerCase(), date: b.date, desc: b.desc }));
    btn.disabled = true;
    if (msg) msg.textContent = "Looking…";
    try {
      const res = await fetch("/api/mybets/closes", { method: "POST", headers: { "Content-Type": "application/json" },
                                                       body: JSON.stringify({ bets }) });
      const out = res.ok ? await res.json() : null;
      if (!out) throw new Error("no answer");
      const got = out.closes || {};
      saveCloses(Object.assign(loadCloses(), got));
      reportCard(host);
      const m2 = host.querySelector(".xt-rc-msg");
      const n = Object.keys(got).length;
      if (m2) m2.textContent = n ? `Found ${n} of ${bets.length}.` : "None of these matched a settled pick of ours — the close stays yours to log.";
    } catch (e) {
      btn.disabled = false;
      if (msg) msg.textContent = "Could not reach the record just now. Try again in a minute.";
    }
  }

  // ---- one listener per event -------------------------------------------
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("input", (e) => {
      const t = e.target;
      if (!t || !t.matches || !t.matches("[data-xc]")) return;
      const box = t.closest("[data-calc]");
      if (box) calc(box);
    });
    document.addEventListener("change", (e) => {
      const t = e.target;
      if (!t || !t.matches) return;
      if (t.matches("[data-xw]")) {
        const box = t.closest("[data-xw-league]");
        if (box) whatifAsk(box, t.dataset.xw === "player" ? t.value : "");
        return;
      }
      if (!t.matches("select[data-xc]")) return;
      const box = t.closest("[data-calc]");
      if (box) calc(box);
    });
    document.addEventListener("click", (e) => {
      const t = e.target && e.target.closest && e.target.closest("[data-xt]");
      if (!t) return;
      if (t.dataset.xt === "rc-closes") askCloses(t);
      if (t.dataset.xt === "wi-stat") {
        const box = t.closest("[data-xw-league]");
        if (!box || !box._wi) return;
        box._wiStat = t.dataset.arg;
        box.querySelector(".xt-wi-out").innerHTML = whatifOut(box._wi, box._wiStat);
      }
    });
  }

  window.QBExtras = { tools, reportCard, dec, implied, toAm, decToAm, noVig, parlay, kelly, upsets, upsetTier,
                      report, clv, tally, verdict, calculatorsHTML, upsetsHTML, reportHTML, CALC,
                      spotChips, spotsHTML, whatifHTML, whatifOut, goalies, goaliesHTML, linesHTML, fightPaths, pathsHTML,
                      bookModel, bookLinesHTML, bookLines };
})();
