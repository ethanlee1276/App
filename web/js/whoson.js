/* WHO'S ON NOW — the site owner's page (engine/whoson). Ethan, 2026-11-01:
   "a feature ONLY AVALIBLE for my Qellys Book account on the site that lets
   me see all active users. It shows me all users and what page they are on."

   Loaded the first time it opens (app.js roomCall). The code is nobody's
   secret; the data is: the server answers /api/owner/whoson for the site's
   own account alone, and to anybody else as if it did not exist.

   Named rows are the members the Privacy Policy's notice has reached and who
   left "Show me in Who's on now" on; everyone else is a number on the page
   they have open (engine/whoson says why). Redrawn every WO_EVERY_MS while
   the page is up and in front of the owner. */

const WO_EVERY_MS = 10000;
let _woTimer = null;
let _woBusy = false;

/* Our own pages by their view names. The menu's own words where it has a
   button for the page, these where it does not or says it differently. */
const WO_PAGES = {
  recommended: "Home", likely: "Most Likely", longshots: "Long Shots", live: "Live", pbp: "Game",
  game: "Game bet", prop: "Prop", record: "Record", mybets: "My Bets", account: "Account",
  props: "Over / Under", edge: "Edge", parlays: "Parlays", potd: "Pick of the Day", ask: "Ask",
  feed: "Social", messages: "Messages", alerts: "Alerts", fantasy: "Fantasy", whoson: "Who's on now",
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
    return `${escapeHtml(g.away)} @ ${escapeHtml(g.home)}${st ? ` <span class="wo-mute">· ${st}</span>` : ""}`;
  }
  const lg = WO_LEAGUES[String(x.detail || "").split("_")[0]];
  return `${escapeHtml(woPage(x.view))}${lg ? ` <span class="wo-mute">· ${escapeHtml(lg)}</span>` : ""}`;
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
  return `<tr><td>${woWhere(p)}</td><td class="num">${p.members}</td><td class="num">${p.visitors}</td></tr>`;
}

function woHTML(d) {
  const counts = [["Members on", d.members_total], ["Visitors", d.visitors], ["Pages open", (d.pages || []).length]]
    .map(([k, v]) => `<div class="wo-tile"><div class="wo-tile-v">${v}</div><div class="wo-tile-k">${k}</div></div>`).join("");
  const named = (d.members || []).map(woMemberHTML).join("");
  const unnamed = d.unnamed_members
    ? `<p class="wo-note">${d.unnamed_members} more member${d.unnamed_members === 1 ? "" : "s"} on, not shown by name:
        the Privacy Policy’s notice has not reached them yet, or they turned off “Show me in Who’s on now”.</p>` : "";
  const pages = (d.pages || []).map(woPageHTML).join("");
  return `<div class="wo-tiles">${counts}</div>
    <section class="wo-card">
      <h2 class="wo-h">By name</h2>
      ${named ? `<ul class="wo-list">${named}</ul>` : `<p class="wo-note">Nobody to show by name right now.</p>`}
      ${unnamed}
    </section>
    <section class="wo-card">
      <h2 class="wo-h">Every page open</h2>
      ${pages ? `<div class="tbl-scroll"><table class="wo-tbl"><thead><tr><th>Page</th><th class="num">Members</th>
        <th class="num">Visitors</th></tr></thead><tbody>${pages}</tbody></table></div>`
        : `<p class="wo-note">Nobody has a page open right now.</p>`}
    </section>
    <p class="wo-foot">A tab counts while it has said where it is in the last ${Math.round((d.window_s || 150) / 60 * 10) / 10} minutes.
      Held in the server’s memory, never written down; only this account can open this page.</p>`;
}

async function woFill() {
  const host = document.getElementById("whoson-body");
  if (!host || _woBusy) return;
  _woBusy = true;
  try {
    const r = await fetch("/api/owner/whoson", { credentials: "same-origin", cache: "no-store" });
    if (r.status === 404 || r.status === 403 || r.status === 401) {
      host.innerHTML = `<p class="empty">This page is only for the site’s own account.</p>`;
      return;
    }
    const d = await r.json();
    host.innerHTML = woHTML(d);
    const sub = document.getElementById("whoson-sub");
    // The site's one clock (app.js tzTime), so it reads in the zone Settings names.
    if (sub && typeof tzTime === "function") {
      sub.textContent = `updated ${tzTime((d.at || Date.now() / 1000) * 1000, { hour: "numeric", minute: "2-digit", second: "2-digit" })}`;
    }
  } catch (e) {
    if (!host.querySelector(".wo-tiles")) host.innerHTML = `<p class="empty">Could not reach the server. Trying again.</p>`;
  } finally {
    _woBusy = false;
  }
}

function woTick() {
  clearTimeout(_woTimer);
  _woTimer = setTimeout(() => {
    if (typeof state !== "undefined" && state.view !== "whoson") return;
    if (document.visibilityState !== "hidden") woFill();
    woTick();
  }, WO_EVERY_MS);
}

function renderWhoson() {
  const host = document.getElementById("whoson-body");
  if (!host) return;
  if (!host.firstChild) host.innerHTML = `<p class="empty">Looking…</p>`;
  woFill();
  woTick();
}
