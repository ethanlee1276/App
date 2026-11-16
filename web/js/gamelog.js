/* GAME LOGS (js/gamelog.js, loaded the first time one opens).

   Ethan, 2026-11-16, with ESPN's game log for Joe Burrow: "we should have game
   logs for every player too that you can look up and see for each player."
   From any player's page (app.js chartDoor, "Game log"): his season a line a
   game, the newest first: the day (and the week, in football), the opponent and
   where, the result and the score, and the league's own columns grouped the way
   a box score groups them (engine/gamelog, /api/players/gamelog). Then the
   season's totals and per-game averages, and what each column means. A season
   picker where his file holds more than one. In a sheet over the page, as his
   charts are, so the page's own redraw every minute never takes it away. */

const GL_CACHE = new Map();
const GL_SPORT = { nfl: "NFL", cfb: "College Football", nba: "NBA", wnba: "WNBA", cbb: "College Basketball",
  nhl: "NHL", mlb: "MLB" };

async function glFetch(sport, player, season) {
  const key = `${sport}|${player}|${season || ""}`;
  if (GL_CACHE.has(key)) return GL_CACHE.get(key);
  let body = null;
  try {
    const q = new URLSearchParams({ sport, player });
    if (season) q.set("season", String(season));
    const r = await fetch(`/api/players/gamelog?${q}`);
    body = r.ok ? await r.json() : null;
  } catch (e) { body = null; }
  if (body && body.player) GL_CACHE.set(key, body);
  return body;
}

//: A cell as the column says it: counts whole, rates to a tenth, time on ice as m:ss.
function glCell(v, label) {
  if (v == null || v === "") return "—";
  if (typeof v === "string") return v;
  if (label === "TOI") {
    const m = Math.floor(v), s = Math.round((v - m) * 60);
    return `${m}:${String(s === 60 ? 0 : s).padStart(2, "0")}`;
  }
  if (label === "MIN") return String(Math.round(v));
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
//: "Wk 10" (and its day under it) in football; the day elsewhere.
function glDay(g) {
  const d = g.date ? new Date(`${g.date}T12:00:00`) : null;
  const day = d && !isNaN(d) ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
  return g.week ? `<b>Wk ${g.week}</b>${day ? `<span>${escapeHtml(day)}</span>` : ""}` : `<b>${escapeHtml(day || g.date || "")}</b>`;
}

function glTableHTML(d) {
  const groups = d.groups || [];
  const cols = groups.flatMap((g) => g.cols.map((c) => ({ ...c, id: `${g.key}.${c.key}` })));
  const titled = groups.some((g) => g.title);
  const head = `<thead>${titled ? `<tr class="gl-groups"><th class="gl-fix" colspan="3"></th>${groups.map((g) =>
      `<th colspan="${g.cols.length}">${escapeHtml(g.title)}</th>`).join("")}</tr>` : ""}
    <tr><th class="gl-fix gl-day">Date</th><th class="gl-fix">Opp</th><th class="gl-fix">Result</th>${cols.map((c) =>
      `<th class="num" title="${escapeAttr(c.title)}">${escapeHtml(c.label)}</th>`).join("")}</tr></thead>`;
  const rows = (d.games || []).map((g) => {
    const res = g.result ? `<span class="${g.result === "W" ? "gl-w" : g.result === "L" ? "gl-l" : "gl-t"}">${
      escapeHtml(g.result)}</span> ${escapeHtml(g.score || "")}` : "";
    const cells = g.dnp ? `<td class="gl-dnp" colspan="${cols.length}">Did not play</td>`
      : cols.map((c) => `<td class="num">${escapeHtml(glCell((g.values || {})[c.id], c.label))}</td>`).join("");
    return `<tr><td class="gl-fix gl-day">${glDay(g)}</td>
      <td class="gl-fix gl-opp">${g.home ? "vs" : "@"} ${escapeHtml(g.opponent || "")}</td>
      <td class="gl-fix gl-res">${res}</td>${cells}</tr>`;
  }).join("");
  const sumRow = (label, vals) => `<tr class="gl-sum"><td class="gl-fix" colspan="3">${escapeHtml(label)}</td>${cols.map((c) =>
    `<td class="num">${escapeHtml(glCell((vals || {})[c.id], c.label))}</td>`).join("")}</tr>`;
  const foot = d.played ? `<tfoot>${sumRow(`Season · ${plural(d.played, "game")}`, d.totals)}${
    sumRow("Per game", d.per_game)}</tfoot>` : "";
  return `<div class="gl-scroll"><table class="agate gl-table">${head}<tbody>${rows}</tbody>${foot}</table></div>`;
}
//: What each column means, each label once.
function glGlossaryHTML(d) {
  const seen = new Map();
  (d.groups || []).forEach((g) => g.cols.forEach((c) => {
    const k = `${c.label}|${c.title}`;
    if (!seen.has(k)) seen.set(k, `<li><b>${escapeHtml(c.label)}</b> ${escapeHtml(c.title)}${
      g.title && (d.groups || []).length > 1 ? ` <span>(${escapeHtml(g.title.toLowerCase())})</span>` : ""}</li>`);
  }));
  return seen.size ? `<div class="gl-gloss"><h4>What the columns mean</h4><ul>${[...seen.values()].join("")}</ul></div>` : "";
}
function glBodyHTML(d, sport) {
  if (!d || !d.player || !(d.games || []).length) {
    return `<p class="gl-empty">No games are on file for this player yet. A game is added once its box score is in.</p>`;
  }
  const pick = (d.seasons || []).length > 1 ? `<label class="gl-season">Season <select data-gl-season>${d.seasons.map((s) =>
    `<option value="${s}"${s === d.season ? " selected" : ""}>${s}</option>`).join("")}</select></label>` : "";
  const who = [d.team, d.position, GL_SPORT[sport] || String(sport || "").toUpperCase()].filter(Boolean).join(" · ");
  return `<div class="gl-head"><h3>${escapeHtml(d.player)} <span>Game log</span></h3>
      <p>${escapeHtml(who)} · ${escapeHtml(String(d.season))}</p>${pick}</div>
    ${glTableHTML(d)}${glGlossaryHTML(d)}`;
}

function glClose() {
  const ov = document.getElementById("gl-overlay");
  if (!ov) return;
  ov.classList.remove("open");
  ov.innerHTML = "";
  if (typeof lockScroll === "function") lockScroll(false);
  document.removeEventListener("keydown", glKey);
}
function glKey(e) { if (e.key === "Escape") glClose(); }

async function glOpen(player, sport) {
  if (!player || !sport) return;
  let ov = document.getElementById("gl-overlay");
  if (!ov) {
    ov = document.createElement("div");
    ov.id = "gl-overlay";
    document.body.appendChild(ov);
    ov.addEventListener("click", (e) => {
      if (e.target === ov || (e.target.closest && e.target.closest(".gl-x"))) glClose();
    });
    ov.addEventListener("change", async (e) => {
      const sel = e.target.closest && e.target.closest("[data-gl-season]");
      if (!sel || !ov._gl) return;
      const body = ov.querySelector(".gl-body");
      if (body) body.innerHTML = `<p class="gl-empty">Loading ${escapeHtml(sel.value)}…</p>`;
      const d = await glFetch(ov._gl.sport, ov._gl.player, sel.value);
      if (body && ov._gl) body.innerHTML = glBodyHTML(d, ov._gl.sport);
    });
  }
  ov._gl = { player, sport };
  ov.innerHTML = `<div class="gl" role="dialog" aria-modal="true" aria-label="${escapeAttr(`Game log — ${player}`)}">
    <button class="gl-x" type="button" aria-label="Close">×</button>
    <div class="gl-body"><p class="gl-empty">Loading ${escapeHtml(player)}’s game log…</p></div></div>`;
  ov.classList.add("open");
  if (typeof lockScroll === "function") lockScroll(true);
  document.addEventListener("keydown", glKey);
  const x = ov.querySelector(".gl-x");
  if (x) x.focus({ preventScroll: true });
  const d = await glFetch(sport, player);
  const body = ov.querySelector(".gl-body");
  if (body && ov._gl && ov._gl.player === player) body.innerHTML = glBodyHTML(d, sport);
}
