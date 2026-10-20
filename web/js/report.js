/* Qellys Book — the game report, drawn on the game page.
   ==========================================================================
   Ethan, 2026-10-19: "I want a full layed out detailed explanation for
   every nfl game just like how the report is. Obv keep out the prop picks
   but everything else it valuable information too have typed out so the
   user can just read it."

   engine/gamereport writes the report from what the board holds — no line,
   price or probability on a player anywhere in it — and this draws it block
   by block: paragraphs, headings, lists, tables, notes, and the players in
   the scan's own card shape. Each player opens his player page; the report
   points at a player, never at a bet.

   LOADED ON FIRST USE (app.js loadReport), like js/extras.js and
   js/slip.js: the first game page with a report asks for it, so the
   site's first paint carries none of it. It runs in the page's global
   scope beside app.js and uses its helpers (escapeHtml, escapeAttr,
   slugify, teamName, playerAvatar) by name, only when drawing. */
(function () {
  "use strict";

  const TONE = { favorable: "up", unfavorable: "down", up: "up", down: "down" };

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
            ${v.label ? `<span class="ms-read-tag ${tone}">${escapeHtml(v.label)}</span>` : ""}</div>
          ${b.type === "verdicts"
            ? ((v.why || []).length ? `<ul class="gr-why">${v.why.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>` : "")
            : v.text ? `<p class="gr-person-text">${escapeHtml(v.text)}</p>` : ""}
          ${form(v.form)}
        </div>`;
      }).join("")}</div>`;
    }
    return "";
  }

  /* The report (r), or — for a reader without the paid key — what it
     holds. */
  function html(r, extras) {
    const head = `<div class="section-title">The game report
      <span class="sub">— ${r ? `about ${r.minutes} min to read · ` : ""}the whole game written out from
      tonight’s board; no prop picks in it</span></div>`;
    if (!r) {
      return `<div id="gp-sec-report" class="gr">${head}<div class="card ms-locked"><b>The game report</b> —
        this game written out top to bottom: the line and what it means, how the units rank, how each team
        plays, who is out and what it opens, who’s guarding who, the trenches, the red zone, coaching and the
        schedule, how the game could go and the players to watch — is part of the subscription.</div></div>`;
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
    return `<div id="gp-sec-report" class="gr">${head}${toc}<div class="card gr-card">${body}</div></div>`;
  }

  window.QBReport = { html, block };
})();
