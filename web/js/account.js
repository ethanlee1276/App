/* THE ACCOUNT PAGES — loaded the first time one of them opens (app.js loadRoom,
   2026-10-24): the Account page and its settings, the plans and the wall, billing, My Bets, messages and
   threads, the Discord page and the streak board.
   A classic script like app.js: it shares the page's globals, and each
   page's renderer here replaces app.js's stub of the same name. Every
   declaration was moved whole out of app.js, in order, with its own
   comments: nothing outside these pages calls any of it (chosen by
   TypeScript's own reading of the file, and checked by name against every
   other script and page). */
const MYBETS_BOOKS = ["DraftKings", "FanDuel", "BetMGM", "Caesars",
                      "ESPN BET", "Fanatics", "bet365", "Other"];

function mbStats(bets) {
  const settled = bets.filter((b) => ["win", "loss", "push"].includes(b.result));
  const staked = settled.reduce((s, b) => s + (Number(b.stake) || 0), 0);
  const profit = settled.reduce((s, b) => s + mbProfit(b), 0);
  const wins = settled.filter((b) => b.result === "win").length;
  const losses = settled.filter((b) => b.result === "loss").length;
  const pushes = settled.filter((b) => b.result === "push").length;
  const pending = bets.length - settled.length;
  const atRisk = bets.filter((b) => b.result === "pending")
    .reduce((s, b) => s + (Number(b.stake) || 0), 0);
  return { n: bets.length, settled: settled.length, pending, wins, losses,
           pushes, staked, profit, atRisk,
           roi: staked > 0 ? profit / staked : null,
           winPct: (wins + losses) > 0 ? wins / (wins + losses) : null };
}

function mbByBook(bets) {
  const books = {};
  for (const b of bets) {
    const k = b.book || "Other";
    const s = books[k] || (books[k] = { staked: 0, profit: 0, n: 0, pending: 0 });
    s.n += 1;
    if (b.result === "pending") { s.pending += 1; continue; }
    s.staked += Number(b.stake) || 0;
    s.profit += mbProfit(b);
  }
  return books;
}

/* ---- Account health, from YOUR log (audit O12, roadmap #43). --------
   The Record page scores the site's own journal per book; this is the
   same score run over the bets YOU logged, in this browser, per book.
   No sportsbook login and no scraping (docs/COMPETITIVE_RECIPE.md marks
   account sync WON'T): the inputs are the rows on this page and nothing
   leaves the device. The weights, the bands, the five-bet floor and the
   wording of the drivers are ledger.account_health's, so the two scores
   mean the same thing; tests/test_your_own_account_health.py runs both
   on one set of bets and holds them equal.

   Two things differ because your log differs. A logged bet has a
   description, not a market column, so the market is READ from the
   words (mbMarket) and a bet it cannot read is counted, not guessed.
   And a logged bet has no closing line unless you gave one (a "close"
   column in a CSV import), so the close-beating signal is scored at
   the neutral half the ledger uses when it has no closes, and the card
   says it is missing rather than implying it was measured. */
const MB_HEALTH_MIN = 5;
const MB_HEALTH_W = { clv: 40, conc: 20, mix: 15, stakes: 13, vol: 12 };
/* The same four signals ledger.HEALTH_BLIND_SPOTS names, said to the
   reader about their own log. */
const MB_HEALTH_BLIND = [
  ["Bet timing after a line move",
   "your log has the day you bet, not the minute against the line’s path"],
  ["Promo and free-bet behavior", "not tracked; this page takes no money"],
  ["Funding pattern (money in and out)", "same — no account is linked, by design"],
  ["Device, IP and browser fingerprint",
   "deliberately out of scope: watching these is how you’d be tempted to "
   + "spoof them, and that is account fraud rather than bankroll management"],
];

/* Did this bet beat its close? Only when the row carries a closing price.
   Positive = you took a better price than the market settled at, in
   implied-probability points (the close's minus yours). */
function mbBetClv(b) {
  if (b == null || b.close == null || b.close === "") return null;
  const mine = mbDecimal(b.odds), close = mbDecimal(b.close);
  if (mine == null || close == null) return null;
  return 1 / close - 1 / mine;
}

function mbHealth(bets) {
  const settled = (bets || []).filter((b) => ["win", "loss", "push"].includes(b.result));
  const byBook = {};
  for (const b of settled) (byBook[b.book || "Other"] = byBook[b.book || "Other"] || []).push(b);
  const W = MB_HEALTH_W, out = [];
  let closes = 0;
  for (const [book, rows] of Object.entries(byBook)) {
    if (rows.length < MB_HEALTH_MIN) continue;
    const clvs = rows.map(mbBetClv).filter((c) => c != null);
    closes += clvs.length;
    const beat = clvs.length ? clvs.filter((c) => c > 0).length / clvs.length : null;
    const clvPts = (beat == null ? 0.5 : beat) * W.clv;
    // Read the markets. Unreadable bets are counted and left out of the
    // two mix signals; with none readable those score the neutral half,
    // never zero — a log the page cannot read is not a clean one.
    const read = rows.map((b) => mbMarket(b.desc)).filter(Boolean);
    const mkts = {};
    for (const m of read) mkts[m.market] = (mkts[m.market] || 0) + 1;
    const top = Object.entries(mkts).sort((a, b) => b[1] - a[1])[0] || null;
    const conc = read.length ? top[1] / read.length : null;
    const propShare = read.length ? read.filter((m) => m.prop).length / read.length : null;
    const concPts = (conc == null ? 0.5 : conc) * W.conc;
    const mixPts = (propShare == null ? 0.5 : propShare) * W.mix;
    const staked = rows.map((b) => Number(b.stake)).filter((s) => s);
    const sharp = staked.length
      ? staked.filter((s) => Math.abs(s / 5 - Math.round(s / 5)) > 1e-9).length / staked.length : 0;
    const stakePts = sharp * W.stakes;
    const volPts = Math.min(rows.length / 100, 1) * W.vol;
    const score = Math.round(clvPts + concPts + mixPts + stakePts + volPts);
    const band = score < 35 ? "low" : score <= 65 ? "moderate" : "elevated";
    const pct = (v) => `${Math.round(v * 100)}%`;
    const drivers = [];
    if (beat != null) {
      drivers.push(`beats the close on ${pct(beat)} of the bets you logged a close for`
        + (beat >= 0.55 ? " — the #1 pattern risk desks act on" : ""));
    }
    if (top) drivers.push(`${pct(conc)} of volume is ${top[0]}`);
    if (propShare != null && propShare >= 0.8) {
      drivers.push(`${pct(propShare)} of volume is player props — the lowest-limit `
        + "markets on the board, and where limiting starts before it spreads");
    } else if (propShare != null && propShare <= 0.4) {
      drivers.push(`${pct(1 - propShare)} of volume is main lines, which is the `
        + "deepest, most tolerant part of the book");
    }
    if (sharp > 0.5) drivers.push("stakes are precise amounts, not round numbers");
    const actions = [];
    if (conc != null && conc >= 0.5) {
      actions.push(`mix in main-line bets (sides/totals) so ${top[0]} isn’t ${pct(conc)} of your volume here`);
    } else if (propShare != null && propShare >= 0.8) {
      actions.push("add sides and totals — spread across many prop markets still "
        + "reads as an all-props account, and main lines are where a book has room to take you on");
    }
    if (sharp > 0.5) {
      actions.push("round stakes to the nearest $5 — precision costs almost nothing in EV and reads recreational");
    }
    if (Object.keys(byBook).length === 1) {
      actions.push("open a second book and split volume — one outlet is a single point of failure");
    }
    if (score > 65) {
      actions.push("route your most limit-prone plays (props with big CLV) to the book you care least about keeping");
    }
    out.push({ book, bets: rows.length, score, band,
               beat_close_rate: beat == null ? null : Math.round(beat * 1000) / 1000,
               top_market: top ? top[0] : null,
               concentration: conc == null ? null : Math.round(conc * 1000) / 1000,
               prop_share: propShare == null ? null : Math.round(propShare * 1000) / 1000,
               sharp_stake_rate: Math.round(sharp * 1000) / 1000,
               unread: rows.length - read.length, drivers, actions });
  }
  out.sort((a, b) => b.score - a.score);
  const blind = MB_HEALTH_BLIND.map(([signal, why]) => ({ signal, why }));
  if (!closes) {
    blind.unshift({ signal: "Beating the closing line",
      why: "your log has no closing prices, so the strongest signal is scored at "
        + "a neutral half; import a CSV with a close column to measure it" });
  }
  return { books: out, blind_spots: blind, closes,
           short: Object.keys(byBook).filter((k) => byBook[k].length < MB_HEALTH_MIN).length };
}

function mbHealthHTML(bets) {
  const h = mbHealth(bets);
  const head = `<div class="section-title">Account health
      <span class="sub">— how limit-prone your own logged betting looks at each book,
      scored the way the Record page scores ours. Computed on this device from
      the bets above; no login, nothing uploaded.</span></div>`;
  if (!h.books.length) {
    return `${head}<p class="list-note">Appears once a book has ${MB_HEALTH_MIN} settled bets
      in your log.</p>`;
  }
  const cards = h.books.map((b) => `
    <div class="card mbh-card">
      <div class="mbh-top"><strong>${escapeHtml(b.book)}</strong>
        <span class="mbh-score ${b.band}">${b.score}</span>
        <span class="chip mbh-band ${b.band}">${b.band} limit risk</span></div>
      <div class="mbh-facts">${plural(b.bets, "settled bet")} · beats the close ${
        b.beat_close_rate == null ? "—" : Math.round(b.beat_close_rate * 100) + "%"}${
        b.top_market ? ` · ${Math.round(b.concentration * 100)}% in ${escapeHtml(b.top_market)}` : ""}${
        b.prop_share == null ? "" : ` · ${Math.round(b.prop_share * 100)}% props`}${
        b.unread ? ` · ${plural(b.unread, "bet")} we couldn’t read a market from` : ""}</div>
      ${b.drivers.length ? `<ul class="mbh-list">${b.drivers.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
      ${b.actions.length ? `<div class="mbh-act"><b>To stay welcome:</b>
        <ul class="mbh-list">${b.actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
    </div>`).join("");
  return `${head}<div class="mbh-grid">${cards}</div>
    <p class="list-note">Inferred from the bets you logged — an estimate of how your
      action could look to a risk desk, not knowledge of any sportsbook’s rules or
      of your account.${h.short ? ` ${plural(h.short, "book")} with fewer than
      ${MB_HEALTH_MIN} settled bets ${h.short === 1 ? "is" : "are"} not scored.` : ""}</p>
    <details class="mbh-blind"><summary>What this score can’t see — and why</summary>
      <ul class="mbh-list">${h.blind_spots.map((s) => `<li><strong>${escapeHtml(s.signal)}</strong>
        — ${escapeHtml(s.why)}</li>`).join("")}</ul></details>`;
}

/* ---- The insights layer: what your own book says about you. --------
   Realized results only, grouped where the sample is real. This is the
   half of a bet tracker that actually changes behavior — the list
   remembers, the groups accuse. */

/* American odds cluster into four habits. +100 is a coin flip priced
   even, so it opens the dogs. */
const MB_BAND_ORDER = ["Heavy favorites", "Favorites", "Small dogs",
                       "Longshots"];
function mbBand(odds) {
  const o = Number(odds);
  if (!o || isNaN(o)) return null;
  if (o <= -200) return "Heavy favorites";
  if (o < 0) return "Favorites";
  if (o < 200) return "Small dogs";
  return "Longshots";
}

/* Settled-only rollup by any labeller. Pushes ride in staked/profit
   (they cost nothing, they decide nothing) but not in the record. */
function mbGroup(bets, keyFn) {
  const out = {};
  for (const b of bets) {
    if (!["win", "loss", "push"].includes(b.result)) continue;
    const k = keyFn(b);
    if (!k) continue;
    const s = out[k] || (out[k] = { n: 0, wins: 0, losses: 0,
                                    staked: 0, profit: 0 });
    s.n += 1;
    if (b.result === "win") s.wins += 1;
    else if (b.result === "loss") s.losses += 1;
    s.staked += Number(b.stake) || 0;
    s.profit += mbProfit(b);
  }
  return out;
}

/* Cumulative P&L in date order — the bankroll curve. */
function mbCurve(bets) {
  const settled = bets.filter((b) =>
    ["win", "loss", "push"].includes(b.result))
    .slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  let run = 0;
  return settled.map((b) => ({ date: b.date || "",
                               pnl: (run += mbProfit(b)) }));
}

/* One-line reads, each gated on a real sample so the page never
   accuses a habit off six bets. At most three — a wall of verdicts
   reads like a horoscope. */
const MB_READ_MIN = 10;
function mbTakeaways(bets) {
  const takes = [];
  const dec = (s) => s.wins + s.losses;
  const bands = mbGroup(bets, (b) => mbBand(b.odds));
  let leak = null;
  for (const k of Object.keys(bands)) {
    const s = bands[k];
    if (dec(s) < MB_READ_MIN || s.staked <= 0) continue;
    const roi = s.profit / s.staked;
    if (roi < -0.10 && (!leak || roi < leak.roi)) leak = { k, s, roi };
  }
  if (leak) takes.push(`${leak.k} are the leak: `
    + `${mbMoney(leak.s.profit, true)} on ${mbMoney(leak.s.staked)} staked `
    + `(−${Math.abs(100 * leak.roi).toFixed(0)}% ROI).`);
  const sports = mbGroup(bets, (b) => b.sport || null);
  let carry = null;
  for (const k of Object.keys(sports)) {
    const s = sports[k];
    if (dec(s) < MB_READ_MIN || s.staked <= 0) continue;
    const roi = s.profit / s.staked;
    if (roi > 0.05 && (!carry || roi > carry.roi)) carry = { k, s, roi };
  }
  if (carry) takes.push(`${carry.k} is carrying you: `
    + `${mbMoney(carry.s.profit, true)} at +${(100 * carry.roi).toFixed(0)}% ROI.`);
  // Flat-stake break-even at YOUR average odds vs the rate you hit.
  const decided = bets.filter((b) => b.result === "win" || b.result === "loss");
  const priced = decided.filter((b) => mbDecimal(b.odds) != null);
  if (priced.length >= 2 * MB_READ_MIN) {
    const be = priced.reduce((s, b) => s + 1 / mbDecimal(b.odds), 0)
      / priced.length;
    const hit = decided.filter((b) => b.result === "win").length
      / decided.length;
    if (hit < be - 0.03) takes.push(`At your average odds you need `
      + `${(100 * be).toFixed(0)}% winners to break even — you’re hitting `
      + `${(100 * hit).toFixed(0)}%.`);
    else if (hit > be + 0.03) takes.push(`You’re beating your break-even: `
      + `${(100 * hit).toFixed(0)}% winners where `
      + `${(100 * be).toFixed(0)}% pays the freight.`);
  }
  const wins = decided.filter((b) => b.result === "win");
  const losses = decided.filter((b) => b.result === "loss");
  if (wins.length >= MB_READ_MIN && losses.length >= MB_READ_MIN) {
    const avg = (a) => a.reduce((s, b) => s + (Number(b.stake) || 0), 0)
      / a.length;
    const wAvg = avg(wins), lAvg = avg(losses);
    if (lAvg > wAvg * 1.25) takes.push(`You bet bigger on your losers — `
      + `${mbMoney(lAvg)} average on losses vs ${mbMoney(wAvg)} on wins.`);
  }
  return takes.slice(0, 3);
}

/* THIS MONTH. Ethan's product audit, 2026-09-23, item 16: My Book as
   a retention engine — "this month" was the one read it named that
   the page did not give (the leak and the market that carries you are
   the takeaways above; the sport and price tables are the best
   markets). One line under your ribbon: this calendar month's record,
   profit and ROI, and last month beside it.
   Grouped on the bet's own date, the day you logged it for. */
function mbMonth(bets, today) {
  const ym = String(today || "").slice(0, 7);
  const [y, m] = ym.split("-").map(Number);
  const prev = new Date(Date.UTC(y, m - 2, 1)).toISOString().slice(0, 7);   // January → last December
  const of = (k) => mbStats((bets || []).filter((b) => String((b || {}).date || "").slice(0, 7) === k));
  return { ym, prev, cur: of(ym), last: of(prev) };
}

function mbMonthName(ym) {
  const [y, m] = String(ym).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 15)).toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
}

function mbMonthHTML(bets, today) {
  const { ym, prev, cur: c, last: l } = mbMonth(bets, today);
  if (!c.n && !l.settled) return "";
  const tone = (v) => v > 0 ? "good" : v < 0 ? "bad" : "";
  const rec = c.settled
    ? `<b>${c.wins}-${c.losses}${c.pushes ? `-${c.pushes}` : ""}</b> · <b class="${tone(c.profit)}">${mbMoney(c.profit, true)}</b>${
        c.roi == null ? "" : ` · ${c.roi >= 0 ? "+" : MINUS}${Math.abs(c.roi * 100).toFixed(1)}% ROI`}`
    : "nothing settled yet";
  // What is still open is the line above's to say ("at risk on …").
  return `<p class="mb-month"><span class="hd-eyebrow">${mbMonthName(ym)}</span> ${rec}${
    l.settled ? `<span class="mb-month-prev">${mbMonthName(prev)} ${mbMoney(l.profit, true)}</span>` : ""}</p>`;
}

function renderMyBets() {
  const host = document.getElementById("mybets-body");
  if (!host) return;
  renderTailFade();
  const acct = acctState();
  setStandaloneSource(acct ? `Account “${acct.name}” — synced through your own server`
                           : "Your device only — nothing is uploaded",
                      acct ? `My Bets · account ${acct.name}`
                           : "My Bets · local to this browser");
  const bets = mbLoad().slice().sort((a, b) =>
    (b.date || "").localeCompare(a.date || "") ||
    (b.id || "").localeCompare(a.id || ""));
  const st = mbStats(bets);
  const books = mbByBook(bets);
  const pcolor = (v) => v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--text-mute)";
  /* v5: YOUR OWN RIBBON. The four stat tiles were the site's old
     vocabulary; the record is a ribbon everywhere else (the deck, the
     Record page, Zeno's page), so it is one here — the same tile, under
     your own label, drawn from your own settled bets: the ring is wins
     over decisions, the number is profit in dollars, the dots are your
     last five. Nothing settled yet, no ribbon; what is at risk is said
     beneath it either way. */
  const ribbon = (() => {
    const recent = bets.filter((b) => ["win", "loss", "push"].includes(b.result)).slice(0, 5)
      .map((b) => ({ result: b.result === "win" ? "won" : b.result === "loss" ? "lost" : "push" }));
    const you = { overall: { settled: st.settled, wins: st.wins, losses: st.losses, pushes: st.pushes,
                             profit: st.profit, staked: st.staked, open: st.pending, roi: st.roi },
                  recent, label: "You · logged by hand" };
    const html = recordRibbonsHTML({ zeno: you }, {}, []);
    return `${html ? `<div class="hd-stats rec-ribbons">${html}</div>` : ""}${
      st.pending ? `<p class="list-note">${mbMoney(st.atRisk)} at risk on ${plural(st.pending, "open bet")}.</p>` : ""}`;
  })();

  const today = new Date().toISOString().slice(0, 10);
  const form = `
    <div class="card mb-form">
      <div class="mb-form-row">
        <label>Book<select id="mb-book">${MYBETS_BOOKS.map((b) =>
          `<option>${escapeHtml(b)}</option>`).join("")}</select></label>
        <label>Sport<select id="mb-sport">${
          ["", "NFL", "CFB", "MLB", "NBA", "WNBA", "UFC", "Other"].map((s) =>
          `<option value="${s}">${s || "—"}</option>`).join("")}</select></label>
        <label>Date<input id="mb-date" type="date" value="${today}"></label>
      </div>
      <div class="mb-form-row">
        <label class="mb-grow">Bet<input id="mb-desc" type="text" maxlength="90"
          placeholder="e.g. Yankees ML, or Judge Over 1.5 total bases"></label>
        <label>Stake $<input id="mb-stake" type="number" min="0" step="0.01"
          inputmode="decimal" placeholder="25"></label>
        <label>Odds<input id="mb-odds" type="number" step="1"
          inputmode="numeric" placeholder="-110"></label>
        <button class="btn primary mb-add" type="button" data-act="mbAdd">Log bet</button>
      </div>
      <div id="mb-form-warn" class="mb-warn"></div>
    </div>`;

  /* THE ROW HAD TO AGREE WITH ITSELF. Ethan, 2026-08-23: "just that
     whole line just looks very cluttered and not good."

     Half of that was the missing `.agate` stylesheet rule. The other
     half was arithmetic: `Bets` counted every bet at the book INCLUDING
     the pending ones, while `Staked`, `Profit` and `ROI` are realized
     figures that skip them. So one open $25 bet at Caesars rendered as
     "1 · $0.00 · $0.00 · —" — a row that looks broken because it is
     quietly describing two different populations at once.

     `Bets` is the settled count now, which is what the other three
     columns are about, and anything still running is named under the
     book rather than folded into a number it does not belong to. A book
     with nothing settled shows dashes instead of $0.00: zero staked
     reads as "bet nothing there", and the truth is "nothing has
     finished". */
  const bookRows = Object.keys(books).sort((a, b) =>
    books[b].profit - books[a].profit).map((k) => {
    const s = books[k];
    const settled = s.n - s.pending;
    return `<tr>
      <td>${escapeHtml(k)}${s.pending
        ? `<span class="agate-sub">${s.pending} open</span>` : ""}</td>
      <td class="num">${settled || "—"}</td>
      <td class="num">${settled ? mbMoney(s.staked) : "—"}</td>
      <td class="num"${settled
        ? ` style="color:${pcolor(s.profit)};font-weight:700"` : ""}>${
        settled ? mbMoney(s.profit, true) : "—"}</td>
      <td class="num">${s.staked > 0 ? (100 * s.profit / s.staked).toFixed(1) + "%" : "—"}</td>
    </tr>`;
  }).join("");

  const resultTag = { win: ["WON", "var(--good)"], loss: ["LOST", "var(--bad)"],
                      push: ["PUSH", "var(--text-mute)"],
                      pending: ["OPEN", "var(--warn)"] };
  const chipTone = { win: "good", loss: "bad", push: "", pending: "warn" };   // v5: the card's pill, the deck's tones
  // Status chips + sport filter (Ethan's My Bets render, 2026-08-11).
  // "Open/Won/Lost" as top-level tabs, sports as a dropdown, and each
  // bet as a card with its stake and what it stands to return.
  const stF = window._mbStatus || "all";
  const spF = window._mbSport || "";
  const sportsSeen = [...new Set(bets.map((b) => b.sport).filter(Boolean))];
  const shown = bets.filter((b) =>
    (stF === "all" || (stF === "open" ? b.result === "pending" : b.result === stF))
    && (!spF || b.sport === spF));
  const chip = (val, label) => `<button class="mbc-chip ${stF === val ? "active" : ""}"
      data-act="mbStatus" data-arg="${val}">${label}</button>`;
  // Render 12 ships the log as a dense TABLE; the cards came from the
  // phone render. Both are the same rows, so this is a view switch
  // rather than a second store — table on a laptop, cards on a phone.
  const vw = window._mbView === "table" ? "table" : "cards";
  const filterBar = bets.length ? `
    <div class="mbc-filters">
      <div class="mbc-chips">${chip("all", "All")}${chip("open", "Open")}${chip("win", "Won")}${chip("loss", "Lost")}${chip("push", "Push")}</div>
      ${sportsSeen.length > 1 ? `<select class="mbc-sport" data-change="mbSport">
        <option value="">All Sports</option>${sportsSeen.map((s) =>
          `<option${s === spF ? " selected" : ""}>${escapeHtml(s)}</option>`).join("")}</select>` : ""}
      <div class="mbc-views">
        <button class="mbc-view${vw === "cards" ? " active" : ""}" type="button"
          data-act="mbView" data-arg="cards">Cards</button>
        <button class="mbc-view${vw === "table" ? " active" : ""}" type="button"
          data-act="mbView" data-arg="table">Table</button>
      </div>
    </div>` : "";
  // What a pending bet stands to return — plain American-odds arithmetic
  // on the user's own stake and price, never a projection.
  const mbToWin = (b) => !b.odds || !b.stake ? 0
    : (b.odds > 0 ? b.stake * b.odds / 100 : b.stake * 100 / Math.abs(b.odds));
  // A saved slip plays its night back (js/extras.js replayInto).
  const replayBtn = (b) => b.src === "slip" && b.result !== "pending" ? `<button class="mb-act" data-xt="replay" data-id="${escapeAttr(b.id || "")}">Replay</button>` : "";
  const card = (b) => {
    const [label, color] = resultTag[b.result] || resultTag.pending;
    const legs = (b.desc || "").includes(" + ") ? (b.desc || "").split(" + ") : null;
    const actions = b.result === "pending"
      ? `<button class="mb-act win" data-act="mbResult" data-arg="${b.id}" data-arg2="win">Win</button>
         <button class="mb-act loss" data-act="mbResult" data-arg="${b.id}" data-arg2="loss">Loss</button>
         <button class="mb-act push" data-act="mbResult" data-arg="${b.id}" data-arg2="push">Push</button>`
      : `<button class="mb-act undo" data-act="mbResult" data-arg="${b.id}" data-arg2="pending">Reopen</button>`;
    const outcome = b.result === "pending"
      ? `To win <b>${mbMoney(mbToWin(b))}</b>`
      : `<b style="color:${pcolor(mbProfit(b))}">${mbMoney(mbProfit(b), true)}</b>`;
    return `<article class="mbc ${b.result === "pending" ? "open" : escapeHtml(b.result)}"
        data-mbid="${escapeAttr(b.id || "")}">
      <div class="mbc-head">
        <span class="mbc-title">${legs ? `${legs.length}-leg parlay` : escapeHtml(b.desc || "")}</span>
        <span class="hd-o">${escapeHtml(oddsTxt(b.odds))}</span>
        <span class="hd-chip ${chipTone[b.result] || "warn"}">${label}</span></div>
      ${legs ? `<ul class="mbc-legs">${legs.map((l) =>
        `<li>${escapeHtml(l)}</li>`).join("")}</ul>` : ""}
      <div class="mbc-sub">${escapeHtml(b.book || "")}${b.sport ? ` · ${escapeHtml(b.sport)}` : ""} · ${escapeHtml(b.date || "")}</div>
      <div class="mbc-foot"><span class="mbc-stake">${mbMoney(b.stake)} staked</span>
        <span class="mbc-outcome">${outcome}</span>
        <span class="mb-actions">${replayBtn(b)}${actions}
          <button class="mb-act del" title="Delete this bet" aria-label="Delete"
            data-act="mbDelete" data-arg="${b.id}">${icon("cross", 12)}</button></span></div>
    </article>`;
  };
  // The same bets as the render's table: date, pick, type, odds, stake,
  // result. "Type" is the shape of the ticket we can actually tell from
  // the row — a parlay has legs joined by " + " — never an invented
  // market label.
  const tableRow = (b) => {
    const [label, color] = resultTag[b.result] || resultTag.pending;
    const legs = (b.desc || "").includes(" + ") ? (b.desc || "").split(" + ") : null;
    const type = legs ? `${legs.length}-leg parlay` : (b.sport || "Single");
    return `<tr data-mbid="${escapeAttr(b.id || "")}">
      <td>${escapeHtml(b.date || "")}</td>
      <td class="mbt-pick">${escapeHtml(b.desc || "")}
        <span class="mbt-book">${escapeHtml(b.book || "")}</span></td>
      <td>${escapeHtml(type)}</td>
      <td class="num">${escapeHtml(oddsTxt(b.odds))}</td>
      <td class="num">${mbMoney(b.stake)}</td>
      <td class="num" style="color:${b.result === "pending" ? "var(--text-mute)" : pcolor(mbProfit(b))}">
        ${b.result === "pending" ? mbMoney(mbToWin(b)) + " to win" : mbMoney(mbProfit(b), true)}</td>
      <td><b style="color:${color}">${label}</b></td>
      <td class="mbt-act">${b.result === "pending"
        ? `<button class="mb-act win" data-act="mbResult" data-arg="${b.id}" data-arg2="win">W</button>
           <button class="mb-act loss" data-act="mbResult" data-arg="${b.id}" data-arg2="loss">L</button>
           <button class="mb-act push" data-act="mbResult" data-arg="${b.id}" data-arg2="push">P</button>`
        : `<button class="mb-act undo" data-act="mbResult" data-arg="${b.id}" data-arg2="pending">Reopen</button>`}${replayBtn(b)}
        <button class="mb-act del" title="Delete this bet" aria-label="Delete"
          data-act="mbDelete" data-arg="${b.id}">${icon("cross", 12)}</button></td>
    </tr>`;
  };
  const betTable = (rows) => `<div class="card mb-table-wrap">
    <table class="agate mb-table"><thead><tr><th>Date</th><th>Pick</th><th>Type</th>
      <th>Odds</th><th>Stake</th><th>Result</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows.map(tableRow).join("")}</tbody></table></div>`;

  host.innerHTML = `
    <div class="card mb-safety">
      <b>No sportsbook passwords, ever.</b> Sportsbooks don’t offer a login for apps, so the
      only way to pull your account automatically would be to store your DraftKings or FanDuel
      password and scrape it — against their terms, and a risk to your account and your money.
      So you log bets here yourself. A <b>Qellys</b> account is a different thing: it is ours,
      you can change or delete it whenever you like, and it is what carries this log to your
      other devices.
    </div>
    ${acctStripHTML()}
    ${form}
    ${ribbon}
    ${mbMonthHTML(bets, today)}
    ${st.settled ? `<div id="mb-report"></div>` : `<div id="mb-risk"></div>`}
    ${(() => {
      if (st.settled < 3) return "";
      const takes = mbTakeaways(bets);
      const curve = mbCurve(bets);
      /* `label` is not decoration. Both of these shipped with an empty
         first <th>, so the column telling you WHAT is being grouped —
         a sport, or a price band — was the one column with no heading.
         Two identical-looking tables stacked with nothing naming either
         is most of why this page read as unfinished. */
      const groupTable = (g, label, order) => {
        const keys = (order || Object.keys(g).sort((a, b) =>
          g[b].profit - g[a].profit)).filter((k) => g[k] && g[k].n);
        if (keys.length < 2) return "";
        return `<div class="card" style="padding:0;overflow-x:auto;margin-bottom:14px">
          <table class="agate"><thead><tr><th>${escapeHtml(label)}</th><th class="num">Bets</th>
            <th class="num">Record</th><th class="num">Staked</th>
            <th class="num">Profit</th><th class="num">ROI</th></tr></thead><tbody>
          ${keys.map((k) => { const s = g[k]; return `<tr>
            <td>${escapeHtml(k)}</td><td class="num">${s.n}</td>
            <td class="num">${s.wins}–${s.losses}</td>
            <td class="num">${mbMoney(s.staked)}</td>
            <td class="num" style="color:${pcolor(s.profit)};font-weight:700">${mbMoney(s.profit, true)}</td>
            <td class="num">${s.staked > 0 ? (100 * s.profit / s.staked).toFixed(1) + "%" : "—"}</td>
          </tr>`; }).join("")}</tbody></table></div>`;
      };
      const last = curve.length ? curve[curve.length - 1].pnl : 0;
      const spark = curve.length >= 2 ? `<div class="card" style="margin-bottom:14px">
        <div class="ffd-h">Bankroll curve</div>
        <div class="gloss-chart" data-gloss-curve="${escapeAttr(JSON.stringify({
          values: curve.map((p) => p.pnl), labels: curve.map((p) => p.date),
          tone: last >= 0 ? "up" : "down", money: true, h: 110,
        }))}">${sparkline(curve.map((p) => p.pnl).reverse(),
          { w: 360, h: 84, line: 0,
            stroke: last >= 0 ? "var(--good)" : "var(--bad)" })}</div>
        <p class="ffd-note" style="margin:4px 0 0">Cumulative P&L over your
          ${curve.length} settled bets, oldest to newest — the flat line is
          break-even.</p></div>` : "";
      return `
        <div class="section-title">What your book says about you
          <span class="sub">— realized results only; the one-line reads wait for
          ${MB_READ_MIN} decided bets in a group before claiming anything.</span></div>
        ${takes.length ? `<div class="card mb-takes"><ul>
          ${takes.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul></div>` : ""}
        ${spark}
        ${groupTable(mbGroup(bets, (b) => b.sport || null), "Sport")}
        ${groupTable(mbGroup(bets, (b) => mbBand(b.odds)), "Price", MB_BAND_ORDER)}`;
    })()}
    ${bets.length ? `
    <div class="section-title">By book
      <span class="sub">— your realized P&L at each sportsbook, best first.
      Counts settled bets only; anything still running is listed under the
      book’s name.</span></div>
    <div class="card" style="padding:0;overflow-x:auto">
      <table class="agate"><thead><tr><th>Book</th><th class="num">Bets</th>
        <th class="num">Staked</th><th class="num">Profit</th>
        <th class="num">ROI</th></tr></thead>
        <tbody>${bookRows}</tbody></table></div>
    ${mbHealthHTML(bets)}
    <div class="section-title">Every bet
      <span class="sub">— newest first. Tap Win/Loss/Push when a bet settles; the totals
      update as you go.</span>
      <span style="float:right;font-size:var(--fs-sm)">
        <button class="btn mb-io" type="button" data-act="mbExport">Export</button>
        <label class="btn mb-io" style="cursor:pointer">Import<input type="file"
          accept="application/json" style="display:none" data-change="mbImport"></label>
      </span></div>
    ${filterBar}
    ${!shown.length
      ? `<p class="rail-quiet" style="margin:4px 0 18px">Nothing matches this filter.</p>`
      : vw === "table" ? betTable(shown)
      : `<div class="mbc-list">${shown.map(card).join("")}</div>`}`
    : `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
        <div class="es-title">No bets logged yet</div>
        <div class="es-sub">Add the first bet you placed at a book above. It stays on this
        device, tracks your P&L by book, and is separate from the model’s own record.</div></div>`}
    <details class="card mb-import">
      <summary>Bulk import — a CSV from your sportsbook, or a Juice Reel export</summary>
      <p class="mb-import-note">The free version of bet syncing: every book (and Juice
      Reel itself) can export your bet history as a spreadsheet/CSV. Choose the file or
      paste the rows — columns are matched by their header names (date, bet, odds,
      stake/risk, result…), in any order. Rows without a book column are filed under the
      Book selected in the form above. Re-importing the same export is safe: bets you
      already logged are skipped, not doubled. Nothing uploads.</p>
      <div class="mb-form-row">
        <label class="btn mb-io" style="cursor:pointer">Choose CSV<input type="file"
          accept=".csv,.txt,.tsv,text/csv,text/plain,text/tab-separated-values"
          style="display:none" data-change="mbBulkFile"></label>
        <span style="color:var(--text-mute);font-size:var(--fs-sm)">or paste rows below,
          then Preview:</span>
      </div>
      <textarea id="mb-bulk-text" rows="4" spellcheck="false"
        placeholder="Date,Bet,Odds,Risk,Result&#10;2026-08-09,Yankees ML,-125,25,Won"></textarea>
      <div class="mb-form-row">
        <button class="btn" type="button" data-act="mbBulkPaste">Preview</button>
      </div>
      <div id="mb-bulk-preview"></div>
    </details>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      This is a manual log for the bets YOU place — not the model’s picks (those are on the
      Record page) and not gambling advice. Data lives only in this browser; clearing your
      browser data erases it, so Export now and then if you want a backup.</p>`;
  sweepRings(host);
  if (typeof mountGlossCharts === "function") mountGlossCharts(host);
  loadExtras().then((X) => X && (st.settled ? X.reportCard(document.getElementById("mb-report")) : X.riskView(document.getElementById("mb-risk"))));
}

/* ============================================================
   THE STREAK — the free daily game (roadmap #4)
   ============================================================
   Pick 3 from a published slate of coin-flip props, win more than you
   lose, keep the flame. The slate file is FREE and carries facts only —
   player, market, line, lock time, graded result. Nothing the model
   thinks appears on this page, which is what lets the page sit outside
   the wall: it is the acquisition feature, not the product.

   Rules live in engine/streak.py and are restated in the fold below;
   the server is the referee (locks, the 3-pick cap, grading) and every
   button here just asks it. */
let _stkSlate = null, _stkSlateAt = 0;
let _stkMe = null;
let _stkLeaders = null, _stkLeadersAt = 0, _stkTonight = 0;

async function stkSlate() {
  if (_stkSlate && Date.now() - _stkSlateAt < 60000) return _stkSlate;
  try {
    const res = await boardFetch("data/streak.json", { cache: "no-cache" });
    if (res.ok) { _stkSlate = await res.json(); _stkSlateAt = Date.now(); }
  } catch (e) { /* keep whatever we had */ }
  return _stkSlate || {};
}

async function stkMe(force) {
  if (_stkMe && !force) return _stkMe;
  try {
    const r = await fetch("/api/streak/me", { credentials: "same-origin" });
    _stkMe = r.ok ? await r.json() : null;
  } catch (e) { _stkMe = null; }
  return _stkMe;
}

async function stkLeaders(force) {
  if (_stkLeaders && !force && Date.now() - _stkLeadersAt < 60000)
    return _stkLeaders;
  try {
    const r = await fetch("/api/streak/leaders", { credentials: "same-origin" });
    if (r.ok) {
      const body = (await r.json()) || {};
      _stkLeaders = body.leaders || [];
      _stkTonight = body.in_tonight || 0;
      _stkLeadersAt = Date.now();
    }
  } catch (e) { /* leaderboard is decoration; the game still works */ }
  return _stkLeaders || [];
}

function stkQuestionRow(q, myPick, locked, signedIn) {
  const line = q.line != null ? String(q.line) : "";
  const graded = q.result === "over" || q.result === "under";
  const verdict = graded && myPick
    ? (myPick === q.result ? "win" : "loss")
    : (q.result === "void" && myPick ? "void" : "");
  const side = (s, word) => {
    const on = myPick === s;
    if (graded || q.result === "void") {
      const hit = q.result === s;
      return `<span class="stk-side done ${hit ? "hit" : ""} ${on ? "mine" : ""}">
        ${word} ${escapeHtml(line)}${on ? " · you" : ""}</span>`;
    }
    if (locked) {
      return `<span class="stk-side done ${on ? "mine" : ""}">${word} ${escapeHtml(line)}${on ? " · you" : ""}</span>`;
    }
    return `<button class="stk-side ${on ? "on" : ""}" data-qid="${escapeHtml(q.qid)}"
      data-side="${s}">${word} ${escapeHtml(line)}</button>`;
  };
  const status = graded
    ? `<span class="stk-res ${verdict}">${
        verdict === "win" ? icon("check") : verdict === "loss" ? icon("cross") : ""}
        ${escapeHtml(q.result)} — ${q.actual != null ? escapeHtml(String(q.actual)) : "final"}</span>`
    : q.result === "void"
      ? `<span class="stk-res">push / no result</span>`
      : locked
        ? `<span class="stk-res">${icon("lock")} locked</span>`
        : `<span class="stk-res">${icon("clock")} locks ${escapeHtml(formatKickoff(q.lock) || "at start")}</span>`;
  return `<div class="stk-q ${verdict}">
    <div class="stk-who">
      <b>${escapeHtml(q.player)}</b>
      <span>${escapeHtml(q.label || q.market)} · ${escapeHtml(q.game || "")}</span>
    </div>
    <div class="stk-sides">${side("over", "Over")}${side("under", "Under")}</div>
    ${status}
  </div>`;
}

async function stkPick(qid, side) {
  try {
    const r = await fetch("/api/streak/pick", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qid, side }),
    });
    const body = await r.json().catch(() => ({}));
    if (r.status === 401) { switchView("account"); return; }
    if (!r.ok) {
      const note = document.getElementById("stk-note");
      if (note) note.textContent = body.error || "That pick didn’t take.";
      return;
    }
    if (_stkMe && _stkSlate) {
      _stkMe.picks = _stkMe.picks || {};
      _stkMe.picks[_stkSlate.date] = body.picks || {};
    }
    renderStreak();
  } catch (e) {
    const note = document.getElementById("stk-note");
    if (note) note.textContent = "Couldn’t reach the server — try again.";
  }
}

async function stkSaveName() {
  const btn = document.getElementById("stk-name-save");
  if (!btn) return;
  try {
    const r = await fetch("/api/streak/name", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: btn.dataset.name || "" }),
    });
    const body = await r.json().catch(() => ({}));
    const note = document.getElementById("stk-note");
    if (!r.ok) {
      if (note) note.textContent = body.error || "That name didn’t take.";
      return;
    }
    if (_stkMe) _stkMe.name = body.name || "";
    stkLeaders(true).then(() => renderStreak());
  } catch (e) { /* the next render retries */ }
}

async function renderStreak() {
  const host = document.getElementById("streak-body");
  if (!host) return;
  const [slate, who] = await Promise.all([stkSlate(), acctWho()]);
  const signedIn = !!(who && who.signed_in);
  const me = signedIn ? await stkMe(true) : null;
  const leadersRows = await stkLeaders();
  if (state.view !== "streak") return;   // navigated away mid-await

  const today = slate.date || "";
  const questions = slate.questions || [];
  const need = slate.picks_required || 3;
  const myToday = (me && me.picks && me.picks[today]) || {};
  const nPicked = Object.keys(myToday).length;
  const now = Date.now();

  // The flame strip — or the invitation to light one.
  let head;
  if (signedIn && me) {
    const last = me.last_result === "survived"
      ? `Survived ${escapeHtml(me.last_day)}.`
      : me.last_result === "lost" ? `Lost ${escapeHtml(me.last_day)} — new fire tonight.` : "";
    head = `<div class="stk-head">
      <div class="stk-flame">${icon("hot", 20)}<b>${me.current}</b><span>day streak</span></div>
      <div class="stk-best">${icon("trophy")} best ${me.best}</div>
      ${last ? `<div class="stk-last">${last}</div>` : ""}
    </div>`;
  } else {
    head = `<div class="stk-head">
      <div class="stk-flame">${icon("hot", 20)}<span>Free to play — an account is the scoreboard.</span></div>
      <button class="stk-cta" id="stk-signin">Sign in to play</button>
    </div>`;
  }

  // Today's slate.
  let card;
  if (!questions.length) {
    card = emptySlate("calendar", "No slate yet today",
      "Questions freeze when tonight’s board stands — check back soon.");
  } else {
    card = `<div class="stk-card">
      <div class="stk-card-head">Tonight — ${signedIn
        ? `${nPicked} of ${need} picked`
        : `pick ${need} to play`}</div>
      ${questions.map((q) => {
        const locked = !q.result && q.lock && Date.parse(q.lock) <= now;
        return stkQuestionRow(q, myToday[q.qid], locked, signedIn);
      }).join("")}
      <div class="stk-note${signedIn && nPicked >= need ? " in" : ""}" id="stk-note">${
        signedIn && nPicked >= need
          // "I made my picks and nothing happened" — the launch-day
          // complaint. Something HAS to say the picks landed, or the
          // silence reads as a failed save.
          ? `You’re in for tonight — all ${need} picks are down. You can change any of them until its game starts; results grade overnight, and the flame moves in the morning.`
          : signedIn && questions.length
            ? "Tap a side to pick it; tap again to clear. Picks lock at first pitch."
            : ""}</div>
    </div>`;
  }

  // Recent nights — the user's own, or just the graded slates.
  const days = slate.days || {};
  const past = Object.keys(days).filter((d) => d !== today)
    .sort().reverse().slice(0, 4);
  const history = past.map((d) => {
    const mine = (me && me.picks && me.picks[d]) || {};
    const qs = (days[d].questions || []).filter((q) => !signedIn || mine[q.qid]);
    if (!qs.length) return "";
    return `<div class="stk-day">
      <div class="stk-day-head">${escapeHtml(d)}${days[d].final ? "" : " — still grading"}</div>
      ${qs.map((q) => stkQuestionRow(q, mine[q.qid], true, signedIn)).join("")}
    </div>`;
  }).filter(Boolean).join("");

  // The leaderboard, and the name that puts you on it.
  // The board fills only with survived nights, which leaves day one
  // reading as broken; the count of tonight's players is the life sign
  // that exists immediately.
  const tonightLine = _stkTonight
    ? `<p class="stk-tonight">${_stkTonight} player${_stkTonight === 1 ? "" : "s"} in tonight</p>`
    : "";
  const board = (leadersRows.length
    ? `<table class="stk-board"><thead><tr><th>Player</th>
        <th class="num">Streak</th><th class="num">Best</th></tr></thead><tbody>
        ${leadersRows.map((r) => `<tr><td>${r.handle
          ? `<a href="#feed/u/${encodeURIComponent(r.handle)}">${escapeHtml(r.name)}</a>` : escapeHtml(r.name)}</td>
          <td class="num">${r.current}</td><td class="num">${r.best}</td></tr>`).join("")}
        </tbody></table>`
    : `<p class="stk-empty">Nobody has survived a night yet — the board lists
        streaks, and the first one claims it.</p>`) + tonightLine;
  // ONE PROFILE (Ethan, 2026-10-07): the board shows your site profile's
  // name. Choosing to appear is still the opt-in — a streak name set to
  // your handle — so nobody lands on a public board by making a profile.
  const prof = me && me.profile;
  const nameBox = !signedIn ? "" : `<div class="stk-namebox">${prof
    ? `<span>${me.name ? "On the board" : "Playing in private"} as <b>${escapeHtml(prof.name)}</b></span>
      <button id="stk-name-save" data-name="${me.name ? "" : escapeAttr(prof.handle)}">${me.name ? "Play in private" : "Show me"}</button>`
    : `<span>Make your profile to appear on the board — or play in private.</span>`}
      <a href="#account">${prof ? "Edit profile" : "Make your profile"}</a></div>`;

  host.innerHTML = `${head}${card}
    ${history ? `<div class="section-title stk-sub">Recent nights</div>${history}` : ""}
    <div class="section-title stk-sub">Leaderboard</div>${board}${nameBox}
    <details class="stk-rules"><summary>House rules</summary><ul>
      <li>Pick exactly ${need} each day. Every pick locks at its own game’s start; until then you can change or clear it.</li>
      <li>Win more picks than you lose and the streak lives. Pushes and voided questions count for neither side.</li>
      <li>Skip a day, or pick fewer than ${need}, and the streak just waits. Only a played-and-lost day resets it.</li>
      <li>Questions are the night’s most evenly priced props — coin flips on purpose. The model’s opinions stay on the boards.</li>
      <li>No money, no prizes — bragging rights and the leaderboard.</li>
    </ul></details>`;

  host.querySelectorAll(".stk-side[data-qid]").forEach((b) => {
    b.addEventListener("click", () => {
      if (!signedIn) { switchView("account"); return; }
      const cur = myToday[b.dataset.qid];
      stkPick(b.dataset.qid, cur === b.dataset.side ? "clear" : b.dataset.side);
    });
  });
  const cta = document.getElementById("stk-signin");
  if (cta) cta.addEventListener("click", () => switchView("account"));
  const save = document.getElementById("stk-name-save");
  if (save) save.addEventListener("click", stkSaveName);
}

function acctSignInHTML() {
  const legacy = acctState();
  // THE WARNING COMES BEFORE THE FORM, not after the password is typed.
  // The server refuses these requests anyway, but a refusal arrives too
  // late to be useful: by then the password is already in the box, and on
  // a phone it is already in the keyboard's suggestion history.
  const insecure = _acctUser && _acctUser.insecure;
  return `<div class="card acct-signin">
    <h2 class="acct-card-h">Welcome back</h2>
    ${insecure ? `<div class="warning">${icon("warn")} <b>${
      _acctUser.allowed ? "This connection is not private."
                        : "Not over this connection."}</b>
      This page came over plain HTTP from another machine, so a password
      typed here crosses your network readable by anyone on it — and it is
      usually a password used somewhere else too.
      ${_acctUser.allowed
        ? `This server has been set to accept it anyway. That setting removed
           the refusal, not the risk.`
        : `Open the site at its <b>https</b> address and sign in there.`}</div>` : ""}
    ${acctFieldsHTML("login")}
    <div class="acct-note">${escapeHtml(_acctNote)}</div>
    ${pkDoorHTML()}
    ${phoneDoorHTML("login")}
    <div class="acct-alt">
      <span>Don’t have an account?</span>
      <button class="btn ghost" data-act="acctGoSignup">Create one</button>
    </div>
    <p class="rank-help acct-fine">We never ask for your sportsbook or ESPN
      password. Those belong to someone else’s service and could not be
      revoked by us. This one is ours, and you can delete it whenever you
      like.</p>
    ${legacy ? `<p class="rank-help">${icon("warn")} This device is still
      signed in to the older PIN profile <b>${escapeHtml(legacy.name)}</b>.
      It keeps working and nothing has been moved — make an account and
      its data syncs up on the next sync.</p>` : ""}
  </div>`;
}

/* ---------------- Subscription -----------------------------------------

   Ethan, 2026-08-15: "we will be accepting money for people to use the
   website once it is complete."

   THE WALL IS UP as of 2026-08-20 and it is a server decision, not a
   client one. `QB_PAYWALL` gates the boards on the way out of the
   process — `gate.redact()` empties the paid lists before the JSON is
   written, and `seal_on_boot()` rewrites anything already on disk at
   startup — so the picks are not in the browser to be un-hidden. What
   this card does is report entitlement and sell a subscription. Nothing
   here is load-bearing for access.

   AND THE CARD NEVER TOUCHES A CARD. Subscribe hands off to a Stripe
   Checkout page; Manage billing hands off to Stripe's customer portal,
   which is also where cancelling happens. A company that builds its own
   cancel flow is deciding how hard it is to leave, and this one is not
   going to be that. */
/* What an account costs, on the account page.
   ---------------------------------------------------------------------
   THERE IS NO FREE PLAN, AND THERE HAS NOT BEEN ONE SINCE THE WALL WENT
   UP. This function used to draw a "Free — $0 always" card next to the
   paid one, listing the Record page, scores, standings, rosters,
   injuries, the fantasy room and the bet log as things you got for
   nothing. Every one of those pages is behind the wall now: WALL_OPEN
   lets an unpaid reader reach the Record page and the account page and
   nothing else, so the card was describing a tier the site does not
   grant.

   Ethan found it from the other side, 2026-08-22: "what exactly is the
   free plan? i didnt see it on the site or when i went to buy a plan."
   He had not seen it because it was never on the paywall — only here,
   after signing in, promising things the wall would refuse. A price list
   that overstates what is included is not a marketing problem; it is the
   part of the page a chargeback quotes back at you.

   ONE PRICING SURFACE, DELIBERATELY. The three prices live on the plans
   page and this card names no figure beyond the entry one, because a
   page advertising one number while Checkout charges another is a
   chargeback in the other direction. */
function billPlansHTML(s) {
  const line = (ok, t) => `<li class="${ok ? "yes" : "no"}">${
    icon(ok ? "check" : "dash", 13)} <span>${t}</span></li>`;
  const entitled = !!(s && s.entitled);
  const days = (s && s.trial_days) || 0;
  // Advertised only where it is true. Somebody who has subscribed before
  // does not get a second trial, and offering one on the page they see
  // after cancelling would be a promise the checkout then refuses.
  const trial = days > 0 && s && s.trial_eligible && !entitled;
  return `
    <section class="set-group">
    <h2 class="set-group-h">What a membership includes</h2>
    <div class="plan-grid">
      <div class="card plan raised${entitled ? " current" : ""}">
        <div class="plan-band">The whole board</div>
        <div class="plan-name">Member</div>
        <div class="plan-price">$25<span>a month, or less on a longer
          plan</span></div>
        <ul class="plan-list">
          ${line(true, "Every priced pick, with its edge and the reasons")}
          ${line(true, "Prop, game-line and long-shot boards, all leagues")}
          ${line(true, "The prediction-market desk and its gate")}
          ${line(true, "The Record page — every graded pick, win or lose")}
          ${line(true, "Scores, standings, rosters and the injury report")}
          ${line(true, "The fantasy room, your bet log and the bankroll tools")}
          ${line(true, "The members’ Discord")}
          ${line(true, "Cancel from this page whenever you like")}
        </ul>
        ${trial ? `<p class="plan-trial">${icon("check", 13)}<span>Start
          with <b>${days} days free</b> on the monthly plan. A card is
          taken now and charged $25 on day ${days + 1} unless you cancel
          before then.</span></p>` : ""}
        ${entitled
          ? `<div class="plan-cta plan-cur">Your plan now</div>`
          : `<button class="btn primary plan-btn" data-act="billSeePlans">See the plans</button>`}
      </div>
    </div>
    <p class="set-foot">One subscription, three lengths, and you see the exact
      total before you enter a card. No card number ever reaches this server —
      checkout and cancellation both happen on Stripe’s own pages. The site
      still takes no bets and holds no money.</p>
    </section>`;
}

/* ONE PLAN, THEN THE LONGER ONES AS SAVINGS (Ethan's product audit,
   2026-09-23, items 11-12): "Instead of three giant equal cards —
   QELLYS BOOK, $25/month, everything included — then save with longer
   plans." The 6-month card wore "Most popular", which nothing
   measured; the badge now goes to the plan that costs least per
   month, which is arithmetic, and it says "Best value". */
function planPerMonth(pl) {
  return pl.price / (pl.months || 1);
}

function bestValuePlanId(plans) {
  let best = null;
  (plans || []).forEach((p) => { if (!best || planPerMonth(p) < planPerMonth(best)) best = p; });
  return best ? best.id : "";
}

/* The FAQ as this reader should see it.
   ---------------------------------------------------------------------
   `FAQ` above is the no-trial wording and stays the base, because the
   trial is a server decision and this file must not assert one that the
   checkout would then refuse. When the server says there IS one — and
   that this reader can still have it — the trial answer is replaced with
   the terms in full.

   THE TERMS IN FULL, not a headline. "3 days free" with the conversion
   left to be discovered is the pattern that fills chargeback forms, and
   several states legislate against it by name. Card required, what it
   becomes, when, and how to stop it: all four, on the page, before the
   click. */
function faqFor(status) {
  const days = (status && status.trial_days) || 0;
  const plan = (status && status.trial_plan) || "";
  const off = status && status.signed_in && status.trial_eligible === false;
  if (!days || off) return FAQ;
  const pl = PLANS.find((p) => p.id === plan) || PLANS[0];
  return FAQ.map(([q, a]) => q === "Is there a free trial?"
    ? [q, `Yes \u2014 ${days} days, on the ${pl.name.toLowerCase()} plan ` +
         `only, one per account. A card is taken at signup and is charged ` +
         `$${pl.price} on day ${days + 1} unless you cancel first. ` +
         `Cancelling during the ${days} days costs nothing and takes one ` +
         `button on your account page. After that the ordinary policy ` +
         `applies: payments are not refundable, and cancelling keeps your ` +
         `access to the end of the period you have already paid for.`]
    : [q, a]);
}

function pwResultsHTML(rec) {
  const o = (rec && rec.overall) || null;
  if (!o || !o.settled) return "";
  const pct = (x) => `${(x * 100).toFixed(1)}%`;
  const net = o.net_units || 0;
  const stat = (value, label, tone) =>
    `<div class="pw-stat"><b${tone ? ` class="${tone}"` : ""}>${value}</b>
       <span>${label}</span></div>`;
  /* v5: THE SITE'S OWN RIBBON, on the page that asks for money. Ethan,
     the day the record was pooled: "i also want the paywall site to show
     this as well" — (no date here: test_paywall_proof reads every
     figure in this function as a claim) —
     the ring, the W-L, the ROI, the units, the settled count and the
     last five, drawn by the same builder as the home and the Record
     page (recordRibbonsHTML) from the same pooled record. AND THE
     COMBINED LINE, as on the Record page (Ethan, the day his Pikkit
     record went up: "we need to display the new combined record here too
     on the paywall"): "Everything we've bet" leads with its split on the
     tile — the model's units and Zeno's, his unit's dollar value beside
     them — then the model's own tile, then Zeno's, so the
     number a buyer is paying for is never hidden inside the bigger one.
     The tiles beneath are the MODEL's and say so: its win rate against
     the break-even its prices require — or the bar alone, while the
     sample cannot carry a rate — and how much it staked to earn its number. */
  const ribbon = recordRibbonsHTML({ combined: rec && rec.combined, zeno: rec && rec.zeno,
                                     pooled_overall: rec && rec.pooled_overall,
                                     likely_overall: rec && rec.likely_overall,
                                     min_graded: rec && rec.min_graded }, o,
                                   (rec && rec.recent) || []);
  return `<div class="pw-results">
    ${ribbon ? `<div class="hd-stats rec-ribbons pw-ribbon">${ribbon}</div>${zenoWhoHTML(rec)}` : ""}
    <div class="pw-stats pw-stats-two">
      ${/* The bar the prices we took actually require is a fact about
            those prices and true at any sample size, so it is what the
            tile carries until a win rate means something. */""}
      ${o.settled >= PROOF_RATE_FLOOR
        ? stat(pct(o.win_rate || 0),
               `the model’s win rate · ${pct(o.breakeven || 0)} needed at our prices`)
        : stat(pct(o.breakeven || 0),
               "needed at the prices we took, to break even")}
      ${stat(`${(o.units_staked || 0).toFixed(1)}u`,
             `the model staked to earn ${net >= 0 ? "+" : "−"}${Math.abs(net).toFixed(2)}u, flat units`,
             net >= 0 ? "pos" : "neg")}
    </div>
    <p class="pw-results-note">${o.settled < PROOF_RATE_FLOOR
      ? `A sample of ${o.settled} proves nothing, and it is shown anyway
         rather than waited out.`
      : `Every one of them is on the Record page with its price, its date
         and its result.`}
      The <a href="#record">Record</a> is free and stays free — read it
      before you pay.</p>
  </div>`;
}

/* The half of the case that survives a bad month. */
function paywallProofHTML(rec) {
  const o = (rec && rec.overall) || null;
  if (!o || !o.settled) {
    return `<div class="pw-proof">
      <div class="pw-proof-head">${iconMark("scale", 18)} Graded in public</div>
      <p>Every pick this model makes is written down before the game and
      graded afterwards, win or lose, on the <a href="#record">Record</a>
      page — which is free and stays free. Nothing has settled yet, so
      there is nothing to show you. That is what this space will say until
      there is.</p></div>`;
  }
  const pr = o.process || {};
  const priced = (pr.good || 0) + (pr.bad || 0) + (pr.flat || 0);
  const clv = o.avg_clv;
  // BEATING THE CLOSE IS THE ONLY LEADING INDICATOR THERE IS. A record
  // can be luck for a long time; taking a price the market later moves
  // past cannot be, over hundreds of bets. It is also the number a
  // pick-seller never publishes, which is most of why it is here.
  const process = (clv != null && o.clv_n)
    ? `<div class="pw-stats">
        <div class="pw-stat"><b class="${clv >= 0 ? "pos" : "neg"}">${
          clv >= 0 ? "+" : "−"}${Math.abs(clv).toFixed(2)}</b>
          <span>average closing-line value, ${o.clv_n} bets</span></div>
        ${priced ? `<div class="pw-stat"><b>${pr.good || 0}–${pr.bad || 0}</b>
          <span>bets that beat the close, against those that did not</span>
          </div>` : ""}
      </div>` : "";
  return `<div class="pw-proof">
    <div class="pw-proof-head">${iconMark("scale", 18)} Graded in public</div>
    ${process}
    <p>${clv != null && o.clv_n
      ? `That is the price we took against the price the market closed at.
         A win rate can be luck for a long time; beating the close over
         hundreds of bets is the part that cannot be, and it is the number
         a pick-seller never shows you.`
      : `Every pick is written down before the game and graded afterwards,
         win or lose, on the free Record page.`}
      No model wins every night, and be suspicious of anyone who claims
      theirs does.</p></div>`;
}


/* Payment methods Stripe Checkout offers on a standard US account with
   nothing extra switched on. NAMES, NOT LOGOS: the brand marks are
   trademarks with usage rules, and a wall of them is the oldest trick in
   the fake-checkout book. Apple Pay and Google Pay are deliberately
   ABSENT — they need domain verification that has not been done, and
   advertising a payment method that does not appear at checkout is the
   kind of small lie that costs the sale in the last five seconds. */
const PW_CARDS = ["Visa", "Mastercard", "Amex", "Discover"];

/* Per-plan lists, in the render's own escalating shape.
   ---------------------------------------------------------------------
   The render (Ethan, 2026-08-20) draws three DIFFERENT lists: thirteen
   lines on monthly, then "Everything In Monthly Plan" plus extras, then
   "Everything In 6 Month Plan" plus more. Read literally that is tiering,
   and this site does not tier — every plan is the same product and the
   only axis is how long you commit for.

   So the SHAPE is copied and the meaning is kept true. Monthly lists what
   the site actually is. The longer plans inherit it by name — which is
   what "Everything in…" means when there is one product — and then list
   what is genuinely different about them, which is the money and the
   commitment. Nothing appears on a longer plan that a monthly subscriber
   does not get. */
const PLAN_EXTRAS = {
  monthly: [],
  sixmonth: [
    "Everything in the Monthly plan",
    "Save $25 against paying monthly",
    "One charge every 6 months, not six",
  ],
  yearly: [
    "Everything in the 6-month plan",
    "Save $75 against paying monthly — the lowest price we offer",
    "One charge a year, and the price is locked for that year",
  ],
};

/* The sports row. Nine chips, and no league logos: the NFL shield and the
   rest are trademarks, and a subscription site printing them next to a
   price implies a licence we do not have. Names and our own marks
   instead. */
/* THE CHIPS THAT SAY WHAT IS COVERED, and what marks them.
   ---------------------------------------------------------------------
   Ethan, 2026-08-22, circling this row: "we should be using emojis
   matching what we are talking about here."

   The drawn set could not do this job. It has no football and no
   baseball, so NFL and CFB both got `shield` and MLB, NBA and WNBA all
   got the same `target` — five chips, two marks, and a row whose whole
   purpose is to show a reader the breadth at a glance. Three identical
   circles say the opposite.

   AND THIS IS THE EXEMPTED CASE, not a hole in it. tests/test_icons.py
   removed emoji from the site because a status mark that changes shape
   per platform and cannot take the colour of the thing it labels is not
   an icon set. Its own exemption list names "the sport logos … 
   illustration, not status marks", and `SPORTS[x].logo` has been 🏈 ⚾ 🏀
   since long before this row existed. These are the same glyphs doing
   the same job on the page that sells the thing.

   The five real sports are checked against SPORTS[] by
   tests/test_paywall_chips.py, so the shop and the app cannot end up
   disagreeing about what a baseball looks like. */
const PW_SPORTS = [
  ["NFL", "🏈"], ["MLB", "⚾"], ["NBA", "🏀"],
  ["WNBA", "🏀"], ["CFB", "🏈"], ["UFC", "🥊"],
  ["Fantasy", "🏆"], ["Prediction markets", "📈"],
  ["Meme coins", "🪙"], ["Ask Qellys AI", "🤖"],
];

/* ASK QELLYS, SOLD WHERE IT IS BOUGHT. Ethan, 2026-09-23: "Also make sure
   we display this feature on the paywall page." A section of its own
   under the hero, a card at the head of the feature grid, a line on the
   plan and a chip in the breadth row.

   THE PREVIEW IS BUILT FROM THE ASK PAGE'S OWN PARTS — the robot, the
   title, a reader's question in its bubble, Ask's typing dots — and it
   shows NO ANSWER. An answer written for a sales page would be numbers
   nobody computed, on the one page where every other number is graded in
   public. The four points beside it are what it does.

   A PICTURE OF THE FEATURE, NOT A WAY INTO IT. Ethan, the same day: "I
   don't want people to be able to access the chat bot from the paywall
   page, I just wanted to display that it's a feature." Nobody could — the
   wall sends a visitor's every route to Ask back here (WALL_OPEN) and the
   server answers /api/ask to subscribers only — but the first preview
   carried the message box, its send button and two question chips, which
   is a chat that LOOKS open. Those are gone; what is left is a scene and
   a line saying it comes with every plan. aria-hidden, no controls, and
   nothing in it takes a tap. */

function pwAskHTML() {
  const point = (text) => `<li>${iconMark("check", 14)}<span>${escapeHtml(text)}</span></li>`;
  return `<section class="pw-ask" aria-labelledby="pw-ask-h">
    <div class="pw-ask-head"><span class="ask-pill">AI</span></div>
    <h2 class="pw-h2" id="pw-ask-h">Meet <em>Ask Qellys.</em></h2>
    <p class="pw-h2sub">Your AI betting assistant. Ask about any team, player or game in
      any sport we cover, and get a straight answer written from our own numbers.</p>
    <picture class="pw-ask-scene"><source type="image/webp"
        srcset="img/ask/qbot-scene@640.webp 640w, img/ask/qbot-scene.webp 960w" sizes="(max-width: 760px) 100vw, 760px">
      <img src="img/ask/qbot-scene.jpg" srcset="img/ask/qbot-scene@640.jpg 640w, img/ask/qbot-scene.jpg 960w"
        sizes="(max-width: 760px) 100vw, 760px" width="960" height="600" loading="lazy" decoding="async"
        alt="The Ask Qellys robot at a laptop, surrounded by questions it answers"></picture>
    <div class="pw-ask-grid">
      <div class="pw-ask-demo" aria-hidden="true" data-bot="thinking">
        <div class="pw-ask-bar">${qbotHTML("head", "pw-ask-bar-bot")}<b>Ask <em>Qellys</em></b></div>
        <div class="ask-row me"><div class="ask-turn me">How have the Lions done against the Packers?</div></div>
        <div class="ask-row bot">${askAva(true)}<div class="ask-turn bot wait"><span class="ask-dots"><i></i><i></i><i></i></span></div></div>
        <div class="pw-ask-incl">${iconMark("lock", 13)}<span>Included with every plan</span></div>
      </div>
      <ul class="pw-ask-points">
        ${point("Any sport, any team, any player — not just who plays tonight")}
        ${point("Head-to-heads, game logs and tonight’s lines, looked up for you")}
        ${point("The sources under every answer, and a pick’s page one tap away")}
        ${point("Says so when our data has nothing on it, and never tells you to bet")}
      </ul>
    </div>
  </section>`;
}

/* WHY THE WALL IS UP, when it is a lapse (Ethan, 2026-10-12): the
   server's own sentence for the status (billing.describe, the line the
   account page shows too), and for a failed card the button to Stripe's
   billing page, which changes the card and pays the open invoice. Not a
   second plan: that would bill them twice once Stripe's retry clears,
   and checkout refuses one. */
function pwLapseHTML(s, rec) {
  const st = s && s.signed_in && !s.entitled && s.note ? s.status : "";
  const fix = st === "past_due" || st === "unpaid";
  return fix || st === "canceled" || (st && s.cancel_at_end) ? `
    <div class="card pw-lapse" role="status"><p>${escapeHtml(s.note)}</p>${pwSinceHTML(rec, s)}${fix
      ? `<button class="btn primary" data-act="billPortal">Update card</button>
         <p class="pw-lapse-note"></p>` : ""}</div>` : "";
}

/* WHAT THEY MISSED (the ideas list's win-back, 2026-10-26): the public
   record from the day the plan ended, off the curve the Record page draws
   (adoptPooledRecord's edge curve), so the two always agree. Win or lose,
   once five picks have graded — a record shown only when it flatters is
   an advert, and the Record page is free to read anyway. */
function pwSinceHTML(rec, s) {
  const end = Number(s && s.period_end);
  const curve = (rec && rec.curve) || [];
  if (!end || end * 1000 > Date.now() || !curve.length) return "";
  const from = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(end * 1000));
  let w = 0, l = 0, n = 0, u = 0;
  curve.forEach((pt) => {
    if (String(pt.date || "").slice(0, 10) < from) return;
    w += Number(pt.w) || 0; l += Number(pt.l) || 0; n += Number(pt.n) || 0; u += Number(pt.day_u) || 0;
  });
  if (w + l < 5) return "";
  const p = Math.max(0, n - w - l);
  const day = new Date(end * 1000).toLocaleDateString(undefined, tzOpts({ month: "short", day: "numeric" }));
  return `<a class="pw-since" href="#record"><span>Since your plan ended ${escapeHtml(day)}</span>
    <b>${w}–${l}${p ? `–${p}` : ""}</b><span class="${u >= 0 ? "pos" : "neg"}">${u >= 0 ? "+" : "−"}${Math.abs(u).toFixed(1)}u</span>
    <i>See every pick ${icon("chev", 12)}</i></a>`;
}

/* The paywall in a store build that sells nothing (boot.js
   QB_STORE_CHECKOUT, today the Play build): members sign in, and that is
   all it says — no price, no plan, no button to pay and no word about
   where to (Play's billing policy, until the US external-links enrolment
   in docs/APP_STORES.md is on). The record stays free to read. */
function storePaywallHTML(rec, status) {
  const signed = !!(status && status.signed_in);
  return `
  <div class="pw pw-store">
    <header class="pw-top">
      <span class="pw-brand">${brandMarkHTML(30)}
        <span class="pw-brand-words">QELLYS <b>BOOK</b></span></span>
      <button class="btn ghost pw-login" data-act="pwSignIn">${signed ? "Account" : "Log in"}</button>
    </header>
    ${pwLapseHTML(status, rec)}
    <section class="pw-hero">
      <h1 class="pw-h1">Members <em>sign in</em> here.</h1>
      <p class="pw-sub">Tonight’s picks, the props and the game reports open
        with a Qellys Book membership. Sign in with the account you already have.</p>
      <p class="pw-sub">${signed ? "Your free account keeps every game live, the game chat and Call it."
        : "Every game live, the game chat and Call it are free with an account."}</p>
      <div class="pw-store-go">
        <button class="btn primary" data-act="pwSignIn">${signed ? "Your account" : "Log in"}</button>
        ${signed ? `<a class="btn ghost" href="#live">Go to the live games</a>`
          : `<button class="btn ghost" data-act="acctGoSignup">Create a free account</button>`}
        <a class="btn ghost" href="#record">See the record — free</a>
      </div>
    </section>
    <div class="pw-trust">${paywallProofHTML(rec)}</div>
  </div>`;
}

function paywallHTML(rec, status) {
  if (!storeSells()) return storePaywallHTML(rec, status);
  /* Same reasoning as the sport chips above: these ten cards are what a
     visitor scans to decide whether the site does the thing they came
     for, and the drawn set was repeating itself here too — `target` on
     Picks and props while the MLB chip also wore `target`, `chart` and
     `rising` a hair apart, `gem` doing duty for meme coins in two
     places. Ten cards, ten distinct marks now, and each one is the thing
     it is about rather than a shape that gestures at it. */
  const feature = (mark, title, body) => `
    <article class="card pw-feat">
      <div class="pw-feat-ic"><span class="pw-emoji lg"
        aria-hidden="true">${mark}</span></div>
      <h3>${escapeHtml(title)}</h3><p>${escapeHtml(body)}</p></article>`;

  /* A plan whose price id is not configured on the server must not draw
     a buy button: the customer commits, and the request 502s. `status`
     comes from /api/billing/status and carries `ready` per plan. When
     the status call failed entirely we assume ready — a network blip
     should not hide the shop. */
  const readiness = {};
  ((status && status.plans) || []).forEach((p) => { readiness[p.id] = !!p.ready; });
  const sellable = (id) => (id in readiness ? readiness[id] : true);
  // Signed in, a plan's button opens checkout; signed out, the free sign-up
  // first, with the plan kept for checkout straight after (pwJoin).
  const join = (id) => (status && status.signed_in ? 'data-act="coStart"' : `data-pwjoin="${escapeAttr(id)}"`);

  /* THE TRIAL, ON ONE CARD. Ethan, 2026-08-22: "we can offer a 3 day free
     trial only for the $25 plan." Drawn from the server's answer rather
     than from a constant here — the server is what actually grants it,
     and a card promising three days that Checkout then refuses is worse
     than no offer at all. Hidden for anybody who has subscribed before,
     because they do not get a second one. */
  const trialDays = (status && status.trial_days) || 0;
  const trialPlan = (status && status.trial_plan) || "";
  const trialOK = trialDays > 0
    && !(status && status.signed_in && status.trial_eligible === false);

  const plan = (pl) => {
    const lines = pl.id === "monthly"
      ? PLAN_FEATURES
      : PLAN_EXTRAS[pl.id].concat(PLAN_FEATURES.slice(0, 4));
    const ok = sellable(pl.id);
    const trial = trialOK && pl.id === trialPlan;
    return `
    <article class="card pw-plan${trial ? " pw-trial" : ""}">
      ${trial ? `<div class="pw-tag pw-tag-trial">${trialDays} days free</div>`
        : ""}
      <div class="pw-plan-name">${pl.id === "monthly" ? "Qellys Book" : escapeHtml(pl.name)}</div>
      ${pl.id === "monthly" ? `<div class="pw-plan-sub">Everything included</div>` : ""}
      <div class="pw-price-row">
        <div class="pw-price"><span class="cur">$</span>${pl.price}<i>/${
          escapeHtml(pl.per)}</i></div>
        ${pl.save ? `<span class="pw-save">Save $${pl.save}</span>` : ""}
      </div>
      <div class="pw-cadence">${trial
        ? `${trialDays} days free, then $${pl.price} a month.`
        : escapeHtml(pl.cadence)}</div>
      <ul class="pw-list">${lines.map((f) =>
        `<li>${iconMark("check", 13)}<span>${escapeHtml(f)}</span></li>`).join("")}</ul>
      ${ok
        ? `<button class="btn primary pw-buy" data-plan="${escapeAttr(pl.id)}"
             ${join(pl.id)}>${
             trial ? `Start ${trialDays} days free` : "Get started"}</button>`
        : `<button class="btn pw-buy" disabled
             title="This plan is not switched on yet">Not available yet</button>`}
      <div class="pw-fine">${trial
        // SAID PLAINLY, on the card, before the click. A trial that
        // collects a card and converts silently is the most complained
        // about pattern in subscriptions and several states legislate
        // against it. Terms §5.3 says the same thing at length.
        ? `Card required. Becomes $${pl.price} a month on day ${
            trialDays + 1} unless you cancel before then — one button on
            your account page.`
        : escapeHtml(pl.cadence)}</div>
    </article>`;
  };
  // The longer plans as rows: the length, the price, what it comes to a
  // month, the saving, and one button. Same product, same checkout.
  const bestId = bestValuePlanId(PLANS);
  const longer = (pl) => {
    const ok = sellable(pl.id);
    const best = pl.id === bestId;
    return `
    <article class="card pw-long${best ? " best" : ""}">
      <div class="pw-long-what"><b>${escapeHtml(pl.name)}</b>${
        best ? `<span class="pw-best">Best value</span>` : ""}
        <span class="pw-long-price">$${pl.price} · $${planPerMonth(pl).toFixed(2)} a month</span></div>
      ${pl.save ? `<span class="pw-save">Save $${pl.save}</span>` : ""}
      ${ok
        ? `<button class="btn pw-buy pw-buy-sm" data-plan="${escapeAttr(pl.id)}"
             ${join(pl.id)}>Choose</button>`
        : `<button class="btn pw-buy pw-buy-sm" disabled
             title="This plan is not switched on yet">Not yet</button>`}
    </article>`;
  };

  return `
  <div class="pw">
    <header class="pw-top">
      <span class="pw-brand">${brandMarkHTML(30)}
        <span class="pw-brand-words">QELLYS <b>BOOK</b></span></span>
      ${status && status.instagram
        ? `<a class="pw-ig" href="${safeHref(status.instagram)}"
             target="_blank" rel="noopener noreferrer"
             title="Qellys Book on Instagram"
             aria-label="Qellys Book on Instagram">${igIcon()}</a>`
        : ""}
      ${status && status.signed_in
        ? `<span class="pw-who" title="${escapeHtml(status.email || "")}">
             <b>Signed in</b>${status.email
               ? `<span>${escapeHtml(status.email)}</span>` : ""}</span>
           <button class="btn ghost pw-login" data-act="pwSignIn">Account</button>`
        : `<button class="btn ghost pw-login" data-act="pwSignIn">Log in</button>
           <button class="btn primary pw-join" data-act="acctGoSignup">Sign up free</button>`}
    </header>
    ${pwLapseHTML(status, rec)}
    ${pwWhyHTML()}
    ${pwDoorsHTML(status, trialOK && sellable(trialPlan) ? trialDays : 0)}

    <section class="pw-hero">
      <h2 class="pw-h1">Data. <em>Edge.</em> Receipts.</h2>
      <p class="pw-sub">Professional sports intelligence. Real-time edges.
        Every call graded in public.</p>
      ${/* FROM sellable(), LIKE THE CARD (audit V-20): the hero promised
            "Start 3 days free" off trialDays alone while the card below,
            asking sellable(), drew "Not available yet" — the primary path
            ended on a dead button. */""}
      ${pwHeroCtaHTML(trialOK && sellable(trialPlan) ? trialDays : 0,
                      PLANS.some((p) => sellable(p.id)))}
      ${/* Tonight's picks, locked, with their counts (flTonightHTML) —
            drawn by pwTonight once the numbers are in, and only on a day
            with picks up. */""}
      <div class="pw-fl"></div>
      ${/* SPORTS FIRST (audit item 6, 2026-09-23): the lede sold three
            audiences at once — "bettors, fantasy players and market
            traders" — and the audit's question was which one this is.
            A sports intelligence platform; the rest come with it. */""}
      <p class="pw-lede">Qellys Book is a sports intelligence platform for
        serious bettors — the model’s estimates, the reasoning behind each
        one, the price we took, and a public record of how they turned out.
        Fantasy and market tools come with it.</p>
      ${/* THE RECEIPTS, ABOVE THE PRICE. The hero promised "every call
            graded in public" and then showed nothing until below the
            plans, which is a claim asking to be taken on faith on the one
            page where it does not have to be. */""}
      ${/* THE RECEIPTS STAY ABOVE THE PRICE (tests/test_paywall_proof):
            "graded in public" is shown, not promised. What moved for the
            audit (V-20) is everything else that stood before the price —
            the twelve-card grid and the Ask demo now follow the FAQ. */""}
      ${pwResultsHTML(rec)}
      ${/* DON'T TAKE OUR WORD FOR IT (audit item 4): the one claim on
            this page a stranger can check, said as the four things that
            make it checkable, with the door to the check itself. */""}
      <div class="pw-verify">
        <b class="pw-verify-h">Don’t take our word for it.</b>
        <ul class="pw-verify-list">
          <li>${iconMark("check", 13)}<span>Every pick is timestamped.</span></li>
          <li>${iconMark("check", 13)}<span>Every price is recorded.</span></li>
          <li>${iconMark("check", 13)}<span>Every result is graded.</span></li>
          <li>${iconMark("check", 13)}<span>Every loss stays on the board.</span></li>
          <li>${iconMark("check", 13)}<span>Every Zeno pick is verified on Pikkit.</span></li>
        </ul>
        <a class="pw-verify-go" href="#record">See the record — it’s free &#8594;</a>
        <a class="pw-verify-go pk-go" href="${PIKKIT_URL}" target="_blank" rel="noopener noreferrer">Zeno’s record on Pikkit &#8599;</a>
      </div>
      <div class="pw-sports">${PW_SPORTS.map(([label, mark]) =>
        // aria-hidden: the label is the next node, and a screen reader
        // announcing "American football NFL" is a stutter, not a help.
        `<span class="pw-sport"><span class="pw-emoji"
           aria-hidden="true">${mark}</span>
           <span>${escapeHtml(label)}</span></span>`).join("")}</div>
    </section>

    <h2 class="pw-h2"><em>Simple pricing.</em> One product.</h2>
    <p class="pw-h2sub">${iconMark("lock", 13)} Every plan is the same full
      site. The only difference is how long you commit for and how much you
      save.</p>
    ${freeVsPlanHTML("pw")}
    <div class="pw-plans" data-shape="one">
      ${plan(PLANS.find((p) => p.id === "monthly") || PLANS[0])}
      <div class="pw-longer">
        <div class="pw-longer-h">Save with a longer plan</div>
        ${PLANS.filter((p) => p.id !== "monthly").map(longer).join("")}
        <p class="pw-longer-note">Every plan is the same product — the length
         is the only difference.</p>
      </div>
    </div>

    <div class="pw-trust">
      <div class="pw-guar">
        <div class="pw-guar-ic">${iconMark("lock", 22)}</div>
        <div>
          <b>Cancel whenever you like</b>
          <p>One button on your account page, which opens Stripe’s own
            portal. No phone call, no retention offer, and no refunds to
            argue about — cancelling stops the next charge and you keep
            everything you have already paid for, to the day.</p>
        </div>
      </div>
      ${paywallProofHTML(rec)}
    </div>


    <h2 class="pw-h2">Questions</h2>
    <div class="pw-faqgrid">
      <aside class="card pw-unlock">
        <div class="pw-unlock-ic">${iconMark("bolt", 24)}</div>
        <h3>Unlock the edge</h3>
        <p>Every number on this site is computed, dated and graded. Read the
          <a href="#record">Record</a> page before you pay — it is free, it
          stays free, and it is the only claim we make that you can check.</p>
        ${sellable("sixmonth") ? `<button class="btn primary pw-unlock-go" data-plan="sixmonth"
          ${join("sixmonth")}>Get started</button>` : `<a class="btn pw-unlock-go" href="#record">See the record</a>`}
      </aside>
      <div class="card pw-faq">${faqFor(status).map(([q, a], i) => `
        <details class="pw-q"${i === 0 ? " open" : ""}>
          <summary>${escapeHtml(q)}</summary>
          <p>${escapeHtml(a)}</p></details>`).join("")}</div>
    </div>

    ${pwAskHTML()}

    <h2 class="pw-h2"><em>Everything</em> you need. All in one place.</h2>
    <div class="pw-feats">
      ${feature("🤖", "Ask Qellys",
        "An AI assistant for any team, player or game in any sport — tonight’s boards and every past game we have stored — answered from our own numbers, with the sources shown.")}
      ${feature("🎟️", "All of Zeno’s props and parlays",
        "Every prop and parlay Zeno places at FanDuel, DraftKings and theScore Bet — the pick, the book, the price he got and the stake — posted the moment he places it. Every one is verified on Pikkit, synced from his sportsbooks: check his record there before you pay.")}
      ${feature("🎯", "Picks and props",
        "Daily best bets, player props and parlay tickets across every sport we cover, each with the arithmetic that produced it.")}
      ${feature("📊", "The model, shown working",
        "Projections, matchup reads and the step-by-step chain from a player’s baseline to the number on the card.")}
      ${feature("🏆", "The full fantasy suite",
        "Draft kit, 20,000-draft mock simulator, lineup optimiser, trade finder, waiver reads and a start calendar.")}
      ${feature("📈", "Prediction markets",
        "Live scanning of prediction-market prices for the spots where the crowd and the model disagree.")}
      ${feature("🪙", "Meme coin scanner",
        "Live token discovery with holder concentration, carry tracking and rug checks.")}
      ${feature("🔀", "Line movement and shopping",
        "Where each price opened, where it is now, and which book is best right now — in payout space, not in cents.")}
      ${feature("📒", "Bet tracker",
        "Log what you actually placed, by hand or by paste, and get ROI, CLV and a record you can argue with.")}
      ${feature("🔔", "Alerts",
        "Line moves, injuries and the nightly summary, on your phone.")}
      ${feature("👤", "Player pages",
        "Every player we hold, with usage, trends, injuries, props and fantasy value in one place.")}
      ${feature("🧾", "A public record",
        "Every pick graded afterwards — wins and losses both — on a page that stays free whether you subscribe or not.")}
    </div>


    <!-- ONE LINE AND TWO LINKS, which is how every site that takes money
         for this does it. Ethan, 2026-08-21: "like 2 links under the pay
         page or something like how other sites have it."

         The full text did not disappear — it moved to where somebody
         reads it on purpose rather than skims past it: Terms §2, §3 and
         §4, and the site footer on every signed-in page. What stays here
         is the part that has to be ON the page taking the payment: the
         age gate and the helpline. That is the industry pattern, and it
         is the pattern for a reason. -->
    <footer class="pw-foot">
      <div class="pw-foot-top">
        <span class="pw-brand small">${brandMarkHTML(22)}
          <span class="pw-brand-words">QELLYS <b>BOOK</b></span></span>
        <div class="pw-secure">
          <div class="pw-secure-head">${iconMark("lock", 13)} Secure checkout</div>
          <p>Payment is taken on Stripe’s own page over an encrypted
            connection. Nothing about your card reaches this server.</p>
          <div class="pw-cards">${PW_CARDS.map((c) =>
            `<span class="pw-card">${escapeHtml(c)}</span>`).join("")}</div>
        </div>
      </div>
      <p class="pw-legal">21+ · Not betting advice · Gambling problem?
        Call <b>1-800-GAMBLER</b></p>
      <p class="pw-copy">© ${new Date().getFullYear()} Qellys Book ·
        <a href="terms.html">Terms</a> · <a href="privacy.html">Privacy</a></p>
    </footer>
  </div>`;
}

/* The wall hides the whole chrome, including the way in. Somebody who
   already pays and is merely signed out lands here and needs a door. */
/* The Instagram link in the top bar.
   ---------------------------------------------------------------------
   Ethan, 2026-08-22: "add a little instagram icon at the top of the page
   and if you click it, it will take you right to my instagram page."

   THE HANDLE IS NOT IN THIS FILE. It arrives on the status payload from
   QB_INSTAGRAM, the same way the Discord page gets it, so there is one
   place to change it and no dead icon on an install that has not set one.
   Unlike the Discord invite it is NOT gated on entitlement — a public
   profile anybody can already find, and showing it to somebody who has
   not subscribed is the point of showing it at all.

   Called wherever the status is refreshed rather than fetching its own:
   a decoration must not cost a request.

   IT ALSO GOES ON THE WALL. `body.walled` hides the top bar, so for a
   visitor who has not paid — the one most worth showing an Instagram to
   — the bar version is invisible. `paywallHTML` draws its own. */
function igIcon(size = 17) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}"
    fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"
    focusable="false"><rect x="3" y="3" width="18" height="18" rx="5"/>
    <circle cx="12" cy="12" r="4"/>
    <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor"
      stroke="none"/></svg>`;
}

/* ======================= THE DISCORD =======================
   Ethan, 2026-08-21, with a render: "once someone makes an account …
   the first thing we should do is give them the link to join the discord
   server … also we should add a discord tab or something so if someone
   doesn't join immediately, they still have the option to join later. i
   do wanna add the main purpose of this discord server is for me to
   select and pick out picks i think are winners."

   SO IT IS TWO THINGS IN ONE PAGE. Arrived at right after paying, it is
   a welcome: the account is made, here is the door, walk through it.
   Reached from the nav later, it is the same page without the confetti —
   which is the whole reason it is a VIEW and not a one-shot screen. A
   welcome you can only see once is a welcome you cannot go back to, and
   "I closed it, where was that link" is the support email this exists to
   prevent.

   THE INVITE IS STILL ONLY SENT TO PAID READERS. `s.discord` arrives on
   the status payload or it does not arrive at all — the server decides,
   and web/js/app.js never holds it otherwise. An unsubscribed reader
   gets this same page as a SALES page: everything about what is inside,
   and a button to the plans where the join button would be. That is
   deliberate. The Discord is where the picks get posted, so handing the
   invite out at signup would hand out the product to anyone who can type
   an email address. */

const DISCORD_PERKS = [
  "Ethan’s own picks — the ones he is actually on",
  "Live line-movement alerts",
  "Injury news and late scratches",
  "Lineup breakdowns and projections",
  "Fantasy picks and strategy",
  "Community chat and discussion",
  "Giveaways and contests",
  "Direct access to the Qellys desk",
];

const DISCORD_INSIDE = [
  ["target", "Daily picks",
   "The plays Ethan has picked out himself, posted as he takes them."],
  ["bolt", "Live alerts",
   "Line moves, steam and injury news while there is still time to act."],
  ["chart", "Projections",
   "The model’s numbers behind the calls, and where they disagree."],
  ["people", "Community",
   "A room of people betting the same card, comparing notes."],
  ["gem", "Giveaways",
   "Contests and drops that run in the server and nowhere else."],
  ["inbox", "Support",
   "Ask a question and get an answer from the person who built it."],
];

/* The channel list from the render. Names only — nothing in this panel
   pretends to be a message somebody sent. An illustration of a chat room
   is fine; inventing posts, members and reaction counts to sit inside it
   would be inventing a track record, and this site has a Record page for
   exactly the reason that claims here have to be real ones. */
const DISCORD_ROOMS = [
  ["Welcome", ["welcome", "announcements", "rules", "get-started"]],
  ["Posted by the site", ["record", "picks", "anchors"]],
  ["Premium", ["premium-picks", "player-props", "live-alerts",
               "lineup-drops", "nba-dfs", "nfl-dfs", "mlb-dfs"]],
  ["Community", ["chat", "wins", "giveaways", "feedback"]],
];

function discordRoomsHTML() {
  return `
    <div class="dc-mock" aria-hidden="true">
      <div class="dc-mock-head">${iconMark("discord", 15)}
        <b>QELLYS BOOK</b></div>
      ${DISCORD_ROOMS.map(([group, rooms]) => `
        <div class="dc-mock-group">${escapeHtml(group)}</div>
        <ul class="dc-mock-list">${rooms.map((r) => `
          <li><span class="dc-hash">#</span>${escapeHtml(r)}</li>`).join("")}
        </ul>`).join("")}
    </div>`;
}

/* WHAT THE SITE POSTS BY ITSELF (engine/discordfeed, engine/witness;
   Ethan, 2026-10-06: "every single night when bets settle, it'll
   automatically post that day's record to the Discord"). The three
   channels, whether each is switched on (web/data/community.json says
   so; it never carries a webhook), and the last posts that went to the
   public one, word for word. Nothing here is written for the page: a
   post shows only after Discord took it. */
const DISCORD_FEED = [
  ["record", "Public", "Last night’s record once every pick has graded: W-L, units, the hit rate against what we said, the best hit and the toughest miss. The week, every Tuesday."],
  ["picks", "Members", "The Pick of the Day the moment it locks, the day’s board when it goes up, and any long shot that cashes."],
  ["anchors", "Public", "The record’s fingerprint, stamped on Bitcoin — the proof on the Verify page."],
];

function dcPostHTML(p) {
  const when = String(p.at || "").replace("T", " ").slice(0, 16);
  const body = escapeHtml(String(p.text || "")).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  return `<article class="card dc-feed-post"><time>${escapeHtml(when)} UTC · #record</time>${body}</article>`;
}

function dcFeedHTML(feed) {
  const ch = (feed && feed.channels) || {};
  const posts = ((feed && feed.posts) || []).slice(0, 5);
  return `
    <h2 class="dc-h2 dc-h2-mid">Posted by the site, by itself</h2>
    <ul class="dc-live">${DISCORD_FEED.map(([name, who, what]) => `
      <li><span class="dc-hash">#${name}</span><span><b>${who}.</b> ${escapeHtml(what)}${
        feed && !ch[name] ? ` <span class="dc-off">(not switched on yet)</span>` : ""}</span></li>`).join("")}
    </ul>
    <h2 class="dc-h2 dc-h2-mid">Latest in #record</h2>
    <div class="dc-feed">${posts.length ? posts.map(dcPostHTML).join("")
      : `<p class="dc-feed-empty">The first post goes up the morning after the next night that grades.
           Until then, every result is on the <a href="#record">Record</a> page.</p>`}</div>`;
}

function discordPageHTML(s, welcome, feed) {
  const invite = s && s.discord;
  const gram = s && s.instagram;
  const year = new Date().getFullYear();

  /* The one button, in its three honest states. Entitled with an invite
     configured: go. Entitled with none: say so plainly rather than
     drawing a dead button — that is a server that has not been finished
     being set up, and pretending otherwise wastes the reader's click.
     Not entitled: the plans. */
  const cta = invite
    ? `<a class="btn primary dc-go" href="${safeHref(invite)}"
          target="_blank" rel="noopener noreferrer">
         ${iconMark("discord", 18)} Join the Discord</a>`
    : (s && s.entitled
        ? `<p class="dc-pending">The invite link is not configured on this
             server yet. It will appear here the moment it is.</p>`
        : `<button class="btn primary dc-go" data-act="dcSeePlans">
             See the plans</button>`);

  const note = invite
    ? `<span class="dc-fine">${icon("lock")} Private server · included
         with your plan</span>`
    : (s && s.entitled ? ""
        : `<span class="dc-fine">${icon("lock")} The server is for
             subscribers — the picks are posted there.</span>`);

  return `
  <div class="dc">
    ${welcome ? `
    <div class="dc-toast" role="status">
      <span class="dc-toast-ic">${iconMark("check", 16)}</span>
      <div><b>Account created</b><span>Welcome to Qellys Book.</span></div>
    </div>` : ""}

    <header class="dc-hero">
      ${welcome ? `<p class="dc-eyebrow">Welcome to</p>` : ""}
      <h1 class="dc-h1">QELLYS <b>BOOK</b></h1>
      ${welcome
        ? `<p class="dc-lede">Your account is all set. You’re in.</p>
           <p class="dc-sub">The next step is the room where the picks get
             posted — our ${'' /* no superlatives we cannot stand behind */}
             members’ Discord.</p>`
        : `<p class="dc-lede">The members’ Discord.</p>
           <p class="dc-sub">The room where the picks get posted, and where
             you can ask about any of them.</p>`}
    </header>

    <section class="card dc-main">
      <div class="dc-main-words">
        <h2 class="dc-h2">Join the <em>Qellys</em> Discord</h2>
        <p class="dc-body">This is the point of the server: Ethan goes
          through the board and picks out the ones he thinks are winners,
          and posts them as he takes them. Everything else — the alerts,
          the projections, the chat — is around that.</p>
        ${gram ? `<p class="dc-body">It is the same thing he has been
          posting publicly on <a href="${safeHref(gram)}" target="_blank"
          rel="noopener noreferrer">Instagram</a> — he puts that run at
          <b>+400 units</b>. That is his own count, on his own page;
          what this site publishes is graded here, pick by pick, on the
          <a href="#record">Record</a> page.</p>`
        : `<p class="dc-body">Every pick this site makes is graded in
          public on the <a href="#record">Record</a> page — the Discord is
          where the ones Ethan is personally on get called out.</p>`}
        <ul class="dc-perks">
          ${DISCORD_PERKS.map((p) => `
            <li>${iconMark("check", 15)}${escapeHtml(p)}</li>`).join("")}
        </ul>
      </div>
      ${discordRoomsHTML()}
    </section>

    ${dcFeedHTML(feed)}

    <section class="card dc-cta">
      <div class="dc-cta-ic">${iconMark("discord", 30)}</div>
      <div class="dc-cta-words">
        ${invite || (s && s.entitled)
          ? `<h2 class="dc-h2">Don’t miss the edge</h2>
             <p class="dc-body">Join now and we’ll see you inside.</p>`
          // Telling somebody who cannot get in that we will see them
          // inside is the kind of small lie that makes a whole page
          // read like marketing rather than a product.
          : `<h2 class="dc-h2">The room comes with the plan</h2>
             <p class="dc-body">Subscribe and the invite is waiting on your
               account page — every plan, same room.</p>`}
      </div>
      <div class="dc-cta-go">${cta}${note}</div>
    </section>

    <h2 class="dc-h2 dc-h2-mid">What you get inside</h2>
    <div class="dc-grid">
      ${DISCORD_INSIDE.map(([ic, title, body]) => `
        <article class="card dc-card">
          <div class="dc-card-ic">${iconMark(ic, 20)}</div>
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(body)}</p>
        </article>`).join("")}
    </div>

    <footer class="dc-foot">
      <div>
        <span class="pw-brand small">${brandMarkHTML(22)}
          <span class="pw-brand-words">QELLYS <b>BOOK</b></span></span>
        <p>© ${year} Qellys Book. All rights reserved.</p>
      </div>
      <div>
        <b>${icon("shield")} Your details stay yours</b>
        <p>We never sell or share your information. See the
          <a href="privacy.html">Privacy Policy</a>.</p>
      </div>
      <div>
        <b>Not sure where to start?</b>
        <p>Read <a href="#why">how the picks are made</a>${invite
          ? `, or ask in the server — somebody will answer`
          : `, and check the <a href="#record">Record</a> before you pay
             for anything`}.</p>
      </div>
    </footer>
  </div>`;
}

function dcTakeWelcome() {
  let had = false;
  try {
    had = localStorage.getItem(DC_WELCOME_KEY) === "1";
    if (had) localStorage.removeItem(DC_WELCOME_KEY);
  } catch (e) {}
  return had;
}

let _dcFeed = null;           // web/data/community.json, once read

async function renderDiscord() {
  const host = document.getElementById("view-discord");
  if (!host) return;
  const welcome = dcTakeWelcome();
  // Drawn twice on purpose: once immediately from whatever the last
  // status call left behind, so the page is never blank while a request
  // is in flight, and again when the fresh answer lands. The invite is
  // the whole point of the page and it is the part that arrives late.
  host.innerHTML = discordPageHTML(_pwStatus || {}, welcome, _dcFeed);
  const feedP = boardFetch("data/community.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  try {
    const r = await fetch("/api/billing/status", { credentials: "same-origin" });
    _pwStatus = await r.json();
  } catch (e) { /* the first draw stands */ }
  _dcFeed = (await feedP) || _dcFeed;
  host.innerHTML = discordPageHTML(_pwStatus || {}, welcome, _dcFeed);
}

/* THE HERO'S TWO DOORS. Ethan's product audit, 2026-09-23, item 7: a
   visitor's first screen should carry two buttons — the trial and
   the record. The trial button TAKES YOU TO THE PLAN CARD rather than
   straight into checkout: that card is where "card required, becomes
   $X a month on day N" is said before the click, and a hero button
   that skipped it would be the silent conversion the card exists to
   refuse. With no trial on offer it says what it does: the plans. */
function pwHeroCtaHTML(trialDays, anySellable = true) {
  // Nothing on sale (the shop not switched on yet): the record is the one
  // door that goes somewhere, so it is the primary one.
  if (!anySellable) {
    return `<div class="pw-cta">
    <a class="btn primary pw-cta-rec" href="#record">See the record — it’s free</a>
  </div>`;
  }
  return `<div class="pw-cta">
    <button class="btn primary pw-cta-go" type="button" data-act="pwToPlans">${
      trialDays > 0 ? `Start ${trialDays} days free` : "See the plans"}</button>
    <a class="btn ghost pw-cta-rec" href="#record">See the record</a>
  </div>`;
}

async function renderPaywall() {
  const host = document.getElementById("view-paywall");
  if (!host) return;
  // ARRIVED DIRECTLY? Then nobody has asked the server anything yet.
  // `_pwStatus` is filled by the boot check, which only runs its own
  // render when the wall goes up — so on a plain #paywall navigation it
  // is null, and the page would draw with no prices marked sellable and
  // no code box.
  if (!_pwStatus) {
    try { await paywallCheck(); } catch (e) { /* draw what we can */ }
  }
  let rec = null;
  try {
    // boardFetch, not fetch: every board payload on the site goes
    // through it (it tracks which endpoints have answered), and the
    // account block this function sits inside is contracted to call
    // nothing but our own API endpoints directly.
    // no-cache, not no-store: revalidate every time, but let a 304
    // reuse the cached body — the record only moves when a cycle
    // grades something. Same trade fetchAllLive documents.
    const r = await boardFetch("/data/record.json", { cache: "no-cache" });
    // The same record every other surface shows — the pooled book
    // (adoptPooledRecord). This read the file raw and kept quoting the
    // edge book after the site had moved on; Ethan, 2026-09-22: "make
    // sure we are updating the paywall site too with the new info."
    if (r.ok) rec = adoptPooledRecord(await r.json());
  } catch (e) { /* the shop still renders without the proof strip */ }
  /* NO CODE BOX ON THE PLANS PAGE. Ethan, 2026-09-09, with a screenshot
     of it circled: "removing where it lets you put the promo codes in on
     the actual site since you can only put them in on the stripe page."

     He is right about the thing that was confusing. A DISCOUNT code goes
     in Stripe's own field, on Stripe's page — this box never took one and
     never could. It takes a comp code, which is a different object: it
     writes an entitlement here and involves no card at all. Two different
     things wearing one label, three inches above a Pay button.

     The redeem path is NOT gone; it lives on the account page, which is
     in WALL_OPEN, so somebody holding a code can still reach it while
     walled. What is gone is being asked for a code at the moment of
     paying, which is where the two get confused. */
  host.innerHTML = paywallHTML(rec, _pwStatus);
  sweepRings(host);                 // the ribbon's ring sweeps in and its numbers count
  pwDock(host);
  pwReferral(host);
  pwTonight(host);
}

/* Tonight's picks on the plans, the same locked cards as the sign-up's. */
function pwTonight(host) {
  flGet().then((fl) => {
    const slot = host.querySelector(".pw-fl");
    if (slot && fl && (fl.tonight || []).some((x) => Number(x.picks) > 0)) slot.innerHTML = flTonightHTML(fl);
  });
}

/* WHY THE PLANS OPENED (2026-10-25: a locked tab explains itself). A paid
   page tapped without a plan lands here (app.js _wallFrom), and the top of
   the plans says what that page holds before anything asks for money. */
const PW_WHY = {
  recommended: ["Home is tonight’s picks", "The best bets on every board, posted before the game with the price we took."],
  likely: ["Picks is Most Likely", "Every pick tiered by its chance of hitting — the board members open first."],
  ask: ["Ask Qellys is for members", "The AI on any team, player or game, answered from our own numbers."],
  edge: ["Edge is for members", "Where our number and the market’s disagree most, ranked."],
  props: ["The props board is for members", "Every player prop we price, with our chance beside the book’s."],
  longshots: ["Long shots are for members", "The big prices our model still likes, every night."],
  futures: ["Futures are for members", "Season-long prices, with our number against the book’s."],
  alerts: ["Alerts are for members", "Line moves, injuries and your players on tonight’s board, on your phone."],
};

/* TWO WAYS IN, BEFORE ANYTHING ELSE (Ethan, 2026-10-26: "the paywall page
   also makes it seem like everything is still locked on a paid service. It
   doesn't give u an option to create an account or anything ... People need
   to know that there is free features available"). Spotify's and Duolingo's
   plans page: the free way and the paid way side by side, each with its own
   button, ahead of the pitch. The free lines are pages WALL_OPEN opens and
   the member lines are PLAN_FEATURES' own (FL_ROWS, beside the sign-up's
   table), so neither side promises what the other holds. */
function pwDoorsHTML(status, trialDays) {
  const signed = !!(status && status.signed_in);
  const mo = PLANS.find((p) => p.id === "monthly") || PLANS[0];
  const best = PLANS.find((p) => p.id === bestValuePlanId(PLANS));
  const li = (t) => `<li>${iconMark("check", 13)}<span>${escapeHtml(t)}</span></li>`;
  return `<div class="pw-doors" role="region" aria-labelledby="pw-doors-h">
    <h1 class="pw-doors-h" id="pw-doors-h">Free to watch. <em>Members get the picks.</em></h1>
    <div class="pw-doors-row">
      <article class="pw-door free">
        <div class="pw-door-top"><b>Free account</b>${signed ? `<span class="pw-door-you">You have this</span>` : ""}</div>
        <p class="pw-door-price">No card, nothing to cancel</p>
        <ul class="pw-door-list">${FL_ROWS.filter(([, f]) => f).map(([t]) => li(t)).join("")}</ul>
        ${signed ? `<a class="btn ghost pw-door-go" href="#live">Go to the live games</a>`
          : `<button type="button" class="btn ghost pw-door-go" data-act="acctGoSignup">Create a free account</button>`}
      </article>
      <article class="pw-door mem">
        <div class="pw-door-top"><b>Member</b><span class="pw-door-tag">The picks</span></div>
        <p class="pw-door-price">$${mo.price} a month${trialDays > 0 ? ` · ${trialDays} days free` : ""}${
          best && best.id !== mo.id ? ` · or $${planPerMonth(best).toFixed(2)} a month ${escapeHtml(best.name.toLowerCase())}` : ""}</p>
        <ul class="pw-door-list"><li class="pw-door-plus">Everything in the free account, plus:</li>${
          FL_ROWS.filter(([, f]) => !f).map(([t]) => li(t)).join("")}</ul>
        <button type="button" class="btn primary pw-door-go" data-act="pwToPlans">${
          trialDays > 0 ? `Start ${trialDays} days free` : "See the plans"}</button>
      </article>
    </div>
    ${signed ? pwLaterHTML() : ""}
  </div>`;
}

/* NOT TODAY? (the ideas list, 2026-10-26): for a signed-in reader not ready
   to pay, the free "tonight's picks are up" alert — how many, never which
   (engine/pushalerts) — one tap from the plans, so the door stays open
   without a sale. Only where alerts can work (app.js pushKind); once on,
   it says so instead of asking again. */
function pwLaterHTML() {
  const kind = typeof pushKind === "function" ? pushKind() : "";
  if (kind !== "web" && kind !== "native") return "";
  const saved = pushSaved();
  if (saved && saved.endpoint && (saved.topics || []).includes("posted")) return pwLaterOnHTML();
  return `<div class="pw-later">
    <button type="button" class="btn ghost" data-pwlater="1">${icon("bell", 14)}<span>Not today — tell me when picks are up</span></button>
    <p class="pw-later-note" role="status">A tap on your lock screen when tonight’s picks post: how many, never which.</p></div>`;
}
// Its own off switch, here: the Alerts page's switches are a members' page.
function pwLaterOnHTML() {
  return `<p class="pw-later on" role="status">${iconMark("bell", 13)}<span>You’ll hear when tonight’s picks are up.</span>
    <button type="button" class="pw-later-off" data-pwlater="off">Turn off</button></p>`;
}
async function pwLater(btn) {
  const wrap = btn.closest(".pw-later");
  const note = wrap && wrap.querySelector(".pw-later-note");
  btn.disabled = true;
  if (btn.dataset.pwlater === "off") {
    // Off for this alert only: whatever else this phone was told stays.
    const saved = pushSaved() || {};
    const rest = (saved.topics || []).filter((t) => t !== "posted");
    try {
      if (rest.length || (saved.mine || []).length) {
        await pushSend("subscribe", { endpoint: saved.endpoint, kind: pushKind() === "native" ? "apns" : "web",
          topics: rest.concat(saved.mine || []) });
        try { localStorage.setItem(PUSH_KEY, JSON.stringify(Object.assign({}, saved, { topics: rest }))); } catch (e) {}
      } else {
        await pushOff(saved);
        try { localStorage.removeItem(PUSH_KEY); } catch (e) {}
      }
      if (wrap) wrap.outerHTML = pwLaterHTML();
    } catch (err) {
      btn.disabled = false;
    }
    return;
  }
  try {
    // The alerts already chosen on this phone stay chosen; "posted" joins them.
    const saved = pushSaved() || {};
    const topics = [...new Set((saved.topics || []).concat("posted"))];
    const got = await pushOn(topics.concat(saved.mine || []));
    const mine = (t) => t === "watches" || t === "bets" || t === "kickoff" || t === "clutch" || t === "finals" || t === "lineup";
    try { localStorage.setItem(PUSH_KEY, JSON.stringify(Object.assign({}, got, {
      topics: got.topics.filter((t) => !mine(t)), mine: got.topics.filter(mine) }))); } catch (e) {}
    buzz("tap");
    if (wrap) wrap.outerHTML = pwLaterOnHTML();
  } catch (err) {
    btn.disabled = false;
    if (note) note.textContent = (err && err.message) || "That did not work — try again.";
  }
}

/* A plan tapped before the account exists: the sign-up first, the plan kept
   (rememberPendingPlan), checkout straight after (acctLandAfterAuth). */
let _suNote = "";
function pwJoin(id) {
  const pl = PLANS.find((p) => p.id === id);
  if (!pl) return;
  rememberPendingPlan(pl.id);
  _suNote = `Make your free account first — checkout opens on the ${pl.name.toLowerCase()} plan right after.`;
  switchView("signup", true);
  window.scrollTo({ top: 0, behavior: "auto" });
}

function pwWhyHTML() {
  const v = typeof _wallFrom === "string" ? _wallFrom : "";
  if (!v) return "";
  const [h, p] = PW_WHY[v] || ["That page is for members",
    "Members get the picks, every board and the tools. Your free account keeps every game live."];
  return `<div class="pw-why" role="status">${iconMark("lock", 16)}<div><b>${escapeHtml(h)}</b>
    <p>${escapeHtml(p)}</p></div></div>`;
}

/* A FRIEND'S CODE ON THE ACCOUNT (engine/referrals): said at the top of the
   plans, where the $6.25 will be taken off — Stripe's page shows it as the
   coupon, and nobody should meet it there for the first time. */
async function pwReferral(host) {
  if (!(_pwStatus && _pwStatus.email)) return;
  let v = null;
  try {
    const r = await fetch("/api/account/referral", { credentials: "same-origin", cache: "no-store" });
    if (r.ok) v = await r.json();
  } catch (e) { v = null; }
  if (!v || !v.used_code || host.querySelector(".pw-ref")) return;
  const top = host.querySelector(".pw-hero, .pw") || host.firstElementChild;
  if (top) top.insertAdjacentHTML("afterbegin", `<p class="pw-ref">${icon("people", 15)} Your friend’s code
    <b>${escapeHtml(v.used_code)}</b> takes $6.25 off your first payment — you’ll see it on the payment page.</p>`);
}

/* THE BUTTON STAYS IN REACH (2026-10-25; Ethan: "the paywall page and all
   that stuff ... needs to be curated to work for an app"). A store app's
   plans screen keeps its one button pinned above the tab bar while the
   reader scrolls the proof; this page put it in the hero and then ran
   two screens of receipts before the plans. On a phone the hero's own
   button rides along at the bottom — the same words, the same action —
   and steps aside once the plans are on screen, where their own buttons
   take over. Nothing is drawn when the hero has no plan to offer. */
function pwDock(host) {
  const go = host.querySelector(".pw-cta-go");
  const plans = host.querySelector(".pw-plans");
  if (!go || !plans) return;
  const monthly = PLANS.find((p) => p.id === "monthly");
  const trial = /days free/.test(go.textContent);
  const fine = trial && monthly ? `then $${monthly.price} a month · cancel anytime` : "Cancel anytime";
  host.insertAdjacentHTML("beforeend", `<div class="pw-dock" role="region" aria-label="Start">
      <button class="btn primary pw-dock-go" type="button" data-act="pwToPlans">${escapeHtml(go.textContent.trim())}</button>
      <span class="pw-dock-fine">${escapeHtml(fine)}</span></div>`);
  const dock = host.querySelector(".pw-dock");
  if (typeof IntersectionObserver !== "function") return;
  new IntersectionObserver((seen) => {
    dock.classList.toggle("away", seen.some((e) => e.isIntersecting));
  }, { threshold: 0.15 }).observe(plans);
}

/* WHICH PLAN, IN WORDS, ON THE ACCOUNT PAGE.
   ---------------------------------------------------------------------
   Ethan, 2026-08-22: "on the account page make sure we show exactly what
   plan they are subscribed too."

   It said "Subscribed — renews 21 Sep 2026." and stopped. That is a
   status, not an answer: it does not say monthly or yearly, what it
   costs, or what the next charge will be. Somebody who bought six months
   and sees a date four weeks out has no way to tell whether they are on
   the plan they think they are, and the place they go next is a
   chargeback or a support email.

   Every line here comes from the server's own record of the
   subscription. Where the server does not know a thing, the line is not
   drawn — an account page that guesses is worse than one that is quiet. */
function planPanelHTML(s) {
  if (!s || !s.entitled) return "";
  const plan = PLANS.find((p) => p.id === s.plan);
  const when = s.period_end
    ? new Date(s.period_end * 1000).toLocaleDateString([],
        { year: "numeric", month: "long", day: "numeric" })
    : "";
  const trial = String(s.status || "") === "trialing";
  // Cancelled to run out at the period's end (billing.read_event).
  const ending = s.cancel_at_end || String(s.status || "") === "canceled";

  // A settings row (setItem) per fact.
  const row = (k, v) => v
    ? setItem({ title: k, val: v }) : "";

  return setGroup("Your plan", [
    setItem({ ico: "gem", tone: "gold",
              title: plan ? escapeHtml(plan.name) + " plan"
                          : (s.comped ? "Complimentary access" : "Your subscription"),
              end: `<span class="chip ${trial || ending ? "warn" : "good"}">${
                trial ? "Free trial" : ending ? "Cancelled" : "Active"}</span>` }),
    row("Price", plan ? `$${plan.price} per ${escapeHtml(plan.per)}` : ""),
    row(trial ? "Trial ends" : ending ? "Access until" : "Renews", when),
    row(trial && plan ? "Then" : "",
        trial && plan ? `$${plan.price} per ${escapeHtml(plan.per)}` : ""),
    row("Started with a code", s.codes && s.codes.active ? "Yes" : ""),
  ], ending ? "Cancelled. Nothing further will be charged and your access runs to the date above."
    : trial ? "Cancel before the trial ends and you are not charged at all — Manage billing, below."
    : s.comped ? "This account was given access directly — there is no card on file and nothing to cancel."
    : "");
}

async function renderBilling() {
  if (!document.getElementById("billing-slot") && !document.getElementById("set-plan")
      && !document.querySelector(".set-code")) return;
  let s;
  try {
    const r = await fetch("/api/billing/status", { credentials: "same-origin" });
    s = await r.json();
  } catch (e) {
    const failed = document.getElementById("billing-slot");
    if (failed) failed.innerHTML = "";
    return;
  }
  // The Membership group on the settings list (settingsHTML) …
  _billStatus = s || false;
  const rows = document.getElementById("set-plan");
  if (rows) rows.innerHTML = planRowsHTML(_billStatus);
  codeScreenRedraw(s);
  // … and the plan's own screen, when it is the one open.
  const slot = document.getElementById("billing-slot");
  if (!slot) return;
  if (!s || !s.signed_in) { slot.innerHTML = ""; return; }
  /* THE CODE BOX DOES NOT DEPEND ON THE PROCESSOR, and the old shape did:
     an unconfigured processor returned early and took the whole panel
     with it. A redeemed code involves no money and no processor, so it
     has to survive that — it is the only way in before the Stripe keys
     are on the box, and it stays the way Ethan comps somebody after. */
  const codes = s.codes || {};
  // NO "FREE" PLAN: there is none (tests/test_free_trial.py). Somebody
  // without one is told so, with the server's own sentence for why when
  // there is more to say than that (payment failed, cancelled, paused).
  const none = setGroup("Your plan", [setItem({ ico: "gem", tone: "gold", title: "No membership",
    sub: s.note && s.note !== "No subscription." ? escapeHtml(s.note) : "" })], s.configured ? "" : s.paywall
    ? "Card payment is not switched on on this server yet. Access is by code for now — if you have one, enter it below."
    : "Everything is free right now, so there is nothing to pay for. A code still works and starts its clock from the day you enter it.");
  slot.innerHTML = (s.configured ? `
    ${s.entitled ? planPanelHTML(s) + yearlyOfferHTML(s) : none}
    ${s.customer_id
      // Only with somebody to bill. Entitled with nobody — a comped
      // address or a redeemed code — "Manage billing" opened Stripe's
      // portal for a customer that does not exist and came back an error.
      ? setGroup("", [setItem({ ico: "card", tone: "gold", title: "Manage billing",
                                sub: "Your card, receipts, or cancelling — on Stripe’s own page",
                                chev: true, attrs: 'data-act="billPortal"' })],
                 s.live === false ? "Stripe test mode — no real money moves." : "")
        + `<p class="set-foot bill-note" role="status"></p>`
      : ""}
    ${s.entitled ? "" : billPlansHTML(s)}`
  : s.entitled ? planPanelHTML(s) : none)
    // NO DISCORD BOX HERE ANY MORE. Ethan, 2026-08-22: "we can remove
    // the discord button in the account tab." There are now two better
    // places for it — the icon in the top bar, which is on every page,
    // and the #discord page, which is what the welcome after paying
    // lands on. A third copy on the account panel was the version
    // somebody had to go looking for.
    + codeBoxHTML(codes);
}

/* YEARLY AT MONTH TWO (2026-10-28, engine/billing.yearly_offer; docs/IDEAS.md).
   A monthly member past their second bill sees the switch here once: "See
   the switch" opens Stripe's own page confirming it, with the new price and
   what this month's bill credits, before anything is charged; "Not now"
   puts it away on this device. Off until the server's QB_YEARLY_OFFER is on. */
const YEARLY_SEEN_KEY = "qb_yearly_seen";
function yearlyOfferHTML(s) {
  const o = s && s.yearly_offer;
  if (!o) return "";
  try { if (localStorage.getItem(YEARLY_SEEN_KEY)) return ""; } catch (e) { /* storage off: shown */ }
  const usd = (c) => `$${(Number(c) / 100).toFixed(Number(c) % 100 ? 2 : 0)}`;
  return `<div class="set-yearly">${setGroup("Switch to yearly", [
    setItem({ ico: "gem", tone: "gold", title: `Save ${usd(o.save_cents)} a year`, chev: true, attrs: 'data-yearly="go"',
              sub: `${usd(o.yearly_cents)} once a year instead of $25 a month. Stripe shows what this month’s bill credits before anything is charged.` }),
    setItem({ title: "Not now", attrs: 'data-yearly="no"' })])}</div>`;
}
if (typeof window !== "undefined" && !window._yearlyBound) {
  window._yearlyBound = true;
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-yearly]");
    if (!b) return;
    if (b.dataset.yearly === "go") { _billGo(b, "yearly"); return; }
    try { localStorage.setItem(YEARLY_SEEN_KEY, "1"); } catch (err) { /* gone for this visit only */ }
    const box = b.closest(".set-yearly");
    if (box) box.remove();
  });
}

/* GIFT A MONTH (2026-10-28, engine/gifts; docs/IDEAS.md). A month for a
   friend, $25 once on Stripe's Checkout, delivered as a code to send: they
   enter it under Redeem a code. Coming back from Checkout (?gift=1&s=…),
   the screen asks the server to read the payment off Stripe, so the code is
   here even before Stripe's own word arrives. */
if (typeof location !== "undefined" && /[?&]gift=1(&|$)/.test(location.search)) window._setOpen = "gift";
async function giftFill() {
  const box = document.getElementById("set-gift");
  if (!box) return;
  const q = new URLSearchParams(location.search);
  const sid = q.get("gift") === "1" ? q.get("s") || "" : "";
  let v = null;
  try {
    if (/^cs_[A-Za-z0-9_]{8,200}$/.test(sid)) {
      try { const u = new URL(location.href); u.searchParams.delete("gift"); u.searchParams.delete("s"); history.replaceState(null, "", u.toString()); } catch (e) { /* the address keeps it */ }
      const r = await fetch("/api/billing/gift_confirm", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ s: sid }) });
      v = r.ok ? await r.json() : null;
    }
    if (!v) { const r = await fetch("/api/billing/gifts", { credentials: "same-origin", cache: "no-store" }); v = r.ok ? await r.json() : null; }
  } catch (e) { v = null; }
  if (box.isConnected) box.innerHTML = giftHTML(v, !!sid);
}
function giftHTML(v, back) {
  const list = (v && v.gifts) || [];
  const buy = v && v.on ? setGroup("", [setItem({ ico: "ticket", tone: "gold", title: "Buy a month for a friend", chev: true, attrs: 'data-gift="buy"',
      sub: "$25, once — not a subscription. You get a code to send; they enter it under Redeem a code for a month of everything." })],
    "Card details go to Stripe, never to this server.") : `<p class="set-foot">Gifts aren’t on yet.</p>`;
  const wait = back && !list.length ? `<p class="set-foot">Stripe is confirming the payment — your code appears here in a moment. Pull to refresh if it doesn’t.</p>` : "";
  const mine = list.length ? setGroup("Your gifts", list.map((g) => setItem({ ico: "ticket", tone: "gold", title: escapeHtml(g.code),
    sub: g.redeemed ? "Used" : "Not used yet — tap to send it", attrs: g.redeemed ? "" : `data-gift-share="${escapeAttr(g.code)}"` })),
    "A code works once, for a month from the day it is entered.") : "";
  return wait + mine + buy + `<p class="set-foot bill-note" role="status"></p>`;
}
if (typeof window !== "undefined" && !window._giftBound) {
  window._giftBound = true;
  document.addEventListener("click", async (e) => {
    const b = e.target.closest && e.target.closest("[data-gift], [data-gift-share]");
    if (!b) return;
    if (b.dataset.gift === "buy") { _billGo(b, "gift"); return; }
    const text = `A month of Qellys Book, on me. Enter ${b.dataset.giftShare} under Settings → Redeem a code at ${location.origin}`;
    try {
      if (navigator.share) await navigator.share({ title: "A month of Qellys Book", text });
      else { await navigator.clipboard.writeText(text); const t = b.querySelector(".set-sub"); if (t) t.textContent = "Copied — send it to them"; }
    } catch (err) { /* the reader closed the sheet */ }
  });
}

/* PASSKEYS (2026-10-28, engine/passkeys; docs/IDEAS.md 8). Face ID, Touch ID
   or the phone's own lock instead of a password or a texted code: added in
   Settings once signed in, used from the sign-in card. Only where the
   browser can (WebAuthn), and not inside the iPhone app, whose web view
   needs the app's own passkey entitlement first (runbook GA). The server
   checks every answer; this only carries bytes between it and the device. */
const pkOK = () => typeof window !== "undefined" && !!window.PublicKeyCredential
  && !!(navigator.credentials && navigator.credentials.create)
  && !(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
const pkBytes = (s) => Uint8Array.from(atob(String(s).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const pkB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
let _pkList = null;
async function pkPost(step, body) {
  const r = await fetch(`/api/passkey/${step}`, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(out.error || "Couldn’t reach the server — try again.");
  return out;
}
// THE CHALLENGE IS FETCHED BEFORE THE TAP. Safari opens the passkey prompt
// only close behind a tap, and a round trip to the box in between can cost
// it; so the screen asks for the next ceremony's options as it draws, and
// the tap goes straight to the device. Each is used once, and only while
// well inside the box's three minutes; otherwise the tap fetches its own.
const PK_NONE = { kind: "", at: 0, p: null };
let _pkPre = PK_NONE;
function pkPrefetch(kind) {
  if (_pkPre.kind === kind && Date.now() - _pkPre.at < 120000) return;
  const pre = { kind, at: Date.now(), p: pkPost(`${kind}-options`) };
  _pkPre = pre;
  pre.p.catch(() => { if (_pkPre === pre) _pkPre = PK_NONE; });
}
// The options fetched ahead (or still on their way), once; else its own.
function pkOptions(kind) {
  const pre = _pkPre;
  _pkPre = PK_NONE;
  return pre.kind === kind && Date.now() - pre.at < 120000 ? pre.p.catch(() => pkPost(`${kind}-options`)) : pkPost(`${kind}-options`);
}
// What the device is, to name the passkey it makes ("iPhone", "Mac").
function pkDeviceName() {
  const ua = navigator.userAgent || "";
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android phone"
    : /Macintosh/.test(ua) ? (navigator.maxTouchPoints > 1 ? "iPad" : "Mac") : /Windows/.test(ua) ? "Windows PC"
    : /CrOS/.test(ua) ? "Chromebook" : /Linux/.test(ua) ? "Linux computer" : "Passkey";
}
// What unlocks a passkey on this device, in its maker's words.
function pkLock() {
  const d = pkDeviceName();
  return d === "iPhone" || d === "iPad" || d === "Mac" ? ["Face ID · Touch ID", "Face ID or Touch ID"]
    : d === "Android phone" ? ["Fingerprint · face", "your fingerprint or face"]
    : d === "Windows PC" ? ["Windows Hello", "Windows Hello"] : ["No password", "this device’s lock"];
}
// A refusal from the device, in a sentence: cancelled is not an error.
function pkSay(err) {
  const n = err && err.name;
  if (n === "NotAllowedError" || n === "AbortError") return "Cancelled — nothing changed.";
  if (n === "InvalidStateError") return "This device already has a passkey for this account.";
  if (n === "SecurityError") return "Passkeys need the site’s own https address.";
  if (n === "NotSupportedError") return "This device can’t make a passkey.";
  return (err && err.message) || "That didn’t work — try again.";
}
function pkHTML() {
  if (_pkList === null) return `<p class="set-foot">Loading…</p>`;
  const when = (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  const rows = _pkList.map((k) => setItem({ ico: "shield", tone: "gold", title: escapeHtml(k.name),
    sub: escapeHtml(`Added ${when(k.made)}${k.used ? ` · last used ${when(k.used)}` : ""}`),
    end: `<button type="button" class="set-val pk-rm" data-pk="remove" data-id="${escapeAttr(k.id)}" aria-label="${escapeAttr(`Remove ${k.name}`)}">Remove</button>`,
    tag: "div" }));
  return (rows.length ? setGroup("On this account", rows) : "")
    + setGroup("", [setItem({ ico: "shield", tone: "gold", title: "Add a passkey", sub: `Use ${pkLock()[1]} to sign in`,
                              chev: true, attrs: 'data-pk="add"' })],
      "A passkey stays on your device; this site keeps only the half that can check it. Your face and fingerprint never leave the phone.")
    + `<p class="set-foot pk-note" role="status"></p>`;
}
async function pkFill() {
  const box = document.getElementById("set-pk");
  if (!box) return;
  try {
    const r = await fetch("/api/passkey/list", { credentials: "same-origin", cache: "no-store" });
    _pkList = r.ok ? ((await r.json()).passkeys || []) : [];
  } catch (e) { _pkList = []; }
  if (box.isConnected) box.innerHTML = pkHTML();
  pkPrefetch("register");
}
async function pkAdd() {
  const o = await pkOptions("register");
  const cred = await navigator.credentials.create({ publicKey: { ...o, challenge: pkBytes(o.challenge),
    user: { ...o.user, id: pkBytes(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: pkBytes(c.id) })) } });
  const r = cred.response;
  const out = await pkPost("register", { clientDataJSON: pkB64(r.clientDataJSON),
    attestationObject: pkB64(r.attestationObject), name: pkDeviceName() });
  _pkList = out.passkeys || _pkList;
}
// Signing in: the device lists this site's passkeys, the person picks one.
async function pkSignIn(card) {
  const say = (t) => { const n = card.querySelector(".acct-note"); if (n) n.textContent = t; };
  say("Waiting for your passkey…");
  try {
    const o = await pkOptions("login");
    const cred = await navigator.credentials.get({ publicKey: { ...o, challenge: pkBytes(o.challenge), allowCredentials: [] } });
    const r = cred.response;
    say("Signing in…");
    const out = await pkPost("login", { id: cred.id, rawId: pkB64(cred.rawId), clientDataJSON: pkB64(r.clientDataJSON),
      authenticatorData: pkB64(r.authenticatorData), signature: pkB64(r.signature),
      userHandle: r.userHandle ? pkB64(r.userHandle) : "" });
    // Signed in: the same steps a phone sign-in takes (phoneGo).
    _acctUser = { signed_in: true, email: out.email, phone: out.phone };
    if (typeof pushRelink === "function") pushRelink();
    welcomeDone();
    if (typeof a2hsArm === "function") a2hsArm();
    if (typeof acceptPendingInvite === "function") acceptPendingInvite();
    try { await acctSync(); } catch (e) {}
    if (typeof renderGreeting === "function") renderGreeting();
    return acctLandAfterAuth();
  } catch (e) { say(pkSay(e)); pkPrefetch("login"); }
}
function pkDoorHTML() {
  if (!pkOK()) return "";
  setTimeout(() => pkPrefetch("login"), 0);
  return `<button type="button" class="acct-forgot ph-door pk-door" data-pk="signin">Sign in with a passkey</button>`;
}
if (typeof window !== "undefined" && !window._pkBound) {
  window._pkBound = true;
  document.addEventListener("click", async (e) => {
    const b = e.target.closest && e.target.closest("[data-pk]");
    if (!b || b.disabled) return;
    const act = b.dataset.pk;
    if (act === "signin") {
      const card = b.closest(".card");
      if (!card) return;
      b.disabled = true;
      try { await pkSignIn(card); } finally { b.disabled = false; }
      return;
    }
    const note = (t) => { const n = document.querySelector(".pk-note"); if (n) n.textContent = t; };
    const paint = (t) => { const box = document.getElementById("set-pk"); if (box) box.innerHTML = pkHTML(); note(t); pkPrefetch("register"); };
    b.disabled = true;
    try {
      if (act === "add") {
        note("Follow your device’s prompt…");
        await pkAdd();
        paint("Added. Next time, sign in with it — no password.");
      } else if (act === "remove") {
        _pkList = (await pkPost("remove", { id: b.dataset.id })).passkeys || [];
        paint("Removed. That device’s passkey no longer signs in here; delete it from the device too.");
      }
    } catch (err) { b.disabled = false; note(pkSay(err)); if (act === "add") pkPrefetch("register"); }
  });
}

/* The code's own screen (Settings › Redeem a code), redrawn from a fresh
   status: a code just applied shows what it covers. */
function codeScreenRedraw(s) {
  const own = document.querySelector(".set-code");
  if (own && s) own.innerHTML = codeBoxHTML(s.codes || {});
}

/* "Have a code?" — Ethan, 2026-08-20. Kept beside the subscribe control
   rather than on a page of its own, because somebody holding a code and
   somebody about to pay are at the same moment in the same decision, and
   a code box nobody finds is a support email. */
function codeBoxHTML(codes) {
  const held = (codes.codes || []).map((c) => setItem({ ico: "ticket", tone: "gold", title: escapeHtml(c.code),
    val: `${c.months} month${c.months === 1 ? "" : "s"} · through ${
      new Date((c.granted_to || 0) * 1000).toLocaleDateString()}` })).join("");
  // Not an .acct-note: those all carry the account's sync line (acctPaintNote).
  return `
    <section class="set-group code-box">
      <h2 class="set-group-h code-head">Have a code?</h2>
      <div class="set-list">
        <div class="set-item code-row">
          <input class="code-in" id="code-in" type="text"
                 autocomplete="off" spellcheck="false"
                 placeholder="Enter your code" aria-label="Discount code">
          <button class="btn primary" data-act="redeemCode">Apply</button>
        </div>${held}
      </div>
      <p class="set-foot code-note" id="code-note" role="status"></p>
      ${codes.active ? `<p class="set-foot">Your code covers you through
        <b>${new Date((codes.granted_to || 0) * 1000).toLocaleDateString()}</b>.
        No card is involved and there is nothing to cancel.</p>` : ""}
    </section>`;
}

/* One card, mounted on both My Bets and Fantasy. Handlers find their
   inputs through the card element itself, so the two mounts never fight
   over ids. */
/* ---------------- The account screen -------------------------------------

   Ethan, 2026-08-16: "the login page is hidden and should be on the main
   screen with maybe an account icon in the top right … it needs to look
   professional."

   It WAS hidden, and the diagnosis is worth keeping because the shape
   recurs: the sign-in form existed, worked, and was well tested — it was
   simply mounted three cards down inside My Bets, reachable only by
   pressing an unlabelled person glyph. Nothing was broken. It just had no
   address of its own, and a thing with no address cannot be linked to,
   cannot be bookmarked, and cannot be the destination of "you need an
   account for that".

   That last one is why this is the piece the paywall waits on: every
   locked board is about to need somewhere to send people.

   ONE COLUMN, NOT A CARD IN A STACK. A sign-in screen is the one page
   where a narrow measure is right — there is a single thing to do, and
   the width of a data table would leave the form stranded in a field of
   nothing. */
function acctScreenHTML() {
  const u = _acctUser;
  // Signed in, the account behind the profile — sign-in, plan, devices,
  // data — is the settings screen's own groups (settingsHTML, 2026-10-25):
  // there is no second card above them saying the email twice.
  if (u && u.signed_in) return "";
  // Signed out. A legacy PIN profile, if this device still has one, goes
  // BELOW the sign-in rather than above it: it is the old thing being
  // replaced, and putting it first would make the upgrade look optional.
  const legacy = acctState() ? acctLegacyCardHTML() : "";
  // Render 1/2's sign-in screen: the wordmark over the card, on a wash.
  // Their tagline was "DATA. EDGE. PROFITS." — a promise of profit is
  // the one thing this site will not print, so ours says what the page
  // actually does.
  return `<div class="acct-screen">
    <div class="acct-hero">
      <span class="acct-hero-mark" aria-hidden="true">
<img class="qmark" src="logo-qb.png" width="152" height="152"
             alt="" decoding="async" />
      </span>
      <span class="acct-hero-words">Qellys <span>Book</span></span>
      <span class="acct-hero-tag">Priced by a model. Graded in public.</span>
      <p class="acct-screen-sub acct-hero-sub">Sign in to Qellys Book —
        one account carries your bet log, your fantasy leagues and your
        subscription to every device you use.</p>
    </div>
    ${acctSignInHTML()}
    <p class="acct-assure">The site takes no bets and never holds your money.
      Card details go to Stripe, never to this server.</p>
    ${legacy}
  </div>`;
}

/* Re-rendered whenever the server's answer changes — a screen still
   showing the sign-in form after a successful sign-in is the commonest
   way a page like this feels broken. */
/* WHAT MEMBERS GET, SHOWN BEFORE THE ACCOUNT EXISTS (Ethan, 2026-10-25: "go
   deeper on the free paid wall for when u sign into the site or first get
   onto the site. look at other apps ... we can show our paid features on
   the sign up site"). The store apps' paywall, built from what each does
   best and kept honest:
     - the picks waiting tonight, as locked cards that carry only their
       count (the widget's and the "picks are up" alert's own number) —
       OddsJam's and Action's locked boards;
     - last night and the record, the only proof this site sells on;
     - the newest graded pick in full, win or lose — the FT's "view a
       sample" before you register;
     - Free beside Member, Duolingo's table, and the three plans with the
       trial's days laid out, Blinkist's timeline.
   Every number comes off /api/firstlook (engine/firstlook); none is
   written here. */
let _fl = null;
let _flAsk = null;
function flGet() {
  if (!_flAsk) {
    _flAsk = fetch("/api/firstlook", { credentials: "same-origin", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((d) => { _fl = d; if (!d) _flAsk = null; return d; });
  }
  return _flAsk;
}

/* HOW MANY ARE HERE (engine/firstlook proof, the ideas list's "true social
   proof"): accounts made this week and pages in a game's room right now.
   Real counts, each sent only once it clears its floor on the server, and
   never rounded up or padded here — real or not shown. */
function flProofHTML(fl) {
  const p = (fl && fl.proof) || {};
  const week = Math.floor(Number(p.week) || 0), rooms = Math.floor(Number(p.rooms) || 0);
  const parts = [];
  if (week > 0) parts.push(`<span><b>${week.toLocaleString()}</b> accounts made this week</span>`);
  if (rooms > 0) parts.push(`<span><i class="fl-proof-live" aria-hidden="true"></i><b>${rooms.toLocaleString()}</b> in game rooms right now</span>`);
  return parts.length ? `<p class="fl-proof">${parts.join("")}</p>` : "";
}

function flTonightHTML(fl) {
  const t = ((fl && fl.tonight) || []).filter((x) => Number(x.picks) > 0);
  const n = t.reduce((a, x) => a + Number(x.picks), 0);
  const night = fl && fl.last_night;
  // A league a card, as many as have picks up; three blank ones before the
  // counts arrive or on a night with none, so the shape never jumps.
  const cards = (t.length ? t.slice(0, 6) : [null, null, null]).map((x) => `
    <div class="fl-lock">
      <div class="fl-lock-top">${x ? `<span>${escapeHtml(((SPORT_META[x.sport] || {}).logo || "") + " " + x.league)}</span>
        <b>${plural(Number(x.picks), "pick")}</b>` : "<span>Tonight</span>"}</div>
      <i aria-hidden="true"></i><i aria-hidden="true"></i><i class="s" aria-hidden="true"></i>
      <span class="fl-lock-ic">${icon("lock", 13)}<span>Members</span></span>
    </div>`).join("");
  return `<section class="fl-tonight" aria-label="Tonight for members">
    <div class="fl-tonight-h"><span class="fl-tag">${iconMark("gem", 12)}Members</span>
      <b>${n ? `${plural(n, "pick")} posted today` : "Tonight’s picks post before every game"}</b></div>
    <div class="fl-locks">${cards}</div>
    ${night ? `<p class="fl-night">Last night <b>${night.w}–${night.l}${night.p ? `–${night.p}` : ""}</b>
      <span class="${night.units >= 0 ? "pos" : "neg"}">${night.units >= 0 ? "+" : "−"}${Math.abs(Number(night.units)).toFixed(1)}u</span>
      · graded on the <a href="#record">Record</a></p>` : ""}
  </section>`;
}

/* Free beside Member. Each free line is a page WALL_OPEN opens and each
   member line is one PLAN_FEATURES sells; nothing here is new. */
const FL_ROWS = [
  ["Every game live — scores, play-by-play and stats", 1],
  ["A chat for every game, a thread on every play", 1],
  ["Call it, and your players’ lines live", 1],
  ["Fantasy lineups and start/sit help, your bet tracker", 1],
  ["The Record — every pick we post, graded", 1],
  ["Tonight’s picks, props and parlays, before the game", 0],
  ["Most Likely — every pick, tiered by its chance", 0],
  ["Ask Qellys, the AI, on any team or player", 0],
  ["Zeno’s bets as he places them, verified on Pikkit", 0],
  ["Game reports, matchups, line moves and alerts", 0],
  ["The members’ Discord", 0],
];

function flTableHTML() {
  const mark = (on) => (on ? `<span class="fl-yes">${iconMark("check", 13)}<span class="sr-only">Included</span></span>`
    : `<span class="fl-no" aria-hidden="true">—</span><span class="sr-only">Not included</span>`);
  // Its own wrapper, so the page's table wrapper (app.js wrapTables) and its
  // reserved scrollbar gutter leave a three-column table alone.
  return `<div class="rank-scroll fl-twrap"><table class="fl-table">
    <thead><tr><th scope="col"><span class="sr-only">What you get</span></th><th scope="col">Free account</th>
      <th scope="col" class="fl-mem">Member</th></tr></thead>
    <tbody>${FL_ROWS.map(([what, free]) => `<tr${free ? "" : ' class="paid"'}><th scope="row">${escapeHtml(what)}</th>
      <td>${mark(free)}</td><td class="fl-mem">${mark(1)}</td></tr>`).join("")}</tbody></table></div>`;
}

function flLastHTML(fl) {
  const b = fl && fl.last;
  if (!b || !b.player) return "";
  const won = b.status === "won", push = b.status === "push";
  const pnl = Number(b.pnl_units) || 0;
  const line = (b.market === "moneyline" || b.line == null) ? "" : `${b.line} `;
  return `<section class="fl-last" aria-labelledby="fl-last-h">
    <h3 class="fl-h3" id="fl-last-h">The last pick we graded</h3>
    <div class="fl-pick ${push ? "push" : won ? "won" : "lost"}">
      <div class="fl-pick-top"><span>${escapeHtml(String(b.sport || "").toUpperCase())}${b.date ? ` · ${escapeHtml(b.date)}` : ""}</span>
        <b class="fl-res">${push ? "Push" : won ? "Won" : "Lost"} ${pnl >= 0 ? "+" : "−"}${Math.abs(pnl).toFixed(2)}u</b></div>
      <b class="fl-pick-who">${escapeHtml(b.player)}</b>
      <span class="fl-pick-bet">${escapeHtml(b.side || "")} ${escapeHtml(line)}${escapeHtml(marketWord(b.market))} · ${escapeHtml(american(b.odds))}</span>
      ${b.hit_prob != null ? `<span class="fl-pick-p">Our chance ${(Number(b.hit_prob) * 100).toFixed(0)}%</span>` : ""}
    </div>
    <p class="fl-note">Members had it before the game. Won or lost, the newest graded pick is the one shown — it is the Record’s own row.</p>
  </section>`;
}

function flRecordHTML(fl) {
  const r = fl && fl.record;
  if (!r || !(r.w + r.l)) return "";
  return `<a class="fl-rec" href="#record"><span>The Record</span>
    <b>${r.w}–${r.l}${r.p ? `–${r.p}` : ""}</b>
    <span class="${r.units >= 0 ? "pos" : "neg"}">${r.units >= 0 ? "+" : "−"}${Math.abs(r.units).toFixed(1)}u</span>
    <i>Every pick, free to read ${icon("chev", 12)}</i></a>`;
}

/* The three plans as one row of choices. Before an account exists a tap
   keeps the plan (rememberPendingPlan) and brings the form up — once the
   account is made, checkout opens on it (acctLandAfterAuth). A build that
   sells nothing (storeSells) names no price. */
function flPlansHTML(status) {
  if (!storeSells()) return `<p class="fl-fine">Members sign in with their account to open the picks.</p>`;
  const ready = {};
  ((status && status.plans) || []).forEach((p) => { ready[p.id] = !!p.ready; });
  const days = (status && status.trial_days) || 0;
  const tplan = (status && status.trial_plan) || "";
  const best = bestValuePlanId(PLANS);
  return `<div class="fl-plans">${PLANS.map((pl) => {
    const trial = days > 0 && pl.id === tplan;
    const ok = !(pl.id in ready) || ready[pl.id];
    return `<button type="button" class="fl-plan${pl.id === best ? " best" : ""}" data-flplan="${escapeAttr(pl.id)}"${ok ? "" : " disabled"}>
      ${pl.id === best ? `<span class="fl-plan-tag">Best value</span>` : trial ? `<span class="fl-plan-tag trial">${days} days free</span>` : ""}
      <b>${escapeHtml(pl.name)}</b>
      <span class="fl-plan-price">$${pl.price}<i>/${escapeHtml(pl.per)}</i></span>
      <span class="fl-plan-per">${!ok ? "Not available yet" : pl.months > 1 ? `$${planPerMonth(pl).toFixed(2)} a month · save $${pl.save}`
        : trial ? `then $${pl.price} a month` : "Cancel anytime"}</span>
    </button>`;
  }).join("")}</div>`;
}

/* The trial's days, said before the card is asked for (faqFor says the
   same in full; Terms §5.3 is the binding version). */
function flTrialHTML(status) {
  const days = (status && status.trial_days) || 0;
  const pl = PLANS.find((p) => p.id === ((status && status.trial_plan) || ""));
  if (!days || !pl || !storeSells() || (status && status.trial_eligible === false)) return "";
  return `<ol class="fl-trial" aria-label="How the free trial works">
    <li><b>Today</b><span>Every pick and every board opens. A card is taken; nothing is charged.</span></li>
    <li><b>Day ${days}</b><span>The last free day — cancelling is one button on your account page.</span></li>
    <li><b>Day ${days + 1}</b><span>$${pl.price} a month begins, unless you cancelled.</span></li>
  </ol>`;
}

function flMembersHTML(fl, status) {
  return `<section class="fl-members" aria-labelledby="fl-h">
    <h2 class="fl-h2" id="fl-h">Free, or the picks too</h2>
    ${flTableHTML()}
    ${flLastHTML(fl)}
    ${flRecordHTML(fl)}
    <h3 class="fl-h3">Choose a plan whenever you’re ready</h3>
    ${flPlansHTML(status)}
    ${flTrialHTML(status)}
    <p class="fl-fine">The free account needs none of this — start free, and the plans are here when you want them.</p>
  </section>`;
}

/* The page the account wall held back (app.js acctWallTurns), said over
   the form: "the link you were sent opens once you're in". */
function wallWhyLine() {
  let h = "";
  try { h = sessionStorage.getItem("qb_wall_back") || ""; } catch (e) {}
  const v = h.replace(/^#/, "").split("/")[0];
  if (!v) return "";
  if (v === "pbp" || v === "game") return "Make a free account and the game you were sent opens.";
  if (v === "live") return "Make a free account to watch every game live, with the room.";
  if (v === "feed" || v === "messages") return "Make a free account to see what was shared with you.";
  if (v === "fantasy") return "Make a free account to open the fantasy tools.";
  if (v === "mybets") return "Make a free account to track your bets.";
  if (v === "streak") return "Make a free account to play the streak.";
  return WALL_OPEN.includes(v) ? "Make a free account and that page opens."
    : "Make a free account first — then the plans open the picks.";
}

/* THE SIGN-UP SCREEN — the first one a new visitor sees (app.js welcomeSeen;
   with the account wall up, the only one: acctWallTurns). Real's order —
   who we are, then the form — with the members' side right under it. */
function signupHTML() {
  const insecure = _acctUser && _acctUser.insecure;
  const wall = !!((_pwStatus && _pwStatus.account_wall) || (_acctUser && _acctUser.account_wall));
  const why = wallWhyLine();
  return `<div class="fsu">
  <header class="fsu-top">
    <span class="fsu-brand">${brandMarkHTML(30)}<span class="fsu-words">Qellys <b>Book</b></span></span>
    <button type="button" class="btn ghost fsu-login" data-act="acctGoLogin">Log in</button>
  </header>
  ${why ? `<p class="fsu-why" role="status">${iconMark("lock", 14)}<span>${escapeHtml(why)}</span></p>` : ""}
  <div class="welcome-hero">
    <h1 class="welcome-h">Every game, live. Every pick, graded.</h1>
    <p class="fsu-sub">Your free account opens every game, its chat and Call it. Members get the picks.</p>
    <div class="fl-proof-host">${flProofHTML(_fl)}</div>
  </div>
  <div class="fl-host">${flTonightHTML(_fl)}</div>
  <div class="card acct-card" id="su-form">
    <div class="card-head">
      <div><div class="player">Create your free account</div>
        <div class="subtitle">Pick a username — it is how the chat knows you. No card,
          nothing to cancel.</div></div>
    </div>
    <p class="fsu-plan-note" role="status">${escapeHtml(_suNote)}</p>
    ${insecure ? `<div class="warning">${icon("warn")} <b>${
      _acctUser.allowed ? "This connection is not private."
                        : "Not over this connection."}</b>
      This page came over plain HTTP, so a password typed here crosses the
      network readable by anyone on it.</div>` : ""}

    ${acctFieldsHTML("signup", `
    ${suWhyHTML()}
    <label class="acct-field"><span class="acct-field-k">Friend’s referral code <i>optional</i></span>
      <input class="acct-ref" maxlength="16" autocomplete="off" autocapitalize="characters" spellcheck="false"
        value="${escapeAttr(referralTyped())}" placeholder="$6.25 off your first payment"></label>
    <label class="acct-confirm">
      <input type="checkbox" class="acct-age">
      <span>I am 21 or older, and I accept the
        <a href="terms.html" target="_blank" rel="noopener">Terms</a> and
        <a href="privacy.html" target="_blank" rel="noopener">Privacy Policy</a>.
        This site publishes model estimates and takes no bets.</span>
    </label>`)}

    <div class="acct-note">${escapeHtml(_acctNote)}</div>
    ${phoneDoorHTML("signup")}

    <div class="acct-alt">
      <span>Already have an account?</span>
      <button class="btn ghost" data-act="acctGoLogin">Log in</button>
    </div>
    <div class="acct-alt-more">
      <button type="button" class="acct-forgot" data-act="acctGoForgot">Forgot password?</button>
      ${wall ? "" : `<button type="button" class="acct-forgot welcome-skip" data-act="welcomeBrowse">Look around first →</button>`}
    </div>
  </div>

  <div class="fl-more">${flMembersHTML(_fl, _pwStatus)}</div>

  ${/* TWO PROMISES, AS AN APP SAYS THEM (2026-10-25): two rows under the
        form, each a mark and one sentence, where two paragraphs of grey
        prose used to sit. Nothing said is lost. */""}
  <ul class="acct-promises">
    <li>${iconMark("lock", 15)}<span>Length is what makes a password hard to guess. We keep a one-way
      scramble of it, never the password — a lost one is replaced from “Forgot password?”, not recovered —
      and we never ask for your sportsbook or ESPN password.</span></li>
    <li>${iconMark("check", 15)}<span>An account is free — it takes no card and subscribes you to nothing.${PLANS[0] ? ` The plans are
      <a href="#paywall">over here</a> when you want them.` : ""}</span></li>
  </ul>
  ${/* The wall's own screens hide the site footer, so they print its line. */""}
  <p class="pw-legal">21+ · Not betting advice · Gambling problem? Call <b>1-800-GAMBLER</b></p></div>`;
}

/* The members' side drawn, then redrawn once its numbers arrive — only its
   own boxes, so a half-typed form is never wiped. On a phone the form's
   button rides along once the form scrolls away (the plans screen's pwDock,
   the same shape). */
function flPaint(host) {
  const need = _pwStatus ? null : paywallCheck().catch(() => null);
  Promise.all([flGet(), need]).then(([fl]) => {
    const a = host.querySelector(".fl-host");
    const b = host.querySelector(".fl-more");
    const c = host.querySelector(".fl-proof-host");
    if (a && fl) a.innerHTML = flTonightHTML(fl);
    if (c && fl) c.innerHTML = flProofHTML(fl);
    if (b) b.innerHTML = flMembersHTML(fl, _pwStatus);
  });
  const form = host.querySelector("#su-form");
  if (!form || host.querySelector(".fsu-dock") || typeof IntersectionObserver !== "function") return;
  host.insertAdjacentHTML("beforeend", `<div class="fsu-dock away" role="region" aria-label="Create your free account">
    <button type="button" class="btn primary" data-flgo="1">Create your free account</button></div>`);
  const dock = host.querySelector(".fsu-dock");
  new IntersectionObserver((seen) => dock.classList.toggle("away", seen.some((e) => e.isIntersecting)),
    { threshold: 0.05 }).observe(form);
}

/* WHAT BRINGS YOU HERE? (docs/IDEAS.md round three): one tap on the sign-up
   form, kept on this device, and the new account lands there (app.js
   whyLand) instead of on the first stop of the tour. Optional. */
const SU_WHY = [["live", "Live games"], ["picks", "Our picks"], ["fantasy", "Fantasy"], ["bets", "Tracking my bets"]];
function suWhyHTML() {
  let on = "";
  try { on = localStorage.getItem("qb_why") || ""; } catch (e) {}
  return `<div class="acct-field acct-why" role="group" aria-label="What brings you here?">
    <span class="acct-field-k">What brings you here? <i>optional</i></span>
    <div class="acct-why-row">${SU_WHY.map(([k, label]) => `<button type="button" class="acct-why-b${k === on ? " on" : ""}"
      data-su-why="${k}" aria-pressed="${k === on}">${label}</button>`).join("")}</div></div>`;
}

function suWhyTap(t) {
  const on = !t.classList.contains("on");
  try { if (on) localStorage.setItem("qb_why", t.dataset.suWhy); else localStorage.removeItem("qb_why"); } catch (err) {}
  t.parentElement.querySelectorAll("[data-su-why]").forEach((b) => {
    const me = b === t && on; b.classList.toggle("on", me); b.setAttribute("aria-pressed", String(me)); });
}

function flToForm(note) {
  const f = document.getElementById("su-form");
  if (!f) return;
  const n = f.querySelector(".fsu-plan-note");
  if (n && note) n.textContent = note;
  f.scrollIntoView({ behavior: "smooth", block: "start" });
  const first = f.querySelector(".acct-handle, input");
  if (first) setTimeout(() => first.focus({ preventScroll: true }), 350);
}

if (typeof window !== "undefined" && !window._flBound) {
  window._flBound = true;
  document.addEventListener("click", (e) => {
    const t = e.target.closest && e.target.closest("[data-flplan], [data-flgo], [data-ps], [data-pwjoin], [data-pwlater], [data-su-why]");
    if (!t) return;
    if (t.dataset.pwjoin) return pwJoin(t.dataset.pwjoin);
    if (t.dataset.pwlater) return pwLater(t);
    if (t.dataset.flgo) return flToForm("");
    if (t.dataset.ps) return planPick(t.dataset.ps);
    if (t.dataset.suWhy) return suWhyTap(t);
    const pl = PLANS.find((p) => p.id === t.dataset.flplan);
    if (!pl) return;
    // Signed in already (the plans page's own row), straight to checkout.
    if (acctSignedIn()) return window.coStart({ dataset: { plan: pl.id } });
    rememberPendingPlan(pl.id);
    flToForm(`Make your account and checkout opens on the ${pl.name.toLowerCase()} plan.`);
  });
}

/* THE OFFER, ONCE, RIGHT AFTER THE ACCOUNT — Duolingo's and Spotify's
   order: the account, your teams, then the plan, with "continue free" a
   full-size button and not a grey link. Only for a new account with no
   plan that chose none on the way in, on a build that sells. */
let _planDone = null;
async function planStep(done) {
  const host = document.getElementById("view-signup");
  if (!host || state.view !== "signup" || !storeSells() || _pendingPlanPeek()) return done();
  let walled = false;
  try { walled = await paywallCheck(1); } catch (e) { walled = false; }
  if (!walled) return done();
  _planDone = done;
  host.innerHTML = planStepHTML(_fl);
  window.scrollTo({ top: 0, behavior: "auto" });
  flGet().then((fl) => {
    const t = host.querySelector(".ps-tonight");
    if (t && fl && _planDone) t.innerHTML = psTonightHTML(fl);
  });
}

function psTonightHTML(fl) {
  const n = ((fl && fl.tonight) || []).reduce((a, x) => a + (Number(x.picks) || 0), 0);
  return n ? `${iconMark("lock", 13)}<span><b>${plural(n, "pick")}</b> waiting for members today</span>` : "";
}

function planStepHTML(fl) {
  const s = _pwStatus || {};
  const days = s.trial_days || 0;
  const tpl = PLANS.find((p) => p.id === s.trial_plan);
  const trial = days > 0 && tpl && s.trial_eligible !== false && (s.plans || []).some((p) => p.id === tpl.id && p.ready);
  const mo = PLANS.find((p) => p.id === "monthly") || PLANS[0];
  const best = PLANS.find((p) => p.id === bestValuePlanId(PLANS));
  const handle = (((_acctUser || {}).profile) || {}).handle || "";
  return `<div class="ps-step">
    <span class="ps-done" aria-hidden="true">${iconMark("check", 26)}</span>
    <h1 class="ps-h">You’re in${handle ? `, @${escapeHtml(handle)}` : ""}.</h1>
    <p class="ps-sub">Every game live, the chat and Call it are yours — free.</p>
    <section class="ps-card" aria-labelledby="ps-h2">
      <span class="fl-tag">${iconMark("gem", 12)}Members</span>
      <h2 class="ps-h2" id="ps-h2">Want the picks too?</h2>
      <p class="ps-tonight">${psTonightHTML(fl)}</p>
      <ul class="ps-list">
        <li>${iconMark("check", 13)}<span>Every pick before the game, with its price and our chance</span></li>
        <li>${iconMark("check", 13)}<span>Most Likely, parlay tickets and every prop board</span></li>
        <li>${iconMark("check", 13)}<span>Ask Qellys, the AI, on any team or player</span></li>
        <li>${iconMark("check", 13)}<span>Zeno’s bets as he places them, verified on Pikkit</span></li>
      </ul>
      <button type="button" class="btn primary ps-go" data-ps="${escapeAttr((trial ? tpl : mo).id)}">${
        trial ? `Start ${days} days free` : `Become a member — $${mo.price} a month`}</button>
      <p class="ps-fine">${trial ? `Then $${tpl.price} a month. Cancel in one tap before day ${days + 1} and nothing is charged.`
        : "Cancel anytime in one tap."}${best && best.id !== mo.id
        ? ` Or $${planPerMonth(best).toFixed(2)} a month on the ${escapeHtml(best.name.toLowerCase())} plan.` : ""}</p>
    </section>
    <button type="button" class="btn ghost ps-free" data-ps="free">Continue with the free account</button>
  </div>`;
}

function planPick(choice) {
  const done = _planDone;
  if (!done) return;
  _planDone = null;
  if (choice !== "free") rememberPendingPlan(choice);
  done();
}

/* AN ACCOUNT BY PHONE (Ethan, 2026-10-25: "you can either make an account
   with an email or a phone number"). A code by text through Twilio Verify
   (engine/smsverify), no password; offered only when the server says it is
   switched on (`phone_signup` on /api/account/me). Signing up asks for the
   username, the referral code and the 21+ box like the email form does;
   signing in asks for the number and the code. */
let _ph = { mode: "", sent: false, to: "" };
const phoneDoorHTML = (mode) => ((_acctUser || {}).phone_signup
  ? `<button type="button" class="acct-forgot ph-door" data-ph="open" data-mode="${mode}">${
    mode === "signup" ? "Use your phone number instead" : "Sign in with your phone number"}</button>` : "");

function phoneCardHTML(mode) {
  const up = mode === "signup";
  return `<h2 class="acct-card-h">${up ? "Create your free account" : "Welcome back"}</h2>
    <p class="rank-help">${up ? "With your phone: we text you a code, and there’s no password to remember."
      : "We’ll text a code to the number on your account."}</p>
    ${up ? `<label class="acct-field"><span class="acct-field-k">Username</span>
      <span class="acct-handle-row"><b>@</b><input class="ph-handle" maxlength="20" autocomplete="username"
        autocapitalize="none" spellcheck="false" placeholder="yourname"></span></label>` : ""}
    <label class="acct-field"><span class="acct-field-k">Mobile number</span>
      <input class="ph-phone" type="tel" autocomplete="tel" inputmode="tel" placeholder="(555) 201-4567"
        ${_ph.sent ? "readonly" : ""} value="${escapeAttr(_ph.to)}"></label>
    ${_ph.sent ? `<label class="acct-field"><span class="acct-field-k">The code we texted</span>
      <input class="ph-code" inputmode="numeric" autocomplete="one-time-code" maxlength="10" placeholder="6 digits"></label>` : ""}
    ${up ? `<label class="acct-field"><span class="acct-field-k">Friend’s referral code <i>optional</i></span>
      <input class="ph-ref" maxlength="16" autocomplete="off" autocapitalize="characters" value="${escapeAttr(referralTyped())}"></label>
      <label class="acct-confirm"><input type="checkbox" class="ph-age"><span>I am 21 or older, and I accept the
        <a href="terms.html" target="_blank" rel="noopener">Terms</a> and
        <a href="privacy.html" target="_blank" rel="noopener">Privacy Policy</a>.</span></label>` : ""}
    <button type="button" class="btn primary" data-ph="go" data-mode="${mode}">${_ph.sent ? (up ? "Create account" : "Sign in") : "Text me a code"}</button>
    <p class="acct-note ph-note" role="status"></p>
    ${_ph.sent ? `<button type="button" class="acct-forgot" data-ph="again" data-mode="${mode}">Send a new code</button>` : ""}
    <button type="button" class="acct-forgot" data-ph="email" data-mode="${mode}">Use ${up ? "email" : "email and password"} instead</button>
    <p class="rank-help acct-fine">Standard text rates may apply. Your number is used to sign you in and nothing else.</p>`;
}

async function phoneGo(card, mode) {
  const note = (t) => { const n = card.querySelector(".ph-note"); if (n) n.textContent = t; };
  const val = (c) => ((card.querySelector(c) || {}).value || "").trim();
  if (!_ph.sent) {
    _ph.to = val(".ph-phone");
    note("Sending…");
    const r = await fetch("/api/account/phone-start", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone: _ph.to }) }).catch(() => null);
    const out = r ? await r.json().catch(() => ({})) : {};
    if (!r || !r.ok) return note(out.error || "Couldn’t reach the server — try again.");
    _ph.sent = true;
    const keep = mode === "signup" ? { h: val(".ph-handle"), age: !!(card.querySelector(".ph-age") || {}).checked } : null;
    card.innerHTML = phoneCardHTML(mode);
    if (keep) {
      const h = card.querySelector(".ph-handle"); if (h) h.value = keep.h;
      const a = card.querySelector(".ph-age"); if (a) a.checked = keep.age;
    }
    const c = card.querySelector(".ph-code"); if (c) c.focus();
    const n2 = card.querySelector(".ph-note"); if (n2) n2.textContent = `Code sent to ${out.to || _ph.to}.`;
    return;
  }
  const body = { phone: _ph.to, code: val(".ph-code") };
  if (mode === "signup") {
    const age = card.querySelector(".ph-age");
    if (!age || !age.checked) return note("Please confirm you are 21 or older and accept the Terms.");
    Object.assign(body, { confirmed: true, handle: val(".ph-handle").replace(/^@/, ""), ref: val(".ph-ref") });
    if (body.handle && !/^[A-Za-z0-9_]{3,20}$/.test(body.handle)) return note("Pick a username: 3–20 letters, numbers or underscores.");
  }
  note("Checking…");
  const r = await fetch("/api/account/phone-verify", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
  const out = r ? await r.json().catch(() => ({})) : {};
  if (!r || !r.ok) return note(out.error || "Couldn’t reach the server — try again.");
  // Signed in: the same steps an email sign-in takes (app.js acctAuth).
  _ph = { mode: "", sent: false, to: "" };
  _acctUser = { signed_in: true, email: out.email, phone: out.phone };
  if (typeof pushRelink === "function") pushRelink();
  welcomeDone();
  if (mode === "signup" && typeof dcMarkWelcome === "function") dcMarkWelcome();
  if (typeof acceptPendingInvite === "function") acceptPendingInvite();
  try { await acctSync(); } catch (e) {}
  if (mode === "signup") return followStep(() => acctLandAfterAuth());
  return acctLandAfterAuth();
}

if (typeof window !== "undefined" && !window._phBound) {
  window._phBound = true;
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-ph]");
    if (!b) return;
    const card = b.closest(".acct-card, .acct-signin");
    if (!card) return;
    const mode = b.dataset.mode || "signup";
    const act = b.dataset.ph;
    if (act === "open" || act === "again") {
      _ph = { mode, sent: false, to: act === "again" ? _ph.to : "" };
      card.innerHTML = phoneCardHTML(mode);
      return;
    }
    if (act === "email") {
      _ph = { mode: "", sent: false, to: "" };
      if (mode === "signup") renderSignup(); else renderAccount();
      return;
    }
    if (act === "go") { b.disabled = true; phoneGo(card, mode).finally(() => { b.disabled = false; }); }
  });
}

/* REAL'S FIRST SCREENS, OURS (Ethan's screenshot, 2026-10-25: "Welcome to
   Real · This is a play ↓", a play's card, "Every big moment in a game
   becomes one of these.", four bars and Continue). Four steps before the
   sign-up — a play, its thread, the game's room, the Record — once per
   device, with a way past on every one. The cards are examples and say so;
   the Record's numbers are the real ones, read off the public file. */
const INTRO_KEY = "qb_intro_v1";
let _introStep = 0;
let _introRecord = null;
const introSeen = () => { try { return localStorage.getItem(INTRO_KEY) === "1"; } catch (e) { return true; } };
const introDone = () => { try { localStorage.setItem(INTRO_KEY, "1"); } catch (e) {} };

const INTRO_CARD = `<div class="wi-card" aria-hidden="true">
    <div class="wi-top"><b>PIT 24–21 BAL</b><span>Q4 1:52</span><span class="wi-rate">9.4</span></div>
    <span class="wi-chip">Go-ahead</span>
    <p class="wi-title">Touchdown pass, 38 yds</p>
    <span class="wi-line"><b>Quarterback</b> · 22/31, 264 yds, 2 TD</span>
    <span class="wi-line"><b>Receiver</b> · 6 rec, 98 yds, 1 TD</span>
    <span class="wi-win">PIT win chance 31% → 78%</span>
    <div class="wi-acts"><span>🔥 2.8k</span><span>😮 640</span><span class="wi-n">💬 1.2k</span></div>
  </div>`;

function introSteps() {
  const r = ((_introRecord || {}).all_time || {}).overall || {};
  const since = Date.parse(`${(_introRecord || {}).record_epoch || ""}T12:00:00`);
  const wl = r.settled ? `<div class="wi-record" aria-hidden="true"><b>${Number(r.wins).toLocaleString()}–${
    Number(r.losses).toLocaleString()}</b><span>${Number(r.settled).toLocaleString()} picks graded${isFinite(since)
    ? ` since ${new Date(since).toLocaleDateString(undefined, { month: "long", day: "numeric" })}` : ""}</span></div>` : "";
  return [
    { lead: "This is a play", art: INTRO_CARD,
      say: "Every big moment in every game becomes one of these — the second it happens, with how much it moved the game." },
    { lead: "Every play has its own thread", art: `<div class="wi-thread" aria-hidden="true">
        <p class="wi-title">Touchdown pass, 38 yds</p>
        <div class="wi-msg"><b>@steelcurtain</b> That’s the game right there</div>
        <div class="wi-msg"><b>@whodat</b> Need one stop. I’m on the under 44.5 😬</div></div>`,
      say: "Tap the bubble on any play to talk about it — or share the bet you’re on." },
    { lead: "Every game has a room", art: `<div class="wi-room" aria-hidden="true">
        <div class="wi-top"><b>PIT 24–21 BAL</b><span>213 here now</span></div>
        <div class="wi-vote"><span>Who wins?</span><i style="--w:63%">PIT 63%</i><i style="--w:37%">BAL 37%</i></div></div>`,
      say: "Live scores, play-by-play, stats and a chat for every game — free." },
    { lead: "Every pick, graded in public", art: wl || `<div class="wi-record" aria-hidden="true"><b>The Record</b></div>`,
      say: "Members get our picks. Everyone gets the Record: every pick we post, won or lost, and nothing deleted." },
  ];
}

function introHTML() {
  const steps = introSteps();
  const i = Math.min(_introStep, steps.length - 1);
  const st = steps[i];
  const last = i === steps.length - 1;
  return `<div class="wiz">
    <div class="wi-head"><img class="welcome-mark" src="logo-qb.png" alt="" width="40" height="40" decoding="async">
      <h1 class="wi-h">Welcome to Qellys Book</h1>
      <button type="button" class="wi-skip" data-intro="skip">${last ? "" : "Skip"}</button></div>
    <div class="wi-stage"><p class="wi-lead">${st.lead}</p>
      ${i === 0 ? `<span class="wi-arrow" aria-hidden="true">↓</span>` : ""}
      ${st.art}<p class="wi-ex">${i < 3 ? "Example" : ""}</p>
      <p class="wi-say">${st.say}</p></div>
    <div class="wi-bars" role="tablist" aria-label="Step ${i + 1} of ${steps.length}">${steps.map((_, k) =>
      `<button type="button" class="wi-bar${k <= i ? " on" : ""}" data-intro="go" data-step="${k}" aria-label="Step ${k + 1}"></button>`).join("")}</div>
    <button type="button" class="btn primary wi-go" data-intro="${last ? "done" : "next"}">${last ? "Create your free account" : "Continue"}</button>
    <div class="wi-foot"><span>Have an account?</span><button type="button" class="btn ghost" data-act="acctGoLogin">Log in</button></div>
  </div>`;
}

function introBind(host) {
  if (host.dataset.introBound) return;
  host.dataset.introBound = "1";
  host.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("[data-intro]");
    if (!b || introSeen()) return;
    const act = b.dataset.intro;
    if (act === "next") _introStep += 1;
    else if (act === "go") _introStep = Number(b.dataset.step) || 0;
    else { introDone(); host.innerHTML = signupHTML(); host.scrollTop = 0; flPaint(host); return; }
    host.innerHTML = introHTML();
  });
  // A swipe moves a step either way, as Real's does.
  let x0 = null;
  host.addEventListener("pointerdown", (e) => { x0 = introSeen() ? null : e.clientX; }, { passive: true });
  host.addEventListener("pointerup", (e) => {
    if (x0 == null) return;
    const dx = e.clientX - x0;
    x0 = null;
    if (Math.abs(dx) < 50) return;
    _introStep = Math.max(0, Math.min(introSteps().length - 1, _introStep + (dx < 0 ? 1 : -1)));
    host.innerHTML = introHTML();
  }, { passive: true });
}

/* AFTER THE ACCOUNT, YOUR TEAMS AND PLAYERS (Ethan, 2026-10-25: "when you
   first go on the Real app after you create an account, you're allowed to
   select your favorite players ... and teams you want to follow ... so you
   can get notifications about your favorite players' props being posted").
   One screen between sign-up and the site: tap teams, search players.
   A team joins the ones the site already brings to the front (settings
   `teams`); every team and player is also a watch (engine/alerts), so the
   Alerts page — and the phone, once alerts are on — says when they're on
   tonight's board. Skippable, and all of it changes later in Settings and
   Alerts. */
const FOLLOW_LEAGUES = [["nfl", "NFL", () => (typeof TEAMS !== "undefined" ? TEAMS : {})],
  ["nba", "NBA", () => (typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : {})],
  ["mlb", "MLB", () => (typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {})],
  ["nhl", "NHL", () => (typeof NHL_TEAMS !== "undefined" ? NHL_TEAMS : {})],
  ["wnba", "WNBA", () => (typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : {})]];
const FOLLOW_MAX = 20;          // engine/alerts.MAX_WATCHES
let _fol = { lg: "nfl", teams: [], players: [], hits: [], q: "", done: null };

function followHTML() {
  const f = _fol;
  const [lg, , map] = FOLLOW_LEAGUES.find(([k]) => k === f.lg) || FOLLOW_LEAGUES[0];
  // One button a team: the maps carry old codes beside the current one
  // (ARI and ARZ are both Arizona), so the first code for a name wins.
  const seen = new Set();
  const teams = Object.entries(map()).filter(([, t]) => !seen.has(t.name) && seen.add(t.name))
    .sort((a, b) => String(a[1].name).localeCompare(String(b[1].name)));
  const n = f.teams.length + f.players.length;
  return `<div class="fol">
    <div class="fol-head"><h1 class="wi-h">Follow your teams and players</h1>
      <p>Their games come first on Live, and we’ll tell you when they’re on tonight’s board.</p></div>
    <div class="fol-tabs" role="tablist">${FOLLOW_LEAGUES.map(([k, label]) =>
      `<button type="button" class="fol-tab${k === lg ? " on" : ""}" data-fol="lg" data-lg="${k}" role="tab" aria-selected="${k === lg}">${label}</button>`).join("")}</div>
    <div class="fol-grid">${teams.map(([abbr, t]) => {
      const key = `${lg}:${abbr}`;
      const on = f.teams.includes(key);
      return `<button type="button" class="fol-team${on ? " on" : ""}" data-fol="team" data-key="${escapeAttr(key)}" aria-pressed="${on}">
        ${typeof teamMark === "function" ? teamMark(abbr, 30, null, lg) : ""}<span>${escapeHtml(t.nick || t.name || abbr)}</span></button>`;
    }).join("")}</div>
    <form class="fol-find" data-fol-form><input name="q" value="${escapeAttr(f.q)}" placeholder="Search a ${FOLLOW_LEAGUES.find(([k]) => k === lg)[1]} player"
      autocomplete="off" aria-label="Search a player"><button class="btn ghost" type="submit">Search</button></form>
    ${f.hits.length ? `<div class="fol-hits">${f.hits.map((p) => {
      const name = p.player || p.name || "";
      const on = f.players.some((x) => x.name === name);
      return `<button type="button" class="fol-hit${on ? " on" : ""}" data-fol="player" data-name="${escapeAttr(name)}">
        <b>${escapeHtml(name)}</b><span>${escapeHtml([p.team, p.position].filter(Boolean).join(" · "))}</span><i>${on ? "Following" : "Follow"}</i></button>`;
    }).join("")}</div>` : ""}
    ${f.players.length ? `<div class="fol-chips">${f.players.map((x) =>
      `<button type="button" class="fol-chip" data-fol="player" data-name="${escapeAttr(x.name)}">${escapeHtml(x.name)} ×</button>`).join("")}</div>` : ""}
    <p class="fol-n">${n ? `${n} followed` : "Nothing yet"} · up to ${FOLLOW_MAX}</p>
    <button type="button" class="btn primary wi-go" data-fol="save">${n ? "Done" : "Skip for now"}</button>
  </div>`;
}

async function followSave() {
  const f = _fol;
  const keep = settings().teams.filter((t) => !f.teams.includes(t));
  setSetting("teams", [...f.teams, ...keep]);
  // Each one a watch, so the Alerts page and the phone know it. A watch the
  // server refuses (the cap, a name it can't read) costs that one only.
  const add = [...f.teams.map((t) => ({ kind: "team", value: t.split(":")[1] })),
               ...f.players.map((p) => ({ kind: "player", value: p.name }))].slice(0, FOLLOW_MAX);
  for (const w of add) {
    try {
      await fetch("/api/alerts/watch", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(w) });
    } catch (e) {}
  }
}

function followBind(host) {
  if (host.dataset.folBound) return;
  host.dataset.folBound = "1";
  host.addEventListener("click", async (e) => {
    const b = e.target.closest && e.target.closest("[data-fol]");
    if (!b || !_fol.done) return;
    const f = _fol, act = b.dataset.fol;
    const full = f.teams.length + f.players.length >= FOLLOW_MAX;
    if (act === "lg") { f.lg = b.dataset.lg; f.hits = []; f.q = ""; }
    else if (act === "team") {
      const k = b.dataset.key;
      if (f.teams.includes(k)) f.teams = f.teams.filter((x) => x !== k);
      else if (!full) f.teams.push(k);
    } else if (act === "player") {
      const name = b.dataset.name;
      if (f.players.some((x) => x.name === name)) f.players = f.players.filter((x) => x.name !== name);
      else if (!full) f.players.push({ name, sport: f.lg });
    } else if (act === "save") {
      b.disabled = true;
      const done = f.done;
      f.done = null;
      if (f.teams.length || f.players.length) await followSave();
      return done();
    }
    host.innerHTML = followHTML();
  });
  host.addEventListener("submit", async (e) => {
    const form = e.target.closest && e.target.closest("[data-fol-form]");
    if (!form || !_fol.done) return;
    e.preventDefault();
    const q = String(new FormData(form).get("q") || "").trim();
    _fol.q = q;
    if (q.length < 2) return;
    try {
      const r = await fetch(`/api/players/search?q=${encodeURIComponent(q)}&sport=${encodeURIComponent(_fol.lg)}&scope=sport`);
      _fol.hits = r.ok ? ((await r.json()).players || []).slice(0, 8) : [];
    } catch (err) { _fol.hits = []; }
    host.innerHTML = followHTML();
  });
}

/* Called by app.js acctAuth the moment a new account exists; `done` is the
   landing it would have gone to. Off the sign-up page, it simply lands. */
function followStep(done) {
  const host = document.getElementById("view-signup");
  if (!host || state.view !== "signup") return done();
  _fol = { lg: FOLLOW_LEAGUES.some(([k]) => k === state.sport) ? state.sport : "nfl",
           teams: settings().teams.filter((t) => FOLLOW_LEAGUES.some(([k]) => t.startsWith(`${k}:`))).slice(0, FOLLOW_MAX),
           players: [], hits: [], q: "", done: () => planStep(done) };
  followBind(host);
  host.innerHTML = followHTML();
  window.scrollTo({ top: 0, behavior: "auto" });
}

async function renderSignup() {
  const host = document.getElementById("view-signup");
  if (!host) return;
  // Somebody already signed in has no business on this page — send them
  // to their account rather than offering a second one.
  await acctWho();
  if (_acctUser && _acctUser.signed_in) {
    switchView("account", false);
    return;
  }
  // Somebody who already chose a plan on the plans page goes straight to the
  // form: the tour is for strangers, not for a buyer.
  if (!introSeen() && !_pendingPlanPeek()) {
    introBind(host);
    host.innerHTML = introHTML();
    if (!_introRecord) {
      fetch("data/record_head.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).then((d) => {
        _introRecord = d;
        if (d && !introSeen() && _introStep === 3) host.innerHTML = introHTML();
      }).catch(() => {});
    }
    return;
  }
  host.innerHTML = signupHTML();
  flPaint(host);
}

function renderAccount() {
  const body = document.getElementById("account-body");
  if (!body) return;
  const u = _acctUser;
  if (u && u.signed_in) {
    /* ONE PROFILE FOR THE WHOLE SITE. Ethan, 2026-10-07: "the account
       page on the feed page and the main account page should be one page
       … it should all be one main profile for the whole site." The top is
       the profile everybody sees on Social (js/social.js mountAccount:
       the header, Posts, Graded picks); Friends and Settings are this
       page's own panels, shown by the tabs under the header. Social's old
       #feed/edit lands here too. If Social cannot load, every panel
       shows, so the account is never out of reach. */
    body.innerHTML = `<div id="acct-prof" class="acct-prof"></div>
      <div data-acct-tab="friends" hidden>${friendsCardHTML()}</div>
      <div data-acct-tab="settings" hidden>${settingsHTML()}${menuDiagHTML()}</div>`;
    loadSocial().then((S) => {
      const el = document.getElementById("acct-prof");
      if (S && S.mountAccount && el) return S.mountAccount(el, u);
      body.querySelectorAll("[data-acct-tab]").forEach((x) => { x.hidden = false; });
    }).then(setLandOn);
  } else {
    body.innerHTML = acctScreenHTML() + friendsCardHTML() + settingsHTML()
      + menuDiagHTML();
    setTimeout(setLandOn, 0);
  }
  renderFantasyLinks();
  bindSettings();
  // Fetched after first paint, then redrawn once — the card renders
  // from cache and must not hold the whole account screen hostage to a
  // fetch. Guarded so the redraw happens only when something arrived.
  if (_acctUser && _acctUser.signed_in && !_socCache) {
    socFetch().then((got) => { if (got) renderAccount(); });
  }
}

/* ============================================================
   The settings screen
   ============================================================
   Ethan, 2026-08-25: "Settings that stick: odds format (−110 vs 1.91),
   units vs dollars, timezone, favorite teams first, which sports show in
   nav."

   BUILT LIKE A PHONE'S OWN SETTINGS since 2026-10-25 (Ethan: "The settings
   and account area ... is ugly and doesn't look like real settings";
   docs/VISUAL_AUDIT.md S1-S6). It was a stack of cards: a billing card
   carrying the whole plans advert, two fantasy cards of paragraphs, then a
   card of pill rows with a paragraph under each. Now it is groups under
   small headers, each a rounded list of rows: an icon tile, the name, the
   value, then a chevron where the row opens a screen of its own, a switch
   where it is on or off, or a segmented control where there are two or
   three choices. A footnote under a group only where one is needed;
   destructive rows last, in red. The look lives in styles.css ("SETTINGS
   LISTS"), because the Alerts page draws the same rows.

   RENDERED SIGNED OUT AS WELL AS IN, and deliberately — the same rule
   ffLinksHTML already follows. These live in this browser and work with
   no account at all; signing in only carries them to your other
   devices. A preferences panel behind a sign-in wall would be a page
   that refuses to remember you until you prove who you are, which is
   the opposite of the point.

   Every control writes through `setSetting`, which stamps the section
   and schedules the same debounced push every other synced section
   uses, or through the account's own endpoints, exactly as before. Only
   the drawing changed. */
const TZ_CHOICES = [
  ["", "This device"],
  ["America/New_York", "Eastern"],
  ["America/Chicago", "Central"],
  ["America/Denver", "Mountain"],
  ["America/Phoenix", "Arizona"],
  ["America/Los_Angeles", "Pacific"],
  ["UTC", "UTC"],
];

/* The screen open inside Settings: "" is the list, otherwise the screen a
   row opened (the time zone, the leagues, your teams, the password, the
   plan, a code, the fantasy links, the calendar). Kept across redraws, so
   a change made on one of those screens does not throw the reader back. */
let _setPage = "";
/* The last answers the plan and the email rows were drawn from (null:
   not read yet; false: the read failed). */
let _billStatus = null;
let _mailState = null;

/* setIco, setItem, setGroup and setSwitch live in app.js: the Alerts page
   draws the same rows. */
/* The KEY is passed, never derived from the label: a settings panel that
   decides which preference it is writing by matching the words on screen
   is one rename away from writing the wrong one. */
function setSeg(key, value, opts) {
  return `<span class="set-seg">${opts.map(([v, label]) => `<button type="button"
    class="${v === value ? "on" : ""}" aria-pressed="${v === value ? "true" : "false"}"
    data-set-key="${escapeAttr(key)}" data-set-val="${escapeAttr(v)}">${escapeHtml(label)}</button>`).join("")}</span>`;
}

const setCheck = () => `<span class="set-check">${icon("check", 16)}</span>`;

function setTeamName(t) {
  const [sport, abbr] = String(t).split(":");
  return teamNameIn(sport, abbr) || abbr;
}

/* A link that asked for one of the screens ("Link a league" on the
   fantasy pages: app.js toAccount) opens it, and the page lands on it
   once it is drawn (renderAccount). */
let _setLand = false;
function setLandOn() {
  if (!_setLand) return;
  _setLand = false;
  setScrollTop();
}

/* The settings screen at the top of the window, under the bar. */
function setScrollTop() {
  const now = document.querySelector(".qb-settings");
  const bar = document.querySelector(".topbar");
  if (now) window.scrollTo({ top: Math.max(0, now.getBoundingClientRect().top + window.scrollY
    - (bar ? bar.offsetHeight : 0) - 12), behavior: "auto" });
}

function settingsHTML() {
  if (window._setOpen) { _setPage = window._setOpen; window._setOpen = ""; _setLand = true; }
  // Drawn first: an unknown screen falls back to the list and clears _setPage.
  const inner = _setPage ? setPageHTML(_setPage) : setListHTML();
  return `<section class="qb-settings set-screen${_setPage ? " set-page" : ""}">${inner}</section>`;
}

/* The list itself. */
function setListHTML() {
  const s = settings();
  const u = _acctUser, inn = !!(u && u.signed_in);
  const out = [];
  if (inn) {
    // A phone account (engine/smsverify) has a number, not an address, and
    // no password to change: it signs in by a texted code.
    out.push(setGroup("Account", [
      ...(u.phone ? [setItem({ ico: "lock", tone: "gold", title: "Phone", val: escapeHtml(u.phone), sub: "Signs in with a texted code" })]
        : [setItem({ ico: "mail", tone: "gold", title: "Email", val: escapeHtml(u.email) }),
           setItem({ ico: "lock", tone: "gold", title: "Password", val: "Change", chev: true,
                     attrs: 'data-set-open="password"' })]),
      ...(pkOK() ? [setItem({ ico: "shield", tone: "gold", title: "Passkeys", val: pkLock()[0], chev: true,
                              attrs: 'data-set-open="passkeys"' })] : []),
      setItem({ ico: "sync", tone: "gold", title: "Sync now", sub: escapeHtml(_acctNote || ""), subCls: "acct-note",
                attrs: 'data-act="acctSyncNow"' }),
    ], "Your bets, fantasy leagues, settings and searches follow this account to every device you sign in on."));
    out.push(`<div id="set-plan">${planRowsHTML(_billStatus)}</div>`);
  }
  const team1 = s.teams.length ? setTeamName(s.teams[0]) : "";
  out.push(setGroup("Preferences", [
    setItem({ tag: "div", ico: "tag", tone: "green", title: "Prices",
              sub: s.odds === "decimal" ? "Shown as 1.91" : "Shown as −110",
              end: setSeg("odds", s.odds, [["american", "American"], ["decimal", "Decimal"]]) }),
    setItem({ tag: "div", ico: "scale", tone: "green", title: "Stakes",
              sub: s.stake === "units" ? "1.4u" : s.stake === "dollars" ? "$28" : "$28 · 1.4u",
              end: setSeg("stake", s.stake, [["both", "Both"], ["units", "Units"], ["dollars", "Dollars"]]) }),
    setItem({ ico: "clock", tone: "green", title: "Time zone",
              val: escapeHtml((TZ_CHOICES.find(([v]) => v === s.tz) || TZ_CHOICES[0])[1]), chev: true,
              attrs: 'data-set-open="tz"' }),
    setItem({ ico: "list", tone: "green", title: "Leagues in the nav",
              val: !s.leagues.length || s.leagues.length >= SPORT_CODES.length ? "All"
                : `${s.leagues.length} of ${SPORT_CODES.length}`, chev: true, attrs: 'data-set-open="leagues"' }),
    setItem({ ico: "star", tone: "green", title: "Your teams",
              val: !s.teams.length ? "None" : s.teams.length > 2 ? `${s.teams.length} teams`
                : escapeHtml(s.teams.map(setTeamName).join(", ")), chev: true, attrs: 'data-set-open="teams"' }),
    setItem({ tag: "label", ico: "palette", tone: "green", title: "Team colours",
              sub: team1 ? escapeHtml(`${team1} on the bar, the Live disc and the lit tab`) : "Follow a team first",
              end: setSwitch(s.teamColors === "on", `data-set-switch="teamColors"${s.teams.length ? "" : " disabled"}`) }),
  ]));
  out.push(`<div id="set-notif">${notifGroupHTML()}</div>`);
  const sl = localStorage.getItem("ff_user"), es = localStorage.getItem("ff_espn_league");
  out.push(setGroup("Connected", [
    setItem({ ico: "football", tone: "amber", title: "Fantasy leagues",
              val: sl && es ? "Sleeper · ESPN" : sl ? "Sleeper" : es ? "ESPN" : "Not linked", chev: true,
              attrs: 'data-set-open="fantasy"' }),
    setItem({ ico: "calendar", tone: "amber", title: "Calendar",
              val: !inn ? "Sign in" : _calLink ? "On" : "Off", chev: true, attrs: 'data-set-open="calendar"' }),
    ...widgetRows(inn),
  ], "Read-only, and none of them asks for a platform password."));
  out.push(setGroup("Help", [
    setItem({ ico: "compass", title: "Show me around", attrs: 'data-set-tour="1"' }),
    setItem({ ico: "book", title: "How the model works", href: "#methodology", chev: true }),
    setItem({ ico: "shield", title: "Privacy Policy", href: "privacy.html", chev: true }),
    setItem({ ico: "info", title: "Terms of Service", href: "terms.html", chev: true }),
  ]));
  if (inn) {
    out.push(setGroup("Your data", [
      setItem({ ico: "download", title: "Download my data", attrs: 'data-act="acctExport"' }),
      setItem({ ico: "search", title: "Clear search history", attrs: 'data-act="acctSearchClear"' }),
      setItem({ ico: "logout", title: "Sign out everywhere", sub: "Every device, this one too",
                attrs: 'data-act="acctSignOutAll"' }),
    ]));
    out.push(setGroup("", [
      setItem({ ico: "logout", tone: "red", title: "Sign out", danger: true, attrs: 'data-act="acctSignOut"' }),
      setItem({ ico: "trash", tone: "red", title: "Delete account", danger: true, attrs: 'data-act="acctDelete"' }),
    ], "Delete removes the account and every bet, league and search we hold for it. It can’t be undone."));
  }
  return out.join("");
}

/* The screen a row opens: Back, its title, its own list or form. */
function setPageHTML(page) {
  const s = settings();
  const head = (title) => `<button type="button" class="set-back" data-set-open="">${icon("chev", 16)}Settings</button>
    <h2 class="set-page-h">${title}</h2>`;
  if (page === "tz") {
    return head("Time zone") + setGroup("", TZ_CHOICES.map(([v, label]) => setItem({
      title: escapeHtml(label), end: v === s.tz ? setCheck() : "",
      attrs: `data-set-key="tz" data-set-val="${escapeAttr(v)}" aria-pressed="${v === s.tz ? "true" : "false"}"` })),
    "Every time on the site reads in this zone. This device follows the phone’s own.");
  }
  if (page === "leagues") {
    return head("Leagues in the nav") + setGroup("", SPORT_CODES.map((c) => {
      const on = !s.leagues.length || s.leagues.includes(c);
      return setItem({ title: escapeHtml((LEAGUE_LABEL && LEAGUE_LABEL[c]) || c.toUpperCase()),
                       end: on ? setCheck() : "", attrs: `data-set-league="${escapeAttr(c)}" aria-pressed="${on}"` });
    }), "All of them, unless you narrow it. The league you are looking at always shows.");
  }
  if (page === "teams") {
    return head("Your teams") + (s.teams.length ? setGroup("", s.teams.map((t) => setItem({
      ico: "star", tone: "gold", title: escapeHtml(setTeamName(t)),
      sub: escapeHtml((t.split(":")[0] || "").toUpperCase()), end: '<span class="set-val">Remove</span>',
      attrs: `data-set-unfav="${escapeAttr(t)}" aria-label="${escapeAttr(`Stop following ${setTeamName(t)}`)}"` })),
    "Their games ride at the front of the strip and wear a star. Picks stay ordered by edge — floating your teams up a ranked board would say the model likes them more than it does.")
      : `<p class="set-foot set-empty">None yet. Open a game and tap the ☆ beside a team.</p>`);
  }
  if (page === "password") {
    return head("Password") + `<div class="set-list">
        <label class="set-field"><span>Current password</span>
          <input type="password" class="acct-old" autocomplete="current-password" maxlength="200"></label>
        <label class="set-field"><span>New password</span>
          <input type="password" class="acct-new" autocomplete="new-password" maxlength="200"></label>
      </div>
      <div class="set-actions">
        <button class="btn primary" data-act="acctChangePassword">Change password</button>
        <button type="button" class="btn ghost acct-forgot" data-act="acctGoForgot">Email me a reset link</button>
        <p class="acct-note"></p>
      </div>
      <p class="set-foot">Changing it signs out every other device — a new password is usually the answer to
        “somebody else may have this”.</p>`;
  }
  if (page === "plan") return head("Membership") + `<div id="billing-slot"></div>`;
  if (page === "code") {
    return head("Redeem a code") + `<div class="set-code">${codeBoxHTML((_billStatus && _billStatus.codes) || {})}</div>`;
  }
  if (page === "invite") {
    setTimeout(invFill, 0);
    return head("Invite friends") + `<div id="set-invite" class="inv-screen"><p class="set-foot">Loading…</p></div>`;
  }
  if (page === "passkeys") {
    setTimeout(pkFill, 0);
    return head("Passkeys") + `<div id="set-pk">${pkHTML()}</div>`;
  }
  if (page === "gift") {
    setTimeout(giftFill, 0);
    return head("Gift a month") + `<div id="set-gift"><p class="set-foot">Loading…</p></div>`;
  }
  if (page === "fantasy") return head("Fantasy leagues") + ffLinksHTML();
  if (page === "calendar") return head("Calendar") + `<div id="set-cal">${calRowHTML()}</div>`;
  _setPage = "";
  return setListHTML();
}

/* INVITE FRIENDS (Ethan, 2026-10-25: a paid member's code gives a new
   member 25% off a month and the member 25% off their next — both $6.25,
   engine/referrals says why never a percentage). A member sees their code,
   a link to share and how it has done; anybody else can add a friend's
   code before their first membership. */
async function invFill() {
  const host = document.getElementById("set-invite");
  if (!host) return;
  let v = null;
  try {
    const r = await fetch("/api/account/referral", { credentials: "same-origin", cache: "no-store" });
    if (r.ok) v = await r.json();
  } catch (e) { v = null; }
  if (!v) { host.innerHTML = `<p class="set-foot">Sign in to see your code.</p>`; return; }
  const $ = (c) => `$${(c / 100).toFixed(2)}`;
  host.innerHTML = v.code ? `
    <div class="inv-hero"><b>Give $6.25, get $6.25</b>
      <p>A friend who joins with your code gets $6.25 off their first payment — a quarter of a month. When they pay,
        $6.25 comes off your next bill. Every friend, no limit.</p></div>
    <div class="inv-code"><span class="inv-k">Your code</span><b>${escapeHtml(v.code)}</b>
      <button type="button" class="btn primary" data-inv="share">Share your link</button>
      <button type="button" class="btn ghost" data-inv="copy">Copy</button></div>
    <p class="set-foot inv-note" role="status"></p>
    ${setGroup("How it’s gone", [
      setItem({ tag: "div", ico: "people", tone: "gold", title: "Joined with your code", val: String(v.joined || 0) }),
      setItem({ tag: "div", ico: "card", tone: "gold", title: "Paid", val: String(v.paid || 0) }),
      setItem({ tag: "div", ico: "gem", tone: "gold", title: "Credited to you", val: $(v.credited_cents || 0) }),
      ...(v.waiting_cents ? [setItem({ tag: "div", ico: "clock", tone: "gold", title: "Waiting",
        val: $(v.waiting_cents), sub: "Lands on your next bill once you’re on a plan." })] : []),
    ], "A credit comes off your next invoice by itself; more than one bill’s worth carries to the next.")}`
    : v.used_code ? `<div class="inv-hero"><b>Your friend’s code is on</b>
        <p>${escapeHtml(v.used_code)} takes $6.25 off your first payment when you pick a plan.</p>
        <a class="btn primary" href="#paywall">See the plans</a></div>`
    : `<div class="inv-hero"><b>Have a friend’s code?</b>
        <p>It takes $6.25 off your first payment. Members get their own code to share once they join.</p></div>
      <form class="inv-add" data-inv-form><input name="code" maxlength="16" autocomplete="off" autocapitalize="characters"
        placeholder="Referral code" aria-label="Referral code"><button class="btn primary" type="submit">Add</button></form>
      <p class="set-foot inv-note" role="status"></p>`;
  const note = (t) => { const n = host.querySelector(".inv-note"); if (n) n.textContent = t; };
  host.querySelectorAll("[data-inv]").forEach((b) => b.addEventListener("click", async () => {
    const text = "Live scores, a chat in every game, and the picks graded in public. $6.25 off your first month:";
    if (b.dataset.inv === "share" && navigator.share) {
      try { await navigator.share({ title: "Qellys Book", text, url: v.link }); return; } catch (e) { if (e && e.name === "AbortError") return; }
    }
    try { await navigator.clipboard.writeText(v.link); note("Link copied."); } catch (e) { note(v.link); }
  }));
  const form = host.querySelector("[data-inv-form]");
  if (form) form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = String(new FormData(form).get("code") || "").trim();
    if (!code) return;
    try {
      const r = await fetch("/api/account/referral", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) });
      const out = await r.json().catch(() => ({}));
      if (r.ok) { invFill(); return; }
      note(out.error || "That code didn’t take.");
    } catch (err) { note("Couldn’t reach the server. Try again."); }
  });
}

/* The Membership group, from the billing status (renderBilling). */
function planRowsHTML(s) {
  if (s === null) {
    return setGroup("Membership", [setItem({ ico: "gem", tone: "gold", title: "Plan", val: "…" })]);
  }
  if (!s || !s.signed_in) return "";
  const plan = PLANS.find((p) => p.id === s.plan);
  const trial = String(s.status || "") === "trialing";
  const ending = s.cancel_at_end || String(s.status || "") === "canceled";
  const when = s.period_end ? new Date(s.period_end * 1000).toLocaleDateString([],
    { year: "numeric", month: "short", day: "numeric" }) : "";
  const rows = [];
  if (s.entitled) {
    const name = plan ? plan.name : s.comped ? "Complimentary" : "Member";
    rows.push(setItem({ ico: "gem", tone: "gold", title: "Plan",
                        val: `${escapeHtml(name)} · ${trial ? "Free trial" : ending ? "Ending" : "Active"}`,
                        chev: true, attrs: 'data-set-open="plan"' }));
    if (when) {
      rows.push(setItem({ ico: "calendar", tone: "gold", title: trial ? "Trial ends" : ending ? "Access until" : "Renews",
                          val: escapeHtml(when) }));
    }
    if (s.customer_id) rows.push(setItem({ ico: "card", tone: "gold", title: "Manage billing", chev: true,
                                           attrs: 'data-act="billPortal"' }));
  } else {
    rows.push(setItem({ ico: "gem", tone: "gold", title: "Plan", val: "None", chev: true, attrs: 'data-set-open="plan"' }));
    if (s.configured) rows.push(setItem({ ico: "card", tone: "gold", title: "See the plans", gold: true, chev: true,
                                          attrs: 'data-act="billSeePlans"' }));
  }
  // GIFT A MONTH (engine/gifts), once a gift price is set at Stripe.
  if (s.gifts) rows.push(setItem({ ico: "ticket", tone: "gold", title: "Gift a month", val: "$25", chev: true, attrs: 'data-set-open="gift"' }));
  rows.push(setItem({ ico: "ticket", tone: "gold", title: "Redeem a code", chev: true, attrs: 'data-set-open="code"' }));
  rows.push(setItem({ ico: "people", tone: "gold", title: "Invite friends",
                      val: s.entitled ? "Give $6.25, get $6.25" : "Have a friend’s code?", chev: true, attrs: 'data-set-open="invite"' }));
  return setGroup("Membership", rows, s.live === false ? "Stripe test mode — no real money moves."
    : "Card details go to Stripe, never to this server.") + `<p class="set-foot bill-note" role="status"></p>`;
}

/* The Notifications group: this phone's alerts, and the two emails. */
function notifGroupHTML() {
  const inn = !!(_acctUser && _acctUser.signed_in);
  const st = _mailState;
  const rows = [setItem({ ico: "bell", tone: "red", title: "Alerts on this phone", href: "#alerts", chev: true })];
  let foot = "";
  if (!inn) {
    foot = "Sign in to get the morning card or the nightly recap by email.";
  } else if (st && st.available) {
    rows.push(setItem({ tag: "label", ico: "sun", tone: "red", title: "Morning card", sub: "The day’s picks, by email",
                        end: setSwitch(!!st.morning, 'data-mail="morning"') }));
    rows.push(setItem({ tag: "label", ico: "moon", tone: "red", title: "Nightly recap", sub: "How last night graded",
                        end: setSwitch(!!st.nightly, 'data-mail="nightly"') }));
    foot = "Every email carries a one-click unsubscribe.";
  } else if (st && st.available === false) {
    foot = "Email is not switched on yet — the digests are built and nothing can send them until a delivery "
      + "provider is configured. Nothing here is subscribed to in the meantime.";
  } else if (st === false) {
    foot = "Could not read your email settings.";
  }
  return setGroup("Notifications", rows, foot);
}

/* YOUR PLAYERS ON THE IPHONE WIDGET (engine/widgetfeed, deploy/ios/native):
   only inside the iPhone app, where its WidgetKey plugin is. On asks the box
   for the account's widget key and hands it to the app, which leaves it
   where the widget reads it; off deletes the key on the box and clears the
   phone. Signing out clears the phone too (app.js acctSignOut). */
const widgetPlugin = () => {
  const C = typeof window !== "undefined" && window.Capacitor;
  return C && C.isNativePlatform && C.isNativePlatform() && C.Plugins && C.Plugins.WidgetKey;
};
let _widgetOn = null;
function widgetRows(inn) {
  const P = widgetPlugin();
  if (!P || !inn) return [];
  if (_widgetOn === null) {
    _widgetOn = false;
    Promise.resolve(P.status()).then((r) => {
      _widgetOn = !!(r && r.on);
      const sw = document.querySelector("[data-widget-switch]");
      if (sw) sw.setAttribute("aria-checked", String(_widgetOn));
    }).catch(() => {});
  }
  return [setItem({ tag: "label", ico: "bell", tone: "amber", title: "iPhone widget",
                    sub: "Your players on the Home Screen and lock screen",
                    end: setSwitch(_widgetOn, 'data-widget-switch="1"') })];
}
async function widgetFlip(sw) {
  const P = widgetPlugin();
  if (!P) return;
  const on = !_widgetOn;
  sw.setAttribute("aria-checked", String(on));
  try {
    const r = await fetch("/api/widget/key", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(on ? {} : { off: true }) });
    const got = r.ok ? await r.json() : null;
    if (!got) throw new Error("refused");
    if (on) await P.set({ key: got.key });
    else await P.clear();
    _widgetOn = on;
  } catch (e) {
    sw.setAttribute("aria-checked", String(!!_widgetOn));
  }
}
if (typeof window !== "undefined" && !window._widgetBound) {
  window._widgetBound = true;
  document.addEventListener("click", (e) => {
    const sw = e.target.closest && e.target.closest("[data-widget-switch]");
    if (sw) { e.preventDefault(); widgetFlip(sw); }
  });
}

/* YOUR GAMES IN YOUR CALENDAR (engine/calfeed, docs/IDEAS.md 12): your
   teams' games this week and every game in a parlay you saved, in the
   phone's own calendar. A calendar app cannot sign in, so the address is
   the key — "New link" replaces it and the old one stops answering. */
let _calLink = null;
function calRowHTML() {
  if (!(_acctUser && _acctUser.signed_in)) {
    return `<p class="set-foot set-empty">Sign in to put your teams’ games and your saved parlays in your calendar.</p>`;
  }
  if (!_calLink) {
    return setGroup("", [setItem({ ico: "calendar", tone: "amber", title: "Add my games to my calendar", gold: true,
                                   attrs: 'data-cal="get"' })],
      "Your teams’ games this week and every game in a parlay you saved — never a pick.");
  }
  // webcal:// is the same address, which a phone hands to its calendar;
  // built from the https one through safeHref, never taken on trust.
  const web = safeHref(_calLink.url), cal = web === "#" ? "#" : "webcal://" + web.replace(/^https?:\/\//i, "");
  return setGroup("", [
    setItem({ ico: "calendar", tone: "amber", title: "Open in Calendar", href: cal, chev: true }),
    setItem({ ico: "link", tone: "amber", title: "Copy link", attrs: 'data-cal="copy"' }),
    setItem({ ico: "sync", tone: "amber", title: "New link", sub: "The old one stops working", attrs: 'data-cal="new"' }),
  ], "Google Calendar: Other calendars → From URL, and paste the link. Anyone with the link sees your games; New link stops the old one.");
}
function bindCalRow() {
  const row = document.getElementById("set-cal");
  if (!row) return;
  row.querySelectorAll("[data-cal]").forEach((b) => b.addEventListener("click", async () => {
    const what = b.dataset.cal;
    if (what === "copy") {
      const t = b.querySelector(".set-title") || b;
      try { await navigator.clipboard.writeText(_calLink.url); t.textContent = "Copied"; } catch (e) { t.textContent = _calLink.url; }
      return;
    }
    try {
      const r = await fetch(what === "new" ? "/api/calendar/new" : "/api/calendar/link",
        what === "new" ? { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" }
          : { credentials: "same-origin" });
      if (r.ok) _calLink = await r.json();
    } catch (e) { /* the row stays; a tap tries again */ }
    row.innerHTML = calRowHTML();
    bindCalRow();
  }));
}

/* THE EMAIL ROWS ARE THE ONE SETTING THAT IS NOT LOCAL.
   Everything else here lives in this browser and syncs as a preferences
   blob; a mailing list has to live on the server, because the thing
   that reads it is a cron job at 9am and not a page. So it is fetched
   and written on its own endpoint, and the group says which of three
   states it is in rather than pretending: signed out (there is nobody to
   mail), not configured (the site cannot send mail at all yet — see
   docs/EMAIL.md), or a pair of switches. */
async function renderMailRow() {
  const host = document.getElementById("set-notif");
  if (!host) return;
  if (!(_acctUser && _acctUser.signed_in)) {
    _mailState = null;
    host.innerHTML = notifGroupHTML();
    return;
  }
  let st = null;
  try {
    const res = await fetch("/api/account/digest", { cache: "no-store" });
    st = res.ok ? await res.json() : false;
  } catch (e) { st = false; }
  _mailState = st || false;
  const now = document.getElementById("set-notif");
  if (!now) return;
  now.innerHTML = notifGroupHTML();
  now.querySelectorAll("[data-mail]").forEach((b) =>
    b.addEventListener("click", async () => {
      const next = { morning: !!st.morning, nightly: !!st.nightly };
      next[b.dataset.mail] = !next[b.dataset.mail];
      b.setAttribute("aria-checked", String(next[b.dataset.mail]));
      try {
        await fetch("/api/account/digest", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
      } catch (e) { /* the next tap retries */ }
      renderMailRow();
    }));
}

/* Redraw the settings screen alone: the profile above it stays put. */
function setRepaint() {
  const host = document.querySelector(".qb-settings");
  if (!host) { renderAccount(); return; }
  host.outerHTML = settingsHTML();
  bindSettings();
  renderFantasyLinks();
}

function bindSettings() {
  const host = document.querySelector(".qb-settings");
  if (!host) return;
  renderMailRow();
  bindCalRow();
  if (_acctUser && _acctUser.signed_in) renderBilling();
  const redraw = () => {
    // Prices, stakes and times are read by every renderer on the site,
    // so the whole board redraws rather than the panel patching the two
    // places somebody remembered.
    if (state.data) renderAll();
    applySport();
    setRepaint();
  };
  // ONE LISTENER ON THE SCREEN, not one per row: the Membership rows land
  // after the billing check, and a row drawn later is a row nobody bound.
  host.addEventListener("click", (e) => {
    const hit = (sel) => { const el = e.target.closest(sel); return el && host.contains(el) ? el : null; };
    const open = hit("[data-set-open]");
    if (open) {
      _setPage = open.dataset.setOpen || "";
      setRepaint();
      // The screen opens at its top, under the bar, wherever the list was.
      setScrollTop();
      return;
    }
    const key = hit("[data-set-key]");
    if (key) {
      setSetting(key.dataset.setKey, key.dataset.setVal);
      redraw();
      return;
    }
    const flip = hit("[data-set-switch]");
    if (flip) {
      if (flip.disabled) return;
      const k = flip.dataset.setSwitch;
      setSetting(k, settings()[k] === "on" ? "off" : "on");
      redraw();
      return;
    }
    const league = hit("[data-set-league]");
    if (league) {
      const code = league.dataset.setLeague;
      // An empty list means EVERY league, so the first tap has to
      // materialise the full list before removing one — otherwise
      // un-ticking a league would read as ticking only that one.
      const cur = settings().leagues.length
        ? settings().leagues.slice() : SPORT_CODES.slice();
      const i = cur.indexOf(code);
      if (i >= 0) cur.splice(i, 1); else cur.push(code);
      // Emptied back out means all of them again, which is also the only
      // state that cannot leave somebody with no leagues at all.
      setSetting("leagues", cur.length ? cur : []);
      redraw();
      return;
    }
    const unfav = hit("[data-set-unfav]");
    if (unfav) {
      const [sport, abbr] = String(unfav.dataset.setUnfav).split(":");
      favToggle(abbr, sport);
      redraw();
    }
  });
  host.querySelectorAll("[data-set-tour]").forEach((b) =>
    b.addEventListener("click", () => tourOpen(0)));
}

/* ---- WHERE A LEAGUE GETS LINKED ----------------------------------------
   Ethan, 2026-08-23: "add all the account syncs and logins for fanstasy
   on the actual account page so its all together and that would make the
   most sense on where that would be."

   It is the rule `acctStripHTML` already follows for sign-in, applied to
   leagues: a page that USES a link has to say whether it is linked, but
   it does not need to be a second place to make one. Two forms for one
   thing is how a username gets typed into the copy nobody is looking at,
   and how a Disconnect on one page leaves the other still showing a
   league.

   So the FORMS live here, once. The Fantasy page keeps what it is for —
   the roster, the waiver watch, the league desk — and wears a strip that
   names what is linked and sends you here to change it.

   These render SIGNED OUT as well as in, and that is deliberate: the
   links live in this browser and work without an account (signing in
   only carries them to your other devices). Following "link it on the
   Account page" and landing on a sign-in wall with no way to link would
   be worse than the duplicate forms this replaces.

   Nothing here asks for a platform password. Sleeper needs a username;
   ESPN needs the league id out of your own URL, with the league set
   public. A card that collected a password is a card this site does not
   ship — see espnConnectHTML for why the cookie route is refused. */
function ffLinksHTML() {
  return `<section class="ffl">
    <div class="section-title minor">Fantasy leagues
      <span class="sub">— link once here and every fantasy surface on the
      site reads your own league. Read-only, and none of them asks for a
      platform password.</span></div>
    <div id="ffl-sleeper"></div>
    <div id="ffl-espn"></div>
    <div id="yahoo-zone"></div><div id="yahoo-desk"></div>
  </section>`;
}

function renderFantasyLinks() {
  if (!document.getElementById("ffl-sleeper")) return;
  renderFflSleeper();
  renderFflEspn();
  // Yahoo came here as-is. Its logic is deliberately untouched — Ethan
  // asked for Yahoo to be left alone for now — but it is a LOGIN, and a
  // login left on the Fantasy page would be the one card contradicting
  // the strip that sends people here. Its desk moved with it because
  // renderYahooZone fills both; when Yahoo is picked back up, that split
  // is the thing to fix.
  renderYahooZone();
}

function renderFflSleeper(errMsg) {
  const zone = document.getElementById("ffl-sleeper");
  if (!zone) return;
  const user = localStorage.getItem("ff_user");
  if (!user) {
    zone.innerHTML = sleeperConnectHTML(errMsg);
    const btn = document.getElementById("sleeper-connect");
    if (btn) btn.addEventListener("click", () => {
      const v = (document.getElementById("sleeper-username").value || "").trim();
      if (!v) return renderFflSleeper("Your Sleeper username — the one you "
                                      + "sign in to Sleeper with.");
      localStorage.setItem("ff_user", v);
      acctTouch("fantasy");
      renderFflSleeper();
    });
    return;
  }
  zone.innerHTML = fflLinkedHTML(
    `Sleeper — ${escapeHtml(user)}`,
    "read-only · no password held · your leagues load on the Fantasy page",
    "ffl-sleeper-off");
  const off = document.getElementById("ffl-sleeper-off");
  if (off) off.addEventListener("click", () => {
    // ff_league goes with it. Leaving the chosen league behind means the
    // next account linked here opens on a league it does not own.
    localStorage.removeItem("ff_user");
    localStorage.removeItem("ff_league");
    acctTouch("fantasy");
    renderFflSleeper();
  });
}

/* ---- THE DIAGNOSTIC, WHERE IT CAN BE READ -------------------------------
   `rescueDrawer` has written its findings to localStorage since the
   second attempt at the menu bug, and nothing has ever displayed them.
   Three rounds of guessing were done with the evidence sitting on the
   reporter's own phone, unreachable — no devtools on an installed app.

   It shows only when there is something to show, so it costs a working
   install nothing and it cannot be mistaken for a normal feature. */
function menuDiagHTML() {
  let rescues = [], log = [];
  try {
    rescues = JSON.parse(localStorage.getItem(MENU_RESCUE_KEY) || "[]");
    log = JSON.parse(localStorage.getItem(MENU_LOG_KEY) || "[]");
  } catch (e) { return ""; }
  if (!rescues.length && !log.length) return "";
  const text = JSON.stringify({ rescues, menu: log }, null, 1);
  const rows = log.slice(0, 14).map((r) =>
    `<div class="mdg-row"><b>${escapeHtml(r.t || "")}</b>
       <span>${escapeHtml(r.what || "")}</span>
       <span class="mdg-why">${escapeHtml(r.why || "")}</span>
       <span class="mdg-view">${escapeHtml(r.view || "")}${
         r.standalone ? " · app" : ""}</span></div>`).join("");
  return `
    <section class="card mdg">
      <div class="section-title minor">Menu diagnostics
        <span class="sub">— recorded on this device because the menu
        misbehaved here. Send this to support and it can be fixed from
        the record instead of from a description.</span></div>
      ${rescues.length ? `<p class="mdg-note">${rescues.length}
        drawer rescue(s) recorded — the panel did not arrive on its
        own.</p>` : ""}
      ${rows ? `<div class="mdg-log">${rows}</div>` : ""}
      <div class="mdg-acts">
        <button class="btn" data-act="menuDiagCopy">Copy the record</button>
        <button class="btn ghost" data-act="menuDiagClear">Clear it</button>
      </div>
      <textarea class="mdg-raw" readonly rows="6"
        aria-label="Menu diagnostics">${escapeHtml(text)}</textarea>
    </section>`;
}

function acctLegacyCardHTML() {
  const a = acctState();
  if (a) {
    return `<div class="card" style="margin-bottom:16px">
      <div class="card-head"><div><div class="player">Account — ${escapeHtml(a.name)}</div>
        <div class="subtitle">Your bets, league link and bankroll follow this name to every
          device that signs in — stored on your own computer, nowhere else.</div></div>
        <div style="display:flex;gap:8px">
          <button class="btn" data-act="acctSyncNow">Sync now</button>
          <button class="btn" data-act="acctSignOut">Sign out</button>
        </div></div>
      <div class="acct-note" style="margin-top:8px;color:var(--text-mute);font-size:0.85em">${escapeHtml(_acctNote)}</div>
    </div>`;
  }
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head"><div><div class="player">Make an account (optional)</div>
      <div class="subtitle">Pick a name and this page’s info follows you to every device —
        it lives on your own computer, not a company’s server. The PIN is optional and
        just keeps others on your Wi-Fi out. Still no sportsbook logins, ever.</div></div></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
      <input type="text" class="acct-name" placeholder="account name" maxlength="24"
        autocomplete="off" style="flex:1;min-width:140px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <input type="text" class="acct-pin" placeholder="PIN (optional)" maxlength="12"
        inputmode="numeric" autocomplete="off" style="width:120px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <button class="btn" data-act="acctGo" data-arg="create">Create</button>
      <button class="btn" data-act="acctGo" data-arg="signin">Sign in</button>
    </div>
    <div class="acct-note" style="margin-top:8px;color:var(--text-mute);font-size:0.85em">${escapeHtml(_acctNote)}</div>
  </div>`;
}

/* ---------------- Yahoo, the one platform that needs approval ----------

   Ethan, 2026-08-15, plays on Sleeper, ESPN and Yahoo.

   WHY THERE IS A CONNECT BUTTON HERE AND NOWHERE ELSE ON THIS SITE.
   Sleeper is public. ESPN is public when a league says so. Yahoo has no
   public read at all — but it has the RIGHT kind of private one: you
   approve it on Yahoo’s own screen, this app never sees a password, and
   you can revoke it from your Yahoo account page whenever you like. That
   is the opposite of pasting a session cookie, which is why a private
   ESPN league is still refused and this is not.

   The token never reaches this page. The browser is told THAT it is
   connected, never what makes it work. */
async function renderYahooZone() {
  const zone = document.getElementById("yahoo-zone");
  if (!zone) return;
  let s;
  try {
    const r = await fetch("/api/yahoo/status");
    s = await r.json();
  } catch (e) { zone.innerHTML = ""; return; }

  if (!s.app_registered) {
    /* NOTHING. THIS IS A SETUP STEP, NOT A FEATURE.

       It used to render a card telling the reader to register a developer
       app, paste two values into a config file and restart the server.
       Ethan, 2026-08-23, with it circled on the live site: "lets get all
       the little things like this telling ME what to do off the website
       since this website is live for anyone to use."

       He is right, and it is worse than untidy — every visitor was being
       handed the operator's to-do list, complete with the names of the
       settings the server reads. A person who cannot act on an instruction
       should not be shown one, so until Yahoo is actually connectable this
       panel does not exist. */
    zone.innerHTML = "";
    return;
  }

  if (!s.connected) {
    zone.innerHTML = `<div class="card">
      <div class="section-title">Yahoo league
        <span class="sub">— approve once on Yahoo’s own page</span></div>
      <p class="rank-help">Yahoo will show you a short code. Paste it back
        here. No password is shared with this app, and you can revoke it
        from your Yahoo account page at any time.</p>
      <div class="ld-connect">
        <button class="btn" id="yahoo-open">Open Yahoo’s approval page</button>
        <input id="yahoo-code" class="rank-input" placeholder="Paste the code Yahoo shows"
          autocomplete="off" spellcheck="false">
        <button class="btn ghost" id="yahoo-connect">Connect</button>
      </div>
      <p class="rank-help" id="yahoo-msg"></p></div>`;
    const msg = document.getElementById("yahoo-msg");
    document.getElementById("yahoo-open").addEventListener("click", async () => {
      try {
        const r = await fetch("/api/yahoo/start");
        const d = await r.json();
        if (!r.ok) throw new Error(d && d.error);
        window.open(d.url, "_blank", "noopener");
      } catch (e) {
        msg.textContent = String((e && e.message) || e);
      }
    });
    document.getElementById("yahoo-connect").addEventListener("click", async () => {
      const code = (document.getElementById("yahoo-code").value || "").trim();
      msg.textContent = "Exchanging the code…";
      try {
        const r = await fetch("/api/yahoo/connect", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d && d.error);
        renderYahooZone();
      } catch (e) {
        msg.textContent = String((e && e.message) || e);
      }
    });
    return;
  }

  zone.innerHTML = `<div class="card"><p class="loading">Reading your Yahoo
    leagues…</p></div>`;
  let leagues = [];
  try {
    const r = await fetch("/api/yahoo/leagues");
    const d = await r.json();
    if (!r.ok) throw new Error(d && d.error);
    leagues = d.leagues || [];
  } catch (e) {
    zone.innerHTML = `<div class="card"><div class="warning">${icon("warn")}
      Yahoo connected, but the league list failed: ${
        escapeHtml(String((e && e.message) || e))}</div></div>`;
    return;
  }
  let picked = localStorage.getItem("ff_yahoo_league") || "";
  if (!leagues.some((l) => l.league_key === picked))
    picked = (leagues[0] || {}).league_key || "";

  zone.innerHTML = `<div class="card">
    <div class="card-head">
      <div><div class="player">Yahoo league</div>
        <div class="subtitle">connected · read-only · revocable from your
          Yahoo account page</div></div>
      <div class="ld-connect">
        ${leagues.length ? `<select id="yahoo-league" class="rank-input">
          ${leagues.map((l) => `<option value="${escapeHtml(l.league_key)}"
            ${l.league_key === picked ? "selected" : ""}>${
            escapeHtml(l.name)}${l.season ? ` · ${escapeHtml(l.season)}` : ""}
            </option>`).join("")}</select>` : ""}
        <button class="btn ghost" id="yahoo-disconnect">Disconnect</button>
      </div>
    </div>
    ${leagues.length ? "" : `<p class="rank-help">This Yahoo account is not
      in any NFL league right now.</p>`}</div>`;

  document.getElementById("yahoo-disconnect").addEventListener("click", async () => {
    await fetch("/api/yahoo/disconnect", { method: "POST" });
    const desk = document.getElementById("yahoo-desk");
    if (desk) desk.innerHTML = "";
    renderYahooZone();
  });
  const sel = document.getElementById("yahoo-league");
  if (sel) sel.addEventListener("change", () => {
    localStorage.setItem("ff_yahoo_league", sel.value);
    acctTouch("fantasy");
    renderLeagueDesk(sel.value, "", "yahoo", "yahoo-desk");
  });
  if (picked) {
    localStorage.setItem("ff_yahoo_league", picked);
    renderLeagueDesk(picked, "", "yahoo", "yahoo-desk");
  }
}

function sleeperConnectHTML(msg) {
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head"><div><div class="player">My league — Sleeper sync</div>
      <div class="subtitle">Free and read-only: see YOUR roster’s usage trends, trade flags,
        and who’s unrostered in YOUR league. No password — just your Sleeper username.</div></div></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
      <input id="sleeper-username" type="text" placeholder="Sleeper username"
        style="flex:1;min-width:180px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <button class="btn" id="sleeper-connect">Connect</button>
    </div>
    ${msg ? `<div class="warning" style="margin-top:10px">${icon('warn')} ${escapeHtml(msg)}</div>` : ""}
  </div>`;
}

/* The Friends card on the Account page. Signed-out it renders nothing —
   unlike settings, there is no meaningful device-local half of a
   friendship. */
function friendsCardHTML() {
  if (!(_acctUser && _acctUser.signed_in)) return "";
  const soc = _socCache;
  const friends = (soc && soc.friends) || [];
  const inv = (soc && soc.invite) || null;
  const days = inv ? Math.max(1, Math.round(inv.expires_in_s / 86400)) : 0;
  // Settings rows since 2026-10-25 (docs/VISUAL_AUDIT.md): a friend a row,
  // the invite link a group of its own.
  // Find people (js/social.js, the Search tab): anybody by name or
  // @handle, not only a link sent to them.
  return `<section class="qb-friends set-screen">
    ${setGroup("", [setItem({ href: "#feed/search", ico: "search", tone: "gold", title: "Find people",
        sub: "Search anyone by name or @handle — follow them or add them", chev: true })])}
    ${setGroup("Friends", friends.length ? friends.map((f) => setItem({ lead: msgAvatar(f.name), title: escapeHtml(f.name),
        end: `<button type="button" class="btn ghost fr-x" data-unfriend="${escapeAttr(String(f.id))}"
          title="Remove — closes the channel both ways" aria-label="Remove ${escapeAttr(f.name)}">Remove</button>` }))
      : [setItem({ ico: "user", title: "No friends yet", sub: "Text somebody your invite link" })],
      `Send picks back and forth. Friends are made by name from <a href="#feed/search">Find people</a>
      or the <a href="#messages">Messages page</a>, or with your invite link — requests wait for a yes,
      and nobody you didn’t say yes to can message you.`)}
    ${inv ? setGroup("Your invite link", [
      setItem({ ico: "link", tone: "gold", title: "Copy my invite link",
                sub: `Good for ${days} day${days === 1 ? "" : "s"}`, attrs: `data-copy-invite="${escapeAttr(inv.token)}"` }),
      setItem({ ico: "sync", title: "Make a new link", sub: "The old one stops working", attrs: "data-revoke-invite" }),
    ], "Anyone who opens it signed in becomes your friend.") : ""}
  </section>`;
}


function msgRequestRow(rq) {
  return `<div class="msg-row unread">
    ${msgAvatar(rq.from)}
    <span class="msg-body">
      <b>${escapeHtml(rq.from)}</b>
      <span class="msg-what">wants to be friends</span>
      <span class="msg-note">Accept and you can send picks both ways.
        Decline and they are never told.</span>
    </span>
    <span class="msg-side">
      <span class="msg-when">${escapeHtml(msgAgo(rq.created_at))}</span>
      <span class="msg-req-btns">
        <button class="btn" data-req-answer="${rq.id}" data-req-yes>Accept</button>
        <button class="btn ghost" data-req-answer="${rq.id}">Decline</button>
      </span>
    </span>
  </div>`;
}

async function renderMessages() {
  const host = document.getElementById("messages-body");
  if (!host) return;
  const u = await acctWho();
  if (state.view !== "messages") return;
  if (!(u && u.signed_in)) {
    host.innerHTML = `<div class="empty-slate">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">Sign in to see your messages</div>
      <div class="es-sub">Texts, picks and parlays your friends send land
        here. Friends are made by invite link or by name — nobody you
        didn’t say yes to can message you.</div></div>`;
    return;
  }
  if (_msgThread) return renderThread(host, _msgThread);
  document.body.classList.remove("msg-thread-open");
  const soc = await socFetch(true);
  if (state.view !== "messages" || _msgThread) return;
  const requests = (soc && soc.requests) || [];
  const threads = (soc && soc.threads) || [];
  const reqBlock = requests.length
    ? `<div class="section-title minor">Friend requests</div>
       <div class="card fr-inbox">${requests.map(msgRequestRow).join("")}</div>`
    : "";
  const rows = threads.map((t) => `
    <button class="msg-row msg-thread-row${t.unseen ? " unread" : ""}"
      data-msg-open="${t.friend_id}" type="button">
      ${msgAvatar(t.name)}
      <span class="msg-body">
        <b>${escapeHtml(t.name)}</b>
        <span class="msg-note">${t.last
          ? `${t.last.mine ? "You: " : ""}${escapeHtml(t.last.preview)}`
          : "No messages yet — say hello."}</span>
      </span>
      <span class="msg-side">
        ${t.last ? `<span class="msg-when">${escapeHtml(msgAgo(
          t.last.created_at))}</span>` : ""}
        ${t.unseen ? `<span class="msg-tab-n">${t.unseen > 9 ? "9+"
          : t.unseen}</span>` : ""}
      </span>
    </button>`).join("");
  const list = threads.length
    ? `<div class="card fr-inbox msg-threads">${rows}</div>`
    : `<div class="empty-slate">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No conversations yet</div>
      <div class="es-sub">Add a friend by name with Find people or New
        message, or text somebody your invite link below — every friend
        gets a thread here.</div></div>`;
  const banner = `<div class="card msg-invite">
    <span class="msg-invite-words"><b>Invite friends. Share picks.</b>
      <span>Send invite links, share parlays, and talk it over.</span></span>
    ${soc && soc.invite ? `<button class="btn"
      data-copy-invite="${escapeAttr(soc.invite.token)}">Invite friends</button>` : ""}
  </div>`;
  host.innerHTML = `
    <div class="msg-head inbox-acts">
      <button class="btn" id="msg-new" type="button">New message</button>
      <a class="btn ghost" href="#feed/search">Find people</a>
    </div>
    <div id="msg-finder" hidden></div>
    ${reqBlock}${list}${banner}`;
  msgBadge();
}

/* One conversation, to Ethan's render (2026-08-26): a FULL message
   page. Back + avatar + name up top, kind filters with counts, date
   separators, name-and-time inside every bubble, share cards drawn like
   a book's ticket — legs with the odds read off the READER's own board,
   under their entitlement, which is the same re-pricing rule the slip
   has always kept — and a composer pinned at the foot. What the render
   drew that is deliberately NOT here: the Online dot (we do not track
   presence and will not), the star and the paperclip (nothing behind
   either), and a Mentions tab (nothing behind it). Risk/To Win rows are
   not drawn because the share never carries a stake — a pointer, not a
   ticket. */
async function renderThread(host, fid) {
  let t = null;
  try {
    const r = await fetch("/api/social/thread", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ friend: fid }),
    });
    if (r.ok) t = await r.json();
  } catch (e) { /* the empty state below is the honest answer */ }
  if (state.view !== "messages" || _msgThread !== fid) return;
  if (!t) {
    _msgThread = 0;
    document.body.classList.remove("msg-thread-open");
    host.innerHTML = `<div class="empty-slate">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">That conversation isn’t yours to open</div>
      <div class="es-sub">Threads exist between friends. If you removed
        this friend, the thread went with them.</div></div>`;
    return;
  }
  document.body.classList.add("msg-thread-open");
  _msgFriendName = t.friend;
  const items = t.items || [];
  _msgLastItems = JSON.stringify(items);
  const nParlay = items.filter((x) => x.kind === "parlay").length;
  const nPick = items.filter((x) => x.kind === "pick").length;
  const tab = (k, label, n) => `<button class="msg-tab${_msgKind === k
    ? " on" : ""}" data-msg-kind="${k}" type="button">${label}${n
    ? `<span class="msg-tab-n">${n}</span>` : ""}</button>`;
  host.innerHTML = `
    <div class="msg-thread">
      <div class="msg-thread-head">
        <button class="btn-quiet" data-msg-back type="button">&#8592; All messages</button>
        <span class="msg-thread-who" id="msg-who">${msgAvatar(t.friend)}<b>${
          escapeHtml(t.friend)}</b>${t.username && t.username !== t.friend
            ? `<span class="msg-who-user">@${escapeHtml(t.username)}</span>`
            : ""}</span>
        <button class="btn-quiet msg-clear-btn" data-msg-clear="${t.friend_id}"
          type="button" title="Clear this conversation from your messages"
          >${icon("cross", 12)} Clear</button>
        <button class="btn-quiet msg-nick-btn" data-msg-nick="${t.friend_id}"
          data-nick-current="${escapeAttr(t.username !== t.friend ? t.friend : "")}"
          data-nick-user="${escapeAttr(t.username || "")}"
          type="button" title="Nickname this friend">${icon("tag", 13)} Nickname</button>
      </div>
      <div class="msg-tabs">
        ${tab("all", "Messages", 0)}
        ${tab("parlay", "Parlays", nParlay)}
        ${tab("pick", "Picks", nPick)}
      </div>
      <div class="msg-bubs" id="msg-bubs">${msgBubsHTML(items)}</div>
      <form class="msg-composer" id="msg-composer" autocomplete="off">
        <input class="msg-search" id="msg-composer-in" maxlength="500"
          placeholder="Message ${escapeAttr(t.friend)}…"
          aria-label="Message ${escapeAttr(t.friend)}">
        <button class="btn" type="submit">Send</button>
      </form>
    </div>`;
  // The PAGE stays put at the top — only the bubble list scrolls.
  window.scrollTo(0, 0);
  msgThreadSize();
  const bubs = document.getElementById("msg-bubs");
  if (bubs) bubs.scrollTop = bubs.scrollHeight;
  const form = document.getElementById("msg-composer");
  const inp = document.getElementById("msg-composer-in");
  if (form && inp) {
    inp.focus();
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const words = inp.value.trim();
      if (!words) return;
      inp.value = "";
      // Optimistic: the bubble is on screen before the round trip
      // answers, and comes back into the box if the server said no.
      if (bubs) {
        bubs.insertAdjacentHTML("beforeend", msgBubble({ kind: "text",
          mine: true, body: words, created_at: Date.now() / 1000 }));
        bubs.scrollTop = bubs.scrollHeight;
      }
      try {
        const r = await fetch("/api/social/dm", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ to: fid, body: words }),
        });
        const out = await r.json().catch(() => ({}));
        if (!r.ok) {
          tfToast(out.error || "That didn’t send.");
          inp.value = words;
          renderThread(host, fid);
        }
      } catch (err) {
        tfToast("Could not reach the server.");
        inp.value = words;
      }
    });
  }
  // Seen AFTER the bubbles have been on screen a beat — and scoped to
  // THIS conversation, so the other threads keep their unread dots.
  setTimeout(() => {
    fetch("/api/social/seen", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ friend: fid }) })
      .then(() => socFetch(true).then(msgBadge))
      .catch(() => {});
  }, 800);
  // A quiet poll while the thread is open, so a reply appears without a
  // refresh. Only the bubble list is touched — never the composer
  // somebody is typing into.
  clearInterval(_msgPoll);
  _msgPoll = setInterval(async () => {
    if (state.view !== "messages" || _msgThread !== fid) {
      clearInterval(_msgPoll);
      return;
    }
    try {
      const r = await fetch("/api/social/thread", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ friend: fid }),
      });
      if (!r.ok) return;
      const t2 = await r.json();
      const blob = JSON.stringify(t2.items || []);
      if (blob === _msgLastItems || state.view !== "messages"
          || _msgThread !== fid) return;
      _msgLastItems = blob;
      const el = document.getElementById("msg-bubs");
      if (el) {
        el.innerHTML = msgBubsHTML(t2.items || []);
        el.scrollTop = el.scrollHeight;
      }
      fetch("/api/social/seen", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ friend: fid }) }).catch(() => {});
    } catch (e) { /* the next tick tries again */ }
  }, 15000);
}

/* Bubbles under date separators, filtered by the kind tabs. The filter
   hides texts around the shares on Parlays/Picks, which is exactly what
   those tabs are for — finding the ticket somebody sent last Tuesday. */
function msgBubsHTML(items) {
  const keep = _msgKind === "all" ? items
    : items.filter((x) => x.kind === _msgKind);
  if (!keep.length) {
    return `<p class="set-empty">${_msgKind === "all"
      ? "No messages yet. Say something, or send a pick over from any pick page."
      : "Nothing of that kind in this conversation yet."}</p>`;
  }
  const out = [];
  let lastDay = "";
  for (const it of keep) {
    const day = new Date((it.created_at || 0) * 1000).toLocaleDateString(
      undefined, tzOpts({ month: "long", day: "numeric", year: "numeric" }));
    if (day !== lastDay) {
      out.push(`<div class="msg-day"><span>${escapeHtml(day)}</span></div>`);
      lastDay = day;
    }
    out.push(msgBubble(it));
  }
  return out.join("");
}

/* My side of a thread wears the same chip the topbar does — initials
   off the signed-in account, never a fake name. */
function msgMyAvatar() {
  const u = typeof _acctUser === "object" && _acctUser ? _acctUser : null;
  const m = acctMark(u);
  return `<span class="msg-ava msg-ava-me"${m.st} aria-hidden="true">${
    escapeHtml(m.ini)}</span>`;
}

// Through tzTime, like every clock on the site — one zone, no
// arithmetic (see the rule above tzOpts).
const msgClock = (ts) => tzTime((ts || 0) * 1000);

function msgBubble(it) {
  const mine = it.mine;
  const head = `<span class="msg-bub-head"><b>${mine ? "You"
    : escapeHtml(_msgFriendName || "")}</b><span class="msg-bub-when">${
    escapeHtml(msgClock(it.created_at))}</span></span>`;
  // The read receipt is REAL: `seen` is the recipient's copy saying it
  // was displayed, the same flag the unread dots run on.
  const ticks = mine ? `<span class="msg-ticks${it.seen ? " seen" : ""}"
    aria-label="${it.seen ? "read" : "sent"}">${it.seen
    ? "&#10003;&#10003;" : "&#10003;"}</span>` : "";
  const body = it.kind === "text"
    ? `<span class="msg-bub-body">${escapeHtml(it.body)}</span>`
    : msgShareCard(it);
  const note = it.kind !== "text" && it.note
    ? `<span class="msg-note">“${escapeHtml(it.note)}”</span>` : "";
  // DELETES FROM YOUR COPY, never theirs — see engine/social's deleting
  // section. The control says so on hover rather than letting somebody
  // assume they have unsent something.
  const rm = it.id ? `<button class="msg-bub-x" data-msg-del="${it.kind}"
      data-msg-del-id="${it.id}" type="button"
      title="Delete this from your messages — they keep their copy"
      aria-label="Delete this message">${icon("cross", 11)}</button>` : "";
  return `<div class="msg-bub-row ${mine ? "mine" : "theirs"}">
    ${mine ? "" : msgAvatar(_msgFriendName)}
    <div class="msg-bub ${mine ? "mine" : "theirs"}${it.kind !== "text"
      ? " share" : ""}">${head}${body}${note}${ticks}${rm}</div>
    ${mine ? msgMyAvatar() : ""}
  </div>`;
}

/* A leg's live price, read off the reader's OWN board — the share
   itself carries only identities, so what shows here is whatever THIS
   account's entitlement already serves. Off-board or other-league legs
   simply show no price, and the card stays a door either way. */
function shareLegLive(sport, l) {
  if (sport !== state.sport) return null;
  const r = findProp(`${slugify(l.player)}-${slugify(l.market)}`);
  if (r) return { odds: r.odds, label: r.market_label || l.market };
  if (GAME_MARKET_WORDS[l.market] && String(l.player).includes("@")) {
    const g = ((state.data || {}).game_bets || []).find((gb) =>
      (gb.matchup || `${gb.away || ""} @ ${gb.home || ""}`) === l.player
      && (gb.market || gb.bet_type || "") === l.market);
    if (g) return { odds: g.odds, label: GAME_MARKET_WORDS[l.market] };
  }
  return null;
}

function msgShareCard(it) {
  const isParlay = it.kind === "parlay";
  const legs = isParlay ? (it.legs || [])
    : [{ player: it.player, market: it.market }];
  let dec = 1, priced = 0;
  const rows = legs.map((l) => {
    const live = shareLegLive(it.sport, l);
    if (live && live.odds != null) {
      const d = mbDecimal(live.odds);
      if (d != null) { dec *= d; priced++; }
    }
    return `<button class="msg-card-leg" type="button"${shareDoorAttrs(
      it.sport, l.player, l.market)}>
      <span class="msg-leg-words"><b>${escapeHtml(l.player)}</b>
        <span>${escapeHtml((live && live.label)
          || String(l.market || "").replace(/_/g, " "))}</span></span>
      ${live && live.odds != null
        ? `<span class="msg-leg-odds">${escapeHtml(american(live.odds))}</span>`
        : `<span class="msg-leg-go">charts &#8594;</span>`}
    </button>`;
  }).join("");
  // Combined price only when EVERY leg priced off this reader's board —
  // the slip's decimal-product arithmetic, never a partial product.
  const combined = isParlay && legs.length >= 2 && priced === legs.length
    ? american(dec >= 2 ? Math.round((dec - 1) * 100)
                        : -Math.round(100 / (dec - 1)))
    : "";
  return `<span class="msg-card">
    <span class="msg-card-head">
      <span class="msg-card-kind${isParlay ? "" : " pick"}">${isParlay
        ? `${legs.length}-LEG PARLAY`
        : `${escapeHtml((it.sport || "").toUpperCase())} PICK`}</span>
      ${combined ? `<span class="msg-card-odds">${combined}</span>` : ""}
    </span>
    ${rows}
  </span>`;
}
