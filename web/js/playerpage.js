/* PLAYER PAGES (js/playerpage.js, loaded the first time one opens).

   Ethan, 2026-11-16, with ESPN's page for Josh Allen: "The page should look
   just like this and have each menu for all players in all sports." The
   address #player/<name> (a name tapped in the search's list, which shows only
   names and faces since 2026-11-17, or any other door to a player) makes
   app.js renderPlayers hand the page here, and it becomes that player's page: a header in the club's colours with the face, the name,
   "Club · #N · POS" and height, weight and age, then six menus.

     Overview  the season's four numbers with their places in the league, the
               newest game (the score, both records, four numbers from it), a
               game's average split by that game, its month, its opponent and
               where, the last five games and the latest headlines, then
               tonight's markets (the card this page always drew, the longest);
     News      the roster's latest note, any move between clubs, and the
               headlines that name the player or the club (headlines and
               links only);
     Stats     season by season, and the career;
     Bio       the roster's facts;
     Splits    the season a game's average at a time (a baseball season's
               totals), by venue, result, month, opponent and, for a
               hitter, the starter's hand;
     Game Log  the season a line a game (js/gamelog.js, drawn in place).

   Everything but the headlines comes from /api/players/page (engine/
   playerpage), kept for the visit; the open menu is remembered per player, so
   the page's own redraw every minute never moves the reader. Its words never
   assume who the player is: the WNBA's players have pages too. */

const PLR_SPORTS = ["nfl", "cfb", "nba", "wnba", "cbb", "nhl", "mlb", "ufc"];
const PLR_TABS = [["overview", "Overview"], ["news", "News"], ["stats", "Stats"], ["bio", "Bio"],
  ["splits", "Splits"], ["log", "Game Log"]];
//: A fighter's menus (engine/ufc/fighterpage): a fight has no season or game log, so its history is Fights.
const PLR_TABS_UFC = [["overview", "Overview"], ["fights", "Fights"], ["stats", "Stats"], ["bio", "Bio"], ["news", "News"]];
const plrTabsOf = (sport) => (sport === "ufc" ? PLR_TABS_UFC : PLR_TABS);
const PLR_CACHE = new Map();
const PLR_TAB = {};
//: Rates print to a tenth (goals against to a hundredth), counts whole.
const PLR_RATES = ["CMP%", "AVG", "RTG", "FG%", "3P%", "FT%", "SV%", "K/9"];
//: A season's best single game, never an average: a kicker's long reads 52, not 52.0.
const PLR_WHOLE = ["LNG"];
//: Leagues whose season is said across two years ("2026–27"); the file labels a season by the year it started.
const PLR_TWO_YEARS = ["nba", "nhl", "cbb"];
//: The seasons picked in the Splits and Game Log menus, kept through the page's redraw.
const PLR_PICK = {};
let _plrNews = null;

async function plrFetch(sport, player, team, season) {
  const key = `${sport}|${player}|${team || ""}|${season || ""}`;
  if (PLR_CACHE.has(key)) return PLR_CACHE.get(key);
  let body = null;
  try {
    const q = new URLSearchParams({ sport, player });
    if (team) q.set("team", team);
    if (season) q.set("season", String(season));
    const r = await fetch(`/api/players/page?${q}`);
    body = r.ok ? await r.json() : null;
  } catch (e) { body = null; }
  if (body && body.player) PLR_CACHE.set(key, body);
  return body;
}
async function plrHeadlines() {
  if (_plrNews) return _plrNews;
  try {
    const r = await boardFetch("data/news.json", { cache: "no-cache" });
    _plrNews = r.ok ? await r.json() : {};
  } catch (e) { _plrNews = {}; }
  return _plrNews;
}

//: A number as its column says it; an average (`avg`) always to a tenth, so 27.0 reads as one.
function plrNum(v, label, avg) {
  if (v == null || v === "") return "—";
  if (typeof v === "string") return v;
  let out;
  if (label === "GAA") out = v.toFixed(2);
  else if (PLR_RATES.includes(label)) out = v.toFixed(1);
  else if (label === "TOI") {
    const m = Math.floor(v), s = Math.round((v - m) * 60);
    out = `${m}:${String(s === 60 ? 0 : s).padStart(2, "0")}`;
  } else if (PLR_WHOLE.includes(label)) out = String(Math.round(v));
  else if (avg) out = v.toFixed(1);
  else if (Number.isInteger(v)) out = v.toLocaleString();
  else out = v.toFixed(1);
  return trueMinus(out);
}
function plrSeasonLabel(sport, s) {
  return PLR_TWO_YEARS.includes(sport) ? `${s}–${String((Number(s) + 1) % 100).padStart(2, "0")}` : String(s);
}
function plrOrd(n) {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" })[n % 10] || "th";
  return `${n}${s}`;
}
function plrDay(iso, opts) {
  const d = iso ? new Date(`${iso.slice(0, 10)}T12:00:00`) : null;
  return d && !isNaN(d) ? d.toLocaleDateString(undefined, opts || { month: "short", day: "numeric" }) : "";
}
function plrAge(bio) {
  const d = bio.born ? new Date(`${bio.born}T12:00:00`) : null;
  if (d && !isNaN(d)) {
    const now = new Date();
    let a = now.getFullYear() - d.getFullYear();
    if (now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) a -= 1;
    return a;
  }
  return bio.age || "";
}
function plrClub(sport, team) {
  const t = (typeof teamsIn === "function" ? teamsIn(sport) : {})[team] || {};
  // A colour as CSS reads it: a feed that writes "0c2340" gets its hash (college's teams may).
  const raw = String(t.primary || "").trim();
  const color = /^#?[0-9a-f]{6}$/i.test(raw) ? (raw[0] === "#" ? raw : `#${raw}`) : "";
  return { name: t.name || teamNameIn(sport, team) || team || "", nick: t.nick || "", color };
}
function plrNorm(s) {
  return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
//: A name as a whole word in a headline.
function plrWord(word) {
  return word ? new RegExp(`\\b${word.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&")}\\b`) : null;
}

/* ---------------- the frame ---------------- */
function plrHeroHTML(player, sport, team, pos, face, bio) {
  const club = plrClub(sport, team);
  const parts = String(player).trim().split(/\s+/);
  const first = parts.length > 1 ? parts[0] : "", rest = parts.length > 1 ? parts.slice(1).join(" ") : parts[0];
  const num = bio && bio.number !== "" && bio.number != null ? `#${bio.number}` : "";
  const ufc = sport === "ufc";
  const line = (ufc ? [(bio && bio.division) || pos, bio && bio.record]
    : [club.name, num, (bio && bio.position) || pos]).filter(Boolean).map(escapeHtml).join(" · ");
  const age = bio ? plrAge(bio) : "";
  const body = bio ? (ufc ? [bio.nickname ? `“${bio.nickname}”` : "", bio.height, bio.reach ? `${bio.reach} reach` : "",
    age !== "" ? `Age ${age}` : ""] : [bio.height, bio.weight, age !== "" ? `Age ${age}` : ""])
    .filter(Boolean).map(escapeHtml).join(" · ") : "";
  // THE CLUB'S LIGHT BEHIND THE WHOLE PAGE (styles.css .amb-club, SITEBG1),
  // inside the header so a redrawn header brings its own and leaves none.
  return `<header class="plr-hero"${club.color ? ` style="--plr-c:${escapeAttr(club.color)}"` : ""}>
      ${club.color ? `<div class="amb-club" style="--amb-c:${escapeAttr(club.color)}" aria-hidden="true"></div>` : ""}
      ${team ? `<span class="plr-mark" aria-hidden="true">${teamMarkIn(sport, team, 168)}</span>` : ""}
      <div class="plr-face">${playerAvatar(player, team, { size: 92, headshot: face, map: teamsIn(sport) })}</div>
      <div class="plr-who">
        <h2 class="plr-name">${first ? `<span>${escapeHtml(first)}</span> ` : ""}<b>${escapeHtml(rest)}</b></h2>
        <p class="plr-club">${team ? teamMarkIn(sport, team, 18) : ""}<span>${line || escapeHtml(lgCode(sport))}</span></p>
        ${body ? `<p class="plr-body">${body}</p>` : ""}
        <div class="plr-flag">${typeof injTag === "function" ? injTag(sport, player) : ""}</div>
      </div>
    </header>`;
}
function plrTabsHTML(open, sport) {
  return `<div class="plr-tabs" role="tablist" aria-label="Player page">${plrTabsOf(sport).map(([k, label]) =>
    `<button type="button" role="tab" class="plr-tab${k === open ? " on" : ""}" data-plr-tab="${k}" aria-selected="${
      k === open}">${label}</button>`).join("")}</div>`;
}
function plrPanelsHTML(open, sport) {
  return plrTabsOf(sport).map(([k]) => `<div class="plr-panel" data-plr-panel="${k}" role="tabpanel"${k === open ? "" : " hidden"}>${
    k === "overview" ? `<div class="plr-tapped"></div><div class="plr-season"></div>${sport === "ufc" ? `<div class="plr-next"></div>`
      : `<div class="plr-prev"></div><div class="plr-charts"></div><div class="plr-splitlet"></div>`}
      <div class="plr-recent"></div><div class="plr-latest"></div><div class="plr-tonight"></div>`
      : `<p class="plr-wait">Loading…</p>`}</div>`).join("");
}

/* ---------------- Overview ---------------- */
function plrSeasonHTML(d, note = "") {
  const nums = (d.headline || []).filter((h) => h.value != null);
  if (!nums.length) return "";
  const ranked = nums.some((h) => h.rank);
  return `<section class="plr-card plr-strip"><h3>${escapeHtml(plrSeasonLabel(d.sport, d.season))} season${ranked
      ? ` <span>Where each ranks in the ${escapeHtml(lgCode(d.sport))} this season</span>` : ""}</h3>${
      note ? `<p class="plr-quiet">${escapeHtml(note)}</p>` : ""}
    <div class="plr-nums">${nums.map((h) => `<div class="plr-num" title="${escapeAttr(h.title)}">
      <span class="plr-k">${escapeHtml(h.label)}</span><b>${escapeHtml(plrNum(h.value, h.label, h.per_game))}</b>${
      h.rank ? `<span class="plr-rank">${plrOrd(h.rank)}${h.low ? " fewest" : ""}</span>` : ""}</div>`).join("")}</div></section>`;
}
/* A season with games on file and none played: the newest season the player did play, said as such
   (engine/playerpage `prior`; Jake Tonges' 2026 showed no season card at all). */
function plrPriorHTML(d) {
  const p = d.prior;
  if (!p) return "";
  return plrSeasonHTML({ ...d, season: p.season, headline: p.headline },
    `No games played in ${plrSeasonLabel(d.sport, d.season)} yet; these are the numbers from the last season played.`);
}
function plrPrevHTML(d) {
  const g = d.last;
  if (!g) return "";
  // An NFL playoff game by its round ("Divisional"), not "Week 20" (gamelog.js glRound, loaded with the page's
  // Overview; the week number until it is).
  const round = typeof glRound === "function" ? glRound(d.sport, d.season, g.week) : "";
  const when = [round || (g.week ? `Week ${g.week}` : ""), plrDay(g.date)].filter(Boolean).join(" · ");
  const [mine, theirs] = String(g.score || "").split("-");
  const side = (team, rec, pts, won) => `<div class="plr-side">${teamMarkIn(d.sport, team, 34)}<div><b>${
    escapeHtml(teamNameIn(d.sport, team) || team)}</b>${rec ? `<small>${escapeHtml(rec)}</small>` : ""}</div>${
    pts != null && pts !== "" ? `<span class="plr-pts${won ? " plr-won" : ""}">${escapeHtml(pts)}</span>` : ""}</div>`;
  const res = g.result ? `<span class="${g.result === "W" ? "gl-w" : g.result === "L" ? "gl-l" : "gl-t"}">${
    escapeHtml(g.result === "W" ? "Won" : g.result === "L" ? "Lost" : "Tied")}</span> · Final` : "";
  const tiles = g.dnp ? `<p class="plr-dnp">Did not play.</p>` : g.pending ? `<p class="plr-dnp">The box score isn’t in yet.</p>`
    : g.no_line ? `<p class="plr-dnp">No stats in this game’s box score.</p>`
    : (g.tiles || []).length ? `<div class="plr-tiles">${g.tiles.map((t) =>
    `<div class="plr-tile" title="${escapeAttr(t.title)}"><span class="plr-k">${escapeHtml(t.label)}</span><b>${
      escapeHtml(plrNum(t.value, t.label))}</b></div>`).join("")}</div>` : "";
  return `<section class="plr-card"><h3>Previous game <span>${escapeHtml(when)}${g.home ? " · home" : " · away"}</span></h3>
    <div class="plr-score">${side(g.team, g.record, mine, g.result === "W")}<div class="plr-mid">${res}</div>${
      side(g.opponent, g.opp_record, theirs, g.result === "L")}</div>${tiles}</section>`;
}
//: The columns a split table shows: his main group's, or every group's (the Splits menu).
function plrCols(groups, only) {
  return (groups || []).filter((g) => !only || g.key === only)
    .flatMap((g) => g.cols.map((c) => ({ ...c, id: `${g.key}.${c.key}`, group: g.title })));
}
function plrSplitTable(rows, cols, opts) {
  const o = opts || {};
  const head = `<thead><tr><th class="gl-fix">${escapeHtml(o.first || "Split")}</th><th class="num">GP</th>${cols.map((c) =>
    `<th class="num" title="${escapeAttr(c.title)}">${escapeHtml(c.label)}</th>`).join("")}</tr></thead>`;
  const body = rows.map((r) => r.break ? `<tr class="plr-break"><td class="gl-fix" colspan="${cols.length + 2}">${
      escapeHtml(r.break)}</td></tr>` : `<tr${r.sum ? ` class="gl-sum"` : ""}><td class="gl-fix">${escapeHtml(r.label)}</td><td class="num">${
      r.gp == null ? "" : escapeHtml(String(r.gp))}</td>${cols.map((c) =>
      `<td class="num">${escapeHtml(plrNum((r.values || {})[c.id], c.label, !!o.avg && r.avg !== false))}</td>`).join("")}</tr>`).join("");
  return `<div class="gl-scroll"><table class="agate gl-table plr-table">${head}<tbody>${body}</tbody></table></div>`;
}
function plrSplitletHTML(d) {
  const sp = d.splits || {}, g = d.last;
  if (!g || !(sp.rows || []).length) return "";
  const by = new Map(sp.rows.map((r) => [r.key, r]));
  const group = (sp.groups || []).some((x) => x.key === d.role) ? d.role : ((sp.groups || [])[0] || {}).key;
  const cols = plrCols(sp.groups, group);
  if (!cols.length) return "";
  const rows = [];
  if (!g.dnp && !g.pending && !g.no_line) rows.push({ label: "This game", gp: 1, values: g.values, avg: false });
  const month = g.date ? by.get(`m:${g.date.slice(0, 7)}`) : null;
  if (month) rows.push(month);
  const vs = by.get(`vs:${g.opponent}`);
  if (vs) rows.push(vs);
  const where = by.get(g.home ? "home" : "away");
  if (where) rows.push(where);
  if (by.get("season")) rows.push(by.get("season"));
  return `<section class="plr-card"><h3>Splits <span>${plrSplitWord(sp)}</span></h3>${
    plrSplitTable(rows, cols, { avg: !sp.totals })}
    <button class="btn plr-go" type="button" data-plr-go="splits">Every split</button></section>`;
}
//: A priced card wears its grade; a card from his history has none.
function plrTonightTitle(page) {
  return page.querySelector(".plr-tonight .grade") ? "Tonight’s markets" : "By market";
}
async function plrRecentInto(slot, d) {
  if (!slot || typeof glFetch !== "function") return;
  const log = await glFetch(d.sport, d.player, d.season);
  if (!slot.isConnected || !log || !(log.games || []).length) return;
  slot.innerHTML = `<section class="plr-card"><h3>Recent games</h3>${glTableHTML({ ...log, games: log.games.slice(0, 5), played: 0 })}
    <button class="btn plr-go" type="button" data-plr-go="log">Full game log</button></section>`;
}

/* THE PLAYER'S CHARTS, ON THE PAGE (Ethan, 2026-11-17, with Jalon Daniels' page: "We should still have the
   players route charts and pass charts and shit on the player page"). The pick page drew them in place (app.js
   chartSlot, js/carrychart.js `mount`); a tapped pick opens this page now, so the Overview draws them under the
   last game, as the pick page did: for the market the reader came for (the tapped pick's, shown first in the
   market cards), else tonight's first priced market, else the one the player's role leads with, with the
   position and tonight's opponent, so a receiver gets the route chart, a passer the throws, a back the carries,
   a hitter the spray chart, a pitcher the pitches, a shooter the shots and a skater or a goalie the shot map, each
   with the matchup where an opponent is named. The chart module picks which and hides the slot when there are
   none (a lineman, a defender). Drawn once: the minute's redraw keeps the chart and the game picked in it. */
const PLR_CHART_MKT = { passing: "pass_yds", rushing: "rush_yds", receiving: "rec_yds", kicking: "kick_pts",
  box: "pts", skater: "sog", goalie: "saves", batting: "hits", pitching: "strikeouts" };
function plrChartRow(page, d) {
  const { player, sport } = page._plr;
  const rows = ((typeof _profRows !== "undefined" && _profRows.get(player)) || []).filter((r) => r && r.market);
  const tab = typeof _profTab !== "undefined" ? _profTab[player] : "";
  const priced = rows.find((r) => r.market_label === tab) || rows[0];
  if (priced) return { ...priced, sport: priced.sport || sport, position: priced.position || d.position || "" };
  // A college passer's throws since 2026-11-17 (engine/passes.CfbPasses), as an NFL passer's.
  const mkt = PLR_CHART_MKT[d.role] || "";
  return mkt ? { player, sport, market: mkt, position: d.position || "", opponent: "" } : null;
}
function plrChartsInto(page, d) {
  const slot = page.querySelector(".plr-charts");
  if (!slot || typeof chartSlot !== "function" || typeof mountCharts !== "function") return;
  const r = plrChartRow(page, d);
  const html = r ? chartSlot(r) : "";
  if (slot._html === html) return;
  slot._html = html;
  slot.innerHTML = html;
  if (html) mountCharts(slot);
}

/* ---------------- News ---------------- */
function plrNewsRows(d, news) {
  const league = ((news || {}).sports || {})[d.sport] || [];
  const club = plrClub(d.sport, d.team);
  const full = plrNorm(d.player), last = plrNorm(typeof surname === "function" ? surname(d.player) : d.player);
  const lastRe = plrWord(last), nickRe = plrWord(club.nick);
  const named = [], team = [];
  league.forEach((h) => {
    const t = plrNorm(h.title);
    const clubNamed = (nickRe && nickRe.test(h.title || "")) || (club.name && t.includes(plrNorm(club.name)));
    if (t.includes(full) || (lastRe && lastRe.test(t) && clubNamed)) named.push(h);
    else if (clubNamed) team.push(h);
  });
  return { named, team, league, club };
}
function plrHeadlineHTML(h) {
  const when = h.epoch ? new Date(h.epoch * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
  return `<li><a href="${safeHref(h.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(h.title || "")}</a>
    <span>${escapeHtml([h.source, when].filter(Boolean).join(" · "))}</span></li>`;
}
function plrNoteHTML(d) {
  const n = d.notes || {}, hurt = n.injury;
  const parts = [];
  if (hurt) {
    const head = [hurt.status, hurt.what].filter(Boolean).join(" · ");
    parts.push(`<div class="plr-note"><b>${escapeHtml(head || "Injury")}</b>${hurt.note ? `<p>${escapeHtml(hurt.note)}</p>` : ""}${
      hurt.back ? `<span>Expected back around ${escapeHtml(plrDay(hurt.back, { month: "long", day: "numeric" }))}</span>` : ""}${
      hurt.source ? `<span>Per ${escapeHtml(hurt.source === "sleeper" ? "Sleeper" : hurt.source)}</span>` : ""}</div>`);
  }
  (n.moves || []).forEach((m) => parts.push(`<div class="plr-note"><b>Joined ${escapeHtml(teamNameIn(d.sport, m.to) || m.to)}</b><p>From ${
    escapeHtml(teamNameIn(d.sport, m.from) || m.from)}${m.date ? `, ${escapeHtml(plrDay(m.date, { month: "long", day: "numeric" }))}` : ""}.</p></div>`));
  return parts.join("");
}
function plrNewsHTML(d, news) {
  const { named, team, league, club } = plrNewsRows(d, news);
  const note = plrNoteHTML(d);
  const list = (rows) => `<ul class="plr-heads">${rows.map(plrHeadlineHTML).join("")}</ul>`;
  let html = note ? `<section class="plr-card"><h3>The latest</h3>${note}</section>` : "";
  if (named.length) html += `<section class="plr-card"><h3>In the headlines</h3>${list(named)}</section>`;
  if (team.length) html += `<section class="plr-card"><h3>${escapeHtml(club.nick || club.name || d.team)} headlines</h3>${list(team.slice(0, 8))}</section>`;
  if (!named.length && !team.length && league.length) {
    html += `<section class="plr-card"><h3>Around the ${escapeHtml(lgCode(d.sport))}</h3><p class="plr-quiet">No headline names this player or the club right now.</p>${
      list(league.slice(0, 6))}</section>`;
  }
  return (html || `<p class="plr-quiet">No news right now.</p>`)
    + `<p class="plr-fine">Headlines and links only, from the publishers’ own feeds. The reporting lives at the source.</p>`;
}
function plrLatestHTML(d, news) {
  const { named, team } = plrNewsRows(d, news);
  const note = plrNoteHTML(d);
  const rows = [...named, ...team].slice(0, 3);
  if (!note && !rows.length) return "";
  return `<section class="plr-card"><h3>Latest</h3>${note}${rows.length ? `<ul class="plr-heads">${rows.map(plrHeadlineHTML).join("")}</ul>` : ""}
    <button class="btn plr-go" type="button" data-plr-go="news">All news</button></section>`;
}

/* ---------------- Stats, Bio, Splits ---------------- */
function plrStatsHTML(d) {
  const c = d.career || {};
  if (!(c.rows || []).length || !(c.groups || []).length) {
    return `<p class="plr-quiet">${escapeHtml(d.no_stats || "No seasons on file yet.")}</p>`;
  }
  return (c.groups || []).map((g) => {
    const cols = plrCols([g]);
    const rows = c.rows.map((r) => ({ label: `${plrSeasonLabel(d.sport, r.season)}${r.team ? ` · ${r.team}` : ""}`, gp: r.gp,
      values: r.values }));
    rows.push({ label: "Career", gp: c.total.gp, values: c.total.values, sum: true });
    return `<section class="plr-card"><h3>${escapeHtml(g.title || "Season by season")} <span>${
      c.per_game ? "A game’s average" : "Totals"}</span></h3>${plrSplitTable(rows, cols, { first: "Season", avg: c.per_game })}</section>`;
  }).join("");
}
function plrBioHTML(d) {
  const b = d.bio || {}, club = plrClub(d.sport, b.team || d.team);
  const born = b.born ? `${plrDay(b.born, { year: "numeric", month: "long", day: "numeric" })}${plrAge(b) !== "" ? ` (age ${plrAge(b)})` : ""}` : "";
  const exp = b.rookie ? "Rookie" : b.years_exp !== "" && b.years_exp != null ? `${plrOrd(Number(b.years_exp) + 1)} season` : "";
  const facts = [
    ["Team", b.team || d.team ? `${teamMarkIn(d.sport, b.team || d.team, 18)} ${escapeHtml(club.name)}` : ""],
    ["Position", escapeHtml(b.position || d.position || "")],
    ["Number", b.number !== "" && b.number != null ? `#${escapeHtml(b.number)}` : ""],
    ["Height", escapeHtml(b.height || "")], ["Weight", escapeHtml(b.weight || "")],
    ["Born", escapeHtml(born)], ["Birthplace", escapeHtml(b.birthplace || "")],
    ["College", escapeHtml(b.college || "")], ["Experience", escapeHtml(exp)],
    ["Shoots", escapeHtml(b.shoots === "L" ? "Left" : b.shoots === "R" ? "Right" : b.shoots || "")],
    ["Status", escapeHtml(b.status || "")],
    ["On file", b.first_season ? escapeHtml(`${b.first_season === b.last_season ? plrSeasonLabel(d.sport, b.first_season)
      : `${plrSeasonLabel(d.sport, b.first_season)} to ${plrSeasonLabel(d.sport, b.last_season)}`} · ${
      plural(b.games || 0, "game")}`) : ""],
  ].filter(([, v]) => v);
  return `<section class="plr-card"><h3>Bio</h3><dl class="plr-bio">${facts.map(([k, v]) =>
    `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
    <p class="plr-fine">From the club’s published roster. A fact the roster does not list is left out.</p></section>`;
}
function plrSeasonPick(d, attr) {
  return (d.seasons || []).length > 1 ? `<label class="gl-season">Season <select ${attr}>${d.seasons.map((s) =>
    `<option value="${s}"${s === d.season ? " selected" : ""}>${escapeHtml(plrSeasonLabel(d.sport, s))}</option>`).join("")}</select></label>` : "";
}
//: A split is a game's average, or (a baseball split, `totals`) the games added up, as a box score reads.
const plrSplitWord = (sp) => (sp.totals ? "Totals" : "A game’s average");
function plrSplitsHTML(d) {
  const sp = d.splits || {};
  if (!(sp.rows || []).length) return `<p class="plr-quiet">No games on file for this season.</p>`;
  const rows = [];
  let lastKind = "";
  sp.rows.forEach((r) => {
    const kind = r.key.startsWith("m:") ? "By month" : r.key.startsWith("vs:") ? "By opponent" : "";
    if (kind && kind !== lastKind) rows.push({ break: kind });
    lastKind = kind || lastKind;
    rows.push(r);
  });
  return `<div class="plr-pick">${plrSeasonPick(d, "data-plr-season")}</div>` + (sp.groups || []).map((g) =>
    `<section class="plr-card"><h3>${escapeHtml(g.title || "Splits")} <span>${plrSplitWord(sp)}</span></h3>${
      plrSplitTable(rows, plrCols([g]), { avg: !sp.totals })}</section>`).join("");
}

/* ---------------- drawing ---------------- */
/* ---------------- A fighter (engine/ufc/fighterpage; Ethan, 2026-11-17: "yes full fighter page") ---------------- */
//: A rate as its tile says it: a share as a percent, a rate to two places.
const plrRate = (r) => (r.pct ? `${Number(r.value).toFixed(0)}%` : Number(r.value).toFixed(2));
//: "KO/TKO", "Submission" or "Decision", as a fight site says how it ended.
const PLR_HOW = { "KO/TKO": "KO/TKO", SUB: "Submission", DEC: "Decision" };
function plrUfcRatesHTML(d) {
  const lead = (d.rates || []).filter((r) => r.lead);
  const rec = (d.bio || {}).record;
  if (!lead.length && !rec) return "";
  const tile = (k, v, t) => `<div class="plr-num"${t ? ` title="${escapeAttr(t)}"` : ""}><span class="plr-k">${escapeHtml(k)}</span><b>${
    escapeHtml(v)}</b></div>`;
  return `<section class="plr-card plr-strip"><h3>Career <span>${d.tracked ? `Rates over ${plural(d.tracked, "tracked fight")}`
      : "The fighter’s measured rates"}</span></h3>
    <div class="plr-nums">${rec ? tile("Record", rec, "Wins, losses and draws") : ""}${lead.slice(0, rec ? 3 : 4)
      .map((r) => tile(r.label, plrRate(r), r.title)).join("")}</div></section>`;
}
function plrUfcNextHTML(d) {
  const n = d.next;
  if (!n || !n.opponent) return "";
  // The card's date as the site says a day ("Sat, Dec 12"); a label the board wrote otherwise, as written.
  const day = /^\d{4}-\d{2}-\d{2}/.test(n.date || "") ? plrDay(n.date, { weekday: "short", month: "short", day: "numeric" }) : n.date;
  return `<section class="plr-card"><h3>Next fight</h3><p class="plr-ufc-next">vs <b>${escapeHtml(n.opponent)}</b>${
    day ? ` · ${escapeHtml(day)}` : ""}${n.division ? ` · ${escapeHtml(n.division)}` : ""}</p>
    <button class="btn plr-go" type="button" data-plr-card="ufc">The fight card</button></section>`;
}
//: A fight's numbers as "landed of thrown", his and the opponent's.
function plrUfcStat(f, key) {
  const s = (f.stats || []).find((x) => x.key === key);
  if (!s || s.me == null) return "—";
  return s.me_att != null ? `${s.me} of ${s.me_att}` : String(s.me);
}
function plrUfcFightsHTML(d, n) {
  const all = d.fights || [];
  if (!all.length) return `<p class="plr-quiet">No tracked fights on file for this fighter yet.</p>`;
  const rows = n ? all.slice(0, n) : all;
  const res = (r) => (r === "W" ? "plr-w" : r === "L" ? "plr-l" : "");
  const body = rows.map((f) => `<tr><td class="gl-fix">${escapeHtml(plrDay(f.date, { year: "numeric", month: "short", day: "numeric" }))}</td>
    <td>${escapeHtml(f.opp || "")}</td><td class="plr-res ${res(f.result)}">${escapeHtml(f.result === "W" ? "Win" : f.result === "L" ? "Loss"
      : "Draw / NC")}</td><td>${escapeHtml(PLR_HOW[f.method] || f.method || "")}</td><td class="num">${f.rnd ? escapeHtml(String(f.rnd)) : ""}</td>
    <td class="num">${escapeHtml(f.clock || "")}</td><td class="num">${escapeHtml(plrUfcStat(f, "ssl"))}</td>
    <td class="num">${escapeHtml(plrUfcStat(f, "tdl"))}</td><td class="num">${escapeHtml(plrUfcStat(f, "kd"))}</td></tr>`).join("");
  const table = `<div class="gl-scroll"><table class="agate gl-table plr-table"><thead><tr><th class="gl-fix">Date</th><th>Opponent</th>
    <th>Result</th><th>Method</th><th class="num">Rnd</th><th class="num">Time</th><th class="num" title="Significant strikes landed of thrown">Sig. str.</th>
    <th class="num" title="Takedowns landed of tried">TD</th><th class="num" title="Knockdowns">KD</th></tr></thead><tbody>${body}</tbody></table></div>`;
  return n ? `<section class="plr-card"><h3>Recent fights</h3>${table}
      ${all.length > n ? `<button class="btn plr-go" type="button" data-plr-go="fights">Every fight</button>` : ""}</section>`
    : `<section class="plr-card"><h3>Every tracked fight <span>Newest first</span></h3>${table}
      <div class="plr-ufc-acts">${typeof ccDoor === "function" ? ccDoor(d.player, "ufc", "fights", "Fight history chart", d.face) : ""}</div>
      <p class="plr-fine">The fights ESPN tracked, with both fighters’ numbers where it kept them.</p></section>`;
}
function plrUfcStatsHTML(d) {
  const by = (keys) => (d.rates || []).filter((r) => keys.includes(r.key));
  const card = (title, rows) => rows.length ? `<section class="plr-card"><h3>${title}</h3><dl class="plr-bio">${rows.map((r) =>
    `<div title="${escapeAttr(r.title)}"><dt>${escapeHtml(r.label)}</dt><dd>${escapeHtml(plrRate(r))}</dd></div>`).join("")}</dl>
    <p class="plr-fine">${rows.map((r) => `${escapeHtml(r.label)}: ${escapeHtml(r.title.toLowerCase())}`).join(" · ")}.</p></section>` : "";
  const ln = d.line || {};
  const how = (d.by_method || []).filter((m) => m.w || m.l);
  const ended = how.length ? `<section class="plr-card"><h3>How the fights ended <span>${plural(ln.n || 0, "tracked fight")}</span></h3>
    <dl class="plr-bio">${how.map((m) => `<div><dt>${escapeHtml(m.name)}</dt><dd>${m.w} won · ${m.l} lost</dd></div>`).join("")}${
      ln.finish_w != null ? `<div><dt>Wins by finish</dt><dd>${Math.round(ln.finish_w * 100)}%</dd></div>` : ""}${
      ln.distance != null ? `<div><dt>Went the distance</dt><dd>${Math.round(ln.distance * 100)}%</dd></div>` : ""}${
      ln.avg_secs ? `<div><dt>Average fight</dt><dd>${Math.floor(ln.avg_secs / 60)}:${String(Math.round(ln.avg_secs % 60)).padStart(2, "0")}</dd></div>` : ""}${
      ln.r1 ? `<div><dt>First-round finishes</dt><dd>${ln.r1}</dd></div>` : ""}</dl></section>` : "";
  const rounds = (d.by_rounds || []).map((r) => `<div><dt>${r.rounds}-round fights</dt><dd>${r.w}-${r.l}${r.d ? `-${r.d}` : ""}${
    r.finish_w != null ? ` · ${Math.round(r.finish_w * 100)}% of wins by finish` : ""}</dd></div>`).join("");
  const fin = (d.by_finish || []).map((x) => `<div><dt>${escapeHtml(x.name)}</dt><dd>${plural(x.n, "fight")}</dd></div>`).join("");
  return (card("Striking", by(["slpm", "sapm", "str_def", "kd_per100"])) + card("Grappling", by(["td_per15", "td_acc", "tdd", "sub_att_per15"]))
    + ended + (rounds ? `<section class="plr-card"><h3>By rounds scheduled</h3><dl class="plr-bio">${rounds}</dl></section>` : "")
    + (fin ? `<section class="plr-card"><h3>When the fights ended</h3><dl class="plr-bio">${fin}</dl></section>` : ""))
    || `<p class="plr-quiet">No measured rates for this fighter yet: they come from tracked fights.</p>`;
}
function plrUfcBioHTML(d) {
  const b = d.bio || {};
  const born = b.born ? `${plrDay(b.born, { year: "numeric", month: "long", day: "numeric" })}${plrAge(b) !== "" ? ` (age ${plrAge(b)})` : ""}`
    : b.age ? `Age ${b.age}` : "";
  const facts = [["Record", b.record], ["Division", b.division], ["Nickname", b.nickname], ["Height", b.height], ["Weight", b.weight],
    ["Reach", b.reach], ["Stance", b.stance], ["Born", born], ["Birthplace", b.birthplace], ["Country", b.country], ["Team", b.team],
    ["Fights on file", d.tracked ? `${plural(d.tracked, "tracked fight")}${b.first_fight ? ` since ${plrDay(b.first_fight, { year: "numeric", month: "short" })}` : ""}` : ""],
    ["Last fight", b.last_fight ? plrDay(b.last_fight, { year: "numeric", month: "long", day: "numeric" }) : ""]].filter(([, v]) => v);
  return `<section class="plr-card"><h3>Bio</h3><dl class="plr-bio">${facts.map(([k, v]) =>
    `<div><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`).join("")}</dl>
    <p class="plr-fine">From the fighter’s published record and ESPN’s fighter page. A fact neither lists is left out.</p></section>`;
}
function plrFillUfc(page, d) {
  const at = (sel) => page.querySelector(sel);
  const set = (sel, html) => { const el = at(sel); if (el) el.innerHTML = html; };
  if (!d || !d.player) {
    const msg = `<p class="plr-quiet">${d ? `We have no UFC fighter named ${escapeHtml(page._plr.player)}: no dossier or tracked fight lists them.`
      : "This page could not load. Open it again in a minute."}</p>`;
    page.querySelectorAll(".plr-panel[data-plr-panel]:not([data-plr-panel=\"overview\"]), .plr-season").forEach((p) => { p.innerHTML = msg; });
    return;
  }
  const hero = at(".plr-hero");
  if (hero) hero.outerHTML = plrHeroHTML(d.player, "ufc", "", (d.bio || {}).division || "", d.face || page._plr.face, d.bio || {});
  set(".plr-season", plrUfcRatesHTML(d));
  set(".plr-next", plrUfcNextHTML(d));
  set(".plr-recent", plrUfcFightsHTML(d, 5));
  set("[data-plr-panel=\"fights\"]", plrUfcFightsHTML(d));
  set("[data-plr-panel=\"stats\"]", plrUfcStatsHTML(d));
  set("[data-plr-panel=\"bio\"]", plrUfcBioHTML(d));
  plrHeadlines().then((news) => {
    if (!page.isConnected) return;
    set("[data-plr-panel=\"news\"]", plrNewsHTML(d, news));
    set(".plr-latest", plrLatestHTML(d, news));
  });
}
//: The next fight's card: the UFC tab, where its pick and its report are.
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("[data-plr-card]");
  if (b && typeof switchView === "function") switchView(b.dataset.plrCard);
});

function plrFill(page, d) {
  if (page._plr.sport === "ufc") return plrFillUfc(page, d);
  page._plr.noStats = (d && d.no_stats) || "";
  const host = page.querySelector(".plr-hero");
  if (host && d && d.bio) host.outerHTML = plrHeroHTML(d.player, d.sport, d.team, d.position,
    d.bio.headshot || page._plr.face, d.bio);
  // The page's own answer can name the club the search did not (a roster name, an address opened cold).
  if (d && d.team && d.team !== page._plr.team && page.isConnected && _plrLive && _plrLive.page === page) {
    page._plr.team = d.team;
    plrFrameOn(page._plr.sport, d.team);
  }
  const at = (sel) => page.querySelector(sel);
  if (!d || !d.player) {
    // No answer at all is a page that could not load; an empty one is the server saying the league holds
    // nobody by this name (no box score, no roster: a player who left for another league, an old link).
    const { player, sport } = page._plr;
    const msg = `<p class="plr-quiet">${d ? `We have no ${escapeHtml(lgCode(sport))} player named ${escapeHtml(player)}: no box
      score or roster we keep lists them.` : "This page could not load. Open it again in a minute."}</p>`;
    page.querySelectorAll(".plr-panel[data-plr-panel]:not([data-plr-panel=\"overview\"]), .plr-season")
      .forEach((p) => { p.innerHTML = msg; });
    return;
  }
  const set = (sel, html) => { const el = at(sel); if (el) el.innerHTML = html; };
  // On the roster, no game logged yet (a freshman, a backup): the page says so, and the rest is the roster's.
  // Games with no numbers in them (a punter, a lineman, a team defense) say the server's reason, as the
  // Stats and Game Log menus do, rather than leaving the Overview's first block empty.
  const quiet = (t) => `<p class="plr-quiet">${escapeHtml(t)}</p>`;
  set(".plr-season", (d.seasons || []).length ? plrSeasonHTML(d) || plrPriorHTML(d) || (d.no_stats ? quiet(d.no_stats) : "")
    : quiet(d.no_stats || "No games on file for this player yet. A game is added once its box score is in."));
  set(".plr-prev", plrPrevHTML(d));
  plrChartsInto(page, d);
  set(".plr-splitlet", plrSplitletHTML(d));
  set("[data-plr-panel=\"stats\"]", plrStatsHTML(d));
  set("[data-plr-panel=\"bio\"]", plrBioHTML(d));
  set("[data-plr-panel=\"splits\"]", plrSplitsHTML(d));
  const picked = (PLR_PICK[page._plr.key] || {}).splits;
  if (picked && String(picked) !== String(d.season)) plrSplitsFor(page, picked);
  plrHeadlines().then((news) => {
    if (!page.isConnected) return;
    set("[data-plr-panel=\"news\"]", plrNewsHTML(d, news));
    set(".plr-latest", plrLatestHTML(d, news));
  });
  loadRoom("js/gamelog.js", "css/gamelog.css").then((ok) => {
    if (!ok || !page.isConnected) return;
    if (glRound(d.sport, d.season, (d.last || {}).week)) set(".plr-prev", plrPrevHTML(d));   // "Week 20" was drawn first
    plrRecentInto(at(".plr-recent"), d);
    if (PLR_TAB[page._plr.key] === "log") plrLogInto(page);
  });
}
async function plrLogInto(page, season) {
  const slot = page.querySelector("[data-plr-panel=\"log\"]");
  if (!slot || typeof glFetch !== "function") return;
  const { sport, player, key } = page._plr;
  if (!season && slot.dataset.drawn) return;
  const d = await glFetch(sport, player, season || (PLR_PICK[key] || {}).log);
  if (!slot.isConnected) return;
  // A punter's page says why it has no games (engine/playerpage.no_stats_note).
  const quiet = !(d && (d.games || []).length) && page._plr.noStats;
  if (quiet) slot.innerHTML = `<p class="plr-quiet">${escapeHtml(quiet)}</p>`;
  else slot.innerHTML = glBodyHTML(d, sport, { inPage: true });
  slot.dataset.drawn = "1";
}
function plrShow(page, tab) {
  PLR_TAB[page._plr.key] = tab;
  page.querySelectorAll(".plr-tab").forEach((b) => {
    const on = b.dataset.plrTab === tab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", String(on));
  });
  page.querySelectorAll(".plr-panel").forEach((p) => { p.hidden = p.dataset.plrPanel !== tab; });
  if (tab === "log") loadRoom("js/gamelog.js", "css/gamelog.css").then((ok) => ok && plrLogInto(page));
}

/* THE PLAYER'S PAGE IN THE CLUB'S COLOURS (PLRWASH1; Ethan, 2026-11-17, with the Panthers @ Saints live
   page, its top circled: "the player page should be colorful with there team colors like how the live
   page looks"). The page wears its club's two colours as a live game's page wears its two clubs'
   (playerpage.css): put on <body> deepened until white type reads on them and as they are (app.js
   twWash, the whole-site wash's own pair), and the page is the player's alone: the search's head waits
   behind the way back, as a game's page has no search above its score. Off as soon as the board stops
   showing a player's page (a watcher on it, so every other drawing of the Players page takes the
   colours with it) or another page opens (app.js _switchViewNow). A club in black alone, or none
   known, keeps the site's light and the header's band. */
const PLR_WASH_VARS = ["--pw-1", "--pw-2", "--pw-1-paper", "--pw-2-paper"];
let _plrWatch = null, _plrPinRO = null;
function plrFrameOn(sport, team) {
  const view = document.getElementById("view-players"), board = document.getElementById("players-board");
  if (!view || !board) return;
  view.classList.add("plr-view");
  const t = team && typeof teamsIn === "function" ? (teamsIn(sport) || {})[team] : null;
  const wash = t && typeof twWash === "function" ? plrWashPair(t) : null;
  if (wash) {
    [wash.deep[0], wash.deep[1], wash.paper[0], wash.paper[1]].forEach((c, i) => document.body.style.setProperty(PLR_WASH_VARS[i], c));
    document.body.classList.add("plr-on");
    plrPin();
  } else plrWashOff();
  if (!_plrWatch && typeof MutationObserver !== "undefined") {
    _plrWatch = new MutationObserver(() => { if (!board.querySelector(":scope > .plr")) plrFrameOff(); });
    _plrWatch.observe(board, { childList: true });
  }
}
/* The club's two colours for its page: the whole-site wash's pair (app.js twWash), save that white,
   silver and grey are a kit's trim beside a club's real colours. Deepened until white type reads on
   them they turn a fog grey, so the Leafs' and Duke's blue washed into grey; they step aside for the
   club's next colour, else twWash's deeper shade of the first. A club whose colours are all trim and
   black (the Raiders, the Nets) keeps them: they are the club. */
function plrWashPair(t) {
  const cs = [t.primary, t.secondary, t.tertiary, t.alt].map(twHex6);
  const chroma = (c) => { const [, a, b] = okLab(c); return Math.hypot(a, b); };
  const trim = (c) => c && okLab(c)[0] > 0.6 && chroma(c) < TW_HUED;
  const pick = cs.some((c) => c && chroma(c) >= TW_HUED) ? cs.map((c) => (trim(c) ? "" : c)) : cs;
  return twWash({ primary: pick[0], secondary: pick[1], tertiary: pick[2], alt: pick[3] });
}
function plrWashOff() {
  document.body.classList.remove("plr-on");
  PLR_WASH_VARS.forEach((k) => document.body.style.removeProperty(k));
}
function plrFrameOff() {
  const view = document.getElementById("view-players");
  if (view) view.classList.remove("plr-view");
  if (document.body) plrWashOff();
}
//: The bar paints the wash's screen-sized picture pinned to the screen's corner, so it is told how far
//: across the screen it starts (the docked sidebar moves it right), as app.js twPin tells it for the
//: whole-site wash: on every draw, and whenever the bar changes size.
function plrPin() {
  const top = document.querySelector(".topbar");
  if (!top || !document.body.classList.contains("plr-on")) return;
  const r = top.getBoundingClientRect();
  if (r.width) top.style.setProperty("--pw-x", `${-Math.round(r.left)}px`);
  if (!_plrPinRO && typeof ResizeObserver !== "undefined") {
    _plrPinRO = new ResizeObserver(() => plrPin());
    _plrPinRO.observe(top);
  }
}

/* THE PLAYER'S PAGE, in place of the card renderPlayers drew (it becomes the
   Overview's market section, with no door out to the pick page). The Players page redraws every 30 seconds while it
   is open: the same player's page is then put back as it was (the open menu, the
   seasons picked, every panel drawn) with only the market cards swapped for the
   fresh ones, since a price can move between two redraws. A first visit draws
   from the visit's copy where there is one. */
let _plrLive = null;
function plrMarkets(page, kept) {
  const tonight = page.querySelector(".plr-tonight");
  if (!tonight) return;
  tonight.replaceChildren(kept);
  if (tonight.firstElementChild) tonight.insertAdjacentHTML("afterbegin", `<h3 class="plr-h">${plrTonightTitle(page)}</h3>`);
}
/* THE PICK A TAP OPENED THIS PAGE ON (app.js openPick; Ethan, 2026-11-17: a pick on the Edge and Most
   Likely boards "always send too the new player page"). It heads the Overview, drawn by the pick page's
   own code (js/detail.js pickOnPlayerHTML, loaded the first time a pick opens a page), with a way down to
   the same market's every number. Redrawn with the page only when it changed, so a fold opened inside
   it stays open; gone with the next door to a player that is not a pick. */
function plrTappedInto(page) {
  const slot = page.querySelector(".plr-tapped"), p = state.playerPick;
  if (!slot) return;
  page._pick = p;
  if (!p || p.slug !== slugify(page._plr.player)) { slot._html = ""; slot.replaceChildren(); return; }
  loadRoom("js/detail.js", "css/detail.css").then((ok) => {
    if (!ok || !slot.isConnected || page._pick !== p || typeof pickOnPlayerHTML !== "function") return;
    const card = pickOnPlayerHTML(p);
    const html = card ? `${card}<button type="button" class="btn ghost plr-tapped-go">This market’s every number</button>`
      : `<p class="plr-quiet">The pick you tapped is no longer on tonight’s board.</p>`;
    if (slot._html === html) return;
    slot._html = html;
    slot.innerHTML = html;
    if (typeof fillMeters === "function") fillMeters(slot);
  });
}
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest(".plr-tapped-go");
  const to = b && b.closest(".plr") && b.closest(".plr").querySelector(".plr-tonight");
  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (to) to.scrollIntoView({ block: "start", behavior: still ? "instant" : "smooth" });
});

//: renderPlayers hands over this player's card alone (the search lists names; only the address draws a card).
function renderPlayerPage(host, player, sport) {
  if (!host || !player || !PLR_SPORTS.includes(sport)) return;
  const r0 = ((typeof _profRows !== "undefined" && _profRows.get(player)) || [])[0] || {};
  const team = r0.team || "", key = `${sport}|${player}`;
  const kept = document.createDocumentFragment();
  while (host.firstChild) kept.appendChild(host.firstChild);
  const same = _plrLive && _plrLive.key === key ? _plrLive.page : null;
  if (same) {
    plrMarkets(same, kept);
    host.replaceChildren(same);
    plrFrameOn(sport, same._plr.team);
    // A pick tapped since this page was last drawn opens it on the Overview, where the pick heads it.
    if (state.playerPick && same._pick !== state.playerPick) plrShow(same, "overview");
    plrTappedInto(same);
    return;
  }
  const open = state.playerPick ? "overview" : PLR_TAB[key] || "overview";
  const cached = PLR_CACHE.get(`${sport}|${player}|${team}|`);
  host.innerHTML = `<section class="plr">${plrHeroHTML(player, sport, team, r0.position || "", r0.headshot,
    cached && cached.bio)}${plrTabsHTML(open, sport)}${plrPanelsHTML(open, sport)}</section>`;
  const page = host.querySelector(".plr");
  page._plr = { key, player, sport, team, face: r0.headshot || "" };
  _plrLive = { key, page };
  plrTappedInto(page);
  plrMarkets(page, kept);
  plrFrameOn(sport, team);
  if (cached) plrFill(page, cached);
  else plrFetch(sport, player, team).then((d) => { if (page.isConnected) plrFill(page, d); });
}

async function plrSplitsFor(page, season) {
  const slot = page.querySelector("[data-plr-panel=\"splits\"]");
  if (!slot) return;
  const { sport, player, team } = page._plr;
  slot.innerHTML = `<p class="plr-wait">Loading ${escapeHtml(String(season))}…</p>`;
  const d = await plrFetch(sport, player, team, season);
  if (slot.isConnected) slot.innerHTML = d && d.player ? plrSplitsHTML(d) : `<p class="plr-quiet">That season could not load.</p>`;
}

function plrToTabs(page) {
  const bar = page.querySelector(".plr-tabs");
  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (bar) bar.scrollIntoView({ block: "start", behavior: still ? "instant" : "smooth" });
}
document.addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest(".plr-tab, .plr-go");
  if (!t) return;
  const page = t.closest(".plr");
  if (!page || !page._plr) return;
  plrShow(page, t.dataset.plrTab || t.dataset.plrGo);
  if (t.dataset.plrGo) plrToTabs(page);
});
//: On the player's page, the market card's "Game log" opens the Game Log menu rather than a sheet over it.
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest(".plr .gl-open");
  const page = b && b.closest(".plr");
  if (!page || !page._plr) return;
  e.stopPropagation();
  plrShow(page, "log");
  plrToTabs(page);
}, true);
document.addEventListener("change", (e) => {
  const sel = e.target.closest && e.target.closest(".plr [data-plr-season], .plr [data-gl-season]");
  if (!sel) return;
  const page = sel.closest(".plr");
  if (!page || !page._plr) return;
  const log = sel.matches("[data-gl-season]");
  PLR_PICK[page._plr.key] = { ...(PLR_PICK[page._plr.key] || {}), [log ? "log" : "splits"]: sel.value };
  if (log) plrLogInto(page, sel.value);
  else plrSplitsFor(page, sel.value);
});
