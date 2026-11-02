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

   Loaded the first time it opens (app.js roomCall). The server answers
   /api/owner/desk for the site's own account alone and, to anybody else, as
   if it did not exist. Everything on it is a count or the business's own
   number — nobody is named here. Redrawn every OD_EVERY_MS while open. */

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

function odSwitchesHTML(sw) {
  if (!Array.isArray(sw)) return odCard("Switches", odErr(sw));
  return odCard("Switches", `<ul class="od-list">${sw.map((s) => odRow(escapeHtml(s.name),
    `${s.on ? "On" : "Off"}${s.note ? ` · ${escapeHtml(s.note)}` : ""}`, s.on ? "good" : "mute")).join("")}</ul>`);
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
  return `${odNowHTML(d.now)}<p class="od-door"><a href="#whoson">Who's on now, by name and page →</a></p>
    ${odNoticeHTML(d.notice)}${waiting ? reps : ""}${odPicksHTML(d.picks)}${odMoneyHTML(d.money)}${odAccountsHTML(d.accounts)}
    ${odHealthHTML(d.health)}${odRoomHTML(d.community)}${waiting ? "" : reps}${odSwitchesHTML(d.switches)}
    <p class="od-foot">Counts and the business's own numbers; nobody is named here. Only this account can open this page.</p>`;
}

async function odFill() {
  const host = document.getElementById("owner-body");
  if (!host || _odBusy) return;
  // Never redraw over a notice being written.
  const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#od-notice");
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
  if (!e.target || e.target.id !== "od-notice") return;
  e.preventDefault();
  const text = (document.getElementById("od-text") || {}).value || "";
  if (!text.trim()) { const s = document.getElementById("od-said"); if (s) s.textContent = "Write the notice first."; return; }
  odNotice({ text, hours: Number((document.getElementById("od-hours") || {}).value || 24),
             tone: (document.getElementById("od-tone") || {}).value || "info" });
});
document.addEventListener("click", (e) => {
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
}
