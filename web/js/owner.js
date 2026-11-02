/* THE OWNER'S DESK — the business at a glance, for the site's own account
   (engine/ownerdesk). Ethan, 2026-11-02: "deep dive and add more features
   and tools the Qellys book owners account should have".

   What an owner checks first, on one page a phone can open: who is on right
   now, accounts (new, coming back), money (paying, trials, cancelling, the
   month's recurring revenue), today's picks by book and the record, the
   box's health (crashes, stale boards, the last update, the settle pass,
   odds credits, disk), the room (posts, chat, reports), the switches, and
   the two tools that change something for everybody: a notice across the
   top of every page (engine/sitenotice), and the reports queue — the feed's
   and the game chat's in one list, each with Hide / Keep it up / Restore.
   What needs the owner (a stale board on a game day, grading stopped, the
   disk filling…) heads the page, and engine/owneralerts pushes the same
   list to this account's phones.

   Who's on now is the desk's first card, under what needs the owner
   (Ethan, the same day: "The Who's on and owners page should be one page").
   It had its own page (js/whoson.js, 2026-11-01) and keeps its own, faster
   clock here — WHO'S ON NOW, below.

   Loaded the first time it opens (app.js roomCall). The server answers
   /api/owner/desk and /api/owner/whoson for the site's own account alone
   and, to anybody else, as if they did not exist. Who's on now names the
   members the Privacy Policy's notice has reached who left "Show me in Who's
   on now" on; everything else on the page is a count or the business's own
   number. The rest of the desk is redrawn every OD_EVERY_MS while open. */

const OD_EVERY_MS = 60000;
let _odTimer = null;
let _odBusy = false;
let _odLast = null;
const OD_HOURS = [[1, "1 hour"], [3, "3 hours"], [6, "6 hours"], [12, "12 hours"], [24, "1 day"], [48, "2 days"],
                  [72, "3 days"], [168, "1 week"]];
const OD_LEAGUES = { nfl: "NFL", cfb: "College", nba: "NBA", nhl: "NHL", mlb: "MLB", wnba: "WNBA", ufc: "UFC" };

const odN = (v) => (v == null || v === "" ? "—" : Number(v).toLocaleString());
const odMoney = (v) => (v == null ? "—" : `$${Math.round(Number(v)).toLocaleString()}`);
const odPct = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : "—");
const odUnits = (u) => (u == null ? "—" : `${u > 0 ? "+" : u < 0 ? "−" : ""}${Math.abs(Number(u)).toFixed(2)}u`);
function odAgo(s) {
  if (s == null) return "—";
  s = Math.max(0, Math.round(s));
  return s < 90 ? `${s} s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}
const odTile = (v, k, tone) => `<div class="od-tile${tone ? ` ${tone}` : ""}"><b>${v}</b><span>${k}</span></div>`;
const odRow = (k, v, tone) => `<li><span>${k}</span><b${tone ? ` class="${tone}"` : ""}>${v}</b></li>`;
const odCard = (title, body, more) => `<section class="od-card"><h2 class="od-h">${title}${more || ""}</h2>${body}</section>`;
const odErr = (sec) => (sec && sec.error ? `<p class="od-note">Could not read this part: ${escapeHtml(sec.error)}</p>` : "");

/* Signups a day for two weeks, as bars: today's on the right. */
function odBars(days) {
  const top = Math.max(1, ...days.map((d) => d.n || 0));
  return `<div class="od-bars" role="img" aria-label="${escapeAttr(`New accounts a day, last ${days.length} days: ${days.map((d) => d.n).join(", ")}`)}">${
    days.map((d) => `<i style="height:${Math.max(4, Math.round((100 * (d.n || 0)) / top))}%" title="${escapeAttr(`${d.day}: ${d.n}`)}"></i>`).join("")}</div>`;
}

function odNowHTML(now) {
  if (!now || now.error) return odErr(now);
  return `<div class="od-tiles">${odTile(odN(now.members), "Members on")}${odTile(odN(now.visitors), "Visitors")}${
    odTile(odN(now.pages), "Pages open")}</div>`;
}

/* WHO'S ON NOW (engine/whoson): everybody on the site this minute and the
   page each has open, named where a member may be (engine/whoson.nameable:
   the Privacy Policy's notice has reached them and they left "Show me in
   Who's on now" on) and a number on their page where not. Its own clock,
   WO_EVERY_MS, against the desk's minute: only this card is redrawn, so a
   notice being written or the hidden reports left open are never touched.
   Until its first answer the card shows the desk's own counts; an old
   #whoson link opens this page (app.js ownerRoute). */
const WO_EVERY_MS = 10000;
let _woTimer = null;
let _woBusy = false;
let _woLast = null;                 // the last answer, kept across the desk's redraws
let _woRefused = false;

/* Our own pages by their view names. The menu's own words where it has a
   button for the page, these where it does not or says it differently. */
const WO_PAGES = {
  recommended: "Home", likely: "Most Likely", longshots: "Long Shots", live: "Live", pbp: "Game",
  game: "Game bet", prop: "Prop", record: "Record", mybets: "My Bets", account: "Account",
  props: "Over / Under", edge: "Edge", parlays: "Parlays", potd: "Pick of the Day", ask: "Ask",
  feed: "Social", messages: "Messages", alerts: "Alerts", fantasy: "Fantasy", owner: "Owner desk",
  whoson: "Owner desk",             // a tab opened before the two were one page
};
const WO_LEAGUES = { nfl: "NFL", cfb: "College football", nba: "NBA", wnba: "WNBA", nhl: "NHL", mlb: "MLB",
  ufc: "UFC", polymarket: "Polymarket", fantasy: "Fantasy" };

function woPage(view) {
  if (WO_PAGES[view]) return WO_PAGES[view];
  const b = document.querySelector(`#sidebar button[data-view="${CSS.escape(view)}"]`);
  const t = b && (b.querySelector(".sb-label") || b).textContent.replace(/\s+/g, " ").trim();
  return t || (view.charAt(0).toUpperCase() + view.slice(1));
}

/* Where somebody is, in words: "KC @ DEN · live", "Most Likely · NFL". */
function woWhere(x) {
  const g = x.game;
  if (g && g.away && g.home) {
    const st = g.state === "live" ? "live" : g.state === "final" ? "final" : g.state === "pre" ? "before the game" : "";
    return `${escapeHtml(g.away)} @ ${escapeHtml(g.home)}${st ? ` <span class="od-mute">· ${st}</span>` : ""}`;
  }
  const lg = WO_LEAGUES[String(x.detail || "").split("_")[0]];
  return `${escapeHtml(woPage(x.view))}${lg ? ` <span class="od-mute">· ${escapeHtml(lg)}</span>` : ""}`;
}

function woAgo(s) {
  s = Math.max(0, Math.round(Number(s) || 0));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

function woInitials(p) {
  const src = String(p.name || p.handle || "?").replace(/[^A-Za-z0-9 ]/g, " ").trim();
  return (src.split(/\s+/).slice(0, 2).map((w) => w[0]).join("") || "?").toUpperCase();
}

function woMemberHTML(m) {
  const c = Math.abs(Number(m.color) || 0) % 8;
  return `<li class="wo-row">
    <span class="wo-av wo-c${c}" aria-hidden="true">${escapeHtml(woInitials(m))}</span>
    <div class="wo-who">
      <div class="wo-name">${m.name ? `${escapeHtml(m.name)} ` : ""}<span class="wo-handle">${m.handle
        ? `@${escapeHtml(m.handle)}` : "no username yet"}</span></div>
      <div class="wo-where">${woWhere(m)}</div>
      <div class="wo-time">On this page ${woAgo(m.on_page_s)} · on the site ${woAgo(m.on_site_s)}${m.tabs > 1 ? ` · ${m.tabs} tabs` : ""}</div>
    </div>
    <span class="wo-seen" title="Last heard from">${woAgo(m.seen_s)} ago</span>
  </li>`;
}

function woPageHTML(p) {
  return `<tr><th scope="row">${woWhere(p)}</th><td>${p.members}</td><td>${p.visitors}</td></tr>`;
}

/* The card's inside from an answer: the counts, by name, every page open. */
function woHTML(d) {
  const at = typeof tzTime === "function" && d.at
    ? tzTime(d.at * 1000, { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "";
  const named = (d.members || []).map(woMemberHTML).join("");
  const unnamed = d.unnamed_members
    ? `<p class="od-note">${d.unnamed_members} more member${d.unnamed_members === 1 ? "" : "s"} on, not shown by name:
        the Privacy Policy’s notice has not reached them yet, or they turned off “Show me in Who’s on now”.</p>` : "";
  const pages = (d.pages || []).map(woPageHTML).join("");
  return `<h2 class="od-h">Who’s on now${at ? ` <span class="od-mute wo-at">${escapeHtml(at)}</span>` : ""}</h2>
    <div class="od-tiles">${odTile(odN(d.members_total), "Members on")}${odTile(odN(d.visitors), "Visitors")}${
      odTile(odN((d.pages || []).length), "Pages open")}</div>
    <h3 class="wo-h">By name</h3>
    ${named ? `<ul class="wo-list">${named}</ul>` : `<p class="od-note">Nobody to show by name right now.</p>`}
    ${unnamed}
    <h3 class="wo-h">Every page open</h3>
    ${pages ? `<div class="tbl-scroll"><table class="od-tbl wo-tbl"><thead><tr><th scope="col">Page</th><th scope="col">Members</th>
      <th scope="col">Visitors</th></tr></thead><tbody>${pages}</tbody></table></div>`
      : `<p class="od-note">Nobody has a page open right now.</p>`}
    <p class="od-note">A tab counts while it has said where it is in the last ${Math.round((d.window_s || 150) / 60 * 10) / 10} minutes.
      Held in the server’s memory, never written down.</p>`;
}

/* The card's inside as it stands: the last answer, else the desk's counts. */
function odWhoInner(now) {
  if (_woLast) return woHTML(_woLast);
  return `<h2 class="od-h">Who’s on now</h2>${odNowHTML(now)}<p class="od-note">${_woRefused
    ? "The names and pages are only for the site’s own account."
    : "Asking who is on, and where…"}</p>`;
}

async function woFill() {
  if (_woBusy) return;
  _woBusy = true;
  try {
    const r = await fetch("/api/owner/whoson", { credentials: "same-origin", cache: "no-store" });
    if (r.status === 404 || r.status === 403 || r.status === 401) {
      _woLast = null;
      _woRefused = true;
    } else if (r.ok) {
      _woLast = await r.json();
      _woRefused = false;
    }
    const card = document.getElementById("od-who");
    if (card) card.innerHTML = odWhoInner(_odLast && _odLast.now);
  } catch (e) {
    /* The last answer stays up; the next tick asks again. */
  } finally {
    _woBusy = false;
  }
}

function woTick() {
  clearTimeout(_woTimer);
  _woTimer = setTimeout(() => {
    if (typeof state !== "undefined" && state.view !== "owner") return;
    if (document.visibilityState !== "hidden") woFill();
    woTick();
  }, WO_EVERY_MS);
}

function odAccountsHTML(a) {
  if (!a || a.error) return odCard("Accounts", odErr(a));
  const b1 = a.back_day1 || {}, b7 = a.back_week1 || {};
  return odCard("Accounts", `<div class="od-tiles">${odTile(odN(a.total), "All accounts")}${odTile(odN(a.new_today), "New today")}${
    odTile(odN(a.new_7d), "New, 7 days")}</div>${odBars(a.signups || [])}
    <ul class="od-list">${odRow("New, last 30 days", odN(a.new_30d))}${odRow("Signed in today", odN(a.seen_today))}${
      odRow("Signed in, last 7 days", odN(a.seen_7d))}${odRow("Signed in, last 30 days", odN(a.seen_30d))}${
      odRow("Came back after their first day", `${odN(b1.back)} of ${odN(b1.of)} · ${odPct(b1.back, b1.of)}`)}${
      odRow("Came back after their first week", `${odN(b7.back)} of ${odN(b7.of)} · ${odPct(b7.back, b7.of)}`)}</ul>`);
}

function odMoneyHTML(m) {
  if (!m || m.error) return odCard("Money", odErr(m));
  const plans = Object.entries(m.by_plan || {}).map(([k, n]) => odRow(`On ${escapeHtml((m.plans || {})[k] || k)}`, odN(n))).join("");
  return odCard("Money", `<div class="od-tiles">${odTile(odN(m.paying), "Paying")}${odTile(odN(m.trialing), "On a trial")}${
    odTile(odMoney(m.mrr), "A month, recurring")}</div>
    <ul class="od-list">${plans}${odRow("New paying, last 7 days", odN(m.new_7d))}${odRow("Renewing in the next 7 days", odN(m.renewing_7d))}${
      odRow("Cancelling at the period's end", odN(m.cancelling), m.cancelling ? "warn" : "")}${
      odRow("Payment failing", odN(m.past_due), m.past_due ? "bad" : "")}${odRow("Lapsed, last 30 days", odN(m.lapsed_30d))}</ul>
    <p class="od-note">“A month, recurring” is every paying plan's price spread over its months: a yearly member counts a twelfth of the year.</p>`);
}

function odPicksHTML(p) {
  if (!p || p.error) return odCard("Today's picks", odErr(p));
  const rows = (p.books || []).map((b) => `<tr><th scope="row">${escapeHtml(b.book)}</th><td>${b.n}</td><td>${b.won}-${b.lost}${b.push ? `-${b.push}` : ""}</td><td>${b.open}</td>
    <td class="${toneOf(b.units)}">${odUnits(b.units)}</td></tr>`).join("");
  const r = p.record || null;
  const rec = r ? `<ul class="od-list">${odRow(`The record${r.since ? ` since ${escapeHtml(r.since)}` : ""}`, `${odN(r.wins)}-${odN(r.losses)} · ${odUnits(r.units)}${
    r.roi != null ? ` · ${(r.roi * 100).toFixed(1)}% ROI` : ""}`)}${r.longshots ? odRow("Long Shots (their own record)",
    `${odN(r.longshots.wins)}-${odN(r.longshots.losses)} · ${odUnits(r.longshots.units)}`) : ""}${odRow("Open bets, every day", odN(p.open))}</ul>` : "";
  return odCard("Today's picks", `${rows ? `<div class="tbl-scroll"><table class="od-tbl"><thead><tr><th scope="col">Book</th><th scope="col">Picks</th>
    <th scope="col">W-L</th><th scope="col">Open</th><th scope="col">Units</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : `<p class="od-note">Nothing on today's boards yet.</p>`}${rec}`, `<a class="od-more" href="#record">Record →</a>`);
}

function odHealthHTML(h) {
  if (!h || h.error) return odCard("The site's health", odErr(h));
  const stale = Object.entries(h.stale || {});
  // Each board's age; a league with no games on its scoreboard is resting, not late.
  const resting = new Set(h.resting || []);
  const boards = Object.entries(h.boards || {}).map(([k, v]) => `<span class="od-pill${resting.has(k) ? " rest" : v > 3 ? " warn" : ""}">${
    escapeHtml(OD_LEAGUES[k] || k)} ${resting.has(k) ? "resting" : v < 1 ? `${Math.round(v * 60)} min` : `${v} h`}</span>`).join("");
  const u = h.update || null;
  const o = h.odds || null;
  const crashes = (h.crash_top || []).map((c) => `<li class="od-mono">×${c.n} ${escapeHtml(c.m)}</li>`).join("");
  return odCard("The site's health", `<div class="od-tiles">${odTile(odN(h.crashes), "Crashes, 24 h", h.crashes ? "warn" : "good")}${
    odTile(odN((h.builds_warned || []).length), "Builds warned", (h.builds_warned || []).length ? "warn" : "good")}${
    odTile(odN(stale.length), "Boards stale", stale.length ? "bad" : "good")}</div>
    ${boards ? `<div class="od-pills" aria-label="How old each board is">${boards}</div>` : ""}
    <ul class="od-list">${odRow("Last update", u ? `${u.ok === false ? "failed" : "ok"}${u.at ? ` · ${escapeHtml(String(u.at).replace("T", " "))}` : ""}` : "—", u && u.ok === false ? "bad" : "")}${
      odRow("Running version", escapeHtml(h.commit || (u && u.commit) || "—"))}${
      odRow("Bets last graded", odAgo(h.settled_ago_s))}${
      o ? odRow("Odds credits left this month", `${odN(o.remaining)} · ${odN(o.per_day)} a day for ${odN(o.days_left)} days`, o.remaining < 2000 ? "warn" : "") : ""}${
      h.disk ? odRow("Disk", `${h.disk.free_gb} GB free · ${h.disk.used_pct}% used`, h.disk.used_pct > 90 ? "bad" : h.disk.used_pct > 80 ? "warn" : "") : ""}${
      (h.builds_warned || []).length ? odRow("Builds with warnings", escapeHtml(h.builds_warned.join(", ")), "warn") : ""}</ul>
    ${u && u.note ? `<p class="od-note od-mono">${escapeHtml(u.note)}</p>` : ""}
    ${crashes ? `<ul class="od-crash">${crashes}</ul>` : ""}`);
}

function odRoomHTML(c) {
  if (!c || c.error) return odCard("The room", odErr(c));
  return odCard("The room", `<ul class="od-list">${odRow("Posts today", odN(c.posts_today))}${odRow("Comments today", odN(c.comments_today))}${
    odRow("Game-chat messages today", odN(c.chat_today))}${odRow("Reports waiting", odN(c.reports_open), c.reports_open ? "warn" : "")}${
    c.push_phones != null ? odRow("Phones with alerts on", odN(c.push_phones)) : ""}</ul>`, `<a class="od-more" href="#feed">Social →</a>`);
}

/* Reports to review: what readers flagged in the feed and the game chat, in
   one queue (engine/ownerdesk.reports). Three reports hide a thing on their
   own until somebody looks; Hide takes it down for everybody, Keep it up
   clears its reports, Restore puts a hidden one back. The words and the
   reasons, never who wrote or who reported. */
const OD_KIND = { post: "Post", comment: "Comment", message: "Game-chat message" };
let _odHidOpen = false;
function odRepHTML(it) {
  const btn = (hide, word, ghost) => `<button type="button" class="btn${ghost ? " ghost" : ""}" data-od-mod="${hide ? 1 : 0}" data-where="${
    escapeAttr(it.where)}" data-kind="${escapeAttr(it.kind)}" data-id="${Number(it.id) || 0}">${word}</button>`;
  const open = it.hidden ? "" : it.kind === "post" ? `<a class="od-more" href="#feed/post/${Number(it.id) || 0}">Open</a>`
    : it.game ? `<a class="od-more" href="#pbp/${escapeAttr(it.game)}">The game</a>` : "";
  const said = `${it.reports ? `${it.reports} report${it.reports === 1 ? "" : "s"}` : "hidden by hand"}${
    (it.reasons || []).length ? ` · ${escapeHtml(it.reasons.join(", "))}` : ""}`;
  return `<li class="od-rep${it.hidden ? " hid" : ""}"><div class="od-rep-t"><b>${OD_KIND[it.kind] || "Item"}</b><span>${said}</span></div>
    <p>${escapeHtml(it.text || "") || `<span class="od-mute">(no words)</span>`}</p>
    <div class="od-rep-acts">${it.hidden ? btn(false, "Restore", true) : `${btn(true, "Hide")}${btn(false, "Keep it up", true)}`}${open}</div></li>`;
}

function odReportsHTML(r) {
  if (!r || r.error) return odCard("Reports to review", odErr(r));
  const open = (r.open || []).map(odRepHTML).join("");
  const hid = (r.hidden || []).map(odRepHTML).join("");
  const more = (n, shown) => (n > shown ? `<p class="od-note">The ${shown} most reported of ${odN(n)}; the rest show as these clear.</p>` : "");
  return odCard(`Reports to review${r.open_n ? ` <span class="od-count">${odN(r.open_n)}</span>` : ""}`,
    `${open ? `<ul class="od-reps">${open}</ul>${more(r.open_n, (r.open || []).length)}`
      : `<p class="od-note">Nothing waiting. Three reports take a post, comment or chat message down on their own until you look at it here.</p>`}
    ${hid ? `<details class="od-hid"${_odHidOpen ? " open" : ""}><summary>Hidden from everybody · ${odN(r.hidden_n)}</summary><ul class="od-reps">${hid}</ul></details>` : ""}`);
}

async function odMod(b) {
  b.disabled = true;
  try {
    const r = await fetch("/api/owner/hide", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ where: b.dataset.where, kind: b.dataset.kind, id: Number(b.dataset.id), hidden: b.dataset.odMod === "1" }) });
    const got = await r.json().catch(() => ({}));
    if (!r.ok) {
      b.disabled = false;
      if (typeof tfToast === "function") tfToast(got.error || "That did not go through.");
      return;
    }
    if (typeof tfToast === "function") tfToast(b.dataset.odMod === "1" ? "Hidden for everybody." : "Up, and its reports cleared.");
    odFill();
  } catch (e) {
    b.disabled = false;
  }
}

/* ACCOUNTS — find any account and act on it (engine/owneraccounts). Ethan,
   2026-11-02: "I also want more access and stuff to be able to do to
   people's accounts". The one card on the desk that names a member: search
   by email, username or account number; an account's card says how it signs
   in, where its membership stands (trial had or not, Stripe's customer
   linked), free access and suspension; and its buttons give or end free
   access, sign it out everywhere, suspend it or lift that, reset a username,
   or delete it (typing its email). Suspend and delete are refused while
   Stripe can still charge the account. Every action is written down: the
   account's own lines on its card, and the latest on the card with no
   account open. The card keeps its own state, so the desk's minute redraw
   leaves a search and an open account where they were. */
const OA_GRANTS = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [180, "6 months"], [366, "A year"]];
const OA_WORDS = { grant: "Gave free access", ungrant: "Ended free access", signout: "Signed out everywhere",
  suspend: "Suspended", unsuspend: "Lifted the suspension", rename: "Reset the username", delete: "Deleted the account" };
const OA_STATUS = { active: ["Paying", "good"], trialing: ["On a trial", "good"], past_due: ["Payment failed", "warn"],
  unpaid: ["Unpaid", "warn"], canceled: ["Cancelled", "rest"], none: ["No plan", "rest"], incomplete: ["Never finished", "rest"],
  paused: ["Paused", "rest"] };
const _oa = { q: "", list: null, card: null, recent: null, busy: false, said: "", armed: "" };
let _oaArmTimer = null;

const oaDay = (t) => (t ? new Date(Number(t) * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—");
function oaChip(st, entitled, suspended) {
  if (suspended) return `<span class="od-pill warn">Suspended</span>`;
  const [w, tone] = OA_STATUS[st] || [st || "No plan", "rest"];
  return `<span class="od-pill${tone === "good" ? "" : ` ${tone}`}">${escapeHtml(entitled && st === "none" ? "Free access" : w)}</span>`;
}

function oaRowHTML(a) {
  return `<li><button type="button" class="oa-hit" data-oa-open="${Number(a.id) || 0}">
    <span class="oa-hit-t"><b>${a.handle ? `@${escapeHtml(a.handle)}` : escapeHtml(a.who || `Account ${a.id}`)}</b>${
      a.handle ? ` <span class="od-mute">${escapeHtml(a.who || "")}</span>` : ""}</span>
    <span class="oa-hit-s">${oaChip(a.status, a.entitled, a.suspended)}<span class="od-mute">#${Number(a.id) || 0} · joined ${oaDay(a.joined)}</span></span>
  </button></li>`;
}

function oaLogHTML(rows, withWho) {
  if (!rows || !rows.length) return `<p class="od-note">Nothing done from the desk yet.</p>`;
  return `<ul class="oa-log">${rows.map((r) => `<li><b>${escapeHtml(OA_WORDS[r.action] || r.action)}</b>${
    withWho ? ` · ${r.gone ? `account ${Number(r.id) || 0} <span class="od-mute">(deleted)</span>`
      : `<button type="button" class="oa-link" data-oa-open="${Number(r.id) || 0}">${escapeHtml(r.who || `account ${r.id}`)}</button>`}` : ""}${
    r.detail ? ` <span class="od-mute">· ${escapeHtml(r.detail)}</span>` : ""}<span class="oa-log-at">${escapeHtml(oaDay(r.at))}</span></li>`).join("")}</ul>`;
}

function oaArmBtn(key, word, again, cls) {
  const armed = _oa.armed === key;
  return `<button type="button" class="btn${cls ? ` ${cls}` : ""}${armed ? " oa-armed" : ""}" data-oa-act="${key}" data-oa-arm="1">${
    armed ? again : word}</button>`;
}

function oaCardHTML(c) {
  const m = c.membership || {};
  const [stWord] = OA_STATUS[m.status] || [m.status || "No plan"];
  const ends = m.period_end ? ` · ${m.cancel_at_end || m.status === "canceled" ? "ends" : "renews"} ${oaDay(m.period_end)}` : "";
  const plan = `${escapeHtml(m.entitled || m.status !== "none" ? stWord : "No plan")}${m.plan_name ? ` · ${escapeHtml(m.plan_name)}` : ""}${
    m.status === "none" ? "" : ends}`;
  const grant = c.grant ? `Until ${oaDay(c.grant)}` : "None";
  const codes = (c.codes && c.codes.codes || []).length ? `${c.codes.codes.length} redeemed${c.codes.active ? `, covered to ${oaDay(c.codes.granted_to)}` : ""}` : "None";
  const blocked = m.charges ? `<p class="od-note">Suspend and Delete wait until Stripe can no longer charge this account: cancel its subscription on Stripe first${
    c.stripe ? ` (<a href="${safeHref(c.stripe)}" target="_blank" rel="noopener">open the customer</a>)` : ""}.</p>` : "";
  const acts = [
    `<form class="oa-grant" id="oa-grant"><label for="oa-days" class="od-sr">How long</label><select id="oa-days">${
      OA_GRANTS.map(([d, w]) => `<option value="${d}"${d === 30 ? " selected" : ""}>${w}</option>`).join("")}</select>
      <button type="submit" class="btn">${c.grant ? "Change free access" : "Give free access"}</button></form>`,
    c.grant ? oaArmBtn("ungrant", "End free access", "Tap again to end it", "ghost") : "",
    oaArmBtn("signout", "Sign out everywhere", "Tap again to sign out", "ghost"),
    c.handle ? oaArmBtn("rename", "Reset username", `Tap again: @member${c.id}`, "ghost") : "",
    c.site_account ? "" : c.suspended ? oaArmBtn("unsuspend", "Lift the suspension", "Tap again to lift it", "ghost")
      : m.charges ? "" : oaArmBtn("suspend", "Suspend", "Tap again to suspend", "oa-warn"),
  ].filter(Boolean).join("");
  const del = c.site_account || m.charges ? "" : `<details class="oa-del"><summary>Delete this account…</summary>
    <form id="oa-delete" autocomplete="off"><p class="od-note">Everything goes: its bets, posts, chat, settings and membership record. It cannot be undone, and the same
      ${c.phone_account ? "number" : "address"} could sign up again — Suspend keeps them out instead.</p>
      <label for="oa-confirm" class="oa-lab">Type its ${c.phone_account ? "phone number" : "email"} to confirm</label>
      <input id="oa-confirm" class="oa-input" type="text" inputmode="${c.phone_account ? "tel" : "email"}" placeholder="${escapeAttr(c.who || "")}">
      <button type="submit" class="btn oa-danger">Delete for good</button></form></details>`;
  return `<div class="oa-top"><button type="button" class="oa-link" data-oa-back="1">← ${_oa.list ? "Results" : "Back"}</button>
      <span class="od-mute">#${Number(c.id) || 0}</span></div>
    <h3 class="oa-name">${c.handle ? `@${escapeHtml(c.handle)}` : escapeHtml(c.who || "")}${c.verified ? ` <span class="od-pill">Verified</span>` : ""} ${
      oaChip(m.status, m.entitled, !!c.suspended)}</h3>
    <ul class="od-list">${odRow(c.phone_account ? "Phone" : "Email", escapeHtml(c.who || "—"))}${
      c.name ? odRow("Display name", escapeHtml(c.name)) : ""}${
      odRow("Joined", oaDay(c.joined))}${odRow("Last seen", c.seen ? oaDay(c.seen) : "Never")}${
      odRow("Signs in with", escapeHtml((c.ways || []).join(", ") || "—"))}${
      odRow("Signed in on", `${odN(c.sessions)} device${c.sessions === 1 ? "" : "s"} · ${odN(c.phones)} phone${c.phones === 1 ? "" : "s"} with alerts`)}${
      odRow("Membership", plan, m.entitled ? "good" : "mute")}${
      odRow("Free trial", m.trial_used ? "Had it — no second trial" : "Never had one", m.trial_used ? "mute" : "")}${
      c.stripe ? odRow("Stripe", `<a href="${safeHref(c.stripe)}" target="_blank" rel="noopener">Open the customer</a>`) : ""}${
      odRow("Free access from the desk", grant, c.grant ? "good" : "mute")}${odRow("Codes", codes, "mute")}${
      c.comped ? odRow("Comp list", "On it — full access", "good") : ""}${
      c.suspended ? odRow("Suspended", `Since ${oaDay(c.suspended)}`, "warn") : ""}</ul>
    ${m.note ? `<p class="oa-says"><b>Its account page says</b> ${escapeHtml(m.note)}</p>` : ""}
    <div class="oa-acts">${acts}</div>${blocked}${del}
    <p class="od-note" id="oa-said" role="status">${escapeHtml(_oa.said || "")}</p>
    <h4 class="wo-h">What the desk has done to it</h4>${oaLogHTML(c.log, false)}`;
}

function oaInner() {
  const search = `<h2 class="od-h">Accounts</h2>
    <form class="oa-find" id="oa-find" role="search" autocomplete="off">
      <label for="oa-q" class="od-sr">Find an account</label>
      <input id="oa-q" class="oa-input" type="search" enterkeyhint="search" value="${escapeAttr(_oa.q)}" placeholder="Email, username or account number">
      <button type="submit" class="btn">Find</button></form>`;
  if (_oa.card) return `${search}${oaCardHTML(_oa.card)}`;
  const list = _oa.list == null ? "" : _oa.list.length ? `<ul class="oa-hits">${_oa.list.map(oaRowHTML).join("")}</ul>`
    : `<p class="od-note">No account matches “${escapeHtml(_oa.q)}”.</p>`;
  return `${search}${list}<p class="od-note" id="oa-said" role="status">${escapeHtml(_oa.said || "")}</p>
    <h4 class="wo-h">Done from the desk lately</h4>${_oa.recent ? oaLogHTML(_oa.recent, true) : `<p class="od-note">Loading…</p>`}`;
}

function oaDraw() {
  const host = document.getElementById("od-acct");
  if (host) host.innerHTML = oaInner();
}

async function oaGet(qs) {
  const r = await fetch(`/api/owner/accounts${qs}`, { credentials: "same-origin", cache: "no-store" });
  const got = await r.json().catch(() => ({}));
  return { ok: r.ok, got };
}

async function oaFind(q) {
  _oa.q = String(q || "").trim();
  _oa.card = null;
  _oa.said = "";
  try {
    const { ok, got } = await oaGet(_oa.q ? `?q=${encodeURIComponent(_oa.q)}` : "");
    if (!ok) { _oa.said = got.error || "That did not go through."; oaDraw(); return; }
    _oa.list = _oa.q ? got.accounts || [] : null;
    _oa.recent = got.recent || [];
  } catch (e) {
    _oa.said = "Could not reach the server.";
  }
  oaDraw();
}

async function oaOpen(id) {
  _oa.said = "";
  _oa.armed = "";
  try {
    const { ok, got } = await oaGet(`?id=${Number(id) || 0}`);
    if (!ok) { _oa.said = got.error || "That did not go through."; oaDraw(); return; }
    _oa.card = got.card;
  } catch (e) {
    _oa.said = "Could not reach the server.";
  }
  oaDraw();
  const host = document.getElementById("od-acct");
  if (host && host.scrollIntoView) host.scrollIntoView({ block: "start", behavior: "smooth" });
}

async function oaAct(action, extra) {
  if (!_oa.card || _oa.busy) return;
  _oa.busy = true;
  _oa.armed = "";
  const id = _oa.card.id;
  try {
    const r = await fetch("/api/owner/account", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, action, ...(extra || {}) }) });
    const got = await r.json().catch(() => ({}));
    if (!r.ok) {
      _oa.said = got.error || "That did not go through.";
    } else if (got.deleted) {
      _oa.card = null;
      _oa.list = (_oa.list || []).filter((a) => a.id !== id);
      _oa.said = `Account #${id} is deleted.`;
      if (typeof tfToast === "function") tfToast("Deleted.");
      oaFind(_oa.q);
      return;
    } else {
      _oa.card = got.card || _oa.card;
      _oa.said = `${OA_WORDS[action] || "Done"}.`;
      if (_oa.list) _oa.list = _oa.list.map((a) => (a.id === id && got.card ? { ...a, handle: got.card.handle,
        suspended: !!got.card.suspended, status: (got.card.membership || {}).status, entitled: !!(got.card.membership || {}).entitled } : a));
      if (typeof tfToast === "function") tfToast(_oa.said);
    }
  } catch (e) {
    _oa.said = "Could not reach the server.";
  } finally {
    _oa.busy = false;
  }
  oaDraw();
}

function odSwitchesHTML(sw, al) {
  if (!Array.isArray(sw)) return odCard("Switches", odErr(sw));
  // The desk's own alerts (engine/owneralerts) reach this account's phones.
  const n = al && !al.error ? Number(al.phones) || 0 : null;
  const mine = n == null ? "" : odRow("Problems pushed to this account's phones",
    n ? `On · ${odN(n)} phone${n === 1 ? "" : "s"}` : "No phone yet", n ? "good" : "warn");
  return odCard("Switches", `<ul class="od-list">${sw.map((s) => odRow(escapeHtml(s.name),
    `${s.on ? "On" : "Off"}${s.note ? ` · ${escapeHtml(s.note)}` : ""}`, s.on ? "good" : "mute")).join("")}${mine}</ul>${
    n === 0 ? `<p class="od-note">Sign in to this account on your phone and turn alerts on (the Alerts page): a stale board, grading stopped, the disk filling, a failed update or odds credits running low then reach you, once a day each.</p>` : ""}`);
}

/* What needs the owner now — the same list engine/owneralerts pushes to this
   account's phones, once a day each. Nothing to show when all is well. */
function odNeedsHTML(needs) {
  if (!Array.isArray(needs) || !needs.length) return "";
  return `<section class="od-card od-needs" aria-label="Needs you"><h2 class="od-h">Needs you</h2><ul class="od-need-list">${
    needs.map((p) => `<li><b>${escapeHtml(p.title || "")}</b><span>${escapeHtml(p.body || "")}</span></li>`).join("")}</ul></section>`;
}

/* The one tool that reaches everybody: a notice across the top of every page. */
function odNoticeHTML(n) {
  const on = n && n.text;
  const until = on && n.until ? (typeof tzTime === "function" ? tzTime(n.until * 1000, { weekday: "short", hour: "numeric", minute: "2-digit" }) : "") : "";
  return odCard("A notice to everybody", `${on ? `<div class="od-live ${escapeAttr(n.tone || "info")}"><b>Up now</b> ${escapeHtml(n.text)}${
    until ? ` <span class="od-mute">· until ${escapeHtml(until)}</span>` : ""}</div>` : `<p class="od-note">No notice up. Write one and it shows across the top of every page until it runs out or you take it down; anybody can close it for themselves.</p>`}
    <form class="od-form" id="od-notice" autocomplete="off">
      <label for="od-text" class="od-sr">The notice</label>
      <textarea id="od-text" maxlength="200" rows="2" placeholder="Tonight's picks are late — the odds feed is down."></textarea>
      <div class="od-form-row">
        <select id="od-hours" aria-label="How long it stays up">${OD_HOURS.map(([h, w]) => `<option value="${h}"${h === 24 ? " selected" : ""}>${w}</option>`).join("")}</select>
        <select id="od-tone" aria-label="How it looks"><option value="info">News</option><option value="warn">Heads up</option><option value="good">Good news</option></select>
        <button type="submit" class="btn">Put it up</button>
        ${on ? `<button type="button" class="btn ghost" id="od-clear">Take it down</button>` : ""}
      </div>
      <p class="od-note" id="od-said" role="status"></p>
    </form>`);
}

function odHTML(d) {
  // Reports waiting go near the top; with none they sit beside the room.
  const waiting = !!(d.reports && d.reports.open_n);
  const reps = odReportsHTML(d.reports);
  return `${odNeedsHTML(d.needs)}<section class="od-card od-who" id="od-who" aria-label="Who’s on now">${odWhoInner(d.now)}</section>
    <section class="od-card od-acct" id="od-acct" aria-label="Accounts">${oaInner()}</section>
    ${odNoticeHTML(d.notice)}${waiting ? reps : ""}${odPicksHTML(d.picks)}${odMoneyHTML(d.money)}${odAccountsHTML(d.accounts)}
    ${odHealthHTML(d.health)}${odRoomHTML(d.community)}${waiting ? "" : reps}${odSwitchesHTML(d.switches, d.alerts)}
    <p class="od-foot">Only this account can open this page. Who’s on now names only the members the Privacy Policy’s notice
      has reached who left “Show me in Who’s on now” on, and Accounts shows one account at a time, for support and the Terms;
      everything else here is a count or the business’s own number.</p>`;
}

async function odFill() {
  const host = document.getElementById("owner-body");
  if (!host || _odBusy) return;
  // Never redraw over a notice being written, or a search or delete being typed.
  const typing = document.activeElement && document.activeElement.closest &&
    document.activeElement.closest("#od-notice, #od-acct form, #od-acct details[open]");
  if (typing && _odLast) return;
  _odBusy = true;
  try {
    const r = await fetch("/api/owner/desk", { credentials: "same-origin", cache: "no-store" });
    if (r.status === 404 || r.status === 403 || r.status === 401) {
      host.innerHTML = `<p class="empty">This page is only for the site’s own account.</p>`;
      return;
    }
    const d = await r.json();
    _odLast = d;
    host.innerHTML = odHTML(d);
    const sub = document.getElementById("owner-sub");
    if (sub && typeof tzTime === "function") {
      sub.textContent = `updated ${tzTime((d.at || Date.now() / 1000) * 1000, { hour: "numeric", minute: "2-digit" })}`;
    }
  } catch (e) {
    if (!host.querySelector(".od-tiles")) host.innerHTML = `<p class="empty">Could not reach the server. Trying again.</p>`;
  } finally {
    _odBusy = false;
  }
}

async function odNotice(body) {
  const said = document.getElementById("od-said");
  try {
    const r = await fetch("/api/owner/notice", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const got = await r.json().catch(() => ({}));
    if (!r.ok) { if (said) said.textContent = got.error || "That did not go through."; return; }
    if (_odLast) _odLast.notice = got.notice || null;
    if (window.qbNotice) qbNotice(got.notice || null);
    else if (got.notice && typeof loadRoom === "function") loadRoom("js/notice.js", "css/notice.css").then(() => window.qbNotice && qbNotice(got.notice));
    document.activeElement && document.activeElement.blur && document.activeElement.blur();
    const host = document.getElementById("owner-body");
    if (host && _odLast) host.innerHTML = odHTML(_odLast);
  } catch (e) {
    if (said) said.textContent = "Could not reach the server.";
  }
}

document.addEventListener("submit", (e) => {
  const f = e.target;
  if (f && f.id === "oa-find") {
    e.preventDefault();
    oaFind((document.getElementById("oa-q") || {}).value || "");
    return;
  }
  if (f && f.id === "oa-grant") {
    e.preventDefault();
    oaAct("grant", { days: Number((document.getElementById("oa-days") || {}).value || 30) });
    return;
  }
  if (f && f.id === "oa-delete") {
    e.preventDefault();
    const typed = ((document.getElementById("oa-confirm") || {}).value || "").trim();
    if (!typed) { _oa.said = "Type the account’s email (or phone number) to delete it."; oaDraw(); return; }
    oaAct("delete", { confirm: typed });
    return;
  }
  if (!e.target || e.target.id !== "od-notice") return;
  e.preventDefault();
  const text = (document.getElementById("od-text") || {}).value || "";
  if (!text.trim()) { const s = document.getElementById("od-said"); if (s) s.textContent = "Write the notice first."; return; }
  odNotice({ text, hours: Number((document.getElementById("od-hours") || {}).value || 24),
             tone: (document.getElementById("od-tone") || {}).value || "info" });
});
document.addEventListener("click", (e) => {
  const t = e.target && e.target.closest ? e.target : null;
  const open = t && t.closest("[data-oa-open]");
  if (open) { oaOpen(open.dataset.oaOpen); return; }
  if (t && t.closest("[data-oa-back]")) { _oa.card = null; _oa.said = ""; _oa.armed = ""; oaDraw(); if (!_oa.recent) oaFind(_oa.q); return; }
  const act = t && t.closest("[data-oa-act]");
  if (act && !act.disabled) {
    // Two taps: the first arms the button for a few seconds, the second acts.
    const key = act.dataset.oaAct;
    if (_oa.armed !== key) {
      _oa.armed = key;
      oaDraw();
      clearTimeout(_oaArmTimer);
      _oaArmTimer = setTimeout(() => { if (_oa.armed === key) { _oa.armed = ""; oaDraw(); } }, 4000);
      return;
    }
    oaAct(key);
    return;
  }
  if (e.target && e.target.id === "od-clear") odNotice({ clear: true });
  const b = e.target && e.target.closest && e.target.closest("[data-od-mod]");
  if (b && !b.disabled) odMod(b);
});
// The hidden list stays open across the minute's redraw.
document.addEventListener("toggle", (e) => {
  if (e.target && e.target.classList && e.target.classList.contains("od-hid")) _odHidOpen = e.target.open;
}, true);

function odTick() {
  clearTimeout(_odTimer);
  _odTimer = setTimeout(() => {
    if (typeof state !== "undefined" && state.view !== "owner") return;
    if (document.visibilityState !== "hidden") odFill();
    odTick();
  }, OD_EVERY_MS);
}

function renderOwner() {
  const host = document.getElementById("owner-body");
  if (!host) return;
  if (!host.firstChild) host.innerHTML = `<p class="empty">Opening the desk…</p>`;
  odFill();
  odTick();
  woFill();
  woTick();
  if (!_oa.recent && !_oa.card) oaFind(_oa.q);
}
