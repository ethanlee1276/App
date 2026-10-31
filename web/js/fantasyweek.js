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
    return days[days.length - 1] >= slateDay();
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

  /* A POSITION'S COLOUR (2026-10-27, the visual pass; Ethan: "look at how
     other fantasy apps ... look visually"). Every fantasy app wears the
     positions in colours, one badge a row, the same hue in every room. */
  function posBadge(pos) {
    const p = String(pos || "").toUpperCase();
    if (!p) return "";
    const dst = p === "DEF" || p === "DST" || p === "D/ST";
    return `<span class="ffpos ffpos-${dst ? "dst" : escapeAttr(p.toLowerCase().replace(/[^a-z]/g, ""))}">${
      escapeHtml(dst ? "D/ST" : p)}</span>`;
  }

  /* Kickoff: the week file's Eastern date and clock as an instant, drawn
     in the reader's own zone (tzTime) with the weekday. */
  function kickoff(g) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String((g || {}).date || ""));
    const k = /^(\d{1,2}):(\d{2})/.exec(String((g || {}).kickoff || ""));
    if (!m || !k) return "";
    let t = Date.UTC(+m[1], +m[2] - 1, +m[3], +k[1] + 5, +k[2]);           // as if Eastern standard time
    try {
      const h = Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric",
                                                          hourCycle: "h23" }).format(new Date(t)));
      if (h !== +k[1]) t -= 3600e3;                                       // daylight time: an hour earlier
    } catch (e) { /* the standard-time guess stands */ }
    return typeof tzTime === "function" ? tzTime(t, { weekday: "short", hour: "numeric", minute: "2-digit" }) : "";
  }

  /* EIGHT WEEKS IN TEN, DRAWN: the floor-to-ceiling span on one scale for
     the whole list (`top`), his number a mark on it. The words stay the
     bar's title and label. */
  function rangeBar(r, top) {
    const rg = r && r.range;
    if (!rg || !(top > 0)) return "";
    const at = (v) => `${Math.max(0, Math.min(100, (Number(v) / top) * 100)).toFixed(1)}%`;
    const words = `8 in 10 weeks ${rg[0]}–${rg[1]}`;
    return `<span class="ffr-range" title="${escapeAttr(words)}" aria-label="${escapeAttr(words)}">
      <span class="ffr-end">${escapeHtml(String(rg[0]))}</span>
      <span class="ffr-track"><i style="left:${at(rg[0])};width:${at(rg[1] - rg[0])}"></i><b style="left:${
        at(r.expected)}"></b></span>
      <span class="ffr-end">${escapeHtml(String(rg[1]))}</span></span>`;
  }

  /* The scale a list's bars share: its highest ceiling, to the next five. */
  function rangeTop(rows) {
    const hi = Math.max(20, ...(rows || []).map((r) => Number(((r || {}).range || [])[1]) || Number((r || {}).expected) || 0));
    return Math.ceil(hi / 5) * 5;
  }

  /* A part of his number from his season average, or none at all: one
     mark on the number, the words in its title and on his panel. */
  function partMark(r) {
    const said = [];
    if ((r.filled || []).length) said.push(`His ${r.filled.map((k) => PART[k] || k).join(", ")} from his season average`);
    if ((r.missing || []).length) said.push(`no line for his ${r.missing.map((k) => PART[k] || k).join(", ")}, left out`);
    return said.length ? `<sup class="ffr-part" title="${escapeAttr(said.join("; "))}">•</sup>` : "";
  }

  /* A TEAM DEFENSE (engine/dstproj): its club's mark, its opponent's
     implied points, and its expected sacks and takeaways for a member. Not a
     player, so not a door to a player's panel. */
  function defRowHTML(r, top) {
    const why = reasons(r, 1);
    const d = r.dst || {};
    const meta = [vs(r), kickoff(r.game || {}), (r.matchup || {}).text || ""].filter(Boolean).join(" · ");
    const more = d.sack != null ? `${Number(d.sack).toFixed(1)} sacks, ${
      (Number(d.int || 0) + Number(d.fum_rec || 0)).toFixed(1)} takeaways expected` : "";
    return `<div class="ffr ffw-def">
      <span class="ffr-face">${teamMark(r.team, 40, nflMap(), "nfl")}</span>
      <span class="ffr-main">
        <span class="ffr-name"><b>${escapeHtml(r.player)}</b>${matchChip(r.matchup)}</span>
        <span class="ffr-meta">${posBadge("DEF")}<span>${escapeHtml(meta)}</span></span>
        ${more || why.length ? `<span class="ffr-why">${escapeHtml([more, why[0]].filter(Boolean).join(" · "))}</span>` : ""}
      </span>
      ${rangeBar(r, top)}
      <span class="ffr-pts"><b>${Number(r.expected).toFixed(1)}</b><span>points</span></span>
    </div>`;
  }

  function rowHTML(r, top) {
    if (r.position === "DEF") return defRowHTML(r, top);
    const why = reasons(r, 1);
    const meta = [vs(r), kickoff(r.game || {}),
      r.script && r.script.team_implied != null ? `team total ${r.script.team_implied}` : ""]
      .filter(Boolean).join(" · ");
    const td = r.td_prob != null ? `<span class="hd-chip">${tdLabel(r.position)} ${Math.round(r.td_prob * 100)}%</span>` : "";
    const maybe = r.play > 0 && r.play < 1;
    return `<div class="ffr ffw-row ffrow-door" data-dossier="${escapeAttr(r.player)}" role="button" tabindex="0">
      <span class="ffr-face">${playerAvatar(r.player, r.team, { size: 40, map: nflMap(), headshot: r.headshot })}</span>
      <span class="ffr-main">
        <span class="ffr-name"><b>${escapeHtml(r.player)}</b>${matchChip(r.matchup)}${playChip(r)}${td}</span>
        <span class="ffr-meta">${posBadge(r.position)}${teamMark(r.team, 14, nflMap(), "nfl")}<span>${escapeHtml(meta)}</span></span>
        ${why.length ? `<span class="ffr-why">${escapeHtml(why[0])}</span>` : ""}
      </span>
      ${rangeBar(r, top)}
      <span class="ffr-pts"><b>${Number(r.expected).toFixed(1)}${partMark(r)}</b><span>${
        maybe ? `${Number(r.ppr).toFixed(1)} if he plays` : "PPR"}</span></span>
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
    const tabs = ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"]
      .filter((p) => p === "ALL" || all.some((r) => r.position === p));
    const want = tabs.includes(wantPos) ? wantPos : "ALL";
    const rows = all.filter((r) => want === "ALL" || r.position === want);
    const shown = showAll ? rows : rows.slice(0, SHOWN);
    const top = rangeTop(shown);
    const parts = shown.some((r) => (r.filled || []).length || (r.missing || []).length);
    // The byes are on the room's own first line (fantasy.js ffStripHTML);
    // how the numbers are built folds under the list, where a reader who
    // wants it looks, rather than standing between the reader and them.
    return `
      <div class="section-title">Week ${escapeHtml(String(w.week || ""))} in fantasy points
        <span class="sub">— every player on the NFL board, PPR, at the chance he plays</span></div>
      ${w.locked && w.locked["players[].fields"] ? `<p class="rank-help">${icon("lock", 12)} Members also see each
        player’s stat line, touchdown chance and game script, and the reasons behind his number —
        <a href="#paywall">the plans</a>.</p>` : ""}
      ${compareHTML(w)}
      <div class="ffr-bar">
        <div class="rec-bf-group ffw-pos" role="group" aria-label="Position">${tabs.map((p) => `
          <button type="button" class="rec-bf${p === want ? " active" : ""}" data-ffwpos="${p}"
            aria-pressed="${p === want ? "true" : "false"}">${p === "ALL" ? "All" : p === "DEF" ? "D/ST" : p}</button>`).join("")}</div>
        <span class="ffr-scale">Bars: 8 weeks in 10, on one 0–${top} scale</span>
      </div>
      <div class="card ffw-list ffr-list">${shown.map((r) => rowHTML(r, top)).join("")
        || panelEmpty("No players at this position on this week’s board.")}</div>
      ${rows.length > shown.length ? `<button type="button" class="btn ghost" data-ffwmore>Show all ${
        rows.length} ${want === "ALL" ? "players" : want === "DEF" ? "defense" : want}s ▾</button>` : ""}
      ${parts ? `<p class="ffr-key"><sup class="ffr-part">•</sup> Part of the number is his season average: the
        board has no line on it. Tap the name for which part.</p>` : ""}
      <details class="ffr-how"><summary>How these numbers are built</summary>
        <p class="rank-help">Each line is the prop board’s own projection — the defence against his
          position, the game script, the weather, who is out around him — and his touchdowns are the
          touchdown model’s. A questionable player counts at the chance he plays; tap any name for
          his whole week. Your league desk (My team) scores your lineup on these numbers under your
          league’s own scoring.</p>
        ${byesNote(w)}${measuredHTML(w.measured)}
      </details>`;
  }

  /* The byes, said once more inside the fold for a reader who opened the
     room by itself (the strip above says them first). */
  function byesNote(w) {
    const byes = (w || {}).byes || [];
    return byes.length ? `<p class="rank-help"><b>On a bye:</b> ${byes.map(nflName).map(escapeHtml).join(", ")}</p>` : "";
  }

  /* The room redraws itself in place: a filter is not a page load. */
  function bind(root) {
    const host = (root || document).querySelector("#ff-week");
    if (!host || host.dataset.bound) return;
    host.dataset.bound = "1";
    host.addEventListener("click", (e) => {
      const at = (sel) => (e.target.closest ? e.target.closest(sel) : null);
      const add = at("[data-ffcadd]"), del = at("[data-ffcdel]"), sc = at("[data-ffcsc]");
      if (add || del || sc) {
        if (add) {
          const n = add.dataset.ffcadd;
          cmp = cmp.includes(n) ? cmp.filter((x) => x !== n) : cmp.concat(n).slice(-CMP_MAX);
        }
        if (del) cmp = cmp.filter((x) => x !== del.dataset.ffcdel);
        if (sc) { try { localStorage.setItem(CMP_SC_KEY, sc.dataset.ffcsc); } catch (e2) { /* the default stays */ } }
        cmpRun(host);
        return;
      }
      const pos = at("[data-ffwpos]");
      const more = at("[data-ffwmore]");
      if (!pos && !more) return;
      if (pos) { wantPos = pos.dataset.ffwpos; showAll = false; }
      if (more) showAll = true;
      host.innerHTML = room(_ffWeek);
    });
    // A name picked from the list adds at once; Enter takes the one name
    // that holds what was typed.
    host.addEventListener("input", (e) => {
      const el = e.target;
      if (!el || el.id !== "ffc-in") return;
      const exact = ((_ffWeek || {}).players || []).find((r) => r.player === el.value);
      if (exact) cmpPick(host, exact.player);
    });
    host.addEventListener("keydown", (e) => {
      const el = e.target;
      if (!el || el.id !== "ffc-in" || e.key !== "Enter") return;
      e.preventDefault();
      const name = cmpFind(_ffWeek, el.value);
      const miss = host.querySelector(".ffc-miss");
      if (name) cmpPick(host, name);
      else if (miss) miss.textContent = el.value.trim() ? "No one on this week’s board by that name, or more than one: keep typing." : "";
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

  /* START A OR B? (engine/fantasy_compare, 2026-10-27; Ethan: "I don't
     know how fantasy works … invent more things"). Two to four of the
     week's players side by side and the call: how often the call outscores
     each of the others, the floor and the ceiling when the points are
     close, and the clock on a questionable one (his inactives against the
     other's kickoff). The server answers (/api/fantasy/compare), so this
     page and Ask say the same thing; this picks the players and draws the
     answer. Your own roster is a tap away once your league desk loads. */
  const CMP_MAX = 4;
  const CMP_SC_KEY = "qb_ffscoring";
  const CMP_SCORING = [["ppr", "PPR"], ["half", "Half"], ["standard", "Std"]];
  const CMP_GRADE = { soft: "soft", tough: "tough", neutral: "average" };
  let cmp = [];                     // the players picked, in order
  let cmpOut = null;                // the server's answer for them
  let cmpAsk = 0;                   // the latest request: an older answer is dropped

  function cmpScoring() {
    try {
      const v = localStorage.getItem(CMP_SC_KEY);
      return CMP_SCORING.some(([k]) => k === v) ? v : "ppr";
    } catch (e) { return "ppr"; }
  }

  /* Your roster, starters first, from the league desk (`_ffDesk`, app.js)
     once it has loaded: the players on this week's file, and your defense
     (the server finds a defense by any of its names). */
  function cmpRoster(w) {
    const L = (typeof _ffDesk !== "undefined" && _ffDesk && _ffDesk.lineup) || null;
    if (!L) return [];
    const have = new Set(((w || {}).players || []).map((r) => ffNorm(r.player)));
    const seats = [...(L.starters || []), ...(L.bench || [])].filter((x) => x && x.player);
    const names = seats.filter((x) => x.position === "DEF" || have.has(ffNorm(x.player))).map((x) => x.player);
    return [...new Set(names)].slice(0, 18);
  }

  /* A typed name: the week's own spelling, exactly, or the one player whose
     name holds it. */
  function cmpFind(w, typed) {
    const k = ffNorm(typed || "");
    if (!k) return null;
    const all = (w || {}).players || [];
    const exact = all.find((r) => ffNorm(r.player) === k);
    if (exact) return exact.player;
    const hits = all.filter((r) => ffNorm(r.player).includes(k));
    return hits.length === 1 ? hits[0].player : null;
  }

  /* A member's stat line, in words. */
  function cmpLine(c) {
    const l = (c || {}).line || {};
    const n = (k, d) => Number(l[k]).toFixed(d || 0);
    const bits = [];
    if (c.position === "QB") {
      if (l.pass_yds != null) bits.push(`${n("pass_yds")} pass yds`);
      if (l.pass_td != null) bits.push(`${n("pass_td", 1)} pass TD`);
      if (l.rush_yds != null) bits.push(`${n("rush_yds")} rush yds`);
    } else {
      if (l.rush_yds != null && (c.position === "RB" || l.rush_yds >= 5)) bits.push(`${n("rush_yds")} rush yds`);
      if (l.receptions != null) bits.push(`${n("receptions", 1)} catches`);
      if (l.rec_yds != null) bits.push(`${n("rec_yds")} rec yds`);
    }
    return bits.join(", ");
  }

  function cmpCardHTML(c, i, sc) {
    const def = c.position === "DEF";
    const who = def ? teamMark(c.team, 28, nflMap(), "nfl")
      : playerAvatar(c.player, c.team, { size: 28, map: nflMap(), headshot: c.headshot });
    const stat = (k, v) => (v == null || v === "" ? ""
      : `<div><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`);
    const line = cmpLine(c);
    return `<div class="ffc-card${i === 0 ? " lead" : ""}">
      <div class="ffc-who">${who}<span><b>${escapeHtml(c.player)}</b>
        <span>${escapeHtml([def ? "D/ST" : c.position, vs(c)].filter(Boolean).join(" · "))}</span></span></div>
      <div class="ffc-n"><b>${Number(c.points).toFixed(1)}</b><span>${def ? "points" : escapeHtml(sc)}</span></div>
      <dl class="ffc-stats">
        ${c.play < 1 ? stat("To play", `${Math.round(c.play * 100)}%${c.status ? ` (${c.status})` : ""}`) : ""}
        ${c.if_plays != null ? stat("If he plays", Number(c.if_plays).toFixed(1)) : ""}
        ${c.floor != null ? stat("8 in 10 weeks", `${Number(c.floor).toFixed(1)}${c.floor < 0 ? " to " : "–"}${
          Number(c.ceiling).toFixed(1)}`) : ""}
        ${stat("Matchup", CMP_GRADE[(c.matchup || {}).grade] || "")}
        ${stat("Kickoff", c.kickoff || "")}
        ${stat("His line", line)}
        ${c.td_prob != null ? stat(c.position === "QB" ? "Rush TD" : "TD chance", `${Math.round(c.td_prob * 100)}%`) : ""}
        ${c.dst ? stat("Sacks · takeaways", `${c.dst.sacks} · ${c.dst.takeaways}`) : ""}
      </dl>
      ${(c.why || []).length ? `<p class="ffc-why">${escapeHtml(c.why[0])}</p>` : ""}
    </div>`;
  }

  /* With a league linked, your matchup decides a close one: ahead, the
     floor; behind, the ceiling (fantasy_h2h's swings say it from the real
     margin). Only when the two at the top are both yours. */
  function cmpDeskNote(o) {
    const D = typeof _ffDesk !== "undefined" ? _ffDesk : null;
    const h = (D && D.h2h) || {};
    if (h.win_prob == null || !(o.notes || []).some((n) => /safer start|bigger week/.test(n))) return "";
    const mine = new Set(cmpRoster(_ffWeek).map(ffNorm));
    if (!(o.call.order || []).slice(0, 2).every((n) => mine.has(ffNorm(n)))) return "";
    const lean = h.win_prob >= 0.55 ? "lean on the safer start"
      : h.win_prob <= 0.45 ? "the bigger week is the one you need" : "";
    return lean ? `<p class="ffc-desk">Your league desk has you ${Math.round(h.win_prob * 100)}% to win
      this week: ${lean}.</p>` : "";
  }

  function cmpResultHTML(w) {
    if (cmp.length < 2) {
      return `<p class="ffc-hint">${cmp.length ? "Add one more to compare."
        : "Your two running backs, your flex options, two defenses to stream: type a name, or tap one from your roster."}</p>`;
    }
    const o = cmpOut;
    if (!o) return `<p class="loading">Comparing…</p>`;
    const unknown = (o.unknown || []).length ? `<p class="ffc-hint">Not on this week’s board (a bye, or no
      projection): ${escapeHtml(o.unknown.join(", "))}.</p>` : "";
    if (o.error || !o.call) return unknown + `<p class="ffc-hint">${escapeHtml(o.error || o.note || "No comparison this week.")}</p>`;
    const free = w && w.locked && w.locked["players[].fields"];
    return `${unknown}
      <div class="ffc-call${o.call.coin ? " coin" : ""}"><span class="ffc-k">The call</span>
        <b>${escapeHtml(o.call.text)}</b></div>
      ${cmpDeskNote(o)}
      <div class="ffc-grid">${(o.players || []).map((c, i) => cmpCardHTML(c, i, o.scoring || "PPR")).join("")}</div>
      ${(o.notes || []).length ? `<ul class="ffc-notes">${o.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}
      ${free ? `<p class="ffc-lock">${icon("lock", 12)} Members also see each player’s stat line, touchdown chance
        and the reason behind his number — <a href="#paywall">the plans</a>.</p>` : ""}`;
  }

  function compareHTML(w) {
    const sc = cmpScoring();
    const roster = cmpRoster(w);
    const full = cmp.length >= CMP_MAX;
    return `<div class="card ffc" id="ffc">
      <div class="ffc-head"><b>Start A or B?</b><span>Pick two to four players: who scores more this week,
        how often, and the clock on a questionable one.</span></div>
      <div class="ffc-pick">
        <input id="ffc-in" class="ffc-in" type="search" list="ffc-names" autocomplete="off" enterkeyhint="done"
          aria-label="Add a player or a defense to compare" placeholder="${full ? "Four at most" : "Add a player or a defense"}"${full ? " disabled" : ""}>
        <datalist id="ffc-names">${((w || {}).players || []).map((r) => `<option value="${escapeAttr(r.player)}">${
          escapeHtml([r.position === "DEF" ? "D/ST" : r.position, r.team].filter(Boolean).join(" · "))}</option>`).join("")}</datalist>
        <div class="rec-bf-group" role="group" aria-label="Scoring">${CMP_SCORING.map(([k, l]) => `
          <button type="button" class="rec-bf${k === sc ? " active" : ""}" data-ffcsc="${k}"
            aria-pressed="${k === sc ? "true" : "false"}">${l}</button>`).join("")}</div>
        <p class="ffc-miss" aria-live="polite"></p>
      </div>
      ${roster.length ? `<div class="ffc-roster"><span>Your roster</span>${roster.map((n) => `
        <button type="button" class="ffc-chip${cmp.includes(n) ? " on" : ""}" data-ffcadd="${escapeAttr(n)}"
          aria-pressed="${cmp.includes(n) ? "true" : "false"}">${escapeHtml(n)}</button>`).join("")}</div>` : ""}
      ${cmp.some((n) => !roster.includes(n)) ? `<div class="ffc-picked">${cmp.filter((n) => !roster.includes(n)).map((n) => `
        <button type="button" class="ffc-chip on" data-ffcdel="${escapeAttr(n)}" aria-label="Remove ${escapeAttr(n)}">${
          escapeHtml(n)} <span aria-hidden="true">×</span></button>`).join("")}</div>` : ""}
      <div class="ffc-out" aria-live="polite">${cmpResultHTML(w)}</div>
    </div>`;
  }

  function cmpPaint(host) {
    const box = host && host.querySelector("#ffc");
    if (box) box.outerHTML = compareHTML(_ffWeek);
  }

  async function cmpRun(host) {
    const ask = ++cmpAsk;
    cmpOut = null;
    cmpPaint(host);
    if (cmp.length < 2) return;
    const qs = cmp.map((n) => `p=${encodeURIComponent(n)}`).join("&") + `&scoring=${cmpScoring()}`;
    let out;
    try {
      const r = await fetch(`/api/fantasy/compare?${qs}`);
      out = await r.json();
    } catch (e) { out = { error: "The comparison did not load. Try again in a moment." }; }
    if (ask !== cmpAsk) return;
    cmpOut = out || { error: "No answer." };
    cmpPaint(host);
  }

  function cmpPick(host, name) {
    if (!name) return;
    cmp = cmp.includes(name) ? cmp : cmp.concat(name).slice(-CMP_MAX);
    cmpRun(host);
  }

  /* YOUR WEEK, AS A TO-DO LIST (engine/fantasy_todo, 2026-10-27; Ethan:
     "I don't know how fantasy works"). The desk's answers in the order a
     week is lost in, each with the points it is worth; a tap scrolls to the
     section that says more. */
  const TODO_SECTIONS = { lineup: "Your best lineup", h2h: "you vs", pickups: "Pickups for your roster",
                          trades: "Trades worth proposing" };
  function todo(d) {
    const list = (d || {}).todo;
    if (!Array.isArray(list)) return "";
    const wk = (d || {}).week || ((d || {}).projection_week || {}).week;
    const item = (t) => `<li class="fft-item ${escapeAttr(t.tone || "info")}"${t.section
        ? ` data-fftsec="${escapeAttr(t.section)}" role="button" tabindex="0"` : ""}>
        <span class="fft-dot" aria-hidden="true"></span>
        <span class="fft-text"><b>${escapeHtml(t.title)}</b>${t.detail ? `<span>${escapeHtml(t.detail)}</span>` : ""}</span>
        ${t.gain != null ? `<span class="fft-gain">+${Number(t.gain).toFixed(1)}</span>` : ""}
      </li>`;
    return `<div class="card fft">
      <div class="fft-head"><b>Your week</b><span>${wk ? `Week ${escapeHtml(String(wk))} · ` : ""}what to do now</span></div>
      ${list.length ? `<ol class="fft-list">${list.map(item).join("")}</ol>`
        : `<p class="fft-none">Nothing to do: your lineup is set and nothing on the wire beats it.</p>`}
    </div>`;
  }
  function todoBind(host) {
    if (!host) return;
    host.querySelectorAll("[data-fftsec]").forEach((el) => {
      const go = () => {
        const want = TODO_SECTIONS[el.dataset.fftsec] || "";
        const t = [...host.querySelectorAll(".section-title")].find((s) => s.textContent.includes(want));
        if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
      };
      el.addEventListener("click", go);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  }

  /* PICKUPS FOR YOUR ROSTER (engine/fantasy_waivers): what each free agent
     adds to YOUR best lineup this week, whom he pushes out, his season, a
     FAAB bid where the league bids from a budget, and the bench player to
     drop. */
  function rosterPickups(d) {
    const P = (d || {}).pickups;
    if (!P || !(P.pickups || []).length) return "";
    const row = (r) => {
      const c = r.card || {};
      const def = r.position === "DEF";
      const b = r.bid || {};
      const bid = b.rule === "stream" ? "Bid $0–1: a one-week stream"
        : b.high ? `Bid $${b.low}–$${b.high} of your $${b.of}` : "";
      return `<div class="hd-row ff-row${def ? "" : " ffrow-door"}"${def ? ""
          : ` data-dossier="${escapeAttr(r.player)}" role="button" tabindex="0"`}>
        <span class="ld-slot">${escapeHtml(def ? "D/ST" : r.position || "")}</span>
        <span class="hd-what"><b>${escapeHtml(r.player)}${matchChip(c.matchup)}${playChip(c)}</b>
          <span>${escapeHtml([r.replaces ? `in for ${r.replaces}` : "", vs(c),
            r.season_ppg ? `${Number(r.season_ppg).toFixed(1)} a game this season` : ""].filter(Boolean).join(" · "))}</span>
          ${bid ? `<span class="ffp-bid">${escapeHtml(bid)}</span>` : ""}</span>
        <span class="hd-state"><b>+${Number(r.gain).toFixed(1)}</b>
          <span class="hd-vs">to your lineup</span></span>
      </div>`;
    };
    const drop = P.drop;
    return `
      <div class="section-title">Pickups for your roster
        <span class="sub">— who adds the most to your best lineup this week</span></div>
      <div class="card ff-rows">${P.pickups.map(row).join("")}</div>
      ${drop ? `<p class="rank-help"><b>To make room:</b> drop ${escapeHtml(drop.player)} (${escapeHtml(drop.position || "")},
        ${Number(drop.ppg || 0).toFixed(1)} a game), your bench player worth least over the season.</p>` : ""}
      ${(P.pickups || []).some((r) => (r.bid || {}).rule === "thumb") ? `<p class="rank-help">The bid is a rule of thumb, not
        a measurement: more for more points a week and more weeks before the playoffs, never more than a quarter of
        what you have left.</p>` : ""}`;
  }

  /* The best of this week nobody in the league rosters (the desk's
     `free_agents`, engine/fantasyweek.free_agents): a pickup is this
     week's question too. */
  function pickups(d) {
    const fa = (d || {}).free_agents || {};
    const order = ["QB", "RB", "WR", "TE", "K", "DEF"].filter((p) => (fa[p] || []).length);
    if (!order.length) return rosterPickups(d);
    const row = (r) => {
      const c = r.card || {};
      const why = reasons(c, 1);
      // A team defense to stream is no player's panel (engine/dstproj).
      const def = r.position === "DEF";
      return `<div class="hd-row ff-row${def ? "" : " ffrow-door"}"${def ? ""
          : ` data-dossier="${escapeAttr(r.player)}" role="button" tabindex="0"`}>
        <span class="ld-slot">${escapeHtml(def ? "D/ST" : r.position || "")}</span>
        <span class="hd-what"><b>${escapeHtml(r.player)}${matchChip(c.matchup)}${playChip(r)}</b>
          <span>${escapeHtml([def ? (c.matchup || {}).text : nflName(r.team), vs(c)].filter(Boolean).join(" · "))}</span>
          ${why.length ? `<span class="ffw-why">${escapeHtml(why[0])}</span>` : ""}</span>
        <span class="hd-state"><b>${Number(r.expected).toFixed(1)}</b>
          <span class="hd-vs">${def ? "points" : "PPR"} this week</span></span>
      </div>`;
    };
    return rosterPickups(d) + `
      <div class="section-title">Best pickups this week
        <span class="sub">— the best of this week’s projections that nobody in your league
        rosters, by position</span></div>
      <div class="card ff-rows">${order.map((p) => fa[p].slice(0, 3).map(row).join("")).join("")}</div>`;
  }

  /* YOUR MATCHUP, LIVE (engine/fantasy_live, 2026-10-27): once a starter on
     either side has kicked off, the score as it stands (Sleeper's points,
     your league's scoring), each side's projected final with what is left
     projected, the win chance, and the lineups slot by slot, the way the
     fantasy apps draw a matchup. While a game is on it asks again every
     minute and redraws only itself. */
  const LIVE_EVERY_MS = 60e3;
  let liveTimer = null;

  function liveHTML(d) {
    const L = (d || {}).live;
    if (!L || !L.me) return "";
    const me = L.me, them = L.them || { players: [], points: 0, projected: 0 };
    const wp = L.win_prob;
    const word = L.done ? "Final" : L.in_progress ? "Live" : "Between games";
    const chip = (p) => p.state === "live" ? `<span class="ffl-st on">${escapeHtml(p.clock || "Live")}</span>`
      : p.state === "final" ? `<span class="ffl-st">Final</span>`
      : p.state === "pre" ? `<span class="ffl-st">${escapeHtml(p.clock || "Not started")}</span>` : "";
    const cell = (p, cls) => p && p.player ? `<span class="ffl-p ${cls}">
        <b>${escapeHtml(p.player)}</b>
        <span class="ffl-pp"><span class="ffl-n">${Number(p.points).toFixed(1)}</span>${chip(p)}</span>
      </span>` : `<span class="ffl-p ${cls} empty">Empty</span>`;
    const n = Math.max(me.players.length, (them.players || []).length);
    const rows = Array.from({ length: n }, (_, i) => {
      const a = me.players[i], b = (them.players || [])[i];
      const slot = (a && a.slot) || (b && b.slot) || "";
      return `<div class="ffl-row">${cell(a, "me")}<span class="ffl-slot">${escapeHtml(slot === "DEF" ? "D/ST"
        : slot === "SUPER_FLEX" ? "SF" : slot === "REC_FLEX" || slot === "WRRB_FLEX" ? "FLEX" : slot)}</span>${cell(b, "them")}</div>`;
    }).join("");
    const lead = Number(me.points) - Number(them.points);
    return `<div class="card ffl${L.in_progress ? " on" : ""}"${L.in_progress ? ` data-ffl-on="1"` : ""}>
      <div class="ffl-head"><span class="ffl-badge${L.in_progress ? " on" : ""}">${word}</span>
        <span>Week ${escapeHtml(String((d || {}).week || ""))}${L.opponent ? ` · vs ${escapeHtml(L.opponent)}` : ""}</span></div>
      <div class="ffl-score">
        <div class="ffl-side"><span class="ffl-who">You</span><b class="${lead >= 0 ? "up" : ""}">${Number(me.points).toFixed(1)}</b>
          <span class="ffl-proj">projected ${Number(me.projected).toFixed(1)}</span></div>
        <div class="ffl-side r"><span class="ffl-who">${escapeHtml(L.opponent || "Them")}</span><b class="${lead < 0 ? "up" : ""}">${
          Number(them.points).toFixed(1)}</b><span class="ffl-proj">projected ${Number(them.projected).toFixed(1)}</span></div>
      </div>
      ${wp != null ? `<div class="ffl-wp" role="img" aria-label="${Math.round(wp * 100)}% to win">
        <span class="ffl-wp-bar"><span style="width:${Math.max(2, Math.min(98, Math.round(wp * 100)))}%"></span></span>
        <span class="ffl-wp-n"><b>${Math.round(wp * 100)}%</b> to win</span></div>` : ""}
      <div class="ffl-rows">${rows}</div>
      <p class="ffl-note">Points so far are Sleeper’s, under your league’s scoring, for the lineup you set. What is
        left is projected: a player yet to play at this week’s projection, one in a game at his points plus his
        projection for the time left.${L.in_progress ? " This card refreshes every minute." : ""}</p>
    </div>`;
  }

  /* While a game is on, ask again every minute and redraw the card alone. */
  function liveWatch(host, leagueId, userId, platform) {
    if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
    if (!host || !host.querySelector(".ffl[data-ffl-on]")) return;
    liveTimer = setTimeout(async () => {
      liveTimer = null;
      const card = host.querySelector(".ffl");
      if (!card || !card.isConnected || document.hidden) {
        if (card && card.isConnected) liveWatch(host, leagueId, userId, platform);
        return;
      }
      try {
        const r = await fetch(`/api/leaguedesk?league=${encodeURIComponent(leagueId)}&user=${
          encodeURIComponent(userId || "")}&platform=${encodeURIComponent(platform || "sleeper")}`);
        const d = await r.json();
        const now = host.querySelector(".ffl");
        if (r.ok && now && now.isConnected) now.outerHTML = liveHTML(d) || now.outerHTML;
      } catch (e) { /* the next minute tries again */ }
      liveWatch(host, leagueId, userId, platform);
    }, LIVE_EVERY_MS);
  }

  /* YOUR SEASON (engine/fantasy_season, 2026-10-27; Ethan: "look at other
     apps … add more features"): playoff odds from the league's own
     schedule played out 2,000 times, power rankings with the all-play
     record and luck, and last week in review. Its own request after the
     desk paints (/api/leagueseason), so the desk is never slower for it.
     Sleeper leagues: their schedule and their weekly box are public. */
  // A simulation never proves a zero or a certainty: none of 2,000 is "<1%".
  const pct = (x) => (x == null ? "–" : x >= 0.995 ? ">99%" : x < 0.005 ? "<1%" : `${Math.round(x * 100)}%`);
  const rec = (w, l, t) => `${w}–${l}${t ? `–${t}` : ""}`;
  const ord = (n) => `${n}${["th", "st", "nd", "rd"][((n % 100) - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th"}`;

  /* What it takes, best record first: the outcomes that land at the same
     chance are one line ("2–4 or better: >99%"), so a team that is in
     unless it collapses reads as one. */
  function seasonPaths(d) {
    const ps = (d.paths || []).filter((p) => p.share >= 0.01);
    const groups = [];
    ps.forEach((p) => {
      const g = groups[groups.length - 1];
      if (g && g.label === pct(p.playoff)) g.lo = p;
      else groups.push({ hi: p, lo: p, label: pct(p.playoff) });
    });
    const r = (p) => rec(p.wins, p.of - p.wins);
    return groups.slice(0, 4).map((g) => ({
      text: g.hi === g.lo ? r(g.hi) : g.hi === ps[0] ? `${r(g.lo)} or better`
        : g.lo === ps[ps.length - 1] ? `${r(g.hi)} or worse` : `${r(g.hi)} to ${r(g.lo)}`,
      label: g.label,
    }));
  }

  function seasonMeHTML(d) {
    const me = (d.teams || []).find((t) => t.me);
    const o = (me || {}).odds;
    if (!me || !o) return "";
    const paths = seasonPaths(d);
    return `<div class="card ffs-me">
      <div class="ffs-big"><b>${pct(o.playoff)}</b><span>to make the playoffs</span></div>
      <p class="ffs-sub">Projected to finish ${rec(Math.round(o.wins), Math.round(o.losses))}, about the
        ${ord(Math.max(1, Math.round(o.seed)))} seed. The top ${escapeHtml(String(d.playoff_teams))} of
        ${(d.teams || []).length} make it; the regular season ends in Week ${escapeHtml(String(d.last_regular_week))}.
        ${o.first >= 0.01 ? ` First place: ${pct(o.first)}.` : ""}</p>
      ${paths.length && d.games_left ? `<ul class="ffs-paths">${paths.map((p) => `<li><b>${p.text}</b>
        the rest of the way: ${p.label} to get in</li>`).join("")}</ul>` : ""}
    </div>`;
  }

  function seasonTableHTML(d) {
    const rows = d.teams || [];
    if (!rows.length) return "";
    const row = (t) => {
      const ap = t.all_play ? `all-play ${rec(t.all_play.w, t.all_play.l, t.all_play.t)}` : "";
      const luck = t.luck == null || Math.abs(t.luck) < 0.5 ? ""
        : `<span class="hd-chip ${t.luck > 0 ? "good" : "bad"}" title="Wins above what the all-play record gives">${
          t.luck > 0 ? "lucky" : "unlucky"} ${t.luck > 0 ? "+" : ""}${Number(t.luck).toFixed(1)}</span>`;
      return `<div class="ffs-row${t.me ? " me" : ""}">
        <span class="ffs-rank">${t.power}</span>
        <span class="ffs-team"><b>${escapeHtml(t.team || "")}${luck}</b>
          <span>${escapeHtml([rec(t.wins, t.losses, t.ties), `${Number(t.pf).toFixed(1)} pts`, ap,
            `projects ${Number(t.strength).toFixed(1)} a week`].filter(Boolean).join(" · "))}</span></span>
        <span class="ffs-pct">${t.odds ? pct(t.odds.playoff) : "–"}</span>
        <span class="ffs-pct">${t.odds ? pct(t.odds.first) : "–"}</span>
      </div>`;
    };
    return `<div class="card ffs-table">
      <div class="ffs-row head"><span class="ffs-rank">#</span><span class="ffs-team">Power ranking</span>
        <span class="ffs-pct">Playoffs</span><span class="ffs-pct">1st</span></div>
      ${rows.map(row).join("")}
    </div>
    <p class="rank-help">Ranked by each roster’s best lineup a week on this season’s averages, under your league’s
      scoring. The odds play the rest of the regular season ${Number(d.sims || 0).toLocaleString()} times on your
      league’s own schedule: each team’s week drawn around that lineup with its starters’ own swings, a player on
      a bye at zero${d.this_week_basis === "week" ? ", this week on this week’s projections" : ""}, ties on record
      to points scored${d.median ? ", and a game against the league’s median every week" : ""}. Rosters as they
      stand today: no trades or pickups. All-play is each week’s score against every team’s, the record without
      the schedule’s luck.</p>`;
  }

  function reviewHTML(d) {
    const R = d.review;
    if (!R) return "";
    const m = R.me;
    const call = (c, word) => `${word} ${escapeHtml(c.started)} (${Number(c.started_pts).toFixed(1)}) over ${
      escapeHtml(c.benched)} (${Number(c.benched_pts).toFixed(1)})`;
    const mine = m ? `<div class="ffr-me">
        <p>${m.result ? `You ${{ W: "won", L: "lost", T: "tied" }[m.result]} ${Number(m.points).toFixed(1)}–${
          Number(m.opp_points).toFixed(1)} against ${escapeHtml(m.opponent || "")}.` : `You scored ${Number(m.points).toFixed(1)}.`}
          ${m.best == null ? "" : `Your best possible lineup scored ${Number(m.best).toFixed(1)}${m.left > 0.05
            ? `: you left ${Number(m.left).toFixed(1)} on your bench.` : ": you set it perfectly."}`}</p>
        ${m.worst_call ? `<p class="ffr-call bad">Costliest call: ${call(m.worst_call, "starting")}, −${
          Number(m.worst_call.diff).toFixed(1)}.${
          m.worst_call.would_have_won ? " The other way, you win the game." : ""}</p>` : ""}
        ${m.best_call ? `<p class="ffr-call good">Best call: ${call(m.best_call, "starting")}, +${
          Number(m.best_call.diff).toFixed(1)}.</p>` : ""}
      </div>` : "";
    return `<div class="section-title">Week ${escapeHtml(String(d.review_week || ""))} in review
        <span class="sub">— your week, and the league’s awards</span></div>
      <div class="card ffr">${mine}
        <ul class="ffr-awards">${(R.awards || []).map((a) => `<li><span>${escapeHtml(a.title)}</span>
          <b>${escapeHtml(a.text)}</b></li>`).join("")}</ul>
      </div>`;
  }

  function seasonHTML(d) {
    if (!d || !(d.teams || []).length) return "";
    return `<div class="section-title">Your season
        <span class="sub">— playoff odds and power rankings</span></div>
      ${seasonMeHTML(d)}${seasonTableHTML(d)}${reviewHTML(d)}`;
  }

  async function season(host, leagueId, userId, platform) {
    liveWatch(host, leagueId, userId, platform);
    const box = host && host.querySelector("#ffs");
    if (!box || !leagueId || (platform && platform !== "sleeper")) return;
    box.innerHTML = `<p class="loading">Playing out the rest of your season…</p>`;
    let d = null;
    try {
      const r = await fetch(`/api/leagueseason?league=${encodeURIComponent(leagueId)}&user=${
        encodeURIComponent(userId || "")}`);
      d = await r.json();
      if (!r.ok) d = null;
    } catch (e) { d = null; }
    if (box.isConnected) box.innerHTML = seasonHTML(d);
  }

  /* ---------------- Tonight: NBA, WNBA and NHL in fantasy points ---------
     engine/fantasy_daily, beside each night's board: every priced player's
     night added up in daily-fantasy points. The points are free; the stat
     line under them (`proj`) is the members' (gate.ROW_PAID_KEYS_BY_FILE).
     The scoring line is drawn from the file's own `scoring`, so the page
     and the sum cannot disagree. */
  const NIGHT = {
    nba: { teams: () => (typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : null),
           parts: [["pts", "PTS"], ["reb", "REB"], ["ast", "AST"], ["fg3m", "3PM"],
                   ["stl", "STL"], ["blk", "BLK"], ["tov", "TO"]],
           unscored: "Double-double and triple-double bonuses are not counted." },
    nhl: { teams: () => (typeof NHL_TEAMS !== "undefined" ? NHL_TEAMS : null),
           parts: [["goals", "G"], ["assists", "A"], ["sog", "SOG"], ["blocks", "BLK"]],
           unscored: "Bonuses (a hat trick, five shots, three blocks or three points) are not "
             + "counted, and goalies are left out: their wins and goals against are not projected." },
  };
  NIGHT.wnba = { ...NIGHT.nba, teams: () => (typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : null) };
  const NIGHT_WORD = { pts: "point", fg3m: "three", reb: "rebound", ast: "assist", stl: "steal",
                       blk: "block", tov: "turnover", goals: "goal", assists: "assist",
                       sog: "shot on goal", blocks: "blocked shot" };
  const NIGHT_POS = ["ALL", "C", "W", "D"];
  let night = { sport: "", game: "", pos: "ALL", all: false };
  let nightDocs = [];

  /* The Eastern date, turned at 6am: the day a night's slate belongs to. */
  function slateDay() {
    try {
      return new Date(new Date().getTime() - 6 * 3600e3)
        .toLocaleDateString("en-CA", { timeZone: "America/New_York" });
    } catch (e) { return new Date().toISOString().slice(0, 10); }
  }

  /* Tonight's files: built, holding players, and not a past night's. */
  function nightCurrent(docs) {
    const day = slateDay();
    return (docs || []).filter((d) => d && NIGHT[d.sport] && (d.players || []).length
      && String(d.date || "").slice(0, 10) >= day);
  }

  const listed = (xs) => (xs.length < 2 ? xs.join("")
    : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

  function tipOff(g) {
    const t = new Date((g || {}).kickoff || "");
    if (isNaN(t.getTime())) return "";
    if (t.getTime() <= new Date().getTime()) return "under way";
    return t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function gameKey(g) { return g && g.away && g.home ? `${g.away}@${g.home}` : ""; }

  function nightRow(r, sport) {
    const cfg = NIGHT[sport], map = cfg.teams();
    const g = r.game || {};
    const home = g.home ? g.home === r.team : null;
    const where = [r.opponent ? `${home === false ? "at" : "vs"} ${r.opponent}` : "", tipOff(g)]
      .filter(Boolean).join(" · ");
    const face = r.headshot ? playerAvatar(r.player, r.team, { size: 40, map, headshot: r.headshot })
      : teamMark(r.team, 40, map, sport);
    const p = r.proj || null;
    // A part the board has no line on is the season average: drawn dim,
    // said once above the list (nightHTML) rather than on every row.
    const avg = new Set(r.filled || []);
    const line = p ? cfg.parts.filter(([k]) => p[k] != null)
      .map(([k, short]) => `<span class="ffn-stat${avg.has(k) ? " avg" : ""}"${avg.has(k)
        ? ` title="Season average: no line tonight"` : ""}><b>${Number(p[k]).toFixed(1)}</b>${short}</span>`).join("") : "";
    return `<div class="ffr ffn-row">
      <span class="ffr-face">${face}</span>
      <span class="ffr-main">
        <span class="ffr-name"><b>${escapeHtml(r.player)}</b>${r.status
          ? `<span class="hd-chip warn">${escapeHtml(r.status)}</span>` : ""}</span>
        <span class="ffr-meta">${posBadge(r.position)}${teamMark(r.team, 14, map, sport)}<span>${escapeHtml(r.team)}${
          where ? ` · ${escapeHtml(where)}` : ""}</span></span>
        ${line ? `<span class="ffn-line">${line}</span>` : ""}
      </span>
      <span class="ffr-pts"><b>${Number(r.points).toFixed(1)}</b><span>FPTS</span></span>
    </div>`;
  }


  function nightScoring(doc) {
    const sc = doc.scoring || {};
    const a = (w) => (/^[aeiou]/.test(w) ? "an " : "a ") + w;
    const parts = Object.keys(sc).map((k) => `${sc[k] < 0 ? "−" : ""}${Math.abs(sc[k])} ${a(NIGHT_WORD[k] || k)}`);
    return `<p class="rank-help"><b>Scoring:</b> ${escapeHtml(listed(parts))}. ${escapeHtml(NIGHT[doc.sport].unscored)}</p>`;
  }

  /* The room: a switch per sport with a slate tonight, then the games, the
     positions (hockey's), and every priced player best first. "" when no
     slate is tonight's, which hides the tab. */
  function daily(docs) {
    nightDocs = nightCurrent(docs);
    if (!nightDocs.length) return "";
    return `<div id="ff-tonight">${nightHTML()}</div>`;
  }

  function nightHTML() {
    const doc = nightDocs.find((d) => d.sport === night.sport) || nightDocs[0];
    night.sport = doc.sport;
    const all = doc.players || [];
    const games = (doc.games || []).filter(gameKey);
    const game = games.some((g) => gameKey(g) === night.game) ? night.game : "";
    const posTabs = doc.sport === "nhl" ? NIGHT_POS.filter((p) => p === "ALL" || all.some((r) => r.position === p)) : [];
    const pos = posTabs.includes(night.pos) ? night.pos : "ALL";
    const rows = all.filter((r) => (!game || gameKey(r.game) === game) && (pos === "ALL" || r.position === pos));
    const shown = night.all ? rows : rows.slice(0, SHOWN);
    const word = { nba: "NBA", wnba: "WNBA", nhl: "NHL" };
    const locked = doc.locked && doc.locked["players[].fields"];
    return `
      ${nightDocs.length > 1 ? `<div class="rec-bf-group ffn-sports" role="group" aria-label="Sport">${nightDocs.map((d) => `
        <button type="button" class="rec-bf${d.sport === doc.sport ? " active" : ""}" data-ffnsport="${escapeAttr(d.sport)}"
          aria-pressed="${d.sport === doc.sport}">${word[d.sport]}</button>`).join("")}</div>` : ""}
      <div class="section-title">Tonight’s ${word[doc.sport]} in fantasy points
        <span class="sub">— ${all.length} players across ${games.length} game${games.length === 1 ? "" : "s"},
        from the same projections as tonight’s props</span></div>
      ${nightScoring(doc)}
      ${locked ? `<p class="rank-help">${icon("lock", 12)} Members also see each player’s stat line, the
        projections the points are added up from — <a href="#paywall">the plans</a>.</p>` : ""}
      <div class="ffn-filters">
        ${games.length > 1 ? `<label class="ffn-game">
          <select data-ffngame aria-label="Game">
            <option value="">All ${games.length} games</option>${games.map((g) => `
            <option value="${escapeAttr(gameKey(g))}"${gameKey(g) === game ? " selected" : ""}>${
              escapeHtml(`${g.away} at ${g.home}${tipOff(g) ? ` · ${tipOff(g)}` : ""}`)}</option>`).join("")}
          </select></label>` : ""}
        ${posTabs.length > 2 ? `<div class="rec-bf-group" role="group" aria-label="Position">${posTabs.map((p) => `
          <button type="button" class="rec-bf${p === pos ? " active" : ""}" data-ffnpos="${p}"
            aria-pressed="${p === pos}">${p === "ALL" ? "All" : p}</button>`).join("")}</div>` : ""}
      </div>
      ${shown.some((r) => r.proj && (r.filled || []).length) ? `<p class="ffn-key">Dimmed numbers are season
        averages: tonight’s board has no line on that stat.</p>` : ""}
      <div class="card ffr-list">${shown.map((r) => nightRow(r, doc.sport)).join("")
        || panelEmpty("No priced players in this game or position tonight.")}</div>
      ${rows.length > shown.length ? `<button type="button" class="btn ghost" data-ffnmore>Show all ${
        rows.length} players ▾</button>` : ""}`;
  }

  function dailyBind(root) {
    const host = (root || document).querySelector("#ff-tonight");
    if (!host || host.dataset.bound) return;
    host.dataset.bound = "1";
    const redraw = () => { host.innerHTML = nightHTML(); };
    host.addEventListener("click", (e) => {
      const at = (sel) => (e.target.closest ? e.target.closest(sel) : null);
      const sport = at("[data-ffnsport]"), pos = at("[data-ffnpos]"), more = at("[data-ffnmore]");
      if (sport) night = { sport: sport.dataset.ffnsport, game: "", pos: "ALL", all: false };
      else if (pos) { night.pos = pos.dataset.ffnpos; night.all = false; }
      else if (more) night.all = true;
      else return;
      redraw();
    });
    host.addEventListener("change", (e) => {
      if (!e.target || !e.target.matches("[data-ffngame]")) return;
      night.game = e.target.value;
      night.all = false;
      redraw();
    });
  }

  /* The tab's name: the sports with a slate tonight. */
  function dailyName(docs) {
    const word = { nba: "NBA", wnba: "WNBA", nhl: "NHL" };
    return listed(nightCurrent(docs).map((d) => word[d.sport])).replace(" and ", " & ") + " tonight";
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

  window.QBWeek = { room, bind, rowFor, dossier, pickups, basis, seat, current, h2hNote, callNote, todo, todoBind,
                    season, live: liveHTML, daily, dailyBind, dailyName, pos: posBadge };
})();
