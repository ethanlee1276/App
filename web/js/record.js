/* THE RECORD PAGE — loaded the first time the Record page opens (app.js loadRoom,
   2026-10-24): the season's ledger, its rooms (by league, by market, by price), the calibration, the closing-line
   read, the calendar and the receipts.
   A classic script like app.js: it shares the page's globals, and each
   page's renderer here replaces app.js's stub of the same name. Every
   declaration was moved whole out of app.js, in order, with its own
   comments: nothing outside these pages calls any of it (chosen by
   TypeScript's own reading of the file, and checked by name against every
   other script and page). */
/* ---------------- routing ---------------- */
/* ============================================================
   Track Record — the journal, on the site
   ============================================================ */
/* The record page used its own bare `.stat` divs, which had almost no CSS —
   that alone is why it read as a spreadsheet bolted to a designed site. It
   now speaks the same component vocabulary as everything else: `.tile`, with
   a `lead` variant for the two numbers that actually decide whether the
   process is working (ROI and CLV). */
/* WHAT THIS RECORD LEAVES OUT, said next to it.

   Ethan, 2026-08-23: "i just dont want our data to be in the red since
   when we first started in july the model wasnt tuned yet and its not
   whats pulling bets now so we are displayong something thats hurting
   us." That is a fair reading of what the number MEANS — a −22% ROI
   earned by gates that no longer exist says nothing about the model
   running tonight, which is the argument the era split already makes.

   IT IS ONLY FAIR WHILE THE PAGE SAYS SO. A record scoped to a start
   date with no line admitting it is a curated record, and this site's
   whole claim is that it grades in public. So the note is not optional,
   not a tooltip, and not behind the "why?" collapse — it sits under the
   numbers it qualifies, it names the count it is leaving out, and the
   all-time figures are one click away inside it. If the disclosure ever
   feels like too much to show, that is the signal that the scoping has
   gone too far, not that the disclosure should go.

   Nothing to disclose draws nothing: a book with no picks before the
   epoch is not hiding anything, and a permanent notice about zero bets
   would be noise pretending to be candour. */
/* HOW MUCH OF THE RECORD HAS A REAL CLOSING LINE BEHIND IT.

   `ledger.clv_coverage` computes this on every export — its own comment
   calls it "the honest prerequisite for anything that wants to reason
   from CLV" — and until 2026-09-19 no page read it. The Model-vs-market
   room quotes closing-line value all over itself; a reader had no way to
   know whether that rested on every settled pick or on a tenth of them.

   Per-market coverage is already on `recClvBoard`'s rows as
   `with_close/settled`. This is the one-line whole-book version, which
   is what belongs beside an all-time claim. */
function recCoverageNote(cov) {
  const n = cov.settled || 0, w = cov.with_close || 0;
  if (!n) return "";
  const pct = (w / n) * 100;
  return `Closing lines are stored for ${w} of those ${n} picks (${
    pct.toFixed(0)}%) — every CLV number on this page is measured on `
    + (w === n ? "all of them." : "that share, not the whole book.");
}

function recEpochHTML(d, src) {
  const ep = (d || {}).record_epoch;
  // `src` is the scoped report on a sport scope and the whole payload on
  // "all"; either way its all_time is the one this note is about. A
  // scoped report without one (an older export) says nothing rather
  // than borrowing the whole journal's count.
  const at = (src || d || {}).all_time || {};
  const o = at.overall || {};
  const hidden = at.hidden_settled || 0;
  /* AND THE BENCH, DISCLOSED THE SAME WAY. A league whose board is
     being rebuilt is off this page entirely — asked for, and right for
     the league — but every other exclusion here is disclosed, and a
     reader has no way to tell a record that leaves nothing out from one
     that leaves a losing league out. A count, not the rows: no league
     is named and no bet is shown. */
  const benched = at.benched_settled || 0;
  const cov = (d || {}).clv_coverage || {};
  if (!ep || (!hidden && !benched) || !o.settled) return "";
  const roi = fmtRoi(o.roi);
  const left = hidden + benched;
  return `<details class="rec-epoch">
    <summary>Record shown from ${escapeHtml(formatGameDate(ep) || ep)} —
      ${left} settled pick${left === 1 ? "" : "s"} ${
      left === 1 ? "is" : "are"} not in these numbers</summary>
    <div>${hidden ? `${hidden} of them settled before that date. ` : ""}Those
      picks are still journaled, still graded and still train the
      model — nothing was deleted, and the samplers and calibration on this
      page still read every one of them. What changed on that date is the
      model, not the bookkeeping: the boards before it ran on gates that no
      longer exist, so their record is a fact about a system that is not
      picking tonight.
      ${benched ? `<br><br>A further <strong>${benched}</strong> settled
        pick${benched === 1 ? " is" : "s are"} from a league whose model is
        being rebuilt. That board is still published and still graded on its
        own page, at no risk, and none of it is counted here — so these
        numbers are the record of what this site is betting now, not of
        everything it has ever run.` : ""}
      <br><br>All-time${at.curve_from
        ? `, from the first journaled pick on ${escapeHtml(
            formatGameDate(at.curve_from) || at.curve_from)}`
        : ", including everything before that date"}, the book is
      <strong>${o.wins}\u2011${o.losses}\u2011${o.pushes || 0}</strong> at
      <strong>${roi}</strong> ROI on ${o.settled} settled picks.
      ${cov.settled ? `<br><br>${escapeHtml(recCoverageNote(cov))}` : ""}</div>
  </details>`;
}

/* A four-up grid of flex rows with five fixed-width columns each was clipping
   its own numbers — the net-units column ran off the right edge of every
   table. Fixed columns in a grid that is allowed to be narrow is the bug;
   these rows are a real grid whose label column is the one that gives. */
function recBucketTable(title, bucket) {
  const keys = Object.keys(bucket || {});
  if (!keys.length) return "";
  const anyClv = keys.some((k) => bucket[k].avg_clv != null);
  const rows = keys
    .sort((a, b) => (bucket[b].w + bucket[b].l) - (bucket[a].w + bucket[a].l))
    .map((k) => {
      const d = bucket[k];
      const net = d.net_u || 0;
      const n = d.w + d.l;
      const rate = n ? d.w / n : 0;
      const clv = anyClv
        ? `<span class="rb-clv" title="Average closing-line value — beating the close is the earliest sign a module earns">${
            d.avg_clv == null ? "—"
              : `${d.avg_clv >= 0 ? "+" : ""}${d.avg_clv.toFixed(2)}`}</span>` : "";
      const pct = `${(rate * 100).toFixed(0)}% win rate`;
      return `<div class="rb-row">
        <span class="rb-name" title="${escapeHtml(k)}">${escapeHtml(k)}</span>
        <span class="rb-bar" role="img" aria-label="${escapeHtml(`${k}: ${pct}`)}"
          title="${escapeHtml(pct)}"><i style="width:${(rate * 100).toFixed(1)}%"></i></span>
        <span class="rb-wl">${d.w}-${d.l}</span>${clv}
        <span class="rb-net ${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</span></div>`;
    }).join("");
  return `<div class="rec-bucket">
    <div class="rb-head">${escapeHtml(title)}</div>
    <div class="rb-rows${anyClv ? " has-clv" : ""}">
      <div class="rb-row rb-labels">
        ${/* The bar column carried an empty `.rb-bar` here, which drew
             its own grey track: a header row with a blank slot in it
             that looked like a rendering fault. It is a label row, so it
             gets a label. "Win" also gives the orange stub underneath a
             meaning — unlabelled, it read as a stray dash. */""}
        <span class="rb-name">&nbsp;</span><span class="rb-barh">Win</span>
        <span class="rb-wl">W-L</span>${anyClv ? `<span class="rb-clv">CLV</span>` : ""}
        <span class="rb-net">Net</span></div>
      ${rows}</div></div>`;
}

function recCurveChart(curve, opts = {}) {
  if (!curve || curve.length < 2) return "";
  const w = 640, h = 190, padL = 46, padR = 14, padT = 16, padB = 28;
  const cums = curve.map((p) => p.cum_u);
  let lo = Math.min(0, ...cums), hi = Math.max(0, ...cums);
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const x = (i) => padL + (i / (curve.length - 1)) * (w - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
  const path = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.cum_u).toFixed(1)}`).join(" L");
  const last = curve[curve.length - 1];
  const color = last.cum_u >= 0 ? "var(--good)" : "var(--bad)";
  // day_u is derivable from the running total, so a payload without it
  // gets the derived number instead of a TypeError. This mattered: a
  // fixture missing the field crashed recCurveChart, and because the
  // whole page is one template literal, the exception blanked EVERY
  // section of the Record page — one optional field, zero pages.
  const dayOf = (p, i) => (p.day_u != null ? p.day_u
    : p.cum_u - (i ? curve[i - 1].cum_u : 0));
  const dots = curve.map((p, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="${i === curve.length - 1 ? 3.4 : 2.4}" fill="${color}"/>`)
    .join("");
  // Scrubbing replaced the per-dot hover circles (2026-08-18, Ethan:
  // "glide your finger across it an it will show the data") — one
  // finger or cursor position, one label, no 10px targets to hunt for.
  const scrub = escapeAttr(JSON.stringify({
    padL, padR,
    l: curve.map((p) => `${p.date} · ${p.n} bet${p.n === 1 ? "" : "s"}`),
    v: curve.map((p, i) => {
      const dayU = dayOf(p, i);
      return `running ${p.cum_u >= 0 ? "+" : ""}${p.cum_u.toFixed(2)}u · day ${
        dayU >= 0 ? "+" : ""}${dayU.toFixed(2)}u`;
    }),
  }));
  /* WHERE THE MODEL CHANGED, on the curve itself.
     Ethan, 2026-08-23, holding the 1W and ALL charts side by side:
     "how has the mlb been doing so good lately and it's been showing on
     the weekly graph but it doesn't seem like the all time numbers r
     moving."

     They are moving — the week climbed 7.05u of a 25.82u hole — but the
     all-time line draws two different models as one continuous story, so
     the upturn reads as noise in a long decline instead of as the point
     where the board started pricing differently. A dashed rule at each
     era start is the cheapest way to say "everything left of this was
     priced by a model that no longer exists", which is the same thing
     the era table underneath says in words.

     Only eras that START INSIDE the visible window get a rule. A range
     chip showing the last week would otherwise stack every marker on the
     left edge, which says nothing and looks like a fault. */
  const eras = (opts.eras || []).filter((e) => e && e.from);
  const marks = eras.map((e) => {
    const i = curve.findIndex((p) => (p.date || "") >= e.from);
    if (i <= 0) return "";                       // absent, or before the window
    const px = x(i).toFixed(1);
    const d = String(e.from).slice(5).replace("-", "/");
    return `<line x1="${px}" y1="${padT}" x2="${px}" y2="${h - padB}"
        stroke="currentColor" stroke-width="1" stroke-dasharray="3 3"
        opacity="0.35"/>
      <text x="${px}" y="${padT - 5}" text-anchor="middle" font-size="9"
        fill="currentColor" opacity="0.5">${escapeHtml(d)}</text>`;
  }).join("");

  const yLabel = (v) => `<text x="${padL - 8}" y="${y(v) + 3.5}" text-anchor="end" font-size="10"
      fill="currentColor" opacity="0.45">${v >= 0 ? "+" : ""}${v.toFixed(1)}u</text>`;
  const grid = (v) => `<line x1="${padL}" y1="${y(v)}" x2="${w - padR}" y2="${y(v)}"
      stroke="currentColor" stroke-width="1" opacity="0.07"/>`;
  // The line alone floated in an empty box. Filling the area under it toward
  // the break-even axis is what makes a P&L curve read as a P&L curve at a
  // glance — above the dashed line is profit, below it is not.
  const area = `M${padL},${y(0)} L${path} L${x(curve.length - 1).toFixed(1)},${y(0)} Z`;
  const gid = `pnlfill${Math.random().toString(36).slice(2, 8)}`;
  const net = last.cum_u;
  const head = `
    <div class="section-title"><span class="st-ico">${icon("rising", 15)}</span>Running P&amp;L
      <span class="sub">— every settled pick, by slate date</span></div>`;
  return `
    ${opts.head === false ? "" : head}
    <div class="card rec-chart">
      <div class="rc-head">
        <div class="rc-net ${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</div>
        <div class="rc-span">${escapeHtml(curve[0].date)} → ${escapeHtml(last.date)}
          · ${curve.length} slate${curve.length === 1 ? "" : "s"}</div>
      </div>
      <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block" role="img"
           aria-label="Cumulative units won or lost over time" data-scrub="${scrub}">
        <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient></defs>
        ${grid(hi)}${lo < 0 ? grid(lo) : ""}
        <path d="${area}" fill="url(#${gid})" stroke="none"/>
        ${marks}
        <line x1="${padL}" y1="${y(0)}" x2="${w - padR}" y2="${y(0)}"
              stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" opacity="0.3"/>
        ${Math.abs(y(0) - y(hi)) > 14 ? yLabel(hi) : ""}${yLabel(0)}${
          lo < 0 && Math.abs(y(lo) - y(0)) > 14 ? yLabel(lo) : ""}
        <text x="${padL}" y="${h - 8}" font-size="10" fill="currentColor" opacity="0.45">${escapeHtml(curve[0].date)}</text>
        <text x="${w - padR}" y="${h - 8}" text-anchor="end" font-size="10" fill="currentColor" opacity="0.45">${escapeHtml(last.date)}</text>
        <path d="M${path}" fill="none" stroke="${color}" stroke-width="2.2"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
      </svg>
      <div class="rc-foot">Slide a finger (or the cursor) along the chart for each
        day’s bets. Flat units — every pick weighted by its stake, no bankroll
        compounding.</div>
    </div>`;
}

/* THE RECORD'S WINDOWS — one list, one state, two places to set it.
   Ethan's product audit, 2026-09-23, item 5: "allow users to open
   Lifetime → 90 Days → 30 Days". The running P&L has had range chips
   since 08-11; since this audit the same `_recRange` also moves the
   headline ribbon at the top of the page, so the chart and the
   number over it can never be reading different windows. Everything
   is cut from the curve the scope in view already ships (each day's
   w, l, n, stake at risk and units), so every sport has its windows
   and the engine runs no extra scan. Declarations, not a const: the
   page can render before this line has run. */
function recRanges() {
  return [["all", Infinity, "Lifetime"], ["3m", 90, "90 days"],
          ["1m", 30, "30 days"], ["1w", 7, "7 days"]];
}

/* The windows this curve can fill. A chip only exists when it would
   show a different window than the whole record. */
function recRangesFor(curve) {
  const all = recRanges();
  // Calendar days only — a week-labelled point is no date (recRangesClosed).
  const pts = (curve || []).filter((p) => /^\d{4}-\d{2}-\d{2}$/.test(String((p || {}).date || "")));
  if (pts.length < 2) return all.slice(0, 1);
  const spanDays = (new Date(pts[pts.length - 1].date)
                    - new Date(pts[0].date)) / 864e5;
  return all.filter(([k, d]) => k === "all" || spanDays > d);
}

function recRangeKey(avail) {
  return avail.some(([k]) => k === _recRange) ? _recRange : "all";
}

/* The first calendar day inside a window, or "" for the whole record.
   Guard the Date math: Infinity days (the whole record) must never
   reach toISOString — an invalid Date throws and, because the page is
   one template literal, one throw blanks every section of it. */
function recRangeFrom(avail, rk) {
  const days = (avail.find(([k]) => k === rk) || [null, Infinity])[1];
  return isFinite(days) ? new Date(Date.now() - days * 864e5).toISOString().slice(0, 10) : "";
}

/* A window's headline in the shape `performance` exports, from the
   curve's own days on or after `from` — or null when the curve cannot
   say (an older payload without w/l) or nothing settled in it. The
   net is the running total's own difference, the way the chart
   rebases it: each day's units are rounded, and summing them drifts
   a few hundredths off the record. */
function recRangeTotals(curve, from) {
  const all = curve || [];
  // A week label ("2026-W04") sorts after every day, so `>= from` let it
  // into every window; a row with no day is in the whole record only.
  const rows = all.filter((p) => p && /^\d{4}-\d{2}-\d{2}$/.test(String(p.date || "")) && p.date >= from);
  if (!rows.length || !rows.every((p) => p.w != null)) return null;
  const sum = (f) => rows.reduce((a, p) => a + (Number(p[f]) || 0), 0);
  const wins = sum("w"), losses = sum("l"), settled = sum("n"), staked = sum("staked");
  const i = all.indexOf(rows[0]);
  const last = Number(rows[rows.length - 1].cum_u);
  const net = Number.isFinite(last)
    ? +(last - (i > 0 ? Number(all[i - 1].cum_u) || 0 : 0)).toFixed(2)
    : +sum("day_u").toFixed(2);
  if (!settled) return null;
  return { settled, wins, losses, pushes: Math.max(0, settled - wins - losses),
           net_units: net, units_staked: staked, roi: staked ? net / staked : 0 };
}

/* The windows this curve can NOT fill yet, each with the reason (audit
   V-22): a chip that silently is not there reads as a missing feature;
   one that is there, greyed, says why. */
function recRangesClosed(curve) {
  const open = new Set(recRangesFor(curve).map(([k]) => k));
  /* CALENDAR DAYS ONLY. An NFL row journaled without its game's day sits
     in the curve under its week label ("2026-W04"), which sorts after
     every real day and is no date at all — the page read "The record
     covers NaN days so far" (Ethan, 2026-10-02). The span is measured
     over the days that are days; the labelled rows still count in every
     total. */
  const pts = (curve || []).filter((p) => /^\d{4}-\d{2}-\d{2}$/.test(String((p || {}).date || "")));
  const span = pts.length >= 2
    ? Math.round((new Date(pts[pts.length - 1].date) - new Date(pts[0].date)) / 864e5) : 0;
  return recRanges().filter(([k]) => !open.has(k)).map(([k, d, label]) => [k, d, label,
    pts.length < 2 ? "Not enough settled days for a window yet."
      : `The record covers ${plural(span, "day")} so far — a ${d}-day window would be the whole record.`]);
}

function recordWindowHTML(avail, rk, closed = []) {
  if (avail.length < 2 && !closed.length) return "";
  return `<div class="rec-windows" role="group" aria-label="Time window">${avail.map(([k, , label]) =>
    `<button type="button" class="rec-win${k === rk ? " active" : ""}" data-win="${k}"
      aria-pressed="${k === rk ? "true" : "false"}">${label}</button>`).join("")}${closed.map(([k, , label, why]) =>
    `<button type="button" class="rec-win off" disabled aria-disabled="true" title="${escapeAttr(why)}">${label}</button>`).join("")}${
    closed.length ? `<span class="rec-win-why">${escapeHtml(closed[closed.length - 1][3])}</span>` : ""}</div>`;
}

/* Records by book, per sport — Ethan, 2026-09-01: "the edge bets have
   a certain section and record spot, the most likely bets have a
   record spot, and excetra. We should also label homers and touchdowns
   and hits and receptions and rebounds and 3 pointers." Each book gets
   its own headline W-L and ROI with its markets underneath, labeled by
   the shipped market_words — never retyped here (the splits table
   already paid for that lesson once). Scoped pages show the sport's
   own books; the all-sports view pools them. */
function recBookSections(br, scope, opts) {
  if (!br) return "";
  // The heading and the book order are arguments so the SHADOW books
  // can reuse this whole function — the pooling loop, the thin-sample
  // note, the per-market tables and, above all, the ROI that keeps a
  // push out of its denominator. A second copy of that arithmetic is
  // how one book ends up with two different ROIs on one screen.
  const O = opts || {};
  /* BOTH HALVES OF THE MOST LIKELY BOOK, named (Ethan, 2026-10-02). This
     drew the paper half alone under the bare name "Most Likely" — 80-36,
     +7.7% — while the section above it read 243-129, −0.6% for the same
     book; the staked half was never drawn here at all. Named for what
     each is, the two add up to the one above. */
  const ORDER = O.order || [["edge", "Edge bets"], ["likely", "Most Likely — paper, before the money"],
                            ["likely_live", "Most Likely — real money"],
                            ["longshots", "Long Shots"]];
  let books;
  if (scope && scope !== "all" && scope !== "intel") {
    books = br[scope];
  } else {
    books = {};
    for (const sp of Object.values(br)) {
      for (const [k, b] of Object.entries(sp)) {
        const t = books[k] || (books[k] = {
          w: 0, l: 0, push: 0, net_u: 0, staked: 0, markets: {} });
        t.w += b.w; t.l += b.l; t.push += b.push || 0;
        t.net_u += b.net_u; t.staked += b.staked;
        for (const [m, v] of Object.entries(b.markets || {})) {
          const tm = t.markets[m] || (t.markets[m] = {
            w: 0, l: 0, net_u: 0, staked: 0 });
          tm.w += v.w; tm.l += v.l;
          tm.net_u += v.net_u; tm.staked += v.staked;
        }
      }
    }
  }
  if (!books || !Object.keys(books).length) return "";
  const cards = ORDER.map(([key, label]) => {
    const b = books[key];
    if (!b || !(b.w + b.l)) return "";
    const roi = b.staked ? b.net_u / b.staked : 0;
    const n = b.w + b.l;
    // A 3-1 record is not a 75% win rate. Said beside the number, the
    // way every other rate on this page is, rather than hidden until
    // the sample looks good.
    // GRADED, not settled: n is wins plus losses, and beside a 7-8-1
    // record "15 settled" contradicted the verdict's "16 settled" one
    // screen up (2026-09-06). A push settles; it does not grade.
    const thin = n < _recMinGraded ? ` · ${n} graded — thin sample` : "";
    const head = `${label} · ${b.w}-${b.l}${b.push ? `-${b.push}` : ""}`
      + ` · ${roi >= 0 ? "+" : ""}${(roi * 100).toFixed(1)}% ROI${thin}`;
    const pretty = Object.fromEntries(Object.entries(b.markets || {})
      .map(([m, v]) => [marketWord(m), v]));
    return recBucketTable(head, pretty);
  }).join("");
  if (!cards) return "";
  return `
    <div class="section-title">${escapeHtml(O.title || "Records by book")}
      <span class="sub">${O.sub || `— every kind of pick keeps its own
      record spot: the staked edge bets, the Most Likely paper book, the
      long shots — and how each market inside them did`}</span></div>
    <div class="rec-buckets">${cards}</div>`;
}

/* EVERY OTHER BOOK THIS LEAGUE HAS, on the league's own page.

   Ethan, 2026-09-19: "i want all bets shown on the record page that had
   been placed and cfb isnt showing that."

   College football's journal held 210 rows under `stale` on top of the
   246 Most Likely and 8 edge bets — graded, dated, real prices — and a
   reader who tapped CFB saw none of them. The panels that draw these
   buckets are written `scoped ? "" : X`, whole-journal only, because
   `stale_flags`, `form_sampler` and `loose_sampler` have no per-sport
   cut to draw. So the rows were not hidden by a decision; they were
   hidden by the shape of a payload.

   `shadow_books` is the same scan as `book_records` over the categories
   in `ledger.SHADOW_SECTIONS`, keyed by sport. These stay OUT of the
   headline — `performance` defaults to ("main","paper"), so the P&L,
   the curve and the verdict cannot see them, and the subtitle says so
   rather than leaving a reader to add the numbers up wrong.

   Scoped only. On "All bets" the dedicated panels above already draw
   each of these buckets with its hit rate and its promotion verdict,
   and printing the same W-L twice on one screen is the failure the ROI
   comment in `book_records` exists for. */
const SHADOW_ORDER = [
  ["stale", "Stale-line flags"], ["form", "Form sampler"],
  ["loose", "Looser gates"], ["longshot_watch", "Long-shot watch"],
  ["predmarket", "Prediction desk"]];

/* ON "ALL BETS", ONLY THE BOOKS WITH NO PANEL OF THEIR OWN.
   `recStaleSection`, `recFormSection` and `recLooseSection` already draw
   their buckets there, with hit rates and promotion verdicts this table
   does not have. The other two have no renderer anywhere — which is how
   `weather`, 2,589 graded desk contracts, was reachable from no page at
   all (Ethan's droplet run, 2026-09-19). */
const SHADOW_ORDER_ALL = SHADOW_ORDER.filter(
  ([k]) => k === "longshot_watch" || k === "predmarket");

/* THE PROMOTION LADDER, SHOWN — what a shadow book needs to become a
   real one, and how close each league is.

   `ledger.stale_verdict` has computed this every export since it was
   written, `export_json` publishes it as `stale_verdicts`, and until
   2026-09-19 NOTHING READ IT — no renderer, no pipeline. Its own
   docstring said the acting half was "a separate change, made with
   this number in hand", and that change was never made.

   Ethan, the same day: "us not having any edge bets for cfb in 2 weeks
   is a problem". College's model cannot supply them — its measured
   disagreement with the line has a negative slope over 2,016 games —
   so the stale-line book is the way up, and a reader should be able to
   see it climbing instead of asking why the board is empty.

   The bar is `stale_verdict`'s and this only reports it: 200 settled
   flags, a hit rate two standard errors over the break-even of the
   prices actually taken, and a positive flat-stake ROI. */
function recStaleLadder(sv, scope) {
  const rows = Object.entries(sv || {})
    .filter(([sp]) => !scope || scope === "all" || sp === scope)
    .sort((a, b) => (b[1].n || 0) - (a[1].n || 0));
  if (!rows.length) return "";
  const line = ([sp, v]) => {
    const up = v.verdict === "promote";
    return `<div class="rl-row ${up ? "won" : ""}">
      <span class="rl-icon">${icon(up ? "check" : "dash")}</span>
      <span class="rl-date">${escapeHtml(
        (SPORT_META[sp] || {}).name || String(sp).toUpperCase())}</span>
      <span class="rl-main">${up
        ? "Promoted — these flags are edge bets"
        : escapeHtml(v.why || "")}</span>
      <span class="rl-proc">${plural(v.n, "flag")} · ${
        ((v.hit_rate || 0) * 100).toFixed(1)}% vs ${
        ((v.break_even || 0) * 100).toFixed(1)}% break-even</span>
      <span class="rl-odds">z ${(v.z || 0) >= 0 ? "+" : ""}${
        (v.z || 0).toFixed(1)}</span>
    </div>`;
  };
  return `
    <div class="section-title">Earning its way up
      <span class="sub">— the stale-line book bets a price a point below
      the field, not an opinion on who wins. It becomes a real edge bet
      when its own graded record says it pays: 200 settled flags, two
      standard errors clear of the break-even on the prices actually
      taken, and a positive flat-stake ROI.</span></div>
    <div class="card" style="padding:0">${rows.map(line).join("")}</div>`;
}

function recShadowBooks(sb, scope, order) {
  const all = !scope || scope === "all";
  return recBookSections(sb, scope, {
    order: order || (all ? SHADOW_ORDER_ALL : SHADOW_ORDER),
    title: "Also tracked, never staked",
    sub: all
      ? `— books kept deliberately out of the P&L above and counted by no
         chip: measurements, not money. Pooled across every league,
         including ones with no board of their own.`
      : `— every other pick journaled for this league, kept deliberately
         out of the P&L above and counted by no chip: they are
         measurements, not money. Each one earns its way into the record
         on its own graded run.`,
  });
}

function recSplitsSection(o, booksDrawn) {
  // On a sport scope "Records by book" has just drawn the edge book by
  // market — the same rows this table's Market chip drew again, number
  // for number, one screen later. The chip goes; side, grade and book
  // are the splits that section does not have.
  const SPLITS = [["market", "Market", booksDrawn ? null : o.by_market],
                  ["side", "Side", o.by_side],
                  ["grade", "Grade", o.by_grade],
                  ["book", "Book", o.by_book]];
  const avail = SPLITS.filter(([, , t]) => t && Object.keys(t).length);
  if (!avail.length) return "";
  const cur = avail.find(([k]) => k === _recSplit) || avail[0];
  const pretty = cur[0] === "market"
    ? Object.fromEntries(Object.entries(cur[2]).map(([k, v]) =>
        [marketWord(k), v]))
    : cur[2];
  const chips = avail.length > 1 ? `<span class="ra-ranges">${avail.map(([k, label]) =>
    `<button class="ra-range ${k === cur[0] ? "active" : ""}"
       data-act="recSetSplit" data-arg="${k}">${label}</button>`).join("")}</span>` : "";
  return `
    <div class="section-title">Splits
      <span class="sub">— where the units actually came from. The bar is win rate;
      the number that matters is net.</span>
      ${chips}</div>
    <div class="rec-buckets rec-buckets-one">
      ${recBucketTable(`By ${cur[1].toLowerCase()}`, pretty)}
    </div>`;
}

/* THIS MONTH, IN ONE CARD (audit V-22): what a reader asks first of a
   young record — how is it going this month in this league — answered in
   one card instead of fourteen panels. The month is the latest settled
   day's; W-L, units and ROI are that month's, cut from the curve; CLV,
   claimed-vs-landed and Brier are the whole graded record's and say so. */
function recMonthCard(src, label) {
  const curve = (src && src.curve) || [];
  if (!curve.length) return "";
  const month = String(curve[curve.length - 1].date || "").slice(0, 7);
  const days = curve.filter((p) => String(p.date || "").startsWith(month));
  const sum = (f) => days.reduce((a, p) => a + (Number(p[f]) || 0), 0);
  const w = sum("w"), l = sum("l"), n = sum("n"), staked = sum("staked"), units = sum("day_u");
  if (!n) return "";
  const o = (src && src.overall) || {};
  const cal = (src && src.calibration) || {};
  const bk = (cal.buckets || []).filter((b) => b && b.n);
  const tot = bk.reduce((a, b) => a + b.n, 0);
  const claimed = tot ? bk.reduce((a, b) => a + b.predicted * b.n, 0) / tot : null;
  const landed = tot ? bk.reduce((a, b) => a + b.actual * b.n, 0) / tot : null;
  const monthName = new Date(`${month}-15T12:00:00Z`).toLocaleString("en-US", { month: "long", timeZone: "UTC" });
  const cell = (k, v, sub) => `<div class="rec-mc-cell"><div class="k">${k}</div><div class="v">${v}</div>${
    sub ? `<div class="s">${sub}</div>` : ""}</div>`;
  return `<div class="card rec-month-card">
    <div class="rec-mc-head">${escapeHtml(monthName)}, ${escapeHtml(label)}</div>
    <div class="rec-mc-grid">
      ${cell("Record", `${w}-${l}`, plural(n, "settled bet"))}
      ${cell("Units", `${units > 0 ? "+" : units < 0 ? MINUS : ""}${Math.abs(units).toFixed(2)}u`,
             staked ? `ROI ${fmtRoi(units / staked)}` : "")}
      ${cell("CLV", o.clv_n ? `${o.avg_clv > 0 ? "+" : ""}${Number(o.avg_clv || 0).toFixed(2)}` : "—",
             o.clv_n ? `on ${plural(o.clv_n, "bet")}, whole record` : "no closing lines yet")}
      ${cell("Claimed → landed", claimed == null ? "—" : `${Math.round(claimed * 100)}% → ${Math.round(landed * 100)}%`,
             tot ? `${tot} graded, whole record` : "")}
      ${cell("Brier", cal.brier_model == null ? "—" : Number(cal.brier_model).toFixed(3),
             cal.brier_market == null ? "" : `market ${Number(cal.brier_market).toFixed(3)}`)}
    </div></div>`;
}

function recRecentSection(recent, settled) {
  const shown = _recAllPicks ? recent : recent.slice(0, 12);
  const more = recent.length - shown.length;
  /* THE LIST IS CAPPED AND USED TO SAY IT WAS COMPLETE. The export
     carries the most recent `RECENT_LIMIT` settled picks; the button
     said "Show all 20 settled picks" under a verdict reading 193
     settled, which is how Ethan read the page as not showing the bets
     it had recommended (2026-09-06). The button now offers what it can
     actually reveal, and the sub-line names the cap against the true
     count — which is the verdict's own `settled`, so the two can never
     disagree. Older picks are not hidden, only not shipped in this
     file: they are in the journal, in every number above, and in the
     receipts CSV. */
  const capped = (settled || 0) > recent.length;
  return `
    <div class="section-title"><span class="st-ico">${icon("list", 15)}</span>Settled bets
      <span class="sub" id="rec-bets-sub">— newest first, at the price we actually got${
        capped ? ` · the ${recent.length} most recent of ${settled} settled`
               : ""}</span></div>
    <div id="rec-bets-bar"></div>
    <div class="card rec-list" id="rec-bets">
      ${shown.map(recSettledRow).join("") || (settled
        // NEVER BELOW THE VERDICT (audit V-5/V-22): "1 settled" over
        // "Nothing settled yet" read as two records. The rows exist; they
        // are not in this file.
        ? panelEmpty(`${plural(settled, "settled bet")} — the rows are in the journal and the receipts CSV, not in this page’s recent list.`)
        : panelEmpty("Nothing settled yet."))}
      ${more > 0 ? `<button class="rec-more" data-act="recShowPicks">
        Show ${more} more</button>` : ""}
    </div>`;
}
/* EVERY SETTLED BET, FILTERABLE. Ethan's product audit, 2026-09-23,
   item 17: the Record as "a financial terminal" — every bet, with
   the model's number, the price, the close and the CLV, filterable.
   The record file ships the most recent RECENT_LIMIT; the rest come
   from /api/record/bets (ledger.settled_page) fifty at a time, over
   the same rows as the headline: the scope in view, the page's
   window, and the two filters here. recRecentSection draws the first
   paint from the shipped rows; recBetsMount takes over and asks the
   journal. On a host with no API the shipped rows are filtered here
   and the list says it is the recent ones, not the whole record. */
let _recBetKind = "";      // "" | props | lines
let _recBetResult = "";    // "" | won | lost
let _recBets = { key: "", rows: [], total: null, remote: false, busy: false };
let _recBetsCtx = null;     // { recent, settled, scope, from } of the page in view

function recBetKind(market) {
  const m = String(market || "");
  return TEAM_SIDE_MARKETS.has(m) || m === "total" ? "lines" : "props";
}

function recBetsQuery(scope, from) {
  return { sport: scope === "all" || scope === "intel" ? "" : String(scope || ""),
           kind: _recBetKind, result: _recBetResult, since: from || "" };
}

function recBetsURL(q, offset) {
  const p = new URLSearchParams();
  ["sport", "kind", "result", "since"].forEach((k) => { if (q[k]) p.set(k, q[k]); });
  if (offset) p.set("offset", String(offset));
  const s = p.toString();
  return `/api/record/bets${s ? `?${s}` : ""}`;
}

function recBetsLocal(recent, q) {
  return (recent || []).filter((b) => b
    && (!q.kind || recBetKind(b.market) === q.kind)
    && (!q.result || b.status === q.result)
    && (!q.since || String(b.day || b.date || "") >= q.since));
}

function recBetsBarHTML(q) {
  const chip = (group, [v, label]) => `<button type="button" class="rec-bf${q[group] === v ? " active" : ""}"
    data-bf="${group}" data-v="${v}" aria-pressed="${q[group] === v ? "true" : "false"}">${label}</button>`;
  return `<div class="rec-bf-group" role="group" aria-label="Market">${
      [["", "All bets"], ["props", "Props"], ["lines", "Game lines"]].map((x) => chip("kind", x)).join("")}</div>
    <div class="rec-bf-group" role="group" aria-label="Result">${
      [["", "Any result"], ["won", "Won"], ["lost", "Lost"]].map((x) => chip("result", x)).join("")}</div>`;
}

/* The list and its line, from whatever _recBets holds: the journal's
   page (remote, with a true total) or the shipped rows (local). */
function recBetsListHTML(st, settled, q) {
  const filtered = !!(q.kind || q.result || q.since);
  // A dozen first, as the list always opened; then what is already
  // here; then the journal's next fifty.
  const shown = _recAllPicks ? st.rows : st.rows.slice(0, 12);
  const empty = filtered ? "No settled bets match these filters." : "Nothing settled yet.";
  const unfetched = st.remote ? Math.max(0, (st.total || 0) - st.rows.length) : 0;
  const more = shown.length < st.rows.length
    ? `<button class="rec-more" type="button" data-act="recShowPicks">Show ${st.rows.length - shown.length} more</button>`
    : unfetched
    ? `<button class="rec-more" type="button" data-bets-more${st.busy ? " disabled" : ""}>Show ${Math.min(unfetched, 50)} more${
        unfetched > 50 ? ` <span class="mini">of ${unfetched}</span>` : ""}</button>`
    : "";
  const line = st.remote
    ? `— newest first, at the price we actually got · ${plural(st.total || 0, "settled bet")}${
        filtered ? " match" : ""}`
    : `— newest first, at the price we actually got${filtered
        ? ` · of the ${((_recBetsCtx || {}).recent || []).length} most recent settled`
        : (settled || 0) > st.rows.length ? ` · the ${st.rows.length} most recent of ${settled} settled` : ""}`;
  return { list: (shown.map(recSettledRow).join("") || panelEmpty(empty)) + more, line };
}

function recBetsPaint(host) {
  const ctx = _recBetsCtx;
  const bar = host.querySelector("#rec-bets-bar"), list = host.querySelector("#rec-bets");
  if (!ctx || !bar || !list) return;
  const q = recBetsQuery(ctx.scope, ctx.from);
  const out = recBetsListHTML(_recBets, ctx.settled, q);
  bar.className = "rec-bets-bar";
  bar.innerHTML = recBetsBarHTML(q);
  list.innerHTML = out.list;
  const sub = host.querySelector("#rec-bets-sub");
  if (sub) sub.textContent = out.line;
  bar.querySelectorAll(".rec-bf").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.bf === "kind") _recBetKind = b.dataset.v || "";
    else _recBetResult = b.dataset.v || "";
    recBetsMount(host);
  }));
  const m = list.querySelector("[data-bets-more]");
  if (m) m.addEventListener("click", () => recBetsFetch(host, _recBets.rows.length));
}

async function recBetsFetch(host, offset) {
  const ctx = _recBetsCtx;
  if (!ctx || _recBets.busy) return;
  const key = _recBets.key;
  _recBets.busy = true;
  try {
    const r = await fetch(recBetsURL(recBetsQuery(ctx.scope, ctx.from), offset));
    const page = r.ok ? await r.json() : null;
    // An answer of nothing at all while this page holds settled rows is a
    // journal the server cannot see (a host with no ledger), not "Nothing
    // settled yet" under a verdict of 38 settled: the shipped rows stand.
    const q = recBetsQuery(ctx.scope, ctx.from);
    const blank = page && !Number(page.total) && (ctx.settled || 0) > 0 && !(q.kind || q.result || q.since);
    if (_recBets.key === key && page && Array.isArray(page.rows) && !blank) {
      _recBets.rows = offset ? _recBets.rows.concat(page.rows) : page.rows;
      _recBets.total = Number(page.total) || 0;
      _recBets.remote = true;
    }
  } catch (e) { /* no API here — the shipped rows stand, and say so */ }
  if (_recBets.key !== key) return;                 // a newer filter won
  _recBets.busy = false;
  recBetsPaint(host);
}

/* Called after every Record render; a chip calls it again. A new
   filter, scope or window starts from the shipped rows and asks the
   journal once; the same one keeps what it already fetched. */
function recBetsMount(host, recent, settled, scope, from) {
  if (recent !== undefined) _recBetsCtx = { recent: recent || [], settled, scope, from };
  const ctx = _recBetsCtx;
  if (!ctx || !host.querySelector("#rec-bets")) return;
  const q = recBetsQuery(ctx.scope, ctx.from);
  const key = JSON.stringify(q);
  const fresh = _recBets.key !== key;
  if (fresh) _recBets = { key, rows: recBetsLocal(ctx.recent, q), total: null, remote: false, busy: false };
  recBetsPaint(host);
  if (fresh) recBetsFetch(host, 0);
}

function recAnalytics(curve, o, eras) {
  if (!curve || curve.length < 2) return recCurveChart(curve);
  // The page's one window (recRanges): the same list and state the
  // headline ribbon reads, so the two never disagree.
  const avail = recRangesFor(curve);
  const rk = recRangeKey(avail);
  const from = recRangeFrom(avail, rk);
  const rows = from ? curve.filter((p) => p.date >= from) : curve;
  if (!rows.length) {
    return `<div class="section-title"><span class="st-ico">${icon("rising", 15)}</span>Running P&amp;L
        <span class="sub">— every settled pick, by slate date</span>
        ${raChips(avail, rk)}</div>
      <p class="rail-quiet" style="margin:0 0 18px">Nothing settled in this
        window — pick a longer range.</p>`;
  }
  // Rebase the running total so the window tells the window's story.
  const first = curve.indexOf(rows[0]);
  const base = first > 0 ? curve[first - 1].cum_u : 0;
  const sliced = rows.map((p) => ({ ...p, cum_u: +(p.cum_u - base).toFixed(2) }));
  const net = sliced[sliced.length - 1].cum_u;
  const hasWL = rows.every((p) => p.w != null);
  const wins = hasWL ? rows.reduce((a, p) => a + p.w, 0) : (rk === "all" ? o.wins : null);
  const losses = hasWL ? rows.reduce((a, p) => a + p.l, 0) : (rk === "all" ? o.losses : null);
  const staked = hasWL ? rows.reduce((a, p) => a + (p.staked || 0), 0)
    : (rk === "all" ? o.units_staked : null);
  const nBets = rows.reduce((a, p) => a + (p.n || 0), 0);
  const roi = staked ? net / staked : null;
  const wr = wins != null && (wins + losses) > 0 ? wins / (wins + losses) : null;
  // DECLUTTERED 2026-08-17 (Ethan: "its very cluttered and nees to be
  // easiler to read"). This block used to repeat the scoreboard three
  // times: a 3-tile column beside the curve (net/win rate/ROI — all in
  // the hero tiles above), a graded/won/lost tile row (the RECORD tile,
  // again), and a 4-tile all-time row. Every number survives — the
  // range-scoped ones on one line under the curve, the all-time ones on
  // one ledger line — but each now appears ONCE.
  const line = (parts) => parts.filter(Boolean).join(" · ");
  const range = line([
    wins != null && `<b>${wins}-${losses}${nBets > wins + losses ? `-${nBets - wins - losses}` : ""}</b> in this window`,
    wr != null && `win rate <b>${(wr * 100).toFixed(1)}%</b>`,
    roi != null && `ROI <b class="${toneOf(roi)}">${roi >= 0 ? "+" : ""}${(roi * 100).toFixed(1)}%</b>`,
    `net <b class="${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</b>`,
  ]);
  const alltime = o.avg_price == null && o.best_streak == null ? "" : line([
    `<b>${(o.units_staked || 0).toFixed(1)}u</b> staked all-time`,
    `<b>${(o.returned_units || 0).toFixed(1)}u</b> returned (stake back + winnings)`,
    o.avg_price != null && `avg price <b>${oddsTxt(o.avg_price)}</b>`,
    o.best_streak != null && `best win streak <b>${o.best_streak}</b>`,
  ]);
  return `
    <div class="section-title"><span class="st-ico">${icon("rising", 15)}</span>Running P&amp;L
      <span class="sub">— every settled pick, by slate date</span>
      ${raChips(avail, rk)}</div>
    <div class="ra-main">
      ${recCurveChart(sliced, { head: false, eras })}
    </div>
    ${/* On ALL the window is the whole book, and the record, win rate,
          ROI and net of the whole book are the verdict's tiles at the top
          of the room. The line earns its place only when a chip has cut
          a window the tiles do not describe. */
      rk === "all" ? "" : `<p class="ra-line">${range}</p>`}
    ${alltime ? `<p class="ra-line ra-dim">${alltime}</p>` : ""}`;
}       // the day whose bets are open, or null
let _recCalScope = "all";

/* A tapped day: its line from the curve at once, its rows from the
   record endpoint, scoped the way the page is. If the endpoint cannot be
   reached (a static host has no /api), the rows this page already holds
   for that day are shown and the panel says that is what they are. */
async function recCalDayOpen(date, curve, recent, book) {
  _recCalDay = date;
  const host = document.getElementById("rc-day");
  if (!host) return;
  document.querySelectorAll(".rc-day.open").forEach((el) => el.classList.remove("open"));
  const cell = document.querySelector(`.rc-day[data-date="${date}"]`);
  if (cell) cell.classList.add("open");
  const p = (curve || []).find((x) => x.date === date) || {};
  const extra = (p.n || 0) - (p.w || 0) - (p.l || 0);
  const head = `<b>${escapeHtml(formatGameDate(date) || date)}</b> · ${p.w || 0}-${p.l || 0}${
    extra > 0 ? `-${extra}` : ""} · <b class="${toneOf(p.day_u || 0)}">${recCalU(p.day_u || 0)}u</b>`;
  host.innerHTML = `<p class="rc-dayhead">${head}</p><p class="rail-quiet">Loading the day’s bets…</p>`;
  let rows = null, note = "";
  try {
    const sport = _recCalScope === "all" ? "" : _recCalScope;
    const r = await fetch(`/api/record/day?date=${encodeURIComponent(date)}&sport=${encodeURIComponent(sport)}&book=${book === "likely" ? "likely" : "edge"}`);
    if (r.ok) rows = ((await r.json()) || {}).rows || [];
  } catch (e) { rows = null; }
  if (_recCalDay !== date) return;                         // another day was tapped
  if (!rows) {
    rows = (recent || []).filter((b) => b.date === date);
    note = `<p class="rail-quiet">The day’s full list could not be fetched — these are the rows this page already holds.</p>`;
  }
  host.innerHTML = `<p class="rc-dayhead">${head}</p>${note}${recCalDayBodyHTML(rows)}`;
}

/* A DAY OF 216 BETS IS NOT A PAGE (Ethan, 2026-09-28: "have a little pull
   down menu or sum so they don't take up the whole page"). The day reads
   as a summary — each league and market with its record and units, the
   biggest swing first — and the bets themselves fold under it, a tap
   away. A day of a handful shows them as they are. */
const REC_DAY_OPEN_MAX = 6;
function recCalDayBodyHTML(rows) {
  if (!rows.length) return panelEmpty("No settled bets on this day in this scope.");
  const list = rows.map(recSettledRow);
  if (rows.length <= REC_DAY_OPEN_MAX) return `<div class="rec-list">${list.join("")}</div>`;
  const groups = new Map();
  rows.forEach((r) => {
    const k = `${String(r.sport || "").toUpperCase()} · ${marketWord(r.market)}`;
    const g = groups.get(k) || { k, w: 0, l: 0, p: 0, u: 0 };
    if (r.status === "won") g.w += 1; else if (r.status === "lost") g.l += 1; else g.p += 1;
    g.u += Number(r.pnl_units) || 0;
    groups.set(k, g);
  });
  const sum = [...groups.values()].sort((a, b) => Math.abs(b.u) - Math.abs(a.u));
  return `<div class="rc-sum" role="list">${sum.map((g) => `<div class="rc-sum-row" role="listitem">
      <span class="rc-sum-k">${escapeHtml(g.k)}</span>
      <span class="rc-sum-wl">${g.w}-${g.l}${g.p ? `-${g.p}` : ""}</span>
      <b class="rc-sum-u ${toneOf(g.u)}">${recCalU(g.u)}u</b></div>`).join("")}</div>
    <details class="row-fold rc-bets">
      <summary><span class="row-fold-more">Show the day’s ${rows.length} bets</span><span class="row-fold-less">Hide the bets</span>
        <span class="row-fold-chev" aria-hidden="true"></span></summary>
      <div class="row-fold-body rec-list">${list.join("")}</div></details>`;
}

function raChips(avail, rk) {
  if (avail.length < 2) return "";
  return `<span class="ra-ranges">${avail.map(([k]) =>
    `<button class="ra-range ${k === rk ? "active" : ""}"
       data-act="recSetRange" data-arg="${k}">${k.toUpperCase()}</button>`).join("")}</span>`;
}

function recEraSection(er) {
  const eras = (er || {}).eras || [];
  // Nothing to compare until there's more than one era with any activity.
  const active = eras.filter((e) => e.settled || e.open);
  if (eras.length < 2 || active.length < 1) return "";
  const row = (e, isCurrent) => {
    const graded = e.wins + e.losses;
    const range = e.from
      ? `since ${e.from}` : (e.to ? `through ${e.to}` : "");
    const roiTxt = graded
      ? `${e.roi >= 0 ? "+" : ""}${(e.roi * 100).toFixed(1)}%`
      : "—";
    const clv = e.avg_clv != null
      ? ` · CLV ${e.avg_clv >= 0 ? "+" : ""}${e.avg_clv.toFixed(2)} pts (${e.clv_n})`
      : "";
    /* DID THE BOARD TELL THE TRUTH ABOUT ITSELF — the question this
       section is named after, and the only one on the row that converges
       fast enough to answer it. W-L, ROI and CLV all need a season: a
       50-bet era swings ten points of ROI on variance alone. Every
       settled bet contributes a measurement to this one.

       Shown as "said 58%, landed 49%" rather than as a signed gap,
       because those are the two numbers a reader can check against the
       list below and a gap is a number they have to take on trust.
       Toned only when the miss clears two standard errors — under that
       it is a sample, not a verdict, and colouring it would be the site
       claiming a finding it does not have. */
    const cl = e.claim || {};
    const claim = cl.n
      ? (() => {
          const off = cl.gap / (cl.se || 1);
          const tone = off <= -2 ? "bad" : off >= 2 ? "good" : "";
          return `<span class="${tone}"> · said ${(cl.claimed * 100).toFixed(0)}%,
             landed ${(cl.landed * 100).toFixed(0)}% (${cl.n})</span>`;
        })()
      : "";
    const sports = Object.entries(e.by_sport || {}).map(([s, d]) =>
      `${s.toUpperCase()} ${d.w}-${d.l} (${d.net_u >= 0 ? "+" : ""}${d.net_u.toFixed(2)}u)`)
      .join(" · ");
    return `
      <div class="rec-row mid tall${isCurrent ? "" : " dim"}">
        <span style="flex:1;min-width:0">
          <strong>${escapeHtml(e.label)}</strong>
          ${isCurrent ? `<span class="chip" style="margin-left:6px">running now</span>` : ""}
          <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">
            ${escapeHtml(range)}${sports ? ` · ${sports}` : ""}${clv}${claim}</span>
        </span>
        <span style="text-align:right;white-space:nowrap">
          <strong>${e.wins}-${e.losses}</strong>
          <span style="display:block;font-size:var(--fs-sm)" class="${toneOf(e.net_units)}">
            ${graded ? `${e.net_units >= 0 ? "+" : ""}${e.net_units.toFixed(2)}u · ${roiTxt} ROI`
                     : `${e.open} open — accruing`}</span>
        </span>
      </div>`;
  };
  return `
    <div class="section-title">Model eras — did the re-tune work?
      <span class="sub">— the record split at each model change. Old losses belong to
      gates that no longer exist; the current era is the model being judged now.</span></div>
    <div class="card" style="padding:0">
      ${eras.map((e) => row(e, e.key === er.current)).join("")}
      <p style="padding:8px 14px;margin:0;font-size:var(--fs-xs);color:var(--text-mute)">
        "Said X, landed Y" is whether the board was honest about its own
        confidence — the fastest signal here, because every settled bet
        measures it while W-L and ROI are mostly variance until a season is in.
        CLV (closing-line value) is next: beating the close consistently shows
        up weeks before the W-L means anything. ROI last, and only past 50+
        graded bets.</p>
    </div>`;
}

/* The parlay bucket. §13 is explicit that this is reported separately and
   never blended, so it gets its own section, its own notional and its own
   ROI — and it leads with the one sentence that matters while the module is
   on probation: whether the same legs bet singly would have done better. */
/* WHAT THIS RECORD IS A RECORD OF.
   Ethan, 2026-08-23: "we suck at parlays and they are loosing us alot of
   money so we need a way to fix that and work on the model or something
   bc its not working."

   The number he was reading was -84.1% ROI over 19 tickets. EIGHTEEN OF
   THE NINETEEN WERE TICKETS THE SCREEN REFUSED. log_board journals rank 1
   off every slate whether or not it qualified — deliberately, because a
   screen that only grades its yeses never tests its noes — and this
   section then blended the two into one headline. So the site's own
   verdict on its parlay model was mostly a scoreboard of the bets it had
   declined to make, and it read as the model failing when it was the
   model working.

   The fix is not to hide the rejects. It is to stop averaging a
   recommendation with a refusal:

     * the KPIs report the RECOMMENDED bucket — every ticket the screen
       put its name to;
     * the refusals get their own line, with the reading spelled out: a
       bad ROI there is the gates being right;
     * the blended total is still printed, below both, labelled as the
       sum of two different questions.

   None of that makes the record good. On the numbers that prompted it the
   recommended bucket is a single ticket, which is no evidence at all, and
   the section says so rather than printing an ROI on n=1. */
/* HOW MANY TICKETS BEFORE A PERCENTAGE MEANS ANYTHING.

   Not a taste. The first cut of this section fixed the blended headline
   and immediately printed "+160.0% ROI" in green off ONE winning ticket,
   which is a worse lie than the -84% it replaced and the same kind: a
   rate quoted on a sample that cannot carry one. Below this floor the
   tiles show the RECORD and the UNITS — both facts about what happened —
   and no rate, no colour, and no verdict.

   Ten is where a single ticket stops being able to swing the number by
   more than about ten points at a one-unit notional. It is not the
   promotion bar; §13 wants a hundred, and the probation tile still says
   so. It is only the point below which a percentage is decoration. */
const PARLAY_RATE_FLOOR = 10;

function recParlaySection(pz) {
  if (!pz || (!pz.graded && !pz.open)) return "";
  const pr = pz.promotion || {};
  const q = pz.by_qualified || {};
  const rec = q.recommended || {};
  const no = q.not_qualified || {};
  const play = q.play || {};
  // The verdict on the SCREEN is asked of the screen's own tickets. The
  // all-rows answer is still carried, and printed in the split below.
  const readable = (rec.graded || 0) >= PARLAY_RATE_FLOOR;
  const sc = (rec.graded ? pz.singles_comparison_recommended : null)
    || pz.singles_comparison || {};
  const cond = (ok, label) =>
    `<span class="pl-cond${ok ? " met" : ""}">${ok ? icon("check") : icon("dash")}
      ${escapeHtml(label)}</span>`;
  // The honest headline. If flat singles on the same legs beat the tickets,
  // that IS the finding, and it should not need reconstructing from a table.
  const verdict = sc.n
    ? `<div class="pl-verdict" style="color:var(--${
        sc.singles_better ? "warn" : "good"})">
       Across ${sc.n} ${rec.graded ? "recommended" : "graded"} ${pluralWord(sc.n, "ticket")}: parlays
       <strong>${sc.parlay_units >= 0 ? "+" : ""}${sc.parlay_units.toFixed(2)}u</strong>,
       the same legs bet singly
       <strong>${sc.singles_units >= 0 ? "+" : ""}${sc.singles_units.toFixed(2)}u</strong>.
       ${sc.n < PARLAY_RATE_FLOOR
         ? `That is ${plural(sc.n, "ticket")} — a difference, not a finding.`
         : sc.singles_better
           ? "Singles were better — the structure is costing money."
           : "The structure has paid for itself so far."}</div>`
    : "";
  const codes = (pz.loss_codes || []).length
    ? `<div class="pl-codes">${pz.loss_codes.map((c) =>
        `<span class="chip">${escapeHtml(c.code)} ×${c.n}</span>`).join(" ")}</div>`
    : "";
  const rows = (pz.recent || []).map((t) => {
    const pnl = t.pnl_units || 0;
    const won = t.status === "won";
    const vd = t.status === "void";
    const legs = (t.legs || []).map((l) => {
      const s = l.status === "won" ? "won" : l.status === "lost" ? "lost" : "push";
      return `<span class="pl-leg ${s}"><span class="pl-mark">${
        l.status === "won" ? icon("check")
          : l.status === "lost" ? icon("cross") : icon("dash")}</span>${
        escapeHtml(l.player || "")} ${escapeHtml(l.side || "")} ${l.line ?? ""}
        <span style="opacity:.6">${escapeHtml(l.market || "")}</span></span>`;
    }).join("");
    return `<div class="rl-row has-legs ${vd ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${vd ? icon("dash") : won ? icon("check") : icon("cross")}</span>
      <span class="rl-date">${escapeHtml(t.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml((t.sport || "").toUpperCase())}
        ${(t.legs || []).length}-leg</strong>
        <span class="rl-bet">Type ${escapeHtml(t.parlay_type || "A")} ·
        ${escapeHtml(t.grade || "")}${t.was_play ? " · slate play" : ""}</span></span>
      <span class="rl-proc"></span>
      <span class="rl-odds">${t.assumed_american == null ? "—"
        : american(t.assumed_american)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
      <span class="pl-legs">${legs}</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Parlays — graded, never staked
      <span class="sub">— on probation until 100 tickets clear the bar. Never
      mixed into the record above.</span></div>
    ${recDisclosure("Why these stake nothing", `${escapeHtml(pr.note || "")}
      Every ticket here is graded at a flat one-unit notional so the ROI means
      something, and at a zero real stake so the account never moves. Tickets
      we <em>declined</em> are journaled too — recording only the ones that
      cleared would measure the gates on the handful of nights they said yes,
      and never test the no. Prices are an assumption, not a quote: no odds
      feed we ingest carries same-game-parlay prices, so each ticket is graded
      at the modelled likely-case price and labelled as such.`)}
    <div class="stats rec-kpis">
      ${readable
        ? recTile("Flat-stake ROI",
                  fmtRoi(rec.roi),
                  `${rec.net_units >= 0 ? "+" : ""}${
                    (rec.net_units || 0).toFixed(2)}u across ${
                    rec.graded} recommended`,
                  { lead: true, tone: toneOf(rec.roi) })
        : recTile("Recommended tickets",
                  rec.graded ? `${rec.wins || 0}-${rec.losses || 0}` : "none yet",
                  rec.graded
                    ? `${rec.net_units >= 0 ? "+" : ""}${
                        (rec.net_units || 0).toFixed(2)}u — too few for a rate`
                    : "no ticket the screen recommended has settled",
                  { lead: true })}
      ${/* NOT a second copy of the record. Below the floor the lead tile
            already shows the recommended W-L, and two tiles reading
            "1-0" is a KPI row arguing about which one to believe. This
            one carries the OTHER bucket, which is the whole point of the
            section — and the open/void counts, which have to live
            somewhere. */""}
      ${recTile("Also graded, not recommended",
                no.graded ? `${no.wins || 0}-${no.losses || 0}` : "—",
                `${no.graded || 0} refused · ${pz.open || 0} open · ${
                  pz.voided || 0} void`)}
      ${recTile("Probation", `${pr.tickets_have || 0}/${pr.tickets_required || 100}`,
                "graded tickets before anything is staked")}
      ${recTile("Leg CLV", pz.avg_leg_clv == null ? "—"
                  : (pz.avg_leg_clv >= 0 ? "+" : "") + pz.avg_leg_clv.toFixed(2),
                pz.leg_clv_n ? `across ${pz.leg_clv_n} legs` : "accrues as legs settle",
                { tone: toneOf(pz.avg_leg_clv) })}
    </div>
    ${parlaySplitHTML(pz, q)}
    <div class="pl-conds">
      ${cond(pr.tickets_have >= pr.tickets_required,
             `${pr.tickets_required || 100} graded tickets`)}
      ${cond(pr.roi_positive, "positive flat-stake ROI")}
      ${cond(pr.clv_non_negative, "leg CLV at or above zero")}
      ${cond(pr.z_clears, `z ≥ ${pr.z_required || 2}${
        pz.z == null ? "" : ` (now ${pz.z.toFixed(2)})`}`)}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${verdict}${rows ||
      `${panelEmpty("No ticket has settled yet — accrues from tonight’s board.")}`}${codes}</div>`;
}

/* WHAT THE HEADLINE IS NOT COUNTING, said out loud.

   The tiles above report the tickets the screen recommended. Everything
   else it graded is here, and the framing matters as much as the number:
   a heavy loss on the refused bucket is the gates being RIGHT, and
   reading it as the model failing is the mistake this whole block exists
   to stop. The blended total sits at the bottom, labelled, so nothing is
   hidden and nobody has to take the split on trust. */
function parlaySplitHTML(pz, q) {
  const line = (label, b, note) => {
    if (!b || !b.graded) return "";
    const u = b.net_units || 0;
    // Same floor as the tiles. A row reading "+160.0%" beside a note
    // saying one ticket is not a record is the page arguing with itself,
    // and the percentage is the half that wins on a glance.
    const rate = b.graded >= PARLAY_RATE_FLOOR
      ? fmtRoi(b.roi) : "";
    return `<div class="pl-split-row">
      <span class="pl-split-label">${escapeHtml(label)}</span>
      <span class="pl-split-n">${b.graded} graded · ${b.wins}W-${b.losses}L</span>
      <span class="pl-split-u ${b.graded >= PARLAY_RATE_FLOOR ? toneOf(u) : ""}">${
        u >= 0 ? "+" : ""}${u.toFixed(2)}u
        ${rate ? `<span class="pl-split-roi">${rate}</span>` : ""}</span>
      ${note ? `<span class="pl-split-note">${note}</span>` : ""}</div>`;
  };
  const rec = q.recommended || {}, no = q.not_qualified || {};
  const body = line("Recommended — the screen said yes", rec,
                    rec.graded < PARLAY_RATE_FLOOR
                      ? `${plural(rec.graded, "ticket")} ${rec.graded === 1 ? "is" : "are"} not a record yet; the bar
                         is ${pz.promotion ? pz.promotion.tickets_required : 100}`
                      : "")
    + line("Refused — shown, never recommended", no,
           `a loss here is the gates working`)
    + line("Everything graded, blended", {
        graded: pz.graded, wins: pz.wins, losses: pz.losses,
        net_units: pz.net_units, roi: pz.roi },
        "two different questions added together — read the rows above first");
  if (!body) return "";
  return `<div class="pl-split">
    <div class="pl-split-head">What this is a record of
      <span class="sub">— the Zone ranks the night’s best constructions even
      when none of them clears, and journals rank 1 either way. Grading a
      refusal beside a recommendation measures the wrong thing, so they are
      counted apart.</span></div>
    ${body}</div>`;
}

/* The Most Likely paper record.

   Ethan, 2026-08-30: "we should also record the bets on the most likley
   page and if it does good then we will attack money and roi and shit to
   it. maybe we do papr bets with it."

   The paper bets already existed — `ledger.log_most_likely` journals the
   top of the board nightly at zero dollar exposure and it grades on the
   same settle pass as everything else. What did not exist was anywhere
   to READ it, which made the bucket write-only and "if it does good"
   unanswerable.

   TWO TESTS, SHOWN APART, because the board can pass one and fail the
   other and the difference is the whole decision:

     is the number true   we said 68%, did 68% land? The claim the page
                          actually makes.
     would it have paid   ROI at the price shown. A perfectly calibrated
                          board still loses to the vig — the 22k-row
                          replay said -5% to -7.4% at every depth — so
                          the first test passing is not the second.

   Money is gated on the second. The verdict string refuses to say
   anything at all below `LIKELY_VERDICT_N` settled rows, and this
   renders that refusal as the headline rather than burying it under a
   number that looks like a result. */
/* WHEN we bet, graded against the close. The models show no edge over
   the closing price (0.468 AUC — noise); whether our EARLY prices beat
   it is the money question, and it accrues on every settled pick
   instead of waiting on win-loss variance. If "2+ days out" goes green
   and "under 2 hours" does not, the site has measured its own betting
   instruction. Verdicts gate at CLV_MIN_N like every CLV number. */
function recLeadtimeSection(lt) {
  if (!lt || (!lt.main && !lt.likely)) return "";
  const table = (got, name) => {
    if (!got || !(got.buckets || []).some((b) => b.settled)) return "";
    const rows = got.buckets.filter((b) => b.settled).map((b) => `<tr>
      <td>${escapeHtml(b.label)}</td>
      <td class="num">${b.settled}</td>
      <td class="num">${b.with_close}</td>
      <td class="num ${b.avg_clv > 0 ? "pos" : b.avg_clv < 0 ? "neg" : ""}">${
        b.avg_clv == null ? "—" : (b.avg_clv >= 0 ? "+" : "") + b.avg_clv.toFixed(2)}</td>
      <td class="num">${b.beat_close == null ? "—" : (b.beat_close * 100).toFixed(0) + "%"}</td>
      <td>${b.verdict ? escapeHtml(b.verdict)
            : `<span class="mini" style="opacity:.6">needs ${got.min_n} closes</span>`}</td>
    </tr>`).join("");
    if (!rows) return "";
    return `<div class="section-title minor">When we bet — ${escapeHtml(name)}
        <span class="sub">— price CLV by how early the pick was made</span></div>
      <table class="agate"><thead><tr><th>Lead time</th>
        <th class="num">Settled</th><th class="num">Closed</th>
        <th class="num">Avg CLV</th><th class="num">Beat close</th>
        <th>Verdict</th></tr></thead><tbody>${rows}</tbody></table>`;
  };
  const body = table(lt.main, "the staked book")
    + table(lt.likely, "the likely book");
  if (!body) return "";
  return `${body}
    <div class="ls-note">Positive CLV means the market moved toward our
    side after we bet — we got the better number, in probability points.
    Beating the close persistently is the earliest sign a book earns;
    if the early buckets earn it and the late ones don’t, the finding is
    an instruction: bet sooner.</div>`;
}

/* THE ONE MOST LIKELY BOARD, BY TIER (engine/likelyboard, ledger
   .board_report). Ethan, 2026-09-26: "yes do the record page next" — one
   record, broken down by tier, so it answers whether Top picks really hit
   more than Worth a look. Every row is tracked on paper at the tier it went
   up at; until one settles, the section says how many are waiting. */
function recBoardSection(bd, scope) {
  if (!bd || (!bd.settled && !bd.open)) return "";
  const pct = pctRoundOr;
  const line = (label, t, extra) => {
    const played = t.settled + (t.push || 0);
    const tone = t.actual == null ? "" : t.claimed != null && t.actual >= t.claimed ? "won" : "lost";
    return `<div class="rl-row rl-cal ${tone}${extra || ""}">
      <span class="rl-date">${escapeHtml(label)}</span>
      <span class="rl-main">${t.settled ? `${t.w}–${t.l}${t.push ? `–${t.push}` : ""} · hit <strong>${pct(t.actual)}</strong> · we said ${pct(t.claimed)}`
        : "no results yet"}</span>
      <span class="rl-proc">${t.open ? `${t.open} open` : played ? `${played} settled` : ""}</span>
      <span class="rl-pnl ${t.roi == null ? "" : toneOf(t.roi)}">${t.roi == null ? "—" : `${t.roi >= 0 ? "+" : ""}${(t.roi * 100).toFixed(1)}%`}</span>
    </div>`;
  };
  /* THE THREE TIERS SUMMED, on a line of its own (Ethan, 2026-10-02: "it
     feels like all these numbers are not adding up"): the total a reader
     would otherwise add in their head, from the ledger's own sum. */
  const total = bd.total && bd.total.settled ? line("All tiers", bd.total, " rl-total") : "";
  const rows = (bd.tiers || []).map((t) => line(t.tier, t)).join("") + total;
  const waiting = !bd.settled
    ? `<p class="ls-note">${plural(bd.open, "pick is", "picks are")} waiting on their games. The first results land once
        they settle — then this shows whether Top picks hit more than the rest.</p>` : "";
  const t0 = new Date(`${String(bd.first_day || "").slice(0, 10)}T12:00:00`);
  const since = Number.isFinite(t0.getTime())
    ? ` since ${t0.toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : "";
  return `<div class="section-title"><span class="st-ico">${icon("target", 15)}</span>Most Likely board · by tier
      <span class="sub">— every pick the board has posted${since}, at the tier it went up at (Top pick, Strong,
      Worth a look), on paper at a flat 0.1u, so each tier’s return is a plain flat-stake return</span></div>
    ${waiting}
    <div class="card rec-board-tiers" style="padding:0;margin-top:6px">${rows}</div>`;
}

function recLikelySection(lk, scope) {
  if (!lk || (!lk.settled && !lk.open)) return "";
  // The league whose rows these are, or "" on the pooled scope. Read off
  // the REPORT rather than the page's scope, so a mislabelled section is
  // impossible: `ledger.likely_report` stamps the sport it filtered on.
  const sp = String((lk || {}).sport || "");
  const spName = sp ? ((SPORT_META[sp] || {}).name || sp.toUpperCase()) : "";
  const cal = lk.calibration || {};
  const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
  const bands = (lk.bands || []).map((b) => `
    <div class="rl-row rl-cal ${b.actual >= b.claimed ? "won" : "lost"}">
      <span class="rl-date">${(b.lo * 100).toFixed(0)}–${(b.hi * 100).toFixed(0)}%</span>
      <span class="rl-main">said ${pct(b.claimed)} · hit <strong>${pct(b.actual)}</strong></span>
      <span class="rl-proc">${b.n} settled</span>
      <span class="rl-pnl ${toneOf(b.roi)}">${b.roi >= 0 ? "+" : ""}${(b.roi * 100).toFixed(1)}%</span>
    </div>`).join("");
  /* A SCORER MARKET, ONE ROW PER SIDE (ledger likely_report `sides`).
     Ethan, 2026-10-02: "No way we have hit 12/13 TD picks bc I've seen
     more then that loose." The row pooled "he scores" with "he does not"
     — opposite bets at opposite prices — so it read as touchdowns. And a
     return on fewer settled than the shelf's own bar is drawn uncoloured:
     too few to read either way, whichever way it points. */
  const sideWord = (m, sd) => {
    const no = String(sd || "").toUpperCase() === "UNDER";
    return m === "anytime_td" ? (no ? "no TD" : "scores")
      : m === "home_runs" ? (no ? "no home run" : "homers") : (no ? "no" : "yes");
  };
  const mkRow = (label, d) => `
    <div class="rl-row rl-cal ${d.actual >= d.claimed ? "won" : "lost"}">
      <span class="rl-date">${label}</span>
      <span class="rl-main">said ${pct(d.claimed)} · hit <strong>${pct(d.actual)}</strong></span>
      <span class="rl-proc">${d.w}/${d.n}</span>
      <span class="rl-pnl ${d.enough === false ? "" : toneOf(d.roi)}"${d.enough === false
        ? ` title="${d.n} settled — too few to read either way"` : ""}>${d.roi >= 0 ? "+" : ""}${(d.roi * 100).toFixed(1)}%</span>
    </div>`;
  const markets = Object.entries(lk.by_market || {}).map(([m, d]) => {
    const sides = Object.entries(d.sides || {});
    return sides.length
      ? sides.map(([sd, x]) => mkRow(`${escapeHtml(marketWord(m))} · ${sideWord(m, sd)}`, x)).join("")
      : mkRow(escapeHtml(marketWord(m)), d);
  }).join("");
  const shelfBar = (Object.values(lk.by_market || {})[0] || {}).needed || 40;
  /* WHETHER THERE IS MONEY ON THIS BOOK, ASKED BEFORE A WORD OF IT IS
     WRITTEN. Every sentence below used to be the paper version, hard
     coded — "ZERO dollars behind it", "nothing here is a position",
     "real money stays off until the ROI column has earned it" — and it
     kept saying so after 2026-09-19, when four leagues’ boards started
     staking 0.25u a row for real. A page that tells a reader no money is
     on a book while money is on it is the worst thing this section can
     do, and it was doing it to Ethan, who owns the account. */
  const live = (lk.staked_sports || []);
  const money = lk.staked || (!spName && live.length > 0);
  const stake = lk.stake_units || 0.25;
  const whose = spName ? escapeHtml(spName)
                       : live.map((x) => x.toUpperCase()).join(", ");
  /* WHICH ROWS HAD MONEY ON THEM (ledger likely_report). The title said
     "staked" over a book whose first weeks were paper (Ethan, 2026-10-02:
     "we are not telling the truth"); the count of each, and the day the
     money began, are said under it. */
  const m0 = new Date(`${String(lk.money_from || "").slice(0, 10)}T12:00:00`);
  const moneyFrom = Number.isFinite(m0.getTime())
    ? m0.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
  const paperN = lk.paper_settled || 0, moneyN = lk.money_settled || 0;
  /* BEHIND ONE TAP (Ethan, 2026-10-02: "we honestly show too much" —
     "yeah do that"). The chance-band table and the per-sport game lines
     are the working under the record, not the record: folded, closed,
     under one summary line, the verdict and the by-market table above. */
  const gameLines = recLikelyGameLines(lk, sp);
  const moreHTML = bands || gameLines
    ? `<details class="rec-fold rec-ml-more"><summary>More — ${[bands ? "by chance band" : "",
        gameLines ? "game lines by sport" : ""].filter(Boolean).join(" and ")}</summary>
      ${bands ? `<div style="opacity:.7;font-size:.9em;margin-top:10px">By claimed
        probability — an average hides the shape, and the top of the board is what
        a reader actually bets.</div>
        <div class="card" style="padding:0;margin-top:6px">${bands}</div>` : ""}
      ${gameLines}</details>` : "";
  const mix = money && paperN && moneyN
    ? ` Of the ${paperN + moneyN} settled, ${paperN} were on paper and ${moneyN} had real money on them${
        moneyFrom ? ` (from ${moneyFrom})` : ""}.` : "";
  return `
    <div class="section-title">Most Likely — ${
      money ? "staked picks" : "the paper record"}${
      spName ? ` · ${escapeHtml(spName)}` : ""}
      <span class="sub">— ${money
        ? `the Most Likely list’s own picks, ${stake}u a row of real money on ${whose}, graded like every other
           bet.${mix} The board’s other picks are scored by tier above`
        : "journaled nightly at no risk, graded like every other bet"}${
      spName ? `. ${escapeHtml(spName)} rows only — every number in this
      section is that league’s own` : ""}</span></div>
    ${recDisclosure("What this is and what it is not", money ? `The board
      claims to rank who actually hits. ${whose} ${live.length > 1 ? "carry"
      : "carries"} ${stake}u of REAL money a row, staked from 2026-09-19 at
      Ethan’s call and BELOW the bar this book set for itself — knowingly, and
      it is named here rather than left to be discovered. ${!spName ? `The
      other leagues in this section are still paper, so the pooled numbers
      below mix the two; scope to a league to see one book at a time. ` : ""}Two
      separate questions are still being asked: whether the probability we
      printed was true, and whether betting it at the price shown makes money.
      A board can be perfectly calibrated and still lose to the vig — that is
      the expected outcome, not a contradiction — and the ROI column, not the
      hit column, is the one that settles it.` : `The board claims to
      rank who actually hits, and until it has a settled record that claim rests
      on a backtest. So the top of it is written down every night at a nominal
      stake with ZERO dollars behind it, and graded on the same pass as
      everything else. Nothing here touches the headline record and nothing here
      is a position. Two separate questions are being asked: whether the
      probability we printed was true, and whether betting it at the price shown
      would have made money. A board can be perfectly calibrated and still lose
      to the vig — that is the expected outcome, not a contradiction — so real
      money stays off until the ROI column, not the hit column, has earned it.`)}
    <div class="card" style="padding:12px 14px;margin-bottom:12px">
      <b>${escapeHtml(lk.verdict || "")}</b></div>
    <div class="stats rec-kpis">
      ${recTile("Claimed vs actual",
                cal.n ? `${pct(cal.claimed)} → ${pct(cal.actual)}` : "—",
                cal.n ? (cal.real ? "a real gap — outside the noise band"
                                  : "inside the noise band")
                      : "nothing settled yet",
                { lead: true, tone: cal.n && cal.real && cal.gap < 0 ? "bad" : "" })}
      ${recTile(money ? "ROI" : "Paper ROI",
                lk.settled ? (lk.roi >= 0 ? "+" : "") + (lk.roi * 100).toFixed(1) + "%" : "—",
                money ? `at the price shown · ${stake}u a row on ${whose}`
                      : "at the price shown · no money staked",
                { tone: toneOf(lk.roi) })}
      ${recTile("Settled", `${lk.wins}-${lk.losses}`,
                lk.enough ? `${lk.open} open` : `${lk.open} open · ${lk.needed} needed for a verdict`)}
      ${recTile("Sample", `${cal.n || 0}`,
                lk.enough ? "enough to judge" :
                  `${Math.max(0, lk.needed - (cal.n || 0))} more to go`,
                { tone: lk.enough ? "good" : "" })}
    </div>
    ${markets ? `<div style="opacity:.7;font-size:.9em;margin-top:14px">Most Likely picks by market —
      this book’s own picks only; Pick of the Day and the Edge picks are scored in
      their own sections. A scorer market is split by side, since “scores” and “no TD”
      are opposite bets, and a return on fewer than ${shelfBar} settled is left uncoloured —
      too few to read either way. If one market holds up and another does not, that is a
      shelf-level decision.</div>
      <div class="card" style="padding:0;margin-top:6px">${markets}</div>` : ""}
    ${moreHTML}`;
}

/* THE GAME ROWS, PER SPORT, because the table above pools them.

   The board began carrying game lines on 2026-09-02 — moneylines
   ranked, spreads and totals as labelled leans — and they journal to
   the same book as the player rows. `by_market` above therefore mixes
   an NFL moneyline with an MLB one, and those are different models with
   different records: the pooled line can read fine while one sport
   quietly pays for the other.

   `ledger.likely_report` cuts it per sport and market; the weekly
   maintenance log already prints it. This is the same cut on the page a
   reader actually opens, which is the rule this bucket exists under —
   a measurement nobody can read is not a measurement. */
function recLikelyGameLines(lk, sp) {
  const by = (lk || {}).by_sport_market || {};
  const sports = Object.keys(by).sort();
  if (!sports.length) return "";
  const pct1 = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
  const rows = sports.map((sp) => {
    const markets = by[sp] || {};
    return Object.keys(markets).sort().map((m) => {
      const d = markets[m] || {};
      return `<div class="rl-row rl-cal ${d.actual >= d.claimed ? "won" : "lost"}">
        <span class="rl-date">${escapeHtml(sp.toUpperCase())}</span>
        <span class="rl-main">${escapeHtml(marketWord(m))} — said ${pct1(d.claimed)}
          · hit <strong>${pct1(d.actual)}</strong></span>
        <span class="rl-proc">${d.w}/${d.n}</span>
        <span class="rl-pnl ${toneOf(d.roi)}">${d.roi >= 0 ? "+" : ""}${
          (d.roi * 100).toFixed(1)}%</span>
      </div>`;
    }).join("");
  }).join("");
  if (!rows) return "";
  // The lede changes with the cut. On a league's own page the sports are
  // not being separated — there is only one — so promising a per-sport
  // split would describe a table the reader is not looking at.
  return `<div style="opacity:.7;font-size:.9em;margin-top:14px">${sp
    ? `Most Likely game lines by market — this board’s picks only (Pick of the
       Day’s spreads and moneylines are counted in its own section). Moneylines
       are ranked; spreads and totals ride as leans and say so on the board.`
    : `Game lines, per sport — the table above pools them, and an NFL moneyline
       and an MLB one are different models. Moneylines are ranked; spreads and
       totals ride as leans and say so on the board.`}</div>
    <div class="card" style="padding:0;margin-top:6px">${rows}</div>`;
}

function recLongshotSection(ls) {
  // Show whenever EITHER bucket has data — after the watchlist split the
  // picks record can be tiny while the calibration sample is huge.
  const hasWatch = ls && ls.watch && (ls.watch.graded || ls.watch.open);
  if (!ls || (!ls.settled && !ls.open && !hasWatch)) return "";
  const graded = ls.wins + ls.losses;
  const hitRate = graded ? (ls.wins / graded) * 100 : 0;
  const calib = ls.avg_model_prob != null
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px">
         Calibration (picks + watchlist, ${ls.calibration_n || 0} graded): model claimed
         <strong>${(ls.avg_model_prob * 100).toFixed(1)}%</strong>
         on average · books implied <strong>${(ls.avg_implied_prob * 100).toFixed(1)}%</strong>
         · actually hit <strong>${(ls.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Model above books AND actual above implied = the board finds real value.</div>` : "";
  const watch = ls.watch && (ls.watch.graded || ls.watch.open)
    ? `<div class="rec-note">
         Watchlist sample — <b>closed, no longer growing</b>. This tracked every
         real-priced homer on the slate to tune the model, at a couple of hundred rows a
         night, and it was more journal than the picks it was meant to inform.
         Final: <strong>${ls.watch.wins}/${ls.watch.graded}</strong> graded
         (${ls.watch.open} still open), flat-stake
         <strong>${ls.watch.roi >= 0 ? "+" : ""}${(ls.watch.roi * 100).toFixed(1)}% ROI</strong>.
         It never entered the record above.</div>` : "";
  // Same row component as the main settled list, so it inherits the same
  // alignment and the same phone treatment instead of clipping mid-word.
  const rows = (ls.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.market_label || "HR")}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Long Shots — tracked separately
      <span class="sub">— home runs &amp; anytime TDs, with their own ROI. Never mixed
      into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `Only the board’s actual
      PICKS — three per night at most — count toward this record, graded at a flat 0.1u
      nominal stake with zero bankroll impact. The watchlist (every real-priced home run
      on the slate, sometimes 100+ names) is tracked separately as a calibration sample
      and never enters this W-L: recommend a couple hundred homers a night and a handful
      always land, which proves nothing. These markets are long shots by nature, so even
      picks that clear the main board’s bar are quarantined here — a night of +650 darts
      would otherwise make the headline record describe the dart board instead of the
      picks the model stands behind. Judge the ROI and calibration over weeks, not the
      hit column.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (ls.roi >= 0 ? "+" : "") + (ls.roi * 100).toFixed(1) + "%",
                `${ls.net_units >= 0 ? "+" : ""}${(ls.net_units || 0).toFixed(2)}u on ${(ls.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(ls.roi) })}
      ${recTile("Long-shot record", `${ls.wins}-${ls.losses}`,
                `picks only · ${ls.open} open`)}
      ${recTile("Hit rate", hitRate.toFixed(1) + "%",
                ls.avg_implied_prob != null
                  ? `books implied ${(ls.avg_implied_prob * 100).toFixed(1)}%`
                  : "plus-money — low is normal")}
      ${recTile("Avg price", ls.avg_odds == null ? "—" : american(ls.avg_odds),
                ls.odds_range ? `range ${american(ls.odds_range[0])} to ${american(ls.odds_range[1])}`
                              : "accrues as picks settle")}
    </div>
    ${Object.keys(ls.by_sport || {}).length > 1 ? `<div style="margin-top:8px">
      ${Object.entries(ls.by_sport).map(([s, d]) =>
        `<span class="chip">${escapeHtml(s.toUpperCase())} ${d.w}/${d.n}
           (${d.net_u >= 0 ? "+" : ""}${d.net_u.toFixed(2)}u)</span>`).join(" ")}</div>` : ""}
    <div class="card" style="padding:0;margin-top:12px">${calib}${rows ||
      `${panelEmpty("Nothing settled yet — accrues from tonight’s board.")}`}${watch}</div>`;
}

/* Calibration: when the model said X%, how often did it actually happen.
   Rendered as honest rows with a sample-size band — small buckets read as
   "too early", never as verdicts. */
function calBucketRows(buckets) {
  return (buckets || []).map((b) => {
    const off = Math.abs(b.actual - b.predicted);
    const flag = b.n < 20 ? `<span style="opacity:.5">n=${b.n} — too early</span>`
      : b.in_band ? `<span style="color:var(--good)">${icon('check')} within noise (n=${b.n})</span>`
      : `<span style="color:var(--warn)">${icon('warn')} off by ${(off * 100).toFixed(0)} pts (n=${b.n})</span>`;
    const bar = (v, color) => `<span style="display:inline-block;height:8px;border-radius:4px;
        width:${Math.max(2, v * 100)}px;background:${color};vertical-align:middle"></span>`;
    return `<div class="rec-row mid">
      <span style="min-width:78px;opacity:.7">${b.lo}–${b.hi}%</span>
      <span style="flex:1;min-width:220px">
        ${bar(b.predicted, "var(--brand)")} <span style="font-size:.8em;opacity:.65">said ${(b.predicted * 100).toFixed(0)}%</span>
        &nbsp; ${bar(b.actual, b.in_band ? "var(--good)" : "var(--warn)")} <span style="font-size:.8em;opacity:.65">hit ${(b.actual * 100).toFixed(0)}%</span>
      </span>
      <span style="min-width:150px;text-align:right;font-size:.85em">${flag}</span>
    </div>`;
  }).join("");
}

/* Brier and log loss, side by side, each against the de-vigged market on the
   same picks. Two strictly proper rules rather than one, because they
   disagree in a way that is itself informative: Brier charges 0.90 for a
   confident miss and log loss charges 3.00, so a model that wins on Brier
   and loses on log loss is paying for rare, loud, wrong calls. */
function scoreRule(label, model, market, edge, note) {
  if (edge == null) return "";
  const good = edge > 0;
  return `<div style="flex:1;min-width:170px">
    <div style="font-size:.78em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55;margin-bottom:3px">${escapeHtml(label)}</div>
    <div style="font-size:1.05em;font-variant-numeric:tabular-nums">
      <span style="color:var(--${good ? "good" : "warn"})">${model}</span>
      <span style="opacity:.45"> vs ${market} market</span></div>
    <div style="font-size:.8em;opacity:.6;margin-top:2px">${escapeHtml(note)}</div>
  </div>`;
}

function calScoreBlock(cal) {
  const cards = [
    scoreRule("Brier", cal.brier_model, cal.brier_market, cal.brier_edge,
              cal.brier_edge > 0 ? "we forecast our own picks better"
                                 : "the market forecasts our picks better"),
    scoreRule("Log loss", cal.logloss_model, cal.logloss_market, cal.logloss_edge,
              cal.logloss_edge > 0 ? "and it holds under the harsher rule"
                                   : "the confident calls are where it costs"),
  ].filter(Boolean).join("");
  if (!cards) return "";
  const ece = cal.ece == null ? "" : `<div style="flex:1;min-width:170px">
    <div style="font-size:.78em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55;margin-bottom:3px">Calibration error</div>
    <div style="font-size:1.05em;font-variant-numeric:tabular-nums">${(cal.ece * 100).toFixed(1)} pts</div>
    <div style="font-size:.8em;opacity:.6;margin-top:2px">average distance from the diagonal</div>
  </div>`;
  const disagree = (cal.brier_edge != null && cal.logloss_edge != null
                    && (cal.brier_edge > 0) !== (cal.logloss_edge > 0))
    ? `<p style="margin:10px 0 0;font-size:.85em;color:var(--warn)">The two rules
        disagree. Both are strictly proper, so this is not a contradiction — it
        means the gap between us and the market is concentrated in the
        confident calls rather than spread across the book. Log loss is the
        one that punishes those, so it is the one to believe.</p>` : "";
  return `<div class="rec-block">
    <div class="rec-cards">${cards}${ece}</div>
    <p style="margin:10px 0 0;font-size:.85em;opacity:.62">Lower is better for both.
      Scored against the de-vigged closing price on the same bets — if we can’t
      out-forecast the close on our own selections, the edge story is fiction.
      Shown either way, because a site that hides this number is a tout with a
      website.</p>${disagree}</div>`;
}

/* Calibration split by market and by horizon.

   The aggregate is the honest headline, and it is also where a real defect
   hides: a model three points hot on one market and three cold on another
   averages to a line that looks perfect. Measured on a test board, an
   aggregate ECE of 7.4 points covered one market sitting dead on the
   diagonal and another twenty points hot.

   Behind a disclosure because it is diagnostic, not the answer — and
   because a page that opens with eleven charts has no headline at all. */
function calSplitRow(label, c) {
  const ece = c.ece == null ? "—" : (c.ece * 100).toFixed(1) + " pts";
  const tone = c.ece == null ? "" : c.ece <= 0.03 ? "var(--good)"
    : c.ece <= 0.07 ? "var(--warn)" : "var(--bad)";
  return `<div class="rec-row flush">
    <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
                 white-space:nowrap">${escapeHtml(label)}</span>
    <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${c.n}</span>
    <span style="min-width:74px;text-align:right;color:${tone};
                 font-variant-numeric:tabular-nums">${ece}</span>
  </div>`;
}

function recCalibrationSplits(s) {
  if (!s) return "";
  // Raw market keys, as recBucketTable already shows them a few sections up.
  // Two names for one market on one page is worse than one ugly name.
  const mk = (s.markets || []).map((c) => calSplitRow(c.market, c)).join("");
  const hz = (s.horizons || []).map((c) => calSplitRow(c.label, c)).join("");
  if (!mk && !hz) return "";
  const held = s.markets_held_back
    ? `<p style="margin:6px 0 0;font-size:.82em;opacity:.55">
        ${plural(s.markets_held_back, "more market")} haven’t reached ${s.min_n} graded
        picks. They’re in the headline number above — they just can’t carry a
        row of their own yet, because the band would be wider than any miss it
        could show.</p>` : "";
  // Degenerate means fewer than two buckets clear the bar — so the rows are
  // worth showing but a COMPARISON between them is not yet supported. The
  // first draft of this copy said "every pick resolves the day it was
  // published" while a 1–3 day row sat underneath it, which is the kind of
  // sentence that quietly teaches a reader to stop trusting the captions.
  const hzBlock = !hz ? "" : s.horizon_degenerate
    ? `<div class="section-title">By horizon</div>
       <p style="margin:0;font-size:.85em;opacity:.6">Only one horizon has
         reached ${s.min_n} graded picks, so there is nothing to compare
         against yet — read these as counts, not as a trend. Calibration is
         known to decay the further out you forecast, and this will say
         something real once futures start settling.</p>${hz}`
    : `<div class="section-title">By horizon
         <span class="sub">— calibration decays the further out you forecast.</span></div>
       ${hz}`;
  return recDisclosure("Calibration by market and horizon", `
    <p style="margin:0 0 8px;font-size:.85em;opacity:.7">Distance from the
      diagonal, per slice. The headline number can look clean while covering a
      market that runs hot and one that runs cold — they average out, and the
      average is the one figure that cannot show it.</p>
    ${mk ? `<div class="section-title">By market</div>${mk}${held}` : ""}
    ${hzBlock}`);
}

/* The forecast log. "Permanent and time-stamped" is a promise until it is
   checkable; this is what makes it checkable. */
function recForecastLog(f) {
  if (!f || !f.n) return "";
  if (!f.ok) {
    return `<div class="card" style="padding:12px 14px;margin-top:12px;
        border-color:var(--bad)">
      <strong style="color:var(--bad)">Forecast log broken at #${f.broken_at}.</strong>
      <p style="margin:6px 0 0;font-size:.87em">Entries up to
        #${f.verified_through} still verify; everything after that one is no
        longer provable. Shown rather than hidden — a tamper-evident log that
        hides its own alarm is decoration.</p></div>`;
  }
  /* THE CHAIN, CHECKED AGAINST THE JOURNAL (audit P0-1, 2026-09-30). A
     sealed forecast the journal no longer matches is "drifted"; one with
     no logged change behind it is "unexplained" — edits made before the
     change log existed land there once, and the nightly check fails if
     that number ever grows. */
  const drift = Number(f.drifted || 0), unexp = Number(f.unexplained || 0);
  const driftLine = drift
    ? `<p style="margin:6px 0 0;font-size:.84em">${drift.toLocaleString()} sealed
        ${drift === 1 ? "forecast no longer matches" : "forecasts no longer match"} the
        journal — ${(drift - unexp).toLocaleString()} with a logged change (listed
        below), ${unexp.toLocaleString()} unexplained, from before every change was
        logged.</p>` : "";
  return `<div class="card" style="padding:12px 14px;margin-top:12px">
    <div style="font-size:.8em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55">Forecast log · ${f.n.toLocaleString()} sealed</div>
    <div style="font-family:var(--font-mono);font-size:.8em;word-break:break-all;
                margin-top:4px;opacity:.85">${escapeHtml(f.head || "")}</div>
    <p style="margin:6px 0 0;font-size:.84em;opacity:.62">Every pick is hashed
      together with the hash before it — what we claimed, the price, and (since
      September 30) the lead time and the seal time — so editing or deleting any
      past forecast changes every hash after it and the chain reports where.
      Results arrive later, so they are not in this chain; every change to a
      graded pick is logged in its own chain instead, below. Write this number
      down: if it ever covers a different past, that is detectable rather than
      deniable.</p>${driftLine}
  </div>`;
}

/* CHANGES TO SETTLED PICKS (audit P0-1). Every re-grade, moved book and
   retired duplicate, with what it was and what it became, from a log the
   database writes itself and chains like the forecasts. */
function recRegrades(r, a, heads) {
  if (!r && !a) return "";
  const rows = (r && r.recent) || [];
  const fmt = (v) => (v == null ? "—" : String(v));
  const head = a && a.head
    ? `<div style="font-family:var(--font-mono);font-size:.78em;word-break:break-all;
         margin-top:4px;opacity:.8">${escapeHtml(a.head)}</div>` : "";
  const broken = a && a.ok === false
    ? `<p style="margin:6px 0 0;color:var(--bad)">Change log broken at #${a.broken_at}.</p>` : "";
  const list = rows.slice(0, 12).map((x) => {
    const ch = Object.entries(x.changes || {}).map(([k, [o, n]]) =>
      `${escapeHtml(k)} ${escapeHtml(fmt(o))} → ${escapeHtml(fmt(n))}`).join(" · ");
    return `<li><span class="mono">${escapeHtml(String(x.ts || "").slice(0, 10))}</span>
      ${escapeHtml(x.player || "")} ${escapeHtml(x.market || "")} — ${ch}
      <span style="opacity:.6">(${escapeHtml(x.reason || "unlabelled")})</span></li>`;
  }).join("");
  return `<div class="card" style="padding:12px 14px;margin-top:12px">
    <div style="font-size:.8em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55">Changes to settled picks · ${((r && r.n) || 0).toLocaleString()} logged</div>
    ${head}${broken}
    ${list ? `<ul style="margin:8px 0 0;padding-left:18px;font-size:.84em">${list}</ul>`
           : `<p style="margin:6px 0 0;font-size:.84em;opacity:.62">No settled pick has
               changed since the change log began.</p>`}
    <p style="margin:6px 0 0;font-size:.8em;opacity:.55">Written by the database on every
      change, whatever made it, and chained so a removed entry breaks the chain.</p>
    ${recHeadsList(heads)}
  </div>`;
}

/* The daily chain heads (`forecast_heads` in record.json). One line a day,
   newest first: save any of them and a later rewrite of the journal shows
   up as a head that no longer matches. */
function recHeadsList(heads) {
  const hs = (heads || []).slice(-7).reverse();
  if (!hs.length) return "";
  const cut = (h) => (h ? String(h).slice(0, 16) + "…" : "—");
  const li = hs.map((h) => `<li><span class="mono">${escapeHtml(String(h.day || ""))}</span>
      forecasts ${Number(h.forecast_n || 0).toLocaleString()}
      <span class="mono">${escapeHtml(cut(h.forecast_head))}</span> · changes
      ${Number(h.audit_n || 0).toLocaleString()}
      <span class="mono">${escapeHtml(cut(h.audit_head))}</span>${h.ok === false
        ? ` <b style="color:var(--bad)">broken</b>` : ""}</li>`).join("");
  return `<div style="margin-top:10px;font-size:.8em;opacity:.8">Daily chain heads
      (save one; a rewritten journal will not match it):
      <ul style="margin:4px 0 0;padding-left:18px">${li}</ul></div>`;
}

/* The learning loop, on the page.

   Everything here happens nightly with nobody touching a dial: the refit
   reads every settled bet and turns one temperature per market, a fit that
   runs to its search boundary closes the market by itself, and every sweep
   is stamped with the commit that produced it. It was all real and all
   invisible — and a learning loop nobody can see is indistinguishable from
   a static model. */
function recRestatedSection(rs, sport) {
  // The record re-priced AND re-sized by the model we have now: the
  // selection haircut applied to the claim, then the price ladder on the
  // stake. The official record stays the receipts of bets as they were
  // made — this answers "what WOULD it read" without editing a row.
  if (!rs) return "";
  const r = sport ? (rs.by_sport || {})[sport] : rs.overall;
  if (!r) return "";
  // NOT `!r.settled`. A restatement where the corrected probabilities
  // clear nothing is the loudest result this block can produce — today's
  // model would have refused the whole book — and returning "" made it
  // render as an absence. It has its own copy now.
  if (!r.settled) {
    return !r.excluded ? "" : `
      <div class="section-title">At today’s model
        <span class="sub">— the same graded picks, re-priced and re-staked
        by the board as it now runs.</span></div>
      <div class="card" style="border-left:3px solid var(--brand)">
        <p style="margin:0;font-size:var(--fs-md)">
          <b style="color:var(--brand)">It refuses all
          ${r.excluded.toLocaleString()} of them.</b> Corrected by the
          selection haircut, not one of these claims still clears
          break-even at the price it was taken at — so today’s model would
          not have placed the bet.</p>
        <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
          That is a statement about the CLAIMS, not the results. It does not
          mean these were bad nights; it means the probabilities behind them
          were about nine points too high, which is the gap the haircut was
          measured on. The record above is unchanged and stays unchanged —
          those bets were made at those stakes and the money moved.</p>
      </div>`;
  }
  const roi = (r.roi ?? 0) * 100;
  const tone = (v) => v >= 0 ? "var(--good)" : "var(--bad)";
  return `
    <div class="section-title">At today’s model
      <span class="sub">— the same graded picks, re-priced by the selection
      haircut and re-staked by the price ladder. Picks the corrected
      probability no longer clears are dropped, not re-sized. The official
      record above is the receipts as bet; this is what those nights would
      have returned under the board as it now runs.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Restated record</div>
        <div class="v">${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ""}</div>
        <div class="tile-sub">${(r.settled ?? 0).toLocaleString()} ${pluralWord(r.settled ?? 0, "pick")} re-sized</div></div>
      <div class="tile"><div class="k">Units staked</div>
        <div class="v">${(r.units_staked ?? 0).toLocaleString()}</div></div>
      <div class="tile"><div class="k">Net units</div>
        <div class="v" style="color:${tone(r.net_units ?? 0)}">${(r.net_units ?? 0) >= 0 ? "+" : ""}${(r.net_units ?? 0).toFixed(2)}</div></div>
      <div class="tile"><div class="k">Restated ROI</div>
        <div class="v" style="color:${tone(roi)}">${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%</div>
        <div class="tile-sub">weighted by conviction, not by ticket count</div></div>
    </div>
    ${r.excluded ? `<p class="list-note" style="margin-top:8px">${r.excluded.toLocaleString()}
      old ${pluralWord(r.excluded, "pick")} are excluded — at their journaled probability and price,
      today’s Kelly would not have made those bets at all.</p>` : ""}`;
}

function recProseSection(pz, sport) {
  // The prose lanes: the nightly postmortem and the weekly model brief.
  // The LLM narrates numbers the arithmetic already produced — never a
  // probability, never a pick. Scoped views show the sport's own
  // paragraph; coverage is structural (the engine back-fills every sport
  // it tracks), so a missing note means a missing night, not a mood.
  if (!pz || (!pz.postmortem && !pz.brief)) return "";
  const para = (e, missing) => {
    if (!e) return "";
    const note = sport ? ((e.by_sport || {})[sport] || missing) : e.overall;
    const when = e.date || e.week_of || "";
    return `
      <div class="rec-entry">
        <div style="font-weight:600;margin-bottom:4px">${escapeHtml(e.headline || "")}
          <span style="opacity:.45;font-weight:400;font-size:.85em"> · ${escapeHtml(when)}</span></div>
        <p style="margin:0;font-size:.9em;line-height:1.5">${escapeHtml(note || "")}</p>
        ${!sport && Object.keys(e.by_sport || {}).length ? `
          <div style="margin-top:8px;display:flex;flex-direction:column;gap:4px">
            ${Object.entries(e.by_sport).map(([sp, n]) => `
              <div style="font-size:.85em;color:var(--text-mute)">
                <span class="chip">${escapeHtml(sp.toUpperCase())}</span> ${escapeHtml(n)}</div>`).join("")}
          </div>` : ""}
      </div>`;
  };
  const capNote = pz.capped ? `
    <p style="padding:8px 14px;margin:0;font-size:.82em;color:var(--text-mute)">
      Paused for the month — the $${(pz.cap_usd ?? 5).toFixed(2)} LLM spend cap
      is reached ($${(pz.month_usd ?? 0).toFixed(2)} used). The arithmetic
      keeps learning either way; only the narration waits.</p>` : "";
  return `
    <div class="section-title">The night desk
      <span class="sub">— the one other job an AI that writes prose gets here:
      narrating. A nightly postmortem of what actually graded and a weekly
      note on what the learning ladder did — written from the arithmetic’s
      own numbers, never setting one. Capped spend, every call on the
      ledger.</span></div>
    <div class="card" style="padding:0">
      ${para(pz.postmortem, `No ${escapeHtml((sport || "").toUpperCase())} picks graded that night.`)}
      ${para(pz.brief, `Quiet week for ${escapeHtml((sport || "").toUpperCase())}.`)}
      ${capNote}
    </div>`;
}

/* WHERE EVERY SPORT STANDS IN THE LADDER, tuned or not (Ethan,
   2026-09-14: "It's only showing mlb and nothing about nfl or CFB"). A
   market under a floor is listed with the floor and the distance to it
   — collecting N of 200 graded bets, or N of 400 book-priced pairs —
   so an early sport reads as early, never as untreated. */
function learningCoverageHTML(cov, sport) {
  if (!cov) return "";
  const sports = Object.keys(cov).filter((s) => !sport || s === sport);
  const lines = [];
  sports.forEach((s) => {
    const c = cov[s] || {};
    const pending = Object.entries(c.markets || {}).filter(([, m]) => m.state !== "tuned");
    if (!pending.length && (c.tuned || 0) > 0) return;
    const head = `${escapeHtml(s.toUpperCase())} — ${(c.settled || 0).toLocaleString()} graded ${pluralWord(c.settled || 0, "bet")} on the journal, ${c.tuned || 0} market${c.tuned === 1 ? "" : "s"} tuned`;
    const body = pending.length
      ? pending.map(([mk, m]) => `<div style="padding:2px 0 2px 12px">${escapeHtml(mk)} · ${escapeHtml(m.note || m.state || "")}</div>`).join("")
      : `<div style="padding:2px 0 2px 12px">no graded bets with a stated probability yet — the ladder starts with its first settled pick</div>`;
    lines.push(`<div class="rec-note"><div>${head}</div>${body}</div>`);
  });
  if (!lines.length) return "";
  return `<div style="padding:4px 0 2px"><div class="mini" style="padding:6px 14px 2px;opacity:.75">Where each sport stands — the same floors for every league</div>${lines.join("")}</div>`;
}

function recSelfTuningSection(st, sport) {
  // `sport` scopes the section to one league's own learning — the ladder
  // fits every sport separately, so each sport's record page shows ITS
  // rows rather than hiding the whole section behind the "All" scope
  // (which is how the learning shipped invisible: the page always lands
  // sport-scoped, and nobody clicks All).
  if (!st) return "";
  const only = (rows) => (rows || []).filter((r) => !sport || r.sport === sport);
  const markets = only(st.markets);
  const weights = only(st.weights);
  const players = only(st.players);
  const closed = only(st.closed);
  const trendEntries = Object.entries(st.trend || {})
    .filter(([sp]) => !sport || sp === sport);
  if (!markets.length && !weights.length && !players.length
      && !trendEntries.length) {
    if (!sport) return "";
    return `
    <div class="section-title">The model tunes itself
      <span class="sub">— settled bets fit the dials; nobody turns one by hand.</span></div>
    <div class="card"><p style="margin:0;padding:12px 14px;font-size:.87em;color:var(--text-mute)">
      Nothing tuned for ${escapeHtml(sport.toUpperCase())} yet. The fitters run
      on every settle pass, on this sport’s own settled bets only, and adopt
      a correction only when it beats the spec in a walk-forward test — so this
      fills in as its journal deepens.</p>${learningCoverageHTML(st.coverage, sport)}</div>`;
  }
  const tone = (m) => m.at_boundary ? "var(--bad)"
    : Math.abs(m.temperature - 1) > 0.05 ? "var(--warn)" : "var(--good)";
  const rows = markets.map((m) => `
    <div class="rec-row">
      <span class="chip">${escapeHtml((m.sport || "").toUpperCase())}</span>
      <span style="flex:1;min-width:120px">${escapeHtml(m.market)}</span>
      <span style="font-variant-numeric:tabular-nums" title="Temperature: >1 pulls probabilities toward 50% (the model ran hot), <1 pushes them out (it ran shy)">T ${(m.temperature ?? 1).toFixed(2)}</span>
      <span style="color:${tone(m)}">${escapeHtml(m.reading || "")}</span>
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(m.samples ?? 0).toLocaleString()}</span>
      ${m.brier_before != null && m.brier_after != null && m.brier_after < m.brier_before
        ? `<span style="opacity:.6;font-variant-numeric:tabular-nums" title="Brier before → after the correction, on held-out outcomes">${m.brier_before.toFixed(4)} → ${m.brier_after.toFixed(4)}</span>` : ""}
    </div>`).join("");
  // A dial resting at ±1.0 is NOT "the search range was too small". r
  // interpolates toward a named endpoint curve, so +1.0 is that curve
  // exactly; one step past it puts a negative weight on vs_opp, which
  // would mean subtracting a player's own history from his projection.
  // The grid cannot widen. What the edge means depends entirely on
  // whether the dial was adopted, so the row has to say which:
  //   adopted  → the model wants a hotter recipe than this family holds,
  //              and the anchor itself is what to revisit. Red.
  //   not      → nothing was applied, and `plateau` says how many dial
  //              settings tied the winner. Most of them tying means the
  //              surface is flat and the argmin landed on an edge because
  //              argmins land somewhere. That is not a defect, and
  //              painting it red sent people looking for a bug.
  const dialTone = (w) => w.adopted
    ? (w.at_boundary ? "var(--bad)" : "var(--warn)") : "var(--good)";
  const dialNote = (w) => {
    if (!w.at_boundary || !w.grid_n) return "";
    const flat = w.plateau >= Math.max(2, w.grid_n * 0.5);
    const txt = w.adopted
      ? `at the family’s edge — the anchor curve is the thing to revisit, not the grid`
      : flat
        ? `${w.plateau}/${w.grid_n} dial settings tied — flat surface, the edge is where the search landed`
        : `${w.plateau}/${w.grid_n} tied — a real slope, but under the adoption bar`;
    return `<span style="opacity:.55;font-size:.92em">${escapeHtml(txt)}</span>`;
  };
  const weightRows = weights.map((w) => `
    <div class="rec-row">
      <span class="chip">${escapeHtml((w.sport || "").toUpperCase())}</span>
      <span style="flex:1;min-width:120px">${escapeHtml(w.market || "")}</span>
      <span style="font-variant-numeric:tabular-nums" title="The recency dial: 0 is the hand-tuned spec curve, positive leans on recent form, negative on the long run. ±1.0 is the end of the family, not the end of a search range. Moves only when the record beats the spec by a real margin.">dial ${(w.r ?? 0) >= 0 ? "+" : ""}${(w.r ?? 0).toFixed(1)}</span>
      <span style="color:${dialTone(w)}">${escapeHtml(w.reading || "")}</span>
      ${dialNote(w)}
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(w.samples ?? 0).toLocaleString()}</span>
      ${w.brier_default != null && w.brier_fitted != null
        ? `<span style="opacity:.6;font-variant-numeric:tabular-nums" title="Walk-forward Brier, spec curve → best curve on the grid. Lower is better; the dial is applied only when it wins by 0.0005 or more. Shown whether or not it was adopted — the margin IS the reason for the verdict.">${w.brier_default.toFixed(4)} → ${w.brier_fitted.toFixed(4)}</span>` : ""}
    </div>`).join("");
  const weightsBlock = !weightRows ? "" : `
    <div class="section-title">The recipe itself, refit
      <span class="sub">— not just the confidence: the blend a projection is built
      from. One dial per market decides how much recent form outweighs the long
      run; the record moves it only by beating the spec curve in a walk-forward
      test, and a dial it examined and left alone says so.</span></div>
    <div class="card" style="padding:0">${weightRows}</div>`;
  // The two walk-forward scores, shown whether the memory was adopted or
  // NOT. This used to render only on adopted rows, which meant a market
  // reading "memory off — didn't help" showed the verdict and hid the
  // evidence for it — you could not tell a memory that lost by a hair from
  // one that lost by a mile, and "didn't help" on its own reads like the
  // fit never ran. Both numbers are stored either way (playerfit.fit
  // computes them before it checks adoption), so there was nothing to
  // fetch — only something to stop hiding.
  const playerScore = (p) => {
    const before = p.score_baseline ?? p.brier_baseline;
    const after = p.score_corrected ?? p.brier_corrected;
    if (before == null || after == null) return "";
    const label = p.score_label || "Brier";
    // Lower is better for both Brier and projection error, so a fall is
    // the memory helping. Say which way it went in words — a reader should
    // not have to know that to read the row.
    const gain = before - after;
    const verdict = gain > 0 ? "memory scored better"
      : gain < 0 ? "memory scored worse" : "no difference";
    return `<span style="opacity:.6;font-variant-numeric:tabular-nums"
      title="Walk-forward ${escapeHtml(label)}, memory off → on: ${escapeHtml(verdict)} by ${Math.abs(gain).toFixed(5)}. Lower is better. Each bet’s correction knew only that player’s EARLIER games, so this is out-of-sample at every row. The memory switches on only when it wins by at least 0.0005.">${before.toFixed(4)} → ${after.toFixed(4)}</span>`;
  };
  const playerRows = players.map((p) => `
    <div class="rec-row">
      <span class="chip">${escapeHtml((p.sport || "").toUpperCase())}</span>
      <span style="min-width:100px">${escapeHtml(p.market || "")}</span>
      <span style="flex:1;min-width:140px;color:${p.adopted ? "var(--warn)" : "var(--good)"}">${escapeHtml(p.reading || "")}</span>
      ${(p.top || []).length ? `<span style="opacity:.75">${(p.top || [])
        .map((t) => `${escapeHtml(t.player)} ×${(t.mult ?? 1).toFixed(2)}`)
        .join(" · ")}</span>` : ""}
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(p.samples ?? 0).toLocaleString()}</span>
      ${playerScore(p)}
    </div>`).join("");
  const playersBlock = !playerRows ? "" : `
    <div class="section-title">Player memory
      <span class="sub">— who the blend persistently misreads. Each correction is
      shrunk by evidence and capped at ±15%, and the memory only switches on for
      a market when remembering players out-predicted forgetting them in a
      causal walk-forward test — "memory off" is a result, not a failure.</span></div>
    <div class="card" style="padding:0">${playerRows}</div>`;
  const trendRows = trendEntries.flatMap(([sp, mkts]) =>
    Object.entries(mkts).map(([mk, t]) => `
      <div class="rec-row">
        <span class="chip">${escapeHtml(sp.toUpperCase())}</span>
        <span style="flex:1;min-width:120px">${escapeHtml(mk)}</span>
        <span style="font-variant-numeric:tabular-nums">ECE ${((t.first || {}).ece ?? 0).toFixed(3)}
          → <span style="color:var(--${t.improved ? "good" : "warn"})">${((t.last || {}).ece ?? 0).toFixed(3)}</span></span>
        <span style="opacity:.5">${t.runs} sweep${t.runs === 1 ? "" : "s"}${t.same_code ? "" : " · across code versions"}</span>
      </div>`)).join("");
  const lastRefit = st.last_refit ? st.last_refit.replace("T", " ") : "—";
  return `
    <div class="section-title">The model tunes itself
      <span class="sub">— a market is fitted once it clears 200 settled bets, and
      REFITTED from every settled bet after that. This is the site’s AI lane:
      arithmetic on outcomes, reproducible and auditable, which is exactly why a
      chatbot never sets a probability here.</span></div>
    <div class="stats">
      <!-- The history of this caption is worth keeping, because it tracked a
           real defect for as long as the defect existed.

           It first said "runs itself after every settle", which was untrue.
           It was corrected to say the stamp only moves on a market’s FIRST
           fit — accurate, because the fitter skipped any market it had
           already corrected: those bets were priced UNDER the correction and
           refitting on them naively replaces a working number with ~1.0.

           That skip is now gone. A refit un-corrects each row by whatever was
           live when it was logged, so the whole journal is fittable and the
           stamp moves whenever any market learns something. The freeze was
           never the goal; it was the price of not having the inverse wired
           up. -->
      <div class="tile"><div class="k">Last fit</div><div class="v" style="font-size:var(--fs-lg)">${escapeHtml(lastRefit)}</div>
        <div class="tile-sub">every market refits from the whole journal —
          each bet’s claim is un-corrected by whatever was live when it was
          placed, so a correction can deepen instead of freezing</div></div>
      <div class="tile"><div class="k">Markets tuned</div><div class="v">${markets.length}</div></div>
      <div class="tile"><div class="k">Self-closed</div><div class="v">${closed.length}</div>
        <div class="tile-sub">a fit at its boundary shuts its own market</div></div>
      <div class="tile"><div class="k">Improving</div><div class="v">${(() => {
        const flat = trendEntries.flatMap(([, mkts]) => Object.values(mkts));
        return flat.length
          ? `${flat.filter((t) => t.improved).length}/${flat.length}` : "—";
      })()}</div>
        <div class="tile-sub">markets whose calibration error is falling</div></div>
    </div>
    <div class="card" style="padding:0">${rows}${learningCoverageHTML(st.coverage, sport)}</div>
    ${weightsBlock}
    ${playersBlock}
    ${trendRows ? `<div class="section-title">Is it getting better?
        <span class="sub">— the same measurement over time, each sweep stamped with the commit
        that produced it, so a move ties to a change rather than to a memory.</span></div>
      <div class="card" style="padding:0">${trendRows}</div>` : ""}
    ${recDisclosure("Why no chatbot sets these numbers", `
      <p style="margin:0;font-size:.87em">The refit is one parameter found by
      arithmetic over every settled outcome. That makes it reproducible (the same
      journal always yields the same temperature), auditable (each sweep is stored
      with its commit), and honest (the reliability chart above shows exactly what
      it did). A language model can do none of those: it does not reproduce run to
      run, cannot be swept over a quarter-million historical props, and cannot be
      temperature-scaled. So AI here means the system correcting itself from its
      own record — and prose staying prose. The decision is recorded in the
      competitive recipe, because it is the one pillar competitors who sell picks
      structurally cannot copy.</p>`)}`;
}

/* THE MOST LIKELY BOARD, GRADING ITSELF (engine/boardlearn). Ethan,
   2026-10-03: "we shouldn't have to constantly run tests for every sport
   like this to make it better and see where it's winning and losing." Every
   settle pass regrades each league's Most Likely record by maker, market
   and claimed chance, refits the record's corrections, and this draws the
   last run: where it holds up, where it over-claims, what it corrected. */
function recBoardLearningSection(bl, sport) {
  if (!bl) return "";
  const sports = Object.keys(bl).filter((s) => (!sport || s === sport) && bl[s] && bl[s].record);
  if (!sports.length) return "";
  const pct = (v) => `${Math.round((v ?? 0) * 100)}%`;
  const tone = (v) => v === "over-claims" ? "var(--bad)" : v === "beats its claim" ? "var(--good)" : "var(--text-mute)";
  const sliceRow = (s) => `
    <div class="rec-row">
      <span style="flex:1;min-width:150px">${escapeHtml(s.key)}</span>
      <span style="font-variant-numeric:tabular-nums">${s.won}-${s.n - s.won}</span>
      <span style="font-variant-numeric:tabular-nums">hit ${pct(s.hit)} · said ${pct(s.said)}</span>
      <span style="color:${tone(s.verdict)}">${escapeHtml(s.verdict)}</span>
    </div>`;
  const cutNames = { maker: "By where the pick came from", market: "By market", position: "By position",
    td_team_total: "Touchdown picks by the team’s expected points", claimed: "By the chance we claimed" };
  const blocks = sports.map((sp) => {
    const e = bl[sp];
    const r = e.record || {};
    const cal = e.calibration || {};
    const moved = Object.entries(cal.groups || {}).filter(([, g]) => (g.k ?? 1) < 1);
    const corrected = cal.passed
      ? (moved.length
        ? moved.map(([g, v]) => `<div class="rec-note">${escapeHtml(g.replace("|", " · "))}: hit ${pct(v.hit)} of ${v.n} where we said ${pct(v.claimed)} — now pulled ${Math.round((1 - v.k) * 100)}% of the way to the price</div>`).join("")
        : `<div class="rec-note">The record backs every group’s numbers as they are — nothing pulled.</div>`)
      : `<div class="rec-note">No correction proven yet on games the fit never saw — the board shows its own numbers.</div>`;
    const h = e.held || {};
    const held = h.n ? `
      <div class="mini" style="padding:8px 14px 2px;opacity:.75">Picks the board held back (our record and the matchup both said no)</div>
      ${sliceRow({ ...h, key: "Held back, graded anyway" })}` : "";
    const sc = e.scout;
    const scout = sc ? `
      <div class="mini" style="padding:8px 14px 2px;opacity:.75">The scout’s flags (${sc.matched} picks matched to their game)${sc.passed ? " — correction adopted" : ""}</div>
      ${(sc.flags || []).map((f) => sliceRow({ ...f, key: f.note })).join("")
        || `<div class="rec-note">No flag has ${15} graded picks yet.</div>`}` : "";
    const cuts = Object.entries(e.slices || {}).filter(([, rows]) => rows.length).map(([cut, rows]) => `
      <div class="mini" style="padding:8px 14px 2px;opacity:.75">${escapeHtml(cutNames[cut] || cut)}</div>
      ${rows.map(sliceRow).join("")}`).join("");
    return `
      <div class="card" style="padding:0;margin-bottom:12px">
        <div class="rec-row tall"><b style="flex:1">${escapeHtml(sp.toUpperCase())} — ${r.won ?? 0}-${(r.n ?? 0) - (r.won ?? 0)} on ${(r.n ?? 0).toLocaleString()} graded picks</b>
          <span>hit ${pct(r.hit)} · said ${pct(r.said)}</span>
          <span style="color:${tone(r.verdict)}">${escapeHtml(r.verdict || "")}</span></div>
        ${cuts}${scout}${held}
        <div class="mini" style="padding:8px 14px 2px;opacity:.75">What it corrected by itself · last run ${escapeHtml((e.at || "").replace("T", " "))} UTC</div>
        ${corrected}
      </div>`;
  }).join("");
  return `
    <div class="section-title">Where Most Likely wins and loses
      <span class="sub">— regraded after every settle, every league, nobody
      running anything. Each slice is judged against the chance we claimed
      for it, so long shots that land as often as we said read as holding
      up. A correction is adopted only when it scores better on games it
      never learned from, and dropped the day it stops.</span></div>
    ${blocks}`;
}

function recLossPatternsSection(lp, sport) {
  if (!lp || !(lp.n_records ?? 0)) return "";
  // Sport scope: each league's page shows the patterns mined from ITS
  // graded bets. The mining stats tiles stay whole-journal (one sweep
  // covers every sport) and say so when scoped.
  const findings = (lp.findings || [])
    .filter((f) => !sport || f.sport === sport);
  const closed = (lp.closed || []).filter((c) => !sport || c.sport === sport);
  const tone = (f) => f.action === "close" ? "var(--bad)"
    : (f.gap_pts ?? 0) > 0 ? "var(--warn)" : "var(--text-mute)";
  const rows = findings.map((f) => `
    <div class="rec-row">
      <span class="chip">${escapeHtml((f.sport || "").toUpperCase())}</span>
      <span style="min-width:100px">${escapeHtml(f.market || "all markets")}</span>
      <span style="flex:1;min-width:140px;font-weight:600">${escapeHtml(f.value || "")}</span>
      <span style="color:${tone(f)}">${escapeHtml(f.reading || "")}</span>
      ${f.action === "close"
        ? `<span class="chip" style="color:var(--bad)">vetoing picks</span>` : ""}
    </div>`).join("");
  const empty = (sport && (lp.findings || []).length) ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      No pattern involves ${escapeHtml(sport.toUpperCase())} — its graded bets
      are in every night’s sweep, and a clean sheet here is the sweep’s
      verdict, not its absence.</p>` : (lp.tested ?? 0) > 0 ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Scanned ${lp.tested} slice${lp.tested === 1 ? "" : "s"} of
      ${(lp.n_records ?? 0).toLocaleString()} graded bets — nothing survives
      false-discovery control yet. Patterns that look real on small samples
      usually aren’t, and a bar that bends to make the page interesting
      stops meaning anything. The bar stays.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Not enough graded bets in any one slice yet — a slice is only tested
      at ${lp.min_n ?? 40}+ settled picks. Every night’s grades feed this.</p>`;
  return `
    <div class="section-title">Learning from losses
      <span class="sub">— the miner slices every graded bet by side, price band,
      stated probability, horizon and book, hunting pockets where the model’s
      claims systematically missed. A pocket that runs hot enough closes itself
      and blocks new picks — the same self-closure markets already live under,
      one level finer.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Record mined</div><div class="v">${(lp.n_records ?? 0).toLocaleString()}</div>
        <div class="tile-sub">graded bets${sport ? ", all sports" : ""}, re-mined after every settle</div></div>
      <div class="tile"><div class="k">Slices tested</div><div class="v">${lp.tested ?? 0}</div>
        ${sport ? `<div class="tile-sub">whole journal, one sweep</div>` : ""}</div>
      <div class="tile"><div class="k">Patterns found</div><div class="v">${findings.length}</div>
        <div class="tile-sub">survivors of false-discovery control${sport ? `, ${escapeHtml(sport.toUpperCase())}` : ""}</div></div>
      <div class="tile"><div class="k">Self-closed</div><div class="v">${closed.length}</div>
        <div class="tile-sub">slices now vetoing new picks</div></div>
    </div>
    <div class="card" style="padding:0">${rows || empty}</div>
    ${recDisclosure("How this avoids fake trends", `
      <p style="margin:0;font-size:.87em">Every "trends" tab in this industry
      is a pattern-hallucination machine: slice one record forty ways and luck
      alone hands you two impressive streaks. Two disciplines here. First, a
      slice is judged on whether the model’s own stated probabilities missed
      reality (said 64%, hit 51%) — not on win rate, which would flag every
      honest longshot bucket. Second, every slice tested enters a
      Benjamini–Hochberg false-discovery correction, and only survivors are
      findings — the flagged set is expected to be at most
      ${Math.round(((lp.alpha ?? 0.05) * 100))}% luck. A pattern that clears
      both bars closes its slice automatically; the pick engines refuse
      anything that lands in it, and the veto’s reason names this page.</p>`)}`;
}

/* PREREGISTERED TESTS — the terms written down before the data.
   Ethan, 2026-08-13: "yeah do that, wire it into the lab."

   It sits beside the hypothesis lab and reads deliberately unlike it. The
   lab reports what a search FOUND; this reports what we said we would
   look for, and how far along it is. Those are different claims and the
   page must not let them look like the same one — a running total that
   reads like a result is exactly what preregistration is for. So a test
   still collecting shows PROGRESS and no number, and only a decided test
   shows a verdict. */
function recPrereg(pr) {
  const tests = (pr && pr.tests) || [];
  if (!tests.length) return "";
  const row = (t) => {
    if (t.status === "void") {
      return `<div class="pr-row"><span class="pr-claim">${escapeHtml(t.claim)}</span>
        <span class="chip down">void — terms changed</span></div>`;
    }
    if (t.status === "collecting") {
      const pct = Math.min(100, Math.round((t.n / t.min_n) * 100));
      return `<div class="pr-row">
        <span class="pr-claim">${escapeHtml(t.claim)}
          <span class="sub">registered ${escapeHtml(t.registered)} · deciding at
          ${t.min_n} bets, and not before</span></span>
        <span class="pr-prog"><i style="width:${pct}%"></i></span>
        <span class="pr-n">${t.n} / ${t.min_n}</span></div>`;
    }
    const tone = t.supported ? "down" : "";
    return `<div class="pr-row">
      <span class="pr-claim">${escapeHtml(t.claim)}
        <span class="sub">${escapeHtml(t.reading || "")}</span></span>
      <span class="chip ${tone}">${t.supported ? "supported" : "not supported"}</span></div>`;
  };
  return `<div class="section-title">Preregistered
      <span class="sub">— written down before the data arrived, and decided
      once at a sample size named in advance. A test still collecting shows
      progress, never a running result.</span></div>
    <div class="card">${tests.map(row).join("")}</div>`;
}

function recHypothesisLab(hl, sport) {
  if (!hl) return "";
  // Sport scope: each league's page shows the hypotheses ABOUT it. The
  // watchlist stays on the combined view — its ideas are free text with
  // no sport field to filter on.
  const hyps = (hl.hypotheses || [])
    .filter((h) => !sport || h.sport === sport);
  const n_of = (s) => hyps.filter((h) => h.status === s).length;
  const tone = (h) => h.action === "close" ? "var(--bad)"
    : h.status === "confirmed" ? "var(--warn)"
    : h.status === "rejected" ? "var(--good)" : "var(--text-mute)";
  const glyph = (h) => h.status === "confirmed" ? icon("check")
    : h.status === "rejected" ? icon("cross") : icon("dash");
  const rows = hyps.map((h) => `
    <div class="rec-row">
      <span style="color:${tone(h)}">${glyph(h)}</span>
      <span class="chip">${escapeHtml((h.sport || "").toUpperCase())}</span>
      <span style="min-width:90px">${escapeHtml(h.market || "all markets")}</span>
      <span style="flex:1;min-width:160px">${escapeHtml(h.claim || "")}
        <span style="opacity:.55;display:block;font-size:.92em">${
          Object.entries(h.dims || {}).map(([d, v]) => escapeHtml(String(v))).join(" × ")}</span></span>
      <span style="color:${tone(h)}">${escapeHtml(h.reading
        || (h.status === "collecting"
            ? `collecting — ${(h.n ?? 0)} matching bets so far` : ""))}</span>
      ${h.action === "close"
        ? `<span class="chip" style="color:var(--bad)">vetoing picks</span>` : ""}
    </div>`).join("");
  const watch = sport ? "" : (hl.watchlist || []).map((w) => `
    <div class="rec-row mute">· ${escapeHtml(w)}</div>`).join("");
  // The sport's own record count and the floor a claim needs, so "no
  // hypothesis yet" says how far the sport is from one (Ethan,
  // 2026-09-14: "I also don't see anything about nfl in the hypothesis
  // lab") instead of reading as a sport the lab skipped.
  const onFile = ((hl.coverage || {})[sport] ?? null);
  const floor = hl.min_n || 40;
  const standing = onFile == null ? "" : ` It has ${onFile.toLocaleString()} graded
      ${pluralWord(onFile, "bet")} on file; a claim about it is tested once ${floor}
      matching bets exist, and the lab reads this record on the same weekly
      pass as every other sport.`;
  const empty = (sport && (hl.hypotheses || []).length) ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      No hypothesis touches ${escapeHtml(sport.toUpperCase())} yet. The lab
      reads every sport’s record — including this one — and proposes
      wherever the evidence points.${standing}</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      The lab has nothing open right now. It reads the record’s own summary
      and proposes slice intersections the miner doesn’t test. Every proposal
      faces the same statistics as everything else on this page;
      nothing an AI writes here can ever set a probability.</p>`;
  return `
    <div class="section-title">The hypothesis lab
      <span class="sub">— the one safe job for an AI that writes prose: propose.
      A language model reads the record’s summary and suggests loss patterns
      built strictly from the miner’s own tested dimensions — the intersections
      no single-dimension sweep covers. The arithmetic disposes: same
      calibration test, same false-discovery bar, re-earned against the growing
      journal on every settle pass.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Confirmed</div><div class="v">${n_of("confirmed")}</div>
        <div class="tile-sub">survived the tribunal — so far</div></div>
      <div class="tile"><div class="k">Rejected</div><div class="v">${n_of("rejected")}</div>
        <div class="tile-sub">a published result, not a failure</div></div>
      <div class="tile"><div class="k">Collecting</div><div class="v">${n_of("collecting")}</div>
        <div class="tile-sub">under the ${hl.min_n ?? 40}-bet floor</div></div>
      <div class="tile"><div class="k">Vetoing</div><div class="v">${hyps.filter((h) => h.action === "close").length}</div>
        <div class="tile-sub">confirmed hot — blocking new picks</div></div>
    </div>
    <div class="card" style="padding:0">${rows || empty}${watch}</div>
    ${recDisclosure("Why the AI only proposes", `
      <p style="margin:0;font-size:.87em">The recorded rule stands: a language
      model never sets a probability, because it cannot be re-run, swept, or
      audited. Its one structural advantage is hypothesis generation — the
      miner tests every single dimension of the record but never their
      intersections, and a model that has read the summary can name the few
      worth testing. So proposals are constrained to the miner’s own menu of
      dimensions, convicted or acquitted by the same statistics that govern
      every number on this page, and re-tried nightly as new bets settle —
      a confirmation that was luck decays on its own. The model saw the record
      before proposing, which is exactly why first confirmations are treated
      as provisional and re-earned forever after.</p>`)}`;
}

/* The selection haircut — engine/selectionfit.py, rendered.

   The chart above this one grades the model's probability SURFACE, over
   every prop it can price. This grades the subset we actually bet, which
   is a different population and a much less flattering one: picking the
   top edges out of a noisy estimator picks, preferentially, the spots
   where the estimate is too high. A model can sit on the diagonal up
   there and still be nine points hot down here.

   Ethan asked for the lower number to be the one on display. So this
   block leads with the two figures side by side — what we claimed, what
   landed — and then says plainly what is being subtracted from every
   probability on the board as a result. */
function recSelectionHaircut(sh, scope) {
  if (!sh) return "";
  const pooled = sh.pooled || {};
  const sports = sh.sports || {};
  // Sport pages show their own row (and the pooled one they may be
  // borrowing); the all-sports page shows everything.
  const keys = Object.keys(sports).filter((s) => !scope || s === scope);
  if (!pooled.n && !keys.length) {
    return `<div class="section-title minor">The selection haircut
        <span class="sub">— not measured yet.</span></div>
      <div class="card"><p style="margin:0;font-size:var(--fs-sm);color:var(--text-mute)">
        Nothing has been fitted. The haircut is measured from settled bets at
        settle time; until a sport reaches ${sh.min_settled || 100} of them the
        board runs on the model’s own numbers.</p></div>`;
  }
  const pct = pctOr;
  // Deliberately NOT .rl-row: that grid has six fixed tracks sized for the
  // receipts table, and dropping three children into it crushes the middle
  // one to a 90px column. This is its own flex row.
  const row = (name, e, using) => {
    const live = !!e.applied;
    const gap = e.gap == null ? null : e.gap * 100;
    return `<div style="display:flex;gap:12px;align-items:flex-start;
                padding:9px 0;border-bottom:var(--hairline) solid var(--border-soft)">
      <span style="min-width:52px;color:var(--text-mute);font-size:var(--fs-sm);
            text-transform:uppercase;letter-spacing:.04em;padding-top:1px">${
        escapeHtml(name)}</span>
      <span style="flex:1;min-width:0">
        <span style="font-variant-numeric:tabular-nums">claimed
          <strong>${pct(e.claimed)}</strong> · landed
          <strong class="${gap == null ? "" : toneOf(gap)}">${pct(e.landed)}</strong>
          ${gap == null ? "" : `<span class="${toneOf(gap)}">(${gap >= 0 ? "+" : ""}${
            gap.toFixed(1)} pts, ±${((e.se || 0) * 100).toFixed(1)})</span>`}
          · ${e.n || 0} settled</span>
        <div style="font-size:var(--fs-sm);color:var(--text-mute);margin-top:3px">
          ${escapeHtml(e.reason || "")}</div></span>
      <span class="chip" style="flex-shrink:0${live || using === "pooled"
        ? ";color:var(--brand)" : ""}">${
        live ? `${e.shift.toFixed(3)} log-odds`
             : using === "pooled" ? "on the pooled cut" : "not applied"}</span></div>`;
  };
  const rows = keys.map((s) => row(s, sports[s], (sh.using || {})[s])).join("");
  // The sentence that answers "so what does it actually do to a bet?".
  // Break-even at −110 is 52.38%, so a claim that used to clear the bar
  // by two points can stop clearing it at all — which is the intended
  // consequence, not a side effect, and the copy says so.
  const live = keys.filter((s) => sports[s].applied).length || pooled.applied;
  const ex = (pooled.applied ? pooled : (sports[keys.find(
    (s) => sports[s].applied)] || {}));
  // Sports the pooled fit is live for elsewhere and refused to, named
  // here so the "every probability" sentence below stays true.
  const refused = keys.filter((s) => (sh.not_borrowing || {})[s]);
  const except = !refused.length ? "" : ` outside ${refused.map(
    (s) => escapeHtml(s.toUpperCase())).join(", ")}`;
  const effect = !live ? "" : `
    <p style="margin:10px 0 0;font-size:var(--fs-sm);color:var(--text-body)">
      Every probability on the board${except} is moved by this before anything
      is computed from it. A pick the model called <strong>55.0%</strong> now
      ships as <strong>${pct(ex.example_55)}</strong> — under the 52.4%
      a −110 price needs — so its edge, its EV and its stake all fall,
      and picks that only just cleared the bar stop clearing it. That is
      the correction working, not the board breaking.</p>`;
  // The held-out test is the reason to believe any of this, so it gets its
  // own sentence rather than living inside a row's fine print.
  const h = (ex || {}).holdout || {};
  const heldOut = !h.ran ? "" : `
    <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
      Validated out of sample before it was allowed to price anything: fitted on
      the first ${h.train_n} settled bets, then scored on the ${h.test_n} it had
      never seen. On those, the gap between claim and result went
      ${(h.gap_before * 100).toFixed(1)} → <strong>${(h.gap_after * 100).toFixed(1)}</strong>
      points and the Brier score ${h.brier_before.toFixed(4)} →
      <strong>${h.brier_after.toFixed(4)}</strong>. A correction that only
      improved the data it was fitted on would be refused here.</p>`;
  const borrowed = keys.filter((s) => (sh.using || {})[s] === "pooled");
  const borrowNote = !borrowed.length ? "" : `
    <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
      ${borrowed.map((s) => escapeHtml(s.toUpperCase())).join(", ")} ${
      borrowed.length > 1 ? "have" : "has"} no fit of ${
      borrowed.length > 1 ? "their" : "its"} own that cleared the bar, so ${
      borrowed.length > 1 ? "they are" : "it is"} borrowing the pooled number.
      What is being corrected is a property of how we SELECT — taking the top
      edges out of a noisy estimate — and that is shared by every sport on the
      board.</p>`;
  /* THE OTHER HALF OF THAT SENTENCE, and the reason the row above it can
     say "not applied" on a night when the pooled row says LIVE. A sport
     that is most of the pooled sample and was refused by its own
     walk-forward does not borrow: the pool is then mostly its own refused
     rows, which is not a second opinion about it. See
     engine/selectionfit.POOL_BORROW_MAX_SHARE. Unexplained, this reads as
     a bug on the one row the reader most wants to trust. */
  const refusedNote = !refused.length ? "" : `
    <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
      ${refused.map((s) => escapeHtml(s.toUpperCase())).join(", ")} ${
      refused.length > 1 ? "do" : "does"} not borrow it — ${refused.map(
      (s) => escapeHtml(sh.not_borrowing[s])).join(" · ")}. A pooled fit that
      is mostly one sport’s own refused bets is not a second opinion about
      that sport, so those bets price on the model’s own numbers.</p>`;
  return `<div class="section-title">The selection haircut
      <span class="sub">— the chart above grades the model’s whole surface.
      This grades the bets we actually made.</span></div>
    <div class="card">
      <p style="margin:0 0 10px;font-size:var(--fs-sm);color:var(--text-mute)">
        Selecting the biggest edges selects for our own overestimates, so the
        picks run hotter than the surface they came from. Measured on settled
        bets, pooled across markets, per sport — one number, shrunk by its own
        standard error and never applied upward.</p>
      ${pooled.n && !scope ? row("all", pooled, "own") : ""}${rows}
      ${effect}${heldOut}${borrowNote}${refusedNote}
      <p style="margin:10px 0 0;font-size:var(--fs-sm);color:var(--text-faint)">
        Last fitted ${escapeHtml(sh.fitted_at || "—")} · refits every settle
        pass, un-doing its own prior correction first so it cannot compound.</p>
    </div>`;
}

/* THE REPLAY, BESIDE THE JOURNAL (audit 2026-09-30, B1-1). The journal's
   Brier above grades the picks the site published; this grades every prop
   the model would have priced over stored history, walked forward — game i
   priced from the games before it only. Calibration numbers only: Brier,
   skill over always guessing the base rate, calibration error, and the
   basis, because a replay against a trailing-average line measures
   forecasting skill, never an edge over a book. */
const REPLAY_SPORT = { mlb: "MLB", nfl: "NFL", cfb: "College", nba: "NBA", wnba: "WNBA" };

function recReplaySection(rp, scope) {
  if (!rp || typeof rp !== "object") return "";
  const sports = Object.keys(REPLAY_SPORT)
    .filter((k) => rp[k] && rp[k].n && (!scope || scope === k));
  if (!sports.length) return "";
  const pct = (x) => x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "\u2212" : ""}${Math.abs(x * 100).toFixed(1)}%`;
  const basisWord = { book: "against harvested book lines", naive: "against a trailing-average line",
                      outcomes: "against who actually scored", mixed: "partly against book lines" };
  const rows = sports.map((k) => {
    const r = rp[k];
    const good = r.skill != null && r.skill > 0;
    return `<div class="rec-row" style="display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-top:1px solid var(--border)">
      <span>${escapeHtml(REPLAY_SPORT[k])}
        <span style="opacity:.6;font-size:.85em">· ${Number(r.n).toLocaleString()} priced · ${escapeHtml(basisWord[r.basis] || r.basis || "")}</span></span>
      <span style="font-variant-numeric:tabular-nums">Brier ${r.brier == null ? "—" : Number(r.brier).toFixed(3)}
        · <span style="color:var(--${good ? "good" : "warn"})">skill ${pct(r.skill)}</span></span>
    </div>`;
  }).join("");
  const when = rp.generated_at ? ` Replayed ${escapeHtml(rp.generated_at)}.` : "";
  return `<div class="section-title minor">Replay over stored history
      <span class="sub">— every prop the model would have priced, not just the ones we bet</span></div>
    <div class="rec-block">${rows}
      <p style="margin:10px 0 0;font-size:.85em;opacity:.62">Walk-forward: each game is
        priced only from the games before it, through the same pricer the boards use.
        Skill is how much better than always guessing the base rate; above zero means
        the forecasts carry information. This measures forecasting, not profit — the
        replay places no bets.${when}</p></div>`;
}

function recCalibrationSection(cal, era) {
  if (!cal || !cal.n || !(cal.buckets || []).length) return "";
  const rows = calBucketRows(cal.buckets);
  const brier = calScoreBlock(cal);
  // The hand-drawn diagram ships as the fallback; mountEChartsAnalytics
  // upgrades the wrapper to the interactive version (see visuals.js).
  const relWrap = (bks, svg) => !svg ? "" : `<div class="gloss-chart"
    style="min-height:240px" data-echart-reliability="${escapeAttr(JSON.stringify({
      buckets: (bks || []).filter((b) => b.n > 0).map((b) => ({
        predicted: b.predicted, actual: b.actual, n: b.n,
        ci: b.ci, in_band: b.in_band })),
    }))}">${svg}</div>`;
  const diagram = relWrap(cal.buckets, reliabilityDiagram(cal.buckets));
  const diagramBlock = !diagram ? "" : `
    <div class="rec-block chart">
      ${diagram}
      <p style="margin:8px auto 10px;max-width:420px;font-size:.83em;opacity:.6;text-align:center">
        Each dot is one probability bucket; its area is how many bets sit in it, and
        the whisker is the same sample-size band as the rows above. On the dashed
        line means the number meant what it said. Below it we ran hot, above it we
        ran cold, and a line that crosses is two different problems wearing one
        average.</p>
    </div>`;
  // Era scoping: the all-time chart is dominated by picks from RETIRED
  // gates. Until the current model has a real sample, say so; after ~50
  // graded, give it its own chart.
  const eraN = (era || {}).n || 0;
  const eraNote = eraN >= 50 ? "" : `
    <p class="rec-note">
      Era note: ${cal.n - eraN} of these ${cal.n} graded picks predate the model re-tune${
      (era || {}).since ? ` (${escapeHtml(era.since)})` : ""} — the misses above were mostly
      earned by gates that no longer exist. The current model gets its own chart here once
      ~50 of its picks settle (${eraN} so far). The nightly calibration refit already feeds
      these misses back into the model’s tempering.</p>`;
  // FOLDED. The era's table is the whole table again — eight rows, a
  // chart and three scores, a second time, on a phone (2026-09-06:
  // "everything seems cluttered"). Its heading stays where it was and
  // says what is inside; the rows open on a tap.
  const eraBlock = eraN >= 50 ? `
    <div class="section-title minor">Current model only
      <span class="sub">— the same test, restricted to picks graded since the
      ${escapeHtml((era || {}).since || "")} re-tune (n=${eraN}).</span></div>
    <details class="rec-epoch rec-fold">
      <summary>Open the current model’s own buckets, chart and scores</summary>
      <div class="card" style="padding:0">${calBucketRows(era.buckets)}
        <div class="rec-block chart">
          ${relWrap(era.buckets, reliabilityDiagram(era.buckets))}</div>${calScoreBlock(era)}</div>
    </details>` : "";
  return `<div class="section-title">Calibration — did "60%" mean 60%?
      <span class="sub">— every settled pick, bucketed by the model’s claimed probability.</span></div>
    <div class="card" style="padding:0">${rows}${diagramBlock}${brier}${eraNote}</div>
    ${eraBlock}`;
}

/* Account health: how sharp our own journaled action looks per book —
   inference from our patterns, clearly labeled as such. */
function recHealthSection(h) {
  if (!h || !(h.books || []).length) return "";
  const bandColor = { low: "var(--good)", moderate: "var(--warn)", elevated: "var(--bad)" };
  const cards = h.books.map((b) => `
    <div class="card" style="padding:14px 16px">
      <div style="display:flex;align-items:center;gap:10px">
        <strong style="flex:1">${escapeHtml(b.book)}</strong>
        <span style="font-weight:800;color:${bandColor[b.band] || "var(--brand)"}">${b.score}</span>
        <span class="chip" style="color:${bandColor[b.band] || "var(--brand)"}">${b.band} limit risk</span>
      </div>
      <div style="font-size:.85em;color:var(--text-mute);margin-top:6px">
        ${b.bets} graded bets · beats the close ${b.beat_close_rate == null ? "—" : (b.beat_close_rate * 100).toFixed(0) + "%"}
        · ${(b.concentration * 100).toFixed(0)}% in ${escapeHtml(b.top_market)}${
        b.prop_share == null ? "" : ` · ${(b.prop_share * 100).toFixed(0)}% props`}</div>
      ${(b.drivers || []).length ? `<ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${b.drivers.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
      ${(b.actions || []).length ? `<div style="margin-top:8px;font-size:.85em">
        <span style="color:var(--brand);font-weight:700">To stay welcome:</span>
        <ul style="margin:4px 0 0;padding-left:18px;color:var(--text-body)">
        ${b.actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
    </div>`).join("");
  // What the score CANNOT see, shipped beside it. A number built from four
  // of the seven signals a risk desk uses will be over-trusted by anyone who
  // can't tell which four — and one of the omissions is a decision rather
  // than a limitation, which is worth saying out loud.
  const blind = !(h.blind_spots || []).length ? "" : `
    <details style="margin-top:10px">
      <summary style="cursor:pointer;font-size:.85em;color:var(--text-mute)">
        What this score can’t see — and why</summary>
      <ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${h.blind_spots.map((s) => `<li><strong>${escapeHtml(s.signal)}</strong>
          — ${escapeHtml(s.why)}</li>`).join("")}
      </ul>
      <p style="font-size:.83em;opacity:.6;margin:8px 0 0">Books watch all of
        these. We score the four we can measure honestly and name the rest
        rather than implying a completeness this doesn’t have.</p>
    </details>`;
  return `<div class="section-title">Account health
      <span class="sub">— books quietly limit winners; this estimates how limit-prone our picks would look at each book if you tailed them. It reads our own journal, not your account.</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">${cards}</div>
    <p style="opacity:.55;font-size:.82em;margin-top:8px">${escapeHtml(h.disclaimer || "")}</p>
    ${blind}`;
}

/* UFC record — journaled fight picks in their own probation bucket,
   graded from post-card results. */
function recUfcSection(u) {
  if (!u || (!u.settled && !u.open)) return "";
  const graded = (u.wins || 0) + (u.losses || 0);
  const rows = (u.recent || []).map((b) => {
    const won = b.status === "won";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${won ? "won" : "lost"}">
      <span class="rl-icon">${won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">moneyline</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">UFC — tracked separately
      <span class="sub">— every journaled fight pick, graded from post-card results.
      Never mixed into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `Scalpy MMA’s picks journal at
      their real prices (one-fifth Kelly stakes) and settle automatically from ESPN’s
      fight results after each card. UFC is the newest graded module, so it earns its
      way like every other signal: its own bucket, its own ROI, and no place in the
      headline record until a real sample says it belongs there.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", fmtRoi(u.roi),
                `${(u.net_units || 0) >= 0 ? "+" : ""}${(u.net_units || 0).toFixed(2)}u on ${(u.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(u.roi) })}
      ${recTile("UFC record", `${u.wins || 0}-${u.losses || 0}`, `${u.open || 0} open`)}
      ${recTile("Hit rate", graded ? ((u.wins / graded) * 100).toFixed(1) + "%" : "—",
                "cards are small samples — judge after 50+")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `${panelEmpty("Grades after each card’s fights are official.")}`}</div>`;
}

/* Polymarket flag record — the Intel page's graded flags, quarantined in
   their own bucket exactly like Long Shots: paper-tracked observations,
   never mixed into the headline record. */
/* The looser-gates sampler — the standing "should the filters be looser?"
   question, answered by its own paper-tracked record instead of a debate. */
function recLooseSection(lo) {
  if (!lo || (!lo.settled && !lo.open)) return "";
  const graded = (lo.wins || 0) + (lo.losses || 0);
  const rows = (lo.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title minor">Looser-gates sampler — measurement in progress
      <span class="sub">— the props that JUST missed the bar, paper-tracked nightly.
      This bucket IS the answer to "should we loosen the filters?"</span></div>
    ${recDisclosure("How this decides anything", `Every build journals the
      near-misses — real-priced Tier 1/2 props within reach of the edge bar or a
      quality grade in the 60s — at a flat 0.1u with zero bankroll impact. If this
      bucket is PROFITABLE after 100+ graded, the real gates loosen and those props
      become picks. If it burns, the gates were right and the argument is over.
      Same promotion bar as every other probation signal on this page.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", graded ? fmtRoi(lo.roi) : "—",
                `${(lo.net_units || 0) >= 0 ? "+" : ""}${(lo.net_units || 0).toFixed(2)}u on ${(lo.units_staked || 0).toFixed(1)}u`,
                { lead: true, tone: toneOf(lo.roi) })}
      ${recTile("Record", `${lo.wins || 0}\u2011${lo.losses || 0}`, `${lo.open || 0} open`)}
      ${recTile("Toward the bar", `${graded}/100`,
                graded >= 100 ? "sample reached — read the ROI" : "graded picks needed")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `${panelEmpty("Nothing settled yet — accrues from tonight’s near-misses.")}`}</div>`;
}

function recPolymarketSection(v) {
  if (!v || !v.graded) return "";
  const pctv = pct;
  const rows = (v.recent || []).map((b) => `
    <div class="rl-row ${b.won ? "won" : "lost"}">
      <span class="rl-icon">${b.won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.resolved || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.side)} ${escapeHtml(b.outcome)}</strong>
        <span class="rl-bet">${escapeHtml(b.market)}</span></span>
      <span class="rl-proc" title="${escapeHtml(traderLabel(b))}">score ${b.score} · ${escapeHtml(traderLabel(b))}</span>
      <span class="rl-odds">${b.price != null ? (b.price * 100).toFixed(0) + "¢" : ""}</span>
      <span class="rl-pnl ${toneOf(b.roi)}">${b.roi >= 0 ? "+" : ""}${(b.roi * 100).toFixed(0)}%</span>
    </div>`).join("");
  return `
    <div class="section-title">Polymarket flags — tracked separately
      <span class="sub">— every informed-flow flag, graded when its market resolves.
      Paper-tracked, never mixed into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `The Polymarket page flags large
      anomalous trades and paper-tracks whether following that money wins. These are
      OBSERVATIONS graded at a flat nominal stake with zero bankroll impact — the fixed
      promotion bar (100+ graded, z ≥ 2, positive ROI) decides if they ever become
      recommendations. The verdict box on the Polymarket page always states the current
      answer.`)}
    <div class="stats rec-kpis">
      ${recTile("Flag record", `${v.wins}-${v.graded - v.wins}`,
                `${v.open || 0} open · ${v.graded} graded`)}
      ${recTile("Hit rate", pctv(v.hit_rate), `entry prices implied ${pctv(v.avg_implied)}`)}
      ${recTile("Flat-stake ROI", (v.roi >= 0 ? "+" : "") + pctv(v.roi),
                "if every flag were $1", { tone: toneOf(v.roi) })}
      ${recTile("Calibration z", String(v.z),
                v.z >= 2 ? "beating its prices" : "not yet distinguishable from price",
                { tone: v.z >= 2 ? "pos" : "" })}
    </div>
    <div class="card pm-rows" style="padding:0;margin-top:12px">${rows ||
      `${panelEmpty("Flags settle as their markets resolve.")}`}</div>`;
}          // null = follow the sport you are on

/* IS THERE ANYTHING TO SHOW FOR THIS LEAGUE — asked of every book, not
   just the one that takes money.

   Ethan, 2026-09-19, with the college Record page reading "Nothing
   journaled for College Football yet" while `record.json` carried 246
   graded Most Likely rows for it.

   `o` is `by_sport[sport].overall`, and that comes from
   `ledger.performance`, whose SQL is `category IN ('main','paper') AND
   stake_units > 0` — the EDGE book, staked. A league whose picks are
   journaled at a zero stake reads 0 settled and 0 open there however
   full its other books are, and a zero stake is exactly what PROBATION
   means. College football has been on it all season: the maintenance
   note calls it "journaled and graded, never staked". So the page asked
   the one book college cannot have rows in, believed the answer, and
   returned before `recBookSections` could draw the two books that were
   full.

   The books carry no stake filter — `book_records` counts wins and
   losses per category — so they are the honest test of whether a league
   has a record worth rendering. */
function recordHasSomething(o, books, own, shadow) {
  if ((o || {}).settled || (o || {}).open) return true;
  if ((own || {}).settled || (own || {}).open) return true;
  // `shadow` rides here rather than in its own clause because it is the
  // same shape and the same question: a league whose ONLY rows are
  // stale-line flags has still placed bets, and since 2026-09-19 the
  // page draws them under "Also tracked, never staked".
  return [books, shadow].some((m) => Object.values(m || {}).some(
    (b) => ((b || {}).w || 0) + ((b || {}).l || 0) > 0));
}

/* THE BOOK A SCOPE OWNS THAT NEITHER `by_sport` NOR `book_records` CAN
   SEE, so the check above can ask it before it calls a league empty.

   `by_sport` is `performance(sport, category=BOOK)` and `book_records`
   maps only the three categories in `ledger.BOOK_SECTIONS` — main,
   paper, likely, longshot. UFC picks are journaled under a category of
   their own, 'ufc', which is in neither, and they are read by
   `ledger.ufc_report` into its own top-level key and drawn by
   `recUfcSection` under "By product".

   So the UFC scope read 0 settled and 0 open with eighteen graded
   fights in the journal, hit the empty state, and returned one line
   ABOVE its own section. Ethan's record check on 2026-09-19 printed it
   as "ufc: empty" next to a journal holding 18 settled and 4 open —
   the same shape as the college bug in the same branch, one scope over.

   Returns whatever that scope's own book is, or null. Every other
   scope's books are already in the two arguments before it. */
function recordOwnBook(d, scope) {
  return scope === "ufc" ? ((d || {}).ufc_record || null) : null;
}

function recWinDate(iso) {
  const t = new Date(`${String(iso).slice(0, 10)}T12:00:00`);
  return Number.isFinite(t.getTime())
    ? t.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : String(iso);
}

function recordScopeHTML(d, scope) {
  const tracked = d.tracked_sports || [];
  const btn = (key, label, n) => ({ key, label, n });
  /* EVERY CHIP COUNTS THE SAME THING — rows journaled in that scope,
     open and settled together.

     They did not. "All bets" carried `overall.settled` while a sport
     carried `settled || open`, so the two badges were different
     quantities wearing the same shape. Caught on the phone on 2026-09-09,
     opening night, where the page read ALL BETS 17 · NFL 13 · MLB 17 —
     a reader adds 13 and 17, gets 30, and is looking at a total of 17.
     It was not an arithmetic error: 17 was every SETTLED row and 13 was
     the NFL's OPEN ones, because the NFL had nothing settled yet and the
     `||` fell through.

     The worse half was what happened next. The fallback means the NFL
     badge would have read 13 all evening and then dropped to 1 the
     instant the first bet of the season graded — a count that goes DOWN
     as more happens is the kind of thing you screenshot and send me.
     Summed, it only ever climbs, the sports add up to All bets, and the
     open/settled split is still one line below on the panel itself. */
  const journaled = (o) => ((o || {}).settled || 0) + ((o || {}).open || 0);
  /* AND THE SOURCE IS `journaled`, NOT `overall` — 2026-09-19.
     Everything above stayed true and was measuring the wrong pool.
     `overall` is `performance(...)`: the EDGE book, staked. Every other
     book a league keeps was outside it, so college football's chip read
     0 beside a page holding 246 graded Most Likely rows and 210
     stale-line flags, and UFC's read 0 beside eighteen graded fights.
     Ethan: "i want all bets shown on the record page that had been
     placed and cfb isnt showing that."

     `ledger.journaled_counts` is one scan with no category filter and
     no stake filter, which is what the sentence above always promised.
     "All bets" and the sports come from that same scan, so they still
     add up. The fallback to `overall` is for a file published before
     this key existed — the first load after a deploy, where the old
     narrow number beats a row of zeros. */
  const jc = d.journaled || {};
  const parts = [btn("all", "All bets",
                     journaled(jc.all || d.overall))];
  /* ZENO'S BETS (Ethan, 2026-09-26: "we should also have a button here for
     'Zenos Bets'"). Not a scope of this page — his book is its own
     record, graded by the books, not by us — so it opens his page, where
     his record and (for members) his bets live. Counted like the others:
     settled and riding together. */
  const zo = (d.zeno || {}).overall || {};
  const zn = (zo.settled || 0) + ((d.zeno || {}).open_n ?? zo.open ?? 0);
  if (zn) parts.push(btn("zeno", "Zeno’s Bets", zn));
  // Before Prediction Market (Ethan, 2026-09-26: "put the zenos bets
  // button before the prediction market button, not after").
  parts.push(btn("intel", "Prediction Market", null));
  for (const sp of tracked) {
    const r = (d.by_sport || {})[sp] || {};
    // A sport with nothing journaled is still listed. Hiding it would
    // make "no bets yet" and "no such board" look identical.
    parts.push(btn(sp, (SPORT_META[sp] || {}).name || sp.toUpperCase(),
                   journaled((jc.by_sport || {})[sp] || r.overall)));
  }
  return leagueChipsHTML(parts, { group: "rec-scopes", chip: "rec-scope", attr: "data-scope",
                                  active: scope, countClass: "rec-scope-n", label: "Record scope" });
}

function bindRecordScopes(host) {
  host.querySelectorAll(".rec-scope").forEach((b) =>
    b.addEventListener("click", () => {
      // His book opens his page (recordScopeHTML says why).
      if (b.dataset.scope === "zeno") { switchView("zeno", true); return; }
      _recordScope = b.dataset.scope;
      renderRecord();
    }));
  host.querySelectorAll(".rec-win").forEach((b) =>
    b.addEventListener("click", () => window._recSetRange(b.dataset.win || "all")));
}

/* The edge test, rendered as a verdict rather than three AUCs.

   Three numbers between 0.4 and 0.6 read as "fine" to anybody who is not
   already thinking about rank statistics, which is everybody at 1am. The
   verdict comes from `edgehistory.measure`, computed once server-side, so
   this panel and the nightly prose and the LLM's evidence pack cannot each
   invent their own reading of the same numbers. */
const EDGE_VERDICTS = {
  edge_is_noise: {
    tone: "neg", label: "No measurable edge",
    say: "Bets the model called better did not win more often than bets it "
       + "called worse. Its ranking and the market’s are the same ranking.",
    then: "Every gate, threshold and stake rule is a function of that "
        + "number, so tuning them cannot help. The model needs information "
        + "the market lacks, not better use of what it already has.",
  },
  edge_inverted: {
    tone: "neg", label: "Edge points backwards",
    say: "The claimed edge sorts winners BELOW losers.",
    then: "Worse than no signal — the gates are selecting against us.",
  },
  edge_predicts: {
    tone: "pos", label: "The edge signal is real",
    say: "Bets the model called better did win more often.",
    then: "The signal carries information, so losses are coming from price, "
        + "timing or sizing rather than from the pick itself.",
  },
};

function recEdgePanel(e, trend, overall) {
  const v = EDGE_VERDICTS[e.verdict] || EDGE_VERDICTS.edge_is_noise;
  const ci = (lo, hi) => (lo == null || hi == null) ? ""
    : `[${lo.toFixed(3)}, ${hi.toFixed(3)}]`;
  const row = (name, val, lo, hi, lead) => `
    <tr${lead ? ' class="lead-row"' : ""}><td>${escapeHtml(name)}</td>
    <td class="num">${val == null ? "—" : val.toFixed(3)}</td>
    <td class="num mini">${ci(lo, hi)}</td></tr>`;

  /* The series, only once it can show a change. One point is not a trend
     and drawing it as one invites reading noise as movement.

     COLOURED BY WHICH SIDE OF A COIN FLIP EACH RUN LANDED ON, per Ethan's
     render — 0.500 is the line the whole panel is about, so a wall of
     identical grey numbers was hiding the one thing the list says. */
  const runs = (trend || []).filter((r) => r.auc_edge != null);
  const spark = runs.length < 3 ? "" : `
    <p class="mini"><strong>Claimed-edge AUC</strong> over the last
    ${runs.length} runs:<br>${runs.map((r) => {
      const a = r.auc_edge;
      return `<span class="ev-run ${a >= 0.5 ? "pos" : "neg"}">${a.toFixed(3)}</span>`;
    }).join(" \u2192 ")}${
      runs.length > 1
      && Math.abs(runs[runs.length - 1].auc_edge - runs[0].auc_edge) < 0.02
      ? " — flat." : "."}</p>`;

  /* THE FOUR TILES, and every one of them is derived rather than typed.
     Ethan's render asks for a summary strip; a strip of hand-written
     reassurance is exactly what this panel exists to refuse, so each
     tile reads a number that is already on the page or already in the
     payload. "Data quality" is the one worth spelling out: it compares
     the rows the test could USE against the rows the record counts, so
     a book with picks missing a stored probability says so instead of
     claiming a clean sample it does not have. */
  /* eligible − n, BOTH FROM THE SNAPSHOT. This subtracted e.n from
     overall.settled, and settled counts pushes while the test can only
     use won/lost — so one push read as a missing probability, forever:
     "Partial — 1 settled pick(s) have no stored probability" on a book
     with nothing missing. A payload without `eligible` (a banked run)
     shows the dash rather than claiming either verdict. */
  const missing = (e.eligible != null && e.n != null)
    ? Math.max(0, e.eligible - e.n) : null;
  const trust = { edge_is_noise: ["No", "Edge not better than market"],
                  edge_inverted: ["No", "Edge sorts winners below losers"],
                  edge_predicts: ["Yes", "Edge beats the market’s ranking"],
                }[e.verdict] || ["No", "Edge not better than market"];
  let stamp = "—", stampSub = "Refreshes with new data";
  if (e.ts) {
    const t = new Date(e.ts.endsWith("Z") ? e.ts : e.ts + "Z");
    if (!isNaN(t)) stamp = tzTime(t);
  }
  const tiles = `
    <div class="stat-cards ev-tiles">
      ${statCardHTML("target", "Trust the model?", escapeHtml(trust[0]),
                     escapeHtml(trust[1]),
                     e.verdict === "edge_predicts" ? "pos" : "neg")}
      ${statCardHTML("shield", "Data quality",
                     missing == null ? "—" : missing ? "Partial" : "High",
                     missing == null
                       ? "Awaiting the next measured run"
                       : missing
                       ? `${plural(missing, "settled pick")} ${missing === 1 ? "has" : "have"} no stored probability`
                       : "No missing model features",
                     missing ? "" : missing == null ? "" : "pos")}
      ${statCardHTML("chart", "Sample size", e.n == null ? "—" : e.n,
                     "Settled bets analysed")}
      ${statCardHTML("calendar", "Last measured", escapeHtml(stamp), stampSub)}
    </div>`;

  return `
  <div class="rec-edge tone-${v.tone}">
    <span class="ev-mark" aria-hidden="true">${icon("scale", 96)}</span>
    <div class="section-title">Is there an edge at all?
      <span class="sub">— ${e.n} settled bets</span></div>
    <div class="rec-edge-verdict"><strong>${escapeHtml(v.label)}.</strong>
      ${escapeHtml(v.say)}</div>
    <div class="ev-scroll"><table class="agate rec-edge-tbl"><thead><tr>
      <th>ranked by</th><th class="num">AUC</th><th class="num">95% CI</th>
    </tr></thead><tbody>
      ${row("the model’s own number", e.auc_model, e.auc_model_lo, e.auc_model_hi)}
      ${row("the market’s price", e.auc_market, e.auc_market_lo, e.auc_market_hi)}
      ${row("our claimed edge", e.auc_edge, e.auc_edge_lo, e.auc_edge_hi, true)}
      ${row("model minus market", e.diff, e.diff_lo, e.diff_hi)}
    </tbody></table></div>
    ${/* Each paragraph gets the mark of what it is about — the render's
         three gold discs. They are labels, not decoration: this panel is
         three separate instruments stacked, and unbroken prose made them
         read as one long caveat. */""}
    <div class="ev-notes">
      <div class="ev-note"><span class="ev-ico">${icon("target", 15)}</span>
        <p><strong>0.500 is a coin flip</strong> — the chance a random
        winner is ranked above a random loser. Rank-based, so the vig
        cannot distort it. ${escapeHtml(v.then)}</p></div>
      ${e.clv_n ? `<div class="ev-note"><span class="ev-ico">${icon("chart", 15)}</span>
        <p><strong>Closing-line value</strong> over ${e.clv_n} bets with a
        close: ${(e.clv_mean * 100).toFixed(2)}% ± ${((e.clv_se || 0) * 100).toFixed(2)}
        — a second, independent instrument.</p></div>` : ""}
      ${spark ? `<div class="ev-note"><span class="ev-ico">${icon("rising", 15)}</span>
        ${spark}</div>` : ""}
    </div>
    ${tiles}
  </div>`;
}

/* THE PICK OF THE DAY'S OWN SPOT ON THE RECORD PAGE.

   Ethan, 2026-09-15: "We will record the 'Pick of the day' record on the
   record page correlated too the sport, and it will have its own spot on
   the record page so we can see how it's doing."

   ITS OWN SECTION RATHER THAN A ROW IN THE BOOK TABLE, and above the
   others, because it is the claim the top of every board makes. A
   showcase pick whose record is three scrolls below it, mixed into a
   table, is a claim nobody checks.

   ONE ROW A DAY PER SPORT AT A FLAT UNIT, so W-L and units both read as
   a record rather than as a rate over a sample of unknown size. The
   count is stated anyway: a 3-1 is not evidence of anything and the
   section says so until it has enough to be.

   Scoped renders that sport's own cut (`potd_by_sport`); "All bets"
   renders the pooled one. A league with nothing in this book yet is an
   absent entry and draws nothing, the same rule the paper book follows. */
const POTD_MIN_N = 20;

function zenoTallyLine(t) {
  if (!t || (!t.settled && !t.open)) return "";
  const n = t.settled || 0;
  const roi = t.roi == null ? null : t.roi * 100;
  return n
    ? `<b style="font-size:var(--fs-lg)">${t.wins}-${t.losses}${
        t.pushes ? `-${t.pushes}` : ""}</b>
       <span style="color:${t.profit >= 0 ? "var(--good)" : "var(--bad)"};font-weight:700">
         ${t.profit >= 0 ? "+" : ""}${zenoMoney(t.profit)}</span>
       ${roi == null ? "" : `<span style="color:${roi >= 0 ? "var(--good)" : "var(--bad)"}">
         ${roi >= 0 ? "+" : ""}${roi.toFixed(1)}% ROI</span>`}
       ${t.net_units == null ? "" : `<span style="color:${t.net_units >= 0 ? "var(--good)" : "var(--bad)"}">
         ${t.net_units >= 0 ? "+" : MINUS}${Math.abs(Number(t.net_units)).toFixed(1)}u</span>`}
       <span style="color:var(--text-mute)">· ${zenoMoney(t.staked)} risked
       · ${n} settled${t.open ? `, ${t.open} riding` : ""}</span>`
    : `<span style="color:var(--text-mute)">Nothing settled yet${
        t.open ? ` — ${plural(t.open, "ticket")} riding` : ""}.</span>`;
}

function recZenoSection(z, scope, tix) {
  if (!z || !z.overall) return "";
  /* A BROKEN STORE IS NOT A QUIET DAY. `block_or_empty` never fails the
     export, but an empty block that came from a failure carries `error`,
     and drawing nothing for it would make the two indistinguishable on
     the one page whose job is being checkable. */
  if (z.error) return `
    <div class="section-title"><span class="st-ico">${icon("star", 15)}</span>Zeno’s Record</div>
    <div class="card"><p class="list-note">${icon("warn")} Zeno’s record could not be read at the
      last build (${escapeHtml(String(z.error))}). The tickets are safe; the page will fill on
      the next build.</p></div>`;
  const t = scope ? (z.by_sport || {})[scope] : z.overall;
  if (!t || (!t.settled && !t.open)) return "";
  const locked = !tix || tix.locked;
  const rows = locked ? [] : (tix.recent || []).filter((r) => !scope || r.sport === scope).slice(0, 10);
  const books = Object.values(z.by_book || {}).filter((b) => b.settled);
  return `
    <div class="section-title"><span class="st-ico">${icon("star", 15)}</span>Zeno’s Record
      <span class="sub">— Zeno’s own tickets at FanDuel, DraftKings and theScore Bet, settled by
        the book, not by our model. ${scope ? escapeHtml((SPORT_META[scope] || {}).name || scope.toUpperCase()) : "All sports"}
        · <a href="#zeno" data-view="zeno">what’s riding now →</a></span></div>
    <div class="card" style="border-left:3px solid var(--brand)">
      <div>${zenoTallyLine(t)}</div>
      <div class="pk-row">${pikkitBadgeHTML()}</div>
      ${!scope && books.length > 1 ? `<div style="margin-top:6px;font-size:var(--fs-sm);color:var(--text-mute)">
        ${books.map((b) => `${escapeHtml(b.name)} ${b.wins}-${b.losses}${b.pushes ? "-" + b.pushes : ""} ${
          b.profit >= 0 ? "+" : ""}${zenoMoney(b.profit)}`).join(" · ")}</div>` : ""}
      ${rows.length ? `<div class="hd-card">${rows.map((r) => zenoTicketRow(r, true)).join("")}</div>`
        : locked && (t.settled || t.open) ? zenoLockedHTML(z) : ""}
      <p style="margin:8px 0 0;font-size:var(--fs-xs);color:var(--text-mute)">
        Real money at real books. Every result here is the sportsbook’s own settlement — nothing is
        re-graded or re-priced by this site — and every ticket is the full ticket: a parlay counts once,
        win or lose. Pushes and voids are refunded and stay out of the ROI.</p>
    </div>`;
}

/* EVERY HEADLINE THE TOP PICK CARRIED (audit A1-5): the log is written
   every cycle and was never published, so a reader who saw a different
   pick at 9 a.m. had nothing to check it against. Last 14 days, newest
   first; a day the headline changed says how many times. */
function recPotdClaims(days, scope) {
  const rows = (days || []).map((d) => ({
    date: d.date, claims: (d.claims || []).filter((c) => !scope || c.sport === scope),
  })).filter((d) => d.claims.length);
  if (!rows.length) return "";
  const what = (c) => c.player
    ? `${escapeHtml(c.player)} ${escapeHtml(String(c.side || ""))} ${c.line != null ? escapeHtml(String(c.line)) : ""} ${escapeHtml(String(c.market || ""))}`
    : "no top pick";
  return `<details class="card rec-claims" style="margin-top:8px">
    <summary>Every headline pick, as it was shown — last ${rows.length} day${rows.length === 1 ? "" : "s"}</summary>
    ${rows.map((d) => {
      const last = d.claims[d.claims.length - 1];
      const moved = d.claims.length > 1 ? ` · changed ${d.claims.length - 1}× that day, first ${what(d.claims[0])}` : "";
      return `<div class="rec-row flush tight"><span style="width:64px;flex-shrink:0;color:var(--text-mute)">${escapeHtml(String(d.date).slice(5))}</span>
        <span style="flex:1;min-width:0">${what(last)}<span style="color:var(--text-mute)">${moved}</span></span></div>`;
    }).join("")}
  </details>`;
}

function recPotdSection(rep, scope, recent) {
  /* EVERY LEAGUE THAT NAMES ONE GETS ITS SECTION, an empty one included
     (Ethan, 2026-10-14: "we only show the pick of the day record for nfl
     and mlb but no other sport"). The record carries an entry for each
     such league (`ledger.POTD_LEAGUES`), so an empty book says "Nothing
     settled yet" under the same heading rather than the heading going
     missing — which read as no such book. A league with no entry (the
     WNBA, on the bench) draws nothing; pooled, nothing still draws
     nothing. The fight card names one since 2026-10-14. */
  if (!rep || (!scope && !rep.settled && !rep.open)) return "";
  const where = scope ? ((SPORT_META[scope] || {}).name || scope.toUpperCase()) : "All sports";
  const n = rep.settled || 0;
  const units = Number(rep.net_units || 0);
  const rows = (recent || []).filter((r) => !scope || r.sport === scope).slice(0, 10);
  const line = n
    ? `<b style="font-size:var(--fs-lg)">${rep.wins}-${rep.losses}${
        rep.pushes ? `-${rep.pushes}` : ""}</b>
       <span style="color:${units >= 0 ? "var(--good)" : "var(--bad)"};font-weight:700">
         ${units >= 0 ? "+" : MINUS}${Math.abs(units).toFixed(2)}u</span>
       <span style="color:var(--text-mute)">· ${Math.round((rep.win_rate || 0) * 100)}% hit rate
       · ${n} settled${rep.open ? `, ${rep.open} riding` : ""}</span>`
    : `<span style="color:var(--text-mute)">Nothing settled yet${
        rep.open ? ` — ${plural(rep.open, "pick")} riding` : ""}.</span>`;
  return `
    <div class="section-title"><span class="st-ico">${icon("target", 15)}</span>Pick of the Day
      <span class="sub">— one pick per sport per day, priced near even money, flat staked.
        ${escapeHtml(where)}</span></div>
    <div class="card" style="border-left:3px solid var(--brand)">
      <div>${line}</div>
      ${n && n < POTD_MIN_N ? `<div style="margin-top:5px;font-size:var(--fs-sm);color:var(--text-mute)">
        ${plural(n, "settled pick")} is too few to judge a hit rate on. This line is the
        record so far, not a claim about what it will do — it needs about ${POTD_MIN_N}
        before the number means much.</div>` : ""}
      ${rows.length ? `<div style="margin-top:8px">
        ${rows.map((r) => `<div class="rec-row flush tight">
          <span style="width:64px;flex-shrink:0;color:var(--text-mute)">${escapeHtml(String(r.date || "").slice(5))}</span>
          <span style="flex:1;min-width:0">${escapeHtml(r.player || "")}
            <span style="color:var(--text-mute)">${escapeHtml(String(r.market || ""))}
              ${r.line != null ? escapeHtml(String(r.line)) : ""} · ${american(r.odds)}</span></span>
          <span style="font-weight:700;color:${
            r.status === "won" ? "var(--good)" : r.status === "lost" ? "var(--bad)" : "var(--text-mute)"}">
            ${escapeHtml(String(r.status || "").toUpperCase())}</span>
        </div>`).join("")}</div>` : ""}
      <p style="margin:8px 0 0;font-size:var(--fs-xs);color:var(--text-mute)">
        Flat one unit, no dollar exposure — this book is a published claim being scored,
        kept apart from the edge board’s money. A day when nothing clears the bar shows the
        best available on the board and records nothing, so every row here qualified.</p>
    </div>`;
}

/* THE WEEK IN ONE CARD (engine/recap; Ethan, 2026-10-04: "do all of it").
   Each published book's last seven days: the record, the units, the hit
   rate against our claim and the price, the best hit and the toughest miss. */
function weekRecapHTML(w) {
  const books = ((w || {}).books || []).filter((b) => b.w + b.l + b.p);
  if (!books.length) return "";
  const pc = (v) => v == null ? "—" : `${Math.round(v * 100)}%`;
  const bet = (x) => `${escapeHtml(x.player || "")} ${escapeHtml(String(x.side || "").toLowerCase())} ${x.line ?? ""} ${
    escapeHtml(String(x.market || "").replace(/_/g, " "))} (${american(x.odds)})`;
  return `<section class="card wk-recap" aria-label="This week">
    <div class="section-title">${icon("calendar", 15)} This week <span class="sub">— ${escapeHtml(recWinDate(w.from))} to ${escapeHtml(recWinDate(w.to))}</span></div>
    ${books.map((b) => `<div class="wk-book"><b>${escapeHtml(b.book)}</b>
      <span class="wk-line">${b.w}-${b.l}${b.p ? `-${b.p}` : ""} · <span class="${b.units >= 0 ? "pos" : "neg"}">${b.units >= 0 ? "+" : trueMinus("-")}${Math.abs(b.units).toFixed(1)}u</span>
        · hit ${pc(b.hit)} (we said ${pc(b.claimed)}, the price said ${pc(b.price)})</span>
      ${b.best ? `<span class="wk-pick">Best hit: ${bet(b.best)}</span>` : ""}
      ${b.worst ? `<span class="wk-pick">Toughest miss: ${bet(b.worst)} at ${pc(b.worst.claim)}</span>` : ""}</div>`).join("")}
  </section>`;
}
async function renderRecord() {
  /* His bets for the Zeno card below, members only (zenoTickets). */
  const _zenoTixRec = await zenoTickets();
  const host = document.getElementById("record-body");
  if (!host) return;
  let d = null, pmv = null;
  // FAILED is not EMPTY (audit V-2): a 404 is "no record file yet", and
  // anything else that is not a 2xx is an outage with its own card.
  const got = { failed: false };
  let kept = "";                    // the offline copy's moment, when that is what answered (sw.js)
  try {
    const res = await boardFetch("data/record.json", { cache: "no-cache" });
    if (res.ok) d = adoptPooledRecord(await res.json());
    if (res.ok) _lastGood.set("record", Date.now());
    else got.failed = res.status !== 404;
    kept = (res.headers && res.headers.get("X-QB-Offline-Copy")) || "";
  } catch (e) { got.failed = true; }
  /* THROUGH THE ENTITLED ENDPOINT FIRST. `predmarkets.json` is a wholly
     paid file — gate.PAID_FILES — so the copy Caddy serves off disk is a
     locked stub with no `validation` key at all once the paywall is on.
     This page read that stub and drew nothing, which is Ethan's "the
     prediction market record page isnt showing anything": the section
     was not broken, it was being handed an empty board and had nothing
     to say about it.

     /api/board/ is where a subscriber's copy lives. The static file
     stays as the fallback for a signed-out reader and for a static host,
     where it correctly yields nothing. */
  try {
    const res = await paidFetch("predmarkets.json");
    if (res.ok) pmv = ((await res.json()) || {}).validation;
  } catch (e) {}
  if (!d && got.failed) { host.innerHTML = outageHTML("the record", "record"); return; }
  if (!d || !d.overall || (!d.overall.settled && !d.overall.open)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">No graded picks yet</div>
      <div class="es-sub">Every recommended pick is journaled automatically at its real
      price and grades itself once results are ingested (nightly, automatic).
      Check back after tonight’s games settle — this page becomes the honest
      scoreboard for everything the model recommends.</div></div>`;
    return;
  }
  // The engine's own word for each market id, for the splits table. Set
  // before anything renders so a payload without the key falls back to
  // prettifying rather than to a stale map from a previous render.
  _marketWords = d.market_words || {};
  // The ledger's own bar for "enough graded bets to mean anything",
  // shipped per sport as `min_graded`; the same constant on every
  // sport's report, so any one of them says what it is.
  _recMinGraded = (Object.values(d.by_sport || {})[0] || {}).min_graded || 30;
  // Default to the sport whose board you came from; "all" is a click away.
  const tracked = d.tracked_sports || [];
  let scope = _recordScope
    || (tracked.includes(state.sport) ? state.sport : "all");
  if (scope !== "all" && scope !== "intel" && !(d.by_sport || {})[scope])
    scope = "all";
  const scoped = (scope === "all") ? null
    : (scope === "intel" ? {overall: {}, curve: [], recent: [],
                            calibration: null, calibration_era: null}
                         : d.by_sport[scope]);
  // With no signal the page reads the copy kept the last time it loaded
  // (sw.js THE RECORD, OFFLINE), and says from when.
  const scopeBar = (kept ? `<div class="rec-offline" role="status">${icon("warn", 14)}
      <span><b>Offline.</b> The record as of ${escapeHtml(tzTime(Date.parse(kept), { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) || kept)} — the
      last time it loaded on this phone. It updates when you are back online.</span></div>` : "")
    + recordScopeHTML(d, scope);

  // Everything below reads ONE object. Scoping by swapping the source
  // rather than by filtering at each call site means a panel cannot
  // quietly keep showing the combined number next to a per-sport one.
  const src = scoped || d;
  const o = src.overall;
  _recCalScope = scope;                       // the day panel fetches in this scope
  if (scope === "intel") {
    host.innerHTML = scopeBar + (pmv
      ? recPolymarketSection(pmv)
      : `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
         <div class="es-title">No Polymarket flags graded yet</div>
         <div class="es-sub">Flags are recorded as the trade tape is read and
         grade when their markets resolve. This is a report card on the
         detector, not a betting P&L — nothing here is staked.</div></div>`);
    bindRecordScopes(host);
    return;
  }
  if (scoped && !recordHasSomething(o, (d.book_records || {})[scope],
                                    recordOwnBook(d, scope),
                                    (d.shadow_books || {})[scope])) {
    // THE EMPTY STATE, AND ONLY WHAT HAS SOMETHING TO SAY ABOUT THIS
    // SPORT. This used to append the whole learning ladder under the
    // slate, on the argument that an empty journal is not an empty
    // model. Rendered for the NBA on 2026-09-06 it read: "Nothing
    // journaled for NBA yet", "Nothing tuned for NBA yet", a mining
    // panel counting "461 graded bets, all sports", preregistered tests
    // about NFL props, and a lab of four zeros — five panels saying
    // nothing, one of them about another league. Ethan: "everything
    // seems cluttered." The restated view and the night desk stay: both
    // draw nothing for a sport they have nothing on, and the desk can
    // have a brief for a sport before its first pick settles (the NFL,
    // every August). The ladder still renders in full for every sport
    // with a journal, and on "All bets".
    host.innerHTML = scopeBar + `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">Nothing journaled for ${escapeHtml(
        (SPORT_META[scope] || {}).name || scope.toUpperCase())} yet</div>
      <div class="es-sub">This board has not recommended a bet that reached a
      result. It fills itself in — every pick is journaled at its real price
      the moment it is made, and grades when the games settle. The whole
      journal’s learning is under <b>All bets</b>.</div></div>`
      + recRestatedSection(d.restated, scope)
      + recProseSection(d.prose, scope);
    bindRecordScopes(host);
    return;
  }
  const unstaked = o.unstaked
    ? `<p class="list-note" style="margin-top:10px">${iconMark("dash")}${plural(o.unstaked, "older settled pick")}
       ${o.unstaked === 1 ? "is" : "are"} held out of this record: a grading bug sized them at 0.00 units, so they
       were never really bets. They stay out rather than being quietly restaked at a
       size nobody chose.</p>` : "";
  // Under the ledger's own bar the verdict already says "too early to
  // call"; this note said it a second time, and said it about "0 settled
  // pick(s) for nfl". It speaks only in the band the verdict does not.
  const small = o.settled >= (src.min_graded || _recMinGraded) && o.settled < 100
    ? `<p class="list-note" style="margin-top:10px">${icon('warn')} ${o.settled} settled picks${
       scoped ? ` for ${escapeHtml((SPORT_META[scope] || {}).name || scope.toUpperCase())}` : ""} —
       results this small are mostly luck. Judge the model after 100+, and judge
       the process by CLV before that.</p>` : "";
  const pr = o.process || {};
  const nProc = (pr.good || 0) + (pr.bad || 0) + (pr.flat || 0);
  /* IS THERE AN EDGE AT ALL — the working, so it goes LAST.

     It led the page from 2026-08-09, on the argument that it is the frame
     the ROI should be read through rather than a footnote to it. That
     argument was right about the panel's importance and wrong about a
     reader's first ten seconds: it is four rows of AUCs with confidence
     intervals, three paragraphs of statistics and a sixty-run trend, and
     it stood between the visitor and the record they came for. Ethan,
     2026-08-23: "can you move this to the bottom of the page." Same
     panel, same words, at the end of the same room — the numbers it
     explains are now above it, which is also the order the explanation
     reads in.

     Scoped panels get nothing: the measurement is computed over the whole
     main book, and slicing it per sport would print a number that was
     never calculated. See docs/THE_INFORMATION_TEST.md. */
  const edgePanel = (scoped || !d.edge_now) ? "" : recEdgePanel(d.edge_now, d.edge_trend, (d.edge || d).overall);
  /* THE VERDICT LEADS. Everything below it is the working; this is the
     answer, and a first-time reader should not have to assemble it from
     six panels. Scoped correctly by construction — `src` is already the
     scoped object, so a per-sport verdict cannot quietly print the
     combined number. */
  // SAID ONCE (2026-10-25, the live NFL record): the ribbon at the top
  // carries the combined total whenever it is not cut to a window with
  // rows in it (the same test the ribbon makes below, `winO`), and the
  // Most Likely section in this same room prints that book's verdict
  // sentence whenever it is drawn at all (recLikelySection). Either one
  // absent, the verdict keeps its copy.
  const lkHere = scoped ? (d.likely_by_sport || {})[scope] : d.likely;
  const winAvail = recRangesFor(src.curve), winFrom = recRangeFrom(winAvail, recRangeKey(winAvail));
  const verdict = recordVerdictHTML(src, scope === "all"
    ? "all sports" : ((SPORT_META[scope] || {}).name || scope.toUpperCase()),
    lkHere, { combinedShown: !(winFrom && recRangeTotals(src.curve, winFrom)),
              likelySaid: !!(lkHere && (lkHere.settled || lkHere.open)) });
  // The page's lead — what happened, in units. Built as a string so it can
  // be handed to the first room rather than rendered above the tab bar,
  // which would leave the tabs floating in the middle of the page.
  /* ONE SPINE, CALENDAR FIRST. Ethan, 2026-09-08: "re organize all the
     record pages for every sport as everything's is just scattered around
     and unorganized. Maybe we put the profit calendars at the top of the
     pages." This room ran verdict, book sections, the process row with
     its long disclosure, two notes, the curve, the calendar, the splits,
     the settled rows, the edge panel — and on "All bets" the Most Likely
     record led and the pooled book sections trailed after everything, so
     the two scopes read in different orders. The same order on every
     scope now, top to bottom the way a reader asks: what happened by day
     (the calendar), what it adds up to (the verdict and its two caveats),
     by book, the curve, the splits, the settled picks, then how it is
     measured (the process grade, the era, what counts as a tracked bet)
     and last the working (is there an edge at all). The book sections
     still lead a sport's numbers (09-01, 09-05) — they sit under the
     verdict on every scope, pooled on "All bets". */
  const likelyCal = (d.likely_calendar || {})[scope];
  const calendar = recCalendarsHTML(src, likelyCal);
  /* Open / Settled, the way every book's My Bets splits it (research in
     docs/VISUAL_REDESIGN.md). This page is the settled half; the open
     half lives on the Live tab with its progress, and the count here is
     the same journal's, so the two never disagree. */
  const ridingNote = o.open
    ? `<p class="list-note rec-riding">${iconMark("dot", 10)}${plural(o.open, "bet")} riding right now —
       ${o.open === 1 ? "it is" : "they are"} on the <a href="#live" data-view="live">Live tab</a> with
       ${o.open === 1 ? "its" : "their"} progress, and ${o.open === 1 ? "lands" : "land"} here once settled.</p>` : "";
  /* THE PAPER BOOK, ON EVERY SCOPE. This read `scoped ? "" : ...`, so
     the entire Most Likely record vanished the moment a reader pressed a
     league — Ethan, 2026-09-10: "the most likley paper bets for nfl are
     not showing on nfl. and the most likley paper bets for mlb ar enot
     showing on lb and so forth." The section was omitted rather than
     scoped because `ledger.likely_report` had no per-sport cut to hand
     it; it does now, and the page renders that sport's own report.
     An absent entry (a league with nothing in this book yet) renders
     nothing, exactly as before. */
  /* UNDER THE FLOOR, THE PAGE COLLAPSES (audit V-22). At one settled bet
     the room drew fourteen panels — 3,700 px to say "1-0, too early".
     Below `min_graded` it shows the calendar, the verdict (which already
     says too early), this month's card and the settled bets, and folds
     everything else under one line that says why it is folded. */
  const recNeed = src.min_graded || _recMinGraded;
  const underFloor = (o.settled || 0) < recNeed;
  const scopeName = scope === "all" ? "all sports" : ((SPORT_META[scope] || {}).name || scope.toUpperCase());
  const foldOpen = (what) => !underFloor ? "" : `<details class="rec-fold"><summary>${what} — too early
      to read (${o.settled || 0} of the ${recNeed} settled bets the record needs)</summary>`;
  const foldClose = underFloor ? "</details>" : "";
  const monthCard = underFloor ? recMonthCard(src, scopeName) : "";
  const receipts = calendar
    /* ZENO'S RECORD — a person's real tickets, beside the model's picks
       and never inside them. Its own store, its own block, its own card:
       two provenances that shared a number would make both worthless.
       Scoped to a league when that league has rows; pooled on "All". */
    + foldOpen("Most Likely, Pick of the Day and Zeno")
    + recZenoSection(d.zeno, scope, _zenoTixRec)
    + recPotdClaims(d.potd_claims, scoped ? scope : "")
    + recPotdSection(scoped ? (d.potd_by_sport || {})[scope] : d.potd,
                     scope, d.potd_recent || [])
    + recBoardSection(scoped ? (d.board_by_sport || {})[scope] : d.board, scope)
    + recLikelySection(scoped ? (d.likely_by_sport || {})[scope] : d.likely,
                       scope)
    + foldClose
    + verdict + ridingNote + unstaked + small + monthCard
    + foldOpen("By book, the running P&amp;L and the splits")
    + recBookSections(d.book_records, scope) + `
    ${recAnalytics(src.curve, o, ((d.model_eras || {}).eras) || [])}
    ${recSplitsSection(o, !!scoped)}
    ${foldClose}
    ${recRecentSection(src.recent || [], o.settled)}
    ${foldOpen("The method behind the record, and the edge test")}
    <div class="section-title"><span class="st-ico">${icon("scale", 15)}</span>How this is measured
      <span class="sub">— the decisions behind the record, the model era, and
      what counts as a tracked bet</span></div>
    ${/* PROCESS ON ITS OWN ROW, per Ethan's render (2026-08-24). It was
         the sixth tile in the strip and it is not the same KIND of
         number as the other five: those are the record, this grades the
         DECISIONS behind it, and it needs three lines to say so where
         they need one. On its own row it can carry the count and both
         causes as bullets, and the two things a reader reaches for next
         — what the record leaves out, and what counts as a tracked bet —
         sit beside it instead of below the fold. */""}
    <div class="rec-process-row">
      ${statCardHTML("scale", "Process",
          nProc ? `${pr.good || 0}<i>W</i> ${pr.bad || 0}<i>L</i>` : "—",
          nProc ? `${nProc} of ${o.settled} priced at close`
                : "needs closing lines — none captured yet",
          "",
          { cardCls: "rec-process",
            help: "Grades the DECISION, not the result: a win that closed "
                + "worse than we bet it got lucky; a loss that beat the "
                + "close was still a good bet. Only counts picks where we "
                + "captured the closing line.",
            extra: nProc ? `<ul class="rp-bullets">
              <li class="good">${plural(pr.lucky_wins || 0, "lucky win")}</li>
              <li class="bad">${pr.unlucky_losses || 0} good-bet ${pluralWord(pr.unlucky_losses || 0, "loss", "losses")}</li>
            </ul>` : "" })}
      <div class="rec-process-side">
        ${recEpochHTML(d, src)}
        ${recDisclosure("What counts as a tracked bet", `Journals every
      <strong>Recommended</strong> bet — the new picks the "On tonight"
      tile counts on each sport’s board (its riding bets were journaled
      the day they were placed): player props plus game bets (moneyline,
      spread &amp; totals, sharp-anchor and model alike) — at the real book price
      shown when it was recommended. One entry per player &amp; market per day.
      Long Shots and stale-line flags are tracked in their own buckets at a flat
      0.1u — never mixed into this record — and the Edge Board is a watchlist,
      not tracked bets.${/* THE PAPER BOOK, disclosed here rather than in a
        panel of its own. It used to open the Receipts tab as a two-row
        split with standard errors and a hundred-row list beneath it, which
        Ethan removed for the space — but the FACT it carried has to
        survive, because these rows are inside the headline ROI and a
        reader has no other way to learn that. A collapsed disclosure costs
        nothing until it is opened, and this is the question a reader opens
        it to ask. Drawn only when the book has rows, so it never describes
        something that never happened. */
        !((d.paper || {}).settled) ? "" : ` <strong>Paper rows are in these
        numbers.</strong> ${d.paper.settled} of the settled bets here were
        journalled while paper mode was on — same pick, same price, same
        settlement, no money on them — and they are already added into
        every figure above. Unit ROI pools honestly because the stakes were
        kept as sized; dollars stay real-money-only, and no paper row has
        ever moved the bankroll.`}`)}
      </div>
    </div>
    ${edgePanel}
    ${foldClose}
  `;
  /* THE PAGE LEADS WITH THE RIBBONS (v5): the scope in view as a ring,
     a W-L and a headline number with its last five, and Zeno's book
     beside it — the account header every tracker opens with. Above the
     rooms, so every room reads under the same number; the receipts
     room still begins with the calendar (test_record_spine). */
  /* THE WINDOW (audit item 5): the headline reads the page's range —
     Lifetime, or the last 90 / 30 / 7 days of the scope in view —
     cut from that scope's own curve. The running P&L follows the
     same state; every other room stays the whole record, and the
     note under the ribbon says so. A window with nothing settled
     keeps the whole record on the ribbon and says that instead. */
  const avail = recRangesFor(src.curve);
  const rk = recRangeKey(avail);
  const from = recRangeFrom(avail, rk);
  const winDays = (avail.find(([k]) => k === rk) || [])[1];
  const winO = from ? recRangeTotals(src.curve, from) : null;
  /* The combined line is the WHOLE record's (engine/zeno.combined): it
     shows only on the whole, unscoped record, never beside a sport, a
     book or a window it was not added up over. ZENO'S TILE TOO: his is
     one all-sports count carried in from Pikkit, and on the NFL page it
     sat beside the NFL's own numbers as if it were one of them (Ethan,
     2026-10-02: "all these numbers are not adding up"). His league cut
     is in his own section below. */
  const dAll = winO || scoped
    ? { ...d, combined: null, zeno: null,
        pooled_overall: winO ? null : src.pooled_overall,
        likely_overall: winO ? null : src.likely_overall } : d;
  const ribbons = winO
    ? recordRibbonsHTML(dAll, { ...winO, label: `Edge picks · last ${winDays} days` },
        (src.recent || []).filter((r) => String((r || {}).date || "") >= from), { parts: true })
    : recordRibbonsHTML(dAll, o, src.recent, { parts: true });
  const winBar = recordWindowHTML(avail, rk, recRangesClosed(src.curve));
  const winNote = !from ? "" : winO
    ? `<p class="rec-win-note">The headline, the running P&amp;L and the settled bets are the last ${winDays} days,
        from ${escapeHtml(recWinDate(from))}. Everything else here is the whole record.</p>`
    : `<p class="rec-win-note">Nothing settled in the last ${winDays} days — the
        headline is the whole record.</p>`;
  host.innerHTML = scopeBar + winBar
    + (ribbons ? `<div class="hd-stats rec-ribbons">${ribbons}</div>${zenoWhoHTML(dAll)}` : "")
    + weekRecapHTML(d.weekly_recap)
    + winNote
    + _recordRooms(d, src, pmv, scope, scoped, receipts)
    + `<p class="rec-stamp">Updated ${escapeHtml(formatStamp(d.generated_at))}
      · settles automatically as results are ingested each day.</p>`;
  bindRecordScopes(host);
  bindSubtabs(host);
  /* The calibration chart in a room that opens already showing. This
     mount sat after `_recordRooms`'s return, where it never ran (the site
     audit, 2026-09-24); a hidden room is still upgraded on its tab tap. */
  if (typeof mountEChartsAnalytics === "function") mountEChartsAnalytics(host);
  sweepRings(host);
  recBetsMount(host, src.recent || [], o.settled, scope, from);
  // The calendar's days are doors to their bets; a day left open on the
  // last render (a range chip, a month arrow) is reopened.
  // The Most Likely calendar's taps ask for its own book; the rows this
  // page holds (`src.recent`) are the edge picks, so it has no fallback.
  const onLikely = _recCalBook === "likely" && !!(likelyCal && Array.isArray(likelyCal.days));
  const calCurve = onLikely ? likelyCal.days : src.curve;
  const calRecent = onLikely ? [] : src.recent || [];
  const calBook = onLikely ? "likely" : "edge";
  host.querySelectorAll(".rc-day[data-date]").forEach((el) =>
    el.addEventListener("click", () => recCalDayOpen(el.dataset.date, calCurve, calRecent, calBook)));
  if (_recCalDay && host.querySelector(`.rc-day[data-date="${_recCalDay}"]`))
    recCalDayOpen(_recCalDay, calCurve, calRecent, calBook);
}

/* The five rooms of the Record page.
   ------------------------------------------------------------------
   Twenty-two sections used to stack here in one scroll. They were never
   twenty-two subjects — they are five, and the grouping below is the one
   already implied by what each panel answers:

     Receipts       what happened, in units
     By product     the buckets kept OUT of the main P&L on purpose
     Calibration    did the probabilities mean what they said
     What it learned the four-rung ladder, showing its work
     Health         how limit-prone our picks look, book by book

   Which panels exist depends on scope, and that is why the groups are
   built as strings and handed to `subtabbedHTML` rather than declared as
   a fixed bar: scoped to one sport, most of "By product" is empty, and a
   tab that opens an empty room is worse than no tab at all. */
function _recordRooms(d, src, pmv, scope, scoped, receipts) {
  // Whole-journal panels are written as inline `scoped ? "" : X` rather
  // than through a helper. A helper reads better and hides the guard from
  // the tests that exist to prove it: six of them scan for `scoped` beside
  // each call, because "a per-book limit risk shown under one sport's
  // name" is a wrong number, not a layout slip. Legibility to the test is
  // worth more here than tidiness.
  // The learning ladder renders on EVERY scope, filtered to the sport in
  // view — each league fits on its own bets. Hiding these behind "All" is
  // how the whole ladder once shipped invisible: this page always lands
  // sport-scoped. Spelled out at each call for the same reason the scope
  // guards above are: a test proves this and can only read what is written.
  return subtabbedHTML("record", [
    ["receipts", "Receipts",
     "what happened, in units — the calendar, the verdict, every settled pick",
     // The paper/money split used to open this tab. Ethan, 2026-08-20:
     // "remove the paper bet section on the record page. its taking up to
     // much space and we dont really need that area any more."
     //
     // Nothing leaves the record by removing it. `overall` has always been
     // `performance(conn)`, whose category default is ("main", "paper") —
     // the two books were ALREADY pooled into every headline number above,
     // and the panel only re-split what the curve had added together. It
     // also mislabelled its own second line "Money rows" while passing
     // that pooled book, so the comparison it drew was paper against
     // paper-plus-money. If the split is ever wanted back, build it from
     // `performance(conn, category="main")`.
     // THE LIKELY RECORD LEADS. Ethan, 2026-08-31: "maybe use those
     // picks instead on our record page instead of showing off the
     // props that lose more." The main journal's cold streak was the
     // first thing every visitor read, while the board the model is
     // best at — and the record that decides whether money ever rides
     // on it — sat two tabs deep. It moves here, above the curve; the
     // honest under-100-settles refusal explains itself while the
     // sample builds. Since 2026-09-08 it rides inside `receipts`,
     // under the calendar and above the verdict, on the "all" scope.
     // ONE STRING, built in renderRecord in the order the reader asks
     // (2026-09-08): the calendar, the Most Likely record on "All bets",
     // the verdict, the books, the curve, the splits, the settled picks,
     // how it is measured, and last the working. Nothing is prefixed or
     // appended here, so the two scopes cannot drift into two orders.
     receipts],
    ["products", "By product",
     "the buckets deliberately kept out of the main P&L",
     (scoped ? "" : recLongshotSection(d.longshots)) + (scoped ? "" : recParlaySection(d.parlays))
     + (scoped ? "" : recStaleSection(d.stale_flags)) + (scoped ? "" : recFormSection(d.form_sampler))
     + (scoped ? "" : recLooseSection(d.loose_sampler))
     + (scoped && scope !== "ufc" ? "" : recUfcSection(d.ufc_record))
     // BOTH SCOPES, different book lists. A sport gets all five; "All
     // bets" gets only the two with no dedicated panel above it, so one
     // book never prints two W-Ls on one screen.
     + recShadowBooks(d.shadow_books, scope)
     + recStaleLadder(d.stale_verdicts, scope)
     // Polymarket's flags are not wagers in this ledger — they are graded
     // by their own report card. Folding a flag rate into a betting P&L
     // would make both numbers mean nothing.
     + (scoped && scope !== "intel" ? "" : recPolymarketSection(pmv))],
    ["calibration", "Calibration",
     "did “60%” actually mean 60%?",
     (scoped ? "" : recLeadtimeSection(d.clv_leadtime))
     + (scoped ? "" : recEraSection(d.model_eras))
     + recCalibrationSection(src.calibration, src.calibration_era)
     + recReplaySection(d.replay, scoped ? scope : null)
     + recSelectionHaircut(d.selection_haircut, scoped ? scope : null)
     + (scoped ? "" : recCalibrationSplits(d.calibration_splits))
     + (scoped ? "" : recForecastLog(d.forecast_log))
     + (scoped ? "" : recRegrades(d.regrades, d.audit_log, d.forecast_heads))],
    ["learning", "What it learned",
     "the four-rung ladder, showing its work",
     recRestatedSection(d.restated, scoped ? scope : null) + recProseSection(d.prose, scoped ? scope : null)
     + recSelfTuningSection(d.self_tuning, scoped ? scope : null)
     + recBoardLearningSection(d.board_learning, scoped ? scope : null)
     + recLossPatternsSection(d.loss_patterns, scoped ? scope : null)
     + recPrereg(d.prereg)
     + recHypothesisLab(d.hypothesis_lab, scoped ? scope : null)],
    ["market", "Model vs market",
     "does the line move our way after we bet it — by sport and market",
     recClvBoard(d.clv_board)],
    ["health", "Health",
     "how limit-prone our picks look, book by book",
     (scoped ? "" : recHealthSection(d.account_health))],
  ]);
}

/* MODEL VERSUS MARKET — does this thing beat the closing line?

   The most persuasive thing this site can show, and persuasive exactly
   because it can come out badly. A win-loss record over a few hundred
   bets is mostly variance wearing a percentage sign. Closing-line value
   grades the DECISION at kickoff, accrues on every settled pick rather
   than only the winners, and cannot be dressed up: either the market
   moved our way or it did not.

   THREE RULES THIS PANEL KEEPS, all of them about not flattering:

     * the SAMPLE SIZE sits beside every number, because +0.4 over nine
       bets and +0.4 over four hundred are different facts;
     * the VERDICT is gated below the ledger's own bar while the NUMBER
       is still shown — hiding a figure until it looks good is the
       failure this panel exists to refuse;
     * a market with settled picks and NO stored closes gets a row
       saying it cannot be graded, rather than quietly not appearing.
       That absence is exactly how the touchdown board hid a broken
       harvest for its entire existence (fixed 2026-08-26). */
function recClvBoard(cb) {
  const rows = (cb && cb.rows) || [];
  if (!rows.length) return "";
  const t = cb.totals || {};
  const pct = pct0Or;
  const clv = (v) => v == null ? "—"
    : `${v >= 0 ? "+" : trueMinus("-")}${Math.abs(v).toFixed(2)}`;
  const verdict = (r) => r.with_close === 0
    ? `<span class="mvm-clv" style="color:var(--text-mute);font-weight:400"
        >no closes yet</span>`
    : r.ready
      ? `<span class="mvm-clv" style="color:${(r.avg_clv || 0) > 0
          ? "var(--good)" : "var(--bad)"}">${clv(r.avg_clv)}</span>`
      : `<span class="mvm-clv" style="color:var(--text-mute)"
           title="Shown, not called — under ${cb.min_n} graded closes this
                  average is not yet evidence">${clv(r.avg_clv)} thin</span>`;
  const line = (r) => `<div class="mvm-row">
      <span class="mvm-name">${escapeHtml(String(r.sport || "").toUpperCase())}
        · ${escapeHtml(r.market_label || r.market || "")}</span>
      <span class="mvm-n">${r.with_close}/${r.settled}${
        r.with_close ? ` · ${pct(r.beat_rate)} beat` : ""}</span>
      ${verdict(r)}
    </div>`;
  return `<div class="section-title">Model versus market
      <span class="sub">— does the line move our way after we bet it? The
      earliest honest evidence there is, and the one number that can come
      out badly in public.</span></div>
    <div class="card">
      <p style="margin:0 0 10px;color:var(--text-dim);font-size:var(--fs-sm)">
        <b style="color:var(--text)">${t.with_close || 0} of ${
        t.settled || 0} settled picks</b> have a real closing line stored
        beside them${t.avg_clv == null ? "" : `, averaging
        <b style="color:${t.avg_clv > 0 ? "var(--good)" : "var(--bad)"}">${
        clv(t.avg_clv)}</b> points our way`}${t.ready
        ? "" : ` — under ${cb.min_n} graded closes, which is why nothing
          below is called a result yet`}.</p>
      <div class="mvm-rows">
        <div class="mvm-row mvm-head">
          <span class="mvm-name">Sport · market</span>
          <span class="mvm-n">closes/settled</span>
          <span class="mvm-clv">CLV</span>
        </div>
        ${rows.map(line).join("")}
      </div>
      <p style="margin:10px 0 0;color:var(--text-mute);font-size:var(--fs-sm)">
        CLV is measured in line points and is side-aware: an over wants the
        number to rise after we take it, an under wants it to fall, so
        positive always means the market came to us. A row reading
        &ldquo;no closes yet&rdquo; is a market we cannot grade — not a
        market that did badly.</p>
    </div>`;
}

/* One settled row, shared by every list that posts settled bets rather
   than copied into each — a second copy of this markup drifts from the
   first the next time either is touched, leaving two lists that disagree
   about what a "lucky" chip means. */
function recSettledRow(b) {
        const won = b.status === "won";
        const push = b.status === "push";
        const pnl = b.pnl_units || 0;
        // Process chip: judge the decision against the close, out loud.
        let procChip = `<span class="rl-proc none">no close</span>`;
        if (b.process === "bad" && won)
          procChip = `<span class="rl-proc warn" title="Won, but the market closed against us — a bad bet that got lucky">${iconMark("dot", 10)}lucky</span>`;
        else if (b.process === "good" && b.status === "lost")
          procChip = `<span class="rl-proc good" title="Lost, but we beat the closing line — good bet, bad night">${iconMark("rising", 11)}beat close</span>`;
        else if (b.clv != null && Math.abs(b.clv) < 0.05)
          // A close that did not move is the row's default state, not a
          // fact worth a chip: "+0.0 CLV" on two rows in three was the
          // noise Ethan was reading around (2026-09-06).
          procChip = "";
        else if (b.clv != null)
          procChip = `<span class="rl-proc ${b.clv >= 0 ? "good" : "bad"}"
            title="Closing-line value — how far the market moved our way after the bet">${b.clv >= 0 ? "+" : ""}${b.clv.toFixed(1)} CLV</span>`;
        // Cause chip: the settle pass's measured circumstance on a loss.
        // Only the exceptional ones get a chip — "variance" is the story
        // a lost row already tells by itself.
        const causeChip = (b.status === "lost" && b.cause && !/^variance/.test(b.cause))
          ? `<span class="rl-proc warn" title="Measured at settle from the ingested results — the circumstance, not an excuse">${escapeHtml(b.cause)}</span>`
          : "";
        // A moneyline has no line to print — "AWAY 0 Moneyline" was the
        // stored placeholder showing through.
        const lineTxt = (b.market === "moneyline" || b.line == null) ? "" : `${b.line} `;
        // ONE grid cell for both chips. As two siblings they were two grid
        // items: on a phone both took the `proc` area and drew on top of
        // each other; on the desktop's six-track grid the second one
        // wrapped onto a row of its own.
        return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
          <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
          <span class="rl-date">${escapeHtml(b.date || "")}</span>
          <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
            <span class="rl-bet">${escapeHtml(b.side || "")} ${lineTxt}${escapeHtml(marketWord(b.market))}${
              /* The terminal's columns (audit item 17): what the model
                 said, and what the price closed at, where known. */
              b.hit_prob != null ? ` · model ${(Number(b.hit_prob) * 100).toFixed(0)}%` : ""}${
              b.closing_odds != null ? ` · closed ${escapeHtml(oddsTxt(b.closing_odds))}` : ""}</span></span>
          <span class="rl-chips">${procChip}${causeChip}</span>
          <span class="rl-odds">${american(b.odds)}</span>
          <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
        </div>`;
      }

/* The stale-line sampler: every pre-game scanner flag, journaled at a flat
   nominal stake and settled like any bet. The signal's CLV was measured on
   30k harvested quotes; this bucket measures whether TAKING the flagged
   price actually cashes — the difference between a statistic and a bet. */
/* Team-form sampler — does backing HOT teams at real prices make money?
   Same quarantine pattern as the stale sampler. */
function recFormSection(fm) {
  if (!fm || (!fm.settled && !fm.open)) return "";
  const graded = fm.wins + fm.losses;
  const hitRate = graded ? (fm.wins / graded) * 100 : 0;
  const rows = (fm.recent || []).map((b) => {
    const won = b.status === "won";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${won ? "won" : "lost"}">
      <span class="rl-icon">${won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(teamName(b.player))}</strong>
        <span class="rl-bet">hot-team moneyline</span></span>
      <span class="rl-proc">form gap ${b.edge != null ? Number(b.edge).toFixed(2) : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title minor">Team-form sampler — measurement in progress
      <span class="sub">— every hot-vs-cold matchup, hot side’s moneyline at the real book
      price. Flat 0.1u, zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `Streaks are the most public stat in
      sports, so the default assumption is the market already prices them — hot teams
      cost more to back. This bucket journals the hot team’s moneyline in every
      hot-vs-cold matchup at the price someone could actually bet, and settles it
      against the real result. The promotion bar is the same as every sampler:
      100+ graded, z ≥ 2, positive ROI. Clear it and form becomes a model input;
      miss it and we’ve learned the market has streaks covered — cheaply.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (fm.roi >= 0 ? "+" : "") + (fm.roi * 100).toFixed(1) + "%",
                `${fm.net_units >= 0 ? "+" : ""}${(fm.net_units || 0).toFixed(2)}u on ${(fm.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(fm.roi) })}
      ${recTile("Sampler record", `${fm.wins}-${fm.losses}`, `${fm.open} open`)}
      ${recTile("Hit rate", graded ? hitRate.toFixed(1) + "%" : "—",
                fm.avg_taken_implied != null
                  ? `needs ${(fm.avg_taken_implied * 100).toFixed(1)}% to break even`
                  : "accrues as games settle")}
      ${recTile("Avg form gap", fm.avg_form_gap != null ? fm.avg_form_gap.toFixed(2) : "—",
                "hot-vs-cold score spread sampled")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `${panelEmpty("Fills as hot-vs-cold matchups settle.")}`}</div>`;
}

function recStaleSection(st) {
  if (!st || (!st.settled && !st.open)) return "";
  const graded = st.wins + st.losses;
  const hitRate = graded ? (st.wins / graded) * 100 : 0;
  const calib = st.avg_taken_implied != null
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px">
         The flagged prices implied <strong>${(st.avg_taken_implied * 100).toFixed(1)}%</strong>
         · the field’s consensus said <strong>${(st.avg_consensus_implied * 100).toFixed(1)}%</strong>
         · they actually hit <strong>${(st.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Hitting above the taken price’s implied = the cheap price was real value.</div>` : "";
  const rows = (st.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `field said ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title minor">Stale-line sampler — measurement in progress
      <span class="sub">— every pre-game stale-line flag, taken at the flagged price. Flat 0.1u,
      zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `The scanner flags a book pricing
      a side at least a point cheaper than every other book’s consensus. On 30,448
      harvested quotes, taking that price beat the eventual close 64.8% of the time —
      but closing-line value is a statistic, not money. This bucket journals every
      pre-game flag automatically and settles it against the real result. If the hit
      rate clears the taken price’s break-even over a real sample, the signal graduates
      from "interesting" to "bettable" — and if it doesn’t, this table is how we find
      out cheaply.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (st.roi >= 0 ? "+" : "") + (st.roi * 100).toFixed(1) + "%",
                `${st.net_units >= 0 ? "+" : ""}${(st.net_units || 0).toFixed(2)}u on ${(st.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(st.roi) })}
      ${recTile("Sampler record", `${st.wins}-${st.losses}${st.pushes ? "-" + st.pushes : ""}`,
                `${st.open} open`)}
      ${recTile("Hit rate", graded ? hitRate.toFixed(1) + "%" : "—",
                st.avg_taken_implied != null
                  ? `needs ${(st.avg_taken_implied * 100).toFixed(1)}% to break even`
                  : "accrues as flags settle")}
      ${recTile("Avg gap", st.avg_gap_pts != null ? st.avg_gap_pts.toFixed(1) + " pts" : "—",
                "flagged price vs field consensus")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${calib}${rows ||
      `${panelEmpty("Nothing settled yet — flags journal on every paid pull and grade as results ingest.")}`}</div>`;
}
