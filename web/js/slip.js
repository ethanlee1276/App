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
    const where = l.found && l.prob != null ? `${FOUND[l.found] || ""}${l.tier ? ` · ${esc(l.tier)}` : ""}` : "";
    const label = v === "unpriced" && l.found ? "No number of ours" : (VERDICT[v] || v);
    const bar = l.prob != null
      ? `<div class="pgr-bar" aria-hidden="true"><i style="width:${Math.round(l.prob * 100)}%"></i>${
        l.needs != null ? `<u style="left:${Math.round(l.needs * 100)}%"></u>` : ""}</div>` : "";
    return `<li class="pgr-leg v-${esc(v)}">
      <div class="pgr-leg-h"><span class="pgr-n">${i + 1}</span><b>${esc(legName(l))}</b>
        <span class="pgr-pill v-${esc(v)}">${esc(label)}</span></div>
      ${meta.length ? `<div class="pgr-leg-m">${meta.join(" · ")}</div>` : ""}${bar}
      ${where ? `<div class="pgr-leg-w">${where}</div>` : ""}
    </li>`;
  }

  function card(s) {
    if (!s || !Array.isArray(s.legs)) return "";
    const g = String(s.grade || "?");
    const letterCls = g.charAt(0) === "?" ? "na" : g.charAt(0).toLowerCase();
    const head = [`${s.n_legs}-leg parlay`, s.book].filter(Boolean).map(esc).join(" · ");
    const lines = [];
    if (s.ours != null) {
      lines.push(`Our chance it all hits <b>${pct(s.ours)}</b>${s.needs != null ? ` · the payout needs <b>${pct(s.needs)}</b>` : ""}`);
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
      <ol class="pgr-legs">${s.legs.map(legHTML).join("")}</ol>
      ${notes}${swap}
      ${foot.map((f) => `<p class="pgr-foot">${esc(f)}</p>`).join("")}
      <p class="pgr-fine">Read from your screenshot by AI and priced by our models. Not betting advice.
        <span>21+ · 1-800-GAMBLER</span></p>
    </div>`;
  }

  window.QBSlip = { send, card, shrink };
})();
