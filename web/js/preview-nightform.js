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
    const cx = 60, cy = 42, L = 22;
    const x2 = cx + Math.cos(r) * L, y2 = cy + Math.sin(r) * L;
    const a1 = r + 2.5, a2 = r - 2.5;
    return `<path class="${hot ? "eng-hot" : "eng-dim"}"
      d="M${cx - Math.cos(r) * L} ${cy - Math.sin(r) * L}L${x2} ${y2}
         M${x2} ${y2}L${x2 + Math.cos(a1) * 7} ${y2 + Math.sin(a1) * 7}
         M${x2} ${y2}L${x2 + Math.cos(a2) * 7} ${y2 + Math.sin(a2) * 7}"/>`;
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
    // §5.3: `material` is true when the condition actually moved a number.
    // The slate does not carry that flag yet, so the prototype derives a
    // stand-in from thresholds the engines already use — wind at 8mph+,
    // altitude at 3000ft+, a roof at all. Wiring the real flag is a build
    // change and belongs with the migration, not with the look.
    const material = roofed || mph >= 8 || alt >= 3000;
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
       avg >= 0 ? "amber" : "brick"],
      ["Suggested exposure", `${stake.toFixed(2)}u`, "flat units, quarter-Kelly capped", ""],
    ];
    $("#summary").innerHTML = cells.map(([l, v, c, k]) =>
      `<div><div class="l">${l}</div><div class="v ${k}">${esc(v)}</div>
        <div class="c">${c}</div></div>`).join("");
    $("#slate-n").textContent = `${(d.games || []).length} venue(s)`;
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
    /* The spec asks for a conditions column — WIND for NFL, PARK for MLB.
       The game logs in the slate carry {week, opponent, value, home} and
       nothing about conditions, so the column is OMITTED rather than filled
       with em dashes. Populating it is a build change (engine/ has the
       weather per game), and it is listed on the field map as outstanding
       rather than quietly shipped as a row of blanks. */
    const rows = logs.length ? logs
      : vals.slice(-6).map(v => ({ value: v }));
    return `<table class="pp">
      <tr><th>Game</th><th>Opp</th><th>Line</th><th>Actual</th><th>Result</th></tr>
      ${rows.map(g => {
        const v = g.value != null ? g.value : g.actual;
        const hit = hitOf(v);
        const opp = g.opponent
          ? `${g.home === false ? "@" : ""}${g.opponent}` : "—";
        return `<tr><td>${esc(g.week != null ? "Wk " + g.week : g.date || "—")}</td>
          <td>${esc(opp)}</td><td>${line != null ? line : "—"}</td>
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
        <div class="cap">${cap}${r.game_date ? ` · ${esc(r.game_date)}` : ""}${
          r.game_kickoff ? ` ${esc(r.game_kickoff)}` : ""}</div>
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
    ["Player avatar", "dropped as a photo — replaced by the venue mark, which encodes conditions instead of decorating"],
    ["Matchup · position", "entry header, right-aligned"],
    ["Selection / book / price", "selection line, Archivo Narrow uppercase"],
    ["Letter grade badge", "amber 2px badge in the header row"],
    ["Projection vs line slider", "engraved ticks on one rule, bone = proj, amber = line"],
    ["HIT PROB / EDGE / EV per unit", "EDGE is the 33px hero; the rest are key/value rows"],
    ["0–10 score bar + readout", "amber bar under the hero with the numeric readout"],
    ["Recent-form trendline", "promoted to the past-performance table, with a conditions column"],
    ["Chip row 1 + 2", "one mono caption line under the selection"],
    ["Reasoning ✓/✗ list", "footnote list, amber check / brick cross, drawn not typed"],
    ["Venue diagram + wind dial", "engraved venue mark; wind drawn at true bearing"],
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
      chrome(d); standing(d); strip(d.games || []); summary(d);
      $("#entries").innerHTML = picks(d).map(entry).join("")
        || `<div class="note" style="border-color:var(--rule)">
              No qualifying plays on this card. Most slates have none — the pass
              list says why, market by market.</div>`;
    })
    .catch(e => { $("#entries").innerHTML =
      `<div class="note">Could not load ${esc(FEEDS[SPORT])} — ${esc(e.message)}</div>`; });
})();
