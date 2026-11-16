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

const PP_SPORTS = ["nfl", "cfb", "nba", "wnba", "cbb", "nhl", "mlb"];
const PP_TABS = [["overview", "Overview"], ["news", "News"], ["stats", "Stats"], ["bio", "Bio"],
  ["splits", "Splits"], ["log", "Game Log"]];
const PP_CACHE = new Map();
const PP_TAB = {};
//: Rates print to a tenth (goals against to a hundredth), counts whole.
const PP_RATES = ["CMP%", "AVG", "RTG", "FG%", "SV%", "K/9"];
//: Leagues whose season is said across two years ("2026–27"); the file labels a season by the year it started.
const PP_TWO_YEARS = ["nba", "nhl", "cbb"];
//: The seasons picked in the Splits and Game Log menus, kept through the page's redraw.
const PP_PICK = {};
let _ppNews = null;

async function ppFetch(sport, player, team, season) {
  const key = `${sport}|${player}|${team || ""}|${season || ""}`;
  if (PP_CACHE.has(key)) return PP_CACHE.get(key);
  let body = null;
  try {
    const q = new URLSearchParams({ sport, player });
    if (team) q.set("team", team);
    if (season) q.set("season", String(season));
    const r = await fetch(`/api/players/page?${q}`);
    body = r.ok ? await r.json() : null;
  } catch (e) { body = null; }
  if (body && body.player) PP_CACHE.set(key, body);
  return body;
}
async function ppHeadlines() {
  if (_ppNews) return _ppNews;
  try {
    const r = await boardFetch("data/news.json", { cache: "no-cache" });
    _ppNews = r.ok ? await r.json() : {};
  } catch (e) { _ppNews = {}; }
  return _ppNews;
}

//: A number as its column says it; an average (`avg`) always to a tenth, so 27.0 reads as one.
function ppNum(v, label, avg) {
  if (v == null || v === "") return "—";
  if (typeof v === "string") return v;
  let out;
  if (label === "GAA") out = v.toFixed(2);
  else if (PP_RATES.includes(label)) out = v.toFixed(1);
  else if (label === "TOI") {
    const m = Math.floor(v), s = Math.round((v - m) * 60);
    out = `${m}:${String(s === 60 ? 0 : s).padStart(2, "0")}`;
  } else if (avg) out = v.toFixed(1);
  else if (Number.isInteger(v)) out = v.toLocaleString();
  else out = v.toFixed(1);
  return trueMinus(out);
}
function ppSeasonLabel(sport, s) {
  return PP_TWO_YEARS.includes(sport) ? `${s}–${String((Number(s) + 1) % 100).padStart(2, "0")}` : String(s);
}
function ppOrd(n) {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" })[n % 10] || "th";
  return `${n}${s}`;
}
function ppDay(iso, opts) {
  const d = iso ? new Date(`${iso.slice(0, 10)}T12:00:00`) : null;
  return d && !isNaN(d) ? d.toLocaleDateString(undefined, opts || { month: "short", day: "numeric" }) : "";
}
function ppAge(bio) {
  const d = bio.born ? new Date(`${bio.born}T12:00:00`) : null;
  if (d && !isNaN(d)) {
    const now = new Date();
    let a = now.getFullYear() - d.getFullYear();
    if (now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) a -= 1;
    return a;
  }
  return bio.age || "";
}
function ppClub(sport, team) {
  const t = (typeof teamsIn === "function" ? teamsIn(sport) : {})[team] || {};
  return { name: t.name || teamNameIn(sport, team) || team || "", nick: t.nick || "", color: t.primary || "" };
}
function ppNorm(s) {
  return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
//: A name as a whole word in a headline.
function ppWord(word) {
  return word ? new RegExp(`\\b${word.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&")}\\b`) : null;
}

/* ---------------- the frame ---------------- */
function ppHeroHTML(player, sport, team, pos, face, bio) {
  const club = ppClub(sport, team);
  const parts = String(player).trim().split(/\s+/);
  const first = parts.length > 1 ? parts[0] : "", rest = parts.length > 1 ? parts.slice(1).join(" ") : parts[0];
  const num = bio && bio.number !== "" && bio.number != null ? `#${bio.number}` : "";
  const line = [club.name, num, (bio && bio.position) || pos].filter(Boolean).map(escapeHtml).join(" · ");
  const age = bio ? ppAge(bio) : "";
  const body = bio ? [bio.height, bio.weight, age !== "" ? `Age ${age}` : ""].filter(Boolean).map(escapeHtml).join(" · ") : "";
  return `<header class="pp-hero"${club.color ? ` style="--pp-c:${escapeAttr(club.color)}"` : ""}>
      ${team ? `<span class="pp-mark" aria-hidden="true">${teamMarkIn(sport, team, 168)}</span>` : ""}
      <div class="pp-face">${playerAvatar(player, team, { size: 92, headshot: face, map: teamsIn(sport) })}</div>
      <div class="pp-who">
        <h2 class="pp-name">${first ? `<span>${escapeHtml(first)}</span> ` : ""}<b>${escapeHtml(rest)}</b></h2>
        <p class="pp-club">${team ? teamMarkIn(sport, team, 18) : ""}<span>${line || escapeHtml(lgCode(sport))}</span></p>
        ${body ? `<p class="pp-body">${body}</p>` : ""}
        <div class="pp-flag">${typeof injTag === "function" ? injTag(sport, player) : ""}</div>
      </div>
    </header>`;
}
function ppTabsHTML(open) {
  return `<div class="pp-tabs" role="tablist" aria-label="Player page">${PP_TABS.map(([k, label]) =>
    `<button type="button" role="tab" class="pp-tab${k === open ? " on" : ""}" data-pp-tab="${k}" aria-selected="${
      k === open}">${label}</button>`).join("")}</div>`;
}
function ppPanelsHTML(open) {
  return PP_TABS.map(([k]) => `<div class="pp-panel" data-pp-panel="${k}" role="tabpanel"${k === open ? "" : " hidden"}>${
    k === "overview" ? `<div class="pp-season"></div><div class="pp-prev"></div><div class="pp-splitlet"></div>
      <div class="pp-recent"></div><div class="pp-latest"></div><div class="pp-tonight"></div>`
      : `<p class="pp-wait">Loading…</p>`}</div>`).join("");
}

/* ---------------- Overview ---------------- */
function ppSeasonHTML(d) {
  const nums = (d.headline || []).filter((h) => h.value != null);
  if (!nums.length) return "";
  const ranked = nums.some((h) => h.rank);
  return `<section class="pp-card pp-strip"><h3>${escapeHtml(ppSeasonLabel(d.sport, d.season))} season${ranked
      ? ` <span>Where each ranks in the ${escapeHtml(lgCode(d.sport))} this season</span>` : ""}</h3>
    <div class="pp-nums">${nums.map((h) => `<div class="pp-num" title="${escapeAttr(h.title)}">
      <span class="pp-k">${escapeHtml(h.label)}</span><b>${escapeHtml(ppNum(h.value, h.label, h.per_game))}</b>${
      h.rank ? `<span class="pp-rank">${ppOrd(h.rank)}${h.low ? " fewest" : ""}</span>` : ""}</div>`).join("")}</div></section>`;
}
function ppPrevHTML(d) {
  const g = d.last;
  if (!g) return "";
  const when = [g.week ? `Week ${g.week}` : "", ppDay(g.date)].filter(Boolean).join(" · ");
  const [mine, theirs] = String(g.score || "").split("-");
  const side = (team, rec, pts, won) => `<div class="pp-side">${teamMarkIn(d.sport, team, 34)}<div><b>${
    escapeHtml(teamNameIn(d.sport, team) || team)}</b>${rec ? `<small>${escapeHtml(rec)}</small>` : ""}</div>${
    pts != null && pts !== "" ? `<span class="pp-pts${won ? " pp-won" : ""}">${escapeHtml(pts)}</span>` : ""}</div>`;
  const res = g.result ? `<span class="${g.result === "W" ? "gl-w" : g.result === "L" ? "gl-l" : "gl-t"}">${
    escapeHtml(g.result === "W" ? "Won" : g.result === "L" ? "Lost" : "Tied")}</span> · Final` : "";
  const tiles = g.dnp ? `<p class="pp-dnp">Did not play.</p>` : (g.tiles || []).length ? `<div class="pp-tiles">${g.tiles.map((t) =>
    `<div class="pp-tile" title="${escapeAttr(t.title)}"><span class="pp-k">${escapeHtml(t.label)}</span><b>${
      escapeHtml(ppNum(t.value, t.label))}</b></div>`).join("")}</div>` : "";
  return `<section class="pp-card"><h3>Previous game <span>${escapeHtml(when)}${g.home ? " · home" : " · away"}</span></h3>
    <div class="pp-score">${side(g.team, g.record, mine, g.result === "W")}<div class="pp-mid">${res}</div>${
      side(g.opponent, g.opp_record, theirs, g.result === "L")}</div>${tiles}</section>`;
}
//: The columns a split table shows: his main group's, or every group's (the Splits menu).
function ppCols(groups, only) {
  return (groups || []).filter((g) => !only || g.key === only)
    .flatMap((g) => g.cols.map((c) => ({ ...c, id: `${g.key}.${c.key}`, group: g.title })));
}
function ppSplitTable(rows, cols, opts) {
  const o = opts || {};
  const head = `<thead><tr><th class="gl-fix">${escapeHtml(o.first || "Split")}</th><th class="num">GP</th>${cols.map((c) =>
    `<th class="num" title="${escapeAttr(c.title)}">${escapeHtml(c.label)}</th>`).join("")}</tr></thead>`;
  const body = rows.map((r) => r.break ? `<tr class="pp-break"><td class="gl-fix" colspan="${cols.length + 2}">${
      escapeHtml(r.break)}</td></tr>` : `<tr${r.sum ? ` class="gl-sum"` : ""}><td class="gl-fix">${escapeHtml(r.label)}</td><td class="num">${
      r.gp == null ? "" : escapeHtml(String(r.gp))}</td>${cols.map((c) =>
      `<td class="num">${escapeHtml(ppNum((r.values || {})[c.id], c.label, !!o.avg && r.avg !== false))}</td>`).join("")}</tr>`).join("");
  return `<div class="gl-scroll"><table class="agate gl-table pp-table">${head}<tbody>${body}</tbody></table></div>`;
}
function ppSplitletHTML(d) {
  const sp = d.splits || {}, g = d.last;
  if (!g || !(sp.rows || []).length) return "";
  const by = new Map(sp.rows.map((r) => [r.key, r]));
  const group = (sp.groups || []).some((x) => x.key === d.role) ? d.role : ((sp.groups || [])[0] || {}).key;
  const cols = ppCols(sp.groups, group);
  if (!cols.length) return "";
  const rows = [];
  if (!g.dnp) rows.push({ label: "This game", gp: 1, values: g.values, avg: false });
  const month = g.date ? by.get(`m:${g.date.slice(0, 7)}`) : null;
  if (month) rows.push(month);
  const vs = by.get(`vs:${g.opponent}`);
  if (vs) rows.push(vs);
  const where = by.get(g.home ? "home" : "away");
  if (where) rows.push(where);
  if (by.get("season")) rows.push(by.get("season"));
  return `<section class="pp-card"><h3>Splits <span>A game’s average</span></h3>${ppSplitTable(rows, cols, { avg: true })}
    <button class="btn pp-go" type="button" data-pp-go="splits">Every split</button></section>`;
}
//: A priced card wears its grade; a card from his history has none.
function ppTonightTitle(page) {
  return page.querySelector(".pp-tonight .grade") ? "Tonight’s markets" : "By market";
}
async function ppRecentInto(slot, d) {
  if (!slot || typeof glFetch !== "function") return;
  const log = await glFetch(d.sport, d.player, d.season);
  if (!slot.isConnected || !log || !(log.games || []).length) return;
  slot.innerHTML = `<section class="pp-card"><h3>Recent games</h3>${glTableHTML({ ...log, games: log.games.slice(0, 5), played: 0 })}
    <button class="btn pp-go" type="button" data-pp-go="log">Full game log</button></section>`;
}

/* ---------------- News ---------------- */
function ppNewsRows(d, news) {
  const league = ((news || {}).sports || {})[d.sport] || [];
  const club = ppClub(d.sport, d.team);
  const full = ppNorm(d.player), last = ppNorm(typeof surname === "function" ? surname(d.player) : d.player);
  const lastRe = ppWord(last), nickRe = ppWord(club.nick);
  const named = [], team = [];
  league.forEach((h) => {
    const t = ppNorm(h.title);
    const clubNamed = (nickRe && nickRe.test(h.title || "")) || (club.name && t.includes(ppNorm(club.name)));
    if (t.includes(full) || (lastRe && lastRe.test(t) && clubNamed)) named.push(h);
    else if (clubNamed) team.push(h);
  });
  return { named, team, league, club };
}
function ppHeadlineHTML(h) {
  const when = h.epoch ? new Date(h.epoch * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
  return `<li><a href="${escapeAttr(h.link || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(h.title || "")}</a>
    <span>${escapeHtml([h.source, when].filter(Boolean).join(" · "))}</span></li>`;
}
function ppNoteHTML(d) {
  const n = d.notes || {}, hurt = n.injury;
  const parts = [];
  if (hurt) {
    const head = [hurt.status, hurt.what].filter(Boolean).join(" · ");
    parts.push(`<div class="pp-note"><b>${escapeHtml(head || "Injury")}</b>${hurt.note ? `<p>${escapeHtml(hurt.note)}</p>` : ""}${
      hurt.back ? `<span>Expected back around ${escapeHtml(ppDay(hurt.back, { month: "long", day: "numeric" }))}</span>` : ""}${
      hurt.source ? `<span>Per ${escapeHtml(hurt.source === "sleeper" ? "Sleeper" : hurt.source)}</span>` : ""}</div>`);
  }
  (n.moves || []).forEach((m) => parts.push(`<div class="pp-note"><b>Joined ${escapeHtml(teamNameIn(d.sport, m.to) || m.to)}</b><p>From ${
    escapeHtml(teamNameIn(d.sport, m.from) || m.from)}${m.date ? `, ${escapeHtml(ppDay(m.date, { month: "long", day: "numeric" }))}` : ""}.</p></div>`));
  return parts.join("");
}
function ppNewsHTML(d, news) {
  const { named, team, league, club } = ppNewsRows(d, news);
  const note = ppNoteHTML(d);
  const list = (rows) => `<ul class="pp-heads">${rows.map(ppHeadlineHTML).join("")}</ul>`;
  let html = note ? `<section class="pp-card"><h3>The latest</h3>${note}</section>` : "";
  if (named.length) html += `<section class="pp-card"><h3>In the headlines</h3>${list(named)}</section>`;
  if (team.length) html += `<section class="pp-card"><h3>${escapeHtml(club.nick || club.name || d.team)} headlines</h3>${list(team.slice(0, 8))}</section>`;
  if (!named.length && !team.length && league.length) {
    html += `<section class="pp-card"><h3>Around the ${escapeHtml(lgCode(d.sport))}</h3><p class="pp-quiet">No headline names this player or the club right now.</p>${
      list(league.slice(0, 6))}</section>`;
  }
  return (html || `<p class="pp-quiet">No news right now.</p>`)
    + `<p class="pp-fine">Headlines and links only, from the publishers’ own feeds. The reporting lives at the source.</p>`;
}
function ppLatestHTML(d, news) {
  const { named, team } = ppNewsRows(d, news);
  const note = ppNoteHTML(d);
  const rows = [...named, ...team].slice(0, 3);
  if (!note && !rows.length) return "";
  return `<section class="pp-card"><h3>Latest</h3>${note}${rows.length ? `<ul class="pp-heads">${rows.map(ppHeadlineHTML).join("")}</ul>` : ""}
    <button class="btn pp-go" type="button" data-pp-go="news">All news</button></section>`;
}

/* ---------------- Stats, Bio, Splits ---------------- */
function ppStatsHTML(d) {
  const c = d.career || {};
  if (!(c.rows || []).length) return `<p class="pp-quiet">No seasons on file yet.</p>`;
  return (c.groups || []).map((g) => {
    const cols = ppCols([g]);
    const rows = c.rows.map((r) => ({ label: `${ppSeasonLabel(d.sport, r.season)}${r.team ? ` · ${r.team}` : ""}`, gp: r.gp,
      values: r.values }));
    rows.push({ label: "Career", gp: c.total.gp, values: c.total.values, sum: true });
    return `<section class="pp-card"><h3>${escapeHtml(g.title || "Season by season")} <span>${
      c.per_game ? "A game’s average" : "Totals"}</span></h3>${ppSplitTable(rows, cols, { first: "Season", avg: c.per_game })}</section>`;
  }).join("");
}
function ppBioHTML(d) {
  const b = d.bio || {}, club = ppClub(d.sport, b.team || d.team);
  const born = b.born ? `${ppDay(b.born, { year: "numeric", month: "long", day: "numeric" })}${ppAge(b) !== "" ? ` (age ${ppAge(b)})` : ""}` : "";
  const exp = b.rookie ? "Rookie" : b.years_exp !== "" && b.years_exp != null ? `${ppOrd(Number(b.years_exp) + 1)} season` : "";
  const facts = [
    ["Team", b.team || d.team ? `${teamMarkIn(d.sport, b.team || d.team, 18)} ${escapeHtml(club.name)}` : ""],
    ["Position", escapeHtml(b.position || d.position || "")],
    ["Number", b.number !== "" && b.number != null ? `#${escapeHtml(b.number)}` : ""],
    ["Height", escapeHtml(b.height || "")], ["Weight", escapeHtml(b.weight || "")],
    ["Born", escapeHtml(born)], ["Birthplace", escapeHtml(b.birthplace || "")],
    ["College", escapeHtml(b.college || "")], ["Experience", escapeHtml(exp)],
    ["Shoots", escapeHtml(b.shoots === "L" ? "Left" : b.shoots === "R" ? "Right" : b.shoots || "")],
    ["Status", escapeHtml(b.status || "")],
    ["On file", b.first_season ? escapeHtml(`${b.first_season === b.last_season ? ppSeasonLabel(d.sport, b.first_season)
      : `${ppSeasonLabel(d.sport, b.first_season)} to ${ppSeasonLabel(d.sport, b.last_season)}`} · ${
      plural(b.games || 0, "game")}`) : ""],
  ].filter(([, v]) => v);
  return `<section class="pp-card"><h3>Bio</h3><dl class="pp-bio">${facts.map(([k, v]) =>
    `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
    <p class="pp-fine">From the club’s published roster. A fact the roster does not list is left out.</p></section>`;
}
function ppSeasonPick(d, attr) {
  return (d.seasons || []).length > 1 ? `<label class="gl-season">Season <select ${attr}>${d.seasons.map((s) =>
    `<option value="${s}"${s === d.season ? " selected" : ""}>${escapeHtml(ppSeasonLabel(d.sport, s))}</option>`).join("")}</select></label>` : "";
}
function ppSplitsHTML(d) {
  const sp = d.splits || {};
  if (!(sp.rows || []).length) return `<p class="pp-quiet">No games on file for this season.</p>`;
  const rows = [];
  let lastKind = "";
  sp.rows.forEach((r) => {
    const kind = r.key.startsWith("m:") ? "By month" : r.key.startsWith("vs:") ? "By opponent" : "";
    if (kind && kind !== lastKind) rows.push({ break: kind });
    lastKind = kind || lastKind;
    rows.push(r);
  });
  return `<div class="pp-pick">${ppSeasonPick(d, "data-pp-season")}</div>` + (sp.groups || []).map((g) =>
    `<section class="pp-card"><h3>${escapeHtml(g.title || "Splits")} <span>A game’s average</span></h3>${
      ppSplitTable(rows, ppCols([g]), { avg: true })}</section>`).join("");
}

/* ---------------- drawing ---------------- */
function ppFill(page, d) {
  const host = page.querySelector(".pp-hero");
  if (host && d && d.bio) host.outerHTML = ppHeroHTML(d.player, d.sport, d.team, d.position,
    d.bio.headshot || page._pp.face, d.bio);
  const at = (sel) => page.querySelector(sel);
  if (!d || !d.player) {
    const msg = `<p class="pp-quiet">This page could not load. Open it again in a minute.</p>`;
    page.querySelectorAll(".pp-panel[data-pp-panel]:not([data-pp-panel=\"overview\"])").forEach((p) => { p.innerHTML = msg; });
    return;
  }
  const set = (sel, html) => { const el = at(sel); if (el) el.innerHTML = html; };
  set(".pp-season", ppSeasonHTML(d));
  set(".pp-prev", ppPrevHTML(d));
  set(".pp-splitlet", ppSplitletHTML(d));
  set("[data-pp-panel=\"stats\"]", ppStatsHTML(d));
  set("[data-pp-panel=\"bio\"]", ppBioHTML(d));
  set("[data-pp-panel=\"splits\"]", ppSplitsHTML(d));
  const picked = (PP_PICK[page._pp.key] || {}).splits;
  if (picked && String(picked) !== String(d.season)) ppSplitsFor(page, picked);
  ppHeadlines().then((news) => {
    if (!page.isConnected) return;
    set("[data-pp-panel=\"news\"]", ppNewsHTML(d, news));
    set(".pp-latest", ppLatestHTML(d, news));
  });
  loadRoom("js/gamelog.js", "css/gamelog.css").then((ok) => {
    if (!ok || !page.isConnected) return;
    ppRecentInto(at(".pp-recent"), d);
    if (PP_TAB[page._pp.key] === "log") ppLogInto(page);
  });
}
async function ppLogInto(page, season) {
  const slot = page.querySelector("[data-pp-panel=\"log\"]");
  if (!slot || typeof glFetch !== "function") return;
  const { sport, player, key } = page._pp;
  if (!season && slot.dataset.drawn) return;
  const d = await glFetch(sport, player, season || (PP_PICK[key] || {}).log);
  if (!slot.isConnected) return;
  slot.innerHTML = glBodyHTML(d, sport);
  slot.dataset.drawn = "1";
}
function ppShow(page, tab) {
  PP_TAB[page._pp.key] = tab;
  page.querySelectorAll(".pp-tab").forEach((b) => {
    const on = b.dataset.ppTab === tab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", String(on));
  });
  page.querySelectorAll(".pp-panel").forEach((p) => { p.hidden = p.dataset.ppPanel !== tab; });
  if (tab === "log") loadRoom("js/gamelog.js", "css/gamelog.css").then((ok) => ok && ppLogInto(page));
}

/* THE PLAYER'S PAGE, in place of the cards renderPlayers drew (they become the
   Overview's market section). The Players page redraws every 30 seconds while it
   is open: the same player's page is then put back as it was (the open menu, the
   seasons picked, every panel drawn) with only the market cards swapped for the
   fresh ones, since a price can move between two redraws. A first visit draws
   from the visit's copy where there is one. */
let _ppLive = null;
function ppMarkets(page, kept) {
  const tonight = page.querySelector(".pp-tonight");
  if (!tonight) return;
  tonight.replaceChildren(kept);
  // A searched-up player's cards come with their own heading ("Found in …",
  // "Closest matches"); a priced card has none, and gets one.
  const lead = tonight.firstElementChild;
  if (lead && !lead.classList.contains("section-title")) {
    tonight.insertAdjacentHTML("afterbegin", `<h3 class="pp-h">${ppTonightTitle(page)}</h3>`);
  }
}
//: Whose card an element is, by the doors every card carries (its charts, its game log, its market chips).
function ppCardOf(el) {
  const door = el.querySelector && el.querySelector("[data-gl], [data-carry], .prof-tab[data-player]");
  return door ? door.dataset.gl || door.dataset.carry || door.dataset.player || "" : "";
}
function renderPlayerPage(host, player, sport) {
  if (!host || !player || !PP_SPORTS.includes(sport)) return;
  const r0 = ((typeof _profRows !== "undefined" && _profRows.get(player)) || [])[0] || {};
  const team = r0.team || "", key = `${sport}|${player}`;
  const kept = document.createDocumentFragment();
  while (host.firstChild) kept.appendChild(host.firstChild);
  // His address named him: a near name the search drew beside him is another player's card, not his page's.
  [...kept.children].forEach((el) => { const who = ppCardOf(el); if (who && who !== player) el.remove(); });
  const same = _ppLive && _ppLive.key === key ? _ppLive.page : null;
  if (same) {
    ppMarkets(same, kept);
    host.replaceChildren(same);
    return;
  }
  const open = PP_TAB[key] || "overview";
  const cached = PP_CACHE.get(`${sport}|${player}|${team}|`);
  host.innerHTML = `<section class="pp">${ppHeroHTML(player, sport, team, r0.position || "", r0.headshot,
    cached && cached.bio)}${ppTabsHTML(open)}${ppPanelsHTML(open)}</section>`;
  const page = host.querySelector(".pp");
  page._pp = { key, player, sport, team, face: r0.headshot || "" };
  _ppLive = { key, page };
  ppMarkets(page, kept);
  if (cached) ppFill(page, cached);
  else ppFetch(sport, player, team).then((d) => { if (page.isConnected) ppFill(page, d); });
}

async function ppSplitsFor(page, season) {
  const slot = page.querySelector("[data-pp-panel=\"splits\"]");
  if (!slot) return;
  const { sport, player, team } = page._pp;
  slot.innerHTML = `<p class="pp-wait">Loading ${escapeHtml(String(season))}…</p>`;
  const d = await ppFetch(sport, player, team, season);
  if (slot.isConnected) slot.innerHTML = d && d.player ? ppSplitsHTML(d) : `<p class="pp-quiet">That season could not load.</p>`;
}

function ppToTabs(page) {
  const bar = page.querySelector(".pp-tabs");
  const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (bar) bar.scrollIntoView({ block: "start", behavior: still ? "instant" : "smooth" });
}
document.addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest(".pp-tab, .pp-go");
  if (!t) return;
  const page = t.closest(".pp");
  if (!page || !page._pp) return;
  ppShow(page, t.dataset.ppTab || t.dataset.ppGo);
  if (t.dataset.ppGo) ppToTabs(page);
});
//: On the player's page, the market card's "Game log" opens the Game Log menu rather than a sheet over it.
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest(".pp .gl-open");
  const page = b && b.closest(".pp");
  if (!page || !page._pp) return;
  e.stopPropagation();
  ppShow(page, "log");
  ppToTabs(page);
}, true);
document.addEventListener("change", (e) => {
  const sel = e.target.closest && e.target.closest(".pp [data-pp-season], .pp [data-gl-season]");
  if (!sel) return;
  const page = sel.closest(".pp");
  if (!page || !page._pp) return;
  const log = sel.matches("[data-gl-season]");
  PP_PICK[page._pp.key] = { ...(PP_PICK[page._pp.key] || {}), [log ? "log" : "splits"]: sel.value };
  if (log) ppLogInto(page, sel.value);
  else ppSplitsFor(page, sel.value);
});
