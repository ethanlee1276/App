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
  const reasons = (r.reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");

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
  const visible = recs.filter((r) => (state.showAll ? true : r._ok));
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
    return `<div class="section-title" style="grid-column:1/-1;margin:14px 0 0">
        ${escapeHtml(k)} <span class="sub">— ${rows.length} prop(s)${nRec ? `, ${nRec} recommended` : ""}</span>
      </div>` + rows.map(cardHTML).join("");
  }).join("");
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
  const reasons = (r.reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
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
      <div class="es-title">No long shots clear the bar right now</div>
      <div class="es-sub">The model only surfaces ${mlb ? "home-run" : "touchdown"} picks that beat
      the book's price inside a sane odds range${mlb ? " (+250 to +650)" : " (-150 to +200)"}.
      ${mlb ? "The most-likely-tonight list appears here once real home-run prices are attached." : ""}</div></div>`;
    return;
  }
  note.innerHTML = `<div class="ls-note">Ranked by <b>edge</b>, never by payout.
    ${mlb ? "At most one per team" : "At most two per game"}, top ${picks.length} shown.</div>`;
  host.innerHTML = picks.map(longShotCard).join("") + watchlistHTML(watch, mlb);
  fillMeters(host);
  revealChildren(host);
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
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
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
      return `<div style="display:flex;gap:12px;padding:6px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
        <span style="flex:1">${escapeHtml(k)}</span>
        <span style="min-width:70px;text-align:right">${d.w}-${d.l}</span>
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
    </div>
    <p style="opacity:.6;font-size:.85em;margin-top:10px">Journals every
      <strong>Recommended</strong> pick — player props and sharp-anchor game bets
      (moneylines &amp; totals) — at the real book price shown when it was
      recommended. Long Shots and Edge Board entries are watchlists, not tracked
      bets. One entry per player &amp; market per day.</p>
    ${small}
    ${recCurveChart(d.curve)}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">
      ${recBucketTable("By market", o.by_market)}
      ${recBucketTable("By side", o.by_side)}
      ${recBucketTable("By grade", o.by_grade)}
    </div>
    <div class="section-title" style="margin-top:18px">Recent settled picks</div>
    <div class="card" style="padding:0">
      ${(d.recent || []).map((b) => {
        const won = b.status === "won";
        const push = b.status === "push";
        const icon = push ? "➖" : (won ? "✅" : "❌");
        const pnl = b.pnl_units || 0;
        return `<div style="display:flex;gap:12px;padding:8px 14px;align-items:center;
            border-bottom:1px solid rgba(255,255,255,.05);white-space:nowrap;overflow:hidden">
          <span>${icon}</span>
          <span style="opacity:.55;min-width:82px;font-size:.85em">${escapeHtml(b.date || "")}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">
            <strong>${escapeHtml(b.player)}</strong>
            <span style="opacity:.6"> ${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
          <span style="min-width:56px;text-align:right">${american(b.odds)}</span>
          <span style="min-width:70px;text-align:right;color:${pnl >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)"}">
            ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
        </div>`;
      }).join("") || `<p class="loading" style="padding:12px">Nothing settled yet.</p>`}
    </div>
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

const VIEW_ORDER = ["recommended", "edge", "longshots", "trending", "players", "record"];

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
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  moveIndicator();
}

function initialView() {
  const h = (location.hash || "").replace("#", "");
  if (["recommended", "edge", "longshots", "trending", "players", "record"].includes(h)) switchView(h);
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
