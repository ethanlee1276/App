/* PLAYER PAGES (js/playerpage.js, loaded the first time one opens).

   Ethan, 2026-11-16, with ESPN's page for Josh Allen: "The page should look
   just like this and have each menu for all players in all sports." When the
   Players page shows one player (the address #player/<name>, or a search that
   finds just one), app.js renderPlayers hands the page here and it becomes
   that player's page: a header in the club's colours with the face, the name,
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
     Splits    the season a game's average at a time, by venue, result,
               month and opponent;
     Game Log  the season a line a game (js/gamelog.js, drawn in place).

   Everything but the headlines comes from /api/players/page (engine/
   playerpage), kept for the visit; the open menu is remembered per player, so
   the page's own redraw every minute never moves the reader. Its words never
   assume who the player is: the WNBA's players have pages too. */

const PLR_SPORTS = ["nfl", "cfb", "nba", "wnba", "cbb", "nhl", "mlb"];
const PLR_TABS = [["overview", "Overview"], ["news", "News"], ["stats", "Stats"], ["bio", "Bio"],
  ["splits", "Splits"], ["log", "Game Log"]];
const PLR_CACHE = new Map();
const PLR_TAB = {};
//: Rates print to a tenth (goals against to a hundredth), counts whole.
const PLR_RATES = ["CMP%", "AVG", "RTG", "FG%", "SV%", "K/9"];
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
  } else if (avg) out = v.toFixed(1);
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
  const line = [club.name, num, (bio && bio.position) || pos].filter(Boolean).map(escapeHtml).join(" · ");
  const age = bio ? plrAge(bio) : "";
  const body = bio ? [bio.height, bio.weight, age !== "" ? `Age ${age}` : ""].filter(Boolean).map(escapeHtml).join(" · ") : "";
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
function plrTabsHTML(open) {
  return `<div class="plr-tabs" role="tablist" aria-label="Player page">${PLR_TABS.map(([k, label]) =>
    `<button type="button" role="tab" class="plr-tab${k === open ? " on" : ""}" data-plr-tab="${k}" aria-selected="${
      k === open}">${label}</button>`).join("")}</div>`;
}
function plrPanelsHTML(open) {
  return PLR_TABS.map(([k]) => `<div class="plr-panel" data-plr-panel="${k}" role="tabpanel"${k === open ? "" : " hidden"}>${
    k === "overview" ? `<div class="plr-season"></div><div class="plr-prev"></div><div class="plr-splitlet"></div>
      <div class="plr-recent"></div><div class="plr-latest"></div><div class="plr-tonight"></div>`
      : `<p class="plr-wait">Loading…</p>`}</div>`).join("");
}

/* ---------------- Overview ---------------- */
function plrSeasonHTML(d) {
  const nums = (d.headline || []).filter((h) => h.value != null);
  if (!nums.length) return "";
  const ranked = nums.some((h) => h.rank);
  return `<section class="plr-card plr-strip"><h3>${escapeHtml(plrSeasonLabel(d.sport, d.season))} season${ranked
      ? ` <span>Where each ranks in the ${escapeHtml(lgCode(d.sport))} this season</span>` : ""}</h3>
    <div class="plr-nums">${nums.map((h) => `<div class="plr-num" title="${escapeAttr(h.title)}">
      <span class="plr-k">${escapeHtml(h.label)}</span><b>${escapeHtml(plrNum(h.value, h.label, h.per_game))}</b>${
      h.rank ? `<span class="plr-rank">${plrOrd(h.rank)}${h.low ? " fewest" : ""}</span>` : ""}</div>`).join("")}</div></section>`;
}
function plrPrevHTML(d) {
  const g = d.last;
  if (!g) return "";
  const when = [g.week ? `Week ${g.week}` : "", plrDay(g.date)].filter(Boolean).join(" · ");
  const [mine, theirs] = String(g.score || "").split("-");
  const side = (team, rec, pts, won) => `<div class="plr-side">${teamMarkIn(d.sport, team, 34)}<div><b>${
    escapeHtml(teamNameIn(d.sport, team) || team)}</b>${rec ? `<small>${escapeHtml(rec)}</small>` : ""}</div>${
    pts != null && pts !== "" ? `<span class="plr-pts${won ? " plr-won" : ""}">${escapeHtml(pts)}</span>` : ""}</div>`;
  const res = g.result ? `<span class="${g.result === "W" ? "gl-w" : g.result === "L" ? "gl-l" : "gl-t"}">${
    escapeHtml(g.result === "W" ? "Won" : g.result === "L" ? "Lost" : "Tied")}</span> · Final` : "";
  const tiles = g.dnp ? `<p class="plr-dnp">Did not play.</p>` : g.pending ? `<p class="plr-dnp">The box score isn’t in yet.</p>`
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
  if (!g.dnp && !g.pending) rows.push({ label: "This game", gp: 1, values: g.values, avg: false });
  const month = g.date ? by.get(`m:${g.date.slice(0, 7)}`) : null;
  if (month) rows.push(month);
  const vs = by.get(`vs:${g.opponent}`);
  if (vs) rows.push(vs);
  const where = by.get(g.home ? "home" : "away");
  if (where) rows.push(where);
  if (by.get("season")) rows.push(by.get("season"));
  return `<section class="plr-card"><h3>Splits <span>A game’s average</span></h3>${plrSplitTable(rows, cols, { avg: true })}
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
  if (!(c.rows || []).length) return `<p class="plr-quiet">No seasons on file yet.</p>`;
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
    `<section class="plr-card"><h3>${escapeHtml(g.title || "Splits")} <span>A game’s average</span></h3>${
      plrSplitTable(rows, plrCols([g]), { avg: true })}</section>`).join("");
}

/* ---------------- drawing ---------------- */
function plrFill(page, d) {
  const host = page.querySelector(".plr-hero");
  if (host && d && d.bio) host.outerHTML = plrHeroHTML(d.player, d.sport, d.team, d.position,
    d.bio.headshot || page._plr.face, d.bio);
  const at = (sel) => page.querySelector(sel);
  if (!d || !d.player) {
    const msg = `<p class="plr-quiet">This page could not load. Open it again in a minute.</p>`;
    page.querySelectorAll(".plr-panel[data-plr-panel]:not([data-plr-panel=\"overview\"])").forEach((p) => { p.innerHTML = msg; });
    return;
  }
  const set = (sel, html) => { const el = at(sel); if (el) el.innerHTML = html; };
  // On the roster, no game logged yet (a freshman, a backup): the page says so, and the rest is the roster's.
  set(".plr-season", (d.seasons || []).length ? plrSeasonHTML(d)
    : `<p class="plr-quiet">No games on file for this player yet. A game is added once its box score is in.</p>`);
  set(".plr-prev", plrPrevHTML(d));
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
  slot.innerHTML = glBodyHTML(d, sport);
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

/* THE PLAYER'S PAGE, in place of the cards renderPlayers drew (they become the
   Overview's market section). The Players page redraws every 30 seconds while it
   is open: the same player's page is then put back as it was (the open menu, the
   seasons picked, every panel drawn) with only the market cards swapped for the
   fresh ones, since a price can move between two redraws. A first visit draws
   from the visit's copy where there is one. */
let _plrLive = null;
function plrMarkets(page, kept) {
  const tonight = page.querySelector(".plr-tonight");
  if (!tonight) return;
  tonight.replaceChildren(kept);
  // A searched-up player's cards come with their own heading ("Found in …",
  // "Closest matches"); a priced card has none, and gets one.
  const lead = tonight.firstElementChild;
  if (lead && !lead.classList.contains("section-title")) {
    tonight.insertAdjacentHTML("afterbegin", `<h3 class="plr-h">${plrTonightTitle(page)}</h3>`);
  }
}
//: Whose card an element is, by the doors every card carries (its charts, its game log, its market chips).
function plrCardOf(el) {
  const door = el.querySelector && el.querySelector("[data-gl], [data-carry], .prof-tab[data-player]");
  return door ? door.dataset.gl || door.dataset.carry || door.dataset.player || "" : "";
}
function renderPlayerPage(host, player, sport) {
  if (!host || !player || !PLR_SPORTS.includes(sport)) return;
  const r0 = ((typeof _profRows !== "undefined" && _profRows.get(player)) || [])[0] || {};
  const team = r0.team || "", key = `${sport}|${player}`;
  const kept = document.createDocumentFragment();
  while (host.firstChild) kept.appendChild(host.firstChild);
  // The address named this player: a near name the search drew beside them is another player's card, not
  // this page's; and a roster row's "Profile" door to the player whose page this already is goes nowhere.
  // Asked for by name, the page is that player's alone: the near names the search listed go with it.
  [...kept.children].forEach((el) => { const who = plrCardOf(el); if (who && who !== player) el.remove(); });
  const asked = typeof searchNorm === "function" && searchNorm(player) === searchNorm(state.search || "");
  kept.querySelectorAll(".roster-hit").forEach((row) => {
    const b = row.querySelector("[data-lookup]");
    if (asked || (b && b.dataset.lookup === player)) row.remove();
  });
  if (asked) {
    [...kept.querySelectorAll(".section-title")].forEach((t) => {
      if (t.textContent.trim() === "Also matching") t.remove();
    });
  }
  const same = _plrLive && _plrLive.key === key ? _plrLive.page : null;
  if (same) {
    plrMarkets(same, kept);
    host.replaceChildren(same);
    return;
  }
  const open = PLR_TAB[key] || "overview";
  const cached = PLR_CACHE.get(`${sport}|${player}|${team}|`);
  host.innerHTML = `<section class="plr">${plrHeroHTML(player, sport, team, r0.position || "", r0.headshot,
    cached && cached.bio)}${plrTabsHTML(open)}${plrPanelsHTML(open)}</section>`;
  const page = host.querySelector(".plr");
  page._plr = { key, player, sport, team, face: r0.headshot || "" };
  _plrLive = { key, page };
  plrMarkets(page, kept);
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
