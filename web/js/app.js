/* Gridiron Edge — app shell.
 *
 * A small client-side router over three views (Recommended / Trending /
 * Players) sharing one data fetch. Rendering helpers draw the pick cards,
 * trending leaderboards and player profiles; visuals.js supplies the SVG art
 * (avatars, stadiums, wind, sparklines).
 */

const state = {
  data: null, minConf: 6.0, minEdge: 2.0, showAll: false,
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
         gamesTitle: "🏟️ This week's stadiums & conditions",
         api: "/api/recommendations", fallback: "data/recommendations.json" },
  mlb: { logo: "⚾", tagline: "AI-powered MLB player-prop model",
         gamesTitle: "🏟️ Today's ballparks & conditions",
         api: "/api/mlb/recommendations", fallback: "data/mlb_recommendations.json" },
};

function applySport() {
  const meta = SPORT_META[state.sport];
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
  return w ? `<span class="chip when">🗓️ ${escapeHtml(w)}</span>` : "";
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
  const params = new URLSearchParams({ min_confidence: state.minConf, min_edge: state.minEdge });
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
  return r.recommended && r.confidence >= state.minConf && r.edge * 100 >= state.minEdge && r.grade !== "Pass";
}

function slateDateLabel(d) {
  // Show the span of actual game dates when the slate covers more than one day.
  const dates = [...new Set((d.games || []).map((g) => g.date).filter(Boolean))].sort();
  if (!dates.length) return `Slate: ${d.date}`;
  if (dates.length === 1) return formatGameDate(dates[0]);
  return `${formatGameDate(dates[0])} – ${formatGameDate(dates[dates.length - 1])}`;
}

function renderAll() {
  const d = state.data;
  if (!d) return;
  document.getElementById("slate-date").textContent = slateDateLabel(d);
  renderStats();
  renderGames();
  renderGameBets();
  renderRecommended();
  renderTrending();
  renderPlayers();
}

/* ============================================================
   Game bets — moneyline (win-probability edge on the game)
   ============================================================ */
function passesGameBet(r) {
  return r.confidence >= state.minConf && r.edge * 100 >= state.minEdge && r.grade !== "Pass";
}

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
  host.innerHTML = visible.map(gameBetCard).join("");
  fillMeters(host);
  revealChildren(host);
}

function gameBetCard(r) {
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">💰 ${stakeTxt}</span>` : "";
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
  const recs = state.data.recommendations.map((r) => ({ ...r, _ok: passesFilters(r) }));
  const visible = recs.filter((r) => (state.showAll ? true : r._ok));
  const host = document.getElementById("cards");
  if (!visible.length) {
    host.innerHTML = `<p class="loading">No props clear the current thresholds. Loosen the sliders or enable “show non-recommended”.</p>`;
    return;
  }
  host.innerHTML = visible.map(cardHTML).join("");
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

function cardHTML(r) {
  const reasons = (r.reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const warnings = (r.warnings || []).map((w) => `<div class="warning">⚠️ ${escapeHtml(w)}</div>`).join("");
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">💰 ${stakeTxt}</span>` : "";
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
        <div class="metric"><div class="k">Edge</div><div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">EV / unit</div><div class="v ${r.ev_per_unit >= 0 ? "pos" : "neg"}">${signedPct(r.ev_per_unit)}</div></div>
      </div>
      ${confMeter(r)}
      <div class="chips">${whenChip(r.game_date, r.game_kickoff)}${trendChip(r)}${booksChip(r)}${stakeChip}</div>
      ${warnings}${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
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
        <div class="mk">${escapeHtml(r.team)} · ${escapeHtml(r.market_label)}${formatGameDate(r.game_date) ? ` · 🗓️ ${escapeHtml(formatGameDate(r.game_date))}` : ""}</div></div>
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
  const rows = (r.logs || []).map((l) => {
    const hit = l.value > r.line;
    return `<tr><td>Wk ${l.week}</td><td>${l.home ? "vs" : "@"} ${escapeHtml(l.opponent)}</td>
      <td class="num ${hit ? "hit" : "miss"}">${l.value}</td></tr>`;
  }).join("");
  const grad = `linear-gradient(135deg, ${teamPrimary(r.team)}, transparent)`;
  return `
    <article class="profile" style="--profile-grad:${grad}">
      <div class="profile-head">
        ${playerAvatar(r.player, r.team, { size: 60, headshot: r.headshot })}
        <div class="meta"><div class="nm">${escapeHtml(r.player)}</div>
          <div class="sub">${teamMark(r.team, 16)} ${escapeHtml(teamName(r.team))} · ${escapeHtml(r.position)} · vs ${escapeHtml(r.opponent)}${whenLabel(r.game_date, r.game_kickoff) ? ` · 🗓️ ${escapeHtml(whenLabel(r.game_date, r.game_kickoff))}` : ""}</div></div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="form-tiles">${tiles}</div>
      <div class="profile-spark">${sparkline(vals, { line: r.line, stroke: teamPrimary(r.team), h: 72 })}</div>
      <table class="log-table">
        <tr><th>Week</th><th>Opponent</th><th style="text-align:right">${escapeHtml(r.market_label)}</th></tr>
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
const VIEW_ORDER = ["recommended", "trending", "players"];

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
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  moveIndicator();
}

function initialView() {
  const h = (location.hash || "").replace("#", "");
  if (["recommended", "trending", "players"].includes(h)) switchView(h);
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
  document.getElementById("show-all").addEventListener("change", (e) => {
    state.showAll = e.target.checked; renderGameBets(); renderRecommended();
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
