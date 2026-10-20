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
              : `• ${v.player}${who ? ` (${who})` : ""}${v.label ? ` — ${v.label}` : ""}${v.text ? `: ${v.text}` : ""}`);
            (v.why || []).forEach((w) => out.push(`    – ${w}`));
            (v.form || []).forEach(([k, lines]) => out.push(`    ${k}: ${(lines || []).join(" | ")}`));
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
    const url = (extras && extras.url) || "";
    shown.set(r.game, { r, url });
    const tools = `<div class="gr-tools">
      <button type="button" class="btn ghost" data-gr-copy="${escapeAttr(r.game)}">Copy the report</button>
      <button type="button" class="btn ghost" data-gr-share="${escapeAttr(r.game)}">Share this game</button></div>`;
    return `<div id="gp-sec-report" class="gr">${head}${tools}${toc}<div class="card gr-card">${body}</div></div>`;
  }

  window.QBReport = { html, block, toText, teaser };
})();
