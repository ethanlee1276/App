/* Gridiron Edge dashboard.
 *
 * Fetches recommendations from the live API (/api/recommendations) when served
 * by server.py, and falls back to the pre-generated data/recommendations.json
 * when the page is opened directly from disk. Renders each pick as a card with
 * a projection-vs-line bar, confidence meter and the model's reasons.
 */

const state = { data: null, minConf: 6.0, minEdge: 2.0, showAll: false };

const gradeClass = (g) => ({
  "Strong Play": "strong", "Play": "play", "Lean": "lean", "Pass": "pass",
}[g] || "pass");

const gradeColor = (g) => ({
  "Strong Play": "var(--strong)", "Play": "var(--play)",
  "Lean": "var(--lean)", "Pass": "var(--pass)",
}[g] || "var(--pass)");

const pct = (x) => `${(x * 100).toFixed(1)}%`;
const signedPct = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
const american = (o) => (o > 0 ? `+${o}` : `${o}`);

async function load() {
  const params = new URLSearchParams({
    min_confidence: state.minConf,
    min_edge: state.minEdge,
  });
  try {
    const res = await fetch(`/api/recommendations?${params}`);
    if (!res.ok) throw new Error("api");
    state.data = await res.json();
  } catch (e) {
    // Static fallback (page opened via file://). Filtering is done client-side.
    const res = await fetch("data/recommendations.json");
    state.data = await res.json();
  }
  render();
}

function passesFilters(r) {
  // When served statically we must re-apply thresholds on the client.
  return r.confidence >= state.minConf && r.edge * 100 >= state.minEdge && r.grade !== "Pass";
}

function render() {
  const d = state.data;
  if (!d) return;

  document.getElementById("slate-date").textContent = `Slate: ${d.date}`;

  const recs = d.recommendations.map((r) => ({
    ...r,
    _recommended: r.recommended && passesFilters(r),
  }));
  const recommendedCount = recs.filter((r) => r._recommended).length;

  renderStats(d, recs, recommendedCount);

  const visible = recs.filter((r) => (state.showAll ? true : r._recommended));
  const host = document.getElementById("cards");
  if (visible.length === 0) {
    host.innerHTML = `<p class="loading">No props clear the current thresholds. Loosen the sliders or enable “show non-recommended”.</p>`;
    return;
  }
  host.innerHTML = visible.map(cardHTML).join("");
}

function renderStats(d, recs, recommendedCount) {
  const avgEdge = recs.filter((r) => r._recommended)
    .reduce((s, r) => s + r.edge, 0) / (recommendedCount || 1);
  const totalStake = recs.filter((r) => r._recommended)
    .reduce((s, r) => s + r.stake_units, 0);
  const tiles = [
    ["Props analyzed", d.counts.props_analyzed],
    ["Recommended", recommendedCount],
    ["Avg edge", recommendedCount ? signedPct(avgEdge) : "—"],
    ["Suggested exposure", `${totalStake.toFixed(2)}u`],
  ];
  document.getElementById("stats").innerHTML = tiles
    .map(([k, v]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div></div>`)
    .join("");
}

function projBar(r) {
  // Scale the track to a window around the projected range and the line.
  const lo = Math.min(r.proj_low, r.line);
  const hi = Math.max(r.proj_high, r.line);
  const pad = (hi - lo) * 0.15 || 1;
  const min = lo - pad, max = hi + pad;
  const pos = (v) => `${((v - min) / (max - min)) * 100}%`;
  const rangeLeft = pos(r.proj_low);
  const rangeWidth = `${((r.proj_high - r.proj_low) / (max - min)) * 100}%`;
  return `
    <div class="projbar">
      <div class="labels"><span>Projection vs line</span><span>${r.market_label}</span></div>
      <div class="track">
        <div class="range" style="left:${rangeLeft};width:${rangeWidth}"></div>
        <div class="line-dot" style="left:${pos(r.line)}" title="Line ${r.line}"></div>
        <div class="proj-dot" style="left:${pos(r.projection)}" title="Projection ${r.projection}"></div>
      </div>
      <div class="legend">
        <span class="proj">Proj ${r.projection}</span>
        <span class="line">Line ${r.line}</span>
      </div>
    </div>`;
}

function confMeter(r) {
  const w = `${(r.confidence / 10) * 100}%`;
  const color = r.confidence >= 8.5 ? "var(--strong)"
    : r.confidence >= 7 ? "var(--play)"
    : r.confidence >= 5.5 ? "var(--lean)" : "var(--pass)";
  return `
    <div class="conf-wrap">
      <div class="conf-meter"><div class="conf-fill" style="width:${w};background:${color}"></div></div>
      <div class="conf-num">${r.confidence.toFixed(1)}/10</div>
    </div>`;
}

function trendChip(r) {
  if (r.trend === "up") return `<span class="chip up">📈 Trending up</span>`;
  if (r.trend === "down") return `<span class="chip down">📉 Cooling off</span>`;
  return `<span class="chip">Steady form</span>`;
}

function cardHTML(r) {
  const reasons = (r.reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const warnings = (r.warnings || [])
    .map((w) => `<div class="warning">⚠️ ${escapeHtml(w)}</div>`).join("");
  const edgeCls = r.edge >= 0 ? "pos" : "neg";
  const stakeChip = r._recommended
    ? `<span class="chip stake">Stake ${r.stake_units.toFixed(2)}u</span>` : "";

  return `
    <article class="card ${r._recommended ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      <div class="card-head">
        <div>
          <div class="player">${escapeHtml(r.player)}</div>
          <div class="subtitle">${escapeHtml(r.team)} vs ${escapeHtml(r.opponent)} · ${escapeHtml(r.position)}</div>
          <div class="pick">${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}
            <span class="book">· ${escapeHtml(r.book)} ${american(r.odds)}</span></div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>

      ${projBar(r)}

      <div class="metrics">
        <div class="metric"><div class="k">Hit prob</div><div class="v">${pct(r.hit_prob)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v ${edgeCls}">${signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">EV / unit</div><div class="v ${r.ev_per_unit >= 0 ? "pos" : "neg"}">${signedPct(r.ev_per_unit)}</div></div>
      </div>

      ${confMeter(r)}

      <div class="chips">${trendChip(r)}${stakeChip}</div>

      ${warnings}
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// --- wiring -----------------------------------------------------------------
function bind() {
  const conf = document.getElementById("min-conf");
  const edge = document.getElementById("min-edge");
  const showAll = document.getElementById("show-all");

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
  showAll.addEventListener("change", () => {
    state.showAll = showAll.checked;
    render();
  });
  document.getElementById("refresh").addEventListener("click", load);
}

bind();
load();
