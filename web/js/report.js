/* Qellys Book — the game report, drawn on the game page.
   ==========================================================================
   Ethan, 2026-10-19: "I want a full layed out detailed explanation for
   every nfl game just like how the report is. Obv keep out the prop picks
   but everything else it valuable information too have typed out so the
   user can just read it."

   engine/gamereport writes the report from what the board holds and this
   draws it block by block: paragraphs, headings, lists, tables, notes, and
   the players in the scan's own card shape. Each player opens his player
   page. Since 2026-11-14 the report also carries each game's parlays
   (engine/gameparlays; Ethan: "for each game ... make 4 3-leg parlays ...
   and 3 2-leg touchdown parlays"), the one place it names a price: every
   leg is a pick the board already posts, and the ticket says the price to
   take it at.

   LOADED ON FIRST USE (app.js loadReport), like js/extras.js and
   js/slip.js: the first game page with a report asks for it, so the
   site's first paint carries none of it. It runs in the page's global
   scope beside app.js and uses its helpers (escapeHtml, escapeAttr,
   slugify, teamName, playerAvatar) by name, only when drawing. */
(function () {
  "use strict";

  const TONE = { favorable: "up", unfavorable: "down", up: "up", down: "down" };

  /* What a league's report holds, for the reader without the paid key
     (engine/gamereport, engine/leaguereport). */
  const HOOPS = "the line and what it means, rest and travel, who carries each team, where each " +
    "defence gives, the injury report and what to check before tip-off";
  const HOLDS = {
    nfl: "the line and what it means, how the units rank, how each team plays, who is out and what it " +
      "opens, who’s guarding who, the trenches, the red zone, coaching and the schedule, how the game " +
      "could go and the players to watch",
    mlb: "the line and what it means, the pitching matchup, how each lineup hits tonight’s hand, the pens, " +
      "the park, the weather and the umpire, and the hitters set up to shine or struggle",
    nhl: "the line and what it means, the tale of the tape, the goalies, the injury report, and the " +
      "skaters set up to shine or struggle",
    nba: HOOPS, wnba: HOOPS, cbb: HOOPS,
  };
  HOLDS.cfb = HOLDS.nfl;

  /* His season, his last games, a trend and his red-zone work
     (engine/gamereport.form_lines): [[label, [lines]]]. */
  function form(rows) {
    if (!(rows || []).length) return "";
    return `<dl class="gr-form">${rows.map(([k, lines]) => `<div class="gr-form-row"><dt>${escapeHtml(k)}</dt>
      <dd>${(lines || []).map((l) => `<span>${escapeHtml(l)}</span>`).join("")}</dd></div>`).join("")}</dl>`;
  }

  function block(b) {
    if (!b || !b.type) return "";
    if (b.type === "p") return `<p class="gr-p">${escapeHtml(b.text)}</p>`;
    if (b.type === "h") return `<h4 class="gr-h">${escapeHtml(b.text)}</h4>`;
    if (b.type === "note") return `<p class="gr-note">${escapeHtml(b.text)}</p>`;
    if (b.type === "list") {
      return `<ul class="gr-list">${(b.items || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`;
    }
    if (b.type === "table") {
      const head = b.head || [];
      return `<div class="gr-table-wrap">${b.title ? `<div class="gr-table-title">${escapeHtml(b.title)}</div>` : ""}
        <table class="agate gr-table"><thead><tr>${head.map((h, i) =>
          `<th${i ? ' class="num"' : ""}>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${(b.rows || []).map((r) => `<tr>${r.map((c, i) =>
          `<td${i ? ' class="num"' : ""}>${escapeHtml(String(c))}</td>`).join("")}</tr>`).join("")}</tbody></table>
        ${b.note ? `<p class="gr-note">${escapeHtml(b.note)}</p>` : ""}</div>`;
    }
    if (b.type === "verdicts" || b.type === "players") {
      return `<div class="gr-people">${(b.items || []).map((v) => {
        const tone = TONE[v.verdict || v.tone] || "";
        const door = v.player ? ` data-open="player:${escapeAttr(slugify(v.player))}"` : "";
        const who = [v.team ? teamName(v.team) : "", v.pos, v.role].filter(Boolean).join(" · ");
        return `<div class="gr-person ${tone}"${door}>
          <div class="gr-person-head">${playerAvatar(v.player, v.team, { size: 36, headshot: v.headshot })}
            <span class="gr-person-who"><b>${escapeHtml(b.type === "verdicts" ? v.title : v.player)}</b>
              <span>${escapeHtml(who)}</span></span>
            ${v.label ? `<span class="ms-read-tag ${tone}">${escapeHtml(v.label)}</span>` : ""}
            ${v.status ? `<span class="ms-read-tag gr-status">${escapeHtml(v.status)}</span>` : ""}</div>
          ${b.type === "verdicts"
            ? ((v.why || []).length ? `<ul class="gr-why">${v.why.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>` : "")
            : v.text ? `<p class="gr-person-text">${escapeHtml(v.text)}</p>` : ""}
          ${v.pick ? `<p class="gr-person-pick">${escapeHtml(v.pick)}</p>` : ""}
          ${form(v.form)}
        </div>`;
      }).join("")}</div>`;
    }
    /* EACH GAME'S PARLAYS (engine/gameparlays, 2026-11-14): four three-leg
       tickets and three scorer pairs, each leg with its price, our chance
       and why, the script the ticket needs, its backups and caveats. */
    if (b.type === "parlays") {
      const items = (xs) => (xs || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
      return `<div class="gr-parlays">${(b.items || []).map((t) => `<div class="gr-parlay">
        <div class="gr-parlay-head"><b>${escapeHtml(t.title || "")}</b></div>
        ${t.price_line ? `<p class="gr-parlay-price">${escapeHtml(t.price_line)}</p>` : ""}
        <ol class="gr-parlay-legs">${(t.legs || []).map((l) => `<li${l.player
          ? ` data-open="player:${escapeAttr(slugify(l.player))}"` : ""}>
          <span class="gr-parlay-pick"><b>${escapeHtml(l.pick || "")}</b>${l.price
            ? ` <span class="gr-parlay-px">${escapeHtml(l.price)}</span>` : ""}${l.chance
            ? ` <span class="gr-parlay-p">${Math.round(Number(l.chance) * 100)}%</span>` : ""}${l.research != null
            ? ` <span class="gr-parlay-r" title="Our research case: his team’s expected points, the defence he faces, his usage and red-zone work, the matchup read and the game script">research ${escapeHtml(String(l.research))} of ${escapeHtml(String(l.research_of || 13))}</span>` : ""}</span>
          ${(l.why || []).length ? `<ul class="gr-why">${items(l.why)}</ul>` : ""}</li>`).join("")}</ol>
        ${t.script ? `<p class="gr-parlay-script">${escapeHtml(t.script)}</p>` : ""}
        ${(t.links || []).length ? `<ul class="gr-list gr-parlay-links">${items(t.links)}</ul>` : ""}
        ${(t.backups || []).length ? `<div class="gr-parlay-sub">Backups</div><ul class="gr-list">${items(t.backups)}</ul>` : ""}
        ${(t.caveats || []).length ? `<div class="gr-parlay-sub">Caveats</div><ul class="gr-list">${items(t.caveats)}</ul>` : ""}
      </div>`).join("")}</div>`;
    }
    return "";
  }

  /* THE REPORT AS PLAIN TEXT — what "Copy the report" puts on the
     clipboard, in the page's reading order (engine/gamereport.to_text is
     the box's copy of the same walk). Tables go row by row with dots
     between the cells: a message app's font is not monospaced, so padded
     columns would not line up anyway. */
  function toText(r, url) {
    const out = [r.title + (r.when ? ` — ${r.when}` : ""), "The Qellys Book game report"];
    for (const s of r.sections || []) {
      out.push("", String(s.title || "").toUpperCase());
      for (const b of s.blocks || []) {
        if (!b || !b.type) continue;
        if (b.type === "p" || b.type === "note") out.push(b.text);
        else if (b.type === "h") out.push("", b.text);
        else if (b.type === "list") (b.items || []).forEach((t) => out.push(`• ${t}`));
        else if (b.type === "table") {
          if (b.title) out.push(b.title);
          [b.head || [], ...(b.rows || [])].forEach((row) => out.push(row.join("  ·  ")));
          if (b.note) out.push(`(${b.note})`);
        } else if (b.type === "verdicts" || b.type === "players") {
          for (const v of b.items || []) {
            const who = [v.team, v.pos].filter(Boolean).join(" ");
            out.push(b.type === "verdicts"
              ? `• ${v.title} — ${v.label}${v.role ? ` (${v.role})` : ""}`
              : `• ${v.player}${who ? ` (${who})` : ""}${v.label ? ` — ${v.label}` : ""}${v.status ? ` (${v.status})` : ""}${v.text ? `: ${v.text}` : ""}`);
            (v.why || []).forEach((w) => out.push(`    – ${w}`));
            if (v.pick) out.push(`    ${v.pick}`);
            (v.form || []).forEach(([k, lines]) => out.push(`    ${k}: ${(lines || []).join(" | ")}`));
          }
        } else if (b.type === "parlays") {
          for (const t of b.items || []) {
            out.push(`• ${t.title}: ${t.price_line || ""}`);
            for (const l of t.legs || []) {
              out.push(`    – ${l.pick}${l.price ? ` (${l.price})` : ""}${l.chance ? `, ${Math.round(Number(l.chance) * 100)}%` : ""}${
                l.research != null ? `, research ${l.research} of ${l.research_of || 13}` : ""}`);
              (l.why || []).forEach((w) => out.push(`        · ${w}`));
            }
            if (t.script) out.push(`    ${t.script}`);
            (t.backups || []).forEach((x) => out.push(`    Backup: ${x}`));
            (t.caveats || []).forEach((x) => out.push(`    Caveat: ${x}`));
          }
        }
      }
    }
    if (url) out.push("", url);
    return out.join("\n");
  }

  /* WHAT SHARE SENDS: the game, its kickoff and its line, and the link —
     the public facts and nothing of the report. Whoever it is forwarded
     to reads the share text before anybody has paid for anything (the
     same rule as app.js pickSlug). */
  function teaser(r) {
    return [r.title + (r.when ? ` — ${r.when}` : ""), r.line ? r.line[0].toUpperCase() + r.line.slice(1) : "",
            "Our full game report is on Qellys Book."].filter(Boolean).join(". ").replace(/\.\./g, ".");
  }

  function said(btn, msg) {
    const was = btn.textContent;
    btn.textContent = msg;
    setTimeout(() => { btn.textContent = was; }, 1600);
  }

  /* The clipboard first, on a phone too: "Copy" that opens a share sheet
     is not what the button says. Where there is no clipboard (an insecure
     context, an app without the permission) the share sheet is the way
     out; where there is neither, the button says so. */
  async function copy(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      said(btn, "Copied");
      return;
    } catch (e) { /* no clipboard here */ }
    if (navigator.share) {
      try { await navigator.share({ text }); } catch (e) { /* dismissed */ }
      return;
    }
    said(btn, "Copy didn’t work");
  }

  async function share(r, url, btn) {
    const text = teaser(r);
    if (navigator.share) {
      try { await navigator.share({ title: r.title, text, url }); } catch (e) { /* dismissed */ }
      return;
    }
    copy(url ? `${text}\n${url}` : text, btn);
  }

  /* The reports drawn this visit, by game, for the two buttons. */
  const shown = new Map();
  if (typeof document !== "undefined") {
    document.addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("[data-gr-copy], [data-gr-share]");
      if (!b) return;
      const hit = shown.get(b.dataset.grCopy || b.dataset.grShare);
      if (!hit) return;
      e.preventDefault();
      if (b.dataset.grCopy) copy(toText(hit.r, hit.url), b);
      else share(hit.r, hit.url, b);
    });
  }

  /* The report (r), or — for a reader without the paid key — what it
     holds. */
  function html(r, extras) {
    const head = `<div class="section-title">The game report
      <span class="sub">— ${r ? `about ${r.minutes} min to read · ` : ""}the whole game written out from
      tonight’s board; no prop picks in it</span></div>`;
    if (!r) {
      const holds = HOLDS[(extras && extras.sport) || ""] || HOLDS.nfl;
      return `<div id="gp-sec-report" class="gr">${head}<div class="card ms-locked"><b>The game report</b> —
        this game written out top to bottom: ${holds} — is part of the subscription.</div></div>`;
    }
    const secs = (r.sections || []).filter((s) => s && (s.blocks || []).length);
    const toc = secs.length > 2 ? `<nav class="std-chips gr-toc" aria-label="Sections of the report">${
      secs.map((s) => `<button type="button" class="chip" data-jump="gr-${escapeAttr(s.key)}">${
        escapeHtml(s.title)}</button>`).join("")}</nav>` : "";
    const body = secs.map((s) => {
      let blocks = s.blocks || [];
      let extra = "";
      // The simulation card draws the same simulated games the report's
      // table lists, as a gauge and a histogram; with it here the table
      // steps aside.
      if (s.key === "scripts" && extras && extras.scripts) {
        blocks = blocks.filter((b) => b.type !== "table");
        extra = `<div class="gr-extra">${extras.scripts}</div>`;
      }
      return `<section class="gr-sec" id="gr-${escapeAttr(s.key)}"><h3 class="gr-title">${escapeHtml(s.title)}</h3>
        ${blocks.map(block).join("")}${extra}</section>`;
    }).join("");
    const url = (extras && extras.url) || "";
    shown.set(r.game, { r, url });
    const tools = `<div class="gr-tools">
      <button type="button" class="btn ghost" data-gr-copy="${escapeAttr(r.game)}">Copy the report</button>
      <button type="button" class="btn ghost" data-gr-share="${escapeAttr(r.game)}">Share this game</button></div>`;
    return `<div id="gp-sec-report" class="gr">${head}${tools}${toc}<div class="card gr-card">${body}</div></div>`;
  }

  /* EACH GAME'S PARLAYS ON THE PARLAYS PAGE (app.js fillGameParlays): the
     board's tickets (engine/gameparlays) as the report's own cards — the
     words engine/gameparlays.card writes for the report, here in the page. */
  const SCORE = { anytime_td: "to score a touchdown", anytime_goal: "to score a goal", goals: "to score a goal" };
  function pickWords(l) {
    const m = String(l.market || "");
    if (SCORE[m]) return `${l.player} ${SCORE[m]}`;
    const line = l.line == null ? "" : ` ${l.line}`;
    return `${l.player || ""} ${String(l.side || "").toLowerCase()}${line} ${
      String(l.market_label || m.replace(/_/g, " ")).toLowerCase()}`.replace(/\s+/g, " ").trim();
  }
  function oddsWords(o) {
    const n = Number(o);
    return Number.isFinite(n) && n ? (n > 0 ? `+${n}` : String(n)) : "";
  }
  function card(t, n, kind, sport) {
    const pct = (x) => `${Math.round(Number(x || 0) * 100)}%`;
    const title = kind === "three" ? `Parlay ${n}`
      : `${["nfl", "cfb"].includes(sport) ? "Touchdown" : "Scorer"} pair ${n}`;
    let price = `${pct(t.joint)} by our numbers (${pct(t.independent)} if the legs were unrelated) · fair ${
      t.fair_words || ""} · take it at ${t.take_words || ""} or better`;
    if (t.naive_words) price += ` · the legs’ own prices multiplied pay ${t.naive_words}, and a book’s same-game price pays less`;
    const script = t.script ? `What it needs: ${t.script}${t.script_chance != null
      ? ` — about ${pct(t.script_chance)} likely by the lines` : ""}` : "";
    return {
      title, price_line: price, script, links: t.links || [], caveats: t.caveats || [],
      legs: (t.legs || []).map((l) => ({ pick: pickWords(l), player: l.player,
        price: [oddsWords(l.odds), l.book || ""].filter(Boolean).join(" "), chance: l.p, why: l.why || [],
        research: l.research, research_of: l.research_of })),
      backups: (t.backups || []).map((b) => `If ${b.for} is out or his number moves: ${pickWords(b.leg || {})} (${
        oddsWords((b.leg || {}).odds)}, ${pct((b.leg || {}).p)})`),
    };
  }
  function gameParlays(gp, sport) {
    const games = (gp && gp.games) || [];
    if (!games.length) return "";
    const pair = ["nfl", "cfb"].includes(sport) ? "touchdown" : sport === "nhl" ? "goal-scorer" : "scorer";
    return `<div class="section-title">Each game’s parlays <span class="sub">— four three-leg tickets and three ${pair}
        pairs a game, from our own picks; every one tracked on the Record page, none staked</span></div>
      <div class="mini tl-rec" data-gp-rec="1"></div>
      ${gp.note ? `<p class="set-note tl-rule">${escapeHtml(gp.note)}</p>` : ""}
      ${games.map((g) => `<details class="gs-game gr-parlay-game"><summary><span class="gs-game-k">${
        escapeHtml(teamName(g.away))} @ ${escapeHtml(teamName(g.home))}</span>
        <span class="gs-game-n">${(g.threes || []).length} three-leg · ${(g.scorers || []).length} pairs</span></summary>
        ${(g.threes || []).length ? block({ type: "parlays", items: g.threes.map((t, i) => card(t, i + 1, "three", sport)) })
          : `<p class="gr-note">${escapeHtml(g.threes_note || "No three-leg ticket without a conflict in this game.")}</p>`}
        ${(g.scorers || []).length ? block({ type: "parlays", items: g.scorers.map((t, i) => card(t, i + 1, "scorers", sport)) })
          : (g.scorers_note ? `<p class="gr-note">${escapeHtml(g.scorers_note)}</p>` : "")}
      </details>`).join("")}`;
  }
  /* Their record so far (record.json two_leg.game, engine/parlayledger
     .report_game_parlays). */
  function gameParlaysRecord(rec) {
    const g = ((rec || {}).two_leg || {}).game || {};
    const bits = [["three", "three-leg"], ["scorers", "pairs"]].map(([k, w]) => {
      const x = g[k] || {};
      if (!x.graded) return x.open ? `${w}: ${x.open} open, none graded yet` : "";
      return `${w}: ${x.wins} of ${x.graded} hit, ${x.net_units >= 0 ? "+" : ""}${x.net_units} units at the take-it price`;
    }).filter(Boolean);
    return bits.length ? `Our record so far — ${bits.join(" · ")}` : "";
  }

  window.QBReport = { html, block, toText, teaser, gameParlays, gameParlaysRecord };
})();
