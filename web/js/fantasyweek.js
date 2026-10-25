/* Qellys Book — this week in fantasy points, drawn on the Fantasy page.
   ==========================================================================
   Ethan, 2026-10-22: "with all this new data added for nfl with how we do
   the offense and defense and game scripts and all the data from our game
   reports. We need to make sure we are using that data correctly for
   fantasy ... make sure we wrap that into it how it should be".

   `fantasy_week.json` (engine/fantasyweek) is every player on the NFL
   board, his week in PPR: the prop board's own projections — the defence
   against his position, the game script, the weather, who is out around
   him — his touchdown chance, and the chance he plays. Paid whole
   (gate.PAID_FILES); app.js fetches it (`ffWeekLoad`) into `_ffWeek`.

   This draws it: the "This week" room, the best pickups on the league
   desk, the week on each lineup row and the line under it, and his week
   in the player panel. The server scores the desk's lineup and
   head-to-head on the same file; this only draws the cards it hands back.

   LOADED ON FIRST USE (app.js loadFantasyWeek), like js/report.js: the
   Fantasy page asks for it, so a first visit anywhere else carries none
   of it. It runs in the page's global scope beside app.js and uses its
   helpers (escapeHtml, escapeAttr, nflName, nflMap, playerAvatar, icon,
   panelEmpty, ffNorm) and `_ffWeek` by name, only when drawing. */
(function () {
  "use strict";

  let wantPos = "ALL";              // the room's position filter
  let showAll = false;              // past the first SHOWN rows

  const SHOWN = 30;

  /* Still this week's? The same rule the server applies (fantasyweek
     .current): its last game is today or later on the Eastern clock,
     turned at 6am. A week whose games are over is not drawn as this one. */
  function current(w) {
    const days = Object.values((w || {}).teams || {})
      .map((t) => String((t || {}).date || "").slice(0, 10)).filter(Boolean).sort();
    if (!days.length) return true;
    let today;
    try {
      today = new Date(new Date().getTime() - 6 * 3600e3)
        .toLocaleDateString("en-CA", { timeZone: "America/New_York" });
    } catch (e) { today = new Date().toISOString().slice(0, 10); }
    return days[days.length - 1] >= today;
  }

  /* "vs Steelers" / "at Steelers": from a board row's game, or a card's
     own `home` flag. */
  function vs(r) {
    const opp = (r || {}).opponent;
    if (!opp) return "";
    const home = r.home != null ? r.home
      : (r.game && r.game.home ? r.game.home === r.team : null);
    return `${home === false ? "at" : "vs"} ${nflName(opp)}`;
  }

  /* Soft or tough only: an average matchup is not news, and a chip on
     every row is a chip nobody reads. */
  function matchChip(m) {
    const word = { soft: "soft matchup", tough: "tough matchup" }[(m || {}).grade];
    if (!word) return "";
    return `<span class="hd-chip ${m.grade === "soft" ? "good" : "bad"}" title="${
      escapeAttr(m.text || "")}">${word}</span>`;
  }

  /* A part of his line the board does not project, in words. */
  const PART = {
    pass_yds: "passing yards", pass_td: "passing touchdowns", pass_int: "interceptions",
    rush_yds: "rushing yards", rec_yds: "receiving yards", receptions: "catches",
    kick_pts: "kicking points", rush_td: "rushing touchdowns", touchdowns: "touchdowns",
  };

  /* A quarterback's scoring chance is a RUSHING touchdown (the touchdown
     model counts rushing and receiving scores; his passing ones are in his
     passing line), and the label says so. */
  function tdLabel(pos) { return pos === "QB" ? "rush TD" : "TD"; }

  /* The chance he plays, when it is not a certainty: a listed player is
     worth that share of his week, and the chip says so. */
  function playChip(r) {
    const p = (r || {}).play;
    if (p == null || p >= 1) return "";
    if (p <= 0) return `<span class="hd-chip bad">${escapeHtml(r.status || "out")}</span>`;
    return `<span class="hd-chip warn" title="${escapeAttr(r.play_source
      ? `From the ${r.play_source}.` : "")}">${escapeHtml(r.status || "listed")} · ${
      Math.round(p * 100)}% to play</span>`;
  }

  /* Why his number is where it is: the chain steps that moved it, then the
     scan's read and a role change. A card (`week_card`) already carries
     these as sentences; a full row carries the parts. */
  function reasons(r, n) {
    if (!r) return [];
    if (Array.isArray(r.why)) return r.why.slice(0, n || 3);
    const out = (r.reasons || []).map((s) => s.why).filter(Boolean);
    if (r.read && r.read.label) out.push(`Matchup scan: ${r.read.label}`);
    const rc = r.role_change;
    if (rc && rc.before != null && rc.after != null) {
      const word = { tgt: "target share", car: "carry share", snap: "snap share" }[rc.share] || "role";
      out.push(`Role change: his ${word} went from ${Math.round(rc.before * 100)}% to ${
        Math.round(rc.after * 100)}% ${rc.games_ago} game${rc.games_ago === 1 ? "" : "s"} ago`);
    }
    return out.slice(0, n || 3);
  }

  function rowHTML(r) {
    const why = reasons(r, 2);
    const where = [r.position, vs(r),
      r.script && r.script.team_implied != null ? `team total ${r.script.team_implied}` : ""]
      .filter(Boolean).join(" · ");
    const more = [
      r.play > 0 && r.play < 1 ? `${Number(r.ppr).toFixed(1)} if he plays` : "",
      r.range ? `8 in 10 weeks ${r.range[0]}–${r.range[1]}` : "",
      r.td_prob != null ? `${tdLabel(r.position)} ${Math.round(r.td_prob * 100)}%` : "",
    ].filter(Boolean).join(" · ");
    return `<div class="hd-row ff-row ffw-row ffrow-door" data-dossier="${escapeAttr(r.player)}"
         role="button" tabindex="0">
      <span class="hd-what"><b>${playerAvatar(r.player, r.team,
        { size: 24, map: nflMap(), headshot: r.headshot })}${escapeHtml(r.player)}${
        matchChip(r.matchup)}${playChip(r)}</b>
        <span>${escapeHtml(where)}</span>
        ${more ? `<span>${escapeHtml(more)}</span>` : ""}
        ${why.length ? `<span class="ffw-why">${why.map(escapeHtml).join(" · ")}</span>` : ""}
        ${(r.filled || []).length ? `<span class="ffw-miss">His ${
          escapeHtml(r.filled.map((k) => PART[k] || k).join(", "))} from his season
          average — the board has no line on ${r.filled.length === 1 ? "it" : "them"}</span>` : ""}
        ${(r.missing || []).length ? `<span class="ffw-miss">No line for his ${
          escapeHtml(r.missing.map((k) => PART[k] || k).join(", "))} — left out,
          not guessed</span>` : ""}</span>
      <span class="hd-state"><b>${Number(r.expected).toFixed(1)}</b>
        <span class="hd-vs">PPR this week</span></span>
    </div>`;
  }

  /* The measurement, in the page's words: what the switch from season
     averages bought, and what it does not count. */
  function measuredHTML(m) {
    const a = ((m || {}).score || {}).ALL;
    if (!a || a.pairs_week == null) return "";
    return `<p class="rank-help">Measured on ${escapeHtml(m.seasons || "past seasons")}, weeks ${
      escapeHtml(m.weeks || "")} (${Number(a.n).toLocaleString()} player-weeks): of every two players
      at a position, this week’s projection had the higher scorer ahead ${(a.pairs_week * 100).toFixed(1)}%
      of the time to the season average’s ${(a.pairs_season * 100).toFixed(1)}%, and missed by
      ${Number(a.mae_week).toFixed(1)} points a week to ${Number(a.mae_season).toFixed(1)}. Byes and
      players ruled out, which only this week reads, are not in those numbers.</p>`;
  }

  function room(w) {
    if (!w) {
      return `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
        <div class="es-title">This week’s projections are not built yet</div>
        <div class="es-sub">They build with the NFL board — every player’s week from the same
          projections the picks use. Back once this week’s board is up.</div></div>`;
    }
    // SEALED WHOLE: a public copy written while the week was paid whole
    // (before 2026-10-25). Since then a reader without a plan gets every
    // row with its workings cut (engine/gate.ROW_PAID_KEYS_BY_FILE).
    if (w.locked_reason && !(w.players || []).length) {
      return `<div class="card ms-locked"><b>Every player’s week in fantasy points</b> — the prop
        board’s projections added up: the defence against his position, the game script, the
        weather, who is out around him, his touchdown chance and the chance he plays, with the
        reasons — is part of the subscription. Your league desk scores your lineup on it too.</div>`;
    }
    if (!current(w)) {
      return `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
        <div class="es-title">Week ${escapeHtml(String(w.week || ""))}’s games are over</div>
        <div class="es-sub">Next week’s projections build with the next NFL board.</div></div>`;
    }
    const all = w.players || [];
    const tabs = ["ALL", "QB", "RB", "WR", "TE", "K"]
      .filter((p) => p === "ALL" || all.some((r) => r.position === p));
    const want = tabs.includes(wantPos) ? wantPos : "ALL";
    const rows = all.filter((r) => want === "ALL" || r.position === want);
    const shown = showAll ? rows : rows.slice(0, SHOWN);
    const byes = w.byes || [];
    return `
      <div class="section-title">Week ${escapeHtml(String(w.week || ""))} in fantasy points
        <span class="sub">— every player on the NFL board, PPR, at the chance he plays</span></div>
      <p class="rank-help">Each line is the prop board’s own projection — the defence against his
        position, the game script, the weather, who is out around him — and his touchdowns are the
        touchdown model’s. A questionable player counts at the chance he plays; tap any name for
        his whole week. Your league desk (Around the league) scores your lineup on these numbers
        under your league’s own scoring.</p>
      ${w.locked && w.locked["players[].fields"] ? `<p class="rank-help">${icon("lock", 12)} Members also see each
        player’s stat line, touchdown chance and game script, and the reasons behind his number —
        <a href="#paywall">the plans</a>.</p>` : ""}
      ${byes.length ? `<p class="rank-help"><b>On a bye:</b> ${byes.map(nflName).map(escapeHtml).join(", ")}</p>` : ""}
      <div class="rec-bf-group ffw-pos" role="group" aria-label="Position">${tabs.map((p) => `
        <button type="button" class="rec-bf${p === want ? " active" : ""}" data-ffwpos="${p}"
          aria-pressed="${p === want ? "true" : "false"}">${p === "ALL" ? "All" : p}</button>`).join("")}</div>
      <div class="card ff-rows ffw-list">${shown.map(rowHTML).join("")
        || panelEmpty("No players at this position on this week’s board.")}</div>
      ${rows.length > shown.length ? `<button type="button" class="btn ghost" data-ffwmore>Show all ${
        rows.length} ${want === "ALL" ? "players" : want}s ▾</button>` : ""}
      ${measuredHTML(w.measured)}`;
  }

  /* The room redraws itself in place: a filter is not a page load. */
  function bind(root) {
    const host = (root || document).querySelector("#ff-week");
    if (!host || host.dataset.bound) return;
    host.dataset.bound = "1";
    host.addEventListener("click", (e) => {
      const pos = e.target.closest && e.target.closest("[data-ffwpos]");
      const more = e.target.closest && e.target.closest("[data-ffwmore]");
      if (!pos && !more) return;
      if (pos) { wantPos = pos.dataset.ffwpos; showAll = false; }
      if (more) showAll = true;
      host.innerHTML = room(_ffWeek);
    });
  }

  /* His line out of this week's file, for the dossier: the row, or that
     his team is on a bye. Null when the week is not built, not readable,
     or over. */
  function rowFor(name, team) {
    const w = _ffWeek;
    if (!w || (w.locked_reason && !(w.players || []).length) || !current(w)) return null;
    const k = ffNorm(name);
    const row = (w.players || []).find((r) => ffNorm(r.player) === k);
    if (row) return row;
    if (team && (w.byes || []).includes(team)) return { bye: true, team };
    return null;
  }

  function dossier(r) {
    if (r.bye) {
      return `<p class="ffd-note">On a bye this week — worth nothing to a lineup until
        ${escapeHtml(nflName(r.team) || "his team")} play again.</p>`;
    }
    const stat = (k, v) => v == null || v === "" ? ""
      : `<span class="ffd-stat"><span class="k">${k}</span><b>${v}</b></span>`;
    const why = reasons(r, 3);
    const listed = r.play > 0 && r.play < 1
      ? ` — ${Number(r.ppr).toFixed(1)} if he plays, and ${Math.round(r.play * 100)}% that he does (${
        escapeHtml(r.status || "listed")}${r.practice ? `, ${escapeHtml(r.practice)} in practice` : ""})`
      : r.play === 0 ? ` — ${escapeHtml(r.status || "ruled out")}, so nothing` : "";
    const stats = stat("8 in 10 weeks", r.range ? `${Number(r.range[0])}–${Number(r.range[1])}` : null)
      + stat(r.position === "QB" ? "Rushing TD" : "TD chance",
             r.td_prob != null ? `${Math.round(r.td_prob * 100)}%` : null)
      + stat("Matchup", ({ soft: "soft", tough: "tough", neutral: "average" })[(r.matchup || {}).grade])
      + stat("Team total", r.script && r.script.team_implied != null ? Number(r.script.team_implied) : null);
    return `<div class="ffcal-p-proj"><b class="ffcal-p-n">${Number(r.expected).toFixed(1)}</b>
        <span class="k">projected PPR this week ${escapeHtml(vs(r))}${listed}</span></div>
      ${stats ? `<div class="ffd-stats">${stats}</div>` : ""}
      ${r.matchup && r.matchup.text ? `<p class="ffd-note">${escapeHtml(r.matchup.text)}.</p>` : ""}
      ${why.length ? `<p class="ffd-note">${why.map(escapeHtml).join(" · ")}</p>` : ""}
      ${(r.filled || []).length ? `<p class="ffd-note">His ${escapeHtml(r.filled.map((k) =>
        PART[k] || k).join(", "))} from his season average: the board has no line on
        ${r.filled.length === 1 ? "it" : "them"} this week.</p>` : ""}`;
  }

  /* The best of this week nobody in the league rosters (the desk's
     `free_agents`, engine/fantasyweek.free_agents): a pickup is this
     week's question too. */
  function pickups(d) {
    const fa = (d || {}).free_agents || {};
    const order = ["QB", "RB", "WR", "TE", "K"].filter((p) => (fa[p] || []).length);
    if (!order.length) return "";
    const row = (r) => {
      const c = r.card || {};
      const why = reasons(c, 1);
      return `<div class="hd-row ff-row ffrow-door" data-dossier="${escapeAttr(r.player)}"
           role="button" tabindex="0">
        <span class="ld-slot">${escapeHtml(r.position || "")}</span>
        <span class="hd-what"><b>${escapeHtml(r.player)}${matchChip(c.matchup)}${playChip(r)}</b>
          <span>${escapeHtml([nflName(r.team), vs(c)].filter(Boolean).join(" · "))}</span>
          ${why.length ? `<span class="ffw-why">${escapeHtml(why[0])}</span>` : ""}</span>
        <span class="hd-state"><b>${Number(r.expected).toFixed(1)}</b>
          <span class="hd-vs">PPR this week</span></span>
      </div>`;
    };
    return `
      <div class="section-title">Best pickups this week
        <span class="sub">— the best of this week’s projections that nobody in your league
        rosters, by position</span></div>
      <div class="card ff-rows">${order.map((p) => fa[p].slice(0, 3).map(row).join("")).join("")}</div>`;
  }

  /* What the desk's lineup was scored on, said once under it. */
  function basis(d) {
    const pw = (d || {}).projection_week || {};
    const b = ((d || {}).lineup || {}).basis || {};
    if (pw.state === "ok") {
      const n = b.season || 0;
      return `<p class="rank-help">Scored on Week ${escapeHtml(String(pw.week || ""))}’s projections —
        the matchup, the game script, the weather and who is out around each player, at the chance
        he plays; a bye or a player ruled out counts as zero.${n ? ` ${n} starter${n === 1 ? " is" : "s are"}
        on ${n === 1 ? "his" : "their"} season average: this week’s board does not carry ${n === 1 ? "him" : "them"}.` : ""}
        Trades stay on season averages — a trade is the rest of the season’s question.</p>`;
    }
    if (!pw.note) return "";
    return `<p class="rank-help">${pw.locked ? `${icon("lock", 12)} ` : ""}${escapeHtml(pw.note)}</p>`;
  }

  /* A starter's week, as the lineup row shows it: chips on his name, the
     game under it, and the biggest reason. */
  function seat(wk) {
    if (!wk || wk.season_average) return { chips: "", vs: "", why: "" };
    if (wk.bye) return { chips: `<span class="hd-chip bad">bye</span>`, vs: "on a bye", why: "" };
    if (wk.play === 0 && wk.status) {
      return { chips: `<span class="hd-chip bad">${escapeHtml(wk.status)}</span>`, vs: "", why: "" };
    }
    const why = reasons(wk, 1);
    return { chips: matchChip(wk.matchup) + playChip(wk), vs: vs(wk),
             why: why.length ? why[0] : "" };
  }

  /* Under the head-to-head's score: what both lineups were scored on. */
  function h2hNote(h, d) {
    if (h.basis === "week") {
      return `<p class="rank-help">Both lineups scored on this week’s projections: the matchups,
        the game scripts, who is out, and a bye or an Out at zero.</p>`;
    }
    const pw = (d || {}).projection_week || {};
    return pw.state === "ok" ? `<p class="rank-help">Scored on season averages: this week’s
      projections are for Week ${escapeHtml(String(pw.week || ""))}, not this game’s week.</p>` : "";
  }

  /* Under the dossier's start/sit call, when the desk scored it on the week. */
  function callNote() {
    return `<p class="ffd-note">The call is scored under your league’s own scoring and slots on
      this week’s projection, at the chance he plays — the same week as above, not his season
      average.</p>`;
  }

  window.QBWeek = { room, bind, rowFor, dossier, pickups, basis, seat, current, h2hNote, callNote };
})();
