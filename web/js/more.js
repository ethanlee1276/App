/* THE MORE MENU'S PAGES — loaded the first time one of them opens (app.js loadRoom,
   2026-10-24): Intel, the team pages, the UFC card, Zeno, Status, Features, About, the standings,
   rosters and injuries, and the lab.
   A classic script like app.js: it shares the page's globals, and each
   page's renderer here replaces app.js's stub of the same name. Every
   declaration was moved whole out of app.js, in order, with its own
   comments: nothing outside these pages calls any of it (chosen by
   TypeScript's own reading of the file, and checked by name against every
   other script and page). */
/* One helper so a citation reads identically whether or not it links.
   Returns an <a> when the flag is on and a plain <span> when it is off,
   so the reader still sees the market name and the wallet either way.

   NO CLASS ARGUMENT, deliberately. The first cut took one, and the mono
   `.wallet` face then lived on whichever element the flag happened to
   produce — so turning the flag off also un-monospaced every wallet
   address, which has nothing to do with payment review and is the one
   place on the site you compare strings character by character. Style
   the wrapper instead: `<span class="wallet">${extLink(...)}</span>`.
   The dress stays put and only the anchor moves. */
function extLink(url, label) {
  return EXTERNAL_MARKET_LINKS
    ? `<a href="${safeHref(url)}" target="_blank" rel="noopener"
         style="color:inherit">${label}</a>`
    : `<span>${label}</span>`;
}

/* THE GLOSSARY (audit V-15): every word the boards use without stopping
   to define it, defined once, in plain English. It lives on the Features
   page and has its own door in the menu and on each board's legend. */
const GLOSSARY = [
  ["Most Likely", "Tonight’s bets ranked by our chance they hit, in four tiers: Top, Strong, Solid, Slight. A ranking by likelihood, not a claim the price is wrong."],
  ["Edge pick", "A bet where our probability beats the book’s price by enough to stake. The bets we put units on."],
  ["Edge", "Our chance minus the chance the price implies, in percentage points. +4 means we think it hits four points more often than the price says."],
  ["EV", "Expected value: what one unit returns on average at this price if our chance is right. +5% means five cents per dollar staked, over many bets."],
  ["Worth a look", "Close to the bar but not over it. Shown so you can see what nearly made it; never staked."],
  ["Pick of the Day", "The single strongest pick across every league, chosen once a day and graded in its own book."],
  ["Riding", "A bet already placed on an earlier pull. It rides at the price it was taken at, even if today’s price no longer clears the bar."],
  ["Journaled", "Written to the record at the moment it is published, at the price shown, with a timestamp that cannot be changed afterwards."],
  ["u (unit)", "One standard stake. Results are in units so they read the same whatever your bankroll."],
  ["Paper", "A bet tracked and graded with no money on it — measured before it is trusted."],
  ["Probation", "A league or market being measured on paper until its record clears the bar to be staked."],
  ["CLV", "Closing line value: whether the price moved our way before the game. Beating the close is the best early sign a pick was good, before results arrive."],
  ["Calibration", "Whether our percentages come true: picks we called 60% should hit about 60% of the time."],
  ["Brier", "A score for probability forecasts, lower is better. Compared against the market’s own score on the same bets."],
  ["De-vig", "Removing the book’s margin from a pair of prices so they add to 100% and read as a fair chance."],
  ["Long shot", "A bet at long odds tracked in its own bucket, never mixed into the headline record."],
  ["Prediction market", "Kalshi and Polymarket: exchanges where traders buy contracts on outcomes. Their prices are shown as a chance and as odds, beside the books’."],
  ["Zeno", "A person’s real tickets, shown beside the model’s picks and never inside them."],
  ["Pikkit", "The app Zeno’s tickets are synced from, so they are his real bets at his real prices."],
];

function glossaryHTML() {
  return `<section class="ft-sec" id="glossary">
    <div class="section-title">Glossary <span class="sub">— every word the boards use, in plain English</span></div>
    <dl class="gloss">${GLOSSARY.map(([t, d]) =>
      `<div class="gloss-row"><dt>${escapeHtml(t)}</dt><dd>${escapeHtml(d)}</dd></div>`).join("")}</dl>
  </section>`;
}

function renderFeatures() {
  const host = document.getElementById("features-body");
  if (!host) return;
  const groups = storeApp()
    ? FEATURES.map(([n, b, rows]) => [n, b, rows.filter((r) => !STORE_APP_ROWS.has(r[0]))]).filter((g) => g[2].length)
    : FEATURES;
  const jump = `<a class="ft-jump" href="#glossary" data-glossary>Glossary</a>` + groups.map(([name]) =>
    `<a class="ft-jump" href="#features-${escapeAttr(slugify(name))}">${escapeHtml(name)}</a>`).join("");
  const count = groups.reduce((a, [, , rows]) => a + rows.length, 0);
  host.innerHTML = `
    <p class="ft-lede">Everything on this site, in one list — ${count} of them.
      Anything with an arrow opens where it lives; the rest are parts of a screen
      and say which one. Nothing here is behind the wall until you click it.</p>
    <div class="ft-jumps">${jump}</div>
    ${groups.map(([name, blurb, rows]) => `
      <section class="ft-sec" id="features-${escapeAttr(slugify(name))}">
        <div class="section-title">${escapeHtml(name)}
          <span class="sub">— ${escapeHtml(blurb)}</span></div>
        <div class="ft-list">${rows.map(([title, desc, view]) => `
          <${view ? "button" : "div"} class="ft-row${view ? " door" : ""}"${
            view ? ` type="button" data-ftview="${escapeAttr(view)}"` : ""}>
            <div class="ft-row-main">
              <b>${escapeHtml(title)}</b>
              <span>${escapeHtml(desc)}</span>
            </div>
            ${view ? `<span class="ft-go" aria-hidden="true">&#8594;</span>` : ""}
          </${view ? "button" : "div"}>`).join("")}</div>
      </section>`).join("")}
    ${glossaryHTML()}`;
  host.querySelectorAll("[data-ftview]").forEach((el) =>
    el.addEventListener("click", () => switchView(el.dataset.ftview, true)));
}

//: What the prior carries this week, in words the reader can check.
function talentWeightLine(t) {
  const w = t && t.weight_now != null ? Math.round(Number(t.weight_now) * 100) : null;
  const g = t && t.games_median != null ? Number(t.games_median) : null;
  if (w == null) return "It carries ~25% of a Week-1 projection and decays toward 5% by November.";
  return `It carries <b>${w}%</b> of the net rating this week${
    g != null ? ` (median ${g} game${g === 1 ? "" : "s"} played)` : ""} and
    reaches its 5% floor by the tenth game, because by then a team’s own
    results have answered the question.`;
}

function talentCardHTML(t) {
  if (!t) return "";
  if (!t.available) return talentWarnHTML(t);
  const L = t.layers || {};
  const chip = (name, n) => `<span class="chip ${n ? "good" : "down"}">${
    escapeHtml(name)} ${n ? n : "—"}</span>`;
  const fit = t.fit || {};
  return `<div class="card" style="--tone:var(--good);margin-bottom:12px">
    <div class="player">${iconMark("check")}Preseason talent prior — ${plural(t.teams_with_prior, "team")}</div>
    <div class="lf-chips" style="margin:6px 0">
      ${chip("recruiting", L.talent)}${chip("blue-chip", L.blue_chip)}
      ${chip("returning", L.returning)}${chip("portal", L.portal)}
    </div>
    <div style="color:var(--text-body);font-size:var(--fs-md)">
      ${fit.fitted
        ? `One standard deviation of recruiting talent is worth
           ${escapeHtml(String(fit.points_per_sd))} net points a game, fitted on
           ${fit.samples} completed team-seasons (r=${escapeHtml(String(fit.r))}).`
        : `The talent-to-points slope is still a documented prior rather than a
           fit — ${escapeHtml(fit.note || "")}`}
      ${talentWeightLine(t)}
      ${(t.missing_layers || []).length
        ? `<b> Not loaded: ${escapeHtml((t.missing_layers || []).join(", "))}.</b>` : ""}
    </div>
    <div class="mini" style="margin-top:6px;opacity:.8">How the four inputs are
      used: the recruiting composite IS the prior; blue-chip ratio only halves it
      where the two disagree on a roster’s sign; returning production speeds or
      slows its decay by up to 30%; the portal moves it by at most 2.5 points.
      Its value against the closing line is unmeasured — the leak-free replays
      that grade this model leave the prior out.</div></div>`;
}

/* EVERY SPORT GETS THE VENUE BEHIND ITS MATCHUP (Ethan, 2026-09-24:
   "make sure you change that so every sport now has [the] new render").
   The game page does it for the leagues with a game page; a UFC fight is
   a card on the UFC page, so each card wears one of the six octagon
   renders (variants/octagon-1..6), picked by the fight's own name so a
   bout keeps its picture from one refresh to the next, under the Pick of
   the Day's fade. */
function fightArtStyle(m) {
  const key = String((m && (m.fight || m.pick)) || "");
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  const n = (h % 6) + 1;
  return `--fight-art:url(${absoluteSrc(venueSrc(`img/venues/variants/octagon-${n}.jpg`))})`;
}
function fightEyebrowHTML(m) {
  const bits = ["UFC", String((m && m.division) || "").replace(/_/g, " ")].filter(Boolean);
  return `<div class="gp-eyebrow">${icon("stadium", 14)} ${escapeHtml(bits.join(" · "))}</div>`;
}

/* The Lab — the walk-forward backtests, published.

   The Book grades what we actually bet, going forward. This grades the
   MODEL, replayed over stored history, which is the only evidence that
   accrues faster than the forward sample. Two things it must never let
   the reader believe:

   1. That a big ROI against NAIVE baseline lines means we beat a book.
      It means the model beats a trailing average — a different and much
      weaker claim — so basis is stated on every row and a naive ROI is
      rendered muted with the caveat attached.
   2. That a good Brier is good. Brier has no natural scale; the bar is
      what you'd score predicting the base rate every time. Skill (vs
      that bar) leads, and hedging — forecasts huddling near the base
      rate — is called out, because a model that answers "about 50%" to
      everything is perfectly calibrated and perfectly useless. */
/* Under this many backtest bets, ROI is noise wearing a percentage. The
   harnesses say it in their own summaries ("ROI — last, and meaningless
   under ~100 bets"); the page has to say it too, or the one number
   everybody reads first is the one least entitled to be believed. */
const LAB_ROI_MIN_BETS = 100;

function labSkillTile(m) {
  const sk = m.skill;
  if (!sk) return recTile("Skill vs guessing", "—",
    `needs 100+ graded forecasts (have ${m.n})`);
  const beats = sk.skill > 0;
  return recTile("Skill vs guessing",
    `${sk.skill >= 0 ? "+" : ""}${(sk.skill * 100).toFixed(1)}%`,
    `vs always saying ${(sk.base_rate * 100).toFixed(0)}% (the base rate)`,
    { lead: true, tone: beats ? "pos" : "neg",
      help: "Brier scored against the base-rate baseline. Positive = the "
          + "model’s probabilities carry information; negative = you would "
          + "do better ignoring it." });
}

function labBins(m) {
  const bins = (m.bins || []).filter((b) => b.n);
  if (!bins.length) return "";
  const rows = bins.map((b) => {
    const gap = b.hit_rate - b.mean_pred;
    const w = Math.min(100, Math.abs(gap) * 300);
    return `<tr>
      <td>${(b.lo * 100).toFixed(0)}–${(b.hi * 100).toFixed(0)}%</td>
      <td class="num">${(b.mean_pred * 100).toFixed(0)}%</td>
      <td class="num">${(b.hit_rate * 100).toFixed(0)}%</td>
      <td class="num ${gap >= 0 ? "pos" : "neg"}">${gap >= 0 ? "+" : ""}${(gap * 100).toFixed(0)}</td>
      <td><span class="lab-bar ${gap >= 0 ? "pos" : "neg"}" style="width:${w}%"></span></td>
      <td class="num">${b.n.toLocaleString()}</td></tr>`;
  }).join("");
  return `<table class="agate lab-bins">
    <thead><tr><th>Said</th><th class="num">Predicted</th><th class="num">Actual</th>
      <th class="num">Gap</th><th></th><th class="num">n</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function labPropCard(m, note) {
  const naive = m.basis === "naive";
  /* A THIRD BASIS, and the chip must not lie about it. "outcomes" is
     the college touchdown harness: graded purely against who scored,
     with no price anywhere in the replay. The old ternary would have
     dressed it in the green "real closes" chip — the exact
     market-relative claim it cannot make. */
  const outcomes = m.basis === "outcomes";
  const sk = m.skill;
  const hedged = sk && sk.hedged > 0.5;
  // A backtest ROI under ~100 bets is noise wearing a percentage — the
  // harnesses say so in their own summaries, so the page must not render
  // it as a result. Below the bar it goes grey and says why.
  /* On a MIXED basis the headline used to be the blended ROI, and that was
     the single most misleading number on the site.

     Measured on the real board: total_bases blended to +2.7% — and its own
     segment table underneath read 25,145 bets vs a naive baseline against
     277 vs real book lines. The blend is 99% naive by bet count, so the
     green +2.7% WAS the naive number, sitting over a subtitle that said
     "8,485 of 293,479 on real closes" and coloured as though it were an
     edge over a market. Strikeouts did the same: +4.6% blended, -0.3% on
     the 102 bets that met a real price.

     The book-priced segment is the only market-relative figure there is,
     so it leads. If it is too thin to mean anything it says so and stays
     grey, which is the honest reading of 277 bets — rather than borrowing
     confidence from 25,145 bets against a trailing average. */
  const bookSeg = (m.segments || {}).book;
  const mixed = m.basis === "mixed";
  const headline = mixed && bookSeg ? bookSeg : { roi: m.roi, n_bets: m.n_bets };
  const thin = (headline.n_bets || 0) < LAB_ROI_MIN_BETS;
  const roiSub = mixed
    ? (bookSeg
        ? `${bookSeg.n_bets.toLocaleString()} bets met a real close`
          + (thin ? ` — under ${LAB_ROI_MIN_BETS}, noise not a result`
                  : " — market-relative")
        : "no bet met a real close — nothing here is market-relative")
    : thin
      ? `only ${m.n_bets} bets — under ${LAB_ROI_MIN_BETS} this is noise, not a result`
      : m.basis === "book"
        ? "priced against real harvested closes — market-relative"
        : "vs a naive baseline line — NOT an edge over a book";
  /* v5: THE BOOK'S ROW, not a six-column table. Measured at 390 on a
     mixed-basis card the table ran 56px past the phone; the row says
     the same things — what it was priced against, bets, won, win rate,
     ROI, net — with the ROI where a reader looks for it. */
  const seg = Object.entries(m.segments || {}).map(([basis, g]) =>
    `<div class="hd-row lab-row">
      <span class="hd-what"><b>${basis === "book" ? "vs real book lines" : "vs naive baseline"}</b>
        <span>${g.n_bets.toLocaleString()} bets · ${g.wins.toLocaleString()} won${g.win_rate != null ? ` · ${(g.win_rate * 100).toFixed(1)}%` : ""}</span></span>
      <span class="hd-state"><b class="${toneOf(g.roi)}">${g.roi >= 0 ? "+" : ""}${(g.roi * 100).toFixed(1)}% ROI</b>
        <span class="hd-vs">${g.net >= 0 ? "+" : ""}${g.net.toFixed(2)}u</span></span>
    </div>`).join("");
  return `<div class="card lab-card">
    <div class="lab-head"><strong>${escapeHtml(m.label)}</strong>
      <span class="chip ${naive ? "warn" : outcomes ? "" : "good"}">${naive ? "naive lines" : outcomes ? "outcomes only" : m.basis === "mixed" ? "mixed basis" : "real closes"}</span>
      <span class="mini">${m.n.toLocaleString()} settled props</span></div>
    <div class="stats rec-kpis">
      ${labSkillTile(m)}
      ${recTile("Projection error", m.mae != null ? m.mae.toFixed(2) : "—",
                "mean absolute, in stat units")}
      ${recTile("Calibration", m.ece != null ? (m.ece * 100).toFixed(1) + "%" : "—",
                `Brier ${m.brier != null ? m.brier.toFixed(4) : "—"}`,
                { help: "Average gap between what it said and what happened." })}
      ${recTile(mixed ? "ROI vs real closes" : "Backtest ROI",
                headline.n_bets
                  ? `${headline.roi >= 0 ? "+" : ""}${(headline.roi * 100).toFixed(1)}%`
                  : "—",
                m.n_bets ? roiSub
                         : outcomes ? "never priced — nothing here is a bet"
                                    : "no bets cleared the gates",
                { tone: (naive || thin) ? "" : toneOf(headline.roi) })}
    </div>
    ${hedged ? `<div class="warning">${icon("warn")} ${(sk.hedged * 100).toFixed(0)}% of
      forecasts sit within 5 points of the base rate — that is hedging, not
      forecasting. A model that answers "about average" to everything scores
      well on calibration and finds no edges worth betting.</div>` : ""}
    ${naive && m.n_bets ? `<div class="warning">${icon("warn")} ${escapeHtml(note || "")}</div>` : ""}
    ${outcomes ? `<div class="ls-note">${escapeHtml(m.basis_note || "Graded against outcomes only — predictive skill, not an edge over a book.")}</div>` : ""}
    ${labBins(m)}
    ${seg ? `<div class="lab-rows"><div class="lab-rows-head">Priced against</div>${seg}</div>` : ""}
  </div>`;
}

/* A section the last run could not measure keeps the previous run's
   numbers, and says so: the date they were replayed and why tonight's
   run had nothing. A week-old number presented as tonight's would be
   the quiet version of the empty page this replaces. */
function labCarried(section) {
  if (!section || !section.carried_from) return "";
  return `<p class="mini" style="opacity:.75">Replayed ${escapeHtml(section.carried_from)} —
    kept from that run${section.carry_reason ? ` (this week: ${escapeHtml(section.carry_reason)})` : ""}</p>`;
}

/* THE USAGE RIPPLE AGAINST THE CLOSE (Ethan, 2026-09-14, Pacheco): when
   a same-position teammate sat, did the beneficiary beat the book's
   number by more than the book allowed? Per market: the absence rows,
   the residual over the close, and the verdict the pricing change waits
   on. A residual near zero means the close already carried the absence
   — and the card's note stays a note. */
function labRippleHTML(rp) {
  if (!rp) return "";
  const head = `<div class="section-title minor">Usage ripple against the close
      <span class="sub">— when a teammate at his position sat, did he beat the
      book’s number by more than the book allowed? The card’s note prices
      nothing until a market clears here.</span></div>`;
  if (!rp.markets) return `${head}<p class="mini" style="padding:4px 0">${escapeHtml(rp.unavailable || "not measured")}</p>`;
  /* v5: the book's row. The table ran 114px past a 390px phone and
     named its markets by their keys ("rush_yds"). Each market is a
     row now: its name, the counts and the judged bets under it, the
     reason as a sentence; the verdict chip, the residual over the
     close and its label on the right. */
  const rows = Object.keys(rp.markets).map((mk) => {
    const m = rp.markets[mk];
    const resid = m.resid_mean != null
      ? `${m.resid_mean >= 0 ? "+" : ""}${m.resid_mean.toFixed(1)}${m.resid_se != null ? ` ± ${m.resid_se.toFixed(1)}` : ""}` : "—";
    const bets = m.bets != null ? ` · ${m.bets} bets judged${m.roi != null ? ` at ${(m.roi >= 0 ? "+" : "")}${(m.roi * 100).toFixed(1)}%` : ""}` : "";
    const v = String(m.verdict || "");
    return `<div class="hd-row lab-row">
      <span class="hd-what"><b>${escapeHtml(marketWord(mk))}</b>
        <span>${m.n || 0} absence rows · ${m.n_measured || 0} measured${bets}</span>${
        m.reason ? `<span class="lab-reason">${escapeHtml(m.reason)}</span>` : ""}</span>
      <span class="hd-state"><span class="hd-chip${v === "clears" ? " good" : ""}">${escapeHtml(v || "—")}</span>
        <b>${resid}</b><span class="hd-vs">actual − close</span></span>
    </div>`;
  }).join("");
  return `${head}<div class="hd-card lab-rows">${rows}</div>
    ${rp.measured_at ? `<div class="mini" style="opacity:.7">Measured ${escapeHtml(String(rp.measured_at).slice(0, 10))}</div>` : ""}`;
}

/* v5: the book's row — the market by name, games priced and the
   projection error against the close under it; the ROI on the right
   with its bets and win rate. The table ran 14px past a phone. */
function labGameTable(games) {
  const rows = (games.markets || []).map((g) => `<div class="hd-row lab-row">
    <span class="hd-what"><b>${escapeHtml(marketWord(g.market))}</b>
      <span>${g.games_priced.toLocaleString()} games priced${g.mae != null ? ` · MAE ${g.mae.toFixed(2)} vs close` : ""}</span></span>
    <span class="hd-state"><b class="${toneOf(g.roi)}">${g.roi != null ? (g.roi >= 0 ? "+" : "") + (g.roi * 100).toFixed(1) + "% ROI" : "—"}</b>
      <span class="hd-vs">${g.n_bets} bets${g.win_rate != null ? ` · ${(g.win_rate * 100).toFixed(1)}%` : ""}</span></span>
  </div>`).join("");
  if (!rows) return `<p class="mini" style="padding:4px 0">${escapeHtml(games.unavailable || "")}</p>`;
  return `<div class="hd-card lab-rows">${rows}</div>`;
}

async function renderLab() {
  const host = document.getElementById("lab-body");
  if (!host) return;
  const got = await fetchJSON(() => paidFetch("backtest.json"), "backtest");
  const d = got.data;
  if (!d || !d.sports) {
    if (got.failed) { host.innerHTML = outageHTML("the Lab’s backtests", "backtest"); return; }
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <div class="es-title">No backtests published yet</div>
      <div class="es-sub">The Lab replays the production model over stored history
      once a week, automatically, as part of the nightly maintenance pass. It
      appears here after the first run.</div></div>`;
    return;
  }
  const order = ["mlb", "nfl", "cfb", "nba", "wnba", "nhl", "ufc"];
  const has = (sport) => {
    const s = d.sports[sport];
    return (s.props || {}).markets || ((s.game_lines || {}).markets);
  };
  const blocks = order.filter((s) => d.sports[s] && has(s)).map((sport) => {
    const s = d.sports[sport];
    const props = s.props || {}, games = s.game_lines || {};
    const cards = (props.markets || []).map((m) => labPropCard(m, d.basis_note)).join("");
    return `<div class="lab-sport">
      <div class="section-title">${sport.toUpperCase()}
        ${props.season ? `<span class="sub">— ${props.season} season</span>` : ""}</div>
      ${labCarried(props)}
      ${cards || `<p class="mini">Player props — ${escapeHtml(props.unavailable || "nothing replayed")}</p>`}
      <div class="mini" style="margin-top:10px;opacity:.75">Game lines (spread &amp; total),
        graded against real closing numbers</div>
      ${labCarried(games)}
      ${labGameTable(games)}
      ${labRippleHTML(s.ripple)}
    </div>`;
  }).join("");
  /* Sports with nothing replayed collapse into one honest table instead
     of six near-empty sections. A gap stated once is information; a gap
     restated six times over is what buries the page that has data. */
  const gaps = order.filter((s) => d.sports[s] && !has(s)).map((sport) => {
    const s = d.sports[sport];
    return `<tr><td>${sport.toUpperCase()}</td>
      <td>${escapeHtml((s.props || {}).unavailable || "—")}</td>
      <td>${escapeHtml((s.game_lines || {}).unavailable || "—")}</td></tr>`;
  }).join("");
  const gapBlock = gaps ? `<div class="section-title minor">Not replayed yet
      <span class="sub">— what each of these needs before it can appear above</span></div>
    <table class="agate"><thead><tr><th>Sport</th><th>Player props</th>
      <th>Game lines</th></tr></thead><tbody>${gaps}</tbody></table>` : "";
  host.innerHTML = `
    ${recDisclosure("What this page is, and what it isn’t", `The Book grades the picks
      we actually made, going forward. This page grades the <em>model</em>, by
      replaying it over history it never saw at the time — projections for each
      game are built only from games before it, then settled against what
      actually happened. That is the only evidence that accrues faster than a
      forward record, which is why it exists. It is also the easiest thing in
      betting to fool yourself with: ${escapeHtml(d.basis_note)}`)}
    ${blocks}
    ${gapBlock}
    <p class="mini" style="opacity:.6;margin-top:14px">Replayed automatically every
      ${d.every_days} days as part of the maintenance pass · last run
      ${escapeHtml(formatStamp(d.generated_at))}</p>`;
}

/* THE RECORD CARRIED IN FROM PIKKIT (engine/zeno.load_snapshot). Ethan,
   2026-09-26, sent Pikkit's all-time, 2026 and September cards: no free
   tracker both syncs and hands the bets out, and Juice Reel's API is
   still pending. Each window says its W-L, dollars, units and ROI, and
   carries Pikkit's own card beside it as the receipt — the numbers were
   read off it, and anyone can check them against it. */
function zenoDay(iso) {
  const t = Date.parse(String(iso || ""));
  return Number.isFinite(t) ? new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : String(iso || "");
}
function zenoSnapshotHTML(snap, unit) {
  const ws = (snap && snap.windows) || [];
  if (!ws.length) return "";
  unit = Number(unit) || 10;
  const src = escapeHtml(snap.source || "Pikkit");
  const card = (w) => {
    const pr = Number(w.profit || 0), u = Number(w.net_units || 0), roi = w.roi == null ? null : Number(w.roi) * 100;
    const tone = pr >= 0 ? "var(--good)" : "var(--bad)";
    return `<figure class="card zeno-win">
      <figcaption class="zeno-win-head"><b>${escapeHtml(w.label || "")}</b>
        <span class="mini">${Number(w.wins)}-${Number(w.losses)}${Number(w.pushes) ? `-${Number(w.pushes)}` : ""}</span></figcaption>
      <div class="zeno-win-nums"><b style="color:${tone}">${pr >= 0 ? "+" : ""}${zenoMoney(pr)}</b>
        <span style="color:${tone}">${u >= 0 ? "+" : MINUS}${Math.abs(u).toFixed(1)}u</span>
        <span style="color:${tone}">${roi == null ? "—" : `${roi >= 0 ? "+" : MINUS}${Math.abs(roi).toFixed(2)}%`} ROI</span></div>
      ${w.receipt ? `<a class="zeno-receipt" href="${safeHref(w.receipt)}" target="_blank" rel="noopener">
        <img src="${escapeAttr(w.receipt)}" alt="${src}’s ${escapeAttr(w.label || "")} card, the receipt for these numbers" loading="lazy"/></a>` : ""}
    </figure>`;
  };
  /* The headline windows (all time, the year) stand; the months, one card
     each, fold under them newest first — six Pikkit cards in a row is a
     wall on a phone. */
  const month = (w) => /^\d{4}-\d{2}$/.test(String(w.key || ""));
  const heads = ws.filter((w) => !month(w)), months = ws.filter(month)
    .sort((a, b) => String(b.key).localeCompare(String(a.key)));
  return `<div class="section-title"><span class="st-ico">${icon("check", 15)}</span>From ${src}
      <span class="sub">— synced from the sportsbooks and marked Verified by ${src}, as of ${escapeHtml(zenoDay(snap.as_of))}.
      Units at $${escapeHtml(String(unit))} each. Tap a card for the original.</span></div>
    <div class="zeno-snap">${heads.map(card).join("")}</div>
    ${months.length ? `<details class="tn-full zeno-months"><summary>Month by month · ${months.length}</summary>
      <div class="zeno-snap">${months.map(card).join("")}</div></details>` : ""}
    ${zenoCalendarHTML(months, snap)}`;
}

/* DAY BY DAY, off Pikkit's calendar cards (Ethan, 2026-09-26, sent June
   through September). The Record page's calendar grid (rc-*) in dollars:
   a cell per day with the day's profit, shaded by size, the month's exact
   total under it and Pikkit's own calendar as the receipt. Pikkit rounds
   each day to three figures, so the days can sum a few cents from the
   month — the foot says the total is Pikkit's. */
function zenoCalMoney(v) {
  const n = Number(v) || 0, m = Math.abs(n);
  return `${n > 0 ? "+" : n < 0 ? MINUS : ""}$${m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1).replace(/\.0$/, "") : m.toFixed(2).replace(/\.?0+$/, "")}`;
}
function zenoCalMonthHTML(w) {
  const [y, m] = String(w.key).split("-").map(Number);
  const first = new Date(y, m - 1, 1), n = new Date(y, m, 0).getDate();
  const days = w.days || {};
  const cells = [];
  for (let i = 0; i < first.getDay(); i++) cells.push(`<span class="rc-day blank"></span>`);
  for (let d = 1; d <= n; d++) {
    const date = `${w.key}-${String(d).padStart(2, "0")}`;
    if (!(date in days)) { cells.push(`<span class="rc-day off">${d}</span>`); continue; }
    const v = Number(days[date]) || 0, a = Math.abs(v);
    const depth = a < 25 ? 1 : a < 100 ? 2 : 3;
    cells.push(`<span class="rc-day ${toneOf(v) || "flat"} rc-${depth}" title="${date}: ${zenoCalMoney(v)}">${d}<b>${zenoCalMoney(v)}</b></span>`);
  }
  const pr = Number(w.profit) || 0;
  return `<div class="rc-month zeno-cal-month">
    <div class="rc-grid">${["S", "M", "T", "W", "T", "F", "S"].map((h) => `<span class="rc-h">${h}</span>`).join("")}${cells.join("")}</div>
    <p class="rc-foot"><b>${escapeHtml(w.label || "")}</b> · ${Object.keys(days).length} days bet
      · <b>${Number(w.wins)}-${Number(w.losses)}${Number(w.pushes) ? `-${Number(w.pushes)}` : ""}</b>
      · <b class="${toneOf(pr)}">${pr >= 0 ? "+" : MINUS}${zenoMoney(Math.abs(pr))}</b> (Pikkit’s total)
      ${w.calendar_receipt ? ` · <a href="${safeHref(w.calendar_receipt)}" target="_blank" rel="noopener">Pikkit’s calendar</a>` : ""}</p></div>`;
}
/* The Record page's profit calendar, his way round (Ethan, 2026-09-26:
   "make the calendars our way and not the screenshots. you have each day
   so u can do that"): one month in view, drawn from the days, arrows only
   where there is a month to go to; Pikkit's calendar is a link under it. */
function zenoCalendarHTML(months, snap) {
  const ms = (months || []).filter((w) => w.days && Object.keys(w.days).length)
    .sort((a, b) => String(a.key).localeCompare(String(b.key)));
  if (!ms.length) return "";
  const keys = ms.map((w) => w.key);
  const ym = keys.includes(_zenoCalMonth) ? _zenoCalMonth : keys[keys.length - 1];
  const i = keys.indexOf(ym);
  const arrow = (to, glyph, label) => to == null ? "" :
    `<button class="ra-range" data-act="zenoCalSetMonth" data-arg="${to}" aria-label="${label}">${glyph}</button>`;
  const nav = keys.length > 1 ? `<span class="ra-ranges">${
    arrow(i > 0 ? keys[i - 1] : null, "‹", "Earlier month")}${
    arrow(i < keys.length - 1 ? keys[i + 1] : null, "›", "Later month")}</span>` : "";
  return `<div class="zeno-cal">
    <div class="section-title"><span class="st-ico">${icon("calendar", 15)}</span>Profit calendar
      <span class="sub">— his dollars by day</span>${nav}</div>
    <div class="card rc-card zeno-cal-card">${zenoCalMonthHTML(ms[i])}</div>
    ${snap && snap.days_note ? `<p class="list-note">${escapeHtml(snap.days_note)}</p>` : ""}</div>`;
}

/* ZENO POSTS HIS OWN BETS (Ethan, 2026-09-26: subscribers get "ALL of my
   Zeno's props and parlays", and until Juice Reel's API is approved,
   posting them the moment he places them is how they arrive). Only with
   his owner token — the same QB_OWNER_TOKEN door as the import; there is
   no account that can post here. A posted bet is a ticket like any other:
   open until he grades it from this page (or the synced copy from Juice
   Reel arrives and takes its place — engine/zeno._posted_twin). */
const ZENO_POST_BOOKS = [["fanduel", "FanDuel"], ["draftkings", "DraftKings"], ["thescore", "theScore Bet"]];
const ZENO_POST_SPORTS = ["nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc", "other"];
async function zenoPost(rows) {
  const r = await fetch("/api/zeno/import", {
    method: "POST",
    headers: { "X-Owner-Token": zenoOwnerToken(), "X-Zeno-Source": "post", "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  let j = {};
  try { j = await r.json(); } catch (e) { j = {}; }
  if (!r.ok) throw new Error(j.error || `the site answered ${r.status}`);
  return j;
}
/* The same ticket again with its result: the store matches it on its key
   (the post's own id) and updates it — never a second row. */
function zenoGradePayload(r, result) {
  const ext = String(r.key || "").split(":").slice(1).join(":");
  const p = { book: r.book, placed_at: r.placed_at, event_at: r.event_at, sport: r.sport, event: r.event,
              market: r.market, selection: r.selection, line: r.line, odds: r.odds, stake: r.stake,
              legs: r.legs, result };
  if (ext && !ext.startsWith("h:")) p.external_id = ext;
  return p;
}
function zenoGradeHTML(r) {
  return `<div class="zeno-grade" data-key="${escapeAttr(r.key || "")}">
    <span class="mini">Grade it:</span>${[["won", "Won"], ["lost", "Lost"], ["push", "Push"], ["void", "Void"]]
      .map(([k, w]) => `<button type="button" class="btn ghost zeno-grade-btn" data-result="${k}">${w}</button>`).join("")}</div>`;
}
function zenoOwnerHTML(tix) {
  if (!tix.owner) {
    return `<details class="zeno-owner-in"><summary class="mini">Zeno? Sign in to post a bet</summary>
      <form class="mb-form zeno-owner-token" autocomplete="off">
        <div class="mb-form-row"><label class="mb-grow">Owner token
          <input type="password" name="token" required autocomplete="off"/></label>
          <button class="btn primary" type="submit">Sign in</button></div>
        <p class="list-note zeno-owner-msg"></p></form></details>`;
  }
  return `<div class="section-title"><span class="st-ico">${icon("ticket", 15)}</span>Post a bet
      <span class="sub">— goes to members the moment you post it; grade it from “Riding now” when it settles</span></div>
    <form class="card mb-form zeno-post" autocomplete="off">
      <div class="mb-form-row">
        <label>Type<select name="kind"><option value="straight">Straight / prop</option><option value="parlay">Parlay</option></select></label>
        <label>Book<select name="book">${ZENO_POST_BOOKS.map(([k, w]) => `<option value="${k}">${w}</option>`).join("")}</select></label>
        <label>Sport<select name="sport">${ZENO_POST_SPORTS.map((k) => `<option value="${k}">${k.toUpperCase()}</option>`).join("")}</select></label>
      </div>
      <div class="mb-form-row"><label class="mb-grow zeno-post-pick">The pick
        <input name="selection" placeholder="Josh Allen Over 1.5 Pass TD"/></label></div>
      <div class="mb-form-row zeno-post-legs" hidden><label class="mb-grow">The legs, one per line
        <textarea name="legs" rows="4" placeholder="Bills ML&#10;Chiefs ML&#10;Allen Over 250.5 Pass Yds"></textarea></label></div>
      <div class="mb-form-row">
        <label class="mb-grow">Game (optional)<input name="event" placeholder="BUF @ MIA"/></label>
        <label>Odds<input name="odds" inputmode="numeric" placeholder="-110" required/></label>
        <label>Stake ($)<input name="stake" inputmode="decimal" placeholder="20" required/></label>
      </div>
      <div class="mb-form-row"><button class="btn primary" type="submit">Post it</button>
        <button class="btn ghost zeno-owner-out" type="button">Sign out</button></div>
      <p class="list-note zeno-post-msg"></p>
    </form>${researchBoxHTML()}`;
}
/* RESEARCH PICKS, WRITTEN DOWN BEFORE KICKOFF (Ethan, 2026-10-04: "do all
   of it"). One pick a line; engine.scancard grades them against the box
   scores, our chance and the price once the week settles. Owner only. */
function researchBoxHTML() {
  return `<div class="section-title"><span class="st-ico">${icon("chart", 15)}</span>Research picks
      <span class="sub">— paste a report’s picks before kickoff; graded after the games</span></div>
    <form class="card mb-form zeno-research" autocomplete="off">
      <div class="mb-form-row"><label>Season<input name="season" inputmode="numeric" value="${new Date().getFullYear()}" required/></label>
        <label>Week<input name="week" inputmode="numeric" placeholder="5" required/></label></div>
      <div class="mb-form-row"><label class="mb-grow">One pick a line: Source | Player | TEAM | market | over/under | line | chance | price
        <textarea name="text" rows="5" placeholder="TD scan | Chase Brown | CIN | anytime td | over | 0.5 | 60-62% | -145"></textarea></label></div>
      <div class="mb-form-row"><button class="btn primary" type="submit">Save picks</button></div>
      <p class="list-note zeno-research-msg"></p></form>`;
}
function bindResearchBox(host) {
  const form = host.querySelector(".zeno-research");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(form), msg = form.querySelector(".zeno-research-msg");
    msg.textContent = "Saving…";
    try {
      const r = await fetch("/api/research", { method: "POST",
        headers: { "X-Owner-Token": zenoOwnerToken(), "Content-Type": "application/json" },
        body: JSON.stringify({ season: Number(f.get("season")), week: Number(f.get("week")), text: f.get("text") }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `the site answered ${r.status}`);
      const bad = (j.errors || []).map((x) => `line ${x.line}: ${x.error}`).join("; ");
      msg.textContent = `Saved ${j.added} (${j.week_total} this week)${j.kept_first ? `, ${j.kept_first} already saved` : ""}${bad ? ` — skipped ${bad}` : ""}`;
      if (j.added) form.querySelector('[name="text"]').value = "";
    } catch (err) { msg.textContent = `Not saved: ${err.message}`; }
  });
}
function bindZenoOwner(host, tix) {
  bindResearchBox(host);
  const tokForm = host.querySelector(".zeno-owner-token");
  if (tokForm) tokForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const tok = String(new FormData(tokForm).get("token") || "").trim();
    const msg = tokForm.querySelector(".zeno-owner-msg");
    try { localStorage.setItem("qb.zenoOwner", tok); } catch (err) { /* private window */ }
    const t = await zenoTickets(true);
    if (!t.owner) {
      try { localStorage.removeItem("qb.zenoOwner"); } catch (err) { /* private window */ }
      if (msg) msg.textContent = "That token was not accepted.";
      await zenoTickets(true);
      return;
    }
    renderZeno();
  });
  const form = host.querySelector(".zeno-post");
  if (form) {
    const kind = form.querySelector('[name="kind"]');
    const legsRow = form.querySelector(".zeno-post-legs"), pickRow = form.querySelector(".zeno-post-pick");
    kind.addEventListener("change", () => {
      legsRow.hidden = kind.value !== "parlay";
      pickRow.hidden = kind.value === "parlay";
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = new FormData(form), msg = form.querySelector(".zeno-post-msg");
      const legs = String(f.get("legs") || "").split("\n").map((x) => x.trim()).filter(Boolean);
      const parlay = f.get("kind") === "parlay";
      const selection = parlay ? `${legs.length}-leg parlay: ${legs.join(" / ")}`.slice(0, 200)
        : String(f.get("selection") || "").trim();
      if (!selection || (parlay && legs.length < 2)) {
        msg.textContent = parlay ? "A parlay needs at least two legs, one per line." : "Type the pick.";
        return;
      }
      const row = { book: f.get("book"), sport: f.get("sport"), event: String(f.get("event") || "").trim() || null,
                    market: parlay ? "parlay" : "prop", selection, legs: parlay ? legs : null,
                    odds: String(f.get("odds") || "").trim(), stake: String(f.get("stake") || "").trim(),
                    placed_at: new Date().toISOString().slice(0, 19), result: "open",
                    external_id: `post-${Date.now()}` };
      msg.textContent = "Posting…";
      try {
        const got = await zenoPost([row]);
        if (!got.added) { msg.textContent = "Not posted — check the odds and the stake."; return; }
        await zenoTickets(true);
        renderZeno();
      } catch (err) { msg.textContent = `Not posted: ${err.message}`; }
    });
    const out = form.querySelector(".zeno-owner-out");
    if (out) out.addEventListener("click", async () => {
      try { localStorage.removeItem("qb.zenoOwner"); } catch (err) { /* private window */ }
      await zenoTickets(true);
      renderZeno();
    });
  }
  const byKey = new Map((tix.open || []).map((r) => [r.key, r]));
  host.querySelectorAll(".zeno-grade").forEach((bar) => bar.querySelectorAll(".zeno-grade-btn").forEach((b) =>
    b.addEventListener("click", async () => {
      const r = byKey.get(bar.dataset.key);
      if (!r) return;
      bar.querySelectorAll("button").forEach((x) => { x.disabled = true; });
      try {
        await zenoPost([zenoGradePayload(r, b.dataset.result)]);
        await zenoTickets(true);
        renderZeno();
      } catch (err) {
        bar.insertAdjacentHTML("beforeend", `<span class="mini">Not saved: ${escapeHtml(err.message)}</span>`);
        bar.querySelectorAll("button").forEach((x) => { x.disabled = false; });
      }
    })));
}

async function renderZeno() {
  const host = document.getElementById("zeno-body");
  if (!host) return;
  const d = await loadRecordOnce();
  const z = (d || {}).zeno;
  if (z && z.error) {
    host.innerHTML = `<div class="card"><p class="list-note">${icon("warn")} Zeno’s record could
      not be read at the last build (${escapeHtml(String(z.error))}). The tickets are safe.</p></div>`;
    return;
  }
  if (!z || !z.overall) {
    host.innerHTML = `<div class="card"><p class="list-note">Nothing here yet — the first
      import will fill this page.</p></div>`;
    return;
  }
  const tix = await zenoTickets();
  const locked = !!tix.locked;
  const open = locked ? [] : (tix.open || []);
  const settled = locked ? [] : (tix.recent || []);
  /* v5: the page opens with his ribbon — the deck's and the Record page's
     own tile (recordRibbonsHTML) — then what is riding and what settled
     as the book's rows, ten settled in view and the rest one tap away. */
  const ribbon = recordRibbonsHTML({ zeno: z }, {}, []);
  const FOLD = 10;
  host.innerHTML = `
    ${ribbon ? `<div class="hd-stats rec-ribbons">${ribbon}</div>`
             : `<div class="card"><p class="list-note">No tickets yet.</p></div>`}
    <div class="card pk-card">${pikkitBadgeHTML("Every Zeno pick is verified on Pikkit")}
      <p class="list-note">Every bet Zeno places is tracked on Pikkit, synced straight from his
        sportsbooks — the record, the charts and each pick. Check it yourself before you tail
        anything.</p></div>
    ${zenoSnapshotHTML(z.snapshot, z.unit_dollars)}
    <p class="list-note">${z.snapshot
      ? `The record up to ${escapeHtml(zenoDay(z.snapshot.as_of))} is ${escapeHtml(z.snapshot.source || "Pikkit")}’s,
         read off the cards above; bets that settle after that are added on top as they come in.`
      : `The record, in dollars, as the books settled it.`} Full receipts on the
      <a href="#record" data-view="record">Record</a> page.</p>
    <div class="section-title"><span class="st-ico">${icon("target", 15)}</span>Riding now
      <span class="sub">— ${locked ? "members only" : open.length ? `${plural(open.length, "open ticket")}, ${zenoMoney(open.reduce((a, r) => a + (Number(r.stake) || 0), 0))} at risk` : "nothing open right now"}</span></div>
    ${locked ? zenoLockedHTML(z)
      : open.length ? `<div class="hd-card">${open.map((r) => zenoTicketRow(r, false)
          + (tix.owner ? zenoGradeHTML(r) : "")).join("")}</div>`
      : `<div class="card"><p class="list-note">Nothing riding. Check back before the next slate.</p></div>`}
    ${settled.length ? `
    <div class="section-title"><span class="st-ico">${icon("check", 15)}</span>Last settled
      <span class="sub">— newest first</span></div>
    <div class="hd-card">${settled.slice(0, FOLD).map((r) => zenoTicketRow(r, true)).join("")}</div>
    ${settled.length > FOLD ? `<details class="tn-full"><summary>${plural(settled.length - FOLD, "more settled ticket")}</summary>
      <div class="hd-card">${settled.slice(FOLD).map((r) => zenoTicketRow(r, true)).join("")}</div></details>` : ""}` : ""}
    ${locked ? "" : `<p class="list-note">
      "Copy" puts the selection, price and book on your clipboard to paste into your own app.
      Prices move; what you get may not be what Zeno got.${z.last_import ? ` Last synced ${escapeHtml(String(z.last_import).replace("T", " ").slice(0, 16))} UTC.` : ""}</p>`}
    ${zenoOwnerHTML(tix)}`;
  sweepRings(host);
  bindZenoOwner(host, tix);
  host.querySelectorAll(".zeno-copy").forEach((b) => b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(b.dataset.text || ""); b.textContent = "Copied"; }
    catch (e) { b.textContent = "Copy failed"; }
    setTimeout(() => { b.textContent = "Copy"; }, 1500);
  }));
}

function pmSpark(series, w = 96, h = 30) {
  // 30-day cumulative P&L curve. Zero line dashed; color by where the
  // month ended.
  if (!series || series.length < 2) return "";
  const pad = 2;
  const vals = series.map((p) => p[1]);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const x = (i) => pad + (i / (series.length - 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" L");
  const last = vals[vals.length - 1];
  const color = last >= 0 ? "var(--good)" : "var(--bad)";
  const fmt = (v) => `${v < 0 ? "−" : "+"}$${Math.abs(Math.round(v)).toLocaleString()}`;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="display:block"
      data-tip="past month: ${fmt(vals[0])} → ${fmt(last)} (low ${fmt(Math.min(...vals))}, high ${fmt(Math.max(...vals))})">
    <line x1="${pad}" y1="${y(0).toFixed(1)}" x2="${w - pad}" y2="${y(0).toFixed(1)}"
      stroke="currentColor" stroke-width="0.7" stroke-dasharray="3 3" opacity="0.25"/>
    <path d="M${pts}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(series.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="2" fill="${color}"/>
  </svg>`;
}

function pmAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/* The desk row's wrapper. The ART is pmThumb's — this was a second copy
   of the same ladder until the board grew one too, and two copies of a
   picture-choosing rule drift the moment one venue gains a field. What
   differs here is only the caption: the desk labels by sport or city,
   the board labels by venue. */
function deskThumb(r) {
  const label = escapeHtml((r.sport || r.city || "").toUpperCase());
  return `<span class="kx-thumb">${pmThumb(r, 19)}
    <span class="kx-thumb-l">${label}</span></span>`;
}

/* THE SAME THUMBNAIL EVERYWHERE A MARKET IS LISTED.
   Ethan, 2026-08-19: "We should be following the thumbnails they use on
   Polly and Kalshi and everything." The desk's rows already drew team
   logos; the board below drew a bare venue letter for all forty, so the
   two halves of the same page identified markets in two different ways.

   The ladder, best available first:
     1. a matched game  -> both teams' logos, the pair reading as a fixture
     2. Polymarket art  -> the venue's own market icon, its URL untouched
     3. a weather row   -> the sun mark
     4. anything else   -> the venue badge it always had

   Rung 2 is a remote image and the only one that can fail in flight, so
   it carries an onerror that swaps in the venue badge rather than leaving
   a broken-image glyph in a row of clean ones. */
function pmThumb(r, size = 19) {
  const sport = String(r.sport || "").toLowerCase();
  const mu = String(r.matchup || "");
  const pair = mu.includes("@") ? mu.split("@")
    : mu.includes(" vs ") ? mu.split(" vs ") : null;
  if (pair && sport) {
    const map = teamsForSport(sport);
    const [away, home] = pair.map((x) => x.trim());
    return `<span class="kx-thumb-pair">${teamMark(away, size, map, sport)}
      ${teamMark(home, size, map, sport)}</span>`;
  }
  if (r.image) {
    return `<img class="kx-thumb-img" src="${escapeAttr(r.image)}" alt=""
      loading="lazy" width="${size + 5}" height="${size + 5}"
      data-onerr="fragment"
      data-fb="${escapeAttr(venueMark(r.venue, size + 2))}">`;
  }
  if (r.city || r.forecast_f != null) {
    return `<span class="kx-thumb-ic wx">${icon("sun", size - 2)}</span>`;
  }
  return venueMark(r.venue, size + 2);
}

function deskSectionHTML(k) {
  if (!k) return "";
  const sports = (k.rows || []).filter((r) => r.rec);
  const wx = (k.weather || []).filter((r) => r.rec);
  const paper = ((k.desk || {}).paper) || {};
  // A row with no recorded side renders nothing — a chip that can read
  // "undefined" is the widget printing its own missing field.
  const side = (s) => s
    ? `<span class="chip ${s === "YES" ? "up" : "down"}">${escapeHtml(s)}</span>` : "";
  // THE RECOMMENDATION IS THE THING YOU CLICK. Ethan, 2026-08-19: "add
  // where we can click on the trade it's recommending and it will pull up
  // a chart of the live odds". These rows ARE the recommendations, and
  // they were the one row shape on this page with no way in — the board
  // below has a View button, the desk had nothing.
  //
  // Weather rows carry no ticker and never reach the board table, so they
  // stay inert rather than opening a panel that has nothing to show.
  const row = (r, why) => `<div class="kx-row${r.ticker ? " openable" : ""}"${
      r.ticker ? ` role="button" tabindex="0"
      data-act="pmRow" data-key="pmRow" data-arg="k:${escapeAttr(r.ticker)}"` : ""}>
      ${deskThumb(r)}
      <span class="kx-title">${escapeHtml(r.title)} ${side(r.rec_side)}
        <span class="kx-match">· ${why}</span></span>
      <span class="kx-num kx-k" data-tick="d:${escapeAttr(
        r.ticker || r.title || "")}" data-tick-v="${(r.prob * 100).toFixed(0)}">${
        (r.prob * 100).toFixed(0)}¢</span>
      <span class="kx-num kx-m">${(r.model_p * 100).toFixed(0)}%</span>
      <span class="kx-num kx-e"><span style="color:var(--${r.edge_pts > 0 ? "good" : "bad"});font-weight:700">${r.edge_pts > 0 ? "+" : ""}${r.edge_pts} pts</span></span>
      <span class="kx-vol">$${Number(r.volume_24h || 0).toLocaleString()}</span>
    </div>`;
  const rows = [
    ...sports.map((r) => row(r, `our model ${(r.model_p * 100).toFixed(0)}% vs the exchange&rsquo;s ${(r.prob * 100).toFixed(0)}¢`)),
    ...wx.map((r) => row(r, `NWS high ${r.forecast_f}&deg; &plusmn;${r.sigma_f}&deg; for ${escapeHtml(r.city)} ${escapeHtml(r.date)}`)),
  ].join("");
  const graded = paper.settled || 0;
  const paperLine = graded
    ? `${paper.wins || 0}&ndash;${paper.losses || 0} graded · ${fmtRoi(paper.roi)} ROI on flat paper stakes`
    : "nothing graded yet — daily weather markets settle same-day, so this record fills fast";
  return `
    <div class="section-title">The desk’s recommendations
      <span class="sub">— all on Kalshi, because a recommendation needs a price we can
      model against and Polymarket rows carry no model number.
      Every row clears a written gate (edge &ge; 6 pts sports / 8 pts weather,
      a real two-sided book, live volume) and is journaled at a flat 0.1u PAPER stake.
      ${paperLine}. Promotion to real stakes takes 100+ graded rows in profit — the same
      bar every other bucket on this site has to clear.</span></div>
    ${rows ? `<div class="card kx-table" style="padding:0">${rows}</div>`
           : `${panelEmpty("No market clears the gate right now. The desk needs: the Kalshi feed reachable at build time, a game our model prices (or a city the forecast covers), and a disagreement bigger than the bar. Each build prints which of those was missing — nothing here is ever forced.")}`}`;
}

/* ONE board out of two venues.
   ------------------------------------------------------------------
   Ethan, 2026-08-12: "Combine the kalshi and polly market board. There
   is too much too scroll through and they are basically the same
   thing." They are: both are event contracts priced in cents, and
   reading them as two tables meant scrolling past one to compare with
   the other. So the row shape is normalized here and the venue becomes
   a COLUMN rather than a section heading.

   What does NOT get flattened is where the two feeds genuinely differ.
   Kalshi gives a two-sided book we can price against, so those rows
   carry a model number and an edge. Polymarket gives a public trade
   tape with wallet identity, which is flow — a different question, and
   it keeps its own tab. Where a venue has no answer the cell is a dash;
   inventing a model number for a Polymarket row to fill the column
   would be the kind of fake symmetry this merge is supposed to kill. */
function pmVenueRows(kx, d) {
  const rows = [];
  for (const r of ((kx || {}).rows || [])) {
    rows.push({
      venue: "KALSHI", title: r.title,
      sub: [(r.sport || "").toUpperCase(), r.matchup].filter(Boolean).join(" · "),
      price: r.prob, model: r.model_p, edge: r.edge_pts,
      vol: r.volume_24h, basis: r.price_basis, url: "",
      key: `k:${r.ticker || r.title}`, sport: (r.sport || "").toUpperCase(),
      rec: !!r.rec, rec_side: r.rec_side || "", matchup: r.matchup || "",
      spread_cents: r.spread_cents, ends: "",
      // OUR recorded price history, carried through to the detail panel.
      // Dropping it here is why the first cut drew no chart: the board
      // row is a projection of the payload row, and anything the
      // projection forgets does not exist downstream.
      tape: r.tape || null, yes_side: r.yes_side || "",
    });
  }
  for (const m of ((d || {}).markets || [])) {
    rows.push({
      venue: "POLY", title: m.question,
      sub: m.end_date ? `resolves ${m.end_date}` : "",
      price: m.yes, model: null, edge: null,
      vol: m.vol24, basis: "",
      // Gated at the SOURCE rather than at each render, so a consumer
      // added later cannot resurrect the outbound link by accident.
      url: (EXTERNAL_MARKET_LINKS && m.slug)
        ? `https://polymarket.com/market/${m.slug}` : "",
      key: `p:${m.slug || m.question}`, sport: "", rec: false, rec_side: "",
      matchup: "", spread_cents: null, ends: m.end_date || "",
      tape: m.tape || null, yes_side: "", image: m.image || "",
    });
  }
  // Volume is the one measure both venues report the same way, so it is
  // the only honest way to rank a mixed table.
  rows.sort((a, b) => (Number(b.vol) || 0) - (Number(a.vol) || 0));
  return rows;
}

/* The desk's own gate, mirrored from engine/sources/kalshi.py so the
   checklist prints the real bars, not vibes. */
const PM_GATE = { edge: 6.0, vol: 250.0, spread: 6.0 };

function pmTapeWindow(pts) {
  const hrs = (pts[pts.length - 1][0] - pts[0][0]) / 3600;
  if (hrs >= 1.5) return `${Math.round(hrs)} hours`;
  const mins = Math.round(hrs * 60);
  return `${mins} minutes`;
}

function pmTapeHTML(r) {
  const pts = (r.tape || []).filter((p) => Array.isArray(p) && p.length > 1);
  if (pts.length < 2) {
    return `<p class="pm-tape-none">No price history yet — we have not
      watched this market long enough to draw one. It fills in as the
      refreshes accumulate.</p>`;
  }
  const yesName = r.yes_label || (r.yes_side === "away" ? (r.away || "Yes")
    : r.yes_side === "home" ? (r.home || "Yes") : "Yes");
  const noName = r.no_label || (r.yes_side === "away" ? (r.home || "No")
    : r.yes_side === "home" ? (r.away || "No") : "No");
  // THE LINE ENDS WHERE THE PANEL SAYS IT IS. A snapshot bucket can be
  // ten minutes old, so the tape's last point and the price printed in
  // 48px above it can differ — and a chart labelled "Yes 55%" under a
  // header reading 83¢ makes the panel argue with itself. The live price
  // IS an observation, taken at build time, so it joins the series as its
  // newest point rather than being drawn as a separate claim.
  // Placed at NOW, not one second after the last bucket. A live price
  // pinned a second past a bucket draws as a vertical spike at the right
  // edge — the shape of an instant crash rather than of ten minutes
  // passing. Where it actually belongs is the clock.
  const nowS = Math.floor(Date.now() / 1000);
  const plotted = (r.price == null || nowS <= pts[pts.length - 1][0])
    ? pts.slice() : pts.concat([[nowS, r.price]]);
  const cfg = { points: plotted, yes_label: yesName, no_label: noName };
  // No separate legend. Both venues label the lines at the right-hand end
  // and so does the chart — a legend above it would be the same two
  // numbers twice, and the SVG fallback carries the colours in the same
  // order.
  return `<div class="pm-tape">
    <div class="pm-tape-head">
      <span class="pm-tape-t">Price history</span>
      <span class="pm-tape-win">last ${pmTapeWindow(pts)}</span>
    </div>
    <div class="pm-tape-plot" data-echart-tape="${escapeAttr(JSON.stringify(cfg))}">
      ${pmTapeSVG(plotted, 300, 96)}
    </div>
    <p class="pm-tape-cap">${pts.length} price${pts.length === 1 ? "" : "s"}
      we recorded, ending at the ${escapeHtml(yesName)} price above. This is
      our own tape — it starts when we started watching, not when the
      market opened.</p>
  </div>`;
}

function pmDetailHTML(r) {
  if (!r) return `<div class="pm-d-empty">${icon("signal", 26)}
    <p>Tap <b>View</b> on any market to open its full read here.</p></div>`;
  const yes = r.price == null ? null : Math.round(r.price * 100);
  const no = yes == null ? null : 100 - yes;
  const modeled = r.model != null;
  const check = (ok, text) => `<li class="${ok ? "ok" : "no"}">${
    icon(ok ? "check" : "cross", 12)} ${text}</li>`;
  const gates = r.venue !== "KALSHI" ? "" : `
    <div class="pm-d-card"><div class="gp-panel-title">The desk’s gate
        <span class="gp-panel-sub">— the real bars, pass or fail</span></div>
      <ul class="pm-d-checks">
        ${check(modeled && Math.abs(r.edge || 0) >= PM_GATE.edge,
          modeled ? `Edge ${r.edge > 0 ? "+" : ""}${r.edge} pts against the ${PM_GATE.edge}-pt bar`
                  : "No model number — we do not price this claim")}
        ${check(r.basis === "book" || r.basis === "mid",
          r.basis === "book" || r.basis === "mid"
            ? "Two-sided book — the mid is a real probability"
            : "One-sided book — price is the last trade, not a mid")}
        ${check(Number(r.vol) >= PM_GATE.vol,
          `24h volume $${Number(r.vol || 0).toLocaleString()} against the $${PM_GATE.vol} floor`)}
        ${r.spread_cents == null ? "" : check(r.spread_cents <= PM_GATE.spread,
          `Spread ${r.spread_cents}¢ against the ${PM_GATE.spread}¢ cap`)}
      </ul>
      ${r.rec ? `<p class="pm-d-verdict good">${icon("check", 12)} Clears every
        gate — journaled as a paper recommendation (${escapeHtml(r.rec_side)}).</p>`
      : `<p class="pm-d-verdict">Does not clear the gate — shown as a price,
        not a pick.</p>`}
    </div>`;
  const summary = `
    <div class="pm-d-card"><div class="gp-panel-title">Market summary</div>
      <div class="pm-d-rows">
        <div><span>Venue</span><b>${r.venue === "POLY" ? "Polymarket" : "Kalshi"}</b></div>
        <div><span>Type</span><b>Binary</b></div>
        ${r.ends ? `<div><span>Resolves</span><b>${escapeHtml(r.ends)}</b></div>` : ""}
        ${r.matchup ? `<div><span>Matched game</span><b>${escapeHtml(r.matchup)}</b></div>` : ""}
        <div><span>24h volume</span><b>$${Number(r.vol || 0).toLocaleString()}</b></div>
        ${r.basis ? `<div><span>Price basis</span><b>${escapeHtml(r.basis)}</b></div>` : ""}
      </div></div>`;
  return `
    <div class="pm-d-head">
      <span class="pm-d-venue">${pmThumb(r, 26)}
        <span>${escapeHtml(String(r.venue || ""))}</span></span>
      <h3 class="pm-d-title">${r.url
        ? `<a href="${safeHref(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>`
        : escapeHtml(r.title)}</h3>
      ${r.sub ? `<div class="pm-d-sub">${escapeHtml(r.sub)}</div>` : ""}
    </div>
    <div class="pm-d-prices">
      <div class="pm-d-price yes"><b>${yes == null ? "—" : yes + "¢"}</b><span>Yes</span></div>
      <div class="pm-d-price no"><b>${no == null ? "—" : no + "¢"}</b><span>No</span></div>
      ${modeled ? `<div class="pm-d-edge" style="color:var(--${(r.edge || 0) >= 0 ? "good" : "bad"})">
        ${r.edge == null ? "—" : `${r.edge >= 0 ? "+" : ""}${r.edge} pts`}<span>Qellys edge</span></div>` : ""}
    </div>
    ${pmTapeHTML(r)}
    ${modeled ? `<p class="pm-d-model">Our model prices the same claim at
      <b>${Math.round(r.model * 100)}%</b>.</p>` : ""}
    ${summary}
    ${gates}
    ${r.url ? `<a class="btn pm-d-out" href="${safeHref(r.url)}" target="_blank"
      rel="noopener">View on Polymarket ↗</a>` : ""}
    <p class="pm-d-note">Prices are the venues’ own. This panel is a read,
      not an order ticket — Qellys takes no wagers.</p>`;
}

const PM_BOARD_SHOWN = 40;

function pmBoardRowHTML(r) {
  const edge = r.edge == null ? `<span style="opacity:.45">—</span>`
    : `<span style="color:var(--${r.edge > 0 ? "good" : "bad"});font-weight:700">
         ${r.edge > 0 ? "+" : ""}${r.edge} pts</span>`;
  const basis = r.basis === "last_trade"
    ? ` <span class="chip" title="One side of the book is empty — this is the last trade, not a two-sided mid">last trade</span>` : "";
  const title = r.url
    ? `<a href="${safeHref(r.url)}" target="_blank" rel="noopener"
          style="color:inherit">${escapeHtml(r.title)}</a>`
    : escapeHtml(r.title);
  // The row's numbers, drawn as lengths — see the meter comment history.
  const pct = r.price == null ? null
    : Math.max(0, Math.min(100, r.price * 100));
  const mdl = r.model == null ? null
    : Math.max(0, Math.min(100, r.model * 100));
  const meter = pct == null ? "" : `<span class="kx-meter" aria-hidden="true">
      <span class="kx-meter-fill" style="width:${pct.toFixed(1)}%"></span>
      ${mdl == null ? "" : `<span class="kx-meter-model ${
        r.edge > 0 ? "up" : r.edge < 0 ? "down" : ""
      }" style="left:${mdl.toFixed(1)}%"></span>`}
    </span>`;
  const no = r.price == null ? null : Math.round((1 - r.price) * 100);
  // THE WHOLE ROW IS THE DOOR. Ethan, 2026-08-19: "add where we can click
  // on the trade it's recommending and it will pull up a chart" — a
  // 44px-wide View button at the far right is not that, especially on a
  // phone. The button stays because it names the action for anyone who
  // needs a target with a label, and the row carries the same call.
  //
  // The title's link-out (Polymarket rows) sits inside, so the handler
  // ignores clicks that landed on an anchor or on the button itself —
  // otherwise opening the venue in a new tab would also swap the panel
  // underneath.
  return `<div class="kx-row openable${_pmSelKey === r.key ? " sel" : ""}"
    role="button" tabindex="0"
    data-act="pmRow" data-key="pmRow" data-arg="${escapeAttr(r.key)}">
    <span class="kx-thumb">${pmThumb(r, 19)}
      <span class="kx-thumb-l">${escapeHtml(String(r.venue || ""))}</span></span>
    <span class="kx-title" title="${escapeAttr(r.title)}">${title}
      ${r.sub ? `<span class="kx-match">· ${escapeHtml(r.sub)}</span>` : ""}${basis}</span>
    <span class="kx-num kx-k" title="The venue’s own price for YES" style="color:var(--good)"${
      r.price == null ? "" : ` data-tick="y:${escapeAttr(r.key)}" data-tick-v="${
        (r.price * 100).toFixed(0)}"`}>${
      r.price == null ? "—" : (r.price * 100).toFixed(0) + "¢"}</span>
    <span class="kx-num kx-n" title="The venue’s implied price for NO" style="color:var(--bad)"${
      no == null ? "" : ` data-tick="n:${escapeAttr(r.key)}" data-tick-v="${no}"`}>${
      no == null ? "—" : no + "¢"}</span>
    <span class="kx-num kx-m" title="Our model’s probability for the same claim">${
      r.model == null ? "—" : (r.model * 100).toFixed(0) + "%"}</span>
    <span class="kx-num kx-e">${edge}</span>
    <span class="kx-vol" title="24h volume">$${Number(r.vol || 0).toLocaleString()}</span>
    <button class="btn pm-view" data-act="pmPick" data-arg="${escapeAttr(r.key)}">View</button>
    ${meter}
  </div>`;
}

function predBoardHTML(kx, d) {
  const all = pmVenueRows(kx, d);
  const k = kx || {};
  const modeled = ((k.rows) || []).filter((r) => r.model_p != null);
  const nRec = ((k.rows) || []).filter((r) => r.rec).length
    + ((k.weather) || []).filter((r) => r.rec).length;
  // Category tabs, the render's top strip. "Top opportunities" sorts the
  // PRICED markets by the size of the gap; everything else is the plain
  // volume table, filtered to one sport where one is picked.
  const cats = [["top", "Top opportunities"], ["all", "All markets"]];
  for (const s of [...new Set(all.map((r) => r.sport).filter(Boolean))].sort()) {
    cats.push([`s:${s}`, s]);
  }
  if (!cats.some(([c]) => c === _pmCatSel)) _pmCatSel = "top";
  const tabs = `<div class="pm-cats">${cats.map(([c, label]) =>
    `<button class="mbc-chip${_pmCatSel === c ? " active" : ""}"
       data-act="pmCatSet" data-arg="${c}">${escapeHtml(label)}</button>`).join("")}</div>`;

  let rows = all;
  if (_pmCatSel === "top") {
    rows = all.slice().sort((a, b) =>
      (b.edge == null ? -1 : Math.abs(b.edge)) - (a.edge == null ? -1 : Math.abs(a.edge)));
  } else if (_pmCatSel.startsWith("s:")) {
    rows = all.filter((r) => r.sport === _pmCatSel.slice(2));
  }
  const shown = rows.slice(0, PM_BOARD_SHOWN);
  const sel = all.find((r) => r.key === _pmSelKey) || null;

  const avgEdge = modeled.length
    ? modeled.reduce((s, r) => s + Math.abs(r.edge_pts || 0), 0) / modeled.length
    : null;
  const totVol = all.reduce((s, r) => s + (Number(r.vol) || 0), 0);

  // `pm-tiles` names the board's own tile strip. `.stats` is the shared
  // tile row and this page grows three of them once it has data — the
  // board's, the flow tab's and the proof tab's. A render check written
  // on a machine where only one had data counted four tiles and pinned
  // four; on a fed board it counted twelve and reported drift that was
  // not there. The claim is about the BOARD's tiles, so it names them.
  //
  // Written as a JS comment rather than the HTML one it started as: an
  // HTML comment inside this template ships to every reader as a DOM
  // node, and test_typography caught its straight apostrophes doing it.
  // Kalshi vs the BOOKS — venue against venue, no model in the row.
  // Roadmap #7: "two markets pricing the same event differently is a
  // feed all by itself." Both columns are facts (the exchange's price,
  // the books' de-vigged moneyline); the reader decides who is wrong.
  const div = ((k.rows) || []).filter((r) => r.divergence)
    .sort((a, b) => Math.abs(b.book_gap_pts) - Math.abs(a.book_gap_pts))
    .slice(0, 6);
  const divergenceHTML = div.length ? `
    <div class="section-title">Kalshi vs the books
      <span class="sub">— the exchange and the sportsbooks pricing the same winner
      differently, in probability points. Two live markets can’t both be right;
      no opinion of ours is in this table.</span></div>
    <div class="card kx-table" style="padding:0">
      ${div.map((r) => `<div class="rec-row">
        <span style="flex:1;min-width:150px"><b>${escapeHtml(r.title || r.matchup || "")}</b>
          <span style="opacity:.55;font-size:.85em"> ${escapeHtml((r.sport || "").toUpperCase())}</span></span>
        <span style="min-width:110px;text-align:right">Kalshi ${(100 * (r.prob || 0)).toFixed(0)}%</span>
        <span style="min-width:100px;text-align:right">books ${(100 * (r.book_p || 0)).toFixed(0)}%</span>
        <span style="min-width:78px;text-align:right;font-weight:700;color:${Math.abs(r.book_gap_pts) >= 7 ? "var(--warn)" : "var(--text-dim)"}">
          ${r.book_gap_pts > 0 ? "+" : ""}${r.book_gap_pts} pts</span>
      </div>`).join("")}
    </div>` : "";
  return `
    ${deskSectionHTML(kx)}
    ${divergenceHTML}
    <div class="section-title">The board
      <span class="sub">— every live market from both venues. Kalshi runs a
      two-sided book we can price against, so those rows carry our number and
      the gap; Polymarket rows show the venue’s price and link out. A dash
      means we do not price that market, not that the edge is zero.</span></div>
    ${tabs}
    <div class="stats pm-tiles">
      ${pmxTile("Markets tracked", all.length, "both venues, live now", "bars")}
      ${pmxTile("Priced by our model", modeled.length, "Kalshi two-sided books", "line")}
      ${pmxTile("Average gap", avgEdge == null ? "—" : avgEdge.toFixed(1) + " pts",
             "model vs market, priced rows", "bars-good")}
      ${pmxTile("24h volume", "$" + Math.round(totVol).toLocaleString(),
             `the desk recommends ${nRec}`, "refresh")}
    </div>
    <div class="pm-layout">
      <div class="card kx-table pm-table" style="padding:0">${
        shown.map(pmBoardRowHTML).join("") || `
        ${panelEmpty(k.note
          || "No open markets on the last pull — the board fills as the venues list events.")}`}
      </div>
      <aside class="card pm-detail">${pmDetailHTML(sel)}</aside>
    </div>
    ${rows.length > shown.length
      ? `<p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:8px">
         Showing ${shown.length} of ${rows.length} in this view.</p>` : ""}`;
}

const PMX_LEAGUES = [["all", "All Markets"], ["nfl", "NFL"], ["cfb", "CFB"], ["mlb", "MLB"],
                     ["nba", "NBA"], ["wnba", "WNBA"], ["ufc", "UFC"]];

/* The venues' marks. Kalshi's is its letter; Polymarket's is drawn as the
   outline mark its app uses. Both are the venues' own identities, shown
   to say whose market a row is — the same reason the table names them.
   The hero's art is Ethan's own banner of the two (web/img/predict,
   2026-09-26: "use this second screenshot as the background of where i
   circled … like how the pick of the day renders is"): it fills the
   hero behind the words, the way the venue fills the Pick of the Day. */
function pmxKalshiMark(size = 30) {
  return `<span class="pmx-k" style="font-size:${size}px" aria-hidden="true">K</span>`;
}
function pmxPolyMark(size = 30) {
  return `<svg class="pmx-poly" width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true">
    <path d="M6 7.5 26 3v26L6 24.5z M6 7.5 26 16 M6 24.5 26 16" fill="none" stroke="currentColor"
      stroke-width="2.6" stroke-linejoin="round"/></svg>`;
}

/* A door to a venue, through the same switch as every outbound market
   link (EXTERNAL_MARKET_LINKS, see extLink): off, it is a plain card. */
const PMX_VENUE_URL = { kalshi: "https://kalshi.com/markets", polymarket: "https://polymarket.com" };
function pmxDoor(venue, cls, inner) {
  return EXTERNAL_MARKET_LINKS
    ? `<a class="${cls}" href="${safeHref(PMX_VENUE_URL[venue])}" target="_blank" rel="noopener">${inner}</a>`
    : `<div class="${cls}">${inner}</div>`;
}

/* A stat tile in the render's dress: the label in small caps, the number
   big, the line under it, and a small drawn glyph beside it. */
function pmxGlyph(kind) {
  if (kind === "line") {
    return `<svg viewBox="0 0 72 36" aria-hidden="true"><path d="M2 32 16 22 26 26 40 12 50 18 70 4"
      fill="none" stroke="var(--brand)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }
  if (kind === "refresh") {
    return `<svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="none"
      stroke="rgba(255,255,255,.12)" stroke-width="1.5"/><path d="M28 14a10 10 0 1 0 1.5 9" fill="none"
      stroke="var(--brand)" stroke-width="2.6" stroke-linecap="round"/><path d="M29 8v7h-7" fill="none"
      stroke="var(--brand)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }
  const green = kind === "bars-good";
  const hs = green ? [14, 22, 30, 36] : [10, 18, 28, 20, 14];
  return `<svg viewBox="0 0 ${hs.length * 9} 36" aria-hidden="true">${hs.map((h, i) =>
    `<rect x="${i * 9}" y="${36 - h}" width="6" height="${h}" rx="1.5" fill="${green ? "var(--good)" : "var(--brand)"}"
      opacity="${green ? 0.55 + i * 0.15 : 0.9}"/>`).join("")}</svg>`;
}
function pmxTile(label, value, sub, glyph) {
  return `<div class="tile pmx-tile"><div class="pmx-tile-txt"><div class="k">${label}</div>
    <div class="v">${value}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>
    ${glyph ? `<span class="pmx-glyph">${pmxGlyph(glyph)}</span>` : ""}</div>`;
}

/* The price line on a flow card: OUR recorded tape of the market the
   trade was in (pm_build attaches it to the busiest markets). No tape,
   no line — a flat line drawn through nothing would be a claim. */
function pmxFlowSpark(f, d) {
  const m = ((d && d.markets) || []).find((x) => x && x.slug === f.slug);
  const pts = ((m && m.tape) || []).filter((p) => Array.isArray(p) && p.length > 1);
  if (pts.length < 2) return "";
  const w = 120, h = 34;
  const xs = pts.map((p) => p[0]), vs = pts.map((p) => p[1]);
  const t0 = Math.min(...xs), span = (Math.max(...xs) - t0) || 1;
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (hi - lo < 0.02) { lo -= 0.01; hi += 0.01; }
  const x = (t) => 1 + ((t - t0) / span) * (w - 2);
  const y = (v) => h - 2 - ((v - lo) / (hi - lo)) * (h - 4);
  const up = vs[vs.length - 1] >= vs[0];
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  return `<svg class="pmx-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${path}" fill="none" stroke="${up ? "var(--good)" : "var(--bad)"}" stroke-width="1.8"
      stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

function pmxFlowCardHTML(f, d, proven) {
  const cents = (p) => p == null ? "—" : `${(p * 100).toFixed(0)}¢`;
  const usd = (v) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const tone = { Live: "good", Chasing: "warn", Historical: "mute" }[f.status] || "brand";
  const nowTone = f.current_price != null && f.entry_price != null
    ? (f.current_price >= f.entry_price ? "good" : "bad") : "mute";
  const ring = f.score >= 70 ? "var(--bad)" : f.score >= 40 ? "var(--brand)" : "var(--text-mute)";
  const sigs = (f.signals || []).map((s) =>
    `<span class="pmx-chip" title="${escapeAttr(s.value || "")}">${escapeHtml(s.name)}</span>`).join("");
  return `<article class="pmx-fcard fc-${tone}">
    <div class="pmx-fcard-head">
      <span class="pmx-ring" style="background:conic-gradient(${ring} ${Math.max(0, Math.min(100, f.score)) * 3.6}deg, var(--fill-hover) 0)"
        title="Composite informed-flow score (0–100)"><span>${f.score}</span></span>
      <span class="pmx-who"><span class="pmx-name">${extLink(`https://polymarket.com/profile/${f.wallet}`,
        escapeHtml(traderLabel(f)))}</span>
        <span class="pmx-meta">${pmAgo(f.ts)} · ${plural(f.wallet_trades, "trade")} on our tape</span></span>
      <span class="pmx-status tone-${tone}">${escapeHtml(String(f.status || "").toUpperCase())}</span>
    </div>
    <div class="pmx-fcard-bet"><b>${escapeHtml(f.side)} ${escapeHtml(f.outcome)}</b>
      <span class="pmx-amt">· ${usd(f.usd)}</span>${pmxFlowSpark(f, d)}</div>
    <div class="pmx-market">${extLink(`https://polymarket.com/market/${f.slug}`, escapeHtml(f.market))}</div>
    <div class="pmx-metrics">
      <div><span>Position</span><b>${usd(f.usd)}</b></div>
      <div><span>Entry</span><b>${cents(f.entry_price)}</b></div>
      <div><span>Now</span><b class="tone-${nowTone}">${cents(f.current_price)}</b></div>
    </div>
    <div class="pmx-chips">${sigs}</div>
    <p class="pmx-foot">The trade this flag points at: <b>${escapeHtml(f.side)} ${escapeHtml(f.outcome)}</b>
      at ${cents(f.current_price)} or better · ${proven
        ? `<span class="tone-good">recommended (signal proven — 0.1u)</span>`
        : `<span class="tone-warn">tracked, not recommended</span> — graded on the Record page`}</p>
  </article>`;
}

function pmxFlowHTML(d, proven) {
  let flow = (d.flow || []).slice();
  const counts = {};
  flow.forEach((f) => { const l = pmFlowLeague(f); counts[l] = (counts[l] || 0) + 1; });
  if (_pmFlowLeague !== "all") flow = flow.filter((f) => pmFlowLeague(f) === _pmFlowLeague);
  const by = { volume: (a, b) => (b.usd || 0) - (a.usd || 0), newest: (a, b) => (b.ts || 0) - (a.ts || 0),
               score: (a, b) => (b.score || 0) - (a.score || 0) }[_pmFlowSort] || (() => 0);
  flow.sort(by);
  const chips = PMX_LEAGUES.map(([k, label]) => `<button type="button" class="pmx-pill${
    _pmFlowLeague === k ? " active" : ""}" data-act="pmFlowLeague" data-arg="${k}">${label}${
    k !== "all" && counts[k] ? ` <small>${counts[k]}</small>` : ""}</button>`).join("");
  const sort = `<label class="pmx-sort">Sort by:
    <select data-change="pmFlowSort" aria-label="Sort the flow">${[["volume", "Most volume"],
      ["newest", "Newest"], ["score", "Highest score"]].map(([k, l]) =>
      `<option value="${k}"${_pmFlowSort === k ? " selected" : ""}>${l}</option>`).join("")}</select></label>`;
  const cards = flow.slice(0, 12).map((f) => pmxFlowCardHTML(f, d, proven)).join("");
  return `<div class="pmx-sechead"><h2>Informed flow <details class="pmx-why"><summary>why?↑</summary>
      <p>Large trades scored for anomaly signals, with receipts on every chip (hover). Probabilities,
      never verdicts.</p></details></h2>
      <div class="pmx-pills">${chips}</div>${sort}</div>
    <div class="pmx-fgrid">${cards || `<div class="empty-slate" style="grid-column:1/-1">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">${_pmFlowLeague === "all" ? "No flagged flow yet" : "No flagged flow in this league"}</div>
      <div class="es-sub">The feed scores the last 24h of recorded tape and accumulates across
      refreshes — big trades are a few per hour.</div></div>`}</div>`;
}

/* The rail: the newest large trades, and the doors to the venues. The
   flow is Polymarket's alone — Kalshi publishes no trade identity. */
function pmxRailHTML(d) {
  const usd = (v) => `$${Math.round(Number(v || 0)).toLocaleString()}`;
  const art = (slug) => {
    const m = ((d && d.markets) || []).find((x) => x && x.slug === slug);
    return m && m.image ? `<img src="${escapeAttr(m.image)}" alt="" loading="lazy" data-onerr="remove"/>` : pmxPolyMark(20);
  };
  const latest = ((d && d.flow) || []).slice().sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 8);
  const rows = latest.map((f) => `<li class="pmx-lf">
      <span class="pmx-lf-art">${art(f.slug)}</span>
      <span class="pmx-lf-txt"><b><span class="tone-good">${usd(f.usd)}</span> ${escapeHtml(f.side)} ${
        escapeHtml(f.outcome)}</b><span>${pmAgo(f.ts)} · Polymarket</span></span>
      <span class="pmx-lf-v">${pmxPolyMark(18)}</span></li>`).join("");
  return `<section class="pmx-card pmx-live"><div class="pmx-card-head">Live flow
      <span class="pmx-livedot">Live</span></div>
      ${rows ? `<ul class="pmx-lflist">${rows}</ul>` : `<p class="pmx-empty">No large trades on the tape yet.</p>`}
      <button type="button" class="pmx-more" data-act="pmxRoom" data-arg="flow">View all live flow →</button></section>
    <section class="pmx-card pmx-tools"><div class="pmx-card-head">Market tools</div>
      ${pmxDoor("kalshi", "pmx-tool", `${pmxKalshiMark(26)}
        <span><b>Kalshi Markets</b><span>Browse live markets →</span></span>`)}
      ${pmxDoor("polymarket", "pmx-tool", `${pmxPolyMark(26)}
        <span><b>Polymarket</b><span>Browse live markets →</span></span>`)}
      <button type="button" class="pmx-tool" data-act="pmxRoom" data-arg="proof"><span class="pmx-q">?</span>
        <span><b>How it works?</b><span>Learn the basics →</span></span></button></section>`;
}
function pmxBindRooms(host) {
  const shell = host.querySelector(".pmx");
  if (!shell) return;
  host.querySelectorAll(".subnav-btn").forEach((b) => b.addEventListener("click", () => {
    shell.dataset.tab = b.dataset.subtab;
  }));
  pmxRailFade(host.querySelector(".pmx-rail"));
}

/* THE RAIL SAYS THERE IS MORE BELOW (Ethan, 2026-09-27, circling the
   cut-off Market tools card: "fix how there is this weird black bar down
   here"). A scrolling column cuts its last card at the edge; faded while
   there is more to scroll, and square again at the end, it reads as a
   list that continues rather than a box that broke. */
function pmxRailFade(rail) {
  if (!rail) return;
  const sync = () => rail.classList.toggle("more-below",
    rail.scrollTop + rail.clientHeight < rail.scrollHeight - 4);
  rail.addEventListener("scroll", sync, { passive: true });
  window.addEventListener("resize", sync, { passive: true });
  sync();
  setTimeout(sync, 400);          // the flow list fills in after the first paint
}

async function renderIntel() {
  const host = document.getElementById("intel-body");
  if (!host) return;
  const [gp, gk] = await Promise.all([
    fetchJSON(() => paidFetch("predmarkets.json"), "predmarkets"),
    fetchJSON(() => paidFetch("kalshi.json"), "kalshi")]);
  const d = gp.data, kx = gk.data;
  if (!d && !kx && (gp.failed || gk.failed)) {
    setStandaloneSource("Kalshi + Polymarket public feeds", "Prediction Market", false);
    host.innerHTML = outageHTML("the prediction-market boards", "predmarkets");
    return;
  }
  // Polymarket silent does not mean the page is empty: Kalshi is half of
  // this board and renders on its own. Same merged table, one venue in it.
  if (!d || (!(d.flow || []).length && !(d.markets || []).length)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No Polymarket data on this pull</div>
      <div class="es-sub">The launcher pulls Kalshi’s order books and Polymarket’s public
      market list and trade tape on every refresh (free, no key needed). Kalshi’s side of
      the board is below; if both stay empty, the machine may not be able to reach the
      venues.</div></div>`
      + predBoardHTML(kx, d);
    host.innerHTML = `<div class="pmx" data-tab="board"><div class="pmx-col">${pmxHeroHTML()}${host.innerHTML}</div></div>`;
    if (typeof mountEChartsAnalytics === "function") mountEChartsAnalytics(host);
    if (typeof mountLiveTicks === "function") mountLiveTicks(host);
    return;
  }
  setStandaloneSource("Kalshi + Polymarket public feeds", "Prediction Market · live venue data");
  const tape = d.tape || {};
  const proven = pmSignalProven(d.validation);
  const cents = (p) => p == null ? "—" : `${(p * 100).toFixed(0)}¢`;
  const usd = (v) => `$${Number(v || 0).toLocaleString()}`;

  const traderCards = (d.top_traders || []).map((t) => {
    const label = traderLabel(t);
    const initials = (t.name ? t.name.replace(/[^a-zA-Z0-9 ]/g, "").split(/\s+/)
      .map((w) => w[0]).slice(0, 2).join("") : t.wallet.slice(2, 4)) || "?";
    const last = (t.recent || [])[0];
    const lastTxt = last
      ? `${escapeHtml(last.side)} ${escapeHtml(last.outcome)} · ${usd(last.usd)} @ ${cents(last.price)} · ${escapeHtml(last.market)} · ${pmAgo(last.ts)}`
      : "no recent public trades pulled";
    return `<article class="card">
      <div class="card-head">
        <div class="card-id">
          <div class="pm-avatar">${escapeHtml(initials)}</div>
          <div>
            <div class="player">#${t.rank} <span class="wallet">${extLink(
              `https://polymarket.com/profile/${t.wallet}`,
              escapeHtml(label))}</span></div>
            <div class="subtitle wallet">${shortWallet(t.wallet)}</div>
          </div>
        </div>
        <span style="font-weight:800;font-size:var(--fs-xl);color:${t.pnl >= 0 ? "var(--good)" : "var(--bad)"}">
          ${t.pnl ? `${t.pnl >= 0 ? "+" : "−"}${usd(Math.abs(t.pnl))}` : "—"}</span>
      </div>
      ${t.pnl_series && t.pnl_series.length > 1
        ? `<div style="margin-top:10px">${pmSpark(t.pnl_series, 300, 62)}
           <div style="color:var(--text-mute);font-size:var(--fs-xs);margin-top:3px">Cumulative P&amp;L — past month (hover for numbers)</div></div>` : ""}
      <div style="margin-top:10px;color:var(--text-body);font-size:var(--fs-sm)">
        <span style="color:var(--text-mute)">Latest:</span> ${lastTxt}</div>
    </article>`;
  }).join("");

  /* THREE ROOMS, not one scroll. The page carried the desk, a Kalshi
     table, a Polymarket table, flow cards, trader cards and two
     validation blocks end to end — Ethan's "too much too scroll
     through". They are three different questions, so they are three
     tabs: what to bet, who is betting, and whether any of it works. */
  const rooms = subtabbedHTML("intel", [
    ["board", "Board",
     "every live market from Kalshi and Polymarket in one table, plus the desk’s picks",
     predBoardHTML(kx, d)],
    ["flow", "Flow",
     "who is betting — Polymarket’s public tape, which Kalshi does not publish",
     `<div class="stats pmx-tiles">
        ${pmxTile("Trades on tape", Number(tape.stored_total || 0).toLocaleString(), `+${tape.new_this_pull || 0} this pull`, "bars")}
        ${pmxTile("Wallets seen", Number(tape.wallets_seen || 0).toLocaleString(), "recording since day one", "line")}
        ${pmxTile("Flow flags · 24h", (d.flow || []).length, "$5K+ scored trades", "bars-good")}
        ${pmxTile("Updated", escapeHtml(formatStamp(d.generated_at, "time")), "refreshes with the site", "refresh")}
      </div>
      ${pmxFlowHTML(d, proven)}
      <div class="section-title">Top traders
        <span class="sub">— ${escapeHtml(d.traders_note || "by realized profit")}</span></div>
      <div class="cards wide">${traderCards ||
        `${panelEmpty("No trader data yet — fills on the next refresh.")}`}</div>
      <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Wallet-age signal
        matures as the tape accrues (it cannot be backfilled). Kalshi carries no public
        trader identity, which is why it appears on the board as a PRICE and never here.
        Analyzing public flow is market research; what the CFTC prosecutes
        (2026) is trading on information <i>you</i> hold a duty to keep confidential.</p>`],
    ["proof", "Does it work?",
     "the flow signal graded against what actually happened",
     `${intelVerdict(d.validation)}${intelReportCard(d.validation)}`],
  ]);
  host.innerHTML = `<div class="pmx" data-tab="${escapeAttr(_subtab.intel || "board")}">
    <div class="pmx-col">${pmxHeroHTML()}${rooms}</div>
    <aside class="pmx-rail">${pmxRailHTML(d)}</aside></div>`;
  // Every other subtabbed page binds its rooms after writing them; without
  // this the tabs render and do nothing.
  bindSubtabs(host);
  pmxBindRooms(host);
  // EACH MOUNT IN ITS OWN TRY. These are three independent enhancements
  // over markup that already stands on its own, and chaining them bare
  // means the first one to throw silently cancels the rest — which is
  // exactly what happened when the price tape was added: the chart never
  // upgraded, no error surfaced, and the SVG fallback made it look like
  // a rendering choice rather than a dead line of code.
  for (const mount of [mountEChartsPanels, mountEChartsAnalytics,
                       mountLiveTicks]) {
    if (typeof mount !== "function") continue;
    try {
      const r = mount(host);
      if (r && typeof r.catch === "function") r.catch(() => {});
    } catch (e) { /* an enhancement never breaks the page it decorates */ }
  }
}

// Position groups, in the order a depth chart is normally read. Football
// only — the other leagues have no unit split worth grouping by, so their
// players list as one squad rather than under an invented heading.
const ROSTER_GROUPS = [
  ["Offense", ["QB", "RB", "FB", "WR", "TE", "OL", "OT", "OG", "C"]],
  ["Defense", ["DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "S", "FS", "SS", "DB"]],
  ["Special teams", ["K", "P", "LS"]],
];

function rosterGroupOf(pos) {
  for (const [label, members] of ROSTER_GROUPS) if (members.includes(pos)) return label;
  return "Other";
}

/* What each league's roster tab is actually showing, said plainly. The
   NFL has a published depth chart; the others are built from who really
   appeared, and the page must not let those look like the same claim. */
/* The search box has to speak the sport it is sitting on. It shipped
   asking for "49ers, SF, Purdy" on every league, which on the MLB page is
   an example of nothing you can type. */
const ROSTER_PLACEHOLDER = {
  nfl: "Search a team or a player… (e.g. 49ers, SF, Purdy)",
  mlb: "Search a team or a player… (e.g. Yankees, NYY, Judge)",
  nba: "Search a team or a player… (e.g. Celtics, BOS, Tatum)",
  wnba: "Search a team or a player… (e.g. Liberty, NYL, Stewart)",
  cfb: "Search a program or a player… (e.g. Georgia, UGA)",
};

const ROSTER_COPY = {
  nfl: "— every team as it stands today, ordered by the coaching staff’s own "
     + "depth chart. Players who are unavailable (IR, PUP, suspended) are listed "
     + "with their status rather than quietly removed.",
  mlb: "— the league’s own active rosters, refreshed through the day, pitchers "
     + "first. The games column is measured from our own logs: playing time is "
     + "still the depth chart, the league feed just decides who exists.",
  nba: "— built from who has actually appeared for each club this season, most "
     + "minutes-logged games first. Measured playing time is the depth chart here, "
     + "rather than somebody’s published guess at one.",
  wnba: "— built from who has actually appeared for each club this season, most "
      + "games first. Measured playing time is the depth chart here, rather than "
      + "somebody’s published guess at one.",
  cfb: "— built from who has actually appeared for each program this season, most "
     + "games first. College rosters churn hardest of any league, so this list is "
     + "thin in week one and fills as the season is played.",
};

/* One player line. The depth slot is the staff's opinion and is shown as
   such; an unranked player gets no number rather than an invented one. */
function rosterPlayerHTML(p, byAppearance) {
  const slot = byAppearance
    ? (p.games != null ? String(p.games) : "—")
    : (p.depth_order ? `${escapeHtml(p.depth_pos || p.position)}${p.depth_order}` : "—");
  // The weekly designation, which the roster read for the first time on
  // 2026-08-13. "Questionable" is not unavailable — he may well play —
  // but it is the single most useful flag on a board where you are about
  // to price his volume, so it shows in its own right rather than being
  // flattened into "active".
  // Where the ESPN injury report adds something the roster feed did not.
  // `back` is the return date; `contested` fires only when BOTH feeds
  // filed and they disagree about whether he plays — a gap the merge
  // filled is not a disagreement, and marking those would flag most of
  // the board.
  const back = p.return_date
    ? ` · back ${escapeHtml(String(p.return_date).slice(5))}` : "";
  const contested = p.injury_conflict
    ? `<span class="chip warn" title="Sleeper and the ESPN injury report
         disagree about whether he plays. The more pessimistic reading is
         shown — this board never clears a player on one feed’s word.">${
         icon("warn")} feeds disagree</span>` : "";
  const tags = [
    p.rookie ? `<span class="chip">rookie</span>` : "",
    p.unavailable ? `<span class="chip down">${escapeHtml(p.status || "out")}${
      p.injury ? ` · ${escapeHtml(p.injury)}` : ""}${back}</span>` : "",
    (!p.unavailable && p.questionable)
      ? `<span class="chip warn">${escapeHtml(p.status || "questionable")}${
          p.injury ? ` · ${escapeHtml(p.injury)}` : ""}${back}</span>` : "",
    contested,
  ].join("");
  const colA = byAppearance
    ? (p.last_seen ? escapeHtml(String(p.last_seen).slice(5)) : "—")
    : (p.age != null ? p.age : "—");
  const colB = byAppearance
    ? "" : (p.years_exp != null ? (p.years_exp === 0 ? "R" : p.years_exp) : "—");
  return `<div class="ros-row${p.unavailable ? " out" : ""}">
    <span class="ros-slot">${escapeHtml(slot)}</span>
    <span class="ros-name">${playerAvatar(p.player, p.team,
        { size: 26, map: nflMap(), headshot: p.headshot })}${escapeHtml(p.player)}${tags}</span>
    <span class="ros-pos">${escapeHtml(p.position)}</span>
    <span class="ros-n">${colA}</span>
    <span class="ros-n">${colB}</span>
  </div>`;
}

function rosterTeamHTML(abbr, team, expanded, byAppearance) {
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport)[abbr] : null)
    || ((typeof TEAMS !== "undefined" && TEAMS[abbr]) || {});
  const label = meta.name || abbr;
  if (!expanded) {
    return `<button class="ros-team" data-team="${escapeHtml(abbr)}">
      <span class="ros-mark">${teamMark(abbr, 30, null, state.sport)}</span>
      <span class="ros-team-name">${escapeHtml(label)}</span>
      <span class="ros-team-n">${team.count}</span>
    </button>`;
  }
  // Football splits into units; the other leagues do not, so they list as
  // one squad rather than under an invented heading.
  let groups;
  if (byAppearance) {
    groups = team.players.map((p) => rosterPlayerHTML(p, true)).join("");
  } else {
    const byGroup = {};
    for (const p of team.players) {
      (byGroup[rosterGroupOf(p.position)] ||= []).push(p);
    }
    groups = ROSTER_GROUPS.map(([g]) => g).concat("Other")
      .filter((g) => byGroup[g] && byGroup[g].length)
      .map((g) => `<div class="ros-group">${escapeHtml(g)}
          <span class="ros-group-n">${byGroup[g].length}</span></div>
        ${byGroup[g].map((p) => rosterPlayerHTML(p, false)).join("")}`).join("");
  }
  return `<div class="card ros-card">
    <button class="ros-team open" data-team="${escapeHtml(abbr)}">
      <span class="ros-mark">${teamMark(abbr, 30, null, state.sport)}</span>
      <span class="ros-team-name">${escapeHtml(label)}</span>
      <span class="ros-team-n">${team.count}${byAppearance ? "" : ` · ${team.rookies} rookie${team.rookies === 1 ? "" : "s"}`}${team.unavailable ? ` · ${team.unavailable} ${byAppearance ? "cold" : "out"}` : ""}</span>
    </button>
    <div class="ros-head">
      <span class="ros-slot">${byAppearance ? "GP" : "SLOT"}</span><span class="ros-name">PLAYER</span>
      <span class="ros-pos">POS</span><span class="ros-n">${byAppearance ? "LAST" : "AGE"}</span><span class="ros-n">${byAppearance ? "" : "EXP"}</span>
    </div>
    ${groups}</div>`;
}

/* Recent team changes, found by diffing our own daily snapshots — no news
   feed to curate and nothing to tell the site about. */
function transactionsHTML(tx) {
  const moves = (tx && tx.moves) || [];
  if (!moves.length) {
    return `<div class="ls-note">No team changes across the
      ${plural(tx && tx.days ? tx.days : 0, "day")} tracked so far. This list fills
      itself in: each build records where every player is, and a trade is
      simply the day that answer changed.</div>`;
  }
  return `<div class="card" style="padding:0;margin-bottom:14px">
    ${moves.slice(0, 40).map((m) => `<div class="ros-move">
      <span class="ros-move-name">${escapeHtml(m.player)}</span>
      <span class="ros-move-teams">${escapeHtml(m.from)} → <b>${escapeHtml(m.to)}</b></span>
      <span class="ros-move-date">${escapeHtml(m.date)}</span>
    </div>`).join("")}</div>`;
}

function standingsRowHTML(t, label) {
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport)[t.team] : null) || {};
  const diff = t.diff > 0 ? `+${t.diff}` : `${t.diff}`;
  const cls = t.diff > 0 ? "good" : t.diff < 0 ? "bad" : "";
  const strk = t.streak > 0 ? "good" : t.streak < 0 ? "bad" : "";
  return `<div class="std-row">
    <span class="std-rank">${t.rank}</span>
    <span class="std-mark">${teamMarkIn(state.sport, t.team, 24)}</span>
    <span class="std-name">${teamLinkHTML(state.sport, t.team, meta.name || meta.nick || t.team)}</span>
    <span class="std-n std-rec">${escapeHtml(t.record)}</span>
    <span class="std-n">${t.points != null ? t.points : t.pct.toFixed(3).replace(/^0/, "")}</span>
    <span class="std-n ${cls}">${escapeHtml(diff)}</span>
    <span class="std-n std-wide">${t.pf_per_game}/${t.pa_per_game}</span>
    <span class="std-n std-wide">${escapeHtml(t.home)}</span>
    <span class="std-n std-wide">${escapeHtml(t.away)}</span>
    <span class="std-n ${strk}">${escapeHtml(t.streak_label)}</span>
    <span class="std-n std-wide">${escapeHtml(t.last10_label)}</span>
  </div>`;
}

function standingsGroupHTML(g, scoreLabel) {
  return `<div class="card std-card">
    <div class="std-group">${escapeHtml(g.label || g.conference)}</div>
    <div class="std-head">
      <span class="std-rank">#</span><span class="std-mark"></span>
      <span class="std-name">TEAM</span>
      <span class="std-n std-rec">${state.sport === "nhl" ? "W-L-OTL" : "W-L"}</span><span class="std-n">${
        state.sport === "nhl" ? "PTS" : "PCT"}</span>
      <span class="std-n">DIFF</span>
      <span class="std-n std-wide">${escapeHtml(scoreLabel || "PF/PA")}</span>
      <span class="std-n std-wide">HOME</span><span class="std-n std-wide">AWAY</span>
      <span class="std-n">STRK</span><span class="std-n std-wide">L10</span>
    </div>
    ${g.teams.map((t) => standingsRowHTML(t)).join("")}
  </div>`;
}

/* The bracket. Every matchup on it happened; nothing here is projected —
   that is what `projected_seeds` is for, and it says so on its face. */
function bracketHTML(b) {
  if (!b || !b.started) {
    return `<div class="ls-note">${escapeHtml((b && b.note) || "")}</div>`;
  }
  return `<div class="brk">${b.rounds.map((r) => `
    <div class="brk-round">
      <div class="brk-round-name">${escapeHtml(r.name)}</div>
      <div class="brk-matches">${r.matchups.map((m) => {
        const [a, bb] = m.teams, [wa, wb] = m.score;
        const line = (team, score, won) => `<div class="brk-side${won ? " won" : ""}">
          <span class="brk-team">${escapeHtml(team)}</span>
          <span class="brk-score">${score}</span></div>`;
        return `<div class="brk-match">
          ${line(a, wa, m.leader === a)}
          ${line(bb, wb, m.leader === bb)}
        </div>`;
      }).join("")}</div>
    </div>`).join("")}</div>`;
}

function seedsHTML(seeds) {
  if (!seeds || !seeds.length) return "";
  return `<div class="section-title">If the season ended today
      <span class="sub">— a PROJECTION from the table above, not a bracket.
      Nothing below has been played, and seeding here uses our own order
      rather than the league’s official tiebreakers.</span></div>
    <div class="ros-teams">${seeds.map((c) => `<div class="card std-card">
      <div class="std-group">${escapeHtml(c.conference)}</div>
      ${c.seeds.map((t) => `<div class="std-row">
        <span class="std-rank">${t.seed}</span>
        <span class="std-name">${escapeHtml(t.team)}</span>
        <span class="std-n std-rec">${escapeHtml(t.record)}</span>
        <span class="std-n">${t.pct.toFixed(3).replace(/^0/, "")}</span>
      </div>`).join("")}
    </div>`).join("")}</div>`;
}        // "player|team" → the entry, for the page being drawn
let _nextUpAt = 0, _nextUpBoard = null;

async function loadNextUp() {
  if (_nextUpBoard && Date.now() - _nextUpAt < 5 * 60e3) return _nextUpBoard;
  try {
    const res = await paidFetch("fantasy.json");
    if (res.ok) { _nextUpBoard = await res.json(); _nextUpAt = Date.now(); }
  } catch (e) {}
  return _nextUpBoard;
}

/* Around the league — headlines beside the injury board. Ethan,
   2026-09-02: "We have an injuries and news page but only display
   injuries. We should add a section for sports news. Figure out what
   we are allowed to pull and display."

   What we're allowed to show is settled in engine/sources/news.py,
   where the parser enforces it: TITLES from publisher-offered RSS
   feeds, the source's name, and a link out to the original reporting —
   never article text, never images. This renderer has nothing else to
   work with even if it wanted to. */
let _newsCache = null;
async function loadNews() {
  if (_newsCache) return _newsCache;
  try {
    const res = await boardFetch("data/news.json", { cache: "no-cache" });
    if (res.ok) _newsCache = await res.json();
  } catch (e) { /* headlines are furniture — the page stands without them */ }
  return _newsCache;
}

function newsSectionHTML(sport, news) {
  const rows = (((news || {}).sports) || {})[sport] || [];
  if (!rows.length) return "";
  const agoWord = (epoch) => {
    if (!epoch) return "";
    const h = (Date.now() / 1000 - epoch) / 3600;
    return h < 1 ? `${Math.max(1, Math.round(h * 60))}m ago`
      : h < 24 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)}d ago`;
  };
  return `
    <div class="section-title">Around the league
      <span class="sub">— headlines only; every one links to the original
      reporting at its source</span></div>
    <div class="card rec-list">
      ${rows.map((r) => `
        <div class="rb-row" style="gap:10px">
          <a href="${safeHref(r.link)}" target="_blank"
             rel="noopener noreferrer" style="flex:1;min-width:0">${escapeHtml(r.title)}</a>
          <span class="k" style="white-space:nowrap;opacity:.65">${escapeHtml(r.source)}${
            r.epoch ? ` · ${agoWord(r.epoch)}` : ""}</span>
        </div>`).join("")}
    </div>`;
}

async function renderInjuries() {
  const host = document.getElementById("injuries-body");
  if (!host) return;
  // Third reader of one file, and the last one to stop fetching it for
  // itself. The page, the watch box beside the board and the note on each
  // card must agree about who is hurt; three fetches with three lifetimes
  // is how they stop agreeing.
  const d = await loadInjuryBoard();
  const sport = state.sport || "nfl";
  const newsHTML = newsSectionHTML(sport, await loadNews());
  const rows = (((d || {}).sports) || {})[sport] || [];
  // Who holds each injured man's work (NFL: the only league with usage
  // shares measured). Keyed the way the injury rows are, so a row finds
  // its own entry without a second normalisation.
  _nextUp = new Map();
  if (sport === "nfl") {
    const fx = await loadNextUp();
    (((fx || {}).waivers || {}).next_up || []).forEach((e) => _nextUp.set(nextUpKey({ player: e.hurt, team: e.team }), e));
  }
  if (!rows.length) {
    const note = sport === "cfb"
      ? `College programs have no duty to report, so this feed runs sparse —
         emptiness here is the league’s opacity, not a fault to chase.`
      : `Either nobody in the league carries a designation right now — rare —
         or the feed declined on the last pull. It is retried on every
         refresh.`;
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No injury designations to show</div>
      <div class="es-sub">${note}</div></div>` + newsHTML;
    return;
  }

  const parsed = rows.map((r) => ({ ...r, ts: Date.parse(r.date || "") || 0 }))
    .sort((a, b) => b.ts - a.ts);
  const outTier = parsed.filter((r) => injTone(r.status) === "var(--bad)");
  const maybeTier = parsed.filter((r) => injTone(r.status) === "var(--warn)");
  // ESPN's NFL feed lists RETURNS too — hundreds of "Active" rows with
  // no injury named. They stay in the by-team groups (a return IS news
  // about that team) but out of the fresh strip, which exists to answer
  // "who just went down", not "who practiced".
  const fresh = parsed.filter((r) => r.ts >= Date.now() - 7 * 86400e3
      && !isReturnRow(r))
    .slice(0, 40);

  /* WHEN these rows were collected, which is not when this file was
     written. A declining feed is answered from cache and raises nothing,
     so the build stamps a fresh `generated_at` over data that stopped
     moving days ago — the page then reports it with full confidence.
     The builder measures the cache's own age; if it is far past the TTL
     this says so, loudly, instead of letting a stale board pass as live. */
  const ageS = (((d || {}).ages_s) || {})[sport];
  const staleAfter = (d || {}).stale_after_s || 3600;
  const staleBanner = (ageS != null && ageS > staleAfter) ? `
    <div class="card" style="--tone:var(--warn);margin-bottom:14px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} <b>These designations are
        ${escapeHtml(ageText(ageS))} old.</b> ESPN’s feed has been declining, so the board is
        being served from the last successful pull — treat every status here as
        unconfirmed until it clears.</p></div>` : "";

  const byTeam = {};
  for (const r of parsed) (byTeam[r.team] = byTeam[r.team] || []).push(r);
  /* "MOST BANGED-UP FIRST" NOW MEANS IT. This sorted on row COUNT, and
     ESPN's feed is mostly return filings — so the team leading the
     section was whichever had the most players practising, and folding
     the blocks made that impossible to miss: the top row read
     "Philadelphia Eagles · no designations · 18". Sort on the tiers the
     summary shows, so the teams worth opening are the ones at the top.
     Counted once here and handed down rather than recomputed per row. */
  const severity = {};
  for (const t of Object.keys(byTeam)) {
    const n = (tone) => byTeam[t].filter((r) => injTone(r.status) === tone).length;
    severity[t] = { out: n("var(--bad)"), maybe: n("var(--warn)") };
  }
  const teams = Object.keys(byTeam).sort((a, b) =>
    severity[b].out - severity[a].out
    || severity[b].maybe - severity[a].maybe
    || byTeam[b].length - byTeam[a].length
    || a.localeCompare(b));

  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;
  host.innerHTML = `
    ${staleBanner}
    <div class="stats">
      ${tile("Players listed", parsed.filter((r) => !isReturnRow(r)).length,
             "carrying a designation")}
      ${tile("Out tier", outTier.length, "out, IR, long-term IL")}
      ${tile("Questionable tier", maybeTier.length, "doubtful through day-to-day")}
      ${tile("Teams affected", teams.length, "of the whole league")}
    </div>
    ${fresh.length ? `
      <div class="section-title">Fresh this week
        <span class="sub">— designations filed in the last seven days, newest first.
        Hover a row for the team’s own wording.</span></div>
      <div class="card inj-list">${fresh.map((r) => injRow(r, true)).join("")}</div>` : ""}
    <div class="section-title">By team
      <span class="sub">— most banged-up first. Every current designation the league
      lists, not just this week’s.</span></div>
    ${teams.map((t) => injTeamBlock(t, byTeam[t], severity[t])).join("")}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      Statuses are the league’s own filings via ESPN’s public feed, refreshed with the
      site on a 30-minute cache, one row per player — his newest filing.${
      _nextUp.size ? ` <b>Next man up</b> names who holds an injured man’s work and the
      share each already held, from the usage board — a measured role, never a
      claim about who is on your league’s wire.` : ""} The NFL’s
      practice-level detail (limited/DNP, the usage model’s injury inputs) lives on the
      Fantasy page — this board is availability, league-wide.
      ${ageS != null
        ? `Designations collected ${escapeHtml(ageText(ageS))} ago.`
        : `Page built ${escapeHtml(formatStamp((d || {}).generated_at, "time"))}.`}</p>`
    + newsHTML;
}

/* ONE TEAM, FOLDED. Ethan, 2026-08-25: "we should make each team as a
   click down menu thing instead of showing every single player all at
   once bc it makes a lot of scrolling for that page."

   The scroll was real and mostly noise. ESPN's NFL feed lists RETURNS
   as well as injuries, so a typical team block is fifteen rows reading
   "Active · undisclosed" wrapped around the two that actually say
   something — thirty-two teams of that is several thousand pixels to
   reach a designation you could not see coming.

   THE SUMMARY HAS TO CARRY THE SIGNAL or folding just hides it. A
   collapsed row that says only "Carolina Panthers 17" makes you open all
   thirty-two to find the one with a player out, which is the same
   scrolling with extra taps. So the tier counts ride on the summary
   line: how many are out, how many are questionable, and — said plainly
   rather than left blank — when a team has neither.

   ALL CLOSED BY DEFAULT, including teams with players out. "Who just
   went down" is already answered above by Fresh this week, which stays
   open; this section is the league-wide reference underneath it, and a
   reference that auto-expands its biggest entries is the scroll again.

   Native <details>: keyboard and screen-reader behaviour for free, and
   it still works with JS broken. The chevron is the site's own rather
   than the UA triangle, because that one does not inherit colour and
   sits black on black in the dark theme. */
function injTeamBlock(team, rows, sev) {
  const { out, maybe } = sev;
  const tiers = out || maybe
    ? `${out ? `<span class="it-tier bad">${out} out</span>` : ""}${
        maybe ? `<span class="it-tier warn">${maybe} questionable</span>` : ""}`
    : `<span class="it-tier quiet">no designations</span>`;
  return `<details class="inj-team">
    <summary class="inj-team-head">${escapeHtml(team)}
      ${tiers}<span class="inj-team-n">${rows.length}</span></summary>
    <div class="card inj-list">${rows.map((r) => injRow(r, false)).join("")}</div>
  </details>`;
}

function pressureHTML(pr, d) {
  if (!pr || !pr.ranked) return "";
  const cols = PRESSURE_RATES.filter(([k]) => (pr.ranked[k] || []).length);
  if (!cols.length) return "";
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport) : {}) || {};
  const CAP = 10;
  const col = ([key, title, note]) => {
    const rows = pr.ranked[key];
    return `
    <div class="rec-bucket">
      <div class="rb-head">${escapeHtml(title)}
        <span class="mini" style="opacity:.6"> ${escapeHtml(note)}</span></div>
      ${rows.slice(0, _stdPressureAll ? rows.length : CAP).map((r) => `
        <div class="std-row std-unit-row">
          <span class="std-rank">${r.rank}</span>
          <span class="std-mark">${teamMarkIn(state.sport, r.team, 22)}</span>
          <span class="std-name">${escapeHtml((meta[r.team] || {}).name
            || (meta[r.team] || {}).nick || r.team)}
            <span class="k" style="opacity:.6">${r.n} game${r.n === 1 ? "" : "s"}</span></span>
          <span class="std-n">${pressurePct(r.value)}</span>
        </div>`).join("")}
    </div>`;
  };
  const most = Math.max(...cols.map(([k]) => pr.ranked[k].length));
  const lastSeason = pr.season_used !== pr.season;
  return `
    <div class="section-title">Under pressure
      <span class="sub">— clutch, reliability, comeback and choke, from the
        finished ${escapeHtml(String(pr.season_used))} games${lastSeason
          ? " — last season’s, until this one has four games a team" : ""}
        · one-score means within ${escapeHtml(pressureUnit(pr))}
        · a team needs ${pr.min_games} games, and ${pr.min_rate_n} of the kind
        counted, to be ranked</span></div>
    ${pr.note ? `<div class="ls-note">${escapeHtml(pr.note)}</div>` : ""}
    <div class="rec-buckets pr-buckets">${cols.map(col).join("")}</div>
    ${most > CAP ? `<button class="btn ghost" type="button"
      data-act="stdPressureToggle">${_stdPressureAll
        ? `Show the top ${CAP}` : `Show all ${most} teams`}</button>` : ""}`;
}

function unitRankingsHTML(ur, d) {
  /* NEVER SILENTLY ABSENT ON A FOOTBALL PAGE. This returned "" whenever
     the build had no rankings — and for the NFL that is every day until
     Week 1 has finals, so the section Ethan asked for on 09-02 was
     invisible when he looked for it on 09-05 and he asked again. The
     rankings themselves are unchanged (scoring offense and defense from
     the same finished games as the table); what changes is the empty
     case, which now says WHY and, on the NFL, shows the model's own
     measured profile ranked on last season until this one has games. */
  const isFootball = state.sport === "nfl" || state.sport === "cfb";
  if (!ur || !(ur.offense || []).length) {
    if (!isFootball) return "";
    return unitRankingsWaitHTML(d || {});
  }
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport) : {}) || {};
  const CAP = 25;
  const col = (title, note, rows) => `
    <div class="rec-bucket">
      <div class="rb-head">${escapeHtml(title)}
        <span class="mini" style="opacity:.6"> ${escapeHtml(note)}</span></div>
      ${rows.slice(0, _stdUnitsAll ? rows.length : CAP).map((r) => `
        <div class="std-row std-unit-row">
          <span class="std-rank">${r.rank}</span>
          <span class="std-mark">${teamMarkIn(state.sport, r.team, 22)}</span>
          <span class="std-name">${escapeHtml((meta[r.team] || {}).name
            || (meta[r.team] || {}).nick || r.team)}
            <span class="k" style="opacity:.6">${escapeHtml(r.record)}</span></span>
          <span class="std-n">${Number(r.value).toFixed(1)}</span>
        </div>`).join("")}
    </div>`;
  const more = ur.offense.length - CAP;
  return `
    <div class="section-title">Team rankings
      <span class="sub">— scoring offense and defense, in ${escapeHtml(
        ur.measure || "points per game")} · from the same finished games
        as the table above</span></div>
    <div class="rec-buckets">
      ${col("Offense", "most points scored", ur.offense)}
      ${col("Defense", "fewest points allowed", ur.defense)}
    </div>
    ${more > 0 ? `<button class="btn ghost" type="button"
      data-act="stdUnitsToggle">${_stdUnitsAll
        ? "Show the top 25" : `Show all ${ur.offense.length} teams`}</button>` : ""}`;
}

/* The football rankings section when the season has no rankings yet.

   Two halves. The REASON, from the standings build's own fields: a
   season nobody has played (`season_wait`, with the first game date when
   the build knows it), or a season whose feed was unreachable, or fewer
   than four teams with a finished game. And, where the board carries
   it, THE MODEL'S OWN PROFILE: `team_shapes` is measured on the latest
   season with enough finals (nfl_build attaches it, ranked on last
   season until this one has games), and its raw offense and defense
   axes are points scored and points allowed per game — the same two
   measures the scoring rankings use, so the columns read the same and
   the caveat the game page already prints applies: last season's roster
   is not this season's. */
function unitRankingsWaitHTML(d) {
  const season = d.season || "";
  // v5: a payload without a season wrote " has no scoring rankings of
  // its own yet" — a sentence with its subject missing, on any board
  // built before the season field landed. Say "this season" instead.
  const who = season ? String(season) : "this season";
  const Who = season ? String(season) : "This season";
  const why = d.season_wait
    ? `The ${season ? `${season} ` : ""}season hasn’t kicked off${
        d.first_games ? ` — first games ${escapeHtml(d.first_games)}` : ""}.
        Scoring rankings start with the first finals.`
    : d.feed_error
      ? `${Who} has no scoring rankings of its own yet — the league feed
         was unreachable on the last build, and fewer than four teams have
         a finished game on file.`
      : `${Who} has no scoring rankings of its own yet — fewer than four
         teams have a finished game on file. They start with the first
         finals.`;
  const shapes = (state.data || {}).team_shapes || {};
  const shapeSeason = (state.data || {}).team_shapes_season || "";
  const teams = Object.keys(shapes).filter((t) => shapes[t] && shapes[t].raw);
  let fallback = "";
  if (teams.length >= 4) {
    const meta = (typeof teamsForSport === "function"
      ? teamsForSport(state.sport) : {}) || {};
    const col = (title, note, key, ascending) => {
      const rows = teams.slice().sort((a, b) => {
        const va = Number(shapes[a].raw[key]), vb = Number(shapes[b].raw[key]);
        return (ascending ? va - vb : vb - va) || a.localeCompare(b);
      });
      return `
      <div class="rec-bucket">
        <div class="rb-head">${escapeHtml(title)}
          <span class="mini" style="opacity:.6"> ${escapeHtml(note)}</span></div>
        ${rows.map((t, i) => `
          <div class="std-row std-unit-row">
            <span class="std-rank">${i + 1}</span>
            <span class="std-mark">${teamMarkIn(state.sport, t, 22)}</span>
            <span class="std-name">${escapeHtml((meta[t] || {}).name
              || (meta[t] || {}).nick || t)}
              <span class="k" style="opacity:.6">${shapes[t].games || 0} gm</span></span>
            <span class="std-n">${Number(shapes[t].raw[key]).toFixed(1)}</span>
          </div>`).join("")}
      </div>`;
    };
    fallback = `
      <p class="rail-quiet" style="margin:0 0 10px">Until then, the model’s
        measured profile — points scored and points allowed per game —
        ranked on the ${escapeHtml(String(shapeSeason))} season. Last season’s
        roster is not this season’s.</p>
      <div class="rec-buckets">
        ${col("Offense", `points scored per game, ${shapeSeason}`, "offense", false)}
        ${col("Defense", `points allowed per game, ${shapeSeason}`, "defense", true)}
      </div>`;
  }
  // The heading says what is ranked BELOW it: last season's finished
  // games until this one has its first, not "no rankings" over a table
  // of thirty-two ranked teams.
  return `
    <div class="section-title">Team rankings
      <span class="sub">— scoring offense and defense${fallback
        ? ` · ranked on the ${escapeHtml(String(shapeSeason))} season’s finished
           games until ${escapeHtml(who)} has its first`
        : ", from finished games"}</span></div>
    <p class="rail-quiet" style="margin:0 0 ${fallback ? "6px" : "22px"}">${why}</p>
    ${fallback}`;
}

async function renderStandings() {
  const host = document.getElementById("standings-body");
  if (!host) return;
  const sport = state.sport || "nfl";
  const d = await loadStandings(sport);
  const title = document.getElementById("standings-title");
  const isFootball = sport === "nfl" || sport === "cfb";
  if (title) title.childNodes[0].nodeValue =
    `${(SPORT_META[sport] || {}).label || sport.toUpperCase()} ${
      isFootball ? "rankings & standings" : "standings"} `;
  const sub = document.getElementById("standings-sub");
  if (sub) {
    /* WHERE THE NUMBERS CAME FROM. The page used to say "counted from our
       own results" whatever had happened — including when that count was
       a half-ingested season showing baseball clubs with ties. The build
       now stamps `source`, and this line reports it rather than asserting
       one of the two. */
    const live = d.source === "league";
    // A season nobody has played yet gets a WAITING header, not
    // "2026 regular season · 0 games counted (feed unavailable)" — we
    // never asked the feed, and the parenthetical would blame a working
    // feed for a season that has not kicked off (2026-08-24).
    sub.textContent = d.season_wait
      ? `— waiting on the ${d.season} season${
          d.first_games ? ` · first games ${d.first_games}` : ""}`
      : d.season
      ? `— ${d.season} regular season · `
        + (live
          ? "the league’s own records, refreshed with the site"
          : d.source === "alignment" ? "the season has opened and no game has finished"
          : `${(d.games_counted || 0).toLocaleString()} games counted from our own results (the league’s feed was unavailable)`)
        + ` · ${d.order_note || ""}`
      : (live ? "— the league’s own records."
              : "— counted from our own results.");
  }
  const groups = d.groups || [];
  /* THE RANKINGS LEAD ON A FOOTBALL PAGE. Ethan asked on 09-02, 09-05
     and 09-08 in the same words: "For nfl and cfb on the rankings page,
     we should have a section ranking the current ranking for teams
     defense and offense." Built on 09-02 and drawn LAST — under eight
     division tables on the NFL, under 130-odd rows on the CFB — and the
     empty-table branch below returned before reaching them, which before
     Week 1 is the NFL on every day the feed answers with no teams. The
     nav button that opens this page says "Rankings": the rankings are
     the first thing on it now, and an empty table cannot hide them. */
  const rankings = unitRankingsHTML(d.unit_rankings, d);
  if (!groups.length) {
    host.innerHTML = `${rankings}<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <h3>${d.season_wait
        ? `Waiting on the ${d.season} season`
        : "No standings yet"}</h3><p>${escapeHtml(d.note
        || "Standings for this sport have not been built yet.")}</p></div>`;
    return;
  }
  const b = d.bracket || {};
  // A division chip from another sport must not filter this one to an
  // empty page — an unknown selection means "All".
  if (_stdGroup && !groups.some((g) =>
      (g.label || g.conference || "") === _stdGroup)) _stdGroup = "";
  /* A fallback table that LOOKS official is the failure this page just
     had. When the league’s feed was unavailable and these are our own
     counted games, say so above the table — not only in a note the empty
     state would have shown. */
  const fallbackBanner = (d.source === "computed" && d.note) ? `
    <div class="card" style="--tone:var(--warn);margin-bottom:14px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} <b>These are our
        counted games, not the league’s table.</b> ${escapeHtml(d.note)}</p></div>` : "";
  host.innerHTML = `
    ${fallbackBanner}
    ${rankings}
    ${b.started ? `<div class="section-title tight">Postseason
        <span class="sub">— every matchup here was played. Series scores are
        games won, so an unfinished series shows where it stands.</span></div>
      ${bracketHTML(b)}` : ""}
    <div class="section-title"${b.started || rankings ? "" : ' style="margin-top:0"'}>Teams
      <span class="sub">— ${groups.length} group(s)</span></div>
    ${groups.length > 2 ? `<div class="std-chips">
      <button class="al-cat${!_stdGroup ? " on" : ""}" type="button"
        data-act="stdSet" data-arg="">All</button>
      ${groups.map((g) => {
        const label = g.label || g.conference || "";
        return `<button class="al-cat${_stdGroup === label ? " on" : ""}"
          type="button" data-act="stdSet" data-arg="${escapeAttr(label)}"
          >${escapeHtml(label)}</button>`;
      }).join("")}</div>` : ""}
    <div class="ros-teams">
      ${groups.filter((g) => !_stdGroup
          || (g.label || g.conference || "") === _stdGroup)
        .map((g) => standingsGroupHTML(g, d.score_label)).join("")}
    </div>
    ${pressureHTML(d.pressure, d)}
    ${b.started ? "" : seedsHTML(d.projected_seeds)}
    ${b.started ? "" : `<div class="ls-note">${escapeHtml(b.note || "")}</div>`}`;
}

async function renderRosters() {
  const host = document.getElementById("rosters-body");
  if (!host) return;
  const sport = state.sport || "nfl";
  const d = await loadRosters(sport);
  // College team ids ride on the roster payload since 2026-09-14 — see
  // rosters_build.write. Without them `teamMark` has no ESPN id for a
  // school and every header drew the monogram instead of the logo.
  if (sport === "cfb" && d && d.team_meta && Object.keys(d.team_meta).length) {
    _cfbTeams = d.team_meta;
    window.ACTIVE_TEAMS = teamsForSport(sport);
  }
  // Only the NFL has a published depth chart. Everything else is built
  // from appearances, and the page must never let those read as the same
  // kind of claim.
  const byAppearance = (d.source === "appearances");
  const sub = document.getElementById("rosters-sub");
  if (sub) sub.textContent = ROSTER_COPY[sport] || "— every team as it stands today.";
  const search = document.getElementById("roster-search");
  if (search) search.placeholder = ROSTER_PLACEHOLDER[sport]
    || "Search a team or a player…";
  const title = document.getElementById("rosters-title");
  if (title) title.childNodes[0].nodeValue =
    `${(SPORT_META[sport] || {}).label || sport.toUpperCase()} rosters `;
  const teams = d.teams || {};
  const abbrs = Object.keys(teams).sort();
  if (!abbrs.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("list", 30)}</div>
      <h3>No roster data for ${escapeHtml(sport.toUpperCase())}</h3>
      <p>${escapeHtml(d.note
        || "Rosters for this sport have not been built yet.")}</p></div>`;
    return;
  }
  const q = (state.rosterQuery || "").trim().toLowerCase();
  // A player search jumps you to his team rather than showing a stray row:
  // "who is this guy with" and "show me that roster" are the same question.
  let shown = abbrs;
  if (q) {
    const known = (typeof teamsForSport === "function")
      ? teamsForSport(sport) : (typeof TEAMS !== "undefined" ? TEAMS : {});
    shown = abbrs.filter((a) => {
      const meta = known[a] || {};
      if (a.toLowerCase().includes(q)) return true;
      if ((meta.name || "").toLowerCase().includes(q)) return true;
      if ((meta.nick || "").toLowerCase().includes(q)) return true;
      if ((meta.loc || "").toLowerCase().includes(q)) return true;
      return teams[a].players.some((p) => p.player.toLowerCase().includes(q));
    });
  }
  // One match is unambiguous — open it instead of making you tap again.
  const open = shown.length === 1 ? shown[0] : _rosterOpen;
  // ANY note the build wrote gets shown, not just the unavailable one.
  //
  // `rosters_build` captures exactly why it fell back to appearances —
  // "built from appearances because the league feed failed (...) —
  // pitchers don't bat, so they are missing from this view" — and then
  // this line dropped it on the floor, because the fallback payload is
  // stamped feed:"live" (it IS live data, just from a different source).
  //
  // So the page Ethan looked at on 2026-08-13 listed 18 Cubs, every one
  // of them a position player, with nothing anywhere saying a whole half
  // of the roster was missing or why. The build had already done the work
  // of explaining itself; the page just had to print it. A missing
  // pitcher that announces itself is a known gap. A silent one is a
  // wrong roster.
  const stale = (d.note || "")
    ? `<div class="warning" style="margin-bottom:12px">${icon('warn')} ${escapeHtml(d.note)}</div>` : "";
  // Team changes come from diffing daily roster snapshots, which only the
  // NFL feed produces. Showing an empty "recent moves" panel for a sport
  // that cannot detect one would read as "no trades happened".
  const moves = d.transactions ? `
    <div class="section-title">Recent team changes
      <span class="sub">— from diffing this site’s own daily roster snapshots,
      not a news feed. Anything that changed teams shows up here on its own.</span></div>
    ${transactionsHTML(d.transactions)}` : "";
  host.innerHTML = stale + moves + `
    <div class="section-title">Teams
      <span class="sub">— ${shown.length} of ${abbrs.length} shown${q ? ` matching "${escapeHtml(q)}"` : ""}
      · ${(d.player_count || 0).toLocaleString()} players on file${
        byAppearance && d.season ? ` · ${d.season} season appearances` : ""}</span></div>
    ${shown.length ? `<div class="ros-teams">
        ${shown.map((a) => rosterTeamHTML(a, teams[a], a === open, byAppearance)).join("")}
      </div>` : panelEmpty(`No team or player matches "${q}".`, "search")}`;
  host.querySelectorAll(".ros-team").forEach((b) => b.addEventListener("click", () => {
    _rosterOpen = _rosterOpen === b.dataset.team ? null : b.dataset.team;
    renderRosters();
  }));
}

function teamRecordLine(r) {
  if (!r || !r.games) return "";
  const ats = r.ats_w + r.ats_l + r.ats_p;
  const ou = r.over + r.under + r.ou_p;
  const bits = [`<b>${escapeHtml(r.record)}</b>`,
                `${r.pf_per_game} scored · ${r.pa_per_game} allowed`];
  if (ats) bits.push(`${r.ats_w}-${r.ats_l}${r.ats_p ? "-" + r.ats_p : ""} ATS`);
  if (ou) bits.push(`${r.over}-${r.under}${r.ou_p ? "-" + r.ou_p : ""} O/U`);
  return bits.join(" · ");
}

function teamSquadHTML(sq, sport) {
  const groups = ((sq || {}).positions || []).filter(
    (g) => (g.players || []).length);
  if (!groups.length) return "";
  /* A RATE PRINTS AS A RATE. `snap_pct` is a share of snaps, 0-1, and
     the row used to read "Snap Pct 0/g · 0.3 total" — seven games of
     four percent added into a number that means nothing, beside a
     per-game figure that rounded to zero (Ethan's Rams page,
     2026-09-10). The engine now says which markets are rates; this
     prints them as one percentage and no total. */
  const stat = (st) => (st.rate
    ? `${escapeHtml(marketWord(st.market))}
       <b>${Math.round(st.per_game * 100)}%</b><span class="tsq-tot">
       of snaps</span>`
    : `${escapeHtml(marketWord(st.market))}
       <b>${st.per_game}</b><span class="tsq-tot">/g · ${st.total} total</span>`);
  const body = groups.map((g) => `
    <div class="tsq-pos">
      <div class="tsq-pos-k">${escapeHtml(g.position)}${
        g.listed > (g.players || []).length
          ? `<span class="tsq-more">${g.listed} listed</span>` : ""}</div>
      ${(g.players || []).map((w) => `
        <button class="tsq-row" type="button"
                data-player-page="${escapeAttr(slugify(w.player))}">
          <span class="tsq-who">${escapeHtml(w.player)}${teamInjMark(w.player)}</span>
          <span class="tsq-gp">${w.games} G</span>
          <span class="tsq-stats">${(w.stats || []).slice(0, 2)
            .map(stat).join('<span class="tsq-sep">·</span>')}</span>
        </button>`).join("")}
    </div>`).join("");
  return `
    <div class="section-title">Squad${sq.season ? ` · ${sq.season}` : ""}
      <span class="sub">— every player with a game logged for this team,
      by position, ordered by what he actually did rather than by a chart
      somebody filed. Tap a name for his own page.</span></div>
    <div class="tsq">${body}</div>
    <p class="rank-help">Built from the game logs this site has ingested,
      so a player who has not taken a snap for this team yet is not here —
      which in the first week of a season is most of a roster.</p>`;
}

function teamSeasonsHTML(p) {
  const rows = (p || {}).seasons || [];
  if (!rows.length) return "";
  return `
    <div class="section-title">Season by season
      <span class="sub">— record, points a game either way, and where each
      unit ranked IN THAT SEASON. A rank without the field it came from is
      not a fact anybody can use.</span></div>
    <div class="rank-scroll"><table class="rank-table"><thead><tr>
      <th>Season</th><th>Record</th><th>Scored</th><th>Allowed</th>
      <th>Offense</th><th>Defense</th><th>ATS</th><th>O/U</th>
      </tr></thead><tbody>
      ${rows.map((r) => `<tr>
        <td>${r.season}</td>
        <td class="rank-name">${escapeHtml(r.record)}</td>
        <td>${r.pf_per_game}</td>
        <td>${r.pa_per_game}</td>
        <td>${r.offense_rank ? `${r.offense_rank} of ${r.teams_ranked}`
              : '<span class="rank-none">—</span>'}</td>
        <td>${r.defense_rank ? `${r.defense_rank} of ${r.teams_ranked}`
              : '<span class="rank-none">—</span>'}</td>
        <td>${r.ats_w + r.ats_l + r.ats_p
              ? `${r.ats_w}-${r.ats_l}${r.ats_p ? "-" + r.ats_p : ""}`
              : '<span class="rank-none">no line</span>'}</td>
        <td>${r.over + r.under + r.ou_p
              ? `${r.over}-${r.under}${r.ou_p ? "-" + r.ou_p : ""}`
              : '<span class="rank-none">no total</span>'}</td>
      </tr>`).join("")}
    </tbody></table></div>`;
}

/* How many opponents to show before the list is a wall. Measured on a
   430px phone: a full NFL list is 31 chips and nine rows, which pushed
   the head-to-head table — the thing he came for — off the bottom of two
   screens. The chips are ordered most-played first, so the first dozen
   are the rivalries and the rest is the long tail. */
const TEAM_OPP_SHOWN = 12;

function teamOppPickerHTML(d, picked) {
  const list = d.opponents || [];
  if (!list.length) return "";
  // THE CHIP THAT WAS PRESSED, which during a fetch is not yet the one
  // the payload knows about. Defaulted to the payload's own answer so a
  // caller that has no pending selection — and every test that calls
  // this directly — behaves exactly as before.
  if (picked === undefined) picked = (d.head_to_head || {}).opponent;
  // A chosen opponent is ALWAYS drawn, wherever he sits in the tail —
  // collapsing the list must never hide the one that is currently on.
  const shown = _teamOppAll ? list
    : list.filter((o, i) => i < TEAM_OPP_SHOWN || o.team === picked);
  const hidden = list.length - shown.length;
  return `
    <div class="section-title">Against
      <span class="sub">— only teams there are finals against, so a chip
      never opens an empty page. Most-played first.</span></div>
    <div class="std-chips">
      ${shown.map((o) => `<button type="button"
        class="al-cat tm-opp${o.team === picked ? " on" : ""}"
        data-team-vs="${escapeAttr(o.team)}"
        aria-pressed="${o.team === picked}">
        ${escapeHtml(o.name || o.team)}
        <span class="tm-n">${o.games}</span></button>`).join("")}
      ${hidden > 0 ? `<button type="button" class="al-cat tm-more"
        data-team-more="1">+${hidden} more</button>` : ""}
      ${_teamOppAll && list.length > TEAM_OPP_SHOWN ? `<button type="button"
        class="al-cat tm-more" data-team-more="0">Show fewer</button>` : ""}
    </div>`;
}

function teamH2HHTML(h, sport) {
  if (!h) return "";
  if (!(h.games || []).length) {
    return `<p class="rank-help">No finals between
      ${escapeHtml(h.name)} and ${escapeHtml(h.opponent_name)} in the seasons
      we hold.</p>`;
  }
  const s = h.summary;
  return `
    <div class="section-title">${escapeHtml(h.name)} vs ${escapeHtml(h.opponent_name)}
      <span class="sub">— ${teamRecordLine(s)}</span></div>
    <div class="rank-scroll"><table class="rank-table"><thead><tr>
      <th>Season</th><th></th><th class="rank-name">Result</th>
      <th>Score</th><th>Line</th><th>ATS</th><th>Total</th>
      </tr></thead><tbody>
      ${h.games.map((g) => `<tr>
        <td>${g.season}${g.period ? ` · ${escapeHtml(_teamWeek(sport, g.period))}` : ""}</td>
        <td>${g.at_home ? "vs" : "at"}</td>
        <td class="rank-name"><b class="${g.result === "W" ? "tm-w"
            : g.result === "L" ? "tm-l" : ""}">${g.result}</b>
          ${g.margin > 0 ? "+" : ""}${g.margin}</td>
        <td>${g.points_for}–${g.points_against}</td>
        <td>${g.line == null ? '<span class="rank-none">—</span>'
              : (g.line > 0 ? "+" : "") + g.line}</td>
        <td>${g.covered === null || g.covered === undefined
              ? '<span class="rank-none">—</span>'
              : g.covered === "push" ? "push" : g.covered ? "cover" : "no"}</td>
        <td>${g.total == null ? '<span class="rank-none">—</span>'
              : `${g.total} ${g.ou || ""}`}</td>
      </tr>`).join("")}
    </tbody></table></div>
    <p class="rank-help">The line is HIS number, not the home team’s — a
      minus means he was laying it. A game we hold no line for still counts
      in the record above and is left blank here rather than graded.</p>`;
}

/* A period is "021" — the week within the season. NFL weeks past 18 are
   the playoffs and saying "Week 21" out loud is worse than saying
   nothing, so those are named. */
function _teamWeek(sport, period) {
  const n = parseInt(period, 10);
  if (!n) return String(period || "");
  if (sport === "nfl" && n > 18) {
    return ({ 19: "Wild Card", 20: "Divisional", 21: "Conf. Champ",
              22: "Super Bowl" })[n] || `Week ${n}`;
  }
  return `Week ${n}`;
}

function renderTeamPage() {
  const host = document.getElementById("team-page");
  if (!host) return;
  const st = _teamState;
  // THE LOADING LINE IS FOR A PAGE THAT IS NOT DRAWN YET. With a team
  // already on screen and only the opponent changing, replacing it with
  // one paragraph is what collapsed the document and lost his place.
  if (!st.data) {
    host.innerHTML = `<p class="loading">Reading ${
      escapeHtml(st.team || "the team")}’s finals…</p>`;
    return;
  }
  const d = st.data;
  if (d.error) {
    host.innerHTML = `<div class="warning">${icon("warn")} ${escapeHtml(d.error)}</div>`;
    return;
  }
  if (d.no_finals) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <div class="es-title">No finished games ingested for this league</div>
      <div class="es-sub">Team history is built from finals this site has
        already loaded. Nothing has been ingested for
        ${escapeHtml((LEAGUE_LABEL[d.sport] || d.sport || "").toUpperCase())} here,
        so there is no record to show — which is a gap in our data rather
        than in the team’s.</div></div>`;
    return;
  }
  if ((d.resolved || []).length) {
    host.innerHTML = `<div class="section-title">Which one?
      <span class="sub">— “${escapeHtml(d.query || st.team)}” is more than
      one team, so this asks rather than picking.</span></div>
      <div class="std-chips">${d.resolved.map((r) => `<button type="button"
        class="al-cat" data-team-sport="${escapeAttr(d.sport)}"
        data-team-open="${escapeAttr(r.team)}">
        ${escapeHtml(r.name || r.team)}</button>`).join("")}</div>`;
    return;
  }
  if (!d.profile) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <div class="es-title">No team matched “${escapeHtml(st.team)}”</div>
      <div class="es-sub">Try the city, the nickname or the abbreviation —
        “Los Angeles Rams”, “Rams” or “LA”.</div></div>`;
    return;
  }
  const p = d.profile;
  /* ESPN'S SHAPE (Ethan, 2026-09-24, with ESPN's Packers page beside
     ours: "I like all the data we included but I want it too be layed
     out like the espn and include all this information and have tabs for
     each page"). A header — crest, city over nickname, the season's
     record and where it stands — then a strip of tabs, one section each.

     The sections are built here in the order they were always drawn, and
     the strip decides which one shows. That order still matters where it
     did: the versus picker and its table come first, because a section
     nobody can reach has not shipped — on a tab it is one tap from the
     top of the page, not several screens down it. */
  const tab = TEAM_TABS.some(([k]) => k === st.tab) ? st.tab : "home";
  _teamInj = teamInjuryMap(d, p);
  const vsTab = `
    ${d.vs_unknown ? `<div class="warning">${icon("warn")} No team here
      matched “${escapeHtml(d.vs_unknown)}” — the history below is
      ${escapeHtml(p.name)} on its own.</div>` : ""}
    ${teamOppPickerHTML(d, _teamState.vs)}
    ${st.loading
      ? `<p class="loading">Reading ${escapeHtml(p.name || p.team)}’s
          record against them…</p>`
      : teamH2HHTML(d.head_to_head, d.sport)}`;
  const historyTab = `${teamSeasonsHTML(p)}`;
  const statsTab = `${teamStatsHTML(d.stats, d.sport)}`;
  const rosterTab = `${teamSquadHTML(d.squad, d.sport)}`;
  const body = {
    home: () => teamHomeHTML(d, p),
    stats: () => statsTab || teamEmptyTab("No stats yet", "No player stats on file for this team yet."),
    schedule: () => teamScheduleHTML(d, p),
    roster: () => (teamLiveRosterHTML(d) || rosterTab) ? (teamLiveRosterHTML(d) || rosterTab) + teamInjKeyHTML(d.sport)
      : teamEmptyTab("No roster yet", "No one has played for this team in the games we hold yet."),
    depth: () => teamDepthHTML(d),
    injuries: () => teamInjuriesHTML(d, p),
    vs: () => vsTab,
    history: () => historyTab,
  }[tab]();
  host.innerHTML = `
    ${teamHeaderHTML(d, p)}
    <nav class="tm-tabs" role="tablist" aria-label="${escapeAttr(p.name || p.team)} sections">
      ${TEAM_TABS.map(([k, label]) => `<button type="button" role="tab" class="tm-tab${
        k === tab ? " on" : ""}" aria-selected="${k === tab}" data-team-tab="${k}">${label}</button>`).join("")}
    </nav>
    <div class="tm-body" role="tabpanel">${body}</div>
    ${["home", "schedule", "vs", "history"].includes(tab) ? `<p class="rank-help">Built from the finished games this site has
      ingested${(p.seasons || []).length
        ? ` — ${p.seasons[p.seasons.length - 1].season} to ${p.seasons[0].season}`
        : ""}. Not a projection and not a pick: a record.</p>` : ""}`;
  // The schedule strip opens on the next game, the way ESPN's does.
  const strip = host.querySelector(".tm-strip");
  const next = strip && strip.children[Number(strip.dataset.start) || 0];
  if (next) strip.scrollLeft = Math.max(0, next.offsetLeft - strip.offsetLeft - next.offsetWidth);
  const on = host.querySelector(".tm-tab.on");
  if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "center" });
  if (["home", "injuries", "depth", "roster"].includes(tab)) teamNeedsBoards(d.sport);
}

/* The team page's tabs, in ESPN's order, then the two that are ours. */
const TEAM_TABS = [["home", "Home"], ["stats", "Stats"], ["schedule", "Schedule"],
  ["roster", "Roster"], ["depth", "Depth Chart"], ["injuries", "Injuries"],
  ["vs", "Versus"], ["history", "History"]];

function teamEmptyTab(title, msg) {
  return `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
    <div class="es-title">${escapeHtml(title)}</div><div class="es-sub">${escapeHtml(msg)}</div></div>`;
}

/* The standings and injury boards are fetched once per league and the
   page redrawn when they land — they are not in the team answer. */
const _teamBoardsAsked = {};
function teamNeedsBoards(sport) {
  if (!sport || _teamBoardsAsked[sport]) return;
  _teamBoardsAsked[sport] = true;
  Promise.all([loadStandings(sport), loadInjuryBoard()]).then(() => {
    if (state.view === "team" && _teamState.sport === sport) renderTeamPage();
  }).catch(() => {});
}

/* This team's row in its league's standings, and the group it sits in. */
function teamStanding(sport, team) {
  const t = _standingsCache[sport] || {};
  for (const g of t.groups || []) {
    const r = (g.teams || []).find((x) => x && x.team === team);
    if (r) return { row: r, group: String(g.label || [g.conference, g.division].filter(Boolean).join(" ")).trim() };
  }
  return null;
}

/* Crest, "GREEN BAY" over "PACKERS", the season's record and standing. */
function teamHeaderHTML(d, p) {
  const full = p.name || d.name || p.team;
  const meta = teamsForSport(d.sport)[p.team] || {};
  const nick = meta.nick && full.endsWith(meta.nick) ? meta.nick : full.split(" ").slice(-1)[0];
  const city = full.endsWith(nick) ? full.slice(0, full.length - nick.length).trim() : "";
  const season = (p.seasons || [])[0];
  const std = teamStanding(d.sport, p.team);
  const record = (std && std.row.record) || (season && season.record) || "";
  const where = std && std.row.rank && std.group ? `${ordinal(std.row.rank)} in ${std.group}` : "";
  return `<header class="tm-head">
    <span class="tm-crest">${teamMarkIn(d.sport, p.team, 64)}</span>
    <div class="tm-id">
      ${city ? `<div class="tm-city">${escapeHtml(city)}</div>` : ""}
      <h2 class="tm-nick">${escapeHtml(nick)}</h2>
      <div class="tm-rec">${escapeHtml([(LEAGUE_LABEL[d.sport] || d.sport || "").toUpperCase(),
        record, where].filter(Boolean).join(" · "))}</div>
    </div>
    <div class="tm-acts">${d.sport === state.sport ? favBtn(p.team) : ""}</div>
  </header>`;
}

/* One game as a schedule cell or row: who, where, and the result or when. */
function teamGameWho(d, g) {
  return `${g.at_home ? "vs" : "@"} ${teamMarkIn(d.sport, g.opponent, 20)}`;
}
function teamGameResult(g) {
  if (!g.final) return "";
  const cls = g.result === "W" ? "tm-w" : g.result === "L" ? "tm-l" : "";
  return `<b class="${cls}">${g.result}</b> ${Math.round(g.points_for)}-${Math.round(g.points_against)}`;
}
/* The NFL's playoff rounds, by the week number nflverse files them under
   (the 18-week seasons, 2021 on). */
const NFL_ROUNDS = { 19: "Wild Card", 20: "Divisional", 21: "Conference", 22: "Super Bowl" };
function teamGameWhen(d, g) {
  if (d.sport === "nfl" || d.sport === "cfb") {
    // Stored as "001" so text sorts as numbers; read as "Wk 1".
    const wk = Number(g.period);
    if (!g.period) return "";
    if (!Number.isFinite(wk)) return String(g.period);
    if (d.sport === "nfl" && Number(g.season) >= 2021 && NFL_ROUNDS[wk]) return NFL_ROUNDS[wk];
    return `Wk ${wk}`;
  }
  return g.date ? String(g.date).slice(5).replace("-", "/") : "";
}
function teamGameDate(g) {
  return g.date ? String(g.date).slice(5).replace(/^0/, "").replace("-", "/").replace("/0", "/") : "";
}

/* Tonight's game on the board, if this team is on it. */
function teamOnBoard(d, p) {
  if (d.sport !== state.sport) return null;
  return ((state.data || {}).games || []).find((g) => g && (g.home === p.team || g.away === p.team)) || null;
}

/* THE DOOR ON A SCHEDULE GAME. Ethan, 2026-09-25, the Jaguars page with
   the schedule strip circled: "we should be able to click on these games,
   and then it'll take you to, like, the live game page for this game where
   it shows all the data." The game on tonight's board opens its game page
   — the same door as the "On tonight's board" card. A game not on the
   board (a final from an earlier week, a week still to come) has no game
   page yet, so it opens the opponent, as before. */
function teamGameDoor(d, p, g) {
  const b = teamOnBoard(d, p);
  const other = b ? (b.home === p.team ? b.away : b.home) : null;
  const same = b && !g.final && g.opponent === other
    && (!g.date || !b.date || String(g.date).slice(0, 10) === String(b.date).slice(0, 10));
  return same ? ` data-team-game="${escapeAttr(gameId(b))}" title="Game page"`
    : ` data-team-sport="${escapeAttr(d.sport)}" data-team-open="${escapeAttr(g.opponent)}" title="${escapeAttr(teamNameIn(d.sport, g.opponent))}"`;
}

function teamHomeHTML(d, p) {
  const games = ((d.schedule || {}).games) || [];
  const next = games.findIndex((g) => !g.final);
  const strip = games.length ? `<div class="section-title">${escapeHtml(String((d.schedule || {}).season || ""))} Schedule
      <button type="button" class="btn-quiet tm-more" data-team-tab="schedule">Full schedule →</button></div>
    <div class="tm-strip" data-start="${next < 0 ? games.length - 1 : next}">${games.map((g, i) => `
      <button type="button" class="tm-cell${i === next ? " next" : ""}"${teamGameDoor(d, p, g)}>
        <span class="tm-cell-d">${escapeHtml(teamGameDate(g) || teamGameWhen(d, g))}</span>
        <span class="tm-cell-o">${teamGameWho(d, g)}</span>
        <span class="tm-cell-r">${g.final ? teamGameResult(g) : escapeHtml(teamGameWhen(d, g) || "TBD")}</span>
      </button>`).join("")}</div>` : "";
  const g = teamOnBoard(d, p);
  const tonight = g ? `<button type="button" class="card tm-next" data-team-game="${escapeAttr(gameId(g))}">
      <span class="tm-next-k">On tonight’s board</span>
      <span class="tm-next-g">${teamMarkIn(d.sport, g.away, 22)} ${escapeHtml(teamNameIn(d.sport, g.away))}
        <span class="gp-at">@</span> ${teamMarkIn(d.sport, g.home, 22)} ${escapeHtml(teamNameIn(d.sport, g.home))}</span>
      <span class="tm-next-m">${escapeHtml([whenLabel(g.date, g.kickoff),
        g.total != null ? `O/U ${Number(g.total).toFixed(1)}` : "",
        g.favorite && g.spread != null ? `${teamNameIn(d.sport, g.favorite)} −${Math.abs(g.spread).toFixed(1)}` : ""]
        .filter(Boolean).join(" · "))} · Game page →</span></button>` : "";
  const s = (p.seasons || [])[0];
  const tile = (k, v, note) => v == null || v === "" ? "" : `<div class="metric"><div class="k">${k}</div>
      <div class="v">${escapeHtml(String(v))}</div>${note ? `<div class="tm-sub">${escapeHtml(note)}</div>` : ""}</div>`;
  const of = (r) => (r && s.teams_ranked ? `${ordinal(r)} of ${s.teams_ranked}` : "");
  const glance = s ? `<div class="section-title">${escapeHtml(String(s.season))} at a glance</div>
    <div class="metrics tm-glance">
      ${tile("Record", s.record)}
      ${tile("Scored / game", s.pf_per_game, of(s.offense_rank))}
      ${tile("Allowed / game", s.pa_per_game, of(s.defense_rank))}
      ${s.ats_w + s.ats_l + s.ats_p ? tile("Against the spread", `${s.ats_w}-${s.ats_l}${s.ats_p ? "-" + s.ats_p : ""}`) : ""}
      ${s.over + s.under + s.ou_p ? tile("Over / under", `${s.over}-${s.under}${s.ou_p ? "-" + s.ou_p : ""}`) : ""}
    </div>` : "";
  const leaders = teamLeadersHTML(d.stats);
  const hurt = teamInjuryRows(d, p);
  const inj = hurt.length ? `<div class="section-title">Injuries
      <button type="button" class="btn-quiet tm-more" data-team-tab="injuries">All ${hurt.length} →</button></div>
    <div class="card tm-list">${hurt.slice(0, 4).map(teamInjuryRowHTML).join("")}</div>` : "";
  const last = games.filter((x) => x.final).slice(-5).reverse();
  const recent = last.length ? `<div class="section-title">Last ${last.length}</div>
    <div class="card tm-list">${last.map((x) => teamScheduleRowHTML(d, x, p)).join("")}</div>` : "";
  const h = d.head_to_head;
  const vsCard = h && (h.games || []).length ? `<button type="button" class="card tm-next" data-team-tab="vs">
      <span class="tm-next-k">Against the ${escapeHtml(teamNameIn(d.sport, h.opponent))}</span>
      <span class="tm-next-g">${escapeHtml(teamRecordLine(h.summary).replace(/<[^>]+>/g, ""))}</span>
      <span class="tm-next-m">${h.games.length} meeting${h.games.length === 1 ? "" : "s"} on file · last: ${
        teamGameResult({ ...h.games[0], final: true })} · every meeting →</span></button>` : "";
  const out = [strip, tonight, vsCard, glance, leaders ? `<div class="section-title">Leaders</div>${leaders}` : "", inj, recent].join("");
  return out || teamEmptyTab("Nothing yet this season", "Nothing on file for this team this season yet.");
}

function teamScheduleRowHTML(d, g, p) {
  const line = g.line != null ? `${g.line > 0 ? "+" : ""}${g.line}` : "";
  const bits = g.final
    ? [line ? `${line} ${g.covered === true ? "covered" : g.covered === false ? "missed" : g.covered === "push" ? "push" : ""}`.trim() : "",
       g.ou ? `${g.ou} ${g.total}` : ""]
    : [line ? `line ${line}` : "", g.total != null ? `total ${g.total}` : ""];
  const door = p ? teamGameDoor(d, p, g)
    : ` data-team-sport="${escapeAttr(d.sport)}" data-team-open="${escapeAttr(g.opponent)}"`;
  return `<button type="button" class="tm-row"${door}>
    <span class="tm-row-w">${escapeHtml(teamGameWhen(d, g))}<small>${escapeHtml(teamGameDate(g))}</small></span>
    <span class="tm-row-o">${g.at_home ? "vs" : "@"} ${teamMarkIn(d.sport, g.opponent, 20)}
      ${escapeHtml(teamNameIn(d.sport, g.opponent))}</span>
    <span class="tm-row-r">${g.final ? teamGameResult(g) : "<span class=\"tm-up\">Upcoming</span>"}
      <small>${escapeHtml(bits.filter(Boolean).join(" · "))}</small></span>
  </button>`;
}

/* EVERY SEASON ON FILE (Ethan, 2026-09-28, on the Bears' schedule:
   "Since we have 2021-2026 stats, we should be able too cycle from 2021 -
   2026 here"). The answer carries `seasons`; a chip fetches that one
   season's schedule alone (`only=schedule`) and keeps it, so flipping
   back is instant. The current season stays `d.schedule` — the Home tab's
   strip reads it. */
function teamSchedFor(d) {
  const st = _teamState;
  const pick = st.schedSeason;
  if (pick && (st.schedCache || {})[pick]) return st.schedCache[pick];
  return d.schedule || {};
}

function teamSeasonChipsHTML(d, sch) {
  const seasons = ((d.schedule || {}).seasons || []).slice();
  if (seasons.length < 2) return "";
  const on = Number(sch.season);
  return `<div class="std-chips tm-seasons" role="group" aria-label="Season">${seasons.map((y) =>
    `<button type="button" class="al-cat${Number(y) === on ? " on" : ""}" aria-pressed="${Number(y) === on}"
      data-team-season="${escapeAttr(String(y))}">${escapeHtml(String(y))}</button>`).join("")}</div>`;
}

function teamScheduleHTML(d, p) {
  const sch = teamSchedFor(d);
  const games = sch.games || [];
  const chips = teamSeasonChipsHTML(d, _teamState.schedLoading ? { season: _teamState.schedLoading } : sch);
  if (_teamState.schedLoading) {
    return `${chips}<p class="loading">Reading ${escapeHtml(String(_teamState.schedLoading))}…</p>`;
  }
  if (!games.length) {
    return chips + teamEmptyTab("No schedule yet", sch.failed
      ? `Couldn’t read ${sch.season} just now — tap it again.`
      : `No ${sch.season ? `${sch.season} ` : ""}schedule on file for this team yet.`);
  }
  const done = games.filter((g) => g.final);
  const w = done.filter((g) => g.result === "W").length, l = done.filter((g) => g.result === "L").length;
  const past = Number(sch.season) !== Number((d.schedule || {}).season);
  return `${chips}<div class="section-title">${escapeHtml(String(sch.season || ""))} Schedule
      <span class="sub">— ${w}-${l}${done.length - w - l ? `-${done.length - w - l}` : ""} in the games ${past ? "played that season" : "played"};
      the line is ${escapeHtml(teamNameIn(d.sport, p.team))}${/s$/i.test(teamNameIn(d.sport, p.team)) ? "’" : "’s"} own;
      ${past ? "each row opens the opponent." : "the game on tonight’s board opens its game page, every other row opens the opponent."}</span></div>
    <div class="card tm-list">${games.map((g) => teamScheduleRowHTML(d, g, p)).join("")}</div>`;
}

/* WHO IS ON THE TEAM TODAY, the way ESPN's roster tab lays it out
   (Ethan, 2026-10-03: "remember how I had you do it when you search a
   team ... the ESPN looking page with the depth chart and the injuries
   and the roster ... I want every single sport to have the same thing").
   The league's live roster board — the NHL's own feed, ESPN's per-club
   rosters for basketball and college, the league's for baseball, the
   players file for the NFL — grouped by position, with the bio columns
   the feed carries and the injury letter beside each name. A column no
   player on this club has is left out. */
const TEAM_ROSTER_COLS = [["number", "#"], ["age", "Age"], ["height", "Ht"],
  ["weight", "Wt"], ["shoots", "Shot"], ["college", "College"], ["birthplace", "Birthplace"]];
function teamLiveRosterHTML(d) {
  const r = d.roster;
  const players = ((r || {}).players || []).filter((p) => p && p.player);
  if (!players.length) return "";
  const cols = TEAM_ROSTER_COLS.filter(([k]) => players.some((p) => p[k] != null && p[k] !== ""));
  const groups = [];
  for (const p of players) {
    const pos = p.position || "—";
    let g = groups.find((x) => x.pos === pos);
    if (!g) groups.push(g = { pos, rows: [] });
    g.rows.push(p);
  }
  const src = ({ league: "the league’s own roster feed", roster: "ESPN’s published rosters",
    appearances: "who has played in the games we hold" })[r.source] || "the published roster";
  return `<div class="section-title">Roster · ${players.length} players
      <span class="sub">— from ${escapeHtml(src)}${r.generated_at
        ? `, updated ${escapeHtml(String(r.generated_at).replace("T", " ").slice(0, 16))}` : ""}.
      Tap a name for his own page.</span></div>
    ${groups.map((g) => `<div class="section-title minor">${escapeHtml(g.pos)}</div>
      <div class="rank-scroll"><table class="rank-table"><thead><tr><th>Name</th>${
        cols.map(([, lab]) => `<th>${escapeHtml(lab)}</th>`).join("")}<th>Status</th></tr></thead><tbody>
        ${g.rows.map((p) => `<tr class="tst-row" tabindex="0" role="link"
            data-player-page="${escapeAttr(slugify(p.player))}">
          <td class="rank-name">${escapeHtml(p.player)}${teamInjMark(p.player)}</td>
          ${cols.map(([k]) => `<td>${p[k] != null && p[k] !== "" ? escapeHtml(String(p[k])) : "—"}</td>`).join("")}
          <td>${p.status ? escapeHtml(p.status) : (p.unavailable ? "Out" : "Active")}</td>
        </tr>`).join("")}
      </tbody></table></div>`).join("")}`;
}

/* The published chart where there is one (the NFL's, as filed); hockey
   and basketball read the club's live roster ordered by ice time or
   minutes over each man's newest games; every other league reads the
   order measured from the games played — and says which it is. */
function teamDepthHTML(d) {
  const pub = d.depth && (d.depth.positions || []).length ? d.depth : null;
  const rows = pub ? pub.positions.map((x) => ({ position: x.position, names: x.players || [] }))
    : (((d.squad || {}).positions) || []).map((x) => ({ position: x.position,
        names: (x.players || []).map((w) => w.player) }));
  if (!rows.length) return teamEmptyTab("No depth chart yet", "No depth chart on file for this team yet.");
  const cols = Math.min(4, Math.max(...rows.map((r) => r.names.length)));
  return `<div class="section-title">Depth chart
      <span class="sub">— ${pub && pub.source === "usage"
        ? `today’s roster, ordered by ${pub.market === "toi" ? "ice time" : "minutes"} a game over each player’s last ${
            pub.window} games — the lines the coach actually sends out, since no club publishes a chart`
        : pub ? `as the team filed it${pub.as_of ? `, ${escapeHtml(String(pub.as_of))}` : ""}`
        : "ordered by who has actually played: games first, then the position’s main stat"}.</span></div>
    <div class="card tm-depth"><table class="rank-table"><thead><tr><th>Pos</th>${
      Array.from({ length: cols }, (_x, i) => `<th>${ordinal(i + 1)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="tm-pos">${escapeHtml(r.position)}</td>${
        Array.from({ length: cols }, (_x, i) => r.names[i]
          ? `<td><button type="button" class="tm-name" data-player-page="${escapeAttr(slugify(r.names[i]))}">${
              escapeHtml(r.names[i])}</button>${teamInjMark(r.names[i])}</td>` : "<td></td>").join("")}</tr>`).join("")}
    </tbody></table></div>
    ${teamLinesHTML(pub && pub.lines)}
    ${teamInjKeyHTML(d.sport)}`;
}

/* Hockey's lines and pairs, read off the club's newest shift charts
   (engine/nhl/lines): who actually played together, with how much of
   their ice they shared — a settled line reads high, a shuffled one low. */
function teamLinesHTML(ln) {
  if (!ln || !((ln.forwards || []).length || (ln.defence || []).length)) return "";
  const grp = (rows, tag) => rows.map((g, i) => `<tr><td class="tm-pos">${tag}${i + 1}</td>${
    (g.players || []).map((n) => `<td><button type="button" class="tm-name" data-player-page="${
      escapeAttr(slugify(n))}">${escapeHtml(n)}</button>${teamInjMark(n)}</td>`).join("")}${
    tag === "D" ? "<td></td>" : ""}<td class="mini">${Math.round(Number(g.together || 0) * 100)}%</td></tr>`).join("");
  return `<div class="section-title">Lines and pairs
      <span class="sub">— who played together, off the club’s last ${ln.games || 1} game${
        (ln.games || 1) === 1 ? "" : "s"} of shift charts${ln.as_of ? ` (as of ${escapeHtml(String(ln.as_of))})` : ""};
      the last column is how much of their ice they shared.</span></div>
    <div class="card tm-depth"><table class="rank-table"><thead><tr><th>Unit</th><th>Skater</th><th></th><th></th><th>Together</th></tr></thead><tbody>
      ${grp(ln.forwards || [], "F")}${grp(ln.defence || [], "D")}
    </tbody></table></div>`;
}

/* The injury board's rows for this team — ESPN files them under the
   full name ("Green Bay Packers"). */
function teamInjuryRows(d, p) {
  const rows = (((_injBoard || {}).sports) || {})[d.sport] || [];
  const want = ffNorm(p.name || d.name || "");
  const nick = ffNorm((teamsForSport(d.sport)[p.team] || {}).nick || "");
  return rows.filter((r) => r && !isReturnRow(r) && (r.team === p.team
    || (want && ffNorm(r.team || "") === want)
    || (nick && want && ffNorm(r.team || "").endsWith(nick) && want.endsWith(nick))));
}
/* ESPN'S LETTER BESIDE THE NAME (Ethan, 2026-09-24, on the depth chart:
   "make sure we indicate if that player is out or questionable or on ir
   … Put a Q or O or IR next too the names in red"). The designation off
   the same injury board the Injuries tab lists, keyed by name, so the
   letter and the report cannot disagree. A status with no short form
   (an "Active" return row) marks nothing. */
let _teamInj = new Map();
const TEAM_INJ_MARKS = [[/injured reserve|^ir\b|\bir$/i, "IR"], [/physically unable|\bpup\b/i, "PUP"],
  [/non-football|\bnfi\b/i, "NFI"], [/suspen/i, "SUSP"], [/\bil\b|injured list|\d+-day/i, "IL"],
  [/\bout\b/i, "O"], [/doubtful/i, "D"], [/questionable/i, "Q"], [/day-to-day/i, "DTD"]];
function teamInjMarkOf(status) {
  const hit = TEAM_INJ_MARKS.find(([re]) => re.test(String(status || "")));
  return hit ? hit[1] : "";
}
/* THE KEY (Ethan, 2026-09-24: "create like a key section … so people
   will know what the letters mean"). The letters a league actually uses,
   in the red they are drawn in, under the chart and the roster. */
const TEAM_INJ_KEY = {
  football: [["Q", "Questionable"], ["D", "Doubtful"], ["O", "Out"], ["IR", "Injured reserve"],
             ["PUP", "Physically unable to perform"], ["NFI", "Non-football injury"], ["SUSP", "Suspended"]],
  other: [["DTD", "Day-to-day"], ["Q", "Questionable"], ["D", "Doubtful"], ["O", "Out"],
          ["IL", "Injured list"], ["SUSP", "Suspended"]],
};
function teamInjKeyHTML(sport) {
  const keys = TEAM_INJ_KEY[sport === "nfl" || sport === "cfb" ? "football" : "other"];
  return `<div class="tm-key" role="note" aria-label="Injury key">
    <span class="tm-key-k">Key</span>
    ${keys.map(([k, v]) => `<span class="tm-key-i"><abbr class="tm-inj">${k}</abbr> ${escapeHtml(v)}</span>`).join("")}
    <span class="tm-key-note">From the league’s injury report. Tap and hold a letter for the injury.</span>
  </div>`;
}

function teamInjuryMap(d, p) {
  const m = new Map();
  for (const r of teamInjuryRows(d, p)) {
    const k = teamInjMarkOf(r.status);
    if (k && r.player) m.set(ffNorm(r.player), { mark: k, status: r.status, injury: r.injury || "" });
  }
  return m;
}
function teamInjMark(player) {
  const hit = _teamInj.get(ffNorm(player || ""));
  return hit ? ` <abbr class="tm-inj" title="${escapeAttr([hit.status, hit.injury].filter(Boolean).join(" — "))}">${
    hit.mark}</abbr>` : "";
}

function teamInjuryRowHTML(r) {
  return `<button type="button" class="tm-row" data-player-page="${escapeAttr(slugify(r.player || ""))}">
    <span class="tm-row-o">${escapeHtml(r.player || "")}<small>${escapeHtml(r.pos || r.position || "")}</small></span>
    <span class="tm-row-r"><b style="color:${injTone(r.status)}">${escapeHtml(r.status || "")}</b>
      <small>${escapeHtml([r.injury, r.return_date ? `return ${r.return_date}` : ""].filter(Boolean).join(" · "))}</small></span>
  </button>`;
}
function teamInjuriesHTML(d, p) {
  if (!_injBoard) return `<p class="loading">Reading the injury report…</p>`;
  const rows = teamInjuryRows(d, p);
  if (!rows.length) return teamEmptyTab("No injuries listed", `Nobody on ${p.name || p.team}’s injury report right now.`);
  return `<div class="section-title">Injury report
      <span class="sub">— ${rows.length} listed${_injBoard.generated_at
        ? `, as of ${escapeHtml(formatStamp(_injBoard.generated_at))}` : ""}.</span></div>
    <div class="card tm-list">${rows.map(teamInjuryRowHTML).join("")}</div>`;
}

/* One box that answers the only question that matters on this page: "so
   what are you telling me to DO?" The answer is driven by the measured
   record, with the promotion bar stated up front — no vibes. */
function pmSignalProven(v) {
  return !!(v && v.graded >= 100 && v.z >= 2 && v.roi > 0);
}

function intelVerdict(v) {
  const pctv = pct;
  const body = pmSignalProven(v)
    ? `<div style="font-weight:800;font-size:var(--fs-xl);color:var(--good)">${icon('check')} The signal has earned
         recommendation status</div>
       <p style="margin:8px 0 0">Graded flags beat their entry prices over ${v.graded} resolutions
       (hit ${pctv(v.hit_rate)} vs ${pctv(v.avg_implied)} implied, ${v.roi >= 0 ? "+" : ""}${pctv(v.roi)} ROI,
       z ${v.z}). Following a fresh LIVE flag below — same side, at or better than the flagged
       entry price — is now a recommended play, sized small (flat 0.1u).</p>`
    : `<div class="pmx-verdict-t"><span class="pmx-info" aria-hidden="true">i</span>What we recommend right now: <span>nothing — watch, don’t bet</span></div>
       <p style="margin:8px 0 0">This page detects large anomalous trades ("informed flow") and
       <b>paper-tracks every flag</b> to find out whether following that money actually wins.
       ${v && v.graded
         ? `So far, over <b>${v.graded}</b> graded flags: hit ${pctv(v.hit_rate)} vs ${pctv(v.avg_implied)}
            implied, ${v.roi >= 0 ? "+" : ""}${pctv(v.roi)} flat-stake ROI, z ${v.z} — statistically
            indistinguishable from the market price. Not enough to bet on.`
         : `No flags have resolved yet, so there is no evidence either way.`}</p>
       <p style="margin:6px 0 0;color:var(--text-mute)">The promotion bar is fixed and public:
       <b>100+ graded flags, z ≥ 2, positive ROI</b>. If the signal (or one wallet, or one
       score band) clears it, this box flips to a recommendation. Until then, every flag below
       is a tracked observation — not a play.</p>`;
  return `<div class="card pmx-verdict${pmSignalProven(v) ? " proven" : ""}">${body}</div>`;
}

/* The report card's tiles in the render's dress: a gold badge with its
   drawn mark, the label in small caps, the number big. */
function pmxBadgeTile(kind, label, value, sub) {
  const g = {
    doc: `<path d="M8 4h11l5 5v19H8z M19 4v5h5 M12 15h8 M12 19h8 M12 23h5" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`,
    target: `<circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" stroke-width="2"/>
      <circle cx="16" cy="16" r="6" fill="none" stroke="currentColor" stroke-width="2"/>
      <circle cx="16" cy="16" r="1.8" fill="currentColor"/><path d="M16 16 26 6 M22 6h4v4" fill="none"
      stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    bars: `<rect x="7" y="18" width="4" height="8" rx="1" fill="currentColor"/><rect x="14" y="13" width="4"
      height="13" rx="1" fill="currentColor"/><rect x="21" y="7" width="4" height="19" rx="1" fill="currentColor"/>`,
    sigma: `<path d="M23 7H9l8 9-8 9h14" fill="none" stroke="currentColor" stroke-width="2.4"
      stroke-linejoin="round" stroke-linecap="round"/>`,
  }[kind] || "";
  return `<div class="tile pmx-btile"><span class="pmx-badge" aria-hidden="true"><svg viewBox="0 0 32 32">${g}</svg></span>
    <div><div class="k">${label}</div><div class="v">${value}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div></div>`;
}

function intelReportCard(v) {
  const head = `<div class="pmx-sechead"><h2>Flag report card <details class="pmx-why"><summary>why?↑</summary>
      <p>Do our flags actually win? Every flag is stored and graded when its market resolves.
      Published, not promised.</p></details></h2></div>`;
  if (!v || !v.graded) {
    return `${head}<div class="card">${panelEmpty("No graded flags yet — flags settle when their markets resolve, so this fills as resolutions land. The recording started the moment the flow feed first ran.")}</div>`;
  }
  const pctv = pct;
  const zColor = v.z >= 1 ? "var(--good)" : v.z <= -1 ? "var(--bad)" : "var(--text)";
  const bandRows = (v.by_score || []).map((b) => `
    <div class="dl-row pm-band">
      <span class="dl-main"><strong>Score ${escapeHtml(b.band)}</strong></span>
      <span class="dl-num">${b.wins}-${b.n - b.wins}</span>
      <span class="dl-num implied">${pctv(b.hit_rate)} vs ${pctv(b.avg_implied)} <small>implied</small></span>
      <span class="dl-num strong ${b.roi >= 0 ? "pos" : "neg"}">${b.roi >= 0 ? "+" : ""}${pctv(b.roi)} ROI</span>
    </div>`).join("");
  const bands = bandRows ? `<div class="dl-row pm-band pm-band-head" aria-hidden="true">
      <span class="dl-main">Score band</span><span class="dl-num">Record</span>
      <span class="dl-num implied">Hit rate vs implied</span><span class="dl-num strong">Flat-stake ROI</span>
    </div>${bandRows}` : "";
  const wallets = (v.wallets || []).map((w) => `
    <div class="dl-row pm-wallet">
      <span class="dl-main"><span class="wallet">${extLink(
        `https://polymarket.com/profile/${w.wallet}`,
        escapeHtml(traderLabel(w)))}</span></span>
      <span class="dl-num">${w.wins}-${w.n - w.wins}</span>
      <span class="dl-num implied">${pctv(w.hit_rate)} vs ${pctv(w.avg_implied)}</span>
      <span class="dl-num strong" title="calibration z — higher = less like luck">z ${w.z}</span>
    </div>`).join("");
  return `${head}
    <div class="stats pmx-report">
      ${pmxBadgeTile("doc", "Flags graded", v.graded, "")}
      ${pmxBadgeTile("target", "Hit rate", pctv(v.hit_rate), `prices implied ${pctv(v.avg_implied)}`)}
      ${pmxBadgeTile("bars", "Flat-stake ROI", `<span class="${v.roi >= 0 ? "pos" : "neg"}">${v.roi >= 0 ? "+" : ""}${pctv(v.roi)}</span>`, "")}
      ${pmxBadgeTile("sigma", "Calibration z", `<span style="color:${zColor}">${v.z}</span>`, "above 0 = flags beat their price")}
    </div>
    ${bands ? `<div class="card pmx-bands" style="padding:0">${bands}</div>` : ""}
    ${intelWeights(v.weights)}
    ${wallets ? `<div class="section-title">Wallets least like luck
        <span class="sub">— graded flags only, min 3, ranked by calibration z</span></div>
      <div class="card" style="padding:0">${wallets}</div>` : ""}`;
}

/* What each signal is worth, and whether that number was MEASURED.
   The score has always been a sum of assigned weights — 40/30/15/8 for
   the size tiers, 20 for impact, 15 for niche, 25 for a fresh wallet.
   The report card above could grade the total and never a component,
   because a flag only ever recorded its total. It records the breakdown
   now, and engine/pmfit fits each weight against the flags that
   resolved. A signal measured at nothing keeps firing and keeps showing
   here at zero: "we looked and this one does not predict anything" is
   the finding, not a reason to hide the row. */
function intelWeights(w) {
  const head = `<div class="section-title">What each signal is worth
      <span class="sub">— fitted against resolved flags, offset by the price the
      market was already charging. A signal only scores for what it adds.</span></div>`;
  if (!w) return "";
  const pts = w.points || {};
  const keys = Object.keys(pts);
  if (!keys.length) {
    const held = (w.held || []).map((h) =>
      `${escapeHtml(h.key === "*" ? "overall" : h.key)}: ${escapeHtml(h.why || "")}`);
    const why = held.length ? ` ${escapeHtml(held.join("; "))}` : "";
    return `${head}<div class="card">${panelEmpty(
      `Still on the assigned weights — ${plural(w.n || 0, "resolved flag")} ${(w.n || 0) === 1 ? "carries" : "carry"} a `
      + `recorded breakdown so far.${why}`)}</div>`;
  }
  const label = {size: "Position size", impact: "Order-book impact",
                 niche: "Niche market", fresh_wallet: "Fresh wallet"};
  const rows = keys.sort((a, b) => pts[b] - pts[a]).map((k) => `
    <div class="dl-row">
      <span class="dl-main"><strong>${escapeHtml(label[k] || k)}</strong></span>
      <span class="dl-num">${pts[k] ? `${pts[k]} pts` : "no measured edge"}</span>
    </div>`).join("");
  return `${head}
    <div class="card" style="padding:0">${rows}</div>
    ${w.note ? `<div class="subtitle">${escapeHtml(w.note)}</div>` : ""}`;
}

/* ============================================================
   NBA — Scalpy probability engine
   ============================================================ */
/* Where a bout's line opened and where it is now (engine/ufc/moves) —
   the snapshots stored since 2026-08-10, said in one line. Evidence:
   the card's numbers do not move for it. */
function ufcLineHTML(t) {
  return t ? `<div style="margin-top:6px;color:var(--text-mute);font-size:var(--fs-sm)">${icon('clock')} ${escapeHtml(t)}</div>` : "";
}

/* Weigh-in state for one bout. "Not recorded" is drawn as its own thing
   on purpose: it and "made weight" are opposite facts, and a page that
   renders them the same way is the reason KILL IF went unenforced. */
function weighInHTML(wi) {
  if (!wi || (!wi.a && !wi.b)) return "";
  const one = (st) => {
    if (!st) return "";
    const n = escapeHtml(st.name || "?");
    if (st.state === "missed") {
      return `<span class="chip down">${n} ${icon('cross')} ${st.weight} (+${st.over} over)</span>`;
    }
    if (st.state === "made") return `<span class="chip up">${n} ${icon('check')} ${st.weight}</span>`;
    if (st.state === "unknown_division") {
      return `<span class="chip">${n} ${st.weight} · catchweight, no limit</span>`;
    }
    return `<span class="chip">${n} — weigh-in not recorded</span>`;
  };
  return `<div class="chips" style="margin-top:8px">${one(wi.a)}${one(wi.b)}</div>`;
}

/* ============================================================
   Live fight — the body diagram
   ============================================================
   The UFC's broadcast graphic is not a damage model. It is a count of
   significant strikes landed to each target area, and that distinction
   is the whole design: "damage" is a judgement nobody publishes, strikes
   to the head is a number somebody counts. Shaded by SHARE of what a
   fighter has absorbed — the deepest colour is where he is being hit
   most, which is what a viewer actually reads off it.

   The diagram shows what a fighter has TAKEN. His own landed strikes
   appear on his opponent. Getting that backwards would invert the whole
   picture while looking completely normal. */
let _liveTimer = null;

const BODY_REGIONS = [
  ["head", "Head"], ["body", "Body"], ["leg", "Legs"],
];

/* Intensity is a region's count against the HOTTEST region in the fight
   — across both fighters, so the two diagrams are directly comparable.

   Share-of-own-total was the first attempt and it was quietly useless: a
   fighter hit evenly in three places scores ~33% everywhere and comes out
   uniformly mid-red, so a man taking 41 to the head looked like a man
   taking 7 to the leg. Normalising to the fight's peak means the worst
   area on the card is the deepest colour and everything else reads
   against it, which is the comparison a viewer is actually making.

   Zero absorbed is not "safe", it is "nothing landed yet" — so an untouched
   diagram is flat panel colour rather than green. Colour never means good. */
function regionFill(n, peak) {
  if (!peak || n == null) return "var(--panel-3)";
  if (!n) return "var(--panel-3)";
  const a = 0.14 + Math.min(1, n / peak) * 0.76;
  return `rgba(239, 68, 68, ${a.toFixed(3)})`;
}

function bodySVG(absorbed, total, peak) {
  const share = (k) => (total > 0 ? (absorbed[k] || 0) / total : null);
  const seg = (k, d) => `<path d="${d}" fill="${regionFill(absorbed[k] || 0, peak)}"
      stroke="var(--border)" stroke-width="1.2"><title>${escapeHtml(
        BODY_REGIONS.find((r) => r[0] === k)[1])}: ${absorbed[k] || 0} landed${
        total > 0 ? ` (${Math.round((share(k) || 0) * 100)}%)` : ""}</title></path>`;
  return `<svg class="bodyfig" viewBox="0 0 100 200" role="img"
      aria-label="Significant strikes absorbed by target area">
    ${seg("head", "M50 6 c9 0 15 7 15 16 c0 10 -6 18 -15 18 c-9 0 -15 -8 -15 -18 c0 -9 6 -16 15 -16 Z")}
    ${seg("body", "M35 44 c-9 3 -14 9 -16 20 l-4 26 c-1 6 6 8 8 2 l4 -16 l1 34 c0 8 1 14 2 20 h60 c1 -6 2 -12 2 -20 l1 -34 l4 16 c2 6 9 4 8 -2 l-4 -26 c-2 -11 -7 -17 -16 -20 c-6 -2 -12 -3 -25 -3 c-13 0 -19 1 -25 3 Z")}
    ${seg("leg", "M30 132 c-1 22 -2 44 -4 60 c-1 6 12 6 13 0 l7 -44 l7 44 c1 6 14 6 13 0 c-2 -16 -3 -38 -4 -60 Z")}
  </svg>`;
}

function fighterPanelHTML(f, peak) {
  const abs = f.absorbed || {}, total = f.absorbed_total || 0;
  const rows = BODY_REGIONS.map(([k, label]) => {
    const n = abs[k] || 0;
    // The BAR is share of this fighter's own total — "where is he being
    // hit" — while the FIGURE is scaled to the fight's peak — "how hard,
    // compared to the other guy". Two questions, two encodings, and the
    // count on the right is the answer to neither being in doubt.
    const pct = total > 0 ? Math.round((n / total) * 100) : 0;
    return `<div class="lf-region">
      <span class="lf-region-name">${escapeHtml(label)}</span>
      <span class="lf-bar"><span style="width:${pct}%;
        background:${regionFill(n, peak)}"></span></span>
      <span class="lf-region-n">${n}</span>
    </div>`;
  }).join("");
  const t = f.totals || {};
  const chip = (label, v) => (v == null ? "" :
    `<span class="chip">${escapeHtml(label)} ${v}</span>`);
  return `<div class="lf-fighter">
    <div class="lf-name">${escapeHtml(f.name || "—")}${
      f.winner ? ` <span class="chip good">WINNER</span>` : ""}</div>
    ${bodySVG(abs, total, peak)}
    <div class="lf-absorbed">${total} significant strike${total === 1 ? "" : "s"} absorbed</div>
    ${rows}
    <div class="lf-chips">
      ${chip("landed", f.landed_total)}
      ${chip("of", t.sig_attempted)}
      ${chip("TD", t.takedowns)}
      ${chip("KD", t.knockdowns)}
    </div>
  </div>`;
}

function liveBoutHTML(b, stale) {
  const s = b.status || {};
  const badge = s.live
    ? `<span class="chip ${stale ? "warn" : "live"}">${stale ? "STALLED" : "LIVE"}${
        s.round ? ` · R${s.round}` : ""}${s.clock ? ` ${escapeHtml(s.clock)}` : ""}</span>`
    : `<span class="chip">${escapeHtml(s.detail || s.state || "")}</span>`;
  if (!b.has_targets) {
    return `<div class="card lf-card">
      <div class="lf-head">${escapeHtml(b.fighters.map((f) => f.name).join(" vs "))} ${badge}</div>
      <div class="ls-note">This bout is live, but the feed is not publishing
      strikes by target for it — so there is no body diagram to draw. Totals
      appear here as soon as it does. A diagram of zeros would look like a
      fight where nothing has landed, which is a different claim entirely.</div>
    </div>`;
  }
  // The hottest single region across BOTH corners sets the scale, so the
  // two figures can be read against each other rather than each against
  // itself.
  const peak = Math.max(1, ...b.fighters.flatMap(
    (f) => BODY_REGIONS.map(([k]) => (f.absorbed || {})[k] || 0)));
  return `<div class="card lf-card">
    <div class="lf-head">${escapeHtml(b.division || "")} ${badge}</div>
    <div class="lf-pair">${b.fighters.map((f) => fighterPanelHTML(f, peak)).join("")}</div>
  </div>`;
}

async function renderLiveFights(host) {
  if (!host) return false;
  let d = null;
  try {
    const res = await boardFetch("data/ufc_live.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !(d.bouts || []).length) { host.innerHTML = ""; return false; }

  const live = (d.bouts || []).filter((b) => b.status && b.status.live);
  if (!live.length) { host.innerHTML = ""; return false; }

  // Age of the DATA, not of the fetch. A count that last moved 90 seconds
  // ago is 90 seconds old however recently we asked for it, and a smoothly
  // redrawn stale number next to a fight somebody is watching is the worst
  // thing this page could do.
  const built = stampMs(d.generated_at) || 0;
  const ageS = built ? Math.max(0, Math.round((Date.now() - built) / 1000)) : null;
  const stale = ageS != null && ageS > (d.stale_after_s || 75);

  host.innerHTML = `
    <div class="section-title tight">Live now
      <span class="sub">— ${escapeHtml(d.disclaimer || "")}</span></div>
    <div class="lf-age ${stale ? "warn" : ""}">${
      ageS == null ? "" : stale
        ? `${icon('warn')} these numbers last changed ${ageS}s ago — the feed has stopped moving`
        : `updated ${ageS}s ago`}</div>
    ${live.map((b) => liveBoutHTML(b, stale)).join("")}
    ${/* Each card already explains its own missing-target case, so the
          payload-level note would just say it a second time. Keep it only
          when it is telling you something the cards did not. */
      d.note && live.some((b) => b.has_targets)
        ? `<div class="ls-note">${escapeHtml(d.note)}</div>` : ""}`;
  return true;
}

/* The UFC pick's "Why it's likely" (Ethan, 2026-09-24: "Every single bet
   we offer needs too have a why it's likely section"). The card's numbers
   (p_model, p_market, p_final) in plain words: the blended chance, where
   it came from, how the fight is expected to go, and the price. */
function ufcWhyHTML(p, title, odds) {
  const items = [];
  const pf = Number(p.p_final);
  const t = probTier(pf);
  if (Number.isFinite(pf)) {
    items.push(["Our chance", `${wholePct(pf)}${t ? ` — ${t.word}, the ${t.band} band` : ""}.
      ${p.p_model != null && p.p_market != null ? `Our fight model has it at ${wholePct(p.p_model)},
      the market at ${wholePct(p.p_market)}; the chance leans ${Number(p.w) >= 0.5 ? "on our model"
      : "on the market"} (weight ${escapeHtml(String(p.w))}).` : ""}`]);
  }
  const m = p.method || {};
  const ways = [["knockout", m.a_ko], ["submission", m.a_sub], ["decision", m.a_dec]]
    .filter(([, v]) => Number(v) > 0).sort((a, b) => b[1] - a[1]);
  if (ways.length) {
    items.push(["How it gets there", `Most often by ${ways[0][0]} (${wholePct(ways[0][1])})${ways[1]
      ? `, then ${ways[1][0]} (${wholePct(ways[1][1])})` : ""}${m.distance != null
      ? `; the fight goes the distance ${wholePct(m.distance)} of the time` : ""}.`]);
  }
  if ((p.style_notes || []).length) {
    items.push(["The matchup", escapeHtml(p.style_notes.join(" · "))]);
  }
  if (odds != null) {
    items.push(["The price", `${p.book ? `${escapeHtml(p.book)} ` : ""}${escapeHtml(american(odds))}${
      p.break_even != null ? ` needs it to land ${wholePct(p.break_even)} of the time to break even` : ""}${
      Number.isFinite(pf) ? `; we have it at ${wholePct(pf)}` : ""}.`]);
  }
  if (p.thin_data) items.push(["Worth knowing", "Thin data on one of the fighters, so the bar it had to clear was higher."]);
  return whySectionHTML(items, pf, "edge");
}

async function renderUFC() {
  const host = document.getElementById("ufc-body");
  if (!host) return;
  // A live fight refreshes on its own clock — the 60s page cycle is far
  // too slow for something that moves in seconds. The timer is cleared on
  // the way out of the view so it cannot keep polling a page nobody is on.
  let liveHost = document.getElementById("ufc-live");
  if (!liveHost) {
    liveHost = document.createElement("div");
    liveHost.id = "ufc-live";
    host.parentNode.insertBefore(liveHost, host);
  }
  renderLiveFights(liveHost);
  if (_liveTimer) clearInterval(_liveTimer);
  _liveTimer = setInterval(() => {
    if (state.view !== "ufc") { clearInterval(_liveTimer); _liveTimer = null; return; }
    renderLiveFights(liveHost);
  }, 10000);
  // Through paidFetch: gating UFC's pick keys without this would fix
  // the leak by breaking the page for the people who pay for it, which
  // is the mistake /api/<sport>/recommendations made for months.
  const gotU = await fetchJSON(() => paidFetch("ufc.json"), "ufc");
  const d = gotU.data;
  if (!d && gotU.failed) {
    setStandaloneSource("The Odds API MMA events + our fighter dossiers", "UFC", false);
    host.innerHTML = outageHTML("the UFC card", "ufc");
    return;
  }
  if (!d) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("glove", 30)}</div>
      <div class="es-title">No UFC data yet</div>
      <div class="es-sub">The launcher builds the card each refresh once you pull and relaunch.</div></div>`;
    return;
  }
  setStandaloneSource("The Odds API MMA events + our fighter dossiers",
                      `UFC · ${escapeHtml(d.event_date || d.status || "")}`);
  const pctv = pctOr;

  if (d.status !== "card") {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("glove", 30)}</div>
      <div class="es-title">No card in the window</div>
      <div class="es-sub">${escapeHtml(d.note || "")}</div></div>
      <div class="ls-note" style="margin-top:14px">The Scalpy MMA doctrine, ready:
        style beats talent (highest-weight input) · win probability hard-capped at 88% —
        four-ounce gloves mean nobody is safer · method of victory is a JOINT distribution
        that must sum to 100% · durability weighs 1.5× finishing ability · the humility
        clamp kills any 15-point market disagreement · never worse than −300 · no cap on how
        many fights qualify — money is capped instead, and a 13-fight card with zero bets is
        a valid output.</div>`;
    return;
  }

  const methodBar = (m, card) => {
    const segs = [["a_ko", "var(--bad)"], ["a_sub", "var(--plum)"],
                  ["a_dec", "var(--brand)"], ["b_dec", "var(--cyan)"],
                  ["b_sub", "var(--warn)"], ["b_ko", "var(--good)"]];
    return `<div style="display:flex;height:10px;border-radius:var(--radius);overflow:hidden;margin-top:8px"
        title="method distribution — left: pick’s KO/SUB/DEC, right: opponent’s DEC/SUB/KO">
      ${segs.map(([k, c]) => `<span style="width:${(m[k] || 0) * 100}%;background:${c}"></span>`).join("")}
    </div>
    <div style="display:flex;justify-content:space-between;color:var(--text-mute);font-size:var(--fs-xs);margin-top:3px">
      <span>KO ${pctv(m.a_ko)} · SUB ${pctv(m.a_sub)} · DEC ${pctv(m.a_dec)}</span>
      <span>distance ${pctv(m.distance)}${
        /* The duration read (script §1.3, engine/ufc/triangle.py):
           E[minutes] over the front-loaded hazard prior, bent by the
           fight's own profile. Assumed three rounds and SAID — the feed
           has no scheduled-rounds field, so a main event's number is
           knowably conservative rather than silently wrong. */
        card && card.e_minutes
          ? ` · ~${card.e_minutes} min${card.hazard_tilt === "late"
              ? " (late-tilted)" : card.hazard_tilt === "flat"
              ? " (flat hazard)" : ""}${(card.scheduled_rounds || 3) === 3
              ? "" : ` of ${card.scheduled_rounds * 5}`}`
          : ""}</span></div>`;
  };

  /* The bet is no longer always the moneyline. Books derive method props
     off the moneyline, so the distribution routinely finds its edge in a
     market the book barely thought about — the card has to say WHICH. */
  const MARKET_LABEL = { moneyline: "Moneyline", method: "Method",
                         distance: "Distance", fighter_finish: "Finish",
                         round: "Round", exact_round: "Exact round" };
  const shopRow = (c) => `
    <div class="ufc-shop-row">
      <span class="sr-m">${escapeHtml(MARKET_LABEL[c.market] || c.market)}</span>
      <span class="sr-s">${escapeHtml(c.selection)}</span>
      <span class="sr-o">${c.priced ? american(c.odds) : `fair ${american(c.fair_odds)}`}</span>
      <span class="sr-e ${c.priced ? (c.edge >= c.required_edge ? "pos" : "") : "mute"}">${
        c.priced ? `${c.edge >= 0 ? "+" : ""}${(c.edge * 100).toFixed(1)}%` : "shop it"}</span>
    </div>`;
  /* Every market the fight implies — on a pass too: the round prices
     (engine/ufc/rounds) are fair numbers to shop whether or not we bet. */
  const shopList = (p) => {
    const b = (p.market_board || []).filter((c) => c.priced || c.fair_odds);
    return b.length ? `<details class="ufc-shop"><summary>Every market this fight implies (${b.length}) — shop the unpriced ones</summary>
        ${b.map(shopRow).join("")}</details>` : "";
  };

  const pickCard = (p) => {
    const best = p.best_market || {};
    const shown = best.odds != null ? best.odds : p.odds;
    const title = p.selection || `${p.pick} ML`;
    return `
    <article class="card fight-hero" style="--grade-color:var(--good);${fightArtStyle(p)}">
      ${fightEyebrowHTML(p)}
      <div class="card-head">
        <div><div class="player">${escapeHtml(title)}</div>
          <div class="subtitle">${escapeHtml(p.fight)}${p.division ? ` · ${escapeHtml(String(p.division).replace(/_/g, " "))}` : ""} ·
            ${escapeHtml(p.book)} ${american(shown)}</div></div>
        <span class="pm-status" style="color:var(--good)">${escapeHtml(p.grade_label || "")} ${p.grade_score != null ? p.grade_score : ""}</span>
      </div>
      <div class="chips" style="margin:2px 0 8px">
        <span class="chip">${escapeHtml(MARKET_LABEL[p.market] || p.market || "moneyline")} · tier ${p.market_tier || 1}</span>
        <span class="chip cond">${escapeHtml(p.volatility || "MEDIUM")} volatility</span>
        ${p.thin_data ? `<span class="chip" style="color:var(--warn);border-color:currentColor">thin data — higher bar</span>` : ""}
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(p.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(p.p_market)}</div></div>
        <div class="metric primary"><div class="k">p_final (w=${p.w})</div><div class="v">${pctv(p.p_final)}</div></div>
      </div>
      <div class="metrics" style="margin-top:6px">
        <div class="metric"><div class="k">Break-even</div><div class="v">${pctv(p.break_even)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v pos">+${(p.edge * 100).toFixed(1)}pts</div></div>
        <div class="metric primary"><div class="k">EV</div><div class="v pos">+${(p.ev * 100).toFixed(1)}%</div></div>
      </div>
      ${ufcWhyHTML(p, title, shown)}
      ${methodBar(p.method || {}, p)}
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">
        ${(p.style_notes || []).map(escapeHtml).join(" · ")} · hold ${(p.hold * 100).toFixed(1)}%
        · stake ${p.stake_units}u${p.required_edge ? ` · needs ${(p.required_edge * 100).toFixed(1)}%` : ""}</div>
      ${/* The Overhead — see docs/THE_OVERHEAD.md. UFC has a building
            after all: the promotion's own facility uses a 25-foot cage
            and arenas use 30, which the model already prices. Drawn to
            scale, so an Apex card is visibly tighter than an arena card.
            The prose stays underneath it — the drawing is the glance,
            the sentence is the reason. */
        (p.environment && ((p.environment.cage || {}).known || (p.environment.altitude || {}).known))
        ? `<div class="ufc-overhead">${octagon({
             venue: p.environment.venue || "",
             rounds: p.rounds, title_fight: p.title_fight,
             environment: p.environment })}</div>` : ""}
      ${(p.environment && (p.environment.why || []).length)
        ? `<div style="margin-top:6px;color:var(--text-mute);font-size:var(--fs-sm)">${icon('stadium')} ${
            escapeHtml([(p.environment.cage || {}).note, (p.environment.altitude || {}).note]
              .filter(Boolean).join(" · "))}</div>` : ""}
      ${shopList(p)}
      ${weighInHTML(p.weigh_in)}
      ${ufcLineHTML(p.line_note)}
      <div class="warning" style="margin-top:8px">KILL IF: ${escapeHtml(p.kill_if)}</div>
    </article>`;
  };

  // A passed fight still shows both corners — the matchup is the whole
  // point of the page, and an unbet fight you can read is far more useful
  // than a one-line "no bet".
  const fighterCol = fighterColHTML;

  const REASON_STYLE = {
    no_data: ["var(--warn)", "No data"],
    no_dossier: ["var(--warn)", "No dossier"],
    no_price: ["var(--text-mute)", "Awaiting price"],
    clamp_kill: ["var(--bad)", "Clamp kill"],
    gate: ["var(--cyan)", "No edge"],
  };

  const passCard = (m) => {
    const [color, label] = REASON_STYLE[m.reason_code] || ["var(--text-mute)", "Pass"];
    const fs = m.fighters || [];
    return `<article class="card fight-hero" style="--grade-color:${color};${fightArtStyle(m)}">
      ${fightEyebrowHTML(m)}
      <div class="card-head" style="align-items:flex-start">
        <div><div class="player" style="font-size:var(--fs-lg)">${escapeHtml(m.fight)}</div>
          <div class="subtitle">${escapeHtml((m.division || "").replace(/_/g, " ") || "division n/a")}
            ${m.odds ? ` · ${escapeHtml(m.book || "")} ${american(m.odds)}` : ""}</div></div>
        <span class="pm-status" style="color:${color}">${m.near_miss ? "NEAR MISS" : label}</span>
      </div>
      <div class="ufc-vs">
        ${fs.map(fighterCol).join(`<span class="vs-sep">vs</span>`)}
      </div>
      ${m.p_final != null ? `<div class="metrics" style="margin-top:10px">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(m.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(m.p_market)}</div></div>
        <div class="metric primary"><div class="k">p_final</div><div class="v">${pctv(m.p_final)}</div></div>
      </div>` : ""}
      <div style="margin-top:10px;color:var(--text-body);font-size:var(--fs-sm)">
        <span style="color:${color};font-weight:700">Passed:</span> ${escapeHtml(m.why || "")}</div>
      ${shopList(m)}
      ${ufcLineHTML(m.line_note)}
    </article>`;
  };

  const c = d.counts || {};
  const pl = d.pass_list || [];
  const nModeled = pl.filter((m) => ["gate", "clamp_kill"].includes(m.reason_code)).length
    + (d.picks || []).length;
  const nWaiting = pl.filter((m) => m.reason_code === "no_price").length;
  // THE HERO IS ETHAN'S BRANDED RENDER (2026-09-07): the arena dressed
  // in Qellys Book boards, one picture for every card. It replaces the
  // six-night octagon rotation of 2026-08-11 — he circled the old
  // banner and said "use exactly to replace this" — so no hash, no
  // variant, no dependence on the card's identity. The six rotation
  // files stay in variants/ as the ingest tool's contract and are not
  // shown here.
  //
  // The button: the fights are the reason for the page and they sit under
  // three screens of context on a phone. A jump rather than a link: they
  // are on this page, and pretending otherwise would be a lie about where
  // the reader is going.
  //
  // Under the banner, the card's Pick of the Day (engine/potd.fight_lines,
  // 2026-10-14): a fighter's moneyline against Pinnacle's fair, on a BET
  // day only — `potdHeroHTML` draws nothing on any other.
  host.innerHTML = `
    <div class="ufc-hero">
      <img class="ufc-banner" alt="" loading="lazy"
        src="${venueSrc("img/venues/ufc-hero.jpg")}" data-onerr="remove"/>
      <button type="button" class="btn ufc-hero-cta" data-ufc-jump="1">
        View upcoming fights ${icon("rising", 13)}</button>
    </div>
    ${potdHeroHTML(d)}
    <div class="stat-cards">
      ${statCardHTML("calendar", "Card", escapeHtml(d.event_date || "—"),
                     `${c.fights || 0} bout${(c.fights || 0) === 1 ? "" : "s"}`)}
      ${statCardHTML("gem", "Modeled", nModeled,
                     "priced &amp; run through the model")}
      ${statCardHTML("clock", "Awaiting prices", nWaiting,
                     "books post MMA lines late")}
      ${statCardHTML("target", "Picks", c.picks || 0,
                     "every fight that clears the bar")}
      ${statCardHTML("shield", "Card exposure",
                     `${((d.exposure || 0) * 100).toFixed(1)}%`,
                     `of bankroll · cap ${((d.card_cap || 0.08) * 100).toFixed(0)}%, the tightest in the system`)}
    </div>
    ${(d.correlation_flags || []).length ? `<div class="card" style="--tone:var(--warn);margin-bottom:12px">
        <div class="player">${icon('warn')} Correlation on this card</div>
        <ul class="reasons">${(d.correlation_flags || []).map((f) =>
          `<li class="neg">${escapeHtml(f)}</li>`).join("")}</ul></div>` : ""}
    ${d.card_venue && d.card_venue.venue
      ? `<div class="ufc-callout"><span class="co-ico">${icon('stadium', 16)}</span>
          <div><strong>${escapeHtml(d.card_venue.venue)}${
          d.card_venue.city ? `, ${escapeHtml(d.card_venue.city)}` : ""}</strong> — cage size and
          altitude are applied to every method and distance price on this card.</div></div>`
      : `<div class="ufc-callout"><span class="co-ico">${icon('info', 16)}</span>
          <div><strong>Venue not recorded</strong> for this card, so cage size and altitude are
          unchecked — a 25-foot cage raises finishes and altitude pushes them later.
          Every price here is set without them.</div></div>`}
    <div id="ufc-fights"></div>
    ${(() => {
      // Fight-by-fight edge table: every PRICED bout on one scannable
      // grid — model vs market vs break-even, and the verdict with its
      // reason. The per-fight cards below carry the depth.
      const rows = [...(d.picks || []).map((p) => ({ ...p, _pick: true })),
                    ...(d.pass_list || []).filter((m) => m.p_final != null)];
      if (!rows.length) return "";
      return `<div class="section-title">Fight-by-fight edge board
          <span class="sub">— every priced bout: the model’s number vs the market’s, and
          the verdict. Bet rows are journaled in the UFC record.</span></div>
        <div class="hd-card">
          ${rows.map((r) => `
            <div class="ufc-edge-row rec-row mid tall${r._pick ? "" : " dim"}">
              <span class="ufc-verdict ${r._pick ? "bet" : "pass"}">${r._pick ? "BET" : "PASS"}</span>
              <span class="ufc-what"><strong>${escapeHtml(r.fight)}</strong>
                <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">
                  ${r._pick ? `${escapeHtml(r.selection || (r.pick + " ML"))} ${american((r.best_market || {}).odds != null ? r.best_market.odds : r.odds)} (${escapeHtml(r.book || "")}) · stake ${r.stake_units}u`
                            : escapeHtml(r.why || "")}</span></span>
              <span class="ufc-num">
                model ${pctv(r.p_final)} · market ${pctv(r.p_market)}
                <span style="display:block;color:${(r.edge || 0) > 0 ? "var(--good)" : "var(--text-mute)"};font-weight:700">
                  ${r.edge != null ? `${r.edge >= 0 ? "+" : ""}${(r.edge * 100).toFixed(1)}pts vs break-even` : ""}</span></span>
            </div>`).join("")}
        </div>`;
    })()}
    ${await (async () => {
      // The UFC record — this card's picks are graded here after the
      // fights, same probation-bucket pattern as every new signal.
      const rec = await loadRecordOnce();
      const u = rec.ufc_record || {};
      if (!u.settled && !u.open) return "";
      const wins = u.wins || 0, losses = u.losses || 0, pushes = u.pushes || 0;
      // PUSHES COUNT IN THE TOTAL. A record of 2-9 with a push in it is
      // twelve graded fights, not eleven, and a breakdown whose slices do
      // not add up to the number in the middle of its own ring is the one
      // thing this panel must never be.
      const graded = wins + losses + pushes;
      const pct = (n) => graded ? `${((n / graded) * 100).toFixed(1)}%` : "—";
      const legend = [["Wins", wins, "var(--good)"],
                      ["Losses", losses, "var(--bad)"],
                      ["Pushes", pushes, "var(--text-mute)"]];
      return `<div class="section-title">UFC record
          <span class="sub">— every journaled pick, graded from fight results after each card.
          Its own bucket until it earns more.</span></div>
        <div class="ufc-record">
          <div class="stat-cards">
            ${statCardHTML("trophy", "Record", `${wins}-${losses}`,
                           `${u.open || 0} open · units`)}
            ${statCardHTML("chart", "Flat ROI",
                           fmtRoi(u.roi),
                           `${(u.net_units || 0) >= 0 ? "+" : ""}${(u.net_units || 0).toFixed(2)}u return on investment`,
                           u.roi == null ? "" : (u.roi >= 0 ? "pos" : "neg"))}
            ${statCardHTML("star", "Graded", graded, "judge after 50+, not 5")}
          </div>
          <div class="ufc-rb">
            <div class="ufc-rb-head">Record breakdown</div>
            <div class="ufc-rb-body">
              ${donutRing(legend.map(([k, n, col]) => ({ label: k, value: n, color: col })),
                          { caption: "Total fights",
                            alt: `${graded} graded: ${wins} won, ${losses} lost, ${pushes} pushed` })}
              <div class="ufc-rb-legend">
                ${legend.map(([k, n, col]) => `<div class="urb-row">
                  <span class="urb-dot" style="background:${col}"></span>
                  <span class="urb-k">${k}</span>
                  <span class="urb-n">${n}</span>
                  <span class="urb-p">${pct(n)}</span></div>`).join("")}
              </div>
            </div>
            <details><summary>Every pick. Every fight. No excuses.</summary>
              <p>Nothing is dropped from this ring. Every fight the desk journaled is in
              it the moment the card grades — the ones that went badly included, which
              is the only version of a record worth showing. It stays a bucket of its
              own until there are enough fights in it to mean something; ${graded}
              ${graded === 1 ? "is" : "are"} not enough, and a good run at this size
              would say no more than a bad one.</p></details>
          </div>
        </div>`;
    })()}
    ${(() => {
      // The page said "re-check after Friday weigh-ins" and then offered no
      // way to know whether anyone had. This is that status, up top, where
      // it changes what you do with the card below.
      const w = d.weigh_ins;
      if (!w) return "";
      if (w.missed) {
        return `<div class="card" style="--tone:var(--bad);margin-bottom:12px">
          <div class="player">${icon('cross')} ${plural(w.missed, "fighter")} missed weight</div>
          <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:4px">Their fights are
          gated off the pick list automatically — that is what KILL IF always said and now
          enforces. ${w.unrecorded} weigh-in(s) still unrecorded.</div></div>`;
      }
      if (w.unrecorded) {
        return `<div class="card" style="--tone:var(--warn);margin-bottom:12px">
          <div class="player">${icon('clock')} ${w.unrecorded} weigh-in(s) not recorded yet</div>
          <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:4px">Fighters weigh in the
          morning before the card, and the site pulls the results on its own once they publish —
          nothing for you to do. Until then these fights are graded <em>without</em> the fight-week
          component rather than being marked down for it, so the picks below stand on their own.
          A miss, when one lands, gates that fight on the next build.</div></div>`;
      }
      return `<div class="card" style="--tone:var(--good);margin-bottom:12px">
        <div class="player">${icon('check')} Weigh-ins complete — ${w.made} on weight, none missed</div></div>`;
    })()}
    ${d.no_qualifying ? `<div class="card"><div class="player">No qualifying plays on this card.</div>
        <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:6px">Most fights on any card
        have no exploitable edge — the pass list below says why, fight by fight. Re-check after
        Friday weigh-ins: missed weight and visible cut damage aren’t fully priced for hours, and
        the weigh-in results land here automatically.</div></div>`
      : `<div class="section-title">Picks
          <span class="sub">— cleared the clamp AND the gate · one-fifth Kelly stakes · journaled
          at these prices and graded after the card</span></div>
        <div class="cards wide">${(d.picks || []).map(pickCard).join("")}</div>`}
    ${(() => {
      // Grouped so the page reads as a card, not a wall: fights we
      // actually priced first, then the ones waiting on books, then the
      // ones no data source covers.
      const groups = [
        ["Modeled — no edge at this price", ["gate", "clamp_kill"],
         "priced, run through the model, and rejected by the clamp or the gate"],
        ["Waiting on prices", ["no_price"],
         "books open MMA lines closer to the card — these re-evaluate every refresh"],
        ["Unmodelable — no tracked stats", ["no_data", "no_dossier"],
         "regional or uncovered records: no fight-by-fight data exists, so the model refuses"],
      ];
      const list = d.pass_list || [];
      const seen = new Set();
      let html = "";
      for (const [title, codes, sub] of groups) {
        const rows = list.filter((m) => codes.includes(m.reason_code));
        rows.forEach((m) => seen.add(m));
        if (!rows.length) continue;
        html += `<div class="section-title">${title}
            <span class="sub">— ${plural(rows.length, "fight")} · ${sub}</span></div>
          <div class="cards wide">${rows.map(passCard).join("")}</div>`;
      }
      const rest = list.filter((m) => !seen.has(m));
      if (rest.length)
        html += `<div class="section-title">Other passes</div>
          <div class="cards wide">${rest.map(passCard).join("")}</div>`;
      return html || `<div class="section-title">Pass list</div>
        ${panelEmpty("Nothing to pass on.")}`;
    })()}
    <div id="ufc-paths"></div>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Every fight is priced
      off a dossier of measured records, and each one is reviewed before a card — a red flag on
      a fighter blocks a bet until it is resolved. The model refuses any fight missing a
      dossier rather than guessing at it. Updated ${escapeHtml(formatStamp(d.generated_at))}.</p>`;
  // Each fight's path (js/extras.js), under the card it reads.
  loadExtras().then((X) => { const el = document.getElementById("ufc-paths"); if (X && el) el.innerHTML = X.pathsHTML(d); });
}

/* ============================================================
   Status — is it live right now
   ============================================================
   Ethan, 2026-08-25: "A status/freshness page — 'MLB board: rebuilt 41s
   ago. Odds: live. Lineups: 11/15 posted.'"

   Every board is asked with a HEAD request, so the page costs a few
   hundred bytes rather than the eight megabytes those files add up to.
   `Last-Modified` on a published board IS its build time — the file is
   written by the pipeline and nothing else touches it — which makes
   this the one freshness answer that cannot be flattered by a cache or
   by the page's own fetch clock.
   ============================================================ */
const STATUS_BOARDS = [
  ["recommendations.json", "NFL board"],
  ["mlb_recommendations.json", "MLB board"],
  ["nba.json", "NBA board"],
  ["wnba.json", "WNBA board"],
  ["nhl.json", "NHL board"],
  ["cfb.json", "College football board"],
  ["ufc.json", "UFC card"],
  ["record.json", "The record"],
  ["feed.json", "The feed"],
  ["injuries.json", "Injury board"],
  ["streak.json", "Streak slate"],
  ["live_mlb.json", "Live scoreboard (MLB)"],
  /* THE FAST CLOCKS BELONG ON THE STATUS PAGE TOO. These five are the
     only files on the site whose staleness is measured in seconds, so
     they are the ones where "the loop died" is both most likely to
     matter and least likely to be noticed — a frozen scoreboard reads
     as a quiet night. */
  ["live_nfl.json", "Live scoreboard (NFL)"],
  ["live_cfb.json", "Live scoreboard (college football)"],
  ["live_nba.json", "Live scoreboard (NBA)"],
  ["live_wnba.json", "Live scoreboard (WNBA)"],
  ["live_nhl.json", "Live scoreboard (NHL)"],
  /* The Lab's weekly backtest (audit O17): nine days overdue once with
     nothing flagging it, because it was not on this list at all. */
  ["backtest.json", "The Lab (weekly backtest)"],
];

/* A FILE'S OWN CLOCK (audit 2026-09-30, F-13 / O17). The slate boards
   rebuild every cycle and use the machine's measured floor; these move on
   slower clocks and would read "stale" all week against it. Hours, the
   same numbers as engine/freshness.MAX_AGE_H. */
const STATUS_MAX_AGE_H = { "backtest.json": 192, "record.json": 6, "ufc.json": 12 };

/* Which league a slate file is, so its row can say "off-season" from the
   heartbeat rather than "never built" or a scary age. */
const STATUS_SPORT_OF = { "recommendations.json": "nfl", "mlb_recommendations.json": "mlb",
  "nba.json": "nba", "wnba.json": "wnba", "nhl.json": "nhl", "cfb.json": "cfb" };

async function boardStamp(file) {
  try {
    // Through the wrapper like every other board read, so a refused
    // request lands in the offline banner's count instead of only in
    // this page's own row. A 404 is an ANSWER — a board this machine
    // has never built is a fact, not a broken wire.
    const res = await boardFetch(`data/${file}`,
                                 { method: "HEAD", cache: "no-store" });
    if (!res.ok) return { file, missing: true };
    const lm = res.headers.get("Last-Modified");
    const at = lm ? Date.parse(lm) : NaN;
    return { file, at: Number.isFinite(at) ? at : null,
             bytes: Number(res.headers.get("Content-Length")) || null };
  } catch (e) {
    return { file, unreachable: true };
  }
}

/* THE CODE RUNNING, AND EACH LEAGUE'S LAST REBUILD (2026-09-23). Ethan:
   "the same most likely pics that we had earlier are the same ones that
   are there now … make sure all of our new changes are taking effect."
   A build that fails or runs out of time keeps the last good board on
   purpose (launch.refresh_nfl, "kept last board"), so a stuck board and a
   quiet slate look the same on every page but this one. The heartbeat has
   carried the commit and each board's last run since August; --boards
   read them over SSH and nothing on the site did. */
const BUILD_LEAGUES = [["nfl", "NFL"], ["cfb", "College football"], ["mlb", "MLB"],
  ["nba", "NBA"], ["wnba", "WNBA"], ["nhl", "NHL"], ["ufc", "UFC"]];

/* THE BOARD'S SELF-CHECK (engine/boardtruth, run by launch._board_truth
   after every build): how many of the claims the page makes held against
   the board's own data. Ethan, 2026-09-25: "making sure all that shit is
   good." Counts only — the detail names picks and lives in the build log. */
const TRUTH_WORDS = { "FLOOR": "under 55%", "CAP": "heavier than −250", "OLD PRICE": "price too old to show",
  "NO NOW": "locked, no current price", "LOCK NOTE": "note and tile disagree",
  "PICK MISSING": "card names a missing pick", "LONGSHOT": "longshot called likeliest",
  "BARE MATE": "teammate-out line with no number", "DATA BEHIND": "stats behind",
  "UNDER EVEN": "under 50%, nothing backing it" };
function truthRowHTML(t, sub) {
  if (!t || t.checked == null) return "";
  if (!t.count) return sub("Self-check", `all ${t.checked} claims hold`, "st-good", "");
  const what = Object.entries(t.by_check || {})
    .map(([k, v]) => `${TRUTH_WORDS[k] || k} ${v}`).join(" · ");
  return sub("Self-check", `${t.count} of ${t.checked} claims fail`, "st-bad", what);
}

/* THE LOOP AND THE CHORES, said outright (2026-10-04). Ethan's 4:26 a.m.
   screenshots showed every board four hours old and nothing saying why:
   the board loop had stopped inside a daily chore. The loop's own last
   cycle and the two chores lanes — the daily pass and the settle — (which
   step, for how long, and when one is stuck, the line it is waiting on)
   now sit under the code row. */
function loopRowsHTML(hb, now) {
  const rowOf = (k, v, cls, why) => `<div class="st-row"><span class="st-k">${k}</span>
      <span class="st-v ${cls}">${escapeHtml(v)}</span><span class="st-sub">${escapeHtml(why || "")}</span>${
        why && cls === "st-bad" ? `<span class="st-why">${escapeHtml(why)}</span>` : ""}</div>`;
  let out = "";
  if (hb.at_epoch) {
    const age = now - hb.at_epoch;
    const late = age > Math.max(20 * 60, 3 * (hb.cycle_p50_s || 0));
    out += rowOf("Refresh loop", `last cycle ${ageText(age)} ago`, late ? "st-bad" : "st-good",
      late ? "the board loop has not finished a cycle lately — the watchdog restarts it after 90 minutes" : "");
  }
  const lanes = [["daily", "Daily chores"], ["settle", "Settling"]];
  lanes.forEach(([key, label]) => {
    const c = (hb.chores || {})[key];
    if (!c) return;
    if (c.stuck) {
      const at = (c.stack || []).slice(-2).join(" ← ");
      out += rowOf(label, `stuck in ${c.step} for ${ageText(c.running_s || 0)}`, "st-bad",
        at ? `waiting at ${at} — the boards keep rebuilding meanwhile` : "the boards keep rebuilding meanwhile");
    } else if (c.resting_until_epoch && c.resting_until_epoch > now && c.killed) {
      // The system took it (out of memory), not our time limit.
      out += rowOf(label, `killed by the system in ${c.killed.step || "a step"} — runs again in ${ageText(c.resting_until_epoch - now)}`,
        "st-bad", "out of memory, most likely; the boards keep rebuilding meanwhile");
    } else if (c.resting_until_epoch && c.resting_until_epoch > now) {
      out += rowOf(label, `stopped at its time limit — runs again in ${ageText(c.resting_until_epoch - now)}`,
        "st-bad", "its stack is in the log; the boards keep rebuilding meanwhile");
    } else if (c.step) {
      out += rowOf(label, `running ${c.step} (${ageText(c.running_s || 0)})`, "st-good", "");
    } else if (c.done_epoch) {
      out += rowOf(label, `idle · last finished ${ageText(now - c.done_epoch)} ago`, "st-good", "");
    }
  });
  return out;
}

/* THE KALSHI TRADER (engine/kalshitrade), counts only, from the heartbeat:
   its mode, today's orders, what is open, its record, and the Pikkit
   profile the account syncs to. Ethan, 2026-10-06: "link the site to a
   pikkit … account so we can legitimately track all the bets the site
   puts in." Nothing when the trader is off. */
function kalshiCardHTML(hb) {
  const k = hb && hb.kalshi;
  if (!k || !k.mode || k.mode === "off") return "";
  const mode = k.stopped ? "stopped" : k.mode === "live" ? "live — real money" : "paper — recording, not placing";
  const row = (l, v, c, n) => `<div class="st-row"><span class="st-k">${l}</span><span class="st-v st-${c}">${escapeHtml(v)}</span><span class="st-sub">${n}</span></div>`;
  return `<div class="section-title">Kalshi trader<span class="sub">— the site’s picks, placed on Kalshi by the box so a Pikkit account can verify them</span></div>
    <div class="card">${row("Mode", mode, k.stopped ? "bad" : k.mode === "live" ? "good" : "off",
      k.pikkit ? `<a href="${safeHref(k.pikkit)}" target="_blank" rel="noopener">Verified on Pikkit →</a>` : "")}
    ${row("Today", `${k.today == null ? "—" : k.today} orders · ${k.open == null ? "—" : k.open} open`, k.today ? "good" : "off",
      k.last_run ? `last pass ${escapeHtml(String(k.last_run).replace("T", " ").slice(0, 16))}` : "")}
    ${row("Record", k.record || "—", "off", "won-lost, settled by Kalshi")}</div>`;
}

function buildsCardHTML(hb) {
  if (!hb) return "";
  const runs = hb.boards || {};
  const now = Date.now() / 1000;
  // THE TWO BOARDS A MEMBER READS, under each league (Ethan, 2026-09-23:
  // "we need to specify on this page the most likely boards and edge
  // boards"). Counted by the launcher off the built board after every run
  // (launch._board_counts) — the Edge board as edgeBoardRows draws it, and
  // how many of those we actually stake.
  const n = (x, one, many) => x == null ? "—" : `${x} ${x === 1 ? one : many}`;
  // A failing row's note gets its own line on a phone, where .st-sub is
  // hidden (Ethan's 2026-10-07 screenshot: "8 of 384 claims fail" with no
  // word of which checks).
  const sub = (label, v, cls, note) => `<div class="st-row st-indent"><span class="st-k">${label}</span>
      <span class="st-v ${cls}">${escapeHtml(v)}</span><span class="st-sub">${escapeHtml(note || "")}</span>${
        note && cls === "st-bad" ? `<span class="st-why">${escapeHtml(note)}</span>` : ""}</div>`;
  const rows = BUILD_LEAGUES.filter(([k]) => runs[k]).map(([k, label]) => {
    const r = runs[k];
    const when = r.at_epoch ? `${ageText(now - r.at_epoch)} ago` : "time unknown";
    const kept = r.ok ? "" : "the last good board";
    const boards = r.most_likely == null && r.edge == null ? "" :
      sub("Most Likely board", n(r.most_likely, "pick", "picks"), r.most_likely ? "st-good" : "st-off", kept)
      + sub("Edge board", n(r.edge, "bet", "bets"), r.edge ? "st-good" : "st-off",
            r.staked ? `${r.staked} staked` : (r.edge === 0 ? "nothing priced wrong" : ""))
      + truthRowHTML(r.truth, sub);
    return `<div class="st-row"><span class="st-k">${escapeHtml(label)}</span>
      <span class="st-v ${r.ok ? "st-good" : "st-bad"}">${r.ok
        ? `rebuilt ${escapeHtml(when)}` : `build failed ${escapeHtml(when)}`}</span>
      <span class="st-sub">${r.ok ? "" : escapeHtml(String(r.note || "kept the last good board"))}</span>${
        // The reason, on a phone too: .st-sub is hidden there, and a bare
        // "build failed" is what Ethan saw on 2026-10-01 with no way to say why.
        r.ok ? "" : `<span class="st-why">${escapeHtml(String(r.note || "kept the last good board"))}</span>`}</div>${boards}`;
  }).join("");
  return `<div class="section-title">Model builds
      <span class="sub">— the code running, each league’s last rebuild on it, and what its Most Likely
        and Edge boards hold.</span></div>
    <div class="card st-card">
      <div class="st-row"><span class="st-k">Code running</span>
        <span class="st-v ${hb.commit ? "st-good" : "st-off"}">${escapeHtml(hb.commit || "unknown")}</span>
        <span class="st-sub">${hb.auto_update ? "updates itself" : ""}</span></div>
      ${loopRowsHTML(hb, now)}
      ${rows}
    </div>`;
}

async function renderStatus() {
  const host = document.getElementById("status-body");
  if (!host) return;
  const dt = document.getElementById("slate-date");
  if (dt) dt.textContent = "Status · freshness";
  host.innerHTML = `<p class="es-sub">Asking every board when it last
    rebuilt…</p>`;
  const stamps = await Promise.all(STATUS_BOARDS.map(([f]) => boardStamp(f)));
  let hb = null;
  try {
    const res = await boardFetch("data/heartbeat.json", { cache: "no-store" });
    hb = res.ok ? await res.json() : null;
  } catch (e) { hb = null; }
  const d = state.data || {};
  const os = d.odds_status || {};
  const inj = d.injury_status || {};
  const runs = (hb && hb.boards) || {};
  const offseason = (file) => !!(runs[STATUS_SPORT_OF[file]] || {}).offseason;
  const lateFor = (file, age) => age != null
    && age > Math.max(staleAfterMs(), (STATUS_MAX_AGE_H[file] || 0) * 3600000);
  const row = ([file, label], s) => {
    const age = s.at ? Date.now() - s.at : null;
    // The floor is this machine's own cycle time where we know it, so
    // "stale" means late for THIS box rather than late for a constant
    // that was true of somebody's laptop.
    const bad = lateFor(file, age) && !offseason(file);
    const state_ = offseason(file) ? ["off-season", "off"]
      : s.missing ? ["never built", "off"]
      : s.unreachable ? ["unreachable", "bad"]
      : age == null ? ["built, time unknown", "off"]
      : bad ? [`${ageText(age / 1000)} ago`, "bad"]
      : [`${ageText(age / 1000)} ago`, "good"];
    return `<div class="st-row">
      <span class="st-k">${escapeHtml(label)}</span>
      <span class="st-v st-${state_[1]}">${escapeHtml(state_[0])}</span>
      <span class="st-sub">${s.bytes
        ? (s.bytes < 1024 ? "&lt;1 KB" : `${(s.bytes / 1024).toFixed(0)} KB`)
        : ""}</span>
    </div>`;
  };
  const cycle = hb && hb.cycle_p50_s
    ? `A full rebuild of every board takes about
       <b>${Math.round(hb.cycle_p50_s / 60)} min</b> on this machine, measured
       over ${escapeHtml(String(hb.cycles_timed || 0))} ${pluralWord(hb.cycles_timed || 0, "cycle")}.`
    : `This machine has not timed a full cycle yet, so "stale" falls back to
       the page’s own floor rather than to a measured one.`;
  const beat = hb && hb.at_epoch
    ? `The refresher last finished a cycle
       <b>${escapeHtml(ageText(Date.now() / 1000 - hb.at_epoch))} ago</b>,
       on a ${Math.round((hb.interval_s || 0) / 60)}-minute timer.`
    : `No heartbeat has been written — either the refresher is not running or
       it has not completed a cycle since it started.`;
  /* THE VERDICT FIRST (audit O17). The page answered "is it working?"
     only to a reader who could interpret a heartbeat, a cycle median and
     sixteen ages. One sentence now leads; the mechanics sit beneath it. */
  const beatAge = hb && hb.at_epoch ? Date.now() / 1000 - hb.at_epoch : null;
  const loopDead = beatAge == null
    || beatAge > Math.max(900, 3 * Math.max(hb.interval_s || 0, hb.cycle_p50_s || 0));
  const late = STATUS_BOARDS.filter(([f], i) => !stamps[i].missing
    && lateFor(f, stamps[i].at ? Date.now() - stamps[i].at : null) && !offseason(f));
  const verdict = loopDead
    ? ["bad", "The refresh loop is not running — boards below are frozen where it stopped."]
    : late.length
      ? ["warn", `Running, but ${plural(late.length, "board")} ${late.length === 1 ? "is" : "are"} behind: ${
          late.slice(0, 4).map(([, l]) => l).join(", ")}${late.length > 4 ? "…" : ""}.`]
      : ["good", "Everything is running and every board is current."];
  host.innerHTML = `
    <div class="st-verdict st-${verdict[0]}" role="status">${escapeHtml(verdict[1])}</div>
    <details class="st-mech"><summary>How this is measured</summary>
      <div class="about-lede"><p>${beat} ${cycle}</p></div></details>
    ${buildsCardHTML(hb)}
    ${kalshiCardHTML(hb)}
    <div class="section-title">Every published board</div>
    <div class="card st-card">${STATUS_BOARDS.map((b, i) => row(b, stamps[i])).join("")}</div>
    <div class="section-title">Tonight’s feeds
      <span class="sub">— for the league you are looking at.</span></div>
    <div class="card st-card">
      <div class="st-row"><span class="st-k">Odds</span>
        <span class="st-v ${os.priced_at ? "st-good" : "st-off"}">${
          os.priced_at ? `pulled ${escapeHtml(
            ageText(Date.now() / 1000 - os.priced_at))} ago` : "not pulled yet"}</span>
        <span class="st-sub">${os.books != null
          ? escapeHtml(plural(os.books, "book")) : ""}</span></div>
      <div class="st-row"><span class="st-k">Lineups</span>
        <span class="st-v ${inj.confirmed ? "st-good" : "st-off"}">${
          inj.confirmed != null && inj.total != null
            ? escapeHtml(`${inj.confirmed} of ${inj.total} posted`)
            : "nothing filed yet"}</span><span class="st-sub"></span></div>
      <div class="st-row"><span class="st-k">This board</span>
        <span class="st-v ${state.builtAt ? "st-good" : "st-off"}">${
          state.builtAt
            ? `built ${escapeHtml(ageText((Date.now() - state.builtAt) / 1000))} ago`
            : "build time unknown"}</span>
        <span class="st-sub">${escapeHtml(
          (LEAGUE_LABEL[state.sport] || state.sport || "").toUpperCase())}</span></div>
    </div>
    ${state.sport === "cfb" && d.talent ? `
    <div class="section-title">The college talent prior
      <span class="sub">— the preseason layer: which inputs arrived, and what it
        carries this week.</span></div>
    ${talentCardHTML(d.talent)}` : ""}
    <p class="es-sub">Every time on this page is read from the file the
    server actually holds, not from when this page fetched it — a board
    that stopped rebuilding this morning says so here even if the page
    itself loaded a second ago.</p>`;
}

/* ============================================================
   About — what this site is, for someone who just landed on it.

   Written for a reader with no context: no jargon in the first screen,
   the limits stated as plainly as the strengths, and the legal and
   responsible-gambling terms in the same place rather than buried in a
   footer nobody opens. The tone is deliberately flat. A page that hypes
   the model on the way to a disclaimer has not really made the
   disclaimer.
   ============================================================ */
function renderAbout() {
  const host = document.getElementById("about-body");
  if (!host) return;
  const src = document.getElementById("data-source");
  if (src) {
    src.className = "data-source";
    src.textContent = "Reference";
    src.title = "Plain-English explainer — no data feed involved";
  }
  const dt = document.getElementById("slate-date");
  if (dt) dt.textContent = "About · terms · responsible play";

  const card = (title, body, accent) => `
    <article class="card about-card"${accent ? ` style="--tone:${accent}"` : ""}>
      <div class="player">${title}</div>
      <div class="about-body">${body}</div>
    </article>`;

  host.innerHTML = `
    <div class="about-lede">
      <p><strong>Qellys Book is one book for everything a sharp bettor keeps
      open in ten tabs.</strong> Six leagues priced nightly by named models.
      A full fantasy football suite with its own draft room. Prediction-market
      intelligence. A live meme-coin radar. And underneath all of it, the one
      thing almost nobody else will show you: <strong>every pick this site has
      ever made, graded in public at the price it was published — losses
      included.</strong></p>

      <p>It is an analytics tool, not a sportsbook and not a tipster. You
      cannot place a bet here and no money changes hands on this site. The
      model estimates its own probability for each outcome and compares it to
      the live prices at ten books. When our number and the book’s number
      disagree by enough to survive our own margin for error, the board shows
      it — with the reasons on the card. When they don’t, the board says
      <em>"no qualifying plays"</em> and shows you nothing. That happens
      often, and it is the system working rather than failing.</p>
    </div>

    <div class="section-title">Six leagues, each with its own model
      <span class="sub">— not one formula wearing six logos</span></div>
    <div class="cards wide">
      ${card("NFL — The NFL Book", `<p>The pro-bettor spec: player props with
        usage bridges and coaching-reset detection, game lines off
        opponent-adjusted team ratings, anytime-TD long shots, and a Week 1
        board that prices from day one instead of going dark until October.</p>`)}
      ${card("MLB — Scalpy 2.0", `<p>Hitter and pitcher props from
        plate-appearance-level data: park factors, umpires, platoon splits,
        bullpen fatigue, Statcast contact quality. Home-run long shots, live
        win-probability charts, and a per-game simulator that deals every
        plate appearance.</p>`)}
      ${card("NBA + WNBA — Scalpy hoops", `<p>Points, rebounds, assists and
        threes through a minutes engine with on/off inheritance — who absorbs
        the shots when the star sits — plus the same public grading as every
        other league.</p>`)}
      ${card("College football", `<p>A market-attention model: it knows which
        games the sharps price hard and which Tuesday slates nobody is
        watching, and it refuses to grade a play whose quarterback nobody has
        confirmed.</p>`)}
      ${card("UFC — Scalpy MMA", `<p>Fighter dossiers with measured records,
        method and round markets, and a card that passes on most fights with
        the reason stated — because most fights deserve a pass.</p>`)}
      ${card("Futures, every league", `<p>Season-long boards priced the same
        honest way, with the hold named so you can see what the book is
        charging you to park money for six months.</p>`)}
    </div>

    <div class="section-title">The betting toolkit
      <span class="sub">— what you open every night</span></div>
    <div class="cards wide">
      ${card("A board with reasons, not emojis", `<p>Every recommended pick
        carries its grade, its stake, and the named factors behind it — with
        each reason labelled by evidence tier: measured tonight, stable
        history, or the model’s own inference. Negative factors get a red
        mark on the card, not a hidden footnote.</p>`)}
      ${card("Player props with the picture", `<p>Every prop card charts the
        player’s actual last ten games against tonight’s line — and the
        search reaches <strong>every player in the league</strong>, not just
        tonight’s board, with faces, multi-market profiles and full game
        logs.</p>`)}
      ${card("Line shopping across ten books", `<p>The same bet is not the
        same price everywhere. The board names the book quoting the best
        number on every pick, and the scanner hunts stale lines, arbitrage
        pairs, middles and low-hold markets across the whole slate.</p>`)}
      ${card("A parlay screen, not a parlay builder", `<p>Legs must earn the
        board as singles first. Then the correlation engine — measured on
        tens of thousands of real games, refined by a per-lineup simulator —
        prices the joint honestly and publishes <strong>the price the book
        must beat</strong> for the ticket to be worth anything.</p>`)}
      ${card("Live, while it plays", `<p>Every game in progress across the
        leagues on one board: score, situation, the posted lines, and a live
        win-probability chart drawn from de-vigged in-play prices. Your open
        bets track themselves as the games run.</p>`)}
      ${card("Long shots, priced honestly", `<p>Home runs and anytime
        touchdowns with real probabilities attached — tracked in their own
        record bucket so a +900 flier never inflates the headline
        win rate.</p>`)}
    </div>

    <div class="section-title">The fantasy football suite
      <span class="sub">— the same engine, pointed at your league</span></div>
    <div class="cards wide">
      ${card("A draft room", `<p>Rankings from every source we can read
        without a password, side by side, with the disagreements flagged — a
        draft kit with tiers, sleepers and a value board — and a
        <strong>mock draft simulator</strong>: snake order against
        value-hungry CPU rooms, judged on projected points, not vibes.</p>`)}
      ${card("Your actual league, synced", `<p>Connect Sleeper, Yahoo or ESPN
        and the desk reads your real roster: a lineup optimiser, a trade
        generator, waiver-wire trends and camp-battle watch — no passwords
        ever taken for sites that need one.</p>`)}
      ${card("The numbers under the names", `<p>Usage movers (whose role is
        growing before the points arrive), buy-low and sell-high flags from
        expected points, and game scripts built from what the betting market
        expects each game to look like.</p>`)}
    </div>

    <div class="section-title">Beyond the sportsbook
      <span class="sub">— two more markets, same discipline</span></div>
    <div class="cards wide">
      ${card("Prediction-market intel", `<p>Polymarket, watched like a tape:
        whale activity, flagged accounts, leaderboards, and market moves
        worth knowing about — the crowd’s real money, read continuously.</p>`)}
      ${card("Rocket Radar — the meme-coin screen", `<p>A live terminal for
        the fastest market there is: momentum measured on our own tape,
        holder concentration from the chain itself, rug-check safety flags
        and embedded live charts. The same honesty rules apply — measured
        numbers or a dash, never a guess.</p>`)}
      ${card("Your own book", `<p>My Bets logs the wagers you actually place
        at your sportsbook — typed in or bulk-imported — grades them, and
        keeps your bankroll curve. Make a free account and it follows you
        from phone to laptop. The whole site installs to your home screen
        like an app.</p>`)}
    </div>

    <div class="section-title">Why here, and not five other subscriptions
      <span class="sub">— the comparison, plainly</span></div>
    <div class="cards wide">
      ${card("One book instead of a stack of tools", `<p>A picks service, a
        props-charting tool, a line-shopping app, a fantasy optimiser and a
        crypto screener — the market sells those separately. Here they are
        one product sharing one data spine, so the injury report that moves
        a prop also moves the fantasy board and the live chart.</p>`)}
      ${card("The record is the product", `<p>Picks services show you a hot
        streak; ours shows you the journal — every pick at its published
        price, wins, losses, closing-line value, and a calibration curve that
        says whether our "60%" actually meant 60%. The
        <strong>Why&nbsp;us</strong> page opens the math itself, with
        calculators to check our work by hand.</p>`)}
      ${card("Built to say no", `<p>A tout must sell picks every night. This
        site caps its slates, passes with reasons, and prints "no qualifying
        plays" when the numbers do not clear — which is exactly the night a
        subscription tout invents a lock.</p>`)}
    </div>

    <div class="section-title">Everything in one place
      <span class="sub">— the practical reason this exists</span></div>
    <div class="cards wide">
      ${card("The information is public. Having it together is the edge.", `
        <p>None of the data here is secret. Box scores, injury reports, depth
        charts, park factors, weather, recruiting rankings, fighter records —
        anyone can look all of it up. The problem is that "anyone" would need
        a dozen browser tabs and two hours per slate, and the line will have
        moved before they finish.</p>
        <p>This site does that gathering continuously and automatically, then
        prices it against <strong>ten sportsbooks at once</strong>. Two books
        quoting the same game differently is a real, ordinary occurrence, and
        on a two-way market a twenty-cent difference in price can be the whole
        margin. You cannot beat a book on information it also has; you can
        beat it on information it hasn’t bothered to price carefully, and on
        being at the right window.</p>`)}

      ${card("What the model is actually doing", `
        <p>For each market it builds a full <strong>distribution</strong>, not a
        pick. Not "this player goes over" but "here is the range of outcomes
        and how likely each one is." It removes the book’s built-in margin
        (the "vig") to find what the market really believes, compares that to
        our number, and then <strong>deliberately shrinks our own edge</strong>
        — because a model that trusts itself completely is a model that has
        stopped noticing it can be wrong.</p>
        <p>Whatever survives that gets graded 0–100 and sized by a fraction of
        the Kelly criterion, a standard bankroll formula. Anything under the
        bar is not shown as a weaker suggestion. It is not shown.</p>`)}

      ${card("We show our losses", `
        <p>Every play the model publishes is recorded at the price and time it
        was published, then graded against the real result — wins and losses
        both — on the <strong>Record</strong> page. Nothing is quietly deleted
        after it loses.</p>
        <p>Newer models are marked <em>on probation</em>: they are tracked and
        graded like everything else, but they have not yet earned the right to
        be staked. Where we are missing a data source, the page says so
        instead of filling the hole with a guess.</p>`)}
    </div>

    <div class="section-title">The honest part
      <span class="sub">— please read this bit properly</span></div>
    <div class="cards wide">
      ${card(`${icon('warn')} Anything can happen. Genuinely anything.`, `
        <p>Sports are random and betting is gambling. A 90% favourite loses
        one time in ten, and that one time can be tonight, and it can happen
        three nights in a row. A quarterback rolls an ankle on the first
        drive. A fighter who has never been stopped gets caught by a punch he
        did not see. A game gets called for weather in the sixth inning.</p>
        <p><strong>No model can predict a single event, and this one does not
        claim to.</strong> It claims something much smaller: that across
        hundreds of bets, taking prices that are better than they should be
        works out better than taking prices that aren’t. Even if every number
        on this site were perfect, you would still have long losing runs. That
        is not a bug in the method — it is what randomness looks like from the
        inside.</p>
        <p>Nothing here is a guarantee, a lock, a sure thing, or a prediction.
        Past results — including ours — do not predict future results.</p>`,
        "var(--bad)")}

      ${card("This is not betting advice", `
        <p>Everything published here is <strong>automated statistical output
        and general information</strong>, produced by our model from public
        data. It is not financial advice, investment advice, or a
        recommendation that you place any particular wager. We are not your
        advisor and we have no idea what your circumstances are.</p>
        <p>Every decision you make with this information is yours alone, and
        so is every outcome. If you would not be comfortable losing the money,
        do not put it at risk.</p>`,
        "var(--warn)")}

      ${card("Legal — the rules that apply", `
        <ul class="about-list">
          <li><strong>You must be of legal gambling age</strong> where you are.
            That is 21 in most of the United States and 18 in some
            jurisdictions. If you are under it, this site is not for you.</li>
          <li><strong>Sports betting is not legal everywhere.</strong> Laws
            differ by country, state and province and they change. It is your
            responsibility to know the rules where you are and to follow
            them.</li>
          <li><strong>We are not affiliated with any sportsbook</strong>, and
            not with the NFL, MLB, NBA, WNBA, UFC, the NCAA or any team,
            school or league. Book names appear only to identify where a price
            was quoted. All trademarks belong to their owners.</li>
          <li><strong>We take no bets, hold no money and process no
            payments.</strong> No part of this site is a wagering service.</li>
          <li><strong>Prices change.</strong> Odds shown were correct when
            fetched and may be stale by the time you read them. The
            timestamp on each page tells you how old the data is — check it.
            Always confirm the current price at your book.</li>
          <li><strong>No warranty.</strong> Data can be wrong, feeds can break
            and models can be miscalibrated. Everything here is provided as-is,
            with no guarantee of accuracy or fitness for any purpose, and we
            accept no liability for losses arising from its use.</li>
          <li><strong>Personal use.</strong> This is a private analytics tool.
            It is not a licensed gambling operator or a paid tipping service,
            and nothing on it is an offer to provide one.</li>
        </ul>`,
        "var(--brand)")}

      ${card(`${iconMark("warn")}If it stops being fun, stop`, `
        <p>Gambling is genuinely addictive, and a tool that makes betting feel
        more rigorous can make it easier to bet more, not less. Bet only money
        you can afford to lose. Never chase a loss. Set a limit before you
        start rather than during. Take breaks. Betting is not a way to make
        a living or to fix a financial problem.</p>
        <p>If it has stopped being fun, or someone close to you thinks it has,
        help is free and confidential:</p>
        <ul class="about-list">
          <li><strong>United States</strong> — 1-800-GAMBLER
            (1-800-426-2537), or text 800GAM to 53342.
            <a href="https://www.ncpgambling.org" target="_blank"
               rel="noopener noreferrer">ncpgambling.org</a></li>
          <li><strong>United Kingdom</strong> — GamCare, 0808 8020 133.
            <a href="https://www.begambleaware.org" target="_blank"
               rel="noopener noreferrer">begambleaware.org</a></li>
          <li><strong>Canada</strong> — ConnexOntario, 1-866-531-2600</li>
          <li><strong>Anywhere</strong> — Gamblers Anonymous,
            <a href="https://www.gamblersanonymous.org" target="_blank"
               rel="noopener noreferrer">gamblersanonymous.org</a></li>
        </ul>
        <p>Most sportsbooks also offer deposit limits, time-outs and
        self-exclusion. Using them is a sign of good process, not weakness.</p>`,
        "var(--good)")}
    </div>

    <div class="section-title">Contact
      <span class="sub">— a real address, answered by the person who builds
      this. It was only in the terms before, which is where nobody looks.</span></div>
    <article class="card about-card">
      <div class="about-body">
        <p>Something broken, something wrong on a page, a question about your
        account or your subscription:
        <a href="mailto:qellysbook@gmail.com">qellysbook@gmail.com</a>.
        The Discord is where the picks get argued about —
        <a href="#discord">the invite lives here</a> — and the
        <a href="#methodology">methodology page</a> answers most questions
        about how a number was made before an email has to.</p>
      </div>
    </article>

    <div class="ls-note" style="margin-top:18px">
      In one sentence: <strong>we gather every number in one place and tell you
      when a price looks wrong — you decide what, if anything, to do about
      it, and the result is never guaranteed.</strong>
    </div>`;
  revealChildren(host);
}
//: Their rows on the Features page, which the store app leaves off too.
const STORE_APP_ROWS = new Set(["Prediction market", "Informed flow", "Top traders", "Rocket Radar"]);

/* ============================================================
   Market Scanner — arbitrage / middles / low holds / sharp money
   (moved here from app.js 2026-10-29; app.js keeps the stub)
   ============================================================ */
/* The face/logo the other boards lead with (Ethan, 2026-08-17: "the
   line shopping page doesnt show any headshots"). Guarded, because a
   payload built before the scanner rows carried player/team should
   render the row it always rendered, not a broken avatar. */
function scanMark(t) {
  return (t.player || t.team)
    ? `<span class="pick-id" style="flex-shrink:0">${betMark(t, 26)}</span>` : "";
}

function scanPairRow(p, extra) {
  /* v5: the book's row. The two legs read on the sub-line; `extra` is
     the right column — a number over its detail (.hd-state). */
  const leg = (side, l) => `${side} ${escapeHtml(String(l.line))} @ ${escapeHtml(l.book)} ${american(l.odds)}`;
  return `<div class="hd-row hd-scan">${scanMark(p)}<div class="hd-what"><b>${escapeHtml(p.bet)}</b>
      <span>${leg("Over", p.over)} · ${leg("Under", p.under)}</span></div>
    <div class="hd-state">${extra}</div></div>`;
}

/* AN EMPTY SECTION SAYS IT ONCE. On a quiet board every one of the
   scanner's six sections drew a section head, its sub, and a card
   holding one sentence saying there was nothing in it — six heads and
   six boxes around nothing, a screen and a half on a phone before the
   sentence at the bottom that says what the page is for (Ethan,
   2026-09-22: "cluttered"). With rows, the full head and its card
   draw as before. Without, the section is one row: its name and the
   reason, in the empty-panel voice, no box. */
function scanSection(title, sub, rows, rowFn, emptyText) {
  if (!rows.length) {
    return `<div class="scan-empty" title="${escapeAttr(sub)}"><b>${title}</b>
      <span class="panel-empty">${escapeHtml(emptyText)}</span></div>`;
  }
  return `<div class="section-title">${title}
      <span class="sub">— ${sub}</span></div>
    <div class="hd-card">
      ${rows.map(rowFn).join("")}
    </div>`;
}

/* A MIDDLE, IN DOLLARS (audit V-19, roadmap #47). The engine's numbers
   are per 1u on EACH leg, so "+184% both win" read as a return on the
   whole stake and the "Total stake" box above the section was ignored.
   The split here is the equal-payout one: each leg staked in proportion
   to 1/decimal price, so landing on either side alone returns the same
   amount and the worst case is one number. */
function scanMiddleSplit(m, stake) {
  const dec = (a) => (a > 0 ? 1 + a / 100 : 1 + 100 / Math.abs(a));
  const dO = dec(Number(m.over.odds)), dU = dec(Number(m.under.odds));
  const inv = 1 / dO + 1 / dU;
  const so = stake * (1 / dO) / inv, su = stake - so;
  const one = so * dO;                     // either leg alone pays this
  return { so, su, worst: one - stake, both: 2 * one - stake };
}

/* Group the middles by player, best first, and flag a leg two rows share.
   Sorted by EV where the sport has an outcome distribution and by window
   width after that, and the row says which ranking it is under. The
   engine sends overlapping permutations (one cheap Over against three
   Unders is three rows); a reader who takes two of them has bet the
   shared leg twice. */
function scanMiddleGroups(middles) {
  const legKey = (side, l) => `${side}|${l.book}|${l.line}|${l.odds}`;
  const rows = (middles || []).slice().sort((a, b) =>
    ((b.ev_per_unit != null) - (a.ev_per_unit != null))
    || ((b.ev_per_unit ?? 0) - (a.ev_per_unit ?? 0))
    || ((b.gap || 0) - (a.gap || 0)));
  const seen = new Set();
  const groups = new Map();
  for (const m of rows) {
    const legs = [legKey("Over", m.over), legKey("Under", m.under)];
    const shared = legs.filter((k) => seen.has(k)).map((k) => k.split("|").slice(0, 2).join(" at "));
    legs.forEach((k) => seen.add(k));
    const who = m.player || m.bet;
    if (!groups.has(who)) groups.set(who, []);
    groups.get(who).push({ ...m, shared });
  }
  return [...groups.entries()].map(([who, list]) => ({ who, list }));
}

function scanMiddleRow(m, stake) {
  const sp = scanMiddleSplit(m, stake);
  const money = (v) => `${v < 0 ? "−" : "+"}$${Math.abs(v).toFixed(2)}`;
  const head = m.ev_per_unit != null
    ? `<b class="hd-pl" style="color:${m.ev_per_unit >= 0 ? "var(--good)" : "var(--text-mute)"}">${m.ev_per_unit >= 0 ? "+" : ""}${(m.ev_per_unit * 100).toFixed(1)}% EV</b>`
    : `<b class="hd-pl">${escapeHtml(String(m.gap))}-point window</b>`;
  const sub = `$${sp.so.toFixed(0)} Over / $${sp.su.toFixed(0)} Under · both win ${money(sp.both)} · one wins ${money(sp.worst)}${
    m.middle_prob != null ? ` · lands in the window ${(m.middle_prob * 100).toFixed(0)}% of the time`
                          : " · no outcome history for this market, so not EV-ranked"}${
    m.shared.length ? `<span class="hd-warn">${icon("warn")} shares the ${escapeHtml(m.shared.join(" and "))} with a row above — fill one of them, not both</span>` : ""}`;
  return scanPairRow(m, `${head}<span>${sub}</span>`);
}

function renderScanner() {
  const host = document.getElementById("scanner-body");
  if (!host) return;
  // Guarded like its neighbours in the same cascade. renderAll() returns
  // early on null data so this is not reachable through it today, but the
  // stake input re-calls this function directly and one unguarded
  // dereference in a render is what the prop page just paid for.
  // Read once, guarded: opened before the board answered (a cold open)
  // `d.odds_status` below threw (tests/test_cold_open.py).
  const d = state.data || {};
  const scan = d.market_scan || {};
  const arbs = scan.arbs || [], middles = scan.middles || [], lows = scan.low_holds || [];

  // The scanner feeds on price DISAGREEMENT, which mostly appears when one
  // book moves before the others. On cached prices (one frozen frame per
  // budget pull) empty sections are the norm, not a bug — say so up front.
  const os = d.odds_status || {};
  const freshness = os.source === "cache"
    ? `<div class="ls-note">Prices are from the last budgeted pull (cached — no
       API spend). Arbs and middles come from catching books mid-move, so a
       single frozen snapshot rarely shows them; scanning sharpens when pulls
       resume normal frequency after the credit reset.</div>`
    : "";

  // Sharp money: anchor picks (priced off the sharp book's fair value) and
  // steam moves (several books re-pricing together = pro money footprint).
  const anchors = (d.game_bets || []).filter((b) =>
    (b.reasons || []).join(" ").toLowerCase().includes("sharp"));
  const steam = (d.recommendations || [])
    .filter((r) => r.line_move && r.line_move.steam)
    .map((r) => ({ r, m: r.line_move }));
  // PROPS A BOOK PRICES BETTER THAN THE SHARP BOOK'S FAIR (engine/sharpvalue,
  // 2026-10-29): the basketball and hockey rows carry `sharp_value`; a
  // football prop priced off the sharp pair (`sharp_anchored`) is the same
  // finding in its own fields. One market against a sharper one, no model.
  const sharpProps = (d.recommendations || []).map((r) => {
    if (r.sharp_value) return { r, v: r.sharp_value };
    const ev = Number(r.ev_per_unit) || 0;
    if (r.sharp_anchored && r.sharp_fair != null && ev >= 0.02 && ev <= 0.15) {
      return { r, v: { side: r.side, odds: r.odds, book: r.book, fair: r.sharp_fair, ev, suspect: ev > 0.07 } };
    }
    return null;
  }).filter(Boolean).sort((a, b) => b.v.ev - a.v.ev).slice(0, 12);

  const stake = state.scanStake || 100;
  const stakeInput = `<div class="ls-note scan-stake-row">
    Total stake for the splits below: $
    <input id="scan-stake" class="scan-stake" type="number" min="10" step="10" value="${stake}" />
  </div>`;

  // With seven books on every prop, hundreds of quotes sit a point below
  // consensus. The board shows the biggest gaps and says how many exist.
  const staleNote = () => {
    const st = (d.market_scan && d.market_scan.stale) || [];
    const total = st.length ? (st[0].total_found || st.length) : 0;
    return total > st.length
      ? `showing the ${st.length} biggest gaps of ${total} found · ` : "";
  };

  const staleRow = (t) => `<div class="hd-row hd-scan">${scanMark(t)}<div class="hd-what"><b>${escapeHtml(t.bet)}</b>
      <span>${escapeHtml(t.book)} ${american(t.odds)} · ${(t.other_books || []).length
        ? escapeHtml(t.other_books.join(", ")) : `the other ${plural(t.books_compared - 1, "book")}`} ${
        t.books_compared - 1 === 1 ? "prices" : "average"} it ${american(t.fair_odds)}</span></div>
    <div class="hd-state" title="How much less likely this book says the bet is than the other books do, in percentage points of implied probability"><b class="hd-pl" style="color:var(--good)">${t.gap_pts.toFixed(2)} pts cheaper</b>
      <span>implied ${(t.implied * 100).toFixed(1)}% here, ${(t.consensus * 100).toFixed(1)}% elsewhere</span></div></div>`;

  const scanFoot = `<p class="list-note">Positive-EV bets live on the
      <b>Recommended</b> and <b>Edge Board</b> pages — that’s the model’s job. This page
      needs no model: it’s the books disagreeing with each other. Arbitrage and middle
      prices move fast; verify at the book before betting. Books limit accounts that
      only arb — mix it into normal betting.</p>`;
  const stale = (d.market_scan && d.market_scan.stale) || [];
  const longs = (d.market_scan && d.market_scan.longshots) || [];
  /* v5: A QUIET BOARD IS ONE CARD. Six sections each drawing their own
     "nothing here" row made the page a list of apologies; when all six
     are empty it rests like the deck — one line behind the paused dot,
     the doors to the pages that are never empty, the note. A board
     with anything on it draws its sections as before, the empty ones as
     one row each (scanSection), and asks for a stake only when there is
     a split to size. */
  if (!stale.length && !longs.length && !arbs.length && !middles.length && !lows.length
      && !anchors.length && !steam.length) {
    host.innerHTML = `${freshness}<div class="hd-quiet lv-quiet"><i class="live-dot paused"></i>Nothing out of
      line right now — no stale lines, no plus-money props, no arbs, no middles, no low holds,
      nothing sharp-flagged. The scanner checks every refresh; gaps open when one book moves
      before the others, and they last minutes.</div>${boardEmptyDoors("scanner")}${scanFoot}`;
    bindEmptyDoors(host);
    return;
  }
  host.innerHTML = freshness + (arbs.length || middles.length ? stakeInput : "")
    + scanSection("Stale lines",
      staleNote()
      + "a book pricing a side cheaper than every other book. No forecast involved — "
      + "measured on 30,448 harvested quotes, taking these beat the closing consensus "
      + "64.8% of the time for +1.49 points of CLV (z=11.6). Verify the price is still "
      + "up before betting; that is the whole game here",
      (d.market_scan && d.market_scan.stale) || [], staleRow,
      "No book is currently out of line with the field. This fills in as books "
      + "update at different speeds — most often right after lineups post.")
    + scanSection("Priced against you — plus-money props",
      "not a play, an avoidance rule. Measured on 27,226 settled quotes joined to real "
      + "results: backing plus-money props cost -16.7% per unit against -6.5% for short "
      + "prices — the books shade big payouts 2.6x harder. No forecast is involved and "
      + "none helps; this is what the PRICE costs before anyone has a view on the player",
      (d.market_scan && d.market_scan.longshots) || [],
      (t) => `<div class="hd-row hd-scan">${scanMark(t)}<div class="hd-what"><b>${escapeHtml(t.bet)}</b>
          <span>${escapeHtml(t.book)} ${american(t.odds)} · implied ${(t.implied * 100).toFixed(1)}%${
            t.grade ? ` · graded ${escapeHtml(t.grade)}` : ""}</span></div>
        <div class="hd-state"><b class="hd-pl" style="color:var(--bad)">${(t.measured_roi * 100).toFixed(1)}% historically</b>
          <span>${escapeHtml(t.band)} band</span></div></div>`,
      "No plus-money quotes on today’s board — main props or long shots. That’s the cheap place to be.")
    + scanSection("Arbitrage", "opposite sides priced so a margin is locked whichever way it lands — IF both legs fill at the shown prices before they move. Rare across US books and gone in minutes",
      arbs, (a) => {
        const so = stake * a.stake_over_pct, su = stake * (1 - a.stake_over_pct);
        const ret = stake * a.profit_pct;
        const suspect = a.suspect
          ? `<span class="hd-warn">${icon('warn')} 5%+ edge — likely a stale line or void risk; verify at both books</span>` : "";
        return scanPairRow(a,
          `<b class="hd-pl" style="color:var(--good)">+${(a.profit_pct * 100).toFixed(2)}% · $${ret.toFixed(2)} locked</b>
           <span>$${so.toFixed(0)} Over / $${su.toFixed(0)} Under</span>${suspect}`);
      },
      "No arbitrage pairs right now. Real arbs across legal US books appear a few times a week and last minutes — this scanner checks every refresh.")
    + (middles.length ? `<div class="section-title">Middles
        <span class="sub">— Over at a low line + Under at a higher one: land between them and BOTH win; miss and one leg pays for the other, less the vig. Grouped by player, best first; dollars are for the stake above</span></div>
      <div class="hd-card">${scanMiddleGroups(middles).map(({ who, list }) =>
        scanMiddleRow(list[0], stake) + (list.length > 1 ? `<details class="scan-more"><summary>${
          plural(list.length - 1, "more window")} on ${escapeHtml(who)}</summary>${
          list.slice(1).map((m) => scanMiddleRow(m, stake)).join("")}</details>` : "")).join("")}</div>`
      : scanSection("Middles", "", [], null,
        "No middle windows open — books currently agree on every line. Gaps open when one book moves before the others."))
    + scanSection("Low holds", "two-sided quotes under 2% combined juice — a turnover feature, not a profit feature: the cheapest way to churn promo/rollover volume or keep an account looking recreational",
      lows, (h) => scanPairRow(h,
        `<b class="hd-pl">${(h.hold_pct * 100).toFixed(1)}% hold</b>
         <span>≈ $${(h.cost_per_1k != null ? h.cost_per_1k : h.hold_pct * 1000).toFixed(0)} per $1,000 bet through</span>`),
      "No low-hold pairs on the current board.")
    + `<div class="section-title">Sharp money
        <span class="sub">— where the professional side of the market is</span></div>
      <div class="hd-card">
        ${anchors.map((b) => `<div class="hd-row hd-scan"><div class="hd-what"><b>${escapeHtml(b.pick_label || "")}</b>
              <span>${escapeHtml(b.matchup || "")} · priced off the sharp book’s fair value</span></div>
            <div class="hd-num"><span class="hd-o">${american(b.odds)}</span>
              <span class="hd-p">+${((b.ev_per_unit || 0) * 100).toFixed(1)}% EV</span></div></div>`).join("")}
        ${sharpProps.map(({ r, v }) => `<div class="hd-row hd-scan sharp-prop">${scanMark(r)}<div class="hd-what"><b>${
              escapeHtml(r.player || "")} ${String(v.side).toUpperCase() === "UNDER" ? "Under" : "Over"} ${
              escapeHtml(String(r.line))} ${escapeHtml(r.market_label || "")}</b>
              <span>${escapeHtml(v.book || "")} ${american(v.odds)} pays more than the sharp book’s fair (${
                Math.round((Number(v.fair) || 0) * 100)}%)${v.suspect
                ? " · a gap this big usually means news moved the sharp price first — check it still stands" : ""}</span></div>
            <div class="hd-num"><span class="hd-o">${american(v.odds)}</span>
              <span class="hd-p">+${((Number(v.ev) || 0) * 100).toFixed(1)}% EV</span></div></div>`).join("")}
        ${steam.map(({ r, m }) => {
          // Every alert answers: is this still bettable, or already missed?
          const age = m.moved_ago_min;
          const cls = (age != null && age > 180)
            ? ["Stale", "", "old move — informational only"]
            : ((r.ev_per_unit || 0) > 0
               ? ["Live", "good", "value still available near the sharp number"]
               : ["Chase", "warn", "line already moved past it — do not follow"]);
          return `<div class="hd-row hd-scan"><span class="hd-rank">${iconMark("hot")}</span><div class="hd-what"><b>${escapeHtml(r.player)} ${escapeHtml(r.market_label || "")}</b>
              <span>steam — several books moved together, ${m.verdict === "with" ? "toward" : "against"} our ${escapeHtml(r.side || "")}${age != null ? ` · ${age < 60 ? age + "m" : Math.round(age / 60) + "h"} ago` : ""} · ${cls[2]}</span></div>
            <div class="hd-state"><span class="hd-chip ${cls[1]}">${cls[0]}</span>
              <span>${Math.abs(m.delta || 0) > 1e-9 ? `${escapeHtml(String(m.open))} → ${escapeHtml(String(m.current))}` : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`}</span></div></div>`;
        }).join("")}
        ${!anchors.length && !steam.length && !sharpProps.length ? `${panelEmpty("Nothing sharp-flagged right now. Sharp-anchor picks and props appear when a book’s price beats the sharp book’s fair value; steam appears when several books re-price together inside an hour.")}` : ""}
      </div>
      ${scanFoot}`;
  armScanCopy(host);

  const inp = document.getElementById("scan-stake");
  if (inp) inp.addEventListener("change", () => {
    state.scanStake = Math.max(10, parseFloat(inp.value) || 100);
    renderScanner();
  });
  renderBookReport();
}

/* COPY A ROW (audit V-23 / O26). A shopper takes the two books and two
   prices to the books' own apps; retyping them is where a −110 becomes a
   −101. Every scanner row gets a Copy button that puts the row's own
   words on the clipboard: the bet, both legs, and the number beside it. */
function scanRowText(row) {
  const clean = (el) => ((el || {}).textContent || "").replace(/\s+/g, " ").trim();
  const st = row.querySelector(".hd-state");
  const state = st ? [...st.children].map(clean).filter(Boolean).join(" · ") || clean(st) : "";
  return [clean(row.querySelector(".hd-what b")), clean(row.querySelector(".hd-what span")), state]
    .filter(Boolean).join(" · ");
}

function armScanCopy(host) {
  if (!host) return;
  host.querySelectorAll(".hd-row.hd-scan").forEach((row) => {
    if (row.querySelector(".scan-copy")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "scan-copy";
    b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy this row");
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      try { await navigator.clipboard.writeText(scanRowText(row)); b.textContent = "Copied"; }
      catch (err) { b.textContent = "Copy failed"; }
      setTimeout(() => { b.textContent = "Copy"; }, 1500);
    });
    row.appendChild(b);
  });
}

/* The book report card (roadmap #7) — which book prices sharpest,
   measured off our own line-history snapshots by the daily chores
   (engine/booksharp.payload). Facts about BOOKS, free file, and it
   belongs on this page because this page is where the books already
   argue with each other. Appends to the scanner host, never replacing
   what renderScanner just drew. */
let _brCache = null, _brAt = 0;

/* Whether our own sharp-book list survives the table above it.

   `engine/booksharp.compare_to_the_list` calls itself "the point of the
   whole module" and it is right: the ranking is interesting, but the
   question worth asking is whether the hand-written list — the one
   `engine.odds.is_sharp_book` consults before we will quote a book as a
   reference price — is backed by anything. The build has computed that
   on every cycle and published it in `vs_list`. No page named the
   field, so the answer shipped to the browser and stopped there.

   IT RENDERS WHEN THE ANSWER IS "the list checks out" TOO. A check that
   is invisible whenever it passes is a check nobody believes when it
   fails, and this one is a claim about our own judgement. */

/* Below this many ranked books, "top half" and "bottom half" are two
   and two, and saying a book is in the wrong half of a four-row table
   dressed as three is a stronger claim than the sample can carry. */
const VS_MIN_BOOKS = 4;

function bookVsListHTML(vs) {
  if (!vs) return "";                       // a build older than the field
  const n = Number(vs.n_ranked) || 0;
  if (!n) return "";                        // the card is not drawn either
  const name = (a) => (a || []).map((b) => escapeHtml(b)).join(", ");
  if (n < VS_MIN_BOOKS) {
    return `<p class="br-vs">Only ${plural(n, "book")} clears the sample bar
      so far — too thin to say which half of this table anybody is in, which
      is the check this line is here to make.</p>`;
  }
  const named = vs.asserted_sharp || [];
  const bad = vs.asserted_but_not || [];
  const unnamed = vs.sharp_but_unnamed || [];
  const bits = [];
  if (!named.length) {
    bits.push(`None of the books we treat as sharp has enough tracked series
      here yet, so this table cannot check that list.`);
  } else {
    bits.push(`We treat ${name(named)} as sharp — the ${
      pluralWord(named.length, "book", "books")} allowed to set the reference
      price we measure a quote against.`);
    bits.push(bad.length
      ? `<b>${name(bad)}</b> ${pluralWord(bad.length, "prices", "price")} in
         the bottom half of this table. We call ${
         pluralWord(bad.length, "it", "them")} sharp; our own snapshots do not.`
      : `Every one of them sits in the top half of this table.`);
  }
  if (unnamed.length) {
    bits.push(`<b>${name(unnamed)}</b> ${
      pluralWord(unnamed.length, "is", "are")} in the measured top three and
      not on that list.`);
  }
  bits.push(`This compares early prices to the closing consensus and nothing
    else, and it has not changed which books we shop.`);
  return `<p class="br-vs">${bits.join(" ")}</p>`;
}

async function renderBookReport() {
  const host = document.getElementById("scanner-body");
  if (!host || document.getElementById("bookreport-card")) return;
  if (!_brCache || Date.now() - _brAt > 300000) {
    try {
      const res = await boardFetch("data/bookreport.json", { cache: "no-cache" });
      _brCache = res.ok ? await res.json() : null;
      _brAt = Date.now();
    } catch (e) { _brCache = null; }
  }
  // NO state.view gate, deliberately: renderScanner is an UNCONDITIONAL
  // renderer — its host prefills on every load whatever page is showing
  // — so a view gate here would leave the card missing whenever the
  // last load landed elsewhere, which is most navigations (the futures
  // lesson, from the other side). The host is hidden with its view.
  const d = _brCache;
  const ranked = ((d || {}).books || []).filter((b) => b.ranked);
  if (document.getElementById("bookreport-card")) return;
  if (!ranked.length) {
    // Said once, in the empty-row voice (audit V-19), rather than a card
    // that silently never appears on a box with too little line history.
    host.insertAdjacentHTML("beforeend", `<div id="bookreport-card" class="scan-empty"><b>Book report card</b>
      <span class="panel-empty">Not ranked yet — a book is ranked once enough of its early prices
      have a closing consensus to be measured against.</span></div>`);
    return;
  }
  const worst = Math.max(...ranked.map((b) => b.mae_pts || 0), 0.1);
  host.insertAdjacentHTML("beforeend", `
    <div id="bookreport-card">
      <div class="section-title br-head">Book report card
        <span class="sub">— which book prices sharpest, measured from our own line
        history: each book’s early prices against that market’s closing consensus.
        Lower error = sharper. A high “moved first” rate with a high error is a book
        that moves first and wrong.</span></div>
      <div class="card" style="padding:0">
        ${ranked.map((b, i) => `
          <div class="rec-row mid">
            <span style="opacity:.5;min-width:18px;font-size:.85em">${i + 1}</span>
            <span style="min-width:120px;font-weight:700">${escapeHtml(b.book)}</span>
            <span class="rb-bar" style="flex:1;min-width:120px"><i style="width:${
              Math.min(100, 100 * (b.mae_pts || 0) / worst).toFixed(0)}%"></i></span>
            <span style="min-width:104px;text-align:right;font-variant-numeric:tabular-nums">${
              (b.mae_pts || 0).toFixed(2)} pts off close</span>
            <span style="min-width:110px;text-align:right;opacity:.75;font-variant-numeric:tabular-nums">moved first ${
              Math.round(100 * (b.lead_rate || 0))}% · n=${b.n}</span>
          </div>`).join("")}
      </div>
      ${bookVsListHTML(d.vs_list)}
      <p style="opacity:.55;font-size:.85em;margin-top:8px">Cut ${escapeHtml(String(d.generated_at || "").slice(0, 10))}
        from ${d.min_series}+ tracked series per book. Books below the sample bar are unranked, not absent.</p>
    </div>`);
}

/* THE ALERTS PAGE (moved from app.js 2026-10-29, the way the Scanner was):
   this phone's alerts and their switches, Take a break, the watches and
   the feed. Fetched the first time the page opens. */
function renderPushZone(note) {
  const host = document.getElementById("push-zone");
  if (!host) return;
  const kind = pushKind(), saved = pushSaved();
  if (!kind) { host.innerHTML = ""; return; }
  const on = !!(saved && saved.endpoint);
  const signedIn = !!(_acctUser && _acctUser.signed_in);
  const topics = ((saved && saved.topics) || ["posted", "settled"]).concat((saved && saved.mine) || []);
  // A SETTINGS SCREEN, NOT A FORM (2026-10-25, docs/VISUAL_AUDIT.md S9): one
  // switch for the phone, a switch a row for each kind of alert, the way a
  // phone's own notification settings read. Until alerts are on, a kind's
  // switch is only a choice.
  const box = (t, label, off) => setItem({ title: label, end: setSwitch(topics.includes(t),
    `data-push-topic="${t}" aria-label="${label}"${off ? " disabled" : ""}`) });
  host.innerHTML = (kind === "home-screen"
    ? setGroup("Alerts on this phone", [setItem({ ico: "bell", tone: "red", title: "Add Qellys to your Home Screen",
        sub: "Then open it from there and turn alerts on here" })],
      "On iPhone, Apple sends a site’s alerts only once it is on your Home Screen: tap Share, then <b>Add to Home Screen</b>.")
    : setGroup("Alerts on this phone", [
        setItem({ ico: "bell", tone: "red", title: "Alerts", sub: on ? "On for this phone" : "Off",
                  end: setSwitch(on, `data-push-go="${on ? "off" : "on"}" aria-label="Alerts on this phone"`) }),
        box("posted", "Tonight’s picks are up"),
        box("settled", "Last night is graded"),
      ], "A tap on your lock screen when tonight’s picks go up and when last night is graded. "
        + "Counts and the record only — never a pick on a lock screen.")
      + setGroup("Yours", [
        box("watches", "My teams and players make the board (members see which)", !signedIn),
        box("bets", "My parlay: on, last leg, settled", !signedIn),
        box("kickoff", "My teams’ games, 10 minutes before they start", !signedIn),
        box("clutch", "Big moments in games I follow", !signedIn),
        box("finals", "Final scores of games I follow", !signedIn),
        box("closegame", "Close games: my teams or my bets, the last minutes within one score", !signedIn),
        box("news", "Injury news: a status change for a player I follow or bet on", !signedIn),
        box("today", "This morning: my teams’ games today, with the times", !signedIn),
        box("lines", "A line moves 2% or a point from my bet, before it starts", !signedIn),
        box("lineup", "My fantasy lineup: a starter out or on a bye", !signedIn),
        // When you've been away (engine/engagement, engine/lifecycle): your
        // team's next game or what's new, your week and the board's, once a
        // week at most — whatever the activity log's switch.
        box("away", "When I’ve been away: my team’s next game, what’s new or my week, once a week at most", !signedIn),
      ], signedIn ? "Your own watches, saved parlays and fantasy lineup (the Sleeper league your league desk last opened). Only your words and your ticket, only on phones you are signed in on."
        : "Sign in for alerts on your own watches and saved parlays.")
      // TAKE A BREAK (engine/pushalerts.pause; the research's one-tap pause):
      // a day or a week of nothing, and the day's limit said plainly.
      + (on ? setGroup("Take a break", [(saved.paused_until || 0) * 1000 > Date.now()
          ? setItem({ ico: "clock", tone: "amber", title: "Paused", sub: `Until ${escapeHtml(tzTime(saved.paused_until * 1000,
              { weekday: "short", hour: "numeric", minute: "2-digit" }))}`, end: `<button type="button" class="set-val" data-push-pause="0">Resume</button>` })
          : setItem({ tag: "div", ico: "clock", tone: "amber", title: "Pause every alert",
              end: `<span class="set-seg"><button type="button" data-push-pause="24">A day</button><button type="button" data-push-pause="168">A week</button></span>` })],
        "Five alerts a day at most (eight on a plan), none overnight where you are. Gambling problem? Call or text 1-800-GAMBLER.") : ""))
    + (note ? `<p class="set-foot push-note" role="status">${escapeHtml(note)}</p>` : "");
  // Off, each kind is a choice for later, drawn dimmer than a live one.
  host.classList.toggle("push-off", !on);
  host.querySelectorAll("[data-push-pause]").forEach((el) => el.addEventListener("click", async () => {
    try {
      const got = await pushSend("pause", { endpoint: saved.endpoint, hours: Number(el.dataset.pushPause) });
      if (got.paused_until) track("limit_set", `pause${el.dataset.pushPause}`);
      try { localStorage.setItem(PUSH_KEY, JSON.stringify(Object.assign({}, pushSaved(), { paused_until: got.paused_until || 0 }))); } catch (e) {}
      renderPushZone(got.paused_until ? "Paused. Nothing comes to this phone until then." : "Alerts are back on.");
    } catch (err) { renderPushZone(err && err.message ? err.message : "That did not work — try again."); }
  }));
  host.querySelectorAll("[data-push-go], [data-push-topic]").forEach((el) => el.addEventListener(
    "click", async () => {
      if (el.disabled) return;
      if (el.matches("[data-push-topic]")) {
        el.setAttribute("aria-checked", el.getAttribute("aria-checked") === "true" ? "false" : "true");
      }
      const picked = [...host.querySelectorAll('[data-push-topic][aria-checked="true"]')].map((c) => c.dataset.pushTopic);
      const turnOff = el.dataset.pushGo === "off" || (el.matches("[data-push-topic]") && !picked.length);
      if (el.matches("[data-push-topic]") && !on) return;           // just a choice until it is on
      try {
        if (turnOff) {
          await pushOff(saved);
          try { localStorage.removeItem(PUSH_KEY); } catch (e) {}
          renderPushZone("Alerts are off on this phone.");
        } else {
          pushRemember(await pushOn(picked.length ? picked : ["posted", "settled"], saved && saved.leagues));
          if (!on) track("push_on", "alerts");
          buzz("tap");
          renderPushZone(on ? "Saved." : "Alerts are on. The next one comes when a board goes up.");
        }
      } catch (err) {
        renderPushZone(err && err.message ? err.message : "That did not work — try again.");
      }
    }));
}

function renderAlerts() {
  const host = document.getElementById("alerts-body");
  if (!host) return;
  const d = state.data || {};
  // Friends first: fetch once if signed in and redraw when it lands.
  // Seen is marked AFTER the rows have actually been shown — a
  // background poll must not eat the unread state.
  //
  // `_acctUser` is null until boot's acctWho() answers, and a cold load
  // of #alerts renders before that. Null means UNKNOWN, not signed out:
  // ask, then redraw if the answer is yes — otherwise a signed-in
  // reader who lands here directly never sees the inbox at all.
  if (!_acctUser) {
    acctWho().then((u) => {
      if (u && u.signed_in && state.view === "alerts") renderAlerts();
    });
  } else if (_acctUser.signed_in && !_socCache) {
    socFetch().then((got) => {
      if (got && state.view === "alerts") renderAlerts();
    });
  }
  const _frUnseen = !!(_socCache && _socCache.inbox && _socCache.inbox.unseen);
  if (_frUnseen && state.view === "alerts") {
    setTimeout(() => {
      fetch("/api/social/seen", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: "{}" })
        .then(() => { if (_socCache) _socCache.inbox.unseen = 0; })
        .catch(() => {});
    }, 1200);
  }
  // Render 14's list: an icon chip, the alert on one line, the CONDITION
  // that fired it underneath. What never crosses is the render's per-row
  // toggle and "Create New Alert" — this page is a digest of feeds we
  // already hold, not a subscription service, and a switch that turns
  // nothing on would be a lie you can click.
  const alRow = (ic, tone, title, cond, right) => `
    <div class="al-row">
      <span class="al-ic ${tone}">${icon(ic, 15)}</span>
      <span class="al-t"><b>${title}</b><span class="al-c">${cond}</span></span>
      ${right || ""}
    </div>`;
  const moved = (d.recommendations || []).filter((r) =>
    r.move_delta != null && (Math.abs(r.move_delta) >= 0.5 || r.move_steam));
  const inj = (d.injury_watch || []).filter((i) => i && i.player);
  const k = _railDeskCache || {};
  const recs = [...(k.rows || []).filter((r) => r.rec),
                ...(k.weather || []).filter((r) => r.rec)];
  const cats = [["all", "All alerts", moved.length + inj.length + recs.length],
                ["moves", "Line moves", moved.length],
                ["injuries", "Injuries", inj.length],
                ["desk", "The desk", recs.length]];
  if (!cats.some(([kk, , n]) => kk === _alFilter && n)) _alFilter = "all";
  const chips = `<div class="al-cats">${cats.filter(([kk, , n]) => n || kk === "all")
    .map(([kk, label, n]) => `<button class="al-cat${kk === _alFilter ? " on" : ""}"
      type="button" data-act="alSet" data-arg="${kk}">${escapeHtml(label)}
      <span class="al-n">${n}</span></button>`).join("")}</div>`;
  const show = (kk) => _alFilter === "all" || _alFilter === kk;
  const sections = [];
  if (moved.length && show("moves")) {
    sections.push(`<div class="section-title">Line movement
        <span class="sub">— tonight’s picks whose line has moved since open. Steam =
        several books moved together, which is the market talking.</span></div>
      <div class="card al-list">${moved.slice(0, 12).map((r) => alRow(
        r.move_delta > 0 ? "rising" : "falling",
        r.move_delta > 0 ? "good" : "bad",
        `${escapeHtml(r.player)} ${escapeHtml(r.side || "")} ${r.line}`,
        `${escapeHtml(r.market_label || r.market || "")} moved
         ${r.move_delta > 0 ? "+" : ""}${r.move_delta} since open`,
        `<span class="kx-num" style="color:var(--${r.move_delta > 0 ? "good" : "bad"})">
           ${r.move_delta > 0 ? "+" : ""}${r.move_delta}</span>${r.move_steam
          ? `<span class="chip down">steam</span>` : ""}`)).join("")}</div>`);
  }
  if (inj.length && show("injuries")) {
    sections.push(`<div class="section-title">Injury watch
        <span class="sub">— designations touching tonight’s board.
        <a href="#injuries">Full report &#8594;</a></span></div>
      <div class="card al-list">${inj.slice(0, 12).map((i) => alRow(
        "warn", "warn", escapeHtml(i.player),
        `${i.team ? escapeHtml(i.team) + " · " : ""}on tonight’s board with a designation`,
        `<span class="chip down">${escapeHtml(i.status || "")}</span>`)).join("")}</div>`);
  }
  if (recs.length && show("desk")) {
    sections.push(`<div class="section-title">The desk
        <span class="sub">— paper recommendations live right now.
        <a href="#intel">The full board &#8594;</a></span></div>
      <div class="card al-list">${recs.slice(0, 6).map((r) => alRow(
        "gem", "brand", escapeHtml(r.title),
        `cleared the desk’s gate at ${(r.prob * 100).toFixed(0)}¢`,
        `${r.rec_side ? `<span class="chip ${r.rec_side === "YES" ? "up" : "down"}">${escapeHtml(r.rec_side)}</span>` : ""}
         <span class="kx-num">${(r.prob * 100).toFixed(0)}&cent;</span>`)).join("")}</div>`);
  }
  host.innerHTML = `<div id="push-zone"></div><div id="watch-zone"></div>`
    + friendInboxHTML()
    + `<div id="feed-zone"></div>`
    + (moved.length + inj.length + recs.length ? chips : "")
    // A free account: what is a member's here says so, rather than a quiet
    // page that would stay quiet (the moves, the desk and the feed are paid).
    + (isWalled() ? sections.join("") + memberLockHTML("Line moves and the desk are for members",
        "A member’s alerts also follow tonight’s picks: their line moves, edges as they appear and go, and the prediction desk.")
      : sections.join("") || `<div class="empty-slate">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">Nothing moving right now</div>
      <div class="es-sub">Alerts fill from four real feeds — the live board diff,
      line movement on tonight’s picks, the injury watch, and the prediction
      desk. A quiet page means a quiet slate, not a broken one.</div></div>`);
  renderPushZone();
  renderWatchZone();
  renderFeedZone();
  renderRailDesk();
}
