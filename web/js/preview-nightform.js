/* Night Form prototype renderer — Recommended page only.
 *
 * Deliberately separate from app.js. The prototype exists to answer "is this
 * direction right?", and it must not be able to break the working site while
 * answering that. It reads the same slate JSON app.js reads.
 *
 * The venue marks below are §5.4's geometry verbatim, with the encoding
 * contract from §5.1 enforced in one place: `material` gates every amber
 * stroke. A mark that encodes nothing renders entirely in graphite, because
 * "the environment is neutral here" is information too.
 */
(() => {
  const $ = s => document.querySelector(s);
  const qs = new URLSearchParams(location.search);
  const SPORT = qs.get("sport") || "nfl";

  const FEEDS = {
    nfl: "data/recommendations.json", cfb: "data/cfb.json",
    mlb: "data/mlb_recommendations.json", nba: "data/nba.json",
    wnba: "data/wnba.json",
  };
  const SUBTITLE = {
    nfl: "AI-powered NFL player-prop model",
    cfb: "College football — attention is the axis",
    mlb: "AI-powered MLB player-prop model",
    nba: "AI-powered NBA player-prop model",
    wnba: "Scalpy — WNBA probability engine",
  };
  /* Spec §1.1: nav is per-league configurable, and the spec's own note only
     records WNBA. The real table is wider — see tests/test_preservation.py. */
  const HIDDEN = { nba: ["longshots"], wnba: ["longshots"],
                   cfb: ["longshots", "trending", "players", "rosters"] };
  const SECTIONS = [["recommended", "Recommended"], ["live", "Live"],
    ["edge", "Edge Board"], ["scanner", "Scanner"], ["longshots", "Long Shots"],
    ["trending", "Trending"], ["players", "Players"], ["rosters", "Rosters"],
    ["standings", "Standings"], ["record", "Record"]];
  const LEAGUES = [["nfl", "NFL"], ["cfb", "CFB"], ["mlb", "MLB"], ["nba", "NBA"],
    ["wnba", "WNBA"], ["ufc", "UFC"], ["more", "More"]];

  const picks = d => (d.recommendations || [])
    .filter(r => r.recommended === true || r._ok === true);
  const esc = s => String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = x => `${(x * 100).toFixed(1)}%`;
  const signed = x => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;

  /* ── venue marks, §5.4 ─────────────────────────────────────────────── */
  function windArrow(bearing, hot) {
    // Drawn at true bearing, §5.1. 0deg = blowing toward the top of the mark.
    const r = (bearing - 90) * Math.PI / 180;
    const cx = 60, cy = 42, L = 15;
    const x2 = cx + Math.cos(r) * L, y2 = cy + Math.sin(r) * L;
    const a1 = r + 2.5, a2 = r - 2.5;
    return `<path class="${hot ? "eng-hot" : "eng-dim"}"
      d="M${cx - Math.cos(r) * L} ${cy - Math.sin(r) * L}L${x2} ${y2}
         M${x2} ${y2}L${x2 + Math.cos(a1) * 5} ${y2 + Math.sin(a1) * 5}
         M${x2} ${y2}L${x2 + Math.cos(a2) * 5} ${y2 + Math.sin(a2) * 5}"/>`;
  }

  function venueMark(kind, scale, cond = {}) {
    const hot = !!cond.material;          // gates ALL amber, §5.3
    const E = hot ? "eng" : "eng-dim";
    const HOT = hot ? "eng-hot" : "eng-dim";
    const detail = scale >= 48;           // drop hatching below 48, §5.2
    let g = "";
    if (kind === "mlb") {
      g = `<path class="eng-fill" d="M60 76L18 34A56 56 0 0 1 102 34Z"/>
           <path class="${E}" d="M60 76L18 34A56 56 0 0 1 102 34Z"/>
           ${cond.shortPorch ? `<path class="${HOT}" style="stroke-width:2.4"
               d="M18 34A56 56 0 0 1 60 16"/>` : ""}
           <path class="${E}" d="M60 70L44 54L60 38L76 54Z"/>
           <circle class="eng-dim" cx="60" cy="54" r="12"/>`;
    } else if (kind === "dome") {
      g = `<ellipse class="${hot ? "eng-amberfill" : "eng-fill"}" cx="60" cy="42" rx="57" ry="39"/>
           <ellipse class="${E}" cx="60" cy="42" rx="57" ry="39"/>
           <path class="eng-dim" d="M60 3V81 M3 42H117 M20 14L100 70 M100 14L20 70"/>
           <ellipse class="eng-dim" cx="60" cy="42" rx="30" ry="20"/>
           <rect class="${E}" x="30" y="30" width="60" height="24"/>`;
    } else if (kind === "court") {
      g = `<rect class="eng-fill" x="8" y="16" width="104" height="52"/>
           <rect class="${E}" x="8" y="16" width="104" height="52"/>
           <path class="eng-dim" d="M60 16V68"/>
           <circle class="eng-dim" cx="60" cy="42" r="10"/>
           <rect class="eng-dim" x="8" y="30" width="20" height="24"/>
           <rect class="eng-dim" x="92" y="30" width="20" height="24"/>`;
    } else if (kind === "octagon") {
      g = `<polygon class="eng-fill" points="93,56 74,75 46,75 27,56 27,28 46,9 74,9 93,28"/>
           <polygon class="${E}" points="93,56 74,75 46,75 27,56 27,28 46,9 74,9 93,28"/>
           <polygon class="eng-dim" points="84,53 70,67 50,67 36,53 36,31 50,17 70,17 84,31"/>`;
    } else {                                             // nfl open air
      g = `<ellipse class="eng-fill" cx="60" cy="42" rx="57" ry="39"/>
           <ellipse class="eng-dim" cx="60" cy="42" rx="57" ry="39"/>
           <ellipse class="eng-dim" cx="60" cy="42" rx="47" ry="31"/>
           <rect class="${E}" x="26" y="27" width="68" height="30"/>
           ${detail ? `<path class="eng-hatch" d="M36 27V57 M46 27V57 M56 27V57
                        M66 27V57 M76 27V57 M86 27V57"/>` : ""}
           <rect class="${E}" x="26" y="27" width="9" height="30"/>
           <rect class="${E}" x="85" y="27" width="9" height="30"/>`;
    }
    if (cond.wind && cond.wind.mph >= 8) g += windArrow(cond.wind.bearing || 0, hot);
    const h = Math.round(scale * 84 / 120);
    return `<svg width="${scale}" height="${h}" viewBox="0 0 120 84"
              aria-hidden="true" style="display:block;margin:0 auto">${g}</svg>`;
  }

  const COMPASS = { N: 0, NNE: 22, NE: 45, ENE: 67, E: 90, ESE: 112, SE: 135,
    SSE: 157, S: 180, SSW: 202, SW: 225, WSW: 247, W: 270, WNW: 292, NW: 315,
    NNW: 337, OUT: 0, IN: 180, CROSS: 270 };

  function condOf(g) {
    const w = g.weather || {};
    const roofed = !!(w.dome || g.roof === "dome" || g.roof === "retractable"
                      || g.indoor);
    const mph = Math.round(w.wind_mph || 0);
    const bearing = COMPASS[(w.wind_dir || "").toUpperCase()] ?? 0;
    const alt = (g.stadium && g.stadium.altitude_ft) || g.altitude_ft || 0;
    /* §5.3: `material` is true when the condition actually MOVED a number
       for at least one play at this venue, and it is computed upstream now —
       engine/pipeline.py::_conditions and engine/mlb/pipeline.py::_conditions
       read the model's own per-market multipliers and intersect them with the
       markets actually priced tonight.

       The threshold fallback below is what this used to do on its own, and it
       answers a DIFFERENT question: it says the condition is big, not that it
       did anything. A 10mph wind at a venue whose only priced market is
       rushing yards moves nothing and should render dim. It survives only for
       payloads built before the flag existed. */
    const c = g.conditions;
    const material = c ? !!c.material : (roofed || mph >= 8 || alt >= 3000);
    return { roofed, wind: { mph, bearing }, alt, material,
             shortPorch: (g.park_factor_hr || 0) > 0 };
  }

  function condText(g) {
    const c = condOf(g), bits = [];
    if (c.roofed) bits.push(`<span class="hot">Roofed</span>`);
    else if (c.wind.mph) {
      const w = g.weather || {};
      const t = w.temp_f != null ? `${Math.round(w.temp_f)}°F · ` : "";
      bits.push(`${t}<span class="${c.material ? "hot" : ""}">${c.wind.mph}mph
                 ${esc((w.wind_dir || "").toUpperCase())}</span>`);
    } else bits.push("conditions not pulled");
    if (c.alt >= 3000) bits.push(`<span class="hot">${(c.alt / 1000).toFixed(1)}k ft</span>`);
    return bits.join(" · ");
  }

  const markKind = g => {
    if (SPORT === "mlb") return "mlb";
    if (SPORT === "nba" || SPORT === "wnba") return "court";
    const c = condOf(g);
    return c.roofed ? "dome" : "nfl";
  };
  const venueName = g => (g.stadium && g.stadium.name) || g.park_name
    || `${g.away} @ ${g.home}`;

  /* ── the engraved compass dial, §5.5 ───────────────────────────────
     "The current cards carry a wind compass dial (numeric mph, cardinal
     label, direction arrow) alongside the diagram. Keep it — but render it
     as an engraved dial. It is the only place the exact bearing is
     legible." So it is kept, and it is the same geometry as the wind arrow
     on the mark rather than a second unrelated drawing. */
  function compass(w, material) {
    const mph = Math.round(w.wind_mph || 0);
    const dir = (w.wind_dir || "").toUpperCase();
    const bearing = COMPASS[dir] ?? 0;
    const cx = 46, cy = 46;
    const hot = material && mph >= 8;
    const ticks = [0, 45, 90, 135, 180, 225, 270, 315].map(d => {
      const a = (d - 90) * Math.PI / 180;
      const outer = 36, inner = d % 90 ? 32 : 29;
      return `M${cx + Math.cos(a) * outer} ${cy + Math.sin(a) * outer}
              L${cx + Math.cos(a) * inner} ${cy + Math.sin(a) * inner}`;
    }).join(" ");
    /* The needle used to run from rim to rim THROUGH the centre, straight
       across the mph value — the number and the bearing fought for the same
       12 pixels. It is a rim pointer now: the bearing stays exact and
       legible, and the centre is left to the number it belongs to. */
    const a = (bearing - 90) * Math.PI / 180;
    const tip = 40, base = 29, halfw = 0.20;
    const pt = (rad, ang) => `${cx + Math.cos(ang) * rad},${cy + Math.sin(ang) * rad}`;
    return `<svg width="92" height="92" viewBox="0 0 92 92" class="dial" aria-hidden="true">
      <circle class="eng-dim" cx="46" cy="46" r="38"/>
      <path class="eng-dim" d="${ticks}"/>
      <text x="46" y="13" text-anchor="middle" class="dial-n">N</text>
      ${mph ? `<polygon class="${hot ? "dial-hot" : "dial-cold"}"
          points="${pt(tip, a)} ${pt(base, a + halfw)} ${pt(base, a - halfw)}"/>` : ""}
      <text x="46" y="50" text-anchor="middle" class="dial-v ${hot ? "hot" : ""}">${mph}</text>
      <text x="46" y="62" text-anchor="middle" class="dial-u">MPH${dir ? " " + esc(dir) : ""}</text>
    </svg>`;
  }

  /* ── venue cards §1.3 ──────────────────────────────────────────────
     The spec contradicts itself here: §1.3 lists every field on these
     cards as must-survive, and §7 says "Venue cards -> conditions strip".
     Following §7 dropped the live badge, the score, the situation line,
     the line summary, the kickoff, the compass dial and the per-game link
     — 205 strings measured missing against the live page. §1.3 wins:
     the preservation contract outranks a layout suggestion. The strip
     stays as well, because §6.5 is explicit that it "replaces nothing". */
  function venueCard(g, picksFor) {
    const c = condOf(g);
    const live = g.live || {};
    const isLive = live.state === "live";
    const isFinal = live.state === "final";
    const w = g.weather || {};
    const fav = g.favorite && g.spread != null
      ? `${esc(teamNick(g.favorite))} −${Math.abs(g.spread).toFixed(1)}` : "";
    const ou = g.total != null ? `O/U ${g.total.toFixed(1)}` : "line not posted yet";
    const score = side => (live.home_score != null && (isLive || isFinal))
      ? `<span class="vc-score">${side === "home" ? live.home_score : live.away_score}</span>` : "";
    const when = [g.date ? fmtDate(g.date) : "", g.kickoff ? fmtTime(g.kickoff) : ""]
      .filter(Boolean).join(" · ");
    return `<article class="vcard ${isLive ? "on" : ""}">
      ${isLive ? `<div class="vc-live"><i></i>LIVE ${esc(live.period || "")}
          ${esc(live.clock || "")}</div>` : ""}
      <div class="vc-art">${venueMark(markKind(g), 200, c)}
        ${c.roofed ? `<div class="vc-roof">Dome</div>` : ""}</div>
      <div class="vc-body">
        <div class="vc-teams">
          <span class="vc-t">${esc(teamNick(g.away))}</span>${score("away")}
          <span class="vc-at">@</span>
          <span class="vc-t">${esc(teamNick(g.home))}</span>${score("home")}
        </div>
        <div class="vc-line">${[fav, ou].filter(Boolean).join(" · ")}</div>
        <div class="vc-when">${esc(when)}</div>
        ${isLive && (live.detail || live.situation)
          ? `<div class="vc-sit"><i></i>${esc(live.detail || live.situation)}</div>` : ""}
        <div class="vc-cond">
          ${c.roofed ? "" : compass(w, c.material)}
          <div class="vc-condtext">
            <div class="vc-venue">${esc(venueName(g))}</div>
            <div>${condText(g)}</div>
          </div>
        </div>
      </div>
      <a class="vc-foot" href="#">${picksFor
        ? `${picksFor} pick${picksFor === 1 ? "" : "s"} for this game`
        : "See this game's board"}<span>&#8594;</span></a>
    </article>`;
  }

  /* Team identities come from the same teams.js the live site loads, so a
     card says "Packers", not "GB". Falls back to the abbreviation for CFB,
     whose 134 identities ride in the payload rather than a checked-in file. */
  const TEAMSET = () => {
    if (SPORT === "mlb") return typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {};
    if (SPORT === "nba") return typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : {};
    if (SPORT === "wnba") return typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : {};
    if (SPORT === "cfb") return (window.__teams || {});
    return typeof TEAMS !== "undefined" ? TEAMS : {};
  };
  const teamNick = a => (TEAMSET()[a] && TEAMSET()[a].nick) || a;
  const fmtDate = d => {
    const t = new Date(d + "T12:00:00");
    return isNaN(t) ? d : t.toLocaleDateString("en-US",
      { weekday: "short", month: "short", day: "numeric" });
  };
  /* MLB kickoffs arrive as a full ISO timestamp and NFL's as "HH:MM", so
     the caption was printing "2026-06-20 2026-06-20T18:20:00Z" — the date
     twice, once as a machine string. One formatter, both shapes. */
  const when = r => {
    const d = r.game_date ? fmtDate(String(r.game_date).slice(0, 10)) : "";
    const k = r.game_kickoff || "";
    const t = /T\d\d:/.test(k) ? fmtTime(k.slice(11, 16))
            : /^\d\d?:\d\d/.test(k) ? fmtTime(k) : "";
    return [d, t].filter(Boolean).join(" · ");
  };
  const fmtTime = k => {
    const [h, m] = String(k).split(":").map(Number);
    if (isNaN(h)) return k;
    const ap = h >= 12 ? "PM" : "AM";
    return `${((h + 11) % 12) + 1}:${String(m || 0).padStart(2, "0")} ${ap} ET`;
  };

  function venueCards(d) {
    const games = d.games || [];
    const count = g => picks(d).filter(r =>
      r.team === g.home || r.team === g.away
      || r.opponent === g.home || r.opponent === g.away).length
      + (d.game_bets || []).filter(b => b.recommended
      && b.home === g.home && b.away === g.away).length;
    $("#vc-n").textContent = `${games.length} venue(s)`;
    $("#vcards").innerHTML = games.map(g => venueCard(g, count(g))).join("")
      || `<div class="note" style="border-color:var(--rule)">
            Nothing is scheduled or in progress for this slate yet.</div>`;
  }

  /* ── game bets §1.3 ────────────────────────────────────────────────
     "moneyline, spread & total edges from the team model", with per-market
     count badges. Dropped from the first prototype entirely. */
  function gameBets(d) {
    const bets = (d.game_bets || []).filter(b => b.recommended);
    const byMarket = {};
    bets.forEach(b => { const k = (b.market_label || b.market || "").toUpperCase();
      byMarket[k] = (byMarket[k] || 0) + 1; });
    $("#gb-counts").innerHTML = Object.entries(byMarket)
      .map(([k, n]) => `<span class="mkt">${esc(k)} <b>${n}</b></span>`).join("");
    $("#gamebets").innerHTML = bets.map((b, i) => `<article class="entry gb">
      <div class="gutter"></div>
      <div>
        <div class="ehead">
          <span class="rot">${String(i + 1).padStart(3, "0")}</span>
          <span class="name">${esc(b.pick_label || b.headline)}</span>
          ${b.grade ? `<span class="grade">${esc(b.grade)}</span>` : ""}
          <span class="match">${esc(b.matchup || "")}</span>
        </div>
        <div class="sel">${esc(b.market_label || b.market)}
          <span class="bk">— ${esc(b.odds ?? "")}</span></div>
        <ul class="reasons">${(b.reasons || []).map(x =>
          `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
      <div class="rail">
        <div class="heroblock">
          <div class="hero ${(b.edge || 0) < 0 ? "neg" : ""}">${signed(b.edge || 0)}</div>
          <div class="hero-l">Edge</div>
        </div>
        <div>
          <div class="kv"><span>Model</span><b>${pct(b.win_prob || 0)}</b></div>
          <div class="kv"><span>Book implied</span><b>${pct(b.fair_prob || 0)}</b></div>
          <div class="kv hot"><span>EV / unit</span><b>${signed(b.ev_per_unit || 0)}</b></div>
          <div class="kv"><span>Stake ¼ Kelly</span><b>${
            b.stake_units != null ? b.stake_units.toFixed(2) + "u" : "—"}</b></div>
        </div>
      </div>
    </article>`).join("") || `<div class="note" style="border-color:var(--rule)">
        No game bets cleared the gates on this card.</div>`;
  }

  /* ── the ranked picks list §1.3 ────────────────────────────────────
     The compact list above the cards: rank, Play, selection, book+odds,
     matchup, qualifier, EV and stake right-aligned. */
  function picksList(d) {
    const rows = picks(d);
    $("#pl-lead").textContent =
      `${rows.length} pick${rows.length === 1 ? "" : "s"} tonight — this is the whole list.`;
    $("#pickslist").innerHTML = rows.map((r, i) => `<div class="prow">
      <span class="pr-n">${String(i + 1).padStart(2, "0")}</span>
      <button class="play sm">Play</button>
      <span class="pr-sel"><b>${esc(r.player)} ${esc(r.side || "")} ${esc(r.line ?? "")}
        ${esc(r.market_label || r.market || "")}</b>
        <span class="pr-bk">${esc(r.odds ?? "")} (${esc(r.book || "")})</span>
        <span class="pr-mt">${esc(r.team || "")} vs ${esc(r.opponent || "")}${
          r.game_date ? ` · ${esc(fmtDate(r.game_date))}` : ""}${
          r.game_kickoff ? ` · ${esc(fmtTime(r.game_kickoff))}` : ""}</span>
        <span class="pr-q">cleared every gate</span></span>
      <span class="pr-ev">${signed(r.edge || 0)}</span>
      <span class="pr-u">${r.stake_units != null ? r.stake_units.toFixed(2) + "u" : "—"}</span>
    </div>`).join("");
  }

  /* ── render ────────────────────────────────────────────────────────── */
  function nav() {
    $("#leagues").innerHTML = LEAGUES.map(([k, l]) =>
      `<a href="?sport=${k}" class="${k === SPORT ? "on" : ""}">${l}</a>`).join("");
    const hide = HIDDEN[SPORT] || [];
    $("#sections").innerHTML = SECTIONS.filter(([k]) => !hide.includes(k))
      .map(([k, l]) => `<a href="#" class="${k === "recommended" ? "on" : ""}">${l}</a>`).join("");
  }

  function chrome(d) {
    $("#subtitle").textContent = SUBTITLE[SPORT] || "See the math. Know if it's working.";
    const dt = d.date ? new Date(d.date + "T12:00:00") : new Date();
    $("#mast-date").textContent = dt.toLocaleDateString("en-US",
      { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
    const built = d.generated_at ? new Date(d.generated_at) : null;
    $("#mast-fresh").textContent = (built
      ? `Built ${built.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })} · `
      : "") + `${picks(d).length} qualified play(s)`;
    const live = d.mode === "live" || d.live === true;
    const m = $("#mode");
    m.className = "mode" + (live ? " live" : "");
    m.lastElementChild.textContent = live ? "Live data" : "Sample data";
  }

  function standing(d) {
    // §9: publishing the record IS the positioning, so it stands in the
    // masthead rather than only on a sub-page.
    const r = d.record || {};
    const roi = r.roi_pct != null ? r.roi_pct : null;
    $("#standing").innerHTML = `
      <span>Running ROI <b class="${roi != null && roi < 0 ? "neg" : ""}">${
        roi != null ? `${roi > 0 ? "+" : ""}${roi.toFixed(1)}%` : "on the Record page"}</b></span>
      ${r.line ? `<span>Record <b>${esc(r.line)}</b></span>` : ""}
      <span>Every pick journaled at its real book price and graded in public.</span>`;
  }

  function strip(games) {
    if (!$("#strip")) return;   // Recommended leads with the cards instead
    $("#strip").innerHTML = games.map(g => {
      const c = condOf(g);
      return `<div class="cell">
        ${venueMark(markKind(g), 48, c)}
        <div><div class="nm">${esc(venueName(g))}</div>
             <div class="cond">${condText(g)}</div></div></div>`;
    }).join("") || `<div class="cell"><div class="nm">No games on the board</div></div>`;
  }

  function summary(d) {
    // `recommendations` carries EVERY priced market with a `recommended`
    // flag, not just the picks — the prototype listed all twelve as plays
    // on its first render. app.js gates on the same idea via r._ok.
    const recs = picks(d);
    const analysed = (d.counts && d.counts.props_analyzed)
                     || (d.recommendations || []).length;
    const avg = recs.length ? recs.reduce((a, r) => a + (r.edge || 0), 0) / recs.length : 0;
    const stake = recs.reduce((a, r) => a + (r.stake_units || 0), 0);
    const cells = [
      ["Markets priced", String(analysed), "props and game bets the model gave a number to", ""],
      ["Recommended bets", String(recs.length), "cleared every approval gate", ""],
      ["Avg edge", signed(avg), "model probability vs the de-vigged book price",
       avg >= 0 ? "good" : "brick"],
      ["Suggested exposure", `${stake.toFixed(2)}u`, "flat units, quarter-Kelly capped", ""],
    ];
    $("#summary").innerHTML = cells.map(([l, v, c, k]) =>
      `<div><div class="l">${l}</div><div class="v ${k}">${esc(v)}</div>
        <div class="c">${c}</div></div>`).join("");
    if ($("#slate-n")) $("#slate-n").textContent = `${(d.games || []).length} venue(s)`;
    $("#rec-n").textContent = `${recs.length} pick(s), ranked by quality`;
    $("#died-label").textContent =
      `Why only ${recs.length}? · where the other ${Math.max(0, analysed - recs.length)} died`;
    $("#died-body").textContent =
      `${analysed} market(s) were priced tonight and ${recs.length} cleared. `
      + `The rest failed an approval gate — no real book number, edge under the `
      + `threshold, juice past the cap, or a sample too small to trust. The gate `
      + `that stopped each one is listed on the full board.`;
  }

  function ppTable(r) {
    const logs = (r.logs || []).slice(-6);
    const vals = r.recent_values || [];
    if (!logs.length && !vals.length) return "";
    const line = r.line;
    const hitOf = v => line != null && v != null
      && (r.side === "UNDER" ? v < line : v > line);
    /* §6.4's conditions column — WIND for NFL, PARK for MLB. Both are
       populated by the build now (see engine/pipeline.py::_log_wind and
       engine/mlb/pipeline.py::_log_park). It is still rendered ONLY when the
       data is actually there: a column of em dashes looks like the data is
       missing rather than not applicable, which is worse than no column. */
    const rows = logs.length ? logs
      : vals.slice(-6).map(v => ({ value: v }));
    const hasWind = rows.some(g => g.wind != null);
    const hasPark = rows.some(g => g.park);
    const cond = hasWind ? "Wind" : hasPark ? "Park" : null;
    const condCell = g => !cond ? ""
      : hasWind ? `<td>${g.wind != null ? esc(g.wind) : "—"}</td>`
      : `<td title="${esc(g.park || "")}">${g.park
          ? esc(String(g.park).replace(/ (Field|Park|Stadium|Center|Centre)$/, ""))
            + (g.park_hr && Math.abs(g.park_hr - 1) >= 0.04
               ? ` <span class="${g.park_hr > 1 ? "hot" : ""}">${
                   g.park_hr > 1 ? "+" : ""}${Math.round((g.park_hr - 1) * 100)}%</span>` : "")
          : "—"}</td>`;
    return `<table class="pp">
      <tr><th>Game</th><th>Opp</th>${cond ? `<th>${cond}</th>` : ""}
          <th>Line</th><th>Actual</th><th>Result</th></tr>
      ${rows.map(g => {
        const v = g.value != null ? g.value : g.actual;
        const hit = hitOf(v);
        const opp = g.opponent
          ? `${g.home === false ? "@" : ""}${g.opponent}` : "—";
        return `<tr><td>${esc(g.week != null ? "Wk " + g.week : g.date || "—")}</td>
          <td>${esc(opp)}</td>${condCell(g)}<td>${line != null ? line : "—"}</td>
          <td>${v != null ? v : "—"}</td>
          <td class="${hit ? "hit" : "miss"}">${line == null ? "—"
            : hit ? (r.side || "OVER") : "miss"}</td></tr>`;
      }).join("")}
    </table>`;
  }

  function projBar(r) {
    if (r.projection == null || r.line == null) return "";
    const lo = Math.min(r.projection, r.line), hi = Math.max(r.projection, r.line);
    const pad = Math.max((hi - lo) * 1.6, hi * 0.12 || 1);
    const a = lo - pad, b = hi + pad;
    const at = v => `${((v - a) / (b - a) * 100).toFixed(1)}%`;
    return `<div class="projbar">
        <div class="track"></div>
        <div class="tick" style="left:${at(r.projection)}"></div>
        <div class="tick line" style="left:${at(r.line)}"></div>
      </div>
      <div class="projleg">Projection vs line —
        <span class="p">proj ${r.projection}</span> ·
        <span class="l">line ${r.line}</span> · ${esc(r.market_label || r.market || "")}</div>`;
  }

  function entry(r, i) {
    const g = (window.__games || []).find(x =>
      x.home === r.team || x.away === r.team || x.home === r.opponent) || {};
    const c = condOf(g);
    const conf = r.confidence != null ? r.confidence : null;
    const cap = [
      conf != null ? `Q ${(conf * 10).toFixed(0)}/100` : null,
      r.usage_role ? esc(r.usage_role) : null,
      r.trend ? esc(r.trend) : null,
      (r.all_lines || []).length > 1
        ? `${r.all_lines.length} books, best ${esc(r.book)}` : null,
      r.stake_units != null ? `${r.stake_units.toFixed(2)}u` : null,
    ].filter(Boolean).join(" · ");
    const NEG = /suppress|tough |capped|fewer |struggles|cold|underdog|risk|unconfirmed|against/i;
    return `<article class="entry">
      <div class="gutter">
        ${venueMark(markKind(g), 48, c)}
        <div class="lab">${esc(venueName(g) || "Venue")}</div>
        <div class="cnd">${condText(g)}</div>
      </div>
      <div>
        <div class="ehead">
          <span class="rot">${String(i + 1).padStart(3, "0")}</span>
          <span class="name">${esc(r.player)}</span>
          ${r.grade ? `<span class="grade">${esc(r.grade)}</span>` : ""}
          <span class="match">${esc(r.team || "")} vs ${esc(r.opponent || "")}${
            r.position ? " · " + esc(r.position) : ""}</span>
        </div>
        <div class="sel">${esc(r.side || "")} ${esc(r.line ?? "")}
          ${esc(r.market_label || r.market || "")}
          <span class="bk">— ${esc(r.book || "")} ${esc(r.odds ?? "")}</span></div>
        <div class="cap">${cap}${when(r) ? ` · ${esc(when(r))}` : ""}</div>
        ${projBar(r)}
        ${ppTable(r)}
        <ul class="reasons">${(r.reasons || []).map(x =>
          `<li class="${NEG.test(x) ? "neg" : ""}">${esc(x)}</li>`).join("")}</ul>
        ${(r.warnings || []).map(w => `<div class="cap" style="color:var(--brick)">${esc(w)}</div>`).join("")}
      </div>
      <div class="rail">
        <div class="heroblock">
          <div class="hero ${(r.edge || 0) < 0 ? "neg" : ""}">${signed(r.edge || 0)}</div>
          <div class="hero-l">Edge</div>
          ${conf != null ? `<div class="scorebar"><i style="width:${conf * 10}%"></i></div>
            <div class="cap">${conf.toFixed(1)}/10 confidence</div>` : ""}
        </div>
        <div>
          <div class="kv"><span>Hit prob</span><b>${pct(r.hit_prob || 0)}</b></div>
          <div class="kv"><span>No-vig fair</span><b>${pct(r.fair_prob || 0)}</b></div>
          <div class="kv"><span>Offered</span><b>${esc(r.odds ?? "—")}</b></div>
          <div class="kv hot"><span>EV / unit</span><b>${signed(r.ev_per_unit || 0)}</b></div>
          <div class="kv"><span>Stake ¼ Kelly</span><b>${
            r.stake_units != null ? r.stake_units.toFixed(2) + "u" : "—"}</b></div>
        </div>
        <div class="heroblock">
          <div class="foot">${esc(r.summary || r.headline || "")}</div>
          <button class="play">Play</button>
        </div>
      </div>
    </article>`;
  }

  /* Spec §1.3 line by line, with where each field went. Rendered on the page
     so "did we lose anything" is answerable by reading rather than trusting. */
  const FIELD_MAP = [
    ["Colour", "green/red = a NUMBER is favourable or against you; amber = a CONDITION is live or material. The spec routed wins through amber; overridden."],
    ["Player avatar", "dropped as a photo — replaced by the venue mark, which encodes conditions instead of decorating"],
    ["Matchup · position", "entry header, right-aligned"],
    ["Selection / book / price", "selection line, Archivo Narrow uppercase"],
    ["Letter grade badge", "amber 2px badge in the header row"],
    ["Projection vs line slider", "engraved ticks on one rule, bone = proj, amber = line"],
    ["HIT PROB / EDGE / EV per unit", "EDGE is the 33px hero in green/red; the rest are key/value rows"],
    ["0–10 score bar + readout", "green bar under the hero with the numeric readout"],
    ["Recent-form trendline", "promoted to the past-performance table, with a real conditions column — WIND from the history DB for NFL, PARK plus its HR factor for MLB"],
    ["Chip row 1 + 2", "one mono caption line under the selection"],
    ["Reasoning ✓/✗ list", "footnote list, green check / red cross, drawn not typed"],
    ["Venue cards + wind dial", "kept front and centre, first block on the page: live badge and clock, score, line summary, kickoff, situation line, engraved compass dial, per-game link, horizontal scroll"],
    ["Summary metric cards", "ruled columns, no card boxes"],
    ["Why only N? expander", "kept, restyled as editorial apparatus"],
    ["Tracked signals expander", "kept"],
    ["why? chips", "amber dagger footnote markers"],
    ["Data-mode pill", "promoted to the masthead, always visible"],
    ["Footer + 1-800-GAMBLER", "kept verbatim, responsible-gambling line on an amber rule"],
  ];

  function fieldmap() {
    $("#fieldmap").innerHTML = `<tr><th>§1.3 field</th><th style="text-align:left">Where it went</th></tr>`
      + FIELD_MAP.map(([a, b]) =>
        `<tr><td>${esc(a)}</td><td style="text-align:left">${esc(b)}</td></tr>`).join("");
  }

  /* ── boot ──────────────────────────────────────────────────────────── */
  nav();
  fieldmap();
  $("#theme").onclick = () => {
    const now = document.documentElement.getAttribute("data-theme") === "light";
    document.documentElement.setAttribute("data-theme", now ? "dark" : "light");
  };
  document.querySelectorAll("[data-sp]").forEach(b =>
    b.onclick = () => { location.search = `?sport=${b.dataset.sp}`; });
  document.querySelectorAll(".why").forEach(b => b.onclick = () => {
    const n = document.getElementById(b.dataset.note);
    n.hidden = !n.hidden;
    b.innerHTML = n.hidden ? "why<sup>†</sup>" : "hide<sup>†</sup>";
  });

  fetch(FEEDS[SPORT] || FEEDS.nfl, { cache: "no-store" })
    .then(r => r.json())
    .then(d => {
      window.__games = d.games || [];
      window.__teams = d.teams || {};
      chrome(d); standing(d); strip(d.games || []); summary(d);
      venueCards(d); picksList(d); gameBets(d);
      $("#entries").innerHTML = picks(d).map(entry).join("")
        || `<div class="note" style="border-color:var(--rule)">
              No qualifying plays on this card. Most slates have none — the pass
              list says why, market by market.</div>`;
    })
    .catch(e => { $("#entries").innerHTML =
      `<div class="note">Could not load ${esc(FEEDS[SPORT])} — ${esc(e.message)}</div>`; });
})();
