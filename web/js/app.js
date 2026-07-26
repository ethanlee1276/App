/* Gridiron Edge — app shell.
 *
 * A small client-side router over three views (Recommended / Trending /
 * Players) sharing one data fetch. Rendering helpers draw the pick cards,
 * trending leaderboards and player profiles; visuals.js supplies the SVG art
 * (avatars, stadiums, wind, sparklines).
 */

const state = {
  data: null, minConf: 6.0, minEdge: 2.0, maxJuice: -350, showAll: false,
  view: "recommended", search: "",
  sport: new URLSearchParams(location.search).get("sport") === "mlb" ? "mlb" : "nfl",
  static: new URLSearchParams(location.search).has("static"),
  bankroll: null, unitPct: 1.0,      // per-user bankroll sizing (localStorage)
};

/* ---------------- bankroll sizing ---------------- */
function loadBankroll() {
  const qp = new URLSearchParams(location.search);
  try {
    const b = localStorage.getItem("ge-bankroll");
    const u = localStorage.getItem("ge-unit-pct");
    if (b !== null && b !== "") state.bankroll = parseFloat(b);
    if (u !== null && u !== "") state.unitPct = parseFloat(u) || 1.0;
  } catch (e) {}
  // URL params win (shareable sizing), e.g. ?bankroll=2500&unit=1
  if (qp.has("bankroll")) { const b = parseFloat(qp.get("bankroll")); if (b > 0) state.bankroll = b; }
  if (qp.has("unit")) { const u = parseFloat(qp.get("unit")); if (u > 0) state.unitPct = u; }
}
function unitDollars() {
  return (state.bankroll && state.bankroll > 0) ? state.bankroll * (state.unitPct / 100) : 0;
}
function money(x) {
  return "$" + x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function stakeDollars(units) { return units * unitDollars(); }
function updateUnitNote() {
  const el = document.getElementById("unit-note");
  if (!el) return;
  const u = unitDollars();
  el.textContent = u > 0 ? `1u = ${money(u)}` : "enter to size bets";
}

const SPORT_META = {
  nfl: { logo: "🏈", tagline: "AI-powered NFL player-prop model",
         gamesTitle: "This week's stadiums & conditions",
         api: "/api/recommendations", fallback: "data/recommendations.json" },
  mlb: { logo: "⚾", tagline: "AI-powered MLB player-prop model",
         gamesTitle: "Today's ballparks & conditions",
         api: "/api/mlb/recommendations", fallback: "data/mlb_recommendations.json" },
};

function applySport() {
  const meta = SPORT_META[state.sport];
  window.ACTIVE_SPORT = state.sport;
  window.ACTIVE_TEAMS = state.sport === "mlb"
    ? (typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {})
    : (typeof TEAMS !== "undefined" ? TEAMS : {});
  document.getElementById("brand-logo").textContent = meta.logo;
  document.getElementById("tagline").textContent = meta.tagline;
  const gt = document.getElementById("games-title");
  if (gt) gt.textContent = meta.gamesTitle;
  document.querySelectorAll(".sport-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.sport === state.sport));
}

/* ---------------- formatting helpers ---------------- */
const gradeClass = (g) => ({ "Strong Play": "strong", "Play": "play", "Lean": "lean", "Pass": "pass" }[g] || "pass");
const gradeColor = (g) => ({ "Strong Play": "var(--good)", "Play": "var(--cyan)", "Lean": "var(--warn)", "Pass": "var(--text-mute)" }[g] || "var(--text-mute)");
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const signedPct = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
const american = (o) => (o > 0 ? `+${o}` : `${o}`);
const activeTeams = () => window.ACTIVE_TEAMS || (typeof TEAMS !== "undefined" ? TEAMS : {});
const teamName = (a) => (activeTeams()[a] && activeTeams()[a].nick) || a;
const teamPrimary = (a) => (activeTeams()[a] && activeTeams()[a].primary) || "var(--brand)";
/* A reason that WORKS AGAINST the bet must not wear a green check. The
   engine phrases negative factors consistently; match those phrasings and
   render them with a red ✗ instead. */
const NEG_REASON = new RegExp(
  ["suppress", "tough ", "holds (lefties|righties)", "capped",
   "strong late relief", "fewer ", "struggles", "knocks balls down",
   "kills carry", "cold", "underdog", "passing risk", "regression risk",
   "soft contact", "\\boverperforming", "reduced exit", "tight zone",
   "small zone", "moving against", "give back", "gives back"].join("|"), "i");

function reasonLI(x) {
  return `<li class="${NEG_REASON.test(x) ? "neg" : ""}">${escapeHtml(x)}</li>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------- date / kickoff formatting ---------------- */
function formatGameDate(dateStr) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || "");
  if (!m) return "";
  // Build a local date (avoids the UTC-parse off-by-one on YYYY-MM-DD).
  const d = new Date(+m[1], +m[2] - 1, +m[3]);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function formatKickoff(kick) {
  if (!kick) return "";
  if (kick.includes("T")) {                       // ISO datetime (MLB first pitch)
    const d = new Date(kick);
    return isNaN(d) ? "" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  const m = /^(\d{1,2}):(\d{2})/.exec(kick);       // "HH:MM" 24h ET (NFL)
  if (m) { let h = +m[1]; const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; return `${h}:${m[2]} ${ap} ET`; }
  return kick;
}
function whenLabel(dateStr, kick) {
  return [formatGameDate(dateStr), formatKickoff(kick)].filter(Boolean).join(" · ");
}
function whenChip(dateStr, kick) {
  const w = whenLabel(dateStr, kick);
  return w ? `<span class="chip when">${escapeHtml(w)}</span>` : "";
}

/* ---------------- motion ---------------- */
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const revealObserver = ("IntersectionObserver" in window) && !reduceMotion
  ? new IntersectionObserver((entries, obs) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); obs.unobserve(e.target); } });
    }, { threshold: 0.08, rootMargin: "0px 0px -6% 0px" })
  : null;

// Tag children for staggered reveal, then observe (or show immediately).
function revealChildren(container) {
  if (!container) return;
  const instant = reduceMotion || state.static || state.quiet || !revealObserver;
  const kids = container.children;
  for (let i = 0; i < kids.length; i++) {
    const el = kids[i];
    el.classList.add("reveal");
    el.style.setProperty("--i", Math.min(i, 12));
    if (instant) el.classList.add("in");
    else revealObserver.observe(el);
  }
}

// Subtle pointer tilt for stadium cards.
function enableTilt(container) {
  if (!container || reduceMotion) return;
  container.querySelectorAll(".tilt").forEach((card) => {
    card.addEventListener("pointermove", (ev) => {
      const r = card.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width - 0.5;
      const py = (ev.clientY - r.top) / r.height - 0.5;
      card.classList.add("tilting");
      card.style.transform = `perspective(760px) rotateY(${px * 7}deg) rotateX(${-py * 7}deg) translateZ(6px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.classList.remove("tilting");
      card.style.transform = "";
    });
  });
}

/* ---------------- theme ---------------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "light" ? "☀️" : "🌙";
  try { localStorage.setItem("ge-theme", theme); } catch (e) {}
}
function initTheme() {
  const param = new URLSearchParams(location.search).get("theme");
  let theme = param;
  if (!theme) { try { theme = localStorage.getItem("ge-theme"); } catch (e) {} }
  if (theme !== "light" && theme !== "dark") theme = "dark";
  applyTheme(theme);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(cur === "dark" ? "light" : "dark");
}

/* ---------------- data ---------------- */
function showSkeleton() {
  const host = document.getElementById("cards");
  if (host) host.innerHTML = Array.from({ length: 6 }, () => `<div class="skeleton-card"></div>`).join("");
}

async function load(quiet = false) {
  state.quiet = quiet;                       // silent re-render (no entrance anim)
  if (!quiet) showSkeleton();
  const refreshBtn = document.getElementById("refresh");
  if (refreshBtn && !quiet) refreshBtn.classList.add("loading");
  const meta = SPORT_META[state.sport];
  const params = new URLSearchParams({ min_confidence: state.minConf, min_edge: state.minEdge, max_juice: state.maxJuice });
  try {
    const res = await fetch(`${meta.api}?${params}`);
    if (!res.ok) throw new Error("api");
    state.data = await res.json();
  } catch (e) {
    const res = await fetch(meta.fallback);
    state.data = await res.json();
  }
  renderAll();
  state.lastLoad = Date.now();
  state.quiet = false;
  if (refreshBtn && !quiet) refreshBtn.classList.remove("loading");
  manageAutoRefresh();
  updateAgo();
}

/* Poll for live updates every 30s while any game is in progress. */
function manageAutoRefresh() {
  const hasLive = (state.data?.games || []).some((g) => (g.live || {}).state === "live");
  const el = document.getElementById("live-refresh");
  if (hasLive && !state.static) {
    if (!state.refreshTimer) state.refreshTimer = setInterval(() => load(true), 30000);
    if (!state.tickTimer) state.tickTimer = setInterval(updateAgo, 1000);
    if (el) el.style.display = "";
  } else {
    clearInterval(state.refreshTimer); state.refreshTimer = null;
    clearInterval(state.tickTimer); state.tickTimer = null;
    if (el) el.style.display = "none";
  }
}

function updateAgo() {
  const el = document.getElementById("live-refresh");
  if (!el || !state.lastLoad) return;
  const s = Math.max(0, Math.round((Date.now() - state.lastLoad) / 1000));
  el.innerHTML = `<span class="live-dot"></span>Auto · updated ${s}s ago`;
}

function passesFilters(r) {
  return r.recommended && r.confidence >= state.minConf && r.edge * 100 >= state.minEdge
    && r.odds >= state.maxJuice && r.grade !== "Pass";
}

function slateDateLabel(d) {
  // Show the span of actual game dates when the slate covers more than one day.
  const dates = [...new Set((d.games || []).map((g) => g.date).filter(Boolean))].sort();
  if (!dates.length) return `Slate: ${d.date}`;
  if (dates.length === 1) return formatGameDate(dates[0]);
  return `${formatGameDate(dates[0])} – ${formatGameDate(dates[dates.length - 1])}`;
}

function renderDataSource(d) {
  const el = document.getElementById("data-source");
  if (!el) return;
  const src = String(d.generated_from || "");
  const live = src.startsWith("live");
  el.className = `data-source ${live ? "live" : "sample"}`;
  el.innerHTML = `<span class="src-dot"></span>${live ? "Live data" : "Sample data"}`;
  el.title = live
    ? (d.built_at ? `Real data · built ${d.built_at.replace("T", " ")}` : "Real live data")
    : "Illustrative sample data — run a live build (see LAUNCH.md) for real games";
}

function renderAll() {
  const d = state.data;
  if (!d) return;
  renderDataSource(d);
  document.getElementById("slate-date").textContent = slateDateLabel(d);
  renderStats();
  renderEmptySlate();
  renderTopPlays();
  renderGames();
  renderGameBets();
  renderRecommended();
  renderEdgeBoard();
  renderScanner();
  renderLongShots();
  renderTrending();
  renderPlayers();
}

/* ============================================================
   Empty state — nothing on the board
   ============================================================ */
function renderEmptySlate() {
  const el = document.getElementById("empty-slate");
  const noGames = !(state.data.games || []).length;
  const noProps = !(state.data.recommendations || []).length;
  if (!noGames || !el) {
    if (el) el.style.display = "none";
    document.getElementById("games-title").style.display = "";
    return;
  }
  const live = String(state.data.generated_from || "").startsWith("live");
  el.style.display = "";
  el.innerHTML = live
    ? `<div class="es-icon">🗓️</div><div class="es-title">No games on the board right now</div>
       <div class="es-sub">Nothing is scheduled or in progress for this slate yet. Check back closer to
       game time — the board refreshes automatically.</div>`
    : `<div class="es-icon">🏟️</div><div class="es-title">No slate loaded</div>
       <div class="es-sub">Build a live slate (see LAUNCH.md) or run <code>python3 generate.py</code>
       for the sample board.</div>`;
  // Nothing else to show; clear the busier sections.
  document.getElementById("games-title").style.display = noProps ? "none" : "";
}

/* ============================================================
   Top plays — best bets across props AND game bets
   ============================================================ */
function topPlaysList() {
  const props = (state.data.recommendations || []).filter(passesFilters).map((r) => ({
    kind: "prop", grade: r.grade, conf: r.confidence, edge: r.edge, stake: r.stake_units,
    team: r.team, live: r.live, headshot: r.headshot,
    label: `${r.player} · ${r.side} ${r.line} ${r.market_label}`,
    sub: `${teamName(r.team)} vs ${teamName(r.opponent)}`, odds: r.odds,
  }));
  const games = (state.data.game_bets || []).filter(passesGameBet).map((r) => ({
    kind: "game", grade: r.grade, conf: r.confidence, edge: r.edge, stake: r.stake_units,
    team: r.team, live: r.live,
    label: r.pick_label, sub: `${r.matchup} · ${r.market_label}`, odds: r.odds,
  }));
  return [...props, ...games].sort((a, b) => b.conf - a.conf || b.edge - a.edge).slice(0, 5);
}

function renderTopPlays() {
  const rows = topPlaysList();
  const title = document.getElementById("topplays-title");
  const host = document.getElementById("topplays");
  if (!rows.length) { title.style.display = "none"; host.innerHTML = ""; return; }
  title.style.display = "";
  const ud = unitDollars();
  host.innerHTML = rows.map((r, i) => {
    const badge = r.team ? teamMark(r.team, 26)
      : `<span class="tp-rank">${i + 1}</span>`;
    const stake = ud > 0 ? money(stakeDollars(r.stake)) : `${r.stake.toFixed(2)}u`;
    return `
      <div class="tp-row" style="--grade-color:${gradeColor(r.grade)}">
        <div class="tp-rank-n">${i + 1}</div>
        <div class="tp-mark">${badge}</div>
        <div class="tp-main">
          <div class="tp-label">${escapeHtml(r.label)}${r.live ? ` <span class="tp-live">● LIVE</span>` : ""}</div>
          <div class="tp-sub">${escapeHtml(r.sub)} · ${american(r.odds)}</div>
        </div>
        <div class="tp-metric"><div class="k">Edge</div><div class="v pos">${signedPct(r.edge)}</div></div>
        <div class="tp-metric"><div class="k">Conf</div><div class="v">${r.conf.toFixed(1)}</div></div>
        <div class="tp-metric"><div class="k">Stake</div><div class="v">${stake}</div></div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>`;
  }).join("");
  revealChildren(host);
}

/* ============================================================
   Game bets — grouped by market (moneyline / spread / total)
   ============================================================ */
function passesGameBet(r) {
  return r.confidence >= state.minConf && r.edge * 100 >= state.minEdge
    && r.odds >= state.maxJuice && r.grade !== "Pass";
}

const GAMEBET_GROUPS = [
  ["moneyline", "Moneyline"], ["spread", "Spread"],
  ["total", "Game total"], ["team_total", "Team total"],
];

function renderGameBets() {
  const bets = (state.data.game_bets || []).map((r) => ({ ...r, _ok: passesGameBet(r) }));
  const visible = bets.filter((r) => (state.showAll ? true : r._ok));
  const title = document.getElementById("gamebets-title");
  const host = document.getElementById("gamebets");
  if (!visible.length) {
    title.style.display = "none";
    host.innerHTML = "";
    return;
  }
  title.style.display = "";
  host.innerHTML = GAMEBET_GROUPS.map(([type, label]) => {
    const rows = visible.filter((b) => b.bet_type === type);
    if (!rows.length) return "";
    return `<div class="gb-group">
        <div class="gb-group-label">${label}<span>${rows.length}</span></div>
        <div class="cards">${rows.map(gameBetCard).join("")}</div>
      </div>`;
  }).join("");
  fillMeters(host);
  host.querySelectorAll(".gb-group .cards").forEach(revealChildren);
}

function gameBetCard(r) {
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">${stakeTxt}</span>` : "";
  const reasons = (r.reasons || []).map(reasonLI).join("");

  // Header (badge + title + sub) varies by bet type; the metrics are shared.
  let mark, title, sub;
  if (r.bet_type === "spread") {
    const ln = `${r.line > 0 ? "+" : ""}${r.line}`;
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} <span class="ml-odds">${ln}</span> <span class="book">${american(r.odds)}</span>`;
    sub = "Spread · cover the number";
  } else if (r.bet_type === "total") {
    const arrow = r.side === "Over" ? "▲" : "▼";
    mark = `<span class="total-badge ${r.side === "Over" ? "over" : "under"}">${arrow}</span>`;
    title = `${escapeHtml(r.side)} ${r.line} <span class="book">${american(r.odds)}</span>`;
    sub = "Total · combined score";
  } else if (r.bet_type === "team_total") {
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} ${escapeHtml(r.side)} ${r.line} <span class="book">${american(r.odds)}</span>`;
    sub = "Team total · this team only";
  } else { // moneyline
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} <span class="ml-odds">${american(r.odds)}</span>`;
    sub = "Moneyline · win outright";
  }

  return `
    <article class="card gamebet ${r._ok ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${mark}
          <div>
            <div class="player">${title}</div>
            <div class="subtitle">${escapeHtml(r.matchup)}${whenLabel(r.date, r.kickoff) ? ` · 🗓️ ${escapeHtml(whenLabel(r.date, r.kickoff))}` : ""}</div>
            <div class="pick">${sub}</div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Model</div><div class="v">${pct(r.win_prob)}</div></div>
        <div class="metric"><div class="k">Book implied</div><div class="v">${pct(r.fair_prob)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips">${stakeChip}</div>
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    </article>`;
}

/* ============================================================
   Recommended view
   ============================================================ */
function renderStats() {
  const d = state.data;
  const recs = d.recommendations.map((r) => ({ ...r, _ok: passesFilters(r) }));
  const rec = recs.filter((r) => r._ok);
  const avgEdge = rec.reduce((s, r) => s + r.edge, 0) / (rec.length || 1);
  const exposure = rec.reduce((s, r) => s + r.stake_units, 0);
  const ud = unitDollars();
  const tiles = [
    { k: "Props analyzed", to: d.counts.props_analyzed, dec: 0 },
    { k: "Recommended", to: rec.length, dec: 0 },
    { k: "Avg edge", to: rec.length ? avgEdge * 100 : 0, dec: 1, suf: "%", pre: avgEdge >= 0 ? "+" : "", cls: "pos" },
    ud > 0
      ? { k: "Suggested exposure", to: exposure * ud, dec: 2, pre: "$", sub: `${exposure.toFixed(2)}u` }
      : { k: "Suggested exposure", to: exposure, dec: 2, suf: "u" },
  ];
  const fmt = (t) => (t.pre || "") + Number(t.to).toFixed(t.dec) + (t.suf || "");
  const instant = state.static || state.quiet;
  document.getElementById("stats").innerHTML = tiles.map((t) =>
    `<div class="tile"><div class="k">${t.k}</div>
       <div class="v ${t.cls || ""}" data-to="${t.to}" data-dec="${t.dec}" data-pre="${t.pre || ""}" data-suf="${t.suf || ""}">${instant ? fmt(t) : "0"}</div>
       ${t.sub ? `<div class="tile-sub">${t.sub}</div>` : ""}</div>`
  ).join("");
  if (!instant) document.querySelectorAll("#stats .v[data-to]").forEach(countUp);
}

function renderGames() {
  const games = [...(state.data.games || [])];
  const host = document.getElementById("games");
  if (!games.length) { host.innerHTML = ""; return; }
  // Live games float to the front of the strip.
  const rank = (g) => ((g.live || {}).state === "live" ? 0 : (g.live || {}).state === "final" ? 2 : 1);
  games.sort((a, b) => rank(a) - rank(b));
  host.innerHTML = games.map(gameCard).join("");
  revealChildren(host);
  enableTilt(host);
}

function gameCard(g) {
  const mlb = state.sport === "mlb";
  const w = g.weather || {};
  const windTxt = mlb && w.wind_dir && !w.dome
    ? `${Math.round(w.wind_mph)}mph ${w.wind_dir}`
    : `${Math.round(w.wind_mph)}mph${w.wind_dir ? " " + w.wind_dir : ""}`;
  const cond = w.dome ? "Indoor" : `${Math.round(w.temp_f)}°F · ${windTxt}`;
  let sub;
  if (mlb) {
    const bits = [`O/U ${g.total.toFixed(1)}`];
    if (g.park_name) bits.unshift(g.park_name);
    if (g.lineups_confirmed === false) bits.push("⚠ lineups pending");
    sub = bits.join(" · ");
  } else {
    const favTxt = g.favorite ? `${teamName(g.favorite)} −${Math.abs(g.spread).toFixed(1)}` : "";
    sub = `${favTxt} · O/U ${g.total.toFixed(1)}`;
  }
  const art = mlb ? ballpark(g) : stadium(g);
  const live = g.live || {};
  const isLive = live.state === "live";
  const isFinal = live.state === "final";
  // Score shown beside each team when the game has started.
  const score = (side) => (live.home_score != null && (isLive || isFinal))
    ? `<b class="score">${side === "home" ? live.home_score : live.away_score}</b>` : "";
  let badge = "";
  if (isLive) {
    badge = `<div class="status-badge live"><span class="live-dot"></span>LIVE
      <span class="per">${escapeHtml(live.period)}${live.clock ? " " + escapeHtml(live.clock) : ""}</span></div>`;
  } else if (isFinal) {
    badge = `<div class="status-badge final">FINAL${live.period && live.period !== "Final" ? " · " + escapeHtml(live.period) : ""}</div>`;
  }
  // MLB live: a mini base-state diamond replaces the outs/runners text.
  // NFL live: the down & distance line.
  let liveDetail = "";
  if (isLive && mlb) {
    const outs = live.outs == null ? 0 : live.outs;
    liveDetail = `
      <div class="live-detail base">
        ${baseDiamond(live.bases, live.outs)}
        <span class="base-label">${outs} out${outs === 1 ? "" : "s"}</span>
      </div>`;
  } else if (isLive && live.detail) {
    liveDetail = `<div class="live-detail"><span class="live-dot sm"></span>${escapeHtml(live.detail)}</div>`;
  }
  // The wind gauge and (for MLB live) the base diamond share the footer row.
  const footer = isLive && mlb
    ? `<div class="wind-wrap live-footer">${windGauge(w)}<span class="cond">${escapeHtml(cond)}</span>${liveDetail}</div>`
    : `<div class="wind-wrap">${windGauge(w)}<span class="cond">${escapeHtml(cond)}</span></div>`;
  return `
    <article class="game-card tilt ${isLive ? "is-live" : ""}">
      <div class="stadium-wrap">${art}${badge}</div>
      <div class="game-info">
        <div class="matchup">
          <span class="mt away">${teamMark(g.away, 18)} ${escapeHtml(teamName(g.away))} ${score("away")}</span>
          <span class="at">@</span>
          <span class="mt home">${teamMark(g.home, 18)} ${escapeHtml(teamName(g.home))} ${score("home")}</span></div>
        <div class="game-sub">${escapeHtml(sub)}</div>
        ${whenLabel(g.date, g.kickoff) ? `<div class="game-when">🗓️ ${escapeHtml(whenLabel(g.date, g.kickoff))}</div>` : ""}
        ${isLive && !mlb ? liveDetail : ""}
      </div>
      ${footer}
    </article>`;
}

function fillMeters(host) {
  host.querySelectorAll(".conf-fill[data-w]").forEach((el) => {
    if (state.quiet) { el.style.transition = "none"; el.style.width = el.dataset.w; }
    else requestAnimationFrame(() => (el.style.width = el.dataset.w));
  });
}

function renderRecommended() {
  const host = document.getElementById("cards");
  // When the whole slate is empty, the empty-slate banner already explains it.
  if (!(state.data.games || []).length && !(state.data.recommendations || []).length) {
    host.innerHTML = "";
    return;
  }
  const recs = state.data.recommendations.map((r) => ({ ...r, _ok: passesFilters(r) }));
  // Home runs are long shots by nature: this page features only the top
  // three (hr_featured, stamped by the pipeline) — the same three that lead
  // the Long Shots page, where the FULL home-run board lives.
  const visible = recs.filter((r) => (state.showAll ? true : r._ok))
    .filter((r) => r.hr_featured !== false);
  if (!visible.length) {
    // Say WHY the board is empty. "Loosen the sliders" is bad advice when the
    // real reason is that no prop has a real book price yet — picks are never
    // made against placeholder lines, so the board fills when books post
    // prices (and lineups) closer to game time.
    const noMarket = recs.length && recs.every((r) => r.has_market === false);
    host.innerHTML = noMarket
      ? `<p class="loading">${noMarketExplainer()}</p>`
      : `<p class="loading">No props clear the current thresholds. Loosen the
         sliders or enable “show non-recommended”.</p>`;
    return;
  }
  // Group by market so all Total Bases props sit together, all Hits
  // together, and so on — full cards, just organized.
  const groups = new Map();
  visible.forEach((r) => {
    const k = r.market_label || r.market || "Other";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  });
  const MARKET_ORDER = ["total bases", "hits", "home runs", "strikeouts",
                        "passing yards", "rushing yards", "receiving yards",
                        "receptions"];
  const keys = [...groups.keys()].sort((a, b) => {
    const ia = MARKET_ORDER.indexOf(a.toLowerCase());
    const ib = MARKET_ORDER.indexOf(b.toLowerCase());
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  host.innerHTML = keys.map((k) => {
    const rows = groups.get(k);
    const nRec = rows.filter((r) => r._ok).length;
    const hrNote = k.toLowerCase() === "home runs"
      ? ` · top 3 only — the full board is on the Long Shots page` : "";
    return `<div class="section-title" style="grid-column:1/-1;margin:14px 0 0">
        ${escapeHtml(k)} <span class="sub">— ${rows.length} prop(s)${nRec ? `, ${nRec} recommended` : ""}${hrNote}</span>
      </div>` + rows.map(cardHTML).join("");
  }).join("");
  // "Analyzed 1030 → showing 3" is alarming unless the page says where the
  // rest went: most are analyzed-but-held (lineups not confirmed, edge too
  // small, or no real price) and non-featured home runs live on Long Shots.
  const hidden = recs.length - visible.length;
  if (hidden > 0) {
    host.innerHTML += `<p class="loading" style="grid-column:1/-1;margin-top:14px">
      ${hidden} more analyzed prop(s) not shown — ${state.showAll
        ? "non-featured home runs live on the Long Shots page"
        : "held (unconfirmed lineup, edge below the bar, or no real price yet) or featured elsewhere. Toggle “show non-recommended” to browse everything"}.</p>`;
  }
  fillMeters(host);
  revealChildren(host);
}

function projBar(r) {
  const lo = Math.min(r.proj_low, r.line), hi = Math.max(r.proj_high, r.line);
  const pad = (hi - lo) * 0.15 || 1, min = lo - pad, max = hi + pad;
  const pos = (v) => `${((v - min) / (max - min)) * 100}%`;
  return `
    <div class="projbar">
      <div class="labels"><span>Projection vs line</span><span>${r.market_label}</span></div>
      <div class="track">
        <div class="range" style="left:${pos(r.proj_low)};width:${((r.proj_high - r.proj_low) / (max - min)) * 100}%"></div>
        <div class="line-dot" style="left:${pos(r.line)}"></div>
        <div class="proj-dot" style="left:${pos(r.projection)}"></div>
      </div>
      <div class="legend"><span class="proj">Proj ${r.projection}</span><span class="line">Line ${r.line}</span></div>
    </div>`;
}

function confMeter(r) {
  const w = `${(r.confidence / 10) * 100}%`;
  const color = r.confidence >= 8.5 ? "var(--good)" : r.confidence >= 7 ? "var(--cyan)" : r.confidence >= 5.5 ? "var(--warn)" : "var(--text-mute)";
  return `<div class="conf-wrap"><div class="conf-meter"><div class="conf-fill" data-w="${w}" style="background:${color}"></div></div>
    <div class="conf-num">${r.confidence.toFixed(1)}/10</div></div>`;
}

function trendChip(r) {
  if (r.trend === "up") return `<span class="chip up">📈 Trending up</span>`;
  if (r.trend === "down") return `<span class="chip down">📉 Cooling off</span>`;
  return `<span class="chip">Steady form</span>`;
}
function booksChip(r) {
  const n = (r.all_lines || []).length;
  return n <= 1 ? "" : `<span class="chip books">🛒 ${n} books · best ${escapeHtml(r.book)}</span>`;
}
function moveChip(r) {
  const m = r.line_move;
  if (!m) return "";
  const what = Math.abs(m.delta || 0) > 1e-9
    ? `${m.open} → ${m.current}`
    : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`;
  const withUs = m.verdict === "with";
  const icon = m.steam ? "🔥" : withUs ? "📈" : "📉";
  return `<span class="chip ${withUs ? "up" : "down"}" title="${withUs ? "Books have re-priced toward our side since our first snapshot" : "Books have re-priced away from our side since our first snapshot"}">${icon} Market ${withUs ? "with" : "against"} pick · ${what}</span>`;
}

function cardHTML(r) {
  const reasons = (r.reasons || []).map(reasonLI).join("");
  const warnings = (r.warnings || []).map((w) => `<div class="warning">⚠️ ${escapeHtml(w)}</div>`).join("");
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">${stakeTxt}</span>` : "";
  return `
    <article class="card ${r._ok ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team, { headshot: r.headshot })}
          <div>
            <div class="player">${escapeHtml(r.player)}</div>
            <div class="subtitle">${escapeHtml(r.team)} vs ${escapeHtml(r.opponent)} · ${escapeHtml(r.position)}</div>
            <div class="pick">${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}
              <span class="book">· ${escapeHtml(r.book)} ${american(r.odds)}</span></div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      ${projBar(r)}
      <div class="metrics">
        <div class="metric"><div class="k">Hit prob</div><div class="v">${pct(r.hit_prob)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v ${r.has_market === false ? "" : (r.edge >= 0 ? "pos" : "neg")}">${r.has_market === false ? "—" : signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">EV / unit</div><div class="v ${r.ev_per_unit >= 0 ? "pos" : "neg"}">${signedPct(r.ev_per_unit)}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips">${r.has_market === false ? `<span class="chip">No book line — model projection only</span>` : ""}${whenChip(r.game_date, r.game_kickoff)}${trendChip(r)}${moveChip(r)}${booksChip(r)}${stakeChip}</div>
      ${warnings}${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    </article>`;
}

/* ============================================================
   Long Shots — NFL anytime TDs / MLB home runs
   ============================================================ */
function renderLongShots() {
  const mlb = state.sport === "mlb";
  const picks = state.data.long_shots || [];
  const host = document.getElementById("longshots");
  const note = document.getElementById("longshots-note");
  document.getElementById("longshots-sub").textContent = mlb
    ? "— home runs, priced on contact quality, park & weather"
    : "— anytime touchdowns, priced on opportunity not hype";

  const watch = state.data.longshot_watch || [];
  if (!picks.length) {
    host.innerHTML = watchlistHTML(watch, mlb);
    note.innerHTML = watch.length
      ? `<div class="ls-note">No price clears the strict <b>value</b> bar right now —
         but the model still ranks tonight's most likely ${mlb ? "home runs" : "scorers"} below,
         with the price shown honestly so you can see what the book charges for them.</div>`
      : `<div class="empty-slate"><div class="es-icon">🎯</div>
      <div class="es-title">No ${mlb ? "home-run" : "touchdown"} board right now</div>
      <div class="es-sub">${escapeHtml(longshotEmptyReason(mlb))}</div></div>`;
    return;
  }
  note.innerHTML = `<div class="ls-note">Top ${picks.length} pick(s), ranked by
    <b>edge</b>, never by payout — the same ${picks.length === 1 ? "one" : picks.length}
    featured on the Recommended page. Every other real-priced
    ${mlb ? "home run" : "scorer"} is ranked below.</div>`;
  host.innerHTML = picks.map(longShotCard).join("") + watchlistHTML(watch, mlb);
  fillMeters(host);
  revealChildren(host);
}

function longshotEmptyReason(mlb) {
  const dg = state.data.longshot_diag;
  if (mlb && dg) {
    if (!dg.hr_props)
      return "No hitter props are built yet. Lineups aren't posted AND no recent " +
             "batting order could be projected — if games are on today, the next " +
             "refresh usually fixes this (the projector needs the free MLB Stats " +
             "API to be reachable).";
    if (!dg.real_priced)
      return `Lineups are in (${dg.hr_props} hitters) but no real home-run prices ` +
             "are attached yet — books post HR props close to game time, and the " +
             "board fills on the next odds refresh.";
    if (!dg.plus_money)
      return `${dg.real_priced} home-run price(s) are attached but none are ` +
             "plus-money in a believable range right now. This usually means " +
             "games are in progress (in-play prices) — tomorrow's board resets " +
             "with fresh pre-game quotes.";
    return `${dg.plus_money} real plus-money price(s) exist but every one failed ` +
           "a sanity guard (edge cap or odds window). If this persists on a " +
           "pre-game board, something is wrong — worth reporting.";
  }
  return "The model only surfaces " + (mlb ? "home-run" : "touchdown") +
         " picks that beat the book's price inside a sane odds range" +
         (mlb ? " (+250 to +650)." : " (-150 to +200).");
}

function watchlistHTML(watch, mlb) {
  if (!watch || !watch.length) return "";
  const rows = watch.map((r, i) => {
    const ev = (r.ev_per_unit * 100).toFixed(0);
    const evColor = r.ev_per_unit > 0 ? "var(--good, #3ddc84)" : "var(--text-mute, #889)";
    const spark = (r.recent_values || []).length > 2
      ? sparkline(r.recent_values, { line: 0.5, stroke: teamPrimary(r.team), w: 64, h: 22 })
      : "";
    return `<div style="display:flex;align-items:center;gap:12px;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);white-space:nowrap;overflow:hidden">
      <span style="opacity:.5;min-width:18px;font-size:.85em">${i + 1}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">
        <strong>${escapeHtml(r.player)}</strong>
        <span style="opacity:.55;font-size:.85em"> ${teamName(r.team)} vs ${teamName(r.opponent)}
          · ${escapeHtml(r.primary_reason || "")}</span></span>
      <span class="mini" style="flex:0 0 auto" title="Home runs, last ${(r.recent_values || []).length} games">${spark}</span>
      <span style="min-width:96px;text-align:right;opacity:.85;font-size:.9em">
        ${(r.model_prob * 100).toFixed(0)}% vs ${(r.implied_prob * 100).toFixed(0)}%</span>
      <span style="min-width:56px;text-align:right">${american(r.odds)}</span>
      <span style="min-width:64px;text-align:right;color:${evColor};font-size:.9em">${r.ev_per_unit > 0 ? "+" : ""}${ev}% EV</span>
    </div>`;
  }).join("");
  return `<div style="grid-column:1/-1;min-width:0">
    <div class="section-title" style="margin-top:20px">Most likely ${mlb ? "to homer" : "to score"} tonight
      <span class="sub">— model % vs the book's implied %. Positive EV = price worth taking;
      negative = likely but overpriced. Never a guarantee.</span></div>
    <div class="card" style="padding:0">${rows}</div></div>`;
}

function longShotCard(r) {
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const reasons = (r.reasons || []).slice(0, 6)
    .map(reasonLI).join("");
  const caveats = (r.caveats || [])
    .map((c) => `<div class="warning">⚠️ ${escapeHtml(c)}</div>`).join("");
  const oppLabel = state.sport === "mlb" ? "Expected PAs" : "RZ chances";
  return `
    <article class="card longshot" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team)}
          <div>
            <div class="player">${escapeHtml(r.player)} <span class="ml-odds">${american(r.odds)}</span></div>
            <div class="subtitle">${escapeHtml(r.matchup)}${whenLabel(r.game_date, r.game_kickoff)
              ? ` · ${escapeHtml(whenLabel(r.game_date, r.game_kickoff))}` : ""}</div>
            <div class="pick">${escapeHtml(r.market_label)}
              <span class="book">· ${escapeHtml(r.book)}</span></div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Model</div><div class="v">${pct(r.model_prob)}</div></div>
        <div class="metric"><div class="k">Book implied</div><div class="v">${pct(r.implied_prob)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">${oppLabel}</div><div class="v">${r.expected_opportunities}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips"><span class="chip stake">${stakeTxt}</span></div>
      <div class="ls-primary">${escapeHtml(r.primary_reason)}</div>
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
      ${caveats}
    </article>`;
}

/* ============================================================
   Trending view — momentum & value from the model
   ============================================================ */
function renderTrending() {
  const recs = state.data.recommendations;
  const risers = recs.filter((r) => (r.trend_delta || 0) > 0).sort((a, b) => b.trend_delta - a.trend_delta).slice(0, 6);
  const fallers = recs.filter((r) => (r.trend_delta || 0) < 0).sort((a, b) => a.trend_delta - b.trend_delta).slice(0, 6);
  const edges = [...recs].sort((a, b) => b.edge - a.edge).slice(0, 6);

  const cols = [
    { title: "🔥 Trending Up", sub: "Biggest recent-form risers", rows: risers, metric: (r) => `<span class="val pos">+${r.trend_delta}</span>`, stroke: "var(--good)" },
    { title: "❄️ Cooling Off", sub: "Production sliding vs prior form", rows: fallers, metric: (r) => `<span class="val neg">${r.trend_delta}</span>`, stroke: "var(--bad)" },
    { title: "💎 Biggest Edges", sub: "Model vs the sportsbook line", rows: edges, metric: (r) => `<span class="val cyan">${signedPct(r.edge)}</span>`, stroke: "var(--cyan)" },
  ];
  const host = document.getElementById("trending");
  host.innerHTML = cols.map((c) => `
    <div class="trend-col">
      <h3>${c.title}</h3><div class="colsub">${c.sub}</div>
      ${c.rows.length ? c.rows.map((r, i) => trendRow(r, i, c)).join("") : `<div class="empty" style="padding:24px">No movers.</div>`}
    </div>`).join("");
  revealChildren(host);
}

function trendRow(r, i, col) {
  const vals = (r.logs || []).map((l) => l.value);
  return `
    <div class="trow" onclick="openPlayer('${escapeHtml(r.player).replace(/'/g, "")}')">
      <div class="trank">${i + 1}</div>
      <div class="who"><div class="nm">${escapeHtml(r.player)}</div>
        <div class="mk">${escapeHtml(r.team)} · ${escapeHtml(r.market_label)}</div></div>
      <div class="mini">${sparkline(vals, { w: 78, h: 30, stroke: col.stroke })}</div>
      ${col.metric(r)}
    </div>`;
}

/* ============================================================
   Players view — search + profile
   ============================================================ */
function renderPlayers() {
  const q = state.search.trim().toLowerCase();
  let recs = state.data.recommendations;
  if (q) recs = recs.filter((r) => r.player.toLowerCase().includes(q));
  // one profile per player (first market listed)
  const seen = new Set();
  const players = recs.filter((r) => (seen.has(r.player) ? false : seen.add(r.player)));
  const host = document.getElementById("players");
  if (!players.length) {
    host.innerHTML = `<div class="empty">No players match “${escapeHtml(state.search)}”.</div>`;
    return;
  }
  host.innerHTML = players.map(profileHTML).join("");
  fillMeters(host);
  revealChildren(host);
}

function profileHTML(r) {
  const f = r.form || {};
  const tiles = [["L1", f.last1], ["L3", f.last3], ["L5", f.last5], ["L10", f.last10], ["Season", f.season]]
    .map(([k, v]) => `<div class="form-tile"><div class="k">${k}</div><div class="v">${v == null ? "—" : v}</div></div>`).join("");
  const vals = (r.logs || []).map((l) => l.value);
  // MLB logs are one GAME per row (with a real date); NFL logs are weeks.
  const mlb = state.sport === "mlb";
  const rows = (r.logs || []).map((l) => {
    const hit = l.value > r.line;
    const when = mlb && l.date ? formatGameDate(l.date) : `Wk ${l.week}`;
    return `<tr><td>${escapeHtml(when)}</td><td>${l.home ? "vs" : "@"} ${escapeHtml(l.opponent)}</td>
      <td class="num ${hit ? "hit" : "miss"}">${l.value}</td></tr>`;
  }).join("");
  const grad = `linear-gradient(135deg, ${teamPrimary(r.team)}, transparent)`;
  return `
    <article class="profile" style="--profile-grad:${grad}">
      <div class="profile-head">
        ${playerAvatar(r.player, r.team, { size: 60, headshot: r.headshot })}
        <div class="meta"><div class="nm">${escapeHtml(r.player)}</div>
          <div class="sub">${teamMark(r.team, 16)} ${escapeHtml(teamName(r.team))} · ${escapeHtml(r.position)} · vs ${escapeHtml(r.opponent)}</div></div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="form-tiles">${tiles}</div>
      <div class="profile-spark">${sparkline(vals, {
        line: r.line, stroke: teamPrimary(r.team), h: 72,
        labels: (r.logs || []).map((l) =>
          `${mlb && l.date ? formatGameDate(l.date) : "Wk " + l.week} ${l.home ? "vs" : "@"} ${l.opponent}`),
      })}</div>
      <table class="log-table">
        <tr><th>${mlb ? "Game" : "Week"}</th><th>Opponent</th><th style="text-align:right">${escapeHtml(r.market_label)}</th></tr>
        ${rows}
      </table>
      <div class="profile-pick">
        <div class="lbl">${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}
          <small>${escapeHtml(r.book)} ${american(r.odds)} · proj ${r.projection} · edge ${signedPct(r.edge)}</small></div>
        <div style="min-width:120px">${confMeter(r)}</div>
      </div>
    </article>`;
}

function openPlayer(name) {
  state.search = name;
  document.getElementById("player-search").value = name;
  switchView("players");
  renderPlayers();
}

/* ---------------- count-up ---------------- */
function countUp(el) {
  const to = parseFloat(el.dataset.to) || 0, dec = +el.dataset.dec || 0;
  const pre = el.dataset.pre || "", suf = el.dataset.suf || "";
  const final = pre + to.toFixed(dec) + suf;
  const dur = 700, t0 = performance.now();
  (function tick(t) {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = pre + (to * e).toFixed(dec) + suf;
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
  // Safety net: guarantee the true value even if rAF is throttled/stalled.
  setTimeout(() => { el.textContent = final; }, dur + 120);
}

/* ---------------- routing ---------------- */
/* ============================================================
   Track Record — the journal, on the site
   ============================================================ */
function recTile(label, value, sub) {
  return `<div class="stat"><div class="stat-k">${label}</div>
    <div class="stat-v">${value}</div>${sub ? `<div class="stat-sub" style="opacity:.6;font-size:.8em">${sub}</div>` : ""}</div>`;
}

function recBucketTable(title, bucket) {
  const keys = Object.keys(bucket || {});
  if (!keys.length) return "";
  const rows = keys
    .sort((a, b) => (bucket[b].w + bucket[b].l) - (bucket[a].w + bucket[a].l))
    .map((k) => {
      const d = bucket[k];
      const net = d.net_u || 0;
      const clv = d.avg_clv != null
        ? `<span style="min-width:78px;text-align:right;opacity:.7;font-size:.9em"
             title="Average closing-line value — beating the close is the earliest sign a module earns">
             CLV ${d.avg_clv >= 0 ? "+" : ""}${d.avg_clv.toFixed(2)}</span>` : "";
      return `<div style="display:flex;gap:12px;padding:6px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
        <span style="flex:1">${escapeHtml(k)}</span>
        <span style="min-width:70px;text-align:right">${d.w}-${d.l}</span>${clv}
        <span style="min-width:80px;text-align:right;color:${net >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)"}">
          ${net >= 0 ? "+" : ""}${net.toFixed(2)}u</span></div>`;
    }).join("");
  return `<div style="min-width:0"><div class="section-title" style="margin-top:16px">${title}</div>
    <div class="card" style="padding:0">${rows}</div></div>`;
}

function recCurveChart(curve) {
  if (!curve || curve.length < 2) return "";
  const w = 640, h = 190, padL = 46, padR = 14, padT = 16, padB = 28;
  const cums = curve.map((p) => p.cum_u);
  let lo = Math.min(0, ...cums), hi = Math.max(0, ...cums);
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const x = (i) => padL + (i / (curve.length - 1)) * (w - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
  const path = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.cum_u).toFixed(1)}`).join(" L");
  const last = curve[curve.length - 1];
  const color = last.cum_u >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)";
  const dots = curve.map((p, i) => {
    const tip = `${p.date} · day ${p.day_u >= 0 ? "+" : ""}${p.day_u.toFixed(2)}u (${p.n} bet${p.n === 1 ? "" : "s"}) · running ${p.cum_u >= 0 ? "+" : ""}${p.cum_u.toFixed(2)}u`;
    return `<circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="${i === curve.length - 1 ? 3.4 : 2.4}" fill="${color}"/>
      <circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="10" fill="transparent"
        style="pointer-events:all;cursor:pointer" data-tip="${escapeHtml(tip)}"/>`;
  }).join("");
  const yLabel = (v) => `<text x="${padL - 6}" y="${y(v) + 3.5}" text-anchor="end" font-size="10"
      fill="currentColor" opacity="0.5">${v >= 0 ? "+" : ""}${v.toFixed(1)}u</text>`;
  return `
    <div class="section-title" style="margin-top:18px">Running P&amp;L — every settled pick, by slate date</div>
    <div class="card" style="padding:12px 8px 6px">
      <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block" role="img"
           aria-label="Cumulative units won or lost over time">
        <line x1="${padL}" y1="${y(0)}" x2="${w - padR}" y2="${y(0)}"
              stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" opacity="0.25"/>
        ${yLabel(hi)}${yLabel(0)}${lo < 0 ? yLabel(lo) : ""}
        <text x="${padL}" y="${h - 8}" font-size="10" fill="currentColor" opacity="0.5">${escapeHtml(curve[0].date)}</text>
        <text x="${w - padR}" y="${h - 8}" text-anchor="end" font-size="10" fill="currentColor" opacity="0.5">${escapeHtml(last.date)}</text>
        <path d="M${path}" fill="none" stroke="${color}" stroke-width="2"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
      </svg>
      <div style="opacity:.55;font-size:.8em;padding:2px 8px 6px">Hover a dot for that day's bets. Flat units — every pick weighted by its stake, no bankroll compounding.</div>
    </div>`;
}

function recLongshotSection(ls) {
  if (!ls || (!ls.settled && !ls.open)) return "";
  const graded = ls.wins + ls.losses;
  const hitRate = graded ? (ls.wins / graded) * 100 : 0;
  const calib = ls.avg_model_prob != null
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px">
         Calibration: model claimed <strong>${(ls.avg_model_prob * 100).toFixed(1)}%</strong>
         on average · books implied <strong>${(ls.avg_implied_prob * 100).toFixed(1)}%</strong>
         · actually hit <strong>${(ls.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Model above books AND actual above implied = the board finds real value.</div>` : "";
  const rows = (ls.recent || []).map((b) => {
    const won = b.status === "won";
    const pnl = b.pnl_units || 0;
    return `<div style="display:flex;gap:12px;padding:7px 14px;align-items:center;
        border-bottom:1px solid rgba(255,255,255,.05);white-space:nowrap;overflow:hidden">
      <span>${won ? "💣" : "▫️"}</span>
      <span style="opacity:.55;min-width:82px;font-size:.85em">${escapeHtml(b.date || "")}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">
        <strong>${escapeHtml(b.player)}</strong>
        <span style="opacity:.6"> HR ${b.hit_prob != null ? `· model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span></span>
      <span style="min-width:56px;text-align:right">${american(b.odds)}</span>
      <span style="min-width:70px;text-align:right;color:${pnl >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)"}">
        ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title" style="margin-top:22px">Long Shots — tracked separately</div>
    <p style="opacity:.6;font-size:.85em;margin:4px 0 10px">Every home-run pick and
      watchlist entry, graded at a flat 0.1u nominal stake with zero bankroll impact.
      This bucket measures whether the HR board finds value — it is never mixed into
      the record above. Long shots lose most nights by design; judge the ROI and
      calibration over weeks, not the hit column.</p>
    <div class="stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px">
      ${recTile("HR record", `${ls.wins}-${ls.losses}`, `${ls.open} open`)}
      ${recTile("Hit rate", hitRate.toFixed(1) + "%", "plus-money — low is normal")}
      ${recTile("Flat-stake ROI", (ls.roi >= 0 ? "+" : "") + (ls.roi * 100).toFixed(1) + "%",
                `${ls.net_units >= 0 ? "+" : ""}${(ls.net_units || 0).toFixed(2)}u at 0.1u each`)}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${calib}${rows ||
      `<p class="loading" style="padding:12px">Nothing settled yet — accrues from tonight's board.</p>`}</div>`;
}

/* Calibration: when the model said X%, how often did it actually happen.
   Rendered as honest rows with a sample-size band — small buckets read as
   "too early", never as verdicts. */
function recCalibrationSection(cal) {
  if (!cal || !cal.n || !(cal.buckets || []).length) return "";
  const rows = cal.buckets.map((b) => {
    const off = Math.abs(b.actual - b.predicted);
    const flag = b.n < 20 ? `<span style="opacity:.5">n=${b.n} — too early</span>`
      : b.in_band ? `<span style="color:var(--good)">✓ within noise (n=${b.n})</span>`
      : `<span style="color:var(--warn)">⚠️ off by ${(off * 100).toFixed(0)} pts (n=${b.n})</span>`;
    const bar = (v, color) => `<span style="display:inline-block;height:8px;border-radius:4px;
        width:${Math.max(2, v * 100)}px;background:${color};vertical-align:middle"></span>`;
    return `<div style="display:flex;gap:12px;align-items:center;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);flex-wrap:wrap">
      <span style="min-width:78px;opacity:.7">${b.lo}–${b.hi}%</span>
      <span style="flex:1;min-width:220px">
        ${bar(b.predicted, "var(--brand)")} <span style="font-size:.8em;opacity:.65">said ${(b.predicted * 100).toFixed(0)}%</span>
        &nbsp; ${bar(b.actual, b.in_band ? "var(--good)" : "var(--warn)")} <span style="font-size:.8em;opacity:.65">hit ${(b.actual * 100).toFixed(0)}%</span>
      </span>
      <span style="min-width:150px;text-align:right;font-size:.85em">${flag}</span>
    </div>`;
  }).join("");
  const brier = cal.brier_edge == null ? "" : cal.brier_edge > 0
    ? `<p style="padding:10px 14px;margin:0;font-size:.88em;color:var(--good)">Forecast test: the model's Brier score
       (${cal.brier_model}) beats the de-vigged market's (${cal.brier_market}) on the same bets — lower is better.
       That's the whole claim of this site in one number.</p>`
    : `<p style="padding:10px 14px;margin:0;font-size:.88em;color:var(--warn)">Forecast test: the de-vigged market's Brier score
       (${cal.brier_market}) still beats the model's (${cal.brier_model}) on our own picks. Shown anyway —
       a site that hides this number is a tout with a website.</p>`;
  return `<div class="section-title" style="margin-top:18px">Calibration — did "60%" mean 60%?
      <span class="sub">— every settled pick, bucketed by the model's claimed probability.</span></div>
    <div class="card" style="padding:0">${rows}${brier}</div>`;
}

/* Account health: how sharp our own journaled action looks per book —
   inference from our patterns, clearly labeled as such. */
function recHealthSection(h) {
  if (!h || !(h.books || []).length) return "";
  const bandColor = { low: "var(--good)", moderate: "var(--warn)", elevated: "var(--bad)" };
  const cards = h.books.map((b) => `
    <div class="card" style="padding:14px 16px">
      <div style="display:flex;align-items:center;gap:10px">
        <strong style="flex:1">${escapeHtml(b.book)}</strong>
        <span style="font-weight:800;color:${bandColor[b.band] || "var(--brand)"}">${b.score}</span>
        <span class="chip" style="color:${bandColor[b.band] || "var(--brand)"}">${b.band} limit risk</span>
      </div>
      <div style="font-size:.85em;color:var(--text-mute);margin-top:6px">
        ${b.bets} graded bets · beats the close ${b.beat_close_rate == null ? "—" : (b.beat_close_rate * 100).toFixed(0) + "%"}
        · ${(b.concentration * 100).toFixed(0)}% in ${escapeHtml(b.top_market)}</div>
      ${(b.drivers || []).length ? `<ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${b.drivers.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
      ${(b.actions || []).length ? `<div style="margin-top:8px;font-size:.85em">
        <span style="color:var(--brand);font-weight:700">To stay welcome:</span>
        <ul style="margin:4px 0 0;padding-left:18px;color:var(--text-body)">
        ${b.actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
    </div>`).join("");
  return `<div class="section-title" style="margin-top:18px">Account health
      <span class="sub">— books quietly limit winners; this estimates how limit-prone your action looks, per book.</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">${cards}</div>
    <p style="opacity:.55;font-size:.82em;margin-top:8px">${escapeHtml(h.disclaimer || "")}</p>`;
}

async function renderRecord() {
  const host = document.getElementById("record-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/record.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !d.overall || (!d.overall.settled && !d.overall.open)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">📒</div>
      <div class="es-title">No graded picks yet</div>
      <div class="es-sub">Every recommended pick is journaled automatically at its real
      price and grades itself once results are ingested (nightly, automatic).
      Check back after tonight's games settle — this page becomes the honest
      scoreboard for everything the model recommends.</div></div>`;
    return;
  }
  const o = d.overall;
  const small = o.settled < 100
    ? `<p class="loading" style="margin-top:10px">⚠️ ${o.settled} settled pick(s) —
       results this small are mostly luck. Judge the model after 100+, and judge
       the process by CLV before that.</p>` : "";
  host.innerHTML = `
    <div class="stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px">
      ${recTile("Record", `${o.wins}-${o.losses}-${o.pushes}`, `${o.open} open`)}
      ${recTile("Win rate", (o.win_rate * 100).toFixed(1) + "%", "break-even ≈ 52.4% at −110")}
      ${recTile("ROI", (o.roi >= 0 ? "+" : "") + (o.roi * 100).toFixed(1) + "%",
                `${o.net_units >= 0 ? "+" : ""}${o.net_units.toFixed(2)}u on ${(o.units_staked || 0).toFixed(1)}u staked`)}
      ${recTile("Avg CLV", o.avg_clv == null ? "—" : (o.avg_clv >= 0 ? "+" : "") + o.avg_clv.toFixed(2) + " pts",
                o.avg_clv == null ? "accrues as daily closes are captured" : "beat the close = sharp process")}
      ${(() => {
        const pr = o.process || {};
        const n = (pr.good || 0) + (pr.bad || 0) + (pr.flat || 0);
        return recTile("Process", n ? `${pr.good || 0}✓ ${pr.bad || 0}✗` : "—",
          n ? `${pr.lucky_wins || 0} lucky win(s) · ${pr.unlucky_losses || 0} good-bet loss(es)`
            : "grades the decision vs the close, not the result");
      })()}
    </div>
    <p style="opacity:.6;font-size:.85em;margin-top:10px">Journals every
      <strong>Recommended</strong> pick — player props and sharp-anchor game bets
      (moneylines &amp; totals) — at the real book price shown when it was
      recommended. One entry per player &amp; market per day. Long Shots are
      tracked in their own bucket below — never mixed into this record — and
      the Edge Board is a watchlist, not tracked bets.</p>
    ${small}
    ${recCurveChart(d.curve)}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">
      ${recBucketTable("By market", o.by_market)}
      ${recBucketTable("By side", o.by_side)}
      ${recBucketTable("By grade", o.by_grade)}
      ${recBucketTable("By book", o.by_book)}
    </div>
    <div class="section-title" style="margin-top:18px">Recent settled picks</div>
    <div class="card" style="padding:0">
      ${(d.recent || []).map((b) => {
        const won = b.status === "won";
        const push = b.status === "push";
        const icon = push ? "➖" : (won ? "✅" : "❌");
        const pnl = b.pnl_units || 0;
        // Process chip: judge the decision against the close, out loud.
        let procChip = `<span style="opacity:.35;font-size:.8em">no close</span>`;
        if (b.process === "bad" && won)
          procChip = `<span style="color:var(--warn);font-size:.8em" title="Won, but the market closed against us — a bad bet that got lucky">🍀 lucky</span>`;
        else if (b.process === "good" && b.status === "lost")
          procChip = `<span style="color:var(--good);font-size:.8em" title="Lost, but we beat the closing line — good bet, bad night">📐 beat close</span>`;
        else if (b.clv != null)
          procChip = `<span style="color:${b.clv >= 0 ? "var(--good)" : "var(--bad)"};font-size:.8em"
            title="Closing-line value — how far the market moved our way after the bet">${b.clv >= 0 ? "+" : ""}${b.clv.toFixed(1)} CLV</span>`;
        return `<div style="display:flex;gap:12px;padding:8px 14px;align-items:center;
            border-bottom:1px solid rgba(255,255,255,.05);white-space:nowrap;overflow:hidden">
          <span>${icon}</span>
          <span style="opacity:.55;min-width:82px;font-size:.85em">${escapeHtml(b.date || "")}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">
            <strong>${escapeHtml(b.player)}</strong>
            <span style="opacity:.6"> ${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
          <span style="min-width:82px;text-align:right">${procChip}</span>
          <span style="min-width:56px;text-align:right">${american(b.odds)}</span>
          <span style="min-width:70px;text-align:right;color:${pnl >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)"}">
            ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
        </div>`;
      }).join("") || `<p class="loading" style="padding:12px">Nothing settled yet.</p>`}
    </div>
    ${recCalibrationSection(d.calibration)}
    ${recHealthSection(d.account_health)}
    ${recLongshotSection(d.longshots)}
    <p style="opacity:.55;margin-top:10px;font-size:.85em">Updated ${escapeHtml(d.generated_at || "")}
      · settles automatically as results are ingested each day.</p>`;
}

/* ============================================================
   Odds status — say exactly why no real prices are attached
   ============================================================ */
function noMarketExplainer() {
  const os = state.data.odds_status;
  if (os && os.error)
    return `Odds feed problem on the last pull (${os.at || ""}): ${os.error} —
            the model keeps proxy lines and recommends nothing until real
            prices return.`;
  if (os && os.checked === false)
    return `The last refresh skipped the odds pull (budget pacing). Real
            prices attach on an upcoming cycle — no action needed.`;
  if (os && os.checked && os.matched === 0)
    return `The odds feed answered at ${os.at || "last refresh"} but had no
            player-prop prices yet (checked ${os.events} game(s)) — books post
            MLB props closer to first pitch. The board fills automatically as
            real prices arrive.`;
  return `Waiting on real sportsbook prices — picks are never recommended
          against placeholder lines. The board fills automatically as real
          prices arrive.`;
}

/* ============================================================
   Edge Board — every positively-priced bet, banded by odds
   ============================================================ */
const EDGE_BANDS = [
  ["Favorites (−105 and shorter)", (o) => o <= -105],
  ["Near even (−104 to +150)", (o) => o > -105 && o <= 150],
  ["Long odds (+151 and up)", (o) => o > 150],
];

function edgeBoardRows() {
  const props = (state.data.recommendations || [])
    .filter((r) => r.has_market !== false && (r.ev_per_unit || 0) > 0.005
                   && r.odds >= state.maxJuice)
    .map((r) => ({
      label: `${r.player} · ${r.side} ${r.line} ${r.market_label}`,
      sub: `${r.book || ""} · ${teamName(r.team)} vs ${teamName(r.opponent)}`,
      odds: r.odds, model: r.hit_prob, implied: r.fair_prob,
      ev: r.ev_per_unit, grade: r.grade, rec: r.recommended,
    }));
  const games = (state.data.game_bets || [])
    .filter((b) => b.grade !== "Pass" && (b.ev_per_unit || 0) > 0.005)
    .map((b) => ({
      label: b.pick_label, sub: `${b.matchup} · ${b.market_label}`,
      odds: b.odds, model: b.win_prob, implied: b.fair_prob,
      ev: b.ev_per_unit, grade: b.grade, rec: b.recommended,
    }));
  return [...props, ...games].sort((a, b) => b.ev - a.ev);
}

function edgeRowHTML(r, i) {
  const evPct = (r.ev * 100).toFixed(1);
  return `<div class="ls-row" style="display:flex;align-items:center;gap:14px;
       padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="opacity:.5;min-width:20px">${i + 1}</span>
    <span style="flex:1"><strong>${escapeHtml(r.label)}</strong>
      <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(r.sub)}</span></span>
    <span style="min-width:64px;text-align:right">${r.odds > 0 ? "+" : ""}${r.odds}</span>
    <span style="min-width:120px;text-align:right;opacity:.8">
      ${(r.model * 100).toFixed(0)}% vs ${(r.implied * 100).toFixed(0)}%</span>
    <span style="min-width:70px;text-align:right;color:var(--green,#3ddc84)">
      +${evPct}% EV</span>
    <span style="min-width:86px;text-align:right;opacity:.75">${r.rec ? "✅ " : ""}${escapeHtml(r.grade || "")}</span>
  </div>`;
}

function renderEdgeBoard() {
  const host = document.getElementById("edge-board");
  const note = document.getElementById("edge-note");
  if (!host) return;
  const rows = edgeBoardRows();
  if (!rows.length) {
    note.innerHTML = "";
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">📈</div>
      <h3>No positively-priced bets right now</h3>
      <p>${noMarketExplainer()}</p>
      <p style="opacity:.7">The Edge Board lists every bet whose real price
      beats the model's probability — including small edges and long odds that
      don't clear the Recommended bar. Expected value is honest math, not a
      guarantee: a +5% EV bet still loses often; the edge shows up over
      hundreds of bets.</p></div>`;
    return;
  }
  note.innerHTML = `${rows.length} positively-priced bet(s) on the board ·
    every number vs a real book price · ✅ = also on the Recommended page`;
  host.innerHTML = EDGE_BANDS.map(([title, test]) => {
    const band = rows.filter((r) => test(r.odds));
    if (!band.length) return "";
    return `<div class="section-title" style="margin-top:18px">${title}
        <span class="sub">— ${band.length} bet(s)</span></div>
      <div class="card" style="padding:0">${band.map(edgeRowHTML).join("")}</div>`;
  }).join("") || "";
}

/* ============================================================
   Market Scanner — arbitrage / middles / low holds / sharp money
   ============================================================ */
function scanPairRow(p, extra) {
  const leg = (side, l) =>
    `<span style="display:block"><strong>${side} ${l.line}</strong>
       <span style="opacity:.65">@ ${escapeHtml(l.book)} ${american(l.odds)}</span></span>`;
  return `<div style="display:flex;align-items:center;gap:14px;padding:11px 16px;
      border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="flex:1"><strong>${escapeHtml(p.bet)}</strong></span>
    <span style="min-width:170px">${leg("Over", p.over)}${leg("Under", p.under)}</span>
    <span style="min-width:150px;text-align:right">${extra}</span>
  </div>`;
}

function scanSection(title, sub, rows, rowFn, emptyText) {
  return `<div class="section-title" style="margin-top:20px">${title}
      <span class="sub">— ${sub}</span></div>
    <div class="card" style="padding:0">
      ${rows.length ? rows.map(rowFn).join("")
        : `<p class="loading" style="padding:12px">${emptyText}</p>`}
    </div>`;
}

function renderScanner() {
  const host = document.getElementById("scanner-body");
  if (!host) return;
  const scan = state.data.market_scan || {};
  const arbs = scan.arbs || [], middles = scan.middles || [], lows = scan.low_holds || [];

  // The scanner feeds on price DISAGREEMENT, which mostly appears when one
  // book moves before the others. On cached prices (one frozen frame per
  // budget pull) empty sections are the norm, not a bug — say so up front.
  const os = state.data.odds_status || {};
  const freshness = os.source === "cache"
    ? `<div class="ls-note">Prices are from the last budgeted pull (cached — no
       API spend). Arbs and middles come from catching books mid-move, so a
       single frozen snapshot rarely shows them; scanning sharpens when pulls
       resume normal frequency after the credit reset.</div>`
    : "";

  // Sharp money: anchor picks (priced off the sharp book's fair value) and
  // steam moves (several books re-pricing together = pro money footprint).
  const anchors = (state.data.game_bets || []).filter((b) =>
    (b.reasons || []).join(" ").toLowerCase().includes("sharp"));
  const steam = (state.data.recommendations || [])
    .filter((r) => r.line_move && r.line_move.steam)
    .map((r) => ({ r, m: r.line_move }));

  const stake = state.scanStake || 100;
  const stakeInput = `<div class="ls-note" style="display:flex;align-items:center;gap:8px">
    Total stake for the splits below: $
    <input id="scan-stake" type="number" min="10" step="10" value="${stake}"
      style="width:90px;background:transparent;color:inherit;border:1px solid rgba(255,255,255,.2);border-radius:6px;padding:4px 8px" />
  </div>`;

  host.innerHTML = freshness + stakeInput
    + scanSection("Arbitrage", "opposite sides priced so a margin is locked whichever way it lands — IF both legs fill at the shown prices before they move. Rare across US books and gone in minutes",
      arbs, (a) => {
        const so = stake * a.stake_over_pct, su = stake * (1 - a.stake_over_pct);
        const ret = stake * a.profit_pct;
        const suspect = a.suspect
          ? `<span style="display:block;color:var(--warn,#e8b33e);font-size:.85em">⚠️ 5%+ edge — likely a stale line or void risk; verify at both books</span>` : "";
        return scanPairRow(a,
          `<span style="color:var(--good,#3ddc84);font-weight:700">+${(a.profit_pct * 100).toFixed(2)}% · $${ret.toFixed(2)} locked</span>
           <span style="display:block;opacity:.7;font-size:.85em">$${so.toFixed(0)} Over / $${su.toFixed(0)} Under</span>${suspect}`);
      },
      "No arbitrage pairs right now. Real arbs across legal US books appear a few times a week and last minutes — this scanner checks every refresh.")
    + scanSection("Middles", "Over at a low line + Under at a higher one: land between them and BOTH win; miss and you only pay the vig. Ranked by EV from the sport's real outcome distribution — never by window width",
      middles, (m) => {
        const evLine = m.ev_per_unit != null
          ? `<span style="font-weight:700;color:${m.ev_per_unit >= 0 ? "var(--good,#3ddc84)" : "var(--text-mute,#889)"}">${m.ev_per_unit >= 0 ? "+" : ""}${(m.ev_per_unit * 100).toFixed(1)}% EV</span>
             <span style="display:block;opacity:.7;font-size:.85em">hits ${(m.middle_prob * 100).toFixed(0)}% of the time · both win +${(m.both_win_return * 100).toFixed(0)}% · worst ${(m.worst_case * 100).toFixed(0)}%</span>`
          : `<span style="font-weight:700">${m.gap} gap</span>
             <span style="display:block;opacity:.7;font-size:.85em">both win +${(m.both_win_return * 100).toFixed(0)}% · worst ${(m.worst_case * 100).toFixed(0)}%</span>`;
        return scanPairRow(m, evLine);
      },
      "No middle windows open — books currently agree on every line. Gaps open when one book moves before the others.")
    + scanSection("Low holds", "two-sided quotes under 2% combined juice — a turnover feature, not a profit feature: the cheapest way to churn promo/rollover volume or keep an account looking recreational",
      lows, (h) => scanPairRow(h,
        `<span style="font-weight:700">${(h.hold_pct * 100).toFixed(1)}% hold</span>
         <span style="display:block;opacity:.7;font-size:.85em">≈ $${(h.cost_per_1k != null ? h.cost_per_1k : h.hold_pct * 1000).toFixed(0)} per $1,000 bet through</span>`),
      "No low-hold pairs on the current board.")
    + `<div class="section-title" style="margin-top:20px">Sharp money
        <span class="sub">— where the professional side of the market is</span></div>
      <div class="card" style="padding:0">
        ${anchors.map((b) => `<div style="display:flex;align-items:center;gap:14px;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
            <span style="flex:1"><strong>${escapeHtml(b.pick_label || "")}</strong>
              <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(b.matchup || "")} · priced off the sharp book's fair value</span></span>
            <span style="min-width:64px;text-align:right">${american(b.odds)}</span>
            <span style="min-width:80px;text-align:right;color:var(--good,#3ddc84)">+${((b.ev_per_unit || 0) * 100).toFixed(1)}% EV</span>
          </div>`).join("")}
        ${steam.map(({ r, m }) => {
          // Every alert answers: is this still bettable, or already missed?
          const age = m.moved_ago_min;
          const cls = (age != null && age > 180)
            ? ["Stale", "var(--text-mute,#889)", "old move — informational only"]
            : ((r.ev_per_unit || 0) > 0
               ? ["Live", "var(--good,#3ddc84)", "value still available near the sharp number"]
               : ["Chase", "var(--warn,#e8b33e)", "line already moved past it — do not follow"]);
          return `<div style="display:flex;align-items:center;gap:14px;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
            <span>🔥</span>
            <span style="flex:1"><strong>${escapeHtml(r.player)} ${escapeHtml(r.market_label || "")}</strong>
              <span style="display:block;opacity:.6;font-size:.85em">steam — several books moved together, ${m.verdict === "with" ? "toward" : "against"} our ${escapeHtml(r.side || "")}${age != null ? ` · ${age < 60 ? age + "m" : Math.round(age / 60) + "h"} ago` : ""} · ${cls[2]}</span></span>
            <span style="min-width:56px;text-align:right;font-weight:700;color:${cls[1]}">${cls[0]}</span>
            <span style="min-width:120px;text-align:right;opacity:.8">${Math.abs(m.delta || 0) > 1e-9 ? `${m.open} → ${m.current}` : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`}</span>
          </div>`;
        }).join("")}
        ${!anchors.length && !steam.length ? `<p class="loading" style="padding:12px">
          Nothing sharp-flagged right now. Sharp-anchor picks appear when a soft book's
          price beats the sharp book's fair value; steam appears when several books
          re-price together inside an hour.</p>` : ""}
      </div>
      <p style="opacity:.55;font-size:.85em;margin-top:12px">Positive-EV bets live on the
      <b>Recommended</b> and <b>Edge Board</b> pages — that's the model's job. This page
      needs no model: it's the books disagreeing with each other. Arbitrage and middle
      prices move fast; verify at the book before betting. Books limit accounts that
      only arb — mix it into normal betting.</p>`;

  const inp = document.getElementById("scan-stake");
  if (inp) inp.addEventListener("change", () => {
    state.scanStake = Math.max(10, parseFloat(inp.value) || 100);
    renderScanner();
  });
}

/* ============================================================
   Prediction Market Intel — informed-flow detection (Polymarket)
   ============================================================ */
function intelStatus(status) {
  const map = {
    Live: ["var(--good,#3ddc84)", "value still available near the flagged entry"],
    Chasing: ["var(--warn,#e8b33e)", "price has already run — the edge is mostly gone"],
    Historical: ["var(--text-mute,#889)", "old flag, informational only"],
  };
  const [color, tip] = map[status] || ["inherit", ""];
  return `<span style="min-width:78px;text-align:right;font-weight:700;color:${color}" title="${tip}">${status}</span>`;
}

function shortWallet(w) {
  return w && w.length > 12 ? `${w.slice(0, 6)}…${w.slice(-4)}` : (w || "");
}

function pmSpark(series, w = 96, h = 30) {
  // 30-day cumulative P&L curve. Zero line dashed; color by where the
  // month ended.
  if (!series || series.length < 2) return "";
  const pad = 2;
  const vals = series.map((p) => p[1]);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const x = (i) => pad + (i / (series.length - 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" L");
  const last = vals[vals.length - 1];
  const color = last >= 0 ? "var(--good)" : "var(--bad)";
  const fmt = (v) => `${v < 0 ? "−" : "+"}$${Math.abs(Math.round(v)).toLocaleString()}`;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="display:block"
      data-tip="past month: ${fmt(vals[0])} → ${fmt(last)} (low ${fmt(Math.min(...vals))}, high ${fmt(Math.max(...vals))})">
    <line x1="${pad}" y1="${y(0).toFixed(1)}" x2="${w - pad}" y2="${y(0).toFixed(1)}"
      stroke="currentColor" stroke-width="0.7" stroke-dasharray="3 3" opacity="0.25"/>
    <path d="M${pts}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(series.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="2" fill="${color}"/>
  </svg>`;
}

function pmAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/* Polymarket and Fantasy are top-level modes next to NFL/MLB, not tabs
   inside a sport — entering one hides the sport nav; leaving restores it. */
const STANDALONE_MODES = ["intel", "fantasy", "nba", "ufc", "why"];

function enterStandaloneMode(name) {
  document.querySelectorAll(".sport-btn").forEach((x) =>
    x.classList.toggle("active", x.dataset.sport === name));
  const nav = document.getElementById("nav");
  if (nav) nav.style.display = "none";
  // Fantasy is NFL — avatars must draw helmets even if MLB was selected.
  if (name === "fantasy") window.ACTIVE_SPORT = "nfl";
  switchView(name);
}

function exitStandaloneMode() {
  const nav = document.getElementById("nav");
  if (nav) nav.style.display = "";
  document.querySelectorAll(".sport-btn").forEach((x) =>
    x.classList.toggle("active", x.dataset.sport === state.sport));
  window.ACTIVE_SPORT = state.sport;
  if (STANDALONE_MODES.includes(state.view)) {
    switchView("recommended");
    // Restore the sports slate's own data-source badge and date label.
    if (state.data) {
      renderDataSource(state.data);
      const el = document.getElementById("slate-date");
      if (el) el.textContent = slateDateLabel(state.data);
    }
  }
}

/* The header badge reflects the ACTIVE page. The sports slate may be on
   sample data (offseason) while Polymarket/Fantasy run on real feeds —
   showing "Sample data" over live pages was a lie of scope. */
function setStandaloneSource(label, dateLabel) {
  const el = document.getElementById("data-source");
  if (el) {
    el.className = "data-source live";
    el.innerHTML = `<span class="src-dot"></span>Live data`;
    el.title = label;
  }
  const dt = document.getElementById("slate-date");
  if (dt && dateLabel) dt.textContent = dateLabel;
}

async function renderIntel() {
  const host = document.getElementById("intel-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/predmarkets.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || (!(d.flow || []).length && !(d.markets || []).length)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🛰️</div>
      <div class="es-title">No prediction-market data yet</div>
      <div class="es-sub">The launcher pulls Polymarket's public market list and trade
      tape on every refresh (free, no key needed). If this persists, the machine may not
      be able to reach gamma-api.polymarket.com.</div></div>`;
    return;
  }
  setStandaloneSource("Polymarket public market + tape feeds", "Polymarket · live venue data");
  const tape = d.tape || {};
  const cents = (p) => p == null ? "—" : `${(p * 100).toFixed(0)}¢`;
  const usd = (v) => `$${Number(v || 0).toLocaleString()}`;
  const statusColor = { Live: "var(--good)", Chasing: "var(--warn)", Historical: "var(--text-mute)" };
  const heat = (s) => s >= 70 ? "var(--bad)" : s >= 40 ? "var(--warn)" : "var(--brand)";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div style="color:var(--text-mute);font-size:12px;margin-top:2px">${sub}</div>` : ""}</div>`;

  const flagCards = (d.flow || []).slice(0, 12).map((f) => {
    const color = statusColor[f.status] || "var(--brand)";
    const sigs = (f.signals || []).map((s) =>
      `<span class="chip" title="${escapeHtml(s.value)}">${escapeHtml(s.name)}</span>`).join("");
    return `<article class="card" style="--grade-color:${color}">
      <div class="card-head">
        <div class="card-id">
          <div class="score-ring" title="Composite informed-flow score (0–100)"
            style="background:conic-gradient(${heat(f.score)} ${f.score * 3.6}deg, rgba(255,255,255,.08) 0)">
            <span>${f.score}</span></div>
          <div>
            <div class="player"><a href="https://polymarket.com/profile/${escapeHtml(f.wallet)}"
              target="_blank" rel="noopener" style="color:inherit">${escapeHtml(f.name || shortWallet(f.wallet))}</a></div>
            <div class="subtitle">${pmAgo(f.ts)} · ${f.wallet_trades} trade(s) on our tape</div>
            <div class="pick">${escapeHtml(f.side)} ${escapeHtml(f.outcome)}
              <span class="book">· ${usd(f.usd)}</span></div>
          </div>
        </div>
        <span class="pm-status" style="color:${color}">${f.status.toUpperCase()}</span>
      </div>
      <div style="margin:8px 0 10px;font-weight:600;line-height:1.35">
        <a href="https://polymarket.com/market/${escapeHtml(f.slug)}" target="_blank"
           rel="noopener" style="color:inherit">${escapeHtml(f.market)}</a></div>
      <div class="metrics">
        <div class="metric"><div class="k">Position</div><div class="v">${usd(f.usd)}</div></div>
        <div class="metric"><div class="k">Entry</div><div class="v">${cents(f.entry_price)}</div></div>
        <div class="metric"><div class="k">Now</div><div class="v" style="color:${color}">${cents(f.current_price)}</div></div>
      </div>
      <div class="chips" style="margin-top:10px">${sigs}</div>
    </article>`;
  }).join("");

  const traderCards = (d.top_traders || []).map((t) => {
    const label = t.name || shortWallet(t.wallet);
    const initials = (t.name ? t.name.replace(/[^a-zA-Z0-9 ]/g, "").split(/\s+/)
      .map((w) => w[0]).slice(0, 2).join("") : t.wallet.slice(2, 4)) || "?";
    const last = (t.recent || [])[0];
    const lastTxt = last
      ? `${escapeHtml(last.side)} ${escapeHtml(last.outcome)} · ${usd(last.usd)} @ ${cents(last.price)} · ${escapeHtml(last.market)} · ${pmAgo(last.ts)}`
      : "no recent public trades pulled";
    return `<article class="card">
      <div class="card-head">
        <div class="card-id">
          <div class="pm-avatar">${escapeHtml(initials)}</div>
          <div>
            <div class="player">#${t.rank} <a href="https://polymarket.com/profile/${escapeHtml(t.wallet)}"
              target="_blank" rel="noopener" style="color:inherit">${escapeHtml(label)}</a></div>
            <div class="subtitle">${shortWallet(t.wallet)}</div>
          </div>
        </div>
        <span style="font-weight:800;font-size:19px;color:${t.pnl >= 0 ? "var(--good)" : "var(--bad)"}">
          ${t.pnl ? `${t.pnl >= 0 ? "+" : "−"}${usd(Math.abs(t.pnl))}` : "—"}</span>
      </div>
      ${t.pnl_series && t.pnl_series.length > 1
        ? `<div style="margin-top:10px">${pmSpark(t.pnl_series, 300, 62)}
           <div style="color:var(--text-mute);font-size:11.5px;margin-top:3px">Cumulative P&amp;L — past month (hover for numbers)</div></div>` : ""}
      <div style="margin-top:10px;color:var(--text-body);font-size:12.5px">
        <span style="color:var(--text-mute)">Latest:</span> ${lastTxt}</div>
    </article>`;
  }).join("");

  const marketRows = (d.markets || []).slice(0, 20).map((m, i) => `
    <div style="display:flex;align-items:center;gap:12px;padding:9px 16px;
        border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="opacity:.4;min-width:20px">${i + 1}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <a href="https://polymarket.com/market/${escapeHtml(m.slug)}" target="_blank" rel="noopener"
           style="color:inherit;font-weight:600">${escapeHtml(m.question)}</a></span>
      <span style="min-width:52px;text-align:right;font-weight:800">${cents(m.yes)}</span>
      <span style="min-width:110px;text-align:right;color:var(--text-mute)">${usd(m.vol24)} / 24h</span>
      <span style="min-width:80px;text-align:right;color:var(--text-mute);font-size:.85em">${escapeHtml(m.end_date || "")}</span>
    </div>`).join("");

  host.innerHTML = `
    <div class="stats">
      ${tile("Trades on tape", Number(tape.stored_total || 0).toLocaleString(), `+${tape.new_this_pull || 0} this pull`)}
      ${tile("Wallets seen", Number(tape.wallets_seen || 0).toLocaleString(), "recording since day one")}
      ${tile("Flow flags · 24h", (d.flow || []).length, "$5K+ scored trades")}
      ${tile("Updated", escapeHtml((d.generated_at || "").slice(11, 16)), "refreshes with the site")}
    </div>
    <div class="section-title">Informed flow
      <span class="sub">— large trades scored for anomaly signals, with receipts on every chip
      (hover). Probabilities, never verdicts.</span></div>
    <div class="cards">${flagCards ||
      `<div class="empty-slate" style="grid-column:1/-1"><div class="es-icon">📡</div>
        <div class="es-title">No flagged flow yet</div>
        <div class="es-sub">The feed scores the last 24h of recorded tape and accumulates
        across refreshes — big trades are a few per hour.</div></div>`}</div>
    ${intelReportCard(d.validation)}
    <div class="section-title" style="margin-top:26px">Top traders
      <span class="sub">— ${escapeHtml(d.traders_note || "by realized profit")}</span></div>
    <div class="cards">${traderCards ||
      `<p class="loading" style="grid-column:1/-1">No trader data yet — fills on the next refresh.</p>`}</div>
    <div class="section-title" style="margin-top:26px">Top markets
      <span class="sub">— live markets by 24h volume · YES price · resolution date</span></div>
    <div class="card" style="padding:0">${marketRows}</div>
    <p style="color:var(--text-mute);font-size:12.5px;margin-top:14px">Wallet-age signal
      matures as the tape accrues (it cannot be backfilled). Kalshi omitted: no public
      trader identity. Analyzing public flow is market research; what the CFTC prosecutes
      (2026) is trading on information <i>you</i> hold a duty to keep confidential.</p>`;
}

/* ============================================================
   Fantasy Football — usage trends, buy-low/sell-high, game scripts
   ============================================================ */
async function renderFantasy() {
  const host = document.getElementById("fantasy-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/fantasy.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !d.season) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🏆</div>
      <div class="es-title">No NFL usage data yet</div>
      <div class="es-sub">${escapeHtml((d && d.note) || "Run `python3 ingest.py nfl` once — usage rows (targets, carries, air yards, PPR points) ride along with the normal player-log ingest, then this page fills automatically.")}</div></div>`;
    return;
  }
  setStandaloneSource(`Ingested NFL ${d.season} weekly stats (nflverse)`,
                      `NFL ${d.season} · ingested history`);
  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(0)}%`;
  const deltaChip = (dv) => {
    if (dv == null || Math.abs(dv) < 0.03) return `<span class="chip">steady</span>`;
    return dv > 0
      ? `<span class="chip up">▲ +${(dv * 100).toFixed(0)}pt vs 4wk</span>`
      : `<span class="chip down">▼ ${(dv * 100).toFixed(0)}pt vs 4wk</span>`;
  };

  const usageRow = (u) => `
    <div style="display:flex;align-items:center;gap:12px;padding:8px 16px;
        border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:0 0 auto">${playerAvatar(u.player, u.team)}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <strong>${escapeHtml(u.player)}</strong>
        <span style="color:var(--text-mute)"> ${escapeHtml(u.position)} · ${teamName(u.team)} · ${escapeHtml(u.metric)}</span></span>
      <span style="min-width:64px;text-align:right" title="season average">${pct(u.season)}</span>
      <span style="min-width:64px;text-align:right;color:var(--text-dim)" title="4-week average">${pct(u.l4)}</span>
      <span style="min-width:64px;text-align:right;font-weight:700" title="most recent week">${pct(u.last)}</span>
      <span style="min-width:120px;text-align:right">${deltaChip(u.delta)}</span>
      <span style="min-width:78px;text-align:right;color:var(--text-dim)"
        title="TD equity from play-by-play">${u.rz_pg != null ? `${u.rz_pg} ${escapeHtml(u.rz_label || "RZ/g")}` : "—"}</span>
      <span style="min-width:70px;text-align:right;color:var(--text-mute)">${u.fp_pg} ppg</span>
    </div>`;
  const usageRows = (d.usage || []).slice(0, 40).map(usageRow).join("");

  const bs = d.buy_sell || {};
  const tradeCard = (r, kind) => {
    const buy = kind === "buy";
    return `<article class="card" style="--grade-color:${buy ? "var(--good)" : "var(--warn)"}">
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team)}
          <div><div class="player">${escapeHtml(r.player)}</div>
            <div class="subtitle">${escapeHtml(r.position)} · ${teamName(r.team)} ·
              ${r.targets_pg} tgt/g · ${r.carries_pg} car/g</div></div>
        </div>
        <span class="pm-status" style="color:${buy ? "var(--good)" : "var(--warn)"}">${buy ? "BUY LOW" : "SELL HIGH"}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Actual</div><div class="v">${r.actual_ppg}</div></div>
        <div class="metric"><div class="k">${r.basis === "xfp" ? "xFP says" : "Volume says"}</div><div class="v">${r.expected_ppg}</div></div>
        <div class="metric"><div class="k">Gap</div><div class="v ${r.gap < 0 ? "pos" : "neg"}">${r.gap > 0 ? "+" : ""}${r.gap}</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:12.5px">
        ${r.basis === "xfp"
          ? (buy ? "Expected points value every opportunity by WHERE it happened — his say the production is coming."
                 : "Scoring above what his situations support — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")
          : (buy ? "Usage says the production is coming — the volume is already there."
                 : "Producing above what the opportunity supports — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")}</div>
    </article>`;
  };

  const scriptCards = (d.scripts || []).slice(0, 16).map((s) => `
    <article class="card">
      <div class="card-head">
        <div><div class="player">${escapeHtml(s.away)} @ ${escapeHtml(s.home)}</div>
          <div class="subtitle">Week ${parseInt(s.week, 10) || escapeHtml(s.week)} · total ${s.total} · ${escapeHtml(s.favorite)} −${Math.abs(s.spread)}</div></div>
        <span class="chip">${escapeHtml(s.archetype)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">${escapeHtml(s.home)} implied</div><div class="v">${s.home_implied}</div></div>
        <div class="metric"><div class="k">${escapeHtml(s.away)} implied</div><div class="v">${s.away_implied}</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:12.5px">${escapeHtml(s.read)}</div>
      ${s.home_proe != null || s.away_proe != null
        ? `<div style="margin-top:6px;color:var(--text-dim);font-size:12px" title="Pass rate over expectation — intent vs situation, the stable half of game script">
            PROE: ${escapeHtml(s.home)} ${s.home_proe != null ? `${s.home_proe >= 0 ? "+" : ""}${(s.home_proe * 100).toFixed(1)}%` : "—"}
            · ${escapeHtml(s.away)} ${s.away_proe != null ? `${s.away_proe >= 0 ? "+" : ""}${(s.away_proe * 100).toFixed(1)}%` : "—"}</div>` : ""}
      <div style="margin-top:6px;color:var(--text-mute);font-size:12px">Script confidence: ${escapeHtml(s.confidence)}</div>
    </article>`).join("");

  const bsCount = (bs.buy_low || []).length + (bs.sell_high || []).length;
  host.innerHTML = `
    <div class="stats">
      <div class="tile"><div class="k">Season</div><div class="v">${d.season}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">${d.season < new Date().getFullYear()
          ? "last completed — live weekly in Sept" : "updating weekly"}</div></div>
      <div class="tile"><div class="k">Usage movers</div><div class="v">${(d.usage || []).length}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">biggest role changes tracked</div></div>
      <div class="tile"><div class="k">Trade flags</div><div class="v">${bsCount}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">outside the sustainable band</div></div>
      <div class="tile"><div class="k">Game scripts</div><div class="v">${(d.scripts || []).length}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">games with posted lines</div></div>
    </div>
    <div id="sleeper-zone"></div>
    <div class="ls-note">Shares are of TEAM volume: targets for WR/TE/QB, carries for RB.
      The delta column is the money — a riser at 42% beats a flat 60%.</div>
    <div class="section-title" style="margin-top:16px">Usage movers
      <span class="sub">— season vs 4-week vs last week, biggest role changes first</span></div>
    <div class="card" style="padding:0">
      <div style="display:flex;gap:12px;padding:8px 16px;border-bottom:1px solid rgba(255,255,255,.08);
          color:var(--text-mute);font-size:11.5px;text-transform:uppercase;letter-spacing:.06em">
        <span style="flex:1">Player</span><span style="min-width:64px;text-align:right">Season</span>
        <span style="min-width:64px;text-align:right">4-week</span><span style="min-width:64px;text-align:right">Last</span>
        <span style="min-width:120px;text-align:right">Trend</span><span style="min-width:70px;text-align:right">PPR</span>
      </div>
      ${usageRows || `<p class="loading" style="padding:12px">No usage rows for this season yet.</p>`}
    </div>
    <div class="section-title" style="margin-top:26px">Buy low
      <span class="sub">— volume-expected points say the production is coming</span></div>
    <div class="cards">${(bs.buy_low || []).map((r) => tradeCard(r, "buy")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
    <div class="section-title" style="margin-top:26px">Sell high
      <span class="sub">— outrunning their opportunity; regression risk</span></div>
    <div class="cards">${(bs.sell_high || []).map((r) => tradeCard(r, "sell")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
    <div class="section-title" style="margin-top:26px">Game scripts
      <span class="sub">— Vegas is the input: implied totals, archetypes, and confidence that
      scales with the spread</span></div>
    <div class="cards">${scriptCards ||
      `<p class="loading" style="grid-column:1/-1">No upcoming NFL games with posted spreads and
       totals in the DB yet — fills when next season's lines are ingested.</p>`}</div>
    <p style="color:var(--text-mute);font-size:12.5px;margin-top:14px">Expected points are
      fit from this season's own data (league value per target and per carry by position) —
      volume-based, so a player can legitimately sustain a positive gap; only gaps beyond
      ~${bs.band || 1.5} PPG are flagged. Updated ${escapeHtml(d.generated_at || "")}.</p>`;
  renderSleeperZone(d);
}

function intelReportCard(v) {
  const head = `<div class="section-title" style="margin-top:26px">Flag report card
      <span class="sub">— do our flags actually win? Every flag is stored and graded when
      its market resolves. Published, not promised.</span></div>`;
  if (!v || !v.graded) {
    return `${head}<div class="card"><p class="loading" style="margin:0">No graded flags yet —
      flags settle when their markets resolve, so this fills as resolutions land.
      The recording started the moment the flow feed first ran.</p></div>`;
  }
  const pctv = (x) => `${(x * 100).toFixed(1)}%`;
  const zColor = v.z >= 1 ? "var(--good)" : v.z <= -1 ? "var(--bad)" : "var(--text)";
  const bands = (v.by_score || []).map((b) => `
    <div style="display:flex;gap:12px;padding:7px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:1">Score ${escapeHtml(b.band)}</span>
      <span style="min-width:60px;text-align:right">${b.wins}-${b.n - b.wins}</span>
      <span style="min-width:120px;text-align:right;opacity:.8">${pctv(b.hit_rate)} vs ${pctv(b.avg_implied)} implied</span>
      <span style="min-width:80px;text-align:right;color:${b.roi >= 0 ? "var(--good)" : "var(--bad)"}">${b.roi >= 0 ? "+" : ""}${pctv(b.roi)} ROI</span>
    </div>`).join("");
  const wallets = (v.wallets || []).map((w) => `
    <div style="display:flex;gap:12px;padding:7px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:1"><a href="https://polymarket.com/profile/${escapeHtml(w.wallet)}" target="_blank"
        rel="noopener" style="color:inherit">${escapeHtml(w.name || shortWallet(w.wallet))}</a></span>
      <span style="min-width:60px;text-align:right">${w.wins}-${w.n - w.wins}</span>
      <span style="min-width:120px;text-align:right;opacity:.8">${pctv(w.hit_rate)} vs ${pctv(w.avg_implied)}</span>
      <span style="min-width:70px;text-align:right;font-weight:700" title="calibration z — higher = less like luck">z ${w.z}</span>
    </div>`).join("");
  return `${head}
    <div class="stats">
      <div class="tile"><div class="k">Flags graded</div><div class="v">${v.graded}</div></div>
      <div class="tile"><div class="k">Hit rate</div><div class="v">${pctv(v.hit_rate)}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">prices implied ${pctv(v.avg_implied)}</div></div>
      <div class="tile"><div class="k">Flat-stake ROI</div><div class="v ${v.roi >= 0 ? "pos" : ""}">${v.roi >= 0 ? "+" : ""}${pctv(v.roi)}</div></div>
      <div class="tile"><div class="k">Calibration z</div><div class="v" style="color:${zColor}">${v.z}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">above 0 = flags beat their price</div></div>
    </div>
    ${bands ? `<div class="card" style="padding:0">${bands}</div>` : ""}
    ${wallets ? `<div class="section-title" style="margin-top:14px">Wallets least like luck
        <span class="sub">— graded flags only, min 3, ranked by calibration z</span></div>
      <div class="card" style="padding:0">${wallets}</div>` : ""}`;
}

/* ---------------- Sleeper league sync (free, read-only, no key) ---------- */
function ffNorm(s) {
  return String(s || "").toLowerCase().normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").replace(/[.'’`-]/g, " ")
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "").replace(/\s+/g, " ").trim();
}

async function sleeperGet(path) {
  const r = await fetch("/api/sleeper/" + path);
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && body.error) || `Sleeper request failed (${r.status})`);
  return body;
}

function sleeperConnectHTML(msg) {
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head"><div><div class="player">My league — Sleeper sync</div>
      <div class="subtitle">Free and read-only: see YOUR roster's usage trends, trade flags,
        and who's unrostered in YOUR league. No password — just your Sleeper username.</div></div></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
      <input id="sleeper-username" type="text" placeholder="Sleeper username"
        style="flex:1;min-width:180px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-family:inherit"/>
      <button class="btn" id="sleeper-connect">Connect</button>
    </div>
    ${msg ? `<div class="warning" style="margin-top:10px">⚠️ ${escapeHtml(msg)}</div>` : ""}
  </div>`;
}

async function renderSleeperZone(d, errMsg) {
  const zone = document.getElementById("sleeper-zone");
  if (!zone) return;
  const username = localStorage.getItem("ff_user");
  if (!username) {
    zone.innerHTML = sleeperConnectHTML(errMsg);
    const btn = document.getElementById("sleeper-connect");
    if (btn) btn.addEventListener("click", () => {
      const v = (document.getElementById("sleeper-username").value || "").trim();
      if (!v) return;
      localStorage.setItem("ff_user", v);
      renderSleeperZone(d);
    });
    return;
  }
  zone.innerHTML = `<p class="loading">Syncing ${escapeHtml(username)}'s Sleeper leagues…</p>`;
  try {
    const user = await sleeperGet(`user/${encodeURIComponent(username)}`);
    if (!user || !user.user_id) throw new Error(`No Sleeper user named “${username}”`);
    let seasonTried = new Date().getFullYear();
    let leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${seasonTried}`) || [];
    if (!leagues.length) {
      seasonTried -= 1;
      leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${seasonTried}`) || [];
    }
    if (!leagues.length) throw new Error("No NFL leagues found on that account");
    let leagueId = localStorage.getItem("ff_league");
    if (!leagues.some((l) => l.league_id === leagueId)) leagueId = leagues[0].league_id;
    const [rosters, lgUsers] = await Promise.all([
      sleeperGet(`league/${leagueId}/rosters`),
      sleeperGet(`league/${leagueId}/users`),
    ]);
    if (!window._slPlayers) window._slPlayers = await sleeperGet("players/nfl");
    renderSleeperPanel(d, { username, user, leagues, leagueId, rosters,
                            lgUsers, seasonTried });
  } catch (e) {
    localStorage.removeItem("ff_user");
    renderSleeperZone(d, String(e.message || e));
  }
}

function renderSleeperPanel(d, ctx) {
  const zone = document.getElementById("sleeper-zone");
  const players = window._slPlayers || {};
  const usageByName = {};
  (d.usage || []).forEach((u) => { usageByName[ffNorm(u.player)] = u; });
  const flagByName = {};
  ((d.buy_sell || {}).buy_low || []).forEach((r) => { flagByName[ffNorm(r.player)] = "BUY LOW"; });
  ((d.buy_sell || {}).sell_high || []).forEach((r) => { flagByName[ffNorm(r.player)] = "SELL HIGH"; });

  const mine = (ctx.rosters || []).find((r) => r.owner_id === ctx.user.user_id
    || (r.co_owners || []).includes(ctx.user.user_id));
  const takenNames = new Set();
  (ctx.rosters || []).forEach((r) => (r.players || []).forEach((pid) => {
    const p = players[pid];
    if (p) takenNames.add(ffNorm(`${p.first_name} ${p.last_name}`));
  }));

  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(0)}%`;
  const POS_ORDER = { QB: 0, RB: 1, WR: 2, TE: 3, K: 4, DEF: 5 };
  const myRows = (mine ? (mine.players || []) : []).map((pid) => {
    const p = players[pid];
    if (!p || !["QB", "RB", "WR", "TE"].includes(p.position)) return null;
    const name = `${p.first_name} ${p.last_name}`;
    const u = usageByName[ffNorm(name)];
    const flag = flagByName[ffNorm(name)];
    return { name, pos: p.position, team: p.team || "", u, flag,
             starter: (mine.starters || []).includes(pid) };
  }).filter(Boolean).sort((a, b) =>
    (POS_ORDER[a.pos] ?? 9) - (POS_ORDER[b.pos] ?? 9)
    || (b.u ? b.u.fp_pg : 0) - (a.u ? a.u.fp_pg : 0));

  const rowHTML = (r) => `
    <div style="display:flex;align-items:center;gap:12px;padding:8px 16px;
        border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:0 0 auto">${playerAvatar(r.name, r.team)}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <strong>${escapeHtml(r.name)}</strong>
        <span style="color:var(--text-mute)"> ${escapeHtml(r.pos)} · ${escapeHtml(r.team || "FA")}${r.starter ? " · starter" : ""}</span>
        ${r.flag ? `<span class="chip ${r.flag === "BUY LOW" ? "up" : "down"}" style="margin-left:6px">${r.flag}</span>` : ""}</span>
      ${r.u ? `<span style="min-width:150px;text-align:right;color:var(--text-dim)"
          title="season · 4-week · last week ${r.u.metric}">${pct(r.u.season)} → ${pct(r.u.l4)} → <b>${pct(r.u.last)}</b></span>
        <span style="min-width:70px;text-align:right;color:var(--text-mute)">${r.u.fp_pg} ppg</span>`
      : `<span style="min-width:220px;text-align:right;color:var(--text-mute)">not among the top usage movers</span>`}
    </div>`;

  const waivers = (d.usage || []).filter((u) =>
    (u.delta || 0) >= 0.03 && !takenNames.has(ffNorm(u.player))).slice(0, 8);

  const leagueOpts = ctx.leagues.map((l) =>
    `<option value="${escapeHtml(l.league_id)}" ${l.league_id === ctx.leagueId ? "selected" : ""}>
       ${escapeHtml(l.name || l.league_id)}</option>`).join("");

  zone.innerHTML = `<div class="card" style="margin-bottom:16px;padding-bottom:6px">
    <div class="card-head">
      <div><div class="player">My league — ${escapeHtml(ctx.username)}</div>
        <div class="subtitle">Sleeper · season ${ctx.seasonTried} · roster read-only</div></div>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="sleeper-league" style="background:var(--panel-2);color:inherit;
          border:1px solid var(--border);border-radius:8px;padding:7px 10px;font-family:inherit">${leagueOpts}</select>
        <button class="btn ghost" id="sleeper-disconnect">Disconnect</button>
      </div>
    </div>
    <div class="section-title" style="margin-top:12px">My roster
      <span class="sub">— usage trend (season → 4wk → last) and trade flags for YOUR players</span></div>
    <div style="margin:0 -18px">${myRows.map(rowHTML).join("") ||
      `<p class="loading" style="padding:12px 16px">Couldn't match a roster you own in this league.</p>`}</div>
    <div class="section-title" style="margin-top:14px">Waiver watch
      <span class="sub">— usage RISERS nobody in this league rosters</span></div>
    <div style="margin:0 -18px">${waivers.map((u) => rowHTML({
        name: u.player, pos: u.position, team: u.team, u, flag: flagByName[ffNorm(u.player)] })).join("") ||
      `<p class="loading" style="padding:12px 16px">Every notable riser is already rostered here.</p>`}</div>
    <p style="color:var(--text-mute);font-size:12px;margin:10px 2px 8px">Boards use PPR scoring;
      custom-scoring recompute lands with the in-season update.</p>
  </div>`;

  const sel = document.getElementById("sleeper-league");
  if (sel) sel.addEventListener("change", () => {
    localStorage.setItem("ff_league", sel.value);
    renderSleeperZone(d);
  });
  const dis = document.getElementById("sleeper-disconnect");
  if (dis) dis.addEventListener("click", () => {
    localStorage.removeItem("ff_user");
    localStorage.removeItem("ff_league");
    renderSleeperZone(d);
  });
}

/* ============================================================
   NBA — Scalpy probability engine
   ============================================================ */
async function renderNBA() {
  const host = document.getElementById("nba-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/nba.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🏀</div>
      <div class="es-title">No NBA data yet</div>
      <div class="es-sub">The launcher builds the NBA slate each refresh once you pull
      and relaunch.</div></div>`;
    return;
  }
  setStandaloneSource("NBA CDN schedule + ingested boxscores + The Odds API",
                      `NBA · ${escapeHtml(d.date || "")}`);
  if (d.status !== "slate") {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🏀</div>
      <div class="es-title">${d.status === "offseason" ? "NBA offseason" : "NBA data unreachable"}</div>
      <div class="es-sub">${escapeHtml(d.note || "")}</div></div>
      <div class="ls-note" style="margin-top:14px">The Scalpy doctrine, ready and waiting:
        minutes are modeled first (~70% of prop variance is minutes) · every stat gets a real
        distribution (negative binomial for rebounds/assists — Poisson understates the tails)
        · the humility clamp shrinks every model number toward the de-vigged market and kills
        any 12-point disagreement · the approval gate demands edge ≥3 points over break-even,
        EV ≥3.5%, hold ≤10%, price ≥ −250 · max 4 picks a slate · CLV is the scoreboard.</div>`;
    return;
  }
  const c = d.counts || {};
  const pctv = (x) => x == null ? "—" : `${(x * 100).toFixed(1)}%`;
  const meta = d.meta || {};
  const gradeColorNBA = { A: "var(--good)", B: "var(--cyan)", C: "var(--warn)", D: "var(--bad)" };

  const pickCard = (p) => `
    <article class="card" style="--grade-color:${gradeColorNBA[p.minutes_grade] || "var(--brand)"}">
      <div class="card-head">
        <div><div class="player">${escapeHtml(p.player)} ${escapeHtml(p.side)} ${p.line} ${escapeHtml(p.market_label)}</div>
          <div class="subtitle">${escapeHtml(p.team)} vs ${escapeHtml(p.opponent)} ·
            ${escapeHtml(p.book)} ${american(p.odds)}</div></div>
        <span class="pm-status" style="color:${gradeColorNBA[p.minutes_grade]}"
          title="Minutes confidence grade — gates the stake">MIN ${escapeHtml(p.minutes_grade)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(p.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(p.p_market)}</div></div>
        <div class="metric"><div class="k">p_final (w=${p.w})</div><div class="v" style="color:var(--brand)">${pctv(p.p_final)}</div></div>
      </div>
      <div class="metrics" style="margin-top:6px">
        <div class="metric"><div class="k">Break-even</div><div class="v">${pctv(p.break_even)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v pos">+${(p.edge * 100).toFixed(1)}pts</div></div>
        <div class="metric"><div class="k">EV</div><div class="v pos">+${(p.ev * 100).toFixed(1)}%</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:12.5px">
        Projection <b>${p.projection}</b> ± ${p.sd} · minutes ${p.base_minutes} → <b>${p.proj_minutes}</b>
        projected · blowout risk ${(p.blowout_prob * 100).toFixed(0)}% · hold ${(p.hold * 100).toFixed(1)}%
        · stake ${p.stake_units}u</div>
      <div class="warning" style="margin-top:8px">KILL IF: ${escapeHtml(p.kill_if)}</div>
    </article>`;

  const missRow = (m) => `
    <div style="display:flex;gap:12px;padding:9px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:1;min-width:0"><strong>${escapeHtml(m.player)} ${escapeHtml(m.side)} ${m.line}
        ${escapeHtml(m.market_label)}</strong>
        <span style="display:block;color:var(--text-mute);font-size:.85em">needs: ${escapeHtml(m.what_would_change)}</span></span>
      <span style="min-width:90px;text-align:right;opacity:.8">${pctv(m.p_final)} final</span>
      <span style="min-width:70px;text-align:right;color:${m.ev >= 0 ? "var(--good)" : "var(--text-mute)"}">${(m.ev * 100).toFixed(1)}% EV</span>
    </div>`;

  host.innerHTML = `
    <div class="stats">
      <div class="tile"><div class="k">Games</div><div class="v">${meta.games || 0}</div></div>
      <div class="tile"><div class="k">Props analyzed</div><div class="v">${c.props_analyzed || 0}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">${escapeHtml(meta.odds || "")}</div></div>
      <div class="tile"><div class="k">Qualifying picks</div><div class="v">${c.picks || 0}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">max 4 per slate by design</div></div>
      <div class="tile"><div class="k">Near misses</div><div class="v">${c.near_misses || 0}</div></div>
    </div>
    ${(meta.teams_on_b2b || []).length ? `<div class="ls-note">Back-to-backs tonight:
      ${meta.teams_on_b2b.map(escapeHtml).join(", ")} — minutes multipliers applied.</div>` : ""}
    ${d.no_qualifying ? `<div class="card" style="margin-top:14px"><div class="player">No qualifying plays at current lines.</div>
        <div style="color:var(--text-body);font-size:13px;margin-top:6px">A no-bet night is a
        correct output, not a failure — forcing a play on a dead slate costs more than a week's
        edge. The near-miss report below shows what came closest and what would need to change.</div></div>`
      : `<div class="section-title" style="margin-top:14px">Qualifying picks
          <span class="sub">— cleared the humility clamp AND the approval gate</span></div>
        <div class="cards">${(d.picks || []).map(pickCard).join("")}</div>`}
    <div class="section-title" style="margin-top:22px">Near-miss report
      <span class="sub">— the closest edges and exactly what would need to change</span></div>
    <div class="card" style="padding:0">${(d.near_misses || []).map(missRow).join("") ||
      `<p class="loading" style="padding:12px">Nothing close.</p>`}</div>
    <p style="color:var(--text-mute);font-size:12.5px;margin-top:14px">Every pick journals to
      the Record page at its real price and grades on CLV — win/loss over a week is noise;
      closing line value over 200+ bets is the only honest measure. Updated ${escapeHtml(d.generated_at || "")}.</p>`;
}

/* ============================================================
   UFC — Scalpy MMA engine
   ============================================================ */
async function renderUFC() {
  const host = document.getElementById("ufc-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/ufc.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🥊</div>
      <div class="es-title">No UFC data yet</div>
      <div class="es-sub">The launcher builds the card each refresh once you pull and relaunch.</div></div>`;
    return;
  }
  setStandaloneSource("The Odds API MMA events + our fighter dossiers",
                      `UFC · ${escapeHtml(d.event_date || d.status || "")}`);
  const pctv = (x) => x == null ? "—" : `${(x * 100).toFixed(1)}%`;

  if (d.status !== "card") {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">🥊</div>
      <div class="es-title">No card in the window</div>
      <div class="es-sub">${escapeHtml(d.note || "")}</div></div>
      <div class="ls-note" style="margin-top:14px">The Scalpy MMA doctrine, ready:
        style beats talent (highest-weight input) · win probability hard-capped at 88% —
        four-ounce gloves mean nobody is safer · method of victory is a JOINT distribution
        that must sum to 100% · durability weighs 1.5× finishing ability · the humility
        clamp kills any 15-point market disagreement · never worse than −300 · max 3 bets
        a card, and a 13-fight card with zero bets is a valid output.</div>`;
    return;
  }

  const methodBar = (m) => {
    const segs = [["a_ko", "var(--bad)"], ["a_sub", "var(--violet,#a78bfa)"],
                  ["a_dec", "var(--brand)"], ["b_dec", "var(--cyan)"],
                  ["b_sub", "var(--warn)"], ["b_ko", "var(--good)"]];
    return `<div style="display:flex;height:10px;border-radius:6px;overflow:hidden;margin-top:8px"
        title="method distribution — left: pick's KO/SUB/DEC, right: opponent's DEC/SUB/KO">
      ${segs.map(([k, c]) => `<span style="width:${(m[k] || 0) * 100}%;background:${c}"></span>`).join("")}
    </div>
    <div style="display:flex;justify-content:space-between;color:var(--text-mute);font-size:11px;margin-top:3px">
      <span>KO ${pctv(m.a_ko)} · SUB ${pctv(m.a_sub)} · DEC ${pctv(m.a_dec)}</span>
      <span>distance ${pctv(m.distance)}</span></div>`;
  };

  const pickCard = (p) => `
    <article class="card" style="--grade-color:var(--good)">
      <div class="card-head">
        <div><div class="player">${escapeHtml(p.pick)} ML</div>
          <div class="subtitle">${escapeHtml(p.fight)}${p.division ? ` · ${escapeHtml(p.division)}` : ""} ·
            ${escapeHtml(p.book)} ${american(p.odds)}</div></div>
        <span class="pm-status" style="color:var(--good)">TIER ${p.edge >= 0.08 ? "A" : p.edge >= 0.05 ? "B" : "C"}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(p.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(p.p_market)}</div></div>
        <div class="metric"><div class="k">p_final (w=${p.w})</div><div class="v" style="color:var(--brand)">${pctv(p.p_final)}</div></div>
      </div>
      <div class="metrics" style="margin-top:6px">
        <div class="metric"><div class="k">Break-even</div><div class="v">${pctv(p.break_even)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v pos">+${(p.edge * 100).toFixed(1)}pts</div></div>
        <div class="metric"><div class="k">EV</div><div class="v pos">+${(p.ev * 100).toFixed(1)}%</div></div>
      </div>
      ${methodBar(p.method || {})}
      <div style="margin-top:8px;color:var(--text-body);font-size:12.5px">
        ${(p.style_notes || []).map(escapeHtml).join(" · ")} · hold ${(p.hold * 100).toFixed(1)}%
        · stake ${p.stake_units}u (one-fifth Kelly)</div>
      <div class="warning" style="margin-top:8px">KILL IF: ${escapeHtml(p.kill_if)}</div>
    </article>`;

  const passRow = (m) => `
    <div style="display:flex;gap:12px;padding:8px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:1;min-width:0"><strong>${escapeHtml(m.fight)}</strong>
        <span style="display:block;color:var(--text-mute);font-size:.85em">${escapeHtml(m.why || "")}</span></span>
      ${m.p_final != null ? `<span style="min-width:80px;text-align:right;opacity:.75">${pctv(m.p_final)} final</span>` : ""}
      ${m.near_miss ? `<span class="chip" style="align-self:center">near miss</span>` : ""}
    </div>`;

  const c = d.counts || {};
  host.innerHTML = `
    <div class="stats">
      <div class="tile"><div class="k">Card</div><div class="v">${escapeHtml(d.event_date || "")}</div></div>
      <div class="tile"><div class="k">Bouts</div><div class="v">${c.fights || 0}</div></div>
      <div class="tile"><div class="k">Dossiers loaded</div><div class="v">${d.dossiers_loaded || 0}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">no dossier, no bet</div></div>
      <div class="tile"><div class="k">Picks</div><div class="v">${c.picks || 0}</div>
        <div style="color:var(--text-mute);font-size:12px;margin-top:2px">max 3 per card by design</div></div>
    </div>
    ${d.no_qualifying ? `<div class="card"><div class="player">No qualifying plays on this card.</div>
        <div style="color:var(--text-body);font-size:13px;margin-top:6px">Most fights on any card
        have no exploitable edge — the pass list below says why, fight by fight. Re-check after
        Friday weigh-ins: missed weight and visible cut damage aren't fully priced for hours.</div></div>`
      : `<div class="section-title">Picks
          <span class="sub">— cleared the clamp AND the gate · one-fifth Kelly stakes</span></div>
        <div class="cards">${(d.picks || []).map(pickCard).join("")}</div>`}
    <div class="section-title" style="margin-top:22px">Pass list
      <span class="sub">— every unbet fight and why. The record that proves the model is
      selective, not lazy.</span></div>
    <div class="card" style="padding:0">${(d.pass_list || []).map(passRow).join("") ||
      `<p class="loading" style="padding:12px">Nothing to pass on.</p>`}</div>
    <p style="color:var(--text-mute);font-size:12.5px;margin-top:14px">Dossiers live in
      data/ufc_dossiers.json (copy the sample file) — the model refuses any fight missing one.
      Updated ${escapeHtml(d.generated_at || "")}.</p>`;
}

/* ============================================================
   Why Us — positioning with receipts, plus the open math layer.
   Every formula here is the same math the engines run; showing it
   is the point. Nothing on this page needs a data feed.
   ============================================================ */
const amToDec = (o) => (o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o));
const amToProb = (o) => (o > 0 ? 100 / (o + 100) : Math.abs(o) / (Math.abs(o) + 100));
const probToAm = (p) => (p >= 0.5 ? -Math.round((p / (1 - p)) * 100) : Math.round(((1 - p) / p) * 100));

function devigMult(ps) {
  const s = ps.reduce((a, b) => a + b, 0);
  return ps.map((p) => p / s);
}

/* Power de-vig: raise each implied prob to the k that makes them sum to 1.
   Shades more of the vig onto favorites than plain division does. */
function devigPower(ps) {
  let lo = 0.5, hi = 8;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (ps.reduce((a, p) => a + Math.pow(p, mid), 0) > 1) lo = mid; else hi = mid;
  }
  const k = (lo + hi) / 2;
  const raw = ps.map((p) => Math.pow(p, k));
  const s = raw.reduce((a, b) => a + b, 0);
  return raw.map((p) => p / s);
}

/* Shin de-vig: models the overround as the book defending against a share z
   of insider money, which loads vig onto longshots (the favorite–longshot
   bias). Solve z by bisection so the fair probs sum to 1. */
function devigShin(ps) {
  const S = ps.reduce((a, b) => a + b, 0);
  if (S <= 1) return devigMult(ps);
  const at = (z) => ps.map((p) =>
    (Math.sqrt(z * z + 4 * (1 - z) * (p * p) / S) - z) / (2 * (1 - z)));
  let lo = 0, hi = 0.5;
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2;
    if (at(mid).reduce((a, b) => a + b, 0) > 1) lo = mid; else hi = mid;
  }
  return at((lo + hi) / 2);
}

/* Kelly criterion: f* = (b·p − q)/b at decimal payout b = dec − 1. */
const kellyFraction = (p, odds) => {
  const b = amToDec(odds) - 1;
  return (b * p - (1 - p)) / b;
};

function whyCalcDevig() {
  const a = parseFloat(document.getElementById("dv-a")?.value);
  const b = parseFloat(document.getElementById("dv-b")?.value);
  const out = document.getElementById("dv-out");
  if (!out) return;
  if (!isFinite(a) || !isFinite(b) || Math.abs(a) < 100 || Math.abs(b) < 100) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter both sides as American odds (±100 or longer).</p>`;
    return;
  }
  const ps = [amToProb(a), amToProb(b)];
  const hold = ps[0] + ps[1] - 1;
  const methods = [
    ["Multiplicative", devigMult(ps), "divide out the vig equally — quick, slightly kind to longshots"],
    ["Power", devigPower(ps), "loads more vig onto the favorite — closer to how props are priced"],
    ["Shin", devigShin(ps), "models insider risk — best for lopsided favorite/longshot prices"],
  ];
  const row = (name, f, note) => `<tr>
    <td style="padding:6px 10px"><strong>${name}</strong>
      <span style="display:block;font-size:.78em;color:var(--text-mute)">${note}</span></td>
    <td style="padding:6px 10px;text-align:right">${(f[0] * 100).toFixed(1)}% <span style="opacity:.6">(${american(probToAm(f[0]))})</span></td>
    <td style="padding:6px 10px;text-align:right">${(f[1] * 100).toFixed(1)}% <span style="opacity:.6">(${american(probToAm(f[1]))})</span></td>
  </tr>`;
  const bench = hold <= 0 ? "an ARBITRAGE — the books disagree enough to lock a margin"
    : hold <= 0.02 ? "a low-hold market — cheap to bet, hard to find"
    : hold <= 0.05 ? "typical main-line juice"
    : "prop-level juice — you need a real edge just to break even";
  out.innerHTML = `
    <p style="margin:8px 0 4px">Book implied: <strong>${(ps[0] * 100).toFixed(1)}%</strong> + <strong>${(ps[1] * 100).toFixed(1)}%</strong>
      = ${( (hold + 1) * 100).toFixed(1)}% → hold <strong style="color:${hold > 0.05 ? "var(--bad)" : hold > 0.02 ? "var(--warn)" : "var(--good)"}">${(hold * 100).toFixed(2)}%</strong>
      <span style="color:var(--text-mute)">— ${bench}.</span></p>
    <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:.92em">
      <tr style="color:var(--text-mute);text-align:right">
        <td style="padding:4px 10px;text-align:left">Fair (vig removed)</td><td>Side A</td><td>Side B</td></tr>
      ${methods.map((m) => row(...m)).join("")}
    </table></div>
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">Where the three agree, trust the number.
      Where they split, the truth is in the range — that honesty is the feature.
      Every board on this site prices edges against de-vigged probabilities, never raw juice.</p>`;
}

function whyCalcKelly() {
  const p = parseFloat(document.getElementById("ky-p")?.value) / 100;
  const odds = parseFloat(document.getElementById("ky-odds")?.value);
  const roll = parseFloat(document.getElementById("ky-roll")?.value);
  const frac = parseFloat(document.getElementById("ky-frac")?.value || "0.25");
  const out = document.getElementById("ky-out");
  if (!out) return;
  if (!isFinite(p) || p <= 0 || p >= 1 || !isFinite(odds) || Math.abs(odds) < 100) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter a win probability (1–99%) and American odds.</p>`;
    return;
  }
  const full = kellyFraction(p, odds);
  const edge = p * amToDec(odds) - 1;
  if (full <= 0) {
    out.innerHTML = `<p style="margin-top:8px"><strong style="color:var(--bad)">No bet.</strong>
      At ${american(odds)} you need ${(amToProb(odds) * 100).toFixed(1)}% to break even and you estimate ${(p * 100).toFixed(1)}% —
      EV ${signedPct(edge)}. Kelly's answer for a negative edge is a stake of zero, and it's the only honest one.</p>`;
    return;
  }
  const stakePct = full * frac;
  const dollars = isFinite(roll) && roll > 0 ? ` = <strong>$${(roll * stakePct).toFixed(2)}</strong> of your $${roll.toFixed(0)}` : "";
  out.innerHTML = `
    <p style="margin-top:8px">EV <strong style="color:var(--good)">${signedPct(edge)}</strong> per unit ·
      full Kelly <strong>${(full * 100).toFixed(1)}%</strong> of bankroll ·
      at your fraction: <strong style="color:var(--brand)">${(stakePct * 100).toFixed(2)}%</strong>${dollars}</p>
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">Full Kelly assumes your probability is exactly right — it never is.
      Betting a quarter to a fifth of Kelly gives up little growth and cuts drawdowns enormously;
      the engines here stake fractional Kelly for exactly that reason. If the number feels big, your probability is too confident.</p>`;
}

function whyCalcParlay() {
  const out = document.getElementById("pl-out");
  if (!out) return;
  const legs = [];
  for (let i = 1; i <= 3; i++) {
    const o = parseFloat(document.getElementById(`pl-o${i}`)?.value);
    if (!isFinite(o) || Math.abs(o) < 100) continue;
    const pv = parseFloat(document.getElementById(`pl-p${i}`)?.value);
    legs.push({ odds: o, p: isFinite(pv) && pv > 0 && pv < 100 ? pv / 100 : amToProb(o) });
  }
  if (legs.length < 2) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter odds for at least two legs (win % optional — blank assumes the book's implied).</p>`;
    return;
  }
  const dec = legs.reduce((a, l) => a * amToDec(l.odds), 1);
  const prob = legs.reduce((a, l) => a * l.p, 1);
  const evParlay = prob * dec - 1;
  const evSingles = legs.reduce((a, l) => a + (l.p * amToDec(l.odds) - 1), 0) / legs.length;
  const verdict = evParlay > evSingles + 1e-9
    ? "the parlay compounds it — only because every leg you entered is +EV"
    : "the singles are the better bet — the parlay multiplies the book's margin into every leg";
  out.innerHTML = `
    <p style="margin-top:8px">${legs.length}-leg parlay pays <strong>${american(probToAm(1 / dec))}</strong>
      (decimal ${dec.toFixed(2)}) · combined win probability <strong>${(prob * 100).toFixed(1)}%</strong></p>
    <p>EV: parlay <strong style="color:${evParlay >= 0 ? "var(--good)" : "var(--bad)"}">${signedPct(evParlay)}</strong>
      vs the same money on singles <strong style="color:${evSingles >= 0 ? "var(--good)" : "var(--bad)"}">${signedPct(evSingles)}</strong>
      <span style="color:var(--text-mute)">— ${verdict}.</span></p>
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">This is why books push parlays:
      at standard −110 juice each leg keeps ~4.5% hold, and a parlay charges it on every leg at once.
      Correlated same-game legs can flip this — but the books price those separately for exactly that reason.</p>`;
}

async function renderWhy() {
  const host = document.getElementById("why-body");
  if (!host) return;
  const src = document.getElementById("data-source");
  if (src) {
    src.className = "data-source";
    src.textContent = "Reference";
    src.title = "Explainer + calculators — no data feed involved";
  }
  const dt = document.getElementById("slate-date");
  if (dt) dt.textContent = "Why us · the open math";

  // Live receipts — the claims below link to real, current numbers.
  let rec = null;
  try {
    const res = await fetch("data/record.json?t=" + Date.now());
    if (res.ok) rec = await res.json();
  } catch (e) {}
  const o = rec && rec.overall;
  const proc = (o && o.process) || {};
  const procN = (proc.good || 0) + (proc.bad || 0) + (proc.flat || 0);
  const cal = rec && rec.calibration;
  const brierLine = cal && cal.brier_edge != null
    ? (cal.brier_edge > 0
      ? `model out-forecasts the de-vigged market on its own picks (Brier ${cal.brier_model} vs ${cal.brier_market})`
      : `the market still forecasts our picks better (Brier ${cal.brier_model} vs ${cal.brier_market}) — shown anyway, because hiding it would make us a tout`)
    : "accrues as picks settle";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div>
    ${sub ? `<div style="color:var(--text-mute);font-size:12px;margin-top:2px">${sub}</div>` : ""}</div>`;
  const proof = o && (o.settled || o.open)
    ? `<div class="stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
        ${tile("Journaled record", `${o.wins}-${o.losses}-${o.pushes}`, `${o.open} open · every pick, no deletions`)}
        ${tile("Avg CLV", o.avg_clv == null ? "—" : (o.avg_clv >= 0 ? "+" : "") + o.avg_clv.toFixed(2) + " pts",
               "did the market move our way after we bet")}
        ${tile("Process record", procN ? `${proc.good || 0} good · ${proc.bad || 0} bad` : "—",
               procN ? `${proc.lucky_wins || 0} lucky win(s) admitted` : "grades vs the closing line")}
        ${tile("Forecast test", cal && cal.brier_edge != null ? (cal.brier_edge > 0 ? "beating the close" : "not yet") : "—", brierLine)}
      </div>
      <p style="margin-top:8px"><button class="btn ghost" id="why-see-record">See the full record →</button></p>`
    : `<p class="loading">The journal is young — every pick logs automatically and this strip fills with real, ungroomed numbers.</p>`;

  const pillar = (icon, title, body) => `<div class="card" style="padding:16px">
    <div style="font-size:1.6em">${icon}</div>
    <h3 style="margin:6px 0 6px">${title}</h3>
    <p style="color:var(--text-body);font-size:.92em;margin:0">${body}</p></div>`;

  const vsRow = (them, us) => `<tr>
    <td style="padding:8px 12px;color:var(--text-mute);border-bottom:1px solid rgba(255,255,255,.05)">${them}</td>
    <td style="padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.05)">${us}</td></tr>`;

  host.innerHTML = `
    <p style="font-size:1.05em;max-width:70ch"><strong>See the math. Know if it's working. Stay in the game.</strong>
      Most betting sites sell certainty. This one sells measurement — every probability is computed
      from data you can name, every pick is graded in public, and the math is on this page for you to check by hand.</p>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:14px">
      ${pillar("🔍", "Transparent math", `Park factors, umpire tendencies, lineup-slot plate appearances, bullpen fatigue,
        minutes engines — every factor on a card is measured from real data, and negative factors get a red ✗, not a hidden footnote.
        The de-vig, Kelly and EV formulas the engines run are open below.`)}
      ${pillar("📒", "Graded in public", `Every recommended pick journals at its real book price the moment it appears and grades
        itself against the final result — wins, losses, closing-line value, and a calibration curve that says whether "60%" meant 60%.
        Long shots are tracked in a separate bucket, never blended into the headline record.`)}
      ${pillar("🚫", "Built to pass", `Approval gates, humility clamps toward the market, hard pick caps, and pass lists that
        say why each game was skipped. "No qualifying plays tonight" is a correct output here — a service that must sell picks
        every night can never say it.`)}
    </div>

    <div class="section-title" style="margin-top:24px">The receipts, live
      <span class="sub">— these numbers come from the actual journal, right now, losses included.</span></div>
    ${proof}

    <div class="section-title" style="margin-top:24px">What picks services sell vs what this is</div>
    <div class="card" style="padding:0;overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:.92em">
        <tr style="color:var(--text-mute)"><td style="padding:8px 12px">The usual pitch</td><td style="padding:8px 12px">Here</td></tr>
        ${vsRow("\"Locks\" and \"guaranteed winners\"", "Probabilities with uncertainty attached. A 60% play loses 4 times in 10 — we say so on the card.")}
        ${vsRow("A record you have to take on faith", "A journal that logs every pick automatically at its real price — it cannot be groomed after the fact.")}
        ${vsRow("Graded on wins and losses only", "Graded on process too: a win that closed worse than we bet is flagged as lucky; a loss that beat the close was a good bet.")}
        ${vsRow("A black-box \"algorithm\"", "Named factors on every card, red marks on the negatives, and the pricing math open on this page.")}
        ${vsRow("More picks when business is slow", "Hard caps and pass lists. The NBA engine maxes at 4 picks a slate; UFC passes on most of every card, with reasons.")}
      </table>
    </div>

    <div class="section-title" style="margin-top:24px">What we deliberately don't do</div>
    <div class="card" style="padding:14px 18px">
      <ul style="margin:0;padding-left:18px;line-height:1.9;color:var(--text-body)">
        <li>No guarantees, locks, or "can't-miss" anything — that language is how touts talk, and it's always false.</li>
        <li>No parlay pushing — the calculator below shows exactly what parlays cost, which is why books advertise them.</li>
        <li>No hiding losses — the Record page keeps every settled pick, and the lucky wins are labeled as lucky.</li>
        <li>No placing bets and no handling money — this recommends, journals, and grades. The decisions stay yours.</li>
        <li>No "premium tier" where the real picks supposedly live — everything the models produce is on these pages.</li>
      </ul>
    </div>

    <div class="section-title" style="margin-top:24px">The open math layer
      <span class="sub">— the same formulas the engines run, interactive. Punch in any real price and check our work.</span></div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Remove the vig — three ways</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">A −110/−110 line isn't 50/50 — it's 52.4% + 52.4% = 104.8%.
        The extra 4.8% is the book's hold. Enter both sides of any market:</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <label>Side A <input id="dv-a" type="number" value="-115" step="5" class="calc-in"></label>
        <label>Side B <input id="dv-b" type="number" value="-105" step="5" class="calc-in"></label>
      </div>
      <div id="dv-out"></div>
    </div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Kelly stake sizer</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">Given your edge, how much should the bet be?
        The answer is usually "less than you think" and sometimes "zero".</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <label>Win prob % <input id="ky-p" type="number" value="55" min="1" max="99" step="0.5" class="calc-in"></label>
        <label>Odds <input id="ky-odds" type="number" value="-110" step="5" class="calc-in"></label>
        <label>Bankroll $ <input id="ky-roll" type="number" value="${state.bankroll || 1000}" min="0" step="50" class="calc-in"></label>
        <label>Fraction <select id="ky-frac" class="calc-in">
          <option value="1">Full Kelly</option><option value="0.5">Half</option>
          <option value="0.25" selected>Quarter</option><option value="0.2">Fifth</option>
        </select></label>
      </div>
      <div id="ky-out"></div>
    </div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Parlay vs singles</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">Enter 2–3 legs. Win % is optional —
        left blank, each leg is assumed to hit exactly as often as the book's price implies.</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        ${[1, 2, 3].map((i) => `<span style="display:inline-flex;gap:6px;align-items:center">
          <label>Leg ${i} <input id="pl-o${i}" type="number" ${i < 3 ? `value="-110"` : ""} step="5" class="calc-in"></label>
          <label>win % <input id="pl-p${i}" type="number" min="1" max="99" step="0.5" class="calc-in" style="width:70px"></label>
        </span>`).join("")}
      </div>
      <div id="pl-out"></div>
    </div>

    <div class="card" style="padding:14px 18px;margin-top:20px;border-left:3px solid var(--warn)">
      <h3 style="margin:0 0 6px">Play the long game</h3>
      <p style="color:var(--text-body);font-size:.92em;margin:0">Even a real edge loses often — that's variance, not failure,
        and it's why stakes here are fractions of bankroll, never "bet big to catch up." 21+ only. Never bet money you
        can't afford to lose. If it stops feeling like a decision, call or text <strong>1-800-GAMBLER</strong> or the National
        Problem Gambling Helpline at <strong>1-800-522-4700</strong> — free, confidential, 24/7.</p>
    </div>`;

  const seeRec = document.getElementById("why-see-record");
  if (seeRec) seeRec.addEventListener("click", () => { exitStandaloneMode(); switchView("record"); });
  [["dv-a", whyCalcDevig], ["dv-b", whyCalcDevig],
   ["ky-p", whyCalcKelly], ["ky-odds", whyCalcKelly], ["ky-roll", whyCalcKelly], ["ky-frac", whyCalcKelly],
   ["pl-o1", whyCalcParlay], ["pl-p1", whyCalcParlay], ["pl-o2", whyCalcParlay],
   ["pl-p2", whyCalcParlay], ["pl-o3", whyCalcParlay], ["pl-p3", whyCalcParlay],
  ].forEach(([id, fn]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", fn);
  });
  whyCalcDevig(); whyCalcKelly(); whyCalcParlay();
}

const VIEW_ORDER = ["recommended", "edge", "scanner", "longshots", "trending", "players", "record", "intel", "fantasy", "nba", "ufc", "why"];

function switchView(name) {
  const dir = VIEW_ORDER.indexOf(name) - VIEW_ORDER.indexOf(state.view);
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active", "from-left", "from-right"));
  const target = document.getElementById(`view-${name}`);
  // Entering view slides in from the direction of travel between tabs.
  if (dir > 0) target.classList.add("from-right");
  else if (dir < 0) target.classList.add("from-left");
  target.classList.add("active");
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "record") renderRecord();
  if (name === "intel") renderIntel();
  if (name === "fantasy") renderFantasy();
  if (name === "nba") renderNBA();
  if (name === "ufc") renderUFC();
  if (name === "why") renderWhy();
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  moveIndicator();
}

function initialView() {
  const h = (location.hash || "").replace("#", "");
  if (STANDALONE_MODES.includes(h)) { enterStandaloneMode(h); return; }
  if (VIEW_ORDER.includes(h)) switchView(h);
}

function moveIndicator() {
  const active = document.querySelector(".nav-btn.active");
  const ind = document.getElementById("nav-indicator");
  if (!active || !ind) return;
  ind.style.left = active.offsetLeft + "px";
  ind.style.width = active.offsetWidth + "px";
}

/* ---------------- wiring ---------------- */
function bind() {
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => switchView(b.dataset.view)));

  document.querySelectorAll(".sport-btn").forEach((b) =>
    b.addEventListener("click", () => {
      if (STANDALONE_MODES.includes(b.dataset.sport)) { enterStandaloneMode(b.dataset.sport); return; }
      exitStandaloneMode();
      if (state.sport === b.dataset.sport) return;
      state.sport = b.dataset.sport;
      state.search = "";
      const search = document.getElementById("player-search");
      if (search) search.value = "";
      const url = new URL(location.href);
      url.searchParams.set("sport", state.sport);
      history.replaceState(null, "", url);
      applySport();
      load();
    }));

  const conf = document.getElementById("min-conf"), edge = document.getElementById("min-edge");
  conf.addEventListener("input", () => {
    state.minConf = parseFloat(conf.value);
    document.getElementById("conf-val").textContent = state.minConf.toFixed(1);
    load();
  });
  edge.addEventListener("input", () => {
    state.minEdge = parseFloat(edge.value);
    document.getElementById("edge-val").textContent = `${state.minEdge}%`;
    load();
  });
  const juice = document.getElementById("max-juice");
  juice.addEventListener("input", () => {
    state.maxJuice = parseInt(juice.value, 10);
    document.getElementById("juice-val").textContent = state.maxJuice;
    load();
  });
  document.getElementById("show-all").addEventListener("change", (e) => {
    state.showAll = e.target.checked; renderTopPlays(); renderGameBets(); renderRecommended();
  });
  document.getElementById("player-search").addEventListener("input", (e) => {
    state.search = e.target.value; renderPlayers();
  });

  const bankrollEl = document.getElementById("bankroll");
  const unitEl = document.getElementById("unit-pct");
  if (state.bankroll) bankrollEl.value = state.bankroll;
  unitEl.value = state.unitPct;
  const onBankrollChange = () => {
    const b = parseFloat(bankrollEl.value);
    state.bankroll = isFinite(b) && b > 0 ? b : null;
    const u = parseFloat(unitEl.value);
    state.unitPct = isFinite(u) && u > 0 ? u : 1.0;
    try {
      localStorage.setItem("ge-bankroll", state.bankroll == null ? "" : String(state.bankroll));
      localStorage.setItem("ge-unit-pct", String(state.unitPct));
    } catch (e) {}
    updateUnitNote();
    renderStats();
    renderTopPlays();
    renderGameBets();
    renderRecommended();
    renderPlayers();
  };
  bankrollEl.addEventListener("input", onBankrollChange);
  unitEl.addEventListener("input", onBankrollChange);
  document.getElementById("refresh").addEventListener("click", load);
  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  window.addEventListener("resize", moveIndicator);
}

initTheme();
loadBankroll();
bind();
applySport();
updateUnitNote();
initialView();
requestAnimationFrame(moveIndicator);
load();
