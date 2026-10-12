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

  const MARKET = {
    pass_yds: "Pass Yds", pass_td: "Pass TDs", pass_att: "Pass Attempts", pass_cmp: "Completions",
    pass_int: "Interceptions", rush_yds: "Rush Yds", rush_att: "Carries", rec_yds: "Rec Yds",
    receptions: "Receptions", rush_rec_yds: "Rush + Rec Yds", pass_rush_yds: "Pass + Rush Yds",
    kick_pts: "Kicking Pts", fg_made: "FGs Made", tackles_ast: "Tackles + Ast",
    pts: "Points", reb: "Rebounds", ast: "Assists", pra: "Pts + Reb + Ast", fg3m: "Threes",
    hits: "Hits", total_bases: "Total Bases", home_runs: "Home Runs", strikeouts: "Strikeouts",
    outs: "Outs", sog: "Shots on Goal", points: "Points", goals: "Goals", assists: "Assists",
    blocks: "Blocks", saves: "Saves",
  };
  const VERDICT = { strong: "Strong", fair: "Fair", weak: "Weak", against: "Against", unpriced: "Not on our board" };
  const FOUND = { likely: "On our Most Likely board", prop: "Our projection", scorer: "Our scorer model",
    game: "Our game line" };

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
      ${liveHTML(l)}${priceHTML(l)}
      ${where ? `<div class="pgr-leg-w">${where}</div>` : ""}${whyHTML(l)}
    </li>`;
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
    return `<div class="pgr-live">${tag} ${bits.join(" · ")}</div>${prog}`;
  }

  /* The facts behind the leg's number, from the board itself
     (engine/slipgrade.why): the projection and its range, how often he has
     cleared this number, the defence, the steps that moved the number, the
     game script, the scan's read, anything to watch and the books' price.
     Folded, so a twelve-leg ticket is still a list. */
  function whyHTML(l) {
    const facts = Array.isArray(l.why) ? l.why : [];
    if (!facts.length) return "";
    return `<details class="pgr-why"><summary>Why we say ${esc(pct(l.prob))}</summary><dl>${
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
      ? ` · our chance for the rest <b>${pct(n.chance)}</b>` : n.live ? " · we don’t put a number on a prop mid-game" : ""}</div>`;
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
      n.kind === "kill" ? "These can’t both win" : "One bet sold twice"}:</b> ${esc((n.legs || []).join(" + "))}${
      n.why ? ` — ${esc(n.why)}` : ""}</div>`).join("");
    const sw = s.swap;
    const swap = s.weakest ? `<div class="pgr-swap"><b>Weakest leg:</b> ${esc(s.weakest)}.${sw ? ` Our likeliest pick in that game: <b>${
      esc(sw.player)} ${esc(String(sw.side || "").toLowerCase())} ${esc(num(sw.line))} ${esc(MARKET[sw.market] || sw.market)}</b> — ${
      pct(sw.prob)}${sw.odds ? ` at ${esc(price(sw.odds))}` : ""}.` : ""}</div>` : "";
    return `<div class="pgr-card">
      <div class="pgr-top"><div class="pgr-grade g-${letterCls}" aria-label="Grade ${esc(g)}">${esc(g.replace("*", ""))}${
        g.indexOf("*") >= 0 ? "<sup>*</sup>" : ""}</div>
        <div class="pgr-sum"><b>${head}</b>${lines.map((x) => `<span>${x}</span>`).join("")}</div></div>
      ${nowHTML(s.now)}${alertsHTML(s.alerts)}${shopHTML(s.shop)}${betterHTML(s.better)}
      ${simHTML(s.sim, s.n_legs)}
      <ol class="pgr-legs">${s.legs.map(legHTML).join("")}</ol>
      ${pairsHTML(s.pairs)}${notes}${swap}
      ${foot.map((f) => `<p class="pgr-foot">${esc(f)}</p>`).join("")}
      <p class="pgr-fine">Read from your screenshot by AI and priced by our models. Not betting advice.
        <span>21+ · 1-800-GAMBLER</span></p>
    </div>`;
  }

  window.QBSlip = { send, card, shrink };
})();
