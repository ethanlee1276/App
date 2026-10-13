/* Ask Qellys grades a parlay from its screenshot — the page half.

   Ethan, 2026-10-12: "add a feature in the ai ask Qellys where users can
   upload a screenshot of there parlay and it will rank it based on all our
   data and tools and models".

   Loaded the first time it is used (app.js loadSlip), like the Feed and the
   Gamecast, so a reader who never grades a ticket never downloads it. Two
   jobs. THE PICTURE: drawn again at most 1568px on its long side (the size
   the reader reads a picture at anyway) as a JPEG small enough for the
   site's 1MB request ceiling, and sent to /api/ask/slip — kept nowhere,
   here or on the server. THE CARD the answer comes back as
   (engine/slipgrade.grade): the grade, our chance the ticket hits against
   what its payout needs, every leg ranked with our number beside what its
   price needs, the pairs the parlay engine would never build, and the
   board's likeliest pick in the weakest leg's game.

   THE LIVE LINE (engine/sliplive, Ethan 2026-10-12: "make sure we are also
   pulling live line for the picks"): each leg's price at every book right
   now at its own number, the best one and when it was pulled; once its game
   is on, the score, the clock and his number so far, and won or lost when
   it is settled. The ticket says where it stands, where to place it, the
   leg it is better without and the pairs that move together.

   AND WHAT TO DO WITH IT (Ethan, 2026-10-13: "the hedge calculator and
   better number and saving uploaded slips too moneys and live chances for
   props mid game ... for all sports"): a prop in play carries its live
   chance (engine/proplive); a leg a book quotes at a better number says
   so (slipgrade.better_number); the leg left to decide the ticket gets a
   hedge calculator that redoes its arithmetic as the reader types a price
   (slipgrade.hedge); and Save puts the slip in My Bets, where the Live tab
   follows it leg by leg (`track`, /api/ask/track) and settles it in My
   Bets when the box score does.

   AND NOTHING LEFT BLANK (Ethan, 2026-10-13, on "Josh Allen Over 5.5
   Carries — NOT ON OUR BOARD": "We can't just not give the user
   information on a prop since it's not on our board ... we need too offer
   better legs too replace legs with if needed"): a leg no board carries
   shows our own read of it (engine/slipread) with the tier the Most Likely
   board's checks would give it, and a weak, against or unpriced leg lists
   better legs to swap in (slipgrade.replacements).

   AND THE LAST LEG (Ethan, 2026-10-13: "add all of them"): a saved slip
   down to the one leg that decides it leads its card with a strip and
   the phone buzzes once (`lastLeg`, the mark kept on the My Bets entry);
   a member who switches the email on (/api/account/lastleg) is mailed
   by the box when it happens, Live tab open or not (engine/slipwatch).

   The file is chosen in app.js (a real file input inside the attach
   sheet's row, so a phone's picker opens on the tap itself), which then
   hands it here with what it owns as `ctx` — the conversation, saving it,
   drawing it, the error sentences, the thinking beat. This file touches
   nothing else of app.js's. */
(function () {
  "use strict";

  const MAX_SIDE = 1568;
  /* The server takes 740 KB of picture (slipgrade.MAX_IMAGE_BYTES); base64
     is a third bigger, and the JSON around it must stay under 1MB. */
  const MAX_B64 = 900000;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (p) => (p == null ? "—" : `${Math.round(Number(p) * 100)}%`);
  const price = (o) => (o ? (o > 0 ? `+${o}` : String(o)) : "");
  const num = (x) => { const n = Number(x); return Number.isFinite(n) ? String(Math.round(n * 10) / 10) : ""; };
  /* "25m ago" from a UTC stamp — the price's own pull, never the page's load. */
  const ago = (iso) => {
    const t = Date.parse(iso || "");
    if (!Number.isFinite(t)) return "";
    const m = Math.max(0, Math.round((Date.now() - t) / 60000));
    return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 48 * 60 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
  };
  /* "Sun 4:25 PM" from the board's "YYYY-MM-DD HH:MM" (the board's own clock, Eastern). */
  const kick = (s) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})/.exec(String(s || ""));
    if (!m) return "";
    const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
    const h = +m[4];
    return `${day} ${((h + 11) % 12) + 1}:${m[5]} ${h < 12 ? "AM" : "PM"} ET`;
  };

  const money = (x) => `$${(Math.round(Number(x) * 100) / 100).toFixed(2)}`;
  const signed = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(Math.round(x * 100))}%`;
  /* American odds to the decimal multiplier on the stake; null for none. */
  const dec = (o) => { const a = Number(o); return !a || !Number.isFinite(a) ? null : a > 0 ? 1 + a / 100 : 1 + 100 / Math.abs(a); };
  const american = (d) => (!(d > 1) ? 0 : d >= 2 ? Math.round((d - 1) * 100) : -Math.round(100 / (d - 1)));

  const MARKET = {
    pass_yds: "Pass Yds", pass_td: "Pass TDs", pass_att: "Pass Attempts", pass_cmp: "Completions",
    pass_int: "Interceptions", rush_yds: "Rush Yds", rush_att: "Carries", rec_yds: "Rec Yds",
    receptions: "Receptions", rush_rec_yds: "Rush + Rec Yds", pass_rush_yds: "Pass + Rush Yds",
    kick_pts: "Kicking Pts", fg_made: "FGs Made", tackles_ast: "Tackles + Ast",
    pts: "Points", reb: "Rebounds", ast: "Assists", pra: "Pts + Reb + Ast", fg3m: "Threes",
    pts_reb: "Pts + Reb", pts_ast: "Pts + Ast", reb_ast: "Reb + Ast",
    hits: "Hits", total_bases: "Total Bases", home_runs: "Home Runs", strikeouts: "Strikeouts",
    outs: "Outs", sog: "Shots on Goal", points: "Points", goals: "Goals", assists: "Assists",
    blocks: "Blocks", saves: "Saves",
  };
  const VERDICT = { strong: "Strong", fair: "Fair", weak: "Weak", against: "Against", unpriced: "Not on our board" };
  const FOUND = { likely: "On our Most Likely board", prop: "Our projection", scorer: "Our scorer model",
    game: "Our game line", read: "Our read — not on our board", game_read: "Our read — not on our board" };

  /* ---- the picture ------------------------------------------------------ */
  /* createImageBitmap reads the file without an <img>; where it is missing,
     a data: URL, which the page's policy allows (a blob: URL it does not). */
  async function decode(file) {
    if (window.createImageBitmap) {
      try { return await createImageBitmap(file); } catch (e) { /* the <img> way below */ }
    }
    const url = await new Promise((ok, no) => {
      const r = new FileReader();
      r.onload = () => ok(r.result);
      r.onerror = () => no(new Error("unreadable"));
      r.readAsDataURL(file);
    });
    return new Promise((ok, no) => {
      const img = new Image();
      img.onload = () => ok(img);
      img.onerror = () => no(new Error("unreadable"));
      img.src = url;
    });
  }

  async function shrink(file) {
    const src = await decode(file);
    const w = src.naturalWidth || src.width, h = src.naturalHeight || src.height;
    if (!w || !h) throw new Error("unreadable");
    try {
      for (const side of [MAX_SIDE, 1280, 1024]) {
        const k = Math.min(1, side / Math.max(w, h));
        const c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(w * k));
        c.height = Math.max(1, Math.round(h * k));
        const g = c.getContext("2d");
        g.fillStyle = "#fff";                    // a see-through PNG is not drawn onto black
        g.fillRect(0, 0, c.width, c.height);
        g.drawImage(src, 0, 0, c.width, c.height);
        for (const q of [0.85, 0.72, 0.6]) {
          const b64 = (c.toDataURL("image/jpeg", q).split(",")[1]) || "";
          if (b64 && b64.length <= MAX_B64) return b64;
        }
      }
    } finally {
      if (src.close) src.close();
    }
    throw new Error("too large");
  }

  /* ---- the conversation --------------------------------------------------- */
  /* The server's own sentence where it wrote one for the reader (not a slip,
     a picture it could not take); the explainer's sentences otherwise. */
  function errorText(ctx, status, body) {
    const e = body && typeof body.error === "string" ? body.error : "";
    if (e && (status === 400 || status === 413 || status === 422)) {
      return e.charAt(0).toUpperCase() + e.slice(1) + (/[.!?]$/.test(e) ? "" : ".");
    }
    return ctx.errorText(status, body);
  }

  async function send(ctx, file) {
    const a = ctx.state();
    if (a.busy) return;
    a.turns.push({ role: "user", text: "Grade this parlay (screenshot attached)" });
    a.busy = true;
    ctx.render();
    const asked = Date.now();
    let turn;
    try {
      if (file.type && !/^image\//.test(file.type)) throw new Error("unreadable");
      const image = await shrink(file);
      const res = await fetch("/api/ask/slip", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image, media_type: "image/jpeg" }),
      });
      let body = {};
      try { body = await res.json(); } catch (e) { body = {}; }
      turn = res.ok && body.slip
        ? { role: "assistant", text: String(body.text || ""), sig: body.sig || "", slip: body.slip }
        : { role: "assistant", text: errorText(ctx, res.status, body), error: true };
    } catch (e) {
      const why = e && e.message;
      turn = { role: "assistant", error: true, text: why === "too large"
        ? "That picture is too large to send — crop it to the ticket and try again."
        : why === "unreadable" ? "That file couldn’t be opened as a picture — try a screenshot."
          : ctx.errorText(0, null) };
    }
    const beat = ctx.thinkMs - (Date.now() - asked);
    if (beat > 0) await new Promise((r) => setTimeout(r, beat));
    a.turns.push(turn);
    a.busy = false;
    ctx.save();
    ctx.render();
  }

  /* ---- the card ------------------------------------------------------------ */
  function legName(l) {
    const side = l.side ? l.side.charAt(0).toUpperCase() + l.side.slice(1) : "";
    if (l.market === "moneyline") return `${l.team || l.game} moneyline`;
    if (l.market === "spread") return `${l.team || l.game} ${l.line > 0 ? "+" : ""}${num(l.line)}`;
    if (l.market === "total") return `${l.game ? `${l.game} · ` : ""}${side} ${num(l.line)} points`;
    if (l.market === "anytime_td" || l.market === "anytime_goal") {
      return `${l.player} ${l.side === "no" ? "not " : ""}to score`;
    }
    if (l.market === "other") return l.text || l.player || "Leg";
    return `${l.player} ${side} ${num(l.line)} ${MARKET[l.market] || l.market}`;
  }

  function legHTML(l, i) {
    const v = l.verdict || "unpriced";
    const meta = [];
    if (l.prob != null) meta.push(`ours <b>${pct(l.prob)}</b>`);
    if (l.needs != null) meta.push(`needs ${pct(l.needs)}${l.odds ? ` at ${esc(price(l.odds))}` : ""}`);
    if (l.game && l.market !== "total") meta.push(esc(l.game));
    const st = (l.live && l.live.state) || "";
    if (l.kickoff && st !== "live" && st !== "final" && kick(l.kickoff)) meta.push(esc(kick(l.kickoff)));
    const where = l.found && l.prob != null ? `${FOUND[l.found] || ""}${l.tier ? ` · ${esc(l.tier)}` : ""}${
      readTag(l)}${
      l.sim_hits != null && simN ? ` · hit in ${Number(l.sim_hits).toLocaleString()} of ${simN.toLocaleString()} simulated nights` : ""}` : "";
    const label = v === "unpriced" && l.found ? "No number of ours" : (VERDICT[v] || v);
    const bar = l.prob != null
      ? `<div class="pgr-bar" aria-hidden="true"><i style="width:${Math.round(l.prob * 100)}%"></i>${
        l.needs != null ? `<u style="left:${Math.round(l.needs * 100)}%"></u>` : ""}</div>` : "";
    const res = l.live && l.live.result;
    return `<li class="pgr-leg v-${esc(v)}${res ? ` r-${esc(res)}` : ""}">
      <div class="pgr-leg-h"><span class="pgr-n">${i + 1}</span><b>${esc(legName(l))}</b>
        ${res ? `<span class="pgr-res r-${esc(res)}">${esc(RESULT[res] || res)}</span>` : ""}
        <span class="pgr-pill v-${esc(v)}">${esc(label)}</span></div>
      ${meta.length ? `<div class="pgr-leg-m">${meta.join(" · ")}</div>` : ""}${bar}
      ${liveHTML(l)}${priceHTML(l)}${betterNumHTML(l)}
      ${where ? `<div class="pgr-leg-w">${where}</div>` : ""}${readHTML(l)}${whyHTML(l)}${chartsHTML(l)}${swapsHTML(l)}
    </li>`;
  }

  /* HIS CHARTS, ONE TAP FROM THE LEG (Ethan, 2026-10-13: "I feel like
     there is more then one place we can route the route checker on"). A
     football leg the charts speak to — rushing, receiving, an anytime
     touchdown — carries a door to his charts; app.js opens it (.cc-open)
     wherever it is drawn. A leg does not know his position, so an NFL
     door asks for "his chart" (kind auto): both are fetched and the one
     he does more of leads — a back's carries even on a receptions leg
     (Ethan: "we are showing only receptions for RBs and only carries for
     WR and TE"). A quarterback's throws are his (the passing chart), and
     college has its carries and, from 2025, the targets its play file
     names, so its door asks for his chart the same way. A baseball leg
     opens the bet's side of the ball: a pitcher's pitch chart on his
     strikeouts or outs, a hitter's hit tracker on anything else. */
  function chartsHTML(l) {
    const lg = String(l.sport || "").toLowerCase(), m = String(l.market || "");
    if (!l.player) return "";
    const door = lg === "nfl" && /rush|rec|anytime|pass/.test(m) ? ["auto", "His charts"]
      : lg === "cfb" && /rush|rec|anytime/.test(m) ? ["auto", "His charts"]
        : lg === "mlb" ? (/^(strikeouts|outs)$/.test(m) ? ["pitches", "Pitch chart"] : ["spray", "Hit tracker"]) : null;
    return door ? `<div class="pgr-charts"><button type="button" class="pgr-chart cc-open" data-carry="${esc(l.player)}" data-lg="${lg}" data-kind="${door[0]}">${door[1]}</button></div>` : "";
  }

  /* AN OFF-BOARD READ (engine/slipread, Ethan 2026-10-13: "We can't just not
     give the user information on a prop since it's not on our board"): the
     board's own model run on a leg the board never built, held to the four
     checks the Most Likely board runs — said as the tier it would earn. */
  function readTag(l) {
    const r = l.read;
    /* A side or a total read off the board (engine/slipgame): our game
       model's own number before the market held it. */
    if (l.found === "game_read" && r) return r.raw != null ? ` · our model alone ${pct(r.raw)}, held to the market` : "";
    if (l.found !== "read" || !r) return "";
    const n = (r.passed || []).length;
    return `${r.would_be && r.makes_board ? ` · would be <b>${esc(r.would_be)}</b> on Most Likely`
      : " · under our Most Likely floor"} · passes ${n} of 4 checks`;
  }

  /* A read with no number — the model refused the role, or we keep too few
     of his games — still says what we know. */
  function readHTML(l) {
    const r = l.read;
    if (l.found === "game_read" && r && l.prob == null) {
      return `<div class="pgr-leg-w">Not on our board${r.why_off ? ` — ${esc(r.why_off)}` : ""}. ${
        r.refused ? `Our game model won’t price it: ${esc(r.refused)}.` : ""} What our data says is below.</div>`;
    }
    if (l.found !== "read" || !r || l.prob != null) return "";
    return `<div class="pgr-leg-w">Not on our board${r.why_off ? ` — ${esc(r.why_off)}` : ""}. ${
      r.refused ? `Our model won’t price it: ${esc(r.refused)}` : "We keep too few of his games to price it."}</div>`;
  }

  /* BETTER LEGS FOR THIS SPOT (slipgrade.replacements, Ethan 2026-10-13: "we
     need too offer better legs too replace legs with if needed"): the same
     bet at a better number, then the board's own picks in the game, each
     with what the swap does to the ticket by our numbers. */
  function swapsHTML(l) {
    const sw = Array.isArray(l.swaps) ? l.swaps : [];
    if (!sw.length) return "";
    const tag = (x) => x.kind === "number" ? "Better number" : x.same_player ? "His other bet"
      : x.tier ? x.tier : x.found === "game" ? "Our game line" : "Our projection";
    return `<div class="pgr-swaps"><b>Better legs for this spot</b><ul>${sw.map((x) => `<li><span class="pgr-swap-k">${
      esc(tag(x))}</span> <b>${esc(x.label)}</b>${x.odds ? ` at ${esc(price(x.odds))}` : ""}${x.book ? ` (${esc(x.book)})` : ""} — ours ${
      pct(x.prob)}${x.ticket_odds ? ` · the ticket pays ${esc(price(x.ticket_odds))}${x.approx ? " (about)" : ""}` : ""}${
      x.ticket_ev != null ? `, return <b class="${x.ticket_ev >= 0 ? "pos" : "neg"}">${signed(x.ticket_ev)}</b>` : ""}</li>`).join("")}</ul></div>`;
  }

  const RESULT = { won: "Won", lost: "Lost", push: "Push" };

  /* What the books show for the leg now, at its own number (sliplive.leg_prices). */
  function priceHTML(l) {
    const p = l.price;
    if (!p) return "";
    if (!p.books || !p.books.length) {
      return `<div class="pgr-price none">${p.any
        ? `No book has a price at exactly ${esc(num(l.line))}${p.main_line != null ? ` — the main line is ${esc(num(p.main_line))}` : ""}.`
        : "No book is pricing this right now."}</div>`;
    }
    const books = p.books.slice(0, 3).map((b, k) => `${k ? "" : "<b>"}${esc(b.book || "Best price")} ${esc(price(b.odds))}${k ? "" : "</b>"}`);
    const bits = [`Now ${books.join(" · ")}`];
    if (p.n > 3) bits.push(`${p.n} books`);
    if (p.fair != null) bits.push(`${pct(p.fair)} with the margin out`);
    if (p.beats_yours && l.odds) bits.push(`<span class="up">beats your ${esc(price(l.odds))}</span>`);
    if (p.main_line != null) bits.push(`main line ${esc(num(p.main_line))}`);
    if (p.stale) bits.push("price may have moved");
    const when = ago(p.as_of);
    return `<div class="pgr-price">${bits.join(" · ")}${when ? ` <span class="pgr-when">· priced ${esc(when)}</span>` : ""}</div>`;
  }

  /* Where the leg's game stands (sliplive.live_state): the score and the
     clock, his number so far against the line, the moneyline's live chance. */
  function liveHTML(l) {
    const g = l.live;
    if (!g || (g.state !== "live" && g.state !== "final")) return "";
    const tag = g.state === "live" ? `<span class="pgr-live-tag">Live</span>` : `<span class="pgr-live-tag fin">Final</span>`;
    const score = g.home_score != null && g.away_score != null
      ? `${esc(g.away)} ${esc(g.away_score)} – ${esc(g.home_score)} ${esc(g.home)}` : "";
    const bits = [score, g.state === "live" ? esc(g.clock || "") : ""].filter(Boolean);
    let prog = "";
    if (g.current != null && l.market !== "moneyline" && l.market !== "spread") {
      const line = (l.market === "anytime_td" || l.market === "anytime_goal") ? 0.5 : Number(l.line);
      const what = l.market === "total" ? "Total" : "Has";
      bits.push(`${what} <b>${esc(num(g.current))}</b>${Number.isFinite(line) && line !== 0.5 ? ` of ${esc(num(line))}` : ""}`);
      if (Number.isFinite(line) && line > 0.5) {
        prog = `<div class="pgr-prog" aria-hidden="true"><i style="width:${Math.min(100, Math.round(100 * g.current / line))}%"></i></div>`;
      }
    } else if (l.market === "spread" && g.cover_by != null) {
      bits.push(g.cover_by > 0 ? `covering by ${esc(num(g.cover_by))}` : g.cover_by < 0 ? `short by ${esc(num(-g.cover_by))}` : "right on the number");
    } else if (l.market === "moneyline" && g.win_prob != null && g.state === "live") {
      bits.push(`<b>${pct(g.win_prob)}</b> to win now`);
    }
    if (g.note) bits.push(esc(g.note));
    return `<div class="pgr-live">${tag} ${bits.join(" · ")}</div>${prog}${g.state === "live" ? chanceHTML(g.chance) : ""}`;
  }

  /* A prop in play, as a race between what he has banked and the game
     left (engine/proplive): our chance the bet wins now, and what it rests
     on — the final he is on course for at his pregame rate, or in baseball
     the plate appearances or batters he has left. */
  function chanceHTML(c) {
    if (!c || c.p == null) return "";
    const on = c.model === "mlb" && c.left != null ? `about ${num(c.left)} ${c.left_unit} left`
      : c.expected != null ? `on course for about ${num(c.expected)}` : "";
    return `<div class="pgr-chance">Our chance now <b>${pct(c.p)}</b>${on ? ` · ${esc(on)}` : ""}${
      c.push ? ` · ${pct(c.push)} to push` : ""}${c.from === "price" ? " · started from its price, not ours" : ""}</div>`;
  }

  /* The same bet at another number a book quotes, when it is the better
     bet by our numbers (slipgrade.better_number), with what it does to the
     ticket. */
  function betterNumHTML(l) {
    const b = l.better_number;
    if (!b) return "";
    return `<div class="pgr-bn"><b>Better number:</b> ${esc(b.label)} at ${esc(price(b.odds))}${b.book ? ` (${esc(b.book)})` : ""} — ours ${
      pct(b.p)} vs ${pct(b.p_here)} at your number, return <b class="pos">${signed(b.ev)}</b> vs ${signed(b.ev_here)} a dollar${
      b.ticket_odds ? `. The ticket would pay ${esc(price(b.ticket_odds))}${b.ticket_ev != null ? `, return ${signed(b.ticket_ev)}` : ""}` : ""}.</div>`;
  }

  /* THE HEDGE. W is what the ticket returns if the last leg wins (stake ×
     its decimal payout, a pushed leg taken out by the server). A bet of H
     at decimal d on the other side returns H·d, so H = W/d returns the
     same either way, and B = S/(d − 1) wins the stake back if the leg
     misses. By our chance p for the leg, the hedge bet itself is worth
     H·((1 − p)·d − 1) — what locking costs, or adds, in expected value. */
  function hedgeOut(stake, pay, odds, p, leg) {
    const S = Number(stake), d = dec(odds), P = Number(pay);
    if (!(S > 0) || !(P > 1) || !d) return `<p class="pgr-hedge-none">Type your stake and the hedge’s price to see the numbers.</p>`;
    const W = S * P, H = W / d, either = W - S - H, B = S / (d - 1), ifHits = W - S - B;
    const rows = [`No hedge: <b class="pos">+${money(W - S)}</b> if it hits, <b class="neg">−${money(S)}</b> if it misses.`];
    rows.push(either > 0
      ? `Lock it: bet <b>${money(H)}</b> and you’re up <b class="pos">${money(either)}</b> whichever way it goes.`
      : "At this price no hedge locks a profit — it would cost more than the ticket can win.");
    if (ifHits > 0) rows.push(`Stake back: bet <b>${money(B)}</b> — <b class="pos">+${money(ifHits)}</b> if it hits, $0.00 if it misses.`);
    const pp = p === "" || p == null ? null : Number(p);
    if (pp != null && Number.isFinite(pp) && either > 0) {
      const ev = H * ((1 - pp) * d - 1);
      rows.push(`By our ${pct(pp)} for ${esc(leg)}, locking ${ev < 0 ? `costs about <b>${money(-ev)}</b>` : `adds about <b>${money(ev)}</b>`} in expected value.`);
    }
    return rows.map((r) => `<p>${r}</p>`).join("");
  }

  /* THE CASH-OUT. A book buys the ticket back for less than it is worth
     to the book; the only question is how much less. By our numbers the
     ticket is worth p × W right now — W its return if the rest win (stake
     × the decimal payout, a pushed leg taken out by the server), p our
     chance for the rest. Against that an offer is a take, a hold, or a
     coin flip (within CASH_EVEN of fair). Never advice: the numbers, and
     what holding risks, said plainly. */
  const CASH_EVEN = 0.03;
  function cashOut(stake, pay, p, offer) {
    const S = Number(stake), P = Number(pay), pp = Number(p);
    if (!(S > 0) || !(P > 1) || !Number.isFinite(pp)) return `<p class="pgr-hedge-none">Type your stake to see what the ticket is worth by our numbers.</p>`;
    const W = S * P, fair = W * pp;
    const rows = [`By our ${pct(pp)} for the rest, the ticket is worth <b>${money(fair)}</b> right now — ${pct(pp)} of the <b>${money(W)}</b> it returns if the rest win.`];
    const raw = String(offer == null ? "" : offer).replace(/[$,\s]/g, "");
    const C = Number(raw);
    if (raw === "" || !Number.isFinite(C) || C < 0) {
      rows.push("Type the cash-out your book is offering and we’ll hold it to that.");
    } else if (!(fair > 0)) {
      rows.push("Any offer beats a ticket we give no chance.");
    } else {
      const ratio = C / fair;
      if (ratio >= 1 + CASH_EVEN) rows.push(`<b class="pos">Take it</b>, by our numbers: ${money(C)} is <b>${money(C - fair)}</b> over what the ticket is worth.`);
      else if (ratio <= 1 - CASH_EVEN) rows.push(`<b class="neg">Hold</b>, by our numbers: the offer is ${pct(ratio)} of fair — the book keeps about <b>${money(fair - C)}</b>. Holding is ${pct(pp)} to collect ${money(W)} and ${pct(1 - pp)} to collect nothing.`);
      else rows.push(`<b>About even</b> — the offer is within ${pct(CASH_EVEN)} of fair. Your call: ${money(C)} now, or ${pct(pp)} at ${money(W)}.`);
    }
    return rows.map((r) => `<p>${r}</p>`).join("");
  }

  function cashoutHTML(c) {
    if (!c || !(c.payout > 1) || c.p == null) return "";
    return `<div class="pgr-hedge pgr-cash" data-pay="${esc(c.payout)}" data-p="${esc(c.p)}">
      <div><b>Cash-out check</b> — what the ticket is worth right now by our numbers, against what your book offers.</div>
      <div class="pgr-hedge-in">
        <label>Your stake $<input data-cash="stake" inputmode="decimal" value="${c.stake ? esc(c.stake) : ""}" placeholder="10"></label>
        <label>Book offers $<input data-cash="offer" inputmode="decimal" value="" placeholder="45"></label>
      </div>
      <div class="pgr-hedge-out">${cashOut(c.stake, c.payout, c.p, "")}</div>
      <small>${c.from === "live" ? "Our chance for the rest is as the games stand now — it moves as they do." : "Nothing has started: our chance for the rest is the pre-game one."}${
        c.approx ? " Legs in one game are priced about, not exactly." : ""}</small>
    </div>`;
  }

  function hedgeHTML(h) {
    if (!h || !(h.payout > 1)) return "";
    const head = h.plan ? `<b>Hedge plan</b> — if the rest hit, <b>${esc(h.leg)}</b> decides the ticket.`
      : `<b>One leg left</b> — <b>${esc(h.leg)}</b> decides the ticket.`;
    const src = h.odds ? `${h.book ? `${esc(h.book)} ` : ""}${esc(price(h.odds))}` : "";
    return `<div class="pgr-hedge" data-pay="${esc(h.payout)}" data-p="${h.p_leg == null ? "" : esc(h.p_leg)}" data-leg="${esc(h.leg)}">
      <div>${head} The hedge is <b>${esc(h.other)}</b>.</div>
      <div class="pgr-hedge-in">
        <label>Your stake $<input data-hedge="stake" inputmode="decimal" value="${h.stake ? esc(h.stake) : ""}" placeholder="10"></label>
        <label>Hedge price <input data-hedge="odds" inputmode="numeric" value="${h.odds ? esc(h.odds) : ""}" placeholder="-150"></label>
      </div>
      <div class="pgr-hedge-out">${hedgeOut(h.stake, h.payout, h.odds, h.p_leg, h.leg)}</div>
      <small>${src ? `The price filled in is our last pull: ${src}${h.stale ? ", from before the game started — books move it, so type the one you see now" : ""}.`
        : "We have no price for the other side — type the one your book shows."}${
        h.approx ? " Same-game parlays pay their own way, so the payout here is close, not exact." : ""}</small>
    </div>`;
  }

  /* The facts behind the leg's number, from the board itself
     (engine/slipgrade.why): the projection and its range, how often he has
     cleared this number, the defence, the steps that moved the number, the
     game script, the scan's read, anything to watch and the books' price.
     Folded, so a twelve-leg ticket is still a list. */
  function whyHTML(l) {
    const facts = Array.isArray(l.why) ? l.why : [];
    if (!facts.length) return "";
    return `<details class="pgr-why"><summary>${l.prob != null ? `Why we say ${esc(pct(l.prob))}` : "What we found"}</summary><dl>${
      facts.map((f) => `<dt>${esc(f.k)}</dt><dd>${esc(f.t)}</dd>`).join("")}</dl></details>`;
  }

  /* The ticket replayed (engine/slipgrade.simulate): a bar for each count
     of legs that landed, the last one — every leg — in gold. */
  function simHTML(sim, n) {
    if (!sim || !sim.nights || !Array.isArray(sim.legs_hit)) return "";
    const peak = Math.max(1, ...sim.legs_hit);
    const bars = sim.legs_hit.map((c, k) => `<div class="pgr-sim-col${k === n ? " all" : ""}">
        <i style="height:${Math.max(2, Math.round(100 * c / peak))}%"></i>
        <span>${k === n ? `all ${n}` : k}</span></div>`).join("");
    const br = sim.breaker;
    return `<div class="pgr-sim">
      <div class="pgr-sim-h"><b>${sim.nights.toLocaleString()} simulated nights</b>
        <span>cashed <b>${Number(sim.cashed).toLocaleString()}</b> times · ${(100 * sim.rate).toFixed(1)}%</span></div>
      <div class="pgr-sim-bars" aria-hidden="true">${bars}</div>
      <p class="pgr-sim-note">Legs that landed each night. Every leg is drawn from its own chance, and legs in one
        game rise and fall together the way our parlay engine measures them.${sim.one_short && br
          ? ` Missed by one leg on ${pct(sim.one_short)} of nights — most often <b>${esc(br.leg)}</b> (${pct(br.share)} of those).` : ""}</p>
    </div>`;
  }

  /* Where the ticket stands once its games are on (slipgrade.standing). */
  function nowHTML(n) {
    if (!n) return "";
    if (n.status === "lost") return `<div class="pgr-now s-lost"><b>Lost</b> — ${esc(n.lost_leg)} missed.</div>`;
    if (n.status === "won") return `<div class="pgr-now s-won"><b>Every leg has won.</b></div>`;
    const bits = [["won", "won"], ["push", "pushed"], ["live", "in play"], ["start", "yet to start"]]
      .filter(([k]) => n[k]).map(([k, w]) => `${n[k]} ${w}`);
    return `<div class="pgr-now s-open"><b>Live</b> · ${bits.join(" · ")}${n.chance != null
      ? ` · our chance for the rest <b>${pct(n.chance)}</b>` : n.live ? " · no number for the rest — a leg in play has no live chance yet" : ""}</div>`;
  }

  function alertsHTML(a) {
    if (!Array.isArray(a) || !a.length) return "";
    return `<div class="pgr-alerts"><b>Read this first</b><ul>${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  }

  /* The ticket at each book quoting every leg (slipgrade.shop). */
  function shopHTML(sh) {
    if (!sh || !Array.isArray(sh.books) || !sh.books.length) return "";
    const books = sh.books.map((b, k) => `${k ? "" : "<b>"}${esc(b.book)} ${esc(price(b.odds))}${k ? "" : "</b>"}`).join(" · ");
    return `<div class="pgr-shop"><b>Place it at</b> ${books}${sh.yours ? ` · your slip ${esc(price(sh.yours))}` : ""}${
      sh.same_game ? `<small>Books price same-game parlays their own way — these are each book’s legs multiplied.</small>` : ""}</div>`;
  }

  /* The leg it is better without, by our numbers (slipgrade.without). */
  function betterHTML(b) {
    if (!b || !b.leg) return "";
    const ev = Math.round(b.ev * 100);
    return `<div class="pgr-better"><b>Better without</b> ${esc(b.leg)}: chance ${pct(b.chance)}, pays ${esc(price(b.odds))}${
      b.approx ? " (about)" : ""}, return <b class="${ev >= 0 ? "pos" : "neg"}">${ev >= 0 ? "+" : ""}${ev}%</b> a dollar.</div>`;
  }

  /* Same-game legs that move together or pull apart (slipgrade.pairs). */
  function pairsHTML(ps) {
    if (!Array.isArray(ps) || !ps.length) return "";
    return `<div class="pgr-pairs"><b>Legs that move together</b><ul>${ps.map((x) => `<li><span class="${
      x.rho >= 0 ? "up" : "down"}">${x.rho >= 0 ? "Together" : "Apart"} ${x.rho >= 0 ? "+" : ""}${esc(Number(x.rho).toFixed(2))}</span> ${
      esc((x.legs || []).join(" + "))}${x.why ? ` — ${esc(x.why)}` : ""}</li>`).join("")}</ul></div>`;
  }

  let simN = 0;
  function card(s) {
    if (!s || !Array.isArray(s.legs)) return "";
    simN = (s.sim && s.sim.nights) || 0;
    const g = String(s.grade || "?");
    const letterCls = g.charAt(0) === "?" ? "na" : g.charAt(0).toLowerCase();
    const head = [`${s.n_legs}-leg parlay`, s.book].filter(Boolean).map(esc).join(" · ");
    const lines = [];
    if (s.ours != null) {
      lines.push(`${s.now ? "Before kickoff our chance was" : "Our chance it all hits"} <b>${pct(s.ours)}</b>${
        s.needs != null ? ` · the payout needs <b>${pct(s.needs)}</b>` : ""}`);
    }
    if (s.ev != null) {
      const ev = Math.round(s.ev * 100);
      lines.push(`Expected return <b class="${ev >= 0 ? "pos" : "neg"}">${ev >= 0 ? "+" : ""}${ev}%</b> a dollar, by our numbers`);
    } else if (s.ours == null) {
      lines.push("None of these legs is on our boards tonight, so there is nothing of ours to grade it by.");
    } else {
      lines.push("The slip shows no price, so we can’t say what the payout needs.");
    }
    const unpriced = s.legs.filter((l) => l.prob == null).length;
    const foot = [];
    if (g.indexOf("*") >= 0 && unpriced) {
      const many = unpriced > 1;
      foot.push(`* We can’t price ${unpriced} leg${many ? "s" : ""} — ${many ? "they count" : "it counts"} at ${
        many ? "their own prices’" : "its own price’s"} break-even, so ${
        many ? "they neither help nor hurt" : "it neither helps nor hurts"} the grade.`);
    }
    if (s.dropped) {
      foot.push(`${s.dropped} leg${s.dropped > 1 ? "s" : ""} on the picture couldn’t be read and ${s.dropped > 1 ? "are" : "is"} left out.`);
    }
    const notes = (s.notes || []).map((n) => `<div class="pgr-note${n.kind === "kill" ? " kill" : ""}"><b>${
      n.kind === "kill" ? (n.exclusive === false ? "Our parlay engine never pairs these" : "These can’t both win")
        : "One bet sold twice"}:</b> ${esc((n.legs || []).join(" + "))}${
      n.why ? ` — ${esc(n.why)}` : ""}</div>`).join("");
    const sw = s.swap;
    const swapped = s.legs.some((l) => l.is_weakest && Array.isArray(l.swaps) && l.swaps.length);
    const swap = s.weakest ? `<div class="pgr-swap"><b>Weakest leg:</b> ${esc(s.weakest)}.${swapped ? " Better legs for it are listed under it."
      : sw ? ` Our likeliest pick in that game: <b>${
      esc(sw.player)} ${esc(String(sw.side || "").toLowerCase())} ${esc(num(sw.line))} ${esc(MARKET[sw.market] || sw.market)}</b> — ${
      pct(sw.prob)}${sw.odds ? ` at ${esc(price(sw.odds))}` : ""}.` : ""}</div>` : "";
    return `<div class="pgr-card">
      <div class="pgr-top"><div class="pgr-grade g-${letterCls}" aria-label="Grade ${esc(g)}">${esc(g.replace("*", ""))}${
        g.indexOf("*") >= 0 ? "<sup>*</sup>" : ""}</div>
        <div class="pgr-sum"><b>${head}</b>${lines.map((x) => `<span>${x}</span>`).join("")}</div></div>
      ${nowHTML(s.now)}${alertsHTML(s.alerts)}${shopHTML(s.shop)}${betterHTML(s.better)}${hedgeHTML(s.hedge)}${cashoutHTML(s.cashout)}
      ${simHTML(s.sim, s.n_legs)}
      <ol class="pgr-legs">${s.legs.map(legHTML).join("")}</ol>
      ${pairsHTML(s.pairs)}${notes}${swap}
      ${foot.map((f) => `<p class="pgr-foot">${esc(f)}</p>`).join("")}${saveHTML(s)}
      <p class="pgr-fine">Read from your screenshot by AI and priced by our models. Not betting advice.
        <span>21+ · 1-800-GAMBLER</span></p>
    </div>`;
  }

  /* ---- My Bets ------------------------------------------------------------- */
  /* My Bets lives in app.js (mbLoad / mbSave: this browser, and the account
     copy when signed in). Read where it is; a page without it saves nothing. */
  const book = () => (typeof mbLoad === "function" && typeof mbSave === "function" ? { load: mbLoad, save: mbSave } : null);
  const SLIPS = new Map();            // the cards drawn, by their slip's key, for Save
  const hash = (t) => { let h = 5381; for (let i = 0; i < t.length; i++) h = ((h * 33) ^ t.charCodeAt(i)) >>> 0; return h.toString(36); };
  /* The same ticket read twice is the same key: its legs, its price. */
  function slipKey(s) {
    return `s${hash((s.legs || []).map((l) => [l.player || l.team || l.game, l.market, l.side, l.line, l.odds].join(":"))
      .sort().join("|") + `|${s.total_odds || ""}`)}`;
  }
  /* The slip's own price, else its legs' multiplied (books price a
     same-game parlay their own way, which is why the slip's comes first). */
  function ticketOdds(s) {
    if (Number(s.total_odds)) return Number(s.total_odds);
    const ds = (s.legs || []).map((l) => dec(l.odds));
    return ds.length && ds.every(Boolean) ? american(ds.reduce((a, b) => a * b, 1)) : 0;
  }
  function today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  /* A My Bets entry, with the legs as the card resolved them — the
     board's player names and team codes and the game ("BUF @ LA"), which
     is what finds the game on the scoreboard after the board moves on. */
  function entryOf(s, stake, odds, key) {
    const legs = s.legs || [];
    const sports = [...new Set(legs.map((l) => String(l.league || l.sport || "").toUpperCase()).filter(Boolean))];
    const desc = `${legs.length}-leg parlay: ${legs.map(legName).join(" + ")}`;
    return {
      id: Date.now() + "" + Math.floor(Math.random() * 1e4),
      book: s.book || "Other", sport: sports.length === 1 ? sports[0] : "Other",
      date: String(s.first_kickoff || "").slice(0, 10) || today(),
      desc: desc.length > 160 ? `${desc.slice(0, 159)}…` : desc,
      stake, odds, result: "pending", src: "slip", slip_key: key,
      legs: legs.map((l) => ({ sport: l.league || l.sport, player: l.player, team: l.team, game: l.game,
        market: l.market, side: l.side, line: l.line, odds: l.odds, text: l.text })),
    };
  }
  function saveHTML(s) {
    const b = book();
    if (!b || !Array.isArray(s.legs) || !s.legs.length) return "";
    const key = slipKey(s);
    SLIPS.set(key, s);
    const have = b.load().find((x) => x && x.slip_key === key);
    if (have) return `<div class="pgr-save done">Saved to My Bets${have.result === "pending" ? " · followed on the Live tab" : ""}.</div>`;
    return `<div class="pgr-save" data-save-key="${esc(key)}">
      <label>Stake $<input data-save-stake inputmode="decimal" value="${s.stake ? esc(s.stake) : ""}" placeholder="10"></label>
      <button type="button" class="pgr-save-btn" data-save-slip>Save to My Bets</button>
      <span class="pgr-save-note">We follow it on the Live tab and settle it in My Bets when the box score does.</span>
    </div>`;
  }
  function save(btn) {
    const box = btn.closest("[data-save-key]");
    const s = box && SLIPS.get(box.dataset.saveKey);
    const b = book();
    if (!s || !b) return;
    const note = box.querySelector(".pgr-save-note");
    const stake = Number(String((box.querySelector("[data-save-stake]") || {}).value || "").replace(/[$,\s]/g, ""));
    const odds = ticketOdds(s);
    if (!(stake > 0)) { note.textContent = "Type the stake you placed it for."; return; }
    if (!odds) { note.textContent = "The slip shows no price, so there is no payout to save — log it by hand in My Bets."; return; }
    const bets = b.load();
    if (!bets.some((x) => x && x.slip_key === box.dataset.saveKey)) {
      bets.push(entryOf(s, stake, odds, box.dataset.saveKey));
      b.save(bets);
    }
    box.outerHTML = `<div class="pgr-save done">Saved to My Bets · followed on the Live tab.</div>`;
  }

  /* ---- the Live tab ------------------------------------------------------- */
  /* Every slip saved from the checker and still pending, read again once a
     minute while the Live tab is open (server `_ask_track`: the legs, no
     picture, no model call). A ticket the box score settles is settled in
     My Bets — won, lost, or every leg pushed — and says so here; one that
     won with a leg pushed is paid at its price without that leg where
     every pushed leg's price is known (`paid_odds`, which My Bets' profit
     reads, the bet itself unchanged), and left for the reader otherwise. */
  const TRACK_MS = 60000;
  const SETTLED_SHOWN_MS = 12 * 3600 * 1000;
  const T = { host: null, ctx: null, timer: 0, busy: false, last: 0, cards: {}, err: "", mail: null, mailBusy: false };

  function tracked(bets) {
    return bets.filter((b) => b && b.src === "slip" && Array.isArray(b.legs) && b.legs.length);
  }
  function settleOne(b, c) {
    const n = c && c.now;
    if (!n || b.result !== "pending") return false;
    if (n.status === "lost") b.result = "loss";
    else if (n.status !== "won") return false;
    else if (!n.push) b.result = "win";
    else if (!n.won) b.result = "push";
    else {
      const pushed = (c.legs || []).filter((l) => (l.live || {}).result === "push").map((l) => dec(l.odds));
      const whole = dec(b.odds);
      if (!whole || !pushed.length || !pushed.every(Boolean)) { b.settle_note = "won with a leg pushed — set the price your book paid"; return true; }
      b.result = "win";
      b.paid_odds = american(whole / pushed.reduce((x, y) => x * y, 1));
    }
    b.settled_by = "box";
    b.settled_at = new Date().toISOString();
    return true;
  }
  function settle(got) {
    const bets = T.ctx.load();
    let moved = false;
    got.forEach((x) => {
      const b = bets.find((y) => y && y.id === x.id);
      if (b && x.slip && settleOne(b, x.slip)) moved = true;
    });
    if (moved) T.ctx.save(bets);
  }
  /* THE LAST LEG. One leg left to decide an open ticket (slipgrade.standing
     says so): the card leads with it, and the phone buzzes once per slip —
     the mark rides on the My Bets entry, so a reload or another device does
     not buzz again. The box notices the same moment on its own clock and
     emails a member who asked (engine/slipwatch). */
  function isLast(c) {
    const n = c && c.now;
    return !!n && n.status === "open" && Number(n.left) === 1;
  }
  function lastHTML(c) {
    if (!isLast(c)) return "";
    const open = (c.legs || []).find((l) => !((l.live || {}).result));
    const who = (c.hedge && c.hedge.leg) || (open && legName(open)) || "One leg";
    return `<div class="pgr-now s-last"><b>Last leg.</b> ${esc(who)} decides it — the hedge and the cash-out check are below.</div>`;
  }
  function lastLeg(got, ctx = T.ctx) {
    const bets = ctx.load();
    const fresh = [];
    (got || []).forEach((x) => {
      const b = bets.find((y) => y && y.id === x.id);
      if (!b || b.result !== "pending" || b.last_leg || !x.slip || !isLast(x.slip)) return;
      b.last_leg = new Date().toISOString();
      fresh.push(b.id);
    });
    if (fresh.length) {
      ctx.save(bets);
      if (typeof ctx.buzz === "function") ctx.buzz("win");
    }
    return fresh;
  }
  async function refresh() {
    if (T.busy || !T.ctx) return;
    const open = tracked(T.ctx.load()).filter((b) => b.result === "pending")
      .sort((a, b) => String(b.id).localeCompare(String(a.id))).slice(0, 10);
    if (!open.length) { draw(); return; }
    T.busy = true;
    try {
      const res = await fetch("/api/ask/track", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slips: open.map((b) => ({ id: b.id, legs: b.legs, stake: b.stake, total_odds: b.odds, book: b.book })) }),
      });
      let body = {};
      try { body = await res.json(); } catch (e) { body = {}; }
      if (res.ok && Array.isArray(body.slips)) {
        T.err = "";
        body.slips.forEach((x) => { if (x && x.id) T.cards[x.id] = x; });
        settle(body.slips);
        lastLeg(body.slips);
      } else {
        T.err = res.status === 401 || res.status === 402 ? "locked" : "down";
      }
    } catch (e) {
      T.err = "down";
    }
    T.busy = false;
    T.last = Date.now();
    draw();
  }
  function trackLegHTML(l) {
    const res = l.live && l.live.result;
    const st = (l.live && l.live.state) || "";
    const when = !st || st === "scheduled" ? (l.kickoff && kick(l.kickoff) ? `<div class="pgr-leg-m">${esc(kick(l.kickoff))}</div>`
      : `<div class="pgr-leg-m">Not on the scoreboard yet</div>`) : "";
    return `<li class="pgr-leg${res ? ` r-${esc(res)}` : ""}">
      <div class="pgr-leg-h"><b>${esc(legName(l))}</b>${res ? `<span class="pgr-res r-${esc(res)}">${esc(RESULT[res] || res)}</span>` : ""}</div>
      ${liveHTML(l)}${when}</li>`;
  }
  function trackCardHTML(b, got) {
    const pay = dec(b.paid_odds || b.odds);
    const head = `<div class="pgr-track-h"><b>${esc(b.desc)}</b><span>${esc(b.book || "")} · ${money(b.stake)} at ${esc(price(b.odds))}${
      pay && b.result === "pending" ? ` · returns ${money(b.stake * pay)}` : ""}</span></div>`;
    const c = got && got.slip;
    const done = b.result !== "pending" && b.settled_by === "box"
      ? `<div class="pgr-now s-${b.result === "win" ? "won" : b.result === "loss" ? "lost" : "open"}">Settled in My Bets from the box score: <b>${
        b.result === "win" ? "Won" : b.result === "loss" ? "Lost" : "Push"}</b>${b.paid_odds ? ` at ${esc(price(b.paid_odds))} (a leg pushed)` : ""}. If your book graded it differently, change it on My Bets.</div>`
      : b.settle_note ? `<div class="pgr-now s-open">${esc(b.settle_note)} on My Bets.</div>` : "";
    if (!c) {
      return `<div class="pgr-card pgr-track-card">${head}${done}<p class="pgr-foot">${got && got.error ? esc(got.error) : "Reading the live line…"}</p></div>`;
    }
    const first = !c.now && c.first_kickoff && kick(c.first_kickoff)
      ? `<div class="pgr-now">Nothing has started · first game ${esc(kick(c.first_kickoff))}</div>` : "";
    return `<div class="pgr-card pgr-track-card">${head}${done || lastHTML(c) + (nowHTML(c.now) || first)}${b.result === "pending" ? hedgeHTML(c.hedge) + cashoutHTML(c.cashout) : ""}
      <ol class="pgr-legs">${(c.legs || []).map(trackLegHTML).join("")}</ol></div>`;
  }
  function draw() {
    const host = T.host;
    if (!host || !T.ctx) return;
    const now = Date.now();
    const show = tracked(T.ctx.load()).filter((b) => b.result === "pending"
      || (b.settled_by === "box" && now - Date.parse(b.settled_at || "") < SETTLED_SHOWN_MS))
      .sort((a, b) => String(b.id).localeCompare(String(a.id)));
    if (!show.length) { host.innerHTML = ""; return; }
    // Typing a hedge price is not interrupted by the minute's redraw.
    const typing = document.activeElement && host.contains(document.activeElement) && document.activeElement.matches("[data-hedge],[data-cash]");
    if (typing) return;
    const note = T.err === "locked" ? "Following saved slips is part of the membership."
      : T.err === "down" ? "Couldn’t reach the live line — trying again in a minute." : "";
    host.innerHTML = `<div class="section-title">Your saved slips
        <span class="sub">— from the parlay checker in Ask, followed leg by leg while the games run</span></div>
      ${note ? `<p class="pgr-foot">${esc(note)}</p>` : ""}
      ${mailHTML()}
      <div class="pgr-track">${show.map((b) => trackCardHTML(b, T.cards[b.id])).join("")}</div>`;
  }
  /* THE EMAIL (engine/slipwatch): the box mails a member when a saved slip
     reaches its last leg, Live tab open or not. The switch is the account's
     own (/api/account/lastleg), read once a visit; nothing is offered on a
     site with no mail relay, and a reader not signed in is told so. */
  function mailHTML() {
    const m = T.mail;
    if (!m) return "";
    if (!m.signed_in) return `<p class="pgr-foot pgr-mail-note">Sign in and we can email you when a saved slip is down to its last leg.</p>`;
    if (!m.available) return `<p class="pgr-foot pgr-mail-note">Email for the last leg isn’t switched on for this site yet.</p>`;
    return `<label class="pgr-mail"><input type="checkbox" data-lastleg-mail${m.on ? " checked" : ""}> Email me when a saved slip is down to its last leg<span>${
      m.on ? ` · to ${esc(m.email || "your address")}` : ""}</span></label>`;
  }
  async function loadMail() {
    if (T.mail || T.mailBusy) return;
    T.mailBusy = true;
    try {
      const res = await fetch("/api/account/lastleg", { credentials: "same-origin" });
      if (res.status === 401) T.mail = { signed_in: false };
      else if (res.ok) T.mail = Object.assign({ signed_in: true }, await res.json());
    } catch (e) { /* the panel draws without the switch; the next visit asks again */ }
    T.mailBusy = false;
    if (T.mail) draw();
  }
  async function setMail(on) {
    if (!T.mail || !T.mail.signed_in) return;
    T.mail.on = on;
    try {
      const res = await fetch("/api/account/lastleg", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ on }),
      });
      if (res.ok) Object.assign(T.mail, await res.json());
      else T.mail.on = !on;
    } catch (e) { T.mail.on = !on; }
    draw();
  }
  function track(host, ctx) {
    T.host = host;
    T.ctx = ctx;
    draw();
    loadMail();
    if (Date.now() - T.last > TRACK_MS - 10000) refresh();
    if (!T.timer) {
      T.timer = setInterval(() => {
        if (!T.ctx || (T.ctx.live && !T.ctx.live()) || document.hidden || !document.body.contains(T.host)) return;
        refresh();
      }, TRACK_MS);
    }
  }

  /* One listener each for the whole page: the hedge and the cash-out check
     redo their numbers as the reader types, and Save saves. The cards are redrawn wholesale, so
     nothing is bound to an element that a redraw would orphan. */
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("input", (e) => {
      const t = e.target;
      if (!t || !t.matches) return;
      if (t.matches("[data-cash]")) {
        const cbox = t.closest(".pgr-cash");
        const cout = cbox && cbox.querySelector(".pgr-hedge-out");
        if (!cout) return;
        const cv = (k) => String((cbox.querySelector(`[data-cash="${k}"]`) || {}).value || "").replace(/[$,\s]/g, "");
        cout.innerHTML = cashOut(cv("stake"), cbox.dataset.pay, cbox.dataset.p, cv("offer"));
        return;
      }
      if (!t.matches("[data-hedge]")) return;
      const box = t.closest(".pgr-hedge");
      const out = box && box.querySelector(".pgr-hedge-out");
      if (!out) return;
      const v = (k) => String((box.querySelector(`[data-hedge="${k}"]`) || {}).value || "").replace(/[$,\s]/g, "").replace("−", "-");
      out.innerHTML = hedgeOut(v("stake"), box.dataset.pay, v("odds"), box.dataset.p, box.dataset.leg);
    });
    document.addEventListener("click", (e) => {
      const btn = e.target && e.target.closest && e.target.closest("[data-save-slip]");
      if (btn) save(btn);
    });
    document.addEventListener("change", (e) => {
      const t = e.target;
      if (t && t.matches && t.matches("[data-lastleg-mail]")) setMail(!!t.checked);
    });
  }

  window.QBSlip = { send, card, shrink, track, hedgeOut, cashOut, slipKey, entryOf, settleOne, lastLeg, lastHTML };
})();
