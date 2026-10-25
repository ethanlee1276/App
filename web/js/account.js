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
function pwLapseHTML(s) {
  const st = s && s.signed_in && !s.entitled && s.note ? s.status : "";
  const fix = st === "past_due" || st === "unpaid";
  return fix || st === "canceled" || (st && s.cancel_at_end) ? `
    <div class="card pw-lapse" role="status"><p>${escapeHtml(s.note)}</p>${fix
      ? `<button class="btn primary" data-act="billPortal">Update card</button>
         <p class="pw-lapse-note"></p>` : ""}</div>` : "";
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
    ${pwLapseHTML(status)}
    <section class="pw-hero">
      <h1 class="pw-h1">Members <em>sign in</em> here.</h1>
      <p class="pw-sub">Tonight’s picks, the props and the game reports open
        with a Qellys Book membership. Sign in with the account you already have.</p>
      <div class="pw-store-go">
        <button class="btn primary" data-act="pwSignIn">${signed ? "Your account" : "Log in"}</button>
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
             data-act="coStart">${
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
             data-act="coStart">Choose</button>`
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
        : `<button class="btn ghost pw-login" data-act="pwSignIn">Log in</button>`}
    </header>
    ${pwLapseHTML(status)}

    <section class="pw-hero">
      <h1 class="pw-h1">Data. <em>Edge.</em> Receipts.</h1>
      <p class="pw-sub">Professional sports intelligence. Real-time edges.
        Every call graded in public.</p>
      ${/* FROM sellable(), LIKE THE CARD (audit V-20): the hero promised
            "Start 3 days free" off trialDays alone while the card below,
            asking sellable(), drew "Not available yet" — the primary path
            ended on a dead button. */""}
      ${pwHeroCtaHTML(trialOK && sellable(trialPlan) ? trialDays : 0,
                      PLANS.some((p) => sellable(p.id)))}
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
          data-act="coStart">Get started</button>` : `<a class="btn pw-unlock-go" href="#record">See the record</a>`}
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
    ${s.entitled ? planPanelHTML(s) : none}
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
    out.push(setGroup("Account", [
      setItem({ ico: "mail", tone: "gold", title: "Email", val: escapeHtml(u.email) }),
      setItem({ ico: "lock", tone: "gold", title: "Password", val: "Change", chev: true,
                attrs: 'data-set-open="password"' }),
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
  if (page === "fantasy") return head("Fantasy leagues") + ffLinksHTML();
  if (page === "calendar") return head("Calendar") + `<div id="set-cal">${calRowHTML()}</div>`;
  _setPage = "";
  return setListHTML();
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
  rows.push(setItem({ ico: "ticket", tone: "gold", title: "Redeem a code", chev: true, attrs: 'data-set-open="code"' }));
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
  return `<section class="qb-friends set-screen">
    ${setGroup("Friends", friends.length ? friends.map((f) => setItem({ lead: msgAvatar(f.name), title: escapeHtml(f.name),
        end: `<button type="button" class="btn ghost fr-x" data-unfriend="${escapeAttr(String(f.id))}"
          title="Remove — closes the channel both ways" aria-label="Remove ${escapeAttr(f.name)}">Remove</button>` }))
      : [setItem({ ico: "user", title: "No friends yet", sub: "Text somebody your invite link" })],
      `Send picks back and forth. Friends are made with your invite link, or by name from the
      <a href="#messages">Messages page</a> — requests wait for a yes, and nobody you didn’t say yes to
      can message you.`)}
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
      <div class="es-sub">Add a friend by name with New message, or text
        somebody your invite link below — every friend gets a thread
        here.</div></div>`;
  const banner = `<div class="card msg-invite">
    <span class="msg-invite-words"><b>Invite friends. Share picks.</b>
      <span>Send invite links, share parlays, and talk it over.</span></span>
    ${soc && soc.invite ? `<button class="btn"
      data-copy-invite="${escapeAttr(soc.invite.token)}">Invite friends</button>` : ""}
  </div>`;
  host.innerHTML = `
    <div class="msg-head">
      <button class="btn" id="msg-new" type="button">New message</button>
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
