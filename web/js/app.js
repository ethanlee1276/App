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
};

/* ---------------- formatting helpers ---------------- */
const gradeClass = (g) => ({ "Strong Play": "strong", "Play": "play", "Lean": "lean", "Pass": "pass" }[g] || "pass");
const gradeColor = (g) => ({ "Strong Play": "var(--good)", "Play": "var(--cyan)", "Lean": "var(--warn)", "Pass": "var(--text-mute)" }[g] || "var(--text-mute)");
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const signedPct = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
const american = (o) => (o > 0 ? `+${o}` : `${o}`);
const teamName = (a) => (typeof TEAMS !== "undefined" && TEAMS[a] && TEAMS[a].nick) || a;
const teamPrimary = (a) => (typeof TEAMS !== "undefined" && TEAMS[a] && TEAMS[a].primary) || "var(--brand)";
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------- data ---------------- */
async function load() {
  const params = new URLSearchParams({ min_confidence: state.minConf, min_edge: state.minEdge });
  try {
    const res = await fetch(`/api/recommendations?${params}`);
    if (!res.ok) throw new Error("api");
    state.data = await res.json();
  } catch (e) {
    const res = await fetch("data/recommendations.json");
    state.data = await res.json();
  }
  renderAll();
}

function passesFilters(r) {
  return r.recommended && r.confidence >= state.minConf && r.edge * 100 >= state.minEdge && r.grade !== "Pass";
}

function renderAll() {
  const d = state.data;
  if (!d) return;
  document.getElementById("slate-date").textContent = `Slate: ${d.date}`;
  renderStats();
  renderGames();
  renderRecommended();
  renderTrending();
  renderPlayers();
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
  const tiles = [
    { k: "Props analyzed", to: d.counts.props_analyzed, dec: 0 },
    { k: "Recommended", to: rec.length, dec: 0 },
    { k: "Avg edge", to: rec.length ? avgEdge * 100 : 0, dec: 1, suf: "%", pre: avgEdge >= 0 ? "+" : "", cls: "pos" },
    { k: "Suggested exposure", to: exposure, dec: 2, suf: "u" },
  ];
  document.getElementById("stats").innerHTML = tiles.map((t) =>
    `<div class="tile"><div class="k">${t.k}</div>
       <div class="v ${t.cls || ""}" data-to="${t.to}" data-dec="${t.dec}" data-pre="${t.pre || ""}" data-suf="${t.suf || ""}">0</div></div>`
  ).join("");
  document.querySelectorAll("#stats .v[data-to]").forEach(countUp);
}

function renderGames() {
  const games = state.data.games || [];
  const host = document.getElementById("games");
  if (!games.length) { host.innerHTML = ""; return; }
  host.innerHTML = games.map(gameCard).join("");
}

function gameCard(g) {
  const w = g.weather || {};
  const cond = w.dome ? "Indoor" : `${Math.round(w.temp_f)}°F · ${Math.round(w.wind_mph)}mph${w.wind_dir ? " " + w.wind_dir : ""}`;
  const favTxt = g.favorite ? `${teamName(g.favorite)} −${Math.abs(g.spread).toFixed(1)}` : "";
  return `
    <article class="game-card">
      <div class="stadium-wrap">${stadium(g)}</div>
      <div class="game-info">
        <div class="matchup"><span class="away">${escapeHtml(teamName(g.away))}</span>
          <span class="at">@</span><span class="home">${escapeHtml(teamName(g.home))}</span></div>
        <div class="game-sub">${escapeHtml(favTxt)} · O/U ${g.total.toFixed(1)}</div>
      </div>
      <div class="wind-wrap">${windGauge(w)}<span class="cond">${escapeHtml(cond)}</span></div>
    </article>`;
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
  host.querySelectorAll(".conf-fill[data-w]").forEach((el) => requestAnimationFrame(() => (el.style.width = el.dataset.w)));
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
  const stakeChip = r._ok ? `<span class="chip stake">Stake ${r.stake_units.toFixed(2)}u</span>` : "";
  return `
    <article class="card ${r._ok ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team)}
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
      <div class="chips">${trendChip(r)}${booksChip(r)}${stakeChip}</div>
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
  document.getElementById("trending").innerHTML = cols.map((c) => `
    <div class="trend-col">
      <h3>${c.title}</h3><div class="colsub">${c.sub}</div>
      ${c.rows.length ? c.rows.map((r, i) => trendRow(r, i, c)).join("") : `<div class="empty" style="padding:24px">No movers.</div>`}
    </div>`).join("");
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
  host.querySelectorAll(".conf-fill[data-w]").forEach((el) => requestAnimationFrame(() => (el.style.width = el.dataset.w)));
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
        ${playerAvatar(r.player, r.team, { size: 60 })}
        <div class="meta"><div class="nm">${escapeHtml(r.player)}</div>
          <div class="sub">${escapeHtml(teamName(r.team))} · ${escapeHtml(r.position)} · vs ${escapeHtml(r.opponent)}</div></div>
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
  const dur = 700, t0 = performance.now();
  (function tick(t) {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = pre + (to * e).toFixed(dec) + suf;
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
}

/* ---------------- routing ---------------- */
function switchView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
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
    state.showAll = e.target.checked; renderRecommended();
  });
  document.getElementById("player-search").addEventListener("input", (e) => {
    state.search = e.target.value; renderPlayers();
  });
  document.getElementById("refresh").addEventListener("click", load);
  window.addEventListener("resize", moveIndicator);
}

bind();
initialView();
requestAnimationFrame(moveIndicator);
load();
