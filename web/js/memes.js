/* ROCKET RADAR — the meme-coin page, loaded the first time it opens
   (app.js renderMemes, 2026-10-24). A classic script like app.js: it
   shares the page's globals (escapeHtml, icon, paidFetch, state …), and
   its `renderMemes` replaces app.js's loader of the same name, so the
   router and the poll below call the page directly from then on. */
/* ============================================================
   ROCKET RADAR — Solana meme coins, the danger channel drawn loudest
   ============================================================
   The build spec's own base rates are the most important thing on the
   page, so they render FIRST, above every score: ~1.4% graduate, 60% of
   traders lose, 82.8% of high-return tokens show artificial growth,
   41% of volume is wash, the median rug dies inside an hour. The page's
   honest value is FILTERING, not prophecy — which is why momentum and
   risk are two numbers that never blend, risk is a GATE, and nothing
   here journals a bet or touches the sports ledger.

   Token names, symbols and URLs are attacker-controlled strings — a
   token can be NAMED an HTML payload — so everything from the feed goes
   through escapeHtml and links render only for https URLs. */
const MC_BASE_RATES = [
  ["~1.4%", "of pump.fun tokens ever graduate to a real DEX listing"],
  ["60%", "of meme-coin traders lose money; ~3% ever clear $1,000"],
  ["82.8%", "of high-return tokens show evidence of artificial growth"],
  ["41.4%", "of Solana meme-coin volume is wash trading (VanEck)"],
  ["<1 hour", "median lifecycle of a rug pull; median hold is ~62 seconds"],
];

function mcMoney(v) {
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function mcPrice(v) {
  if (v == null || isNaN(v)) return "—";
  return v >= 1 ? `$${v.toFixed(2)}` : `$${Number(v).toPrecision(3)}`;
}

function mcAge(min) {
  if (min == null || isNaN(min)) return "—";
  if (min < 1) return "<1m";
  if (min < 90) return `${Math.round(min)}m`;
  if (min < 48 * 60) return `${(min / 60).toFixed(1)}h`;
  return `${(min / 1440).toFixed(1)}d`;
}

function mcPct(v) {
  if (v == null || isNaN(v)) return `<span style="opacity:.45">—</span>`;
  const c = v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--text-mute)";
  return `<span style="color:${c};font-weight:600">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
}

/* Price over our own snapshot tape — honest resolution (one point per
   launcher refresh, up to 6h), self-contained, no external bytes. The
   LIVE candle chart is the venue's own embed, opened per coin below. */
function mcSpark(series, w = 300, h = 44) {
  const pts = (series || []).filter((p) => p && p[1] != null);
  if (pts.length < 2) return "";
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (t) => x1 === x0 ? 0 : ((t - x0) / (x1 - x0)) * (w - 2) + 1;
  const sy = (v) => y1 === y0 ? h / 2 : h - 3 - ((v - y0) / (y1 - y0)) * (h - 6);
  const d = pts.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
  const up = ys[ys.length - 1] >= ys[0];
  // Snapshots land one per refresh, not on a grid — the scrub data
  // carries each point's own x fraction so the finger snaps to real
  // points instead of an even spacing that doesn't exist.
  const fmtP = (v) => "$" + (v >= 1 ? v.toFixed(2)
    : v >= 0.01 ? v.toFixed(4) : Number(v).toPrecision(3));
  const scrub = escapeAttr(JSON.stringify({
    x: pts.map((p) => x1 === x0 ? 0 : (p[0] - x0) / (x1 - x0)),
    l: pts.map((p) => tzTime(p[0], { hour: "2-digit", minute: "2-digit" })),
    v: pts.map((p) => fmtP(p[1])),
  }));
  return `<svg class="mc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
    role="img" aria-label="price over our snapshot tape" data-scrub="${scrub}"><polyline points="${d}"
    fill="none" stroke="var(--${up ? "good" : "bad"})" stroke-width="1.5"/></svg>`;
}

/* Addresses come from third-party feeds and end up inside an onclick and
   an iframe src — nothing that fails the base58 shape gets either. */
const MC_B58 = /^[1-9A-HJ-NP-Za-km-z]{25,50}$/;

function mcChartRef(c) {
  if (c.pair && MC_B58.test(c.pair)) return { addr: c.pair, kind: "ds" };
  if (c.pool && MC_B58.test(c.pool)) return { addr: c.pool, kind: "gt" };
  return null;
}

//: The rendered board, keyed by mint, so a chart click carries one
//: validated token id instead of a bag of strings through an onclick.
let _mcCoins = {};
//: The coin whose chart is open, surviving re-renders: the board
//: self-refreshes every few seconds and losing your coin to a data
//: tick would make the terminal unusable.
let _mcOpenMint = null;

function mcChartBtn(c, cls) {
  if (!mcChartRef(c) || !MC_B58.test(c.mint || "")) return "";
  return `<button class="${cls || "btn mc-chart-btn"}" type="button"
    data-act="mcShowChart" data-arg="${c.mint}"
    title="Open the venue’s own live candle chart for this pool">Live chart</button>`;
}

/* ONE chart at a time, in the terminal room. Sixty live iframes is a
   tab-killer; one, where you asked for it, is a terminal. The embed is
   the venue's own page for the pool, so the candles are as live as
   Axiom's — they come from the same place. Called from a card or the
   board table it also walks you to the Charts room, because a chart
   opening in a hidden panel is a click that did nothing. */
window.mcShowChart = function (mint, scroll = true) {
  const c = _mcCoins[mint];
  const dock = document.getElementById("mc-chart-dock");
  if (!c || !dock) return;
  const ref = mcChartRef(c);
  if (!ref || !MC_B58.test(ref.addr || "")) return;
  _mcOpenMint = mint;
  // The candle chart is an iframe served by a decentralized-exchange
  // aggregator. Read-only, no wallet and no swap — and still the most
  // trading-venue-looking pixel on the site, which is why it is behind
  // the review flag. See EXTERNAL_MARKET_LINKS.
  const src = !EXTERNAL_MARKET_LINKS ? ""
    : ref.kind === "gt"
      ? `https://www.geckoterminal.com/solana/pools/${ref.addr}?embed=1&info=0&swaps=0`
      : `https://dexscreener.com/solana/${ref.addr}?embed=1&theme=dark&info=0`;
  const i = c.ind || {};
  const stat = (k, v, color) => `<div class="metric"><div class="k">${k}</div>
    <div class="v"${color ? ` style="color:${color}"` : ""}>${v}</div></div>`;
  // ONE header line: name, the five numbers, momentum/risk — everything
  // above the candles is height taken from the candles.
  dock.innerHTML = `<div class="card mc-chart-card">
    <div class="card-head mc-dock-head"><div class="player mc-dock-id">${mcTile(c, 30)}${mcName(c)}
      <span style="color:var(--text-mute);font-weight:400"> — live from ${
        ref.kind === "gt" ? "GeckoTerminal" : "DexScreener"}</span></div>
      <div class="metrics mc-dock-stats">
        ${stat("Price", mcPrice(c.price_usd))}
        ${stat("5m", mcPct((c.price_change || {}).m5))}
        ${stat("1h", mcPct((c.price_change || {}).h1))}
        ${stat("Liq", mcMoney(c.liquidity))}
        ${stat("Top 10", i.top10_share != null ? (i.top10_share * 100).toFixed(0) + "%" : "—")}
      </div>
      <span title="MomentumScore / RiskScore" style="font-weight:800">
        <span style="color:var(--brand)">${c.momentum}</span>
        <span style="color:var(--text-mute)"> / </span>
        <span style="color:${c.risk >= 60 ? "var(--bad)" : "var(--warn)"}">${c.risk}</span></span></div>
    ${src ? `<iframe src="${src}" loading="lazy" title="Live pool chart"
      referrerpolicy="no-referrer" allow="clipboard-write"></iframe>`
      /* NOT an iframe with an empty src — a browser resolves src="" to
         the CURRENT page, which would load the whole app recursively
         inside its own chart dock. The placeholder also keeps the
         "is a chart open" check at mcTick() honest, since that reads
         for an iframe. */
      : `<div class="mc-chart-off">Price chart hidden while the payment
           application is under review. Every number above is ours and is
           unaffected.</div>`}</div>`;
  document.querySelectorAll("#view-memes .mc-pick").forEach((b) =>
    b.classList.toggle("active", b.dataset.mint === mint));
  const panel = dock.closest(".subgroup");
  if (panel && panel.hidden) {
    const tab = document.querySelector(
      '#view-memes .subnav-btn[data-subtab="charts"]');
    if (tab) tab.click();
  }
  if (scroll) dock.scrollIntoView({ behavior: "smooth", block: "start" });
};

/* "Just landed": first sighting on OUR tape within the last ten
   minutes — the coins-moving-IN half of the question the scan exists
   to answer. The badge follows the coin everywhere its name renders. */
function mcNewTag(c) {
  const fs = Number(c && c.first_seen);
  if (!fs || (Date.now() / 1000 - fs) > 600) return "";
  return `<span class="mc-new" title="First seen by our scan under ten minutes ago — this is when it reached the radar, not when the pair was created.">new</span>`;
}

/* The coin's monogram tile — a stable colour from the symbol, so the
   same coin wears the same colour on the watchlist, the cards and the
   dock. No token images on the free feeds; a typed identity beats a
   broken-image icon. */
function mcTile(c, size = 34) {
  const sym = String(c.symbol || c.name || c.mint || "?").replace(/[^A-Za-z0-9]/g, "").slice(0, 4) || "?";
  let h = 0;
  for (const ch of sym) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `<span class="mc-tile" style="width:${size}px;height:${size}px;
    background:hsl(${h} 42% 24%);color:hsl(${h} 70% 78%)">${escapeHtml(sym.slice(0, 3))}</span>`;
}

/* Momentum as a bar you can read at a glance, not a bare digit. */
function mcMomBar(m) {
  const v = Math.max(0, Math.min(100, m || 0));
  const tone = v >= 70 ? "var(--good)" : v >= 45 ? "var(--brand-2)" : "var(--text-mute)";
  return `<span class="mc-mom" title="MomentumScore ${v}/100 — cohort-relative order flow: volume acceleration, unique-buyer growth, buy/sell pressure, price acceleration">
    <i style="width:${v}%;background:${tone}"></i><b style="color:${tone}">${v}</b></span>`;
}

/* Risk as a named badge. The number alone told a newcomer nothing —
   "risk 55" reads as noise; "ELEVATED 55" reads as a verdict. */
function mcRiskBadge(c, gate = 60) {
  const r = c.risk || 0;
  const [label, tone] = r >= gate ? ["GATED", "var(--bad)"]
    : r >= 35 ? ["ELEVATED", "var(--warn)"] : ["LOW RISK", "var(--good)"];
  const why = (c.risk_why || []).length ? ":\n" + c.risk_why.map((w) => "· " + w).join("\n") : "";
  return `<span class="mc-riskb" style="color:${tone};border-color:${tone}"
    title="RiskScore ${r}/100 — authorities, LP lock, holder concentration, liquidity, age, wash pattern${why}">${label} ${r}</span>`;
}

/* One coin's identity cell, shared by cards and the board table. */
function mcName(c) {
  const label = c.symbol || c.name || (c.mint || "").slice(0, 8);
  const inner = `<b>${escapeHtml(label)}</b>${c.name && c.symbol
    ? ` <span style="color:var(--text-mute);font-weight:400">${escapeHtml(String(c.name).slice(0, 28))}</span>` : ""}`;
  const linked = (c.url && /^https:\/\//.test(c.url))
    ? `<a href="${safeHref(c.url)}" target="_blank" rel="noopener" style="color:inherit">${inner}</a>`
    : inner;
  return linked + mcNewTag(c);
}

/* ============================================================
   Rocket Radar's record — did the calls actually go up?
   ============================================================ */
/* Ethan, 2026-08-19: "track which meme coins we recommend and if they
   actually gain value or lose value after we recommend them … make it
   real and accurate."

   Three things this page refuses to do, each of which is how a memecoin
   track record normally lies:

   THE HEADLINE IS THE MEDIAN. A mean return over memecoins is a number
   about the single luckiest row — one 50x drags an average of fifty
   losers into positive territory. Median, hit rate and the worst case
   get equal billing, and the mean is not shown at all.

   THE PEAK IS NOT THE RESULT. A coin that went 5x and round-tripped and
   a coin that never moved both close at 0%, and a board that quotes
   "peaked +400%" without the close is quoting the first one as a win.
   Both numbers sit on the same row, always.

   THE DEAD ONES STAY. Coins leave the feed because liquidity died, and
   dropping them would delete exactly the losses that matter. They are
   counted, labelled, and never folded into the median as an invented
   -100%. */
/* "3h ago" beats a timestamp on a board whose calls resolve in minutes —
   the reader's question is how long this has had to work, not what the
   clock said. Days appear once hours stop being readable. */
function memeWhen(d) {
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function memePct(v, digits = 0) {
  if (v == null || !isFinite(v)) return `<span style="opacity:.45">—</span>`;
  const c = v > 0 ? "good" : v < 0 ? "bad" : "text-mute";
  return `<span style="color:var(--${c});font-weight:700">${
    v > 0 ? "+" : ""}${(v * 100).toFixed(digits)}%</span>`;
}

function memeRecordRow(r) {
  const when = r.ts ? new Date(r.ts * 1000) : null;
  const marks = r.marks || {};
  return `<div class="mr-row${r.gone ? " gone" : ""}">
    <span class="mr-when">${when ? memeWhen(when) : "—"}</span>
    <span class="mr-sym">${escapeHtml(r.symbol || r.mint.slice(0, 4))}
      ${r.channel === "exit" ? `<span class="chip down">EXIT</span>`
        : `<span class="chip up">#${r.rank}</span>`}</span>
    <span class="mr-n">${memePct(marks["1h"])}</span>
    <span class="mr-n">${memePct(marks["24h"])}</span>
    <span class="mr-n">${memePct(r.peak)}</span>
    <span class="mr-n">${memePct(r.last)}</span>
    <span class="mr-tag">${r.gone
      ? `<span class="chip warn" title="The coin stopped appearing in the feed — for a memecoin that usually means the pool is dead">gone</span>`
      : ""}</span>
  </div>`;
}

function memeChannelHTML(name, label, ch, horizons) {
  if (!ch || !ch.calls) {
    return `<div class="card"><div class="section-title">${escapeHtml(label)}</div>
      ${panelEmpty("No calls filed yet. The record starts the first time this channel puts a coin on the board.")}</div>`;
  }
  const p = ch.path || {};
  const rows = horizons.map((h) => {
    const m = (ch.marks || {})[h] || {};
    if (!m.n) {
      return `<tr><td>${h}</td><td colspan="5" style="color:var(--text-mute)">
        no call is ${h} old yet</td></tr>`;
    }
    return `<tr><td>${h}</td><td>${m.n}</td><td>${memePct(m.median)}</td>
      <td>${(m.hit_rate * 100).toFixed(0)}%</td>
      <td>${memePct(m.best)}</td><td>${memePct(m.worst)}</td></tr>`;
  }).join("");
  return `<div class="card">
    <div class="section-title">${escapeHtml(label)}
      <span class="sub">— ${ch.calls} call(s) filed. Median, not mean: one
      50x would drag an average of fifty losers into the green.</span></div>
    <div class="tbl-wrap"><table class="agate mr-tbl">
      <thead><tr><th>After</th><th>Calls</th><th>Median</th><th>Up</th>
        <th>Best</th><th>Worst</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="mr-path">Over the ${p.n} call(s) at least an hour old — the
      same set the table above measures — the median peaked
      ${memePct(p.median_peak)}, bottomed ${memePct(p.median_trough)} and
      sits at ${memePct(p.median_last)}${p.gone ? ` · <b>${p.gone}</b> of
      them left the feed entirely` : ""}${p.never_marked ? `, and
      ${p.never_marked} vanished before we could mark them once — counted
      here, never folded into the median as an invented −100%` : ""}.</p>
  </div>`;
}

/* ============================================================
   THE MEME VERDICT — the medians, and the shape behind them
   ============================================================ */
/* Ethan, 2026-08-20: "of our last 40 calls, the median peaked +31% and
   ended -83%; here's the distribution."

   That sentence is the product. Every meme account on the internet posts
   the one call that went up; almost nobody posts what the median call did
   after they posted it, and nobody at all posts the shape. A ledger that
   keeps the PATH — peak and trough, not just the endpoint — is what makes
   it sayable, and it has been keeping it since it shipped.

   THE HISTOGRAM IS NOT DECORATION. A median of -83% because everything
   sagged is a completely different product from a median of -83% because
   four calls in forty went up tenfold and the rest went to zero. The
   medians cannot tell those apart and the bars can, which is the only
   reason they are here. */
function memeDistBars(dist, total) {
  const rows = (dist || []).filter((b) => b.n > 0);
  if (!rows.length) return "";
  const max = Math.max(...rows.map((b) => b.n));
  return `<div class="md-bars">${(dist || []).map((b) => {
    // Colour by which side of flat the bucket sits on, so the shape reads
    // before the labels do.
    const up = b.label.indexOf("+") === 0 || b.label.indexOf("> +") === 0;
    const w = max ? Math.round((b.n / max) * 100) : 0;
    return `<div class="md-row">
      <span class="md-lab">${escapeHtml(b.label)}</span>
      <span class="md-track"><span class="md-fill${up ? " up" : " down"}"
        style="width:${w}%"></span></span>
      <span class="md-n">${b.n}</span>
    </div>`;
  }).join("")}</div>
  <p class="md-cap">${total} call${total === 1 ? "" : "s"} old enough to have a
  path. Buckets are wider at the top because the interesting question up
  there is “did it double”, not “by how much exactly”.</p>`;
}

/* Below this many followed calls the medians are a small sample wearing a
   percentage. Same principle as the Record page's own gate, and the same
   reason: this panel exists to be believed, so it has to refuse when it
   cannot support the claim. */
const MEME_MIN_CALLS = 20;

function memeVerdictHTML(rec) {
  const chans = (rec && rec.channels) || {};
  const r = (chans.rocket || {}).path || {};
  const marks = ((chans.rocket || {}).marks || {})["24h"] || {};
  const followed = r.followed || 0;
  const pc = (v) => v == null ? "—"
    : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  const tile = (label, value, sub, tone) => `
    <div class="rv-tile${tone ? " " + tone : ""}">
      <div class="rv-v">${value}</div>
      <div class="rv-k">${escapeHtml(label)}</div>
      ${sub ? `<div class="rv-s">${sub}</div>` : ""}
    </div>`;

  const thin = followed < MEME_MIN_CALLS;
  const say = thin ? "" : (() => {
    const peak = r.median_peak, last = r.median_last;
    if (peak == null || last == null) return "";
    const gave = (peak - last) * 100;
    return `<p>Of ${followed} call${followed === 1 ? "" : "s"} we could follow,
      the <b>median peaked ${pc(peak)}</b> and <b>ended ${pc(last)}</b>${
      gave > 5 ? ` — giving back ${gave.toFixed(0)} points between its best
      moment and its last one` : ""}.${
      r.gone ? ` ${r.gone} went to zero and stayed there; they are counted
      here, not dropped.` : ""}</p>
      ${marks.hit_rate != null ? `<p>At 24 hours, <b>${(marks.hit_rate * 100).toFixed(0)}%
      were above the price we called them at</b>${
      marks.down_80 ? `, and ${marks.down_80} had lost four fifths or more` : ""}.</p>` : ""}`;
  })();

  return `<section class="card rv-card">
    <div class="section-title">The verdict
      <span class="sub">— what happened to the coins this page called, including
      the ones that went to zero</span></div>
    <div class="rv-tiles md-tiles">
      ${tile("calls", String(r.n || 0),
             followed ? `${followed} followable` : "none old enough yet")}
      ${tile("median peak", pc(r.median_peak), "best moment after the call",
             r.median_peak != null && r.median_peak > 0 ? "good" : "")}
      ${tile("median now", pc(r.median_last), "where they sit today",
             r.median_last != null && r.median_last >= 0 ? "good" : "warn")}
      ${tile("gone", String(r.gone || 0), "stopped quoting entirely",
             r.gone ? "warn" : "")}
    </div>
    ${thin ? `<p class="rv-early">${icon("warn", 14)}
        <b>Too early to call.</b> ${followed} followable call${followed === 1 ? "" : "s"}
        against the ${MEME_MIN_CALLS} this panel needs before a median means
        anything. The rows below are the record so far and they are real —
        they are just not yet a pattern.</p>`
      : `<div class="rv-read md-read">
          <div>${memeDistBars(r.dist_last, followed)}</div>
          <div class="rv-says">${say}
            <p class="md-warn">This is what the radar said, not a return anyone
            could have earned — it assumes nothing about entry, exit, slippage
            or the size you could actually fill. Most memecoins go to zero.
            Publishing this is the point.</p>
          </div>
        </div>`}
  </section>`;
}

function memeRecordHTML(rec) {
  if (!rec || !rec.calls_total) {
    return `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <h3>The record starts with the next build</h3>
      <p>Every coin this page puts on the rocket list or flags for exit is
      filed at the price shown, then re-checked on every refresh — 1 hour,
      6 hours, 24 hours and a week later. Nothing here is back-filled and
      nothing is ever removed, including the coins that go to zero.</p></div>`;
  }
  const hz = rec.horizons || ["1h", "6h", "24h", "7d"];
  const recent = (rec.recent || []).slice(0, 30);
  return `${memeVerdictHTML(rec)}
    ${memeChannelHTML("rocket", "Rockets — what we called up",
      (rec.channels || {}).rocket, hz)}
    ${memeChannelHTML("exit", "Danger — what we called broken",
      (rec.channels || {}).exit, hz)}
    <div class="card">
      <div class="section-title">Every recent call
        <span class="sub">— the receipts, newest first. A call is one coin
        on one channel on one day, so a coin sitting on the board for six
        hours counts once.</span></div>
      <div class="mr-head">
        <span>When</span><span>Coin</span><span>1h</span><span>24h</span>
        <span>Peak</span><span>Now</span><span></span></div>
      ${recent.map(memeRecordRow).join("")
        || `${panelEmpty("No calls yet.")}`}
    </div>
    <p class="mr-note">This is a record of what the radar said, not advice
    and not a return you could have earned: it assumes nothing about entry,
    exit, slippage or the size you could actually fill. Most memecoins go
    to zero. The point of publishing this is that you can see when ours
    did.</p>`;
}

async function renderMemes() {
  const host = document.getElementById("memes-body");
  if (!host) return;
  // paidFetch: `coins`, `rocket` and `exits` are gated, so the public
  // file carries the counts and none of the scan. The record below
  // stays on boardFetch — it is free and it is the evidence.
  const gotMc = await fetchJSON(() => paidFetch("memecoins.json"), "memecoins");
  const d = gotMc.data;
  // The record is its own file and its own failure: a board with no
  // record still draws, and a record with no board is still readable.
  let rec = null;
  try {
    const res = await boardFetch("data/memerecord.json", { cache: "no-cache" });
    if (res.ok) rec = await res.json();
  } catch (e) {}

  /* One line closed, the full block a tap away. The first cut of this
     page gave the base rates a five-tile card that pushed the charts —
     the product — below the fold ("you can barely see the charts").
     The facts stay unskippable: the strip renders on every room, closed
     or open, and the summary line IS the five numbers. */
  const honesty = `
    <details class="card mc-honesty">
      <summary><span class="mc-honesty-head">How to read this page — and the base rates</span>
        <span class="mc-honesty-line">~1.4% ever graduate · 60% of traders lose ·
        82.8% artificial growth · 41.4% wash volume · median rug &lt;1h</span></summary>
      <div class="mc-legend">
        <div class="mc-leg"><b>Momentum 0–100</b><span>Percentile vs the live cohort:
          volume acceleration 30%, unique-buyer growth 30%, buy/sell pressure 25%,
          price acceleration 15%. It ranks motion — it does not predict.</span></div>
        <div class="mc-leg"><b>Risk gate</b><span>Authorities, LP lock, holder
          concentration, liquidity, age and wash patterns score 0–100; at the gate
          the coin is barred from the rocket list no matter how hard it moves.</span></div>
        <div class="mc-leg"><b>Danger channel</b><span>Exit signals in priority
          order — liquidity draining, pressure flipping, price rolling over — fired
          for every coin, gated or not. Leaving matters most on the worst coins.</span></div>
      </div>
      <div class="mc-rates">${MC_BASE_RATES.map(([n, t]) =>
        `<div class="mc-rate"><span class="mc-rate-n">${n}</span><span>${t}</span></div>`).join("")}</div>
      <div class="mc-honesty-foot">A tracker’s genuine value is filtering scams and enforcing
      disciplined exits, not predicting moonshots. Nothing on this page is a buy signal,
      nothing is journaled as a bet, and none of it touches the sports model.</div>
    </details>`;

  if (!d && gotMc.failed) {
    setStandaloneSource("DexScreener + GeckoTerminal free feeds", "Meme coins", false);
    host.innerHTML = honesty + outageHTML("the meme-coin board", "memecoins");
    return;
  }
  if (!d || !(d.coins || []).length) {
    host.innerHTML = honesty + `
      <div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No meme-coin data yet</div>
      <div class="es-sub">The launcher polls GeckoTerminal’s new + trending Solana pools and
      DexScreener’s pair snapshots on every refresh (free, no key). If this persists,
      one of those feeds is declining and the page fills again when it recovers.</div></div>`;
    return;
  }
  setStandaloneSource("DexScreener + GeckoTerminal free feeds",
                      "Meme coins · live venue data");

  // The hero — Ethan (2026-08-10): "Meme coin page has no direction. I
  // have no clue what I'm looking at." The first thing on the page now
  // SAYS what the page is, what the three systems do, and how live the
  // data is. Everything in it is measured, nothing is a promise.
  const upd = (d.generated_at || "").slice(11, 19);
  const clear = (d.n || 0) - (d.gated || 0);
  const hero = `
    <div class="card mc-hero">
      <div class="mc-hero-words">
        <div class="mc-hero-title">Rocket Radar
          <span class="mc-hero-live">${icon("dot", 10)} live · rescans ~15s</span></div>
        <p>Solana meme coins, straight off the venues. <b>Momentum</b> ranks what’s
        moving right now (order flow, not hype). The <b>risk gate</b> keeps
        rug-shaped coins off the rocket list. The <b>danger channel</b> fires exit
        signals — including on coins the gate already refused. Tap any coin for its
        live chart; hover any score for its receipt.</p>
      </div>
      <div class="mc-hero-stats">
        <div class="mc-hs"><b>${d.n || 0}</b><span>tracked</span></div>
        <div class="mc-hs"><b style="color:var(--good)">${clear}</b><span>clear the gate</span></div>
        <div class="mc-hs"><b style="color:var(--warn)">${d.gated || 0}</b><span>gated</span></div>
        <div class="mc-hs"><b style="color:var(--bad)">${(d.exits || []).length}</b><span>flashing exit</span></div>
        <div class="mc-hs"><b>${escapeHtml(upd || "—")}</b><span>last scan</span></div>
      </div>
    </div>`;

  const byMint = {};
  for (const c of d.coins || []) byMint[c.mint] = c;
  const heat = (m) => m >= 70 ? "var(--good)" : m >= 45 ? "var(--brand)" : "var(--text-mute)";
  const riskColor = (r) => r >= (d.risk_gate || 60) ? "var(--bad)" : r >= 35 ? "var(--warn)" : "var(--good)";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;

  /* Indicator chips with receipts in the hover — same contract as the
     intel flags: every claim names its number. */
  const chipsFor = (c) => {
    const i = c.ind || {};
    const ch = [];
    ch.push(`<span class="chip" title="Pair age. Median rug dies inside an hour — under 30 minutes is a risk point.">${mcAge(i.age_min)} old</span>`);
    if (i.liq_mc != null) ch.push(`<span class="chip${i.liq_mc < 0.03 ? " down" : ""}" title="Liquidity ÷ market cap. Under 3% means one sell craters it.">liq/MC ${(i.liq_mc * 100).toFixed(1)}%</span>`);
    if (i.ratio_m5 != null) ch.push(`<span class="chip${i.ratio_m5 >= 1.2 ? " up" : i.ratio_m5 < 1 ? " down" : ""}" title="Buys per sell, last 5 minutes.">b/s ${i.ratio_m5.toFixed(2)}</span>`);
    if (i.vol_spike != null) ch.push(`<span class="chip" title="5-minute volume vs its share of the hour. 1.0 = steady pace.">vol ×${i.vol_spike.toFixed(1)}</span>`);
    if (i.buyers_m5 != null) ch.push(`<span class="chip" title="UNIQUE buying wallets in 5 minutes (GeckoTerminal) — broad wallet count is the anti-wash signal.">${i.buyers_m5} buyers/5m</span>`);
    if (i.top10_share != null) ch.push(`<span class="chip${i.top10_share > 0.30 ? " down" : ""}" title="Share of supply held by the ten largest accounts EXCLUDING the largest — which is almost always the pool’s own vault, market structure rather than an insider. Over 30% is the insider-concentration flag.">top10 ${(i.top10_share * 100).toFixed(0)}%</span>`);
    if (i.freeze_auth === true) ch.push(`<span class="chip down" title="RugCheck: the dev can FREEZE your tokens — the honeypot switch. The single worst flag on this board.">freeze auth</span>`);
    if (i.mint_auth === true) ch.push(`<span class="chip down" title="RugCheck: the dev can mint more supply at will.">mint auth</span>`);
    if (i.mint_auth === false && i.freeze_auth === false) ch.push(`<span class="chip up" title="RugCheck: mint and freeze authority both renounced — the two worst switches are off. A prerequisite, not a promise.">authorities renounced</span>`);
    if (i.lp_locked_pct != null && i.lp_locked_pct < 50) ch.push(`<span class="chip down" title="RugCheck: how much of the liquidity pool is locked. Unlocked LP can be pulled at any moment.">LP ${i.lp_locked_pct.toFixed(0)}% locked</span>`);
    if (c.carried) ch.push(`<span class="chip" title="No longer on the trending/new lists — kept on the scan while its tape lives (2h), because a dying coin leaves trending at exactly the moment the exit signals matter most.">off-trending</span>`);
    if (i.whale_share != null && i.whale_share > 0.15) ch.push(`<span class="chip down" title="The largest single account after the pool. One seller this size can crater the chart alone.">whale ${(i.whale_share * 100).toFixed(0)}%</span>`);
    if (i.vol_accel != null) ch.push(`<span class="chip${i.vol_accel > 0 ? " up" : ""}" title="Volume second derivative off our own snapshot tape — the ignition signal.">accel ${i.vol_accel > 0 ? "+" : ""}${i.vol_accel.toFixed(0)}</span>`);
    if (i.wash_flag) ch.push(`<span class="chip down" title="Volume spiked >500% while price moved <5% — volume with no one in it (arXiv:2507.01963).">wash pattern</span>`);
    if (c.boosted) ch.push(`<span class="chip down" title="Someone is PAYING DexScreener to promote this token.">paid promo</span>`);
    return ch.join("");
  };

  const rocketCards = (d.rocket || []).map((m) => byMint[m]).filter(Boolean)
    .map((c) => `<article class="card" style="--grade-color:${heat(c.momentum)}">
      <div class="card-head">
        <div class="card-id">
          <div class="score-ring" title="MomentumScore 0–100, percentile vs the live cohort — volume acceleration 30%, unique-buyer growth 30%, buy/sell pressure 25%, price acceleration 15%"
            style="background:conic-gradient(${heat(c.momentum)} ${c.momentum * 3.6}deg, rgba(255,255,255,.08) 0)">
            <span>${c.momentum}</span></div>
          <div>
            <div class="player">${mcName(c)}</div>
            <div class="subtitle">${mcPrice(c.price_usd)} · liq ${mcMoney(c.liquidity)} · MC ${mcMoney(c.market_cap || c.fdv)}</div>
            <div class="pick">5m ${mcPct((c.price_change || {}).m5)} · 1h ${mcPct((c.price_change || {}).h1)}</div>
          </div>
        </div>
        ${mcRiskBadge(c, d.risk_gate || 60)}
      </div>
      <div class="chips" style="margin-top:10px">${chipsFor(c)}</div>
      ${mcSpark(c.spark) ? `<div class="mc-spark-wrap" title="Price over our own snapshot tape — one point per refresh, up to six hours">${mcSpark(c.spark)}</div>` : ""}
      ${mcChartBtn(c) ? `<div style="margin-top:10px">${mcChartBtn(c)}</div>` : ""}
    </article>`).join("");

  const exitCards = (d.exits || []).map((m) => byMint[m]).filter(Boolean)
    .map((c) => `<article class="card" style="--grade-color:var(--bad)">
      <div class="card-head">
        <div class="card-id"><div>
          <div class="player">${mcName(c)}</div>
          <div class="subtitle">${mcPrice(c.price_usd)} · liq ${mcMoney(c.liquidity)} · 5m ${mcPct((c.price_change || {}).m5)}</div>
        </div></div>
        ${mcRiskBadge(c, d.risk_gate || 60)}
      </div>
      <ul class="mc-exit-why">${(c.exit_why || []).map((w) =>
        `<li>${escapeHtml(w)}</li>`).join("")}</ul>
      ${mcSpark(c.spark) ? `<div class="mc-spark-wrap">${mcSpark(c.spark)}</div>` : ""}
      ${mcChartBtn(c) ? `<div style="margin-top:10px">${mcChartBtn(c)}</div>` : ""}
    </article>`).join("");

  const rows = (d.coins || []).slice()
    .sort((a, b) => (b.momentum || 0) - (a.momentum || 0))
    .map((c, ix) => {
      const i = c.ind || {};
      const gated = c.risk >= (d.risk_gate || 60);
      return `<tr${gated ? ` class="mc-gated" title="RiskScore ${c.risk} — over the gate; excluded from the rocket list${(c.risk_why || []).length ? ":\n" + c.risk_why.map((w) => "· " + w).join("\n") : ""}"` : ""}>
        <td class="num">${ix + 1}</td>
        <td>${mcName(c)}</td>
        <td class="num">${mcAge(i.age_min)}</td>
        <td class="num">${mcPrice(c.price_usd)}</td>
        <td class="num">${mcPct((c.price_change || {}).m5)}</td>
        <td class="num">${mcPct((c.price_change || {}).h1)}</td>
        <td class="num">${mcMoney(c.liquidity)}</td>
        <td class="num">${mcMoney((c.volume || {}).h1)}</td>
        <td class="num">${i.ratio_m5 != null ? i.ratio_m5.toFixed(2) : "—"}</td>
        <td class="num">${i.buyers_m5 != null ? i.buyers_m5 : "—"}</td>
        <td class="num"${i.top10_share != null && i.top10_share > 0.30 ? ` style="color:var(--bad);font-weight:700"` : ""}>${i.top10_share != null ? (i.top10_share * 100).toFixed(0) + "%" : "—"}</td>
        <td class="num" style="color:${heat(c.momentum)};font-weight:700">${c.momentum}</td>
        <td class="num" style="color:${riskColor(c.risk)};font-weight:700">${c.risk}${gated ? `<span class="mc-gate-tag">gated</span>` : ""}</td>
        <td>${mcChartBtn(c, "mc-chart-link") || ""}</td>
      </tr>`;
    }).join("");

  /* THE ROOMS. Same organization the Record page earned: the tab bar is
     subtabbedHTML, the choice is remembered, an empty room never draws a
     tab. Charts is the FIRST room — Ethan: the charts lead, everything
     else is a tap away — with a coin-picker terminal that auto-opens the
     top coin so the page lands on live candles, not on a menu. */
  _mcCoins = byMint;
  const rocketSet = new Set(d.rocket || []);
  const chartable = [
    ...(d.rocket || []).map((m) => byMint[m]).filter(Boolean),
    ...(d.coins || []).slice()
      .sort((a, b) => (b.momentum || 0) - (a.momentum || 0))
      .filter((c) => !rocketSet.has(c.mint)),
  ].filter((c) => mcChartRef(c) && MC_B58.test(c.mint || "")).slice(0, 24);

  // The watchlist replaced a strip of bare coin names — "It just shows
  // coin names with rocket next to it." Every row now carries the
  // decision surface: rank, identity tile, price, 5-minute move, the
  // momentum bar and the named risk badge. Same machinery underneath
  // (mc-picker / mc-pick / mcShowChart), so the poll-and-restore
  // contract is untouched.
  const picker = chartable.map((c, ix) => `<button type="button"
      class="mc-pick" data-mint="${c.mint}" data-act="mcShowChart" data-arg="${c.mint}"
      title="Open the live chart">
      <span class="mc-rank">${ix + 1}</span>
      ${mcTile(c, 32)}
      <span class="mc-pick-id"><b>${escapeHtml((c.symbol || c.name || c.mint.slice(0, 6)).slice(0, 12))}${
        rocketSet.has(c.mint) ? ` <span class="mc-pick-tag">rocket</span>` : ""}${mcNewTag(c)}</b>
        <em>${escapeHtml(String(c.name || "").slice(0, 22))}</em></span>
      <span class="mc-pick-nums"><b>${mcPrice(c.price_usd)}</b>
        <span class="mc-pick-pct">${mcPct((c.price_change || {}).m5)} 5m</span></span>
      ${mcMomBar(c.momentum)}
    </button>`).join("");

  const chartsRoom = !chartable.length ? "" : `
    <div class="mc-term">
      <div class="mc-watch">
        <div class="mc-watch-head">Watchlist
          <span>momentum-ranked · tap a coin to chart it</span></div>
        <div class="mc-picker" role="group" aria-label="Pick a coin to chart">${picker}</div>
      </div>
      <div id="mc-chart-dock"></div>
    </div>`;

  const rocketRoom = `
    <div class="section-title">Rocket list
      <span class="sub">— highest momentum among coins UNDER the risk gate. Momentum is
      cohort-relative order flow: acceleration and unique buyers, not RSI lines. Hover any
      chip or score for its receipt.</span></div>
    <div class="cards wide">${rocketCards ||
      `<div class="empty-slate" style="grid-column:1/-1"><div class="es-icon">${icon("signal", 30)}</div>
        <div class="es-title">Nothing clears the gate right now</div>
        <div class="es-sub">Either every tracked coin is over the risk line — common, and the
        page working as designed — or the snapshot tape is too short: acceleration needs
        three sightings of a coin, so give the refresh loop a few minutes.</div></div>`}</div>`;

  const dangerRoom = `
    <div class="section-title">Danger channel
      <span class="sub">— exit signals in the spec’s priority order, IGNORING the gate: a
      dangerous coin crashing is exactly what this channel is for.</span></div>
    <div class="cards wide">${exitCards ||
      `${panelEmpty("No exit signals on the current board.")}`}</div>`;

  const boardRoom = `
    <div class="stats">
      ${tile("Coins tracked", d.n || 0, "GT new + trending, DS boosts")}
      ${tile("Clear the risk gate", (d.n || 0) - (d.gated || 0), `RiskScore under ${d.risk_gate || 60}`)}
      ${tile("Behind the gate", d.gated || 0, "momentum can’t buy them back")}
      ${tile("Flashing exit", (d.exits || []).length, "the danger channel")}
    </div>
    <div class="section-title">Full board
      <span class="sub">— every tracked coin, momentum-sorted. Dimmed rows are over the
      risk gate — shown, not hidden, because “filtered out” and “never seen” must not
      look identical (hover for the reasons).</span></div>
    <div class="card" style="padding:0;overflow-x:auto">
      <table class="agate mc-board"><thead><tr>
        <th>#</th><th>Coin</th><th>Age</th><th>Price</th><th>5m</th><th>1h</th>
        <th>Liq</th><th>Vol 1h</th><th title="Buys per sell, last 5 minutes">B/S 5m</th>
        <th title="Unique buying wallets, last 5 minutes">Buyers</th>
        <th title="Supply held by the ten largest accounts, excluding the largest (almost always the pool vault). Measured for the first 20 coins in discovery order.">Top 10</th>
        <th>Momentum</th><th>Risk</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;

  host.innerHTML = hero + honesty + subtabbedHTML("memes", [
    ["charts", "Radar",
     "the watchlist and the live chart — where you actually sit", chartsRoom],
    ["rocket", "Rockets",
     "the movers that also clear the risk gate, with their receipts", rocketRoom],
    ["danger", "Danger",
     "exit signals — get-out warnings, including on gated coins", dangerRoom],
    ["board", "Screener",
     "every tracked coin, every column, momentum-sorted", boardRoom],
    ["record", "Record",
     "what happened to the coins we called — every one of them",
     memeRecordHTML(rec)],
  ]) + `
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      Top-10 holder share comes from Solana’s public RPC and EXCLUDES the largest account,
      which for a live coin is almost always the trading pool’s own vault — the number
      judges wallets, not market structure, and “—” means unmeasured, never safe.
      What this board still cannot see (paid firehose tier, deliberately parked — the doc
      has the map): mint/freeze authority, honeypot checks, dev-wallet sells, bundled
      snipers, holder velocity, smart-money wallets. Their absence is stated here rather
      than silently scored as safe. Volume acceleration and the sparklines run off our own
      snapshot tape and need a few sightings of a coin — young boards under-read them
      honestly. The Live chart button opens the venue’s own candle chart for the pool.
      Updated ${escapeHtml(formatStamp(d.generated_at, "time"))}; this board rescans
      every ~15 seconds (new-coin discovery ~25s — the free feeds’ rate-limit ceiling),
      and this page re-pulls on the same clock without disturbing an open chart.</p>`;
  bindSubtabs(host);
  // Land on candles, not on a menu — but never yank someone out of the
  // room they chose last time, and never scroll a page that just opened.
  // A re-render keeps the coin the user had open, falling back to the
  // top of the board only when that coin left it.
  const dock = document.getElementById("mc-chart-dock");
  if (chartable.length && dock && !dock.closest(".subgroup").hidden) {
    const want = (_mcOpenMint && byMint[_mcOpenMint]
                  && mcChartRef(byMint[_mcOpenMint]))
      ? _mcOpenMint : chartable[0].mint;
    mcShowChart(want, false);
  }
}

/* The board self-refreshes while you watch. The launcher rebuilds the
   JSON every ~15 seconds (its own thread — see launch.py), so the page
   re-pulls on a matching clock. Two refusals keep it civil: a hidden
   tab never polls, and an OPEN live chart is never yanked — the candle
   iframe is the venue's own stream and already moves second by second;
   re-rendering under it would reload the chart every tick, which is
   the one way to make a live terminal feel broken. The rocket/danger/
   board rooms refresh freely because nothing in them holds state. */
const MEMES_POLL_MS = 20000;
setInterval(() => {
  if (state.view !== "memes" || document.hidden) return;
  const dock = document.getElementById("mc-chart-dock");
  const watching = dock && dock.querySelector("iframe")
    && !dock.closest(".subgroup").hidden;
  if (watching) return;
  renderMemes();
}, MEMES_POLL_MS);
