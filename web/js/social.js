/* Qellys Book — Social: the feed, profiles and the Tail button.
   ==========================================================================
   Ethan, 2026-10-06: a social page where people post parlays, a whale-tail
   Tail button with a counter, likes, comments, a bio. 2026-10-07: "a full
   social feature … profiles for users" (audit: docs/SOCIAL_AUDIT.md), and
   then, with a render of the page: "The social page looks cluttered … Here
   is renders you must follow … the account page on the feed page and the
   main account page should be one page … it should all be one main
   profile for the whole site."

   THE RENDER'S LAYOUT, THE SITE'S PALETTE. Three columns — the Social nav
   (Post, Feed, Following, My Posts, Trending, Top Bettors, Tags, Sports),
   the feed under the banner, and the rail (Trending Picks, Top Bettors,
   Popular Sports, Community Stats, the Discord). Colour stays the site's
   gold-on-warm-black (Ethan, 2026-08-23: "carried through the whole site
   so everything matches"); the render's navy is the one thing not copied.

   ONE PROFILE. Your own profile IS the Account page (app.js renderAccount
   mounts mountAccount below): the same header everybody else's profile
   wears, with your posts, picks, friends and settings under it. A link to
   your own handle, and the old #feed/edit, both land there.

   LOADED ON FIRST USE (app.js loadSocial), like the chart library. It runs
   in the page's global scope beside app.js and visuals.js and uses their
   helpers (escapeHtml, icon, teamMark, tfToast, switchView …) by name.

   ROUTES (in the address bar, so back, forward and shared links work):
     #feed  #feed/following  #feed/mine  #feed/s/<sport>  #feed/tag/<tag>
     #feed/trending  #feed/leaders  #feed/tags  #feed/activity
     #feed/post/<id>  #feed/u/<handle>[/picks]  #feed/search/<q>

   THE PAGE SENDS WHICH ROWS, NEVER WHAT THEY SAY. A posted leg is a game id
   or player · market · side · line; the server reads every number off its
   own board, locks a paid leg for a reader who has not paid, and hands out
   bet-slip links only on Tail. */
(function () {
  "use strict";

  const STRONG_KEY = "qb_feed_strong";
  const SPORTS = [["nfl", "NFL"], ["cfb", "CFB"], ["mlb", "MLB"], ["nba", "NBA"],
                  ["wnba", "WNBA"], ["nhl", "NHL"], ["ufc", "UFC"], ["soccer", "Soccer"]];
  const SPORT_NAME = Object.fromEntries(SPORTS);
  // Parlays come off the site's own boards; UFC and soccer are talk only.
  const BOARD_SPORTS = ["nfl", "cfb", "mlb", "nba", "wnba", "nhl"];
  const POPULAR = ["nfl", "mlb", "nba", "nhl", "cfb", "wnba", "ufc", "soccer"];
  const REASONS = [["spam", "Spam"], ["abuse", "Harassment"], ["hate", "Hate"],
                   ["scam", "Scam or selling picks"], ["other", "Something else"]];
  const METRICS = [["win", "Win %"], ["units", "Units"], ["followers", "Followers"]];
  const DAYS = [["7", "7D"], ["30", "30D"], ["all", "All"]];
  const NAV = [["feed", "#feed", "home", "Feed"], ["following", "#feed/following", "userplus", "Following"],
               ["mine", "#feed/mine", "doc", "My Posts"], ["trending", "#feed/trending", "trend", "Trending"],
               ["leaders", "#feed/leaders", "people", "Top Bettors"], ["tags", "#feed/tags", "tag", "Tags"],
               ["activity", "#feed/activity", "bell", "Activity"]];
  const MAX_LEGS = 3;

  const F = { posts: [], more: false, next: 0, paged: "offset", me: null, signedIn: false, unseen: 0,
              rail: null, railMetric: "win", railDays: "30", search: null, profile: null, follows: null,
              post: null, page: null, leaders: null, metric: "win", days: "30",
              comp: { text: "", mode: "", legs: [], sport: "nfl", q: "", results: null, open: false,
                      poll: ["", ""], link: "", talkSport: "" } };
  const ACCT = { el: null, tab: "posts", edit: false, prof: null, posts: [], more: false, next: 0 };

  // ── drawn marks ───────────────────────────────────────────────────────────
  // The site's own icon() covers most of this page; these are the few it
  // has no reason to carry for anybody who never opens Social.
  const P = {
    edit: '<path d="M11.2 2.3l2.5 2.5-7.9 7.9-3.3.8.8-3.3z"/><path d="M9.8 3.7l2.5 2.5"/>',
    home: '<path d="M2.5 7.2L8 2.8l5.5 4.4"/><path d="M4 6.2v7.3h3V10h2v3.5h3V6.2"/>',
    userplus: '<circle cx="6.2" cy="5.4" r="2.6"/><path d="M1.6 13.6c.5-2.5 2.3-3.9 4.6-3.9s4.1 1.4 4.6 3.9"/><path d="M12.6 4v4M10.6 6h4"/>',
    doc: '<path d="M4 1.8h5.3l2.9 2.9v9.5H4z"/><path d="M9.2 1.8v3h3"/><path d="M6 8.2h4.2M6 10.8h4.2"/>',
    trend: '<path d="M1.8 11.8l4.1-4.1 2.6 2.6 5.6-5.6"/><path d="M10.4 4.7h3.7v3.7"/>',
    poll: '<path d="M3 13.5v-5M8 13.5V3M13 13.5V6"/>',
    link: '<path d="M6.8 9.2a2.6 2.6 0 003.7 0l2.4-2.4a2.6 2.6 0 00-3.7-3.7l-.9.9"/><path d="M9.2 6.8a2.6 2.6 0 00-3.7 0L3.1 9.2a2.6 2.6 0 003.7 3.7l.9-.9"/>',
    slip: '<rect x="2.5" y="2" width="11" height="12" rx="1.6"/><path d="M5 5.5h6M5 8h6M5 10.5h3.5"/>',
    up: '<path d="M8 13.5V3M3.8 7.2L8 3l4.2 4.2"/>',
    fire: '<path d="M8 14.2c2.8 0 4.6-1.9 4.6-4.4 0-2.9-2.4-4.3-3.1-7.6-1.6 1.2-2.4 2.6-2.5 4.2-.7-.6-1.1-1.4-1.2-2.4-1.4 1.4-2.4 3.4-2.4 5.8 0 2.5 1.8 4.4 4.6 4.4z"/>',
    soccer: '<circle cx="8" cy="8" r="6.2"/><path d="M8 5.2l2.4 1.7-.9 2.8h-3l-.9-2.8z"/><path d="M8 5.2V1.9M10.4 6.9l3.1-1M9.5 9.7l1.9 2.7M6.5 9.7l-1.9 2.7M5.6 6.9l-3.1-1"/>',
    x: '<path d="M4 4l8 8M12 4l-8 8"/>',
    plus: '<path d="M8 3v10M3 8h10"/>',
    chevr: '<path d="M6 3.5L10.5 8 6 12.5"/>',
    back: '<path d="M10 3.5L5.5 8l4.5 4.5"/>',
    pin: '<path d="M8 14.5s4.5-4.2 4.5-8a4.5 4.5 0 10-9 0c0 3.8 4.5 8 4.5 8z"/><circle cx="8" cy="6.5" r="1.6"/>',
    cal: '<rect x="2.2" y="3.2" width="11.6" height="10.6" rx="1.6"/><path d="M2.2 6.6h11.6M5.4 1.8v2.6M10.6 1.8v2.6"/>',
    gear: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.6v1.8M8 12.6v1.8M1.6 8h1.8M12.6 8h1.8M3.5 3.5l1.3 1.3M11.2 11.2l1.3 1.3M3.5 12.5l1.3-1.3M11.2 4.8l1.3-1.3"/>',
    // The feed's own marks (2026-10-06), moved out of app.js's set on
    // 2026-10-07 — nothing outside Social draws them, so a first visit
    // need not carry them: a whale's tail for Tail (Ethan: "make it a
    // whale's tail as the button"), a heart, a speech bubble, a flag, dots.
    whale: '<path d="M8 10.2C6.3 8.3 3.6 8.4.9 5.6c2.9-.2 5.4.1 7.1 2.2 1.7-2.1 4.2-2.4 7.1-2.2-2.7 2.8-5.4 2.7-7.1 4.6z"/>'
           + '<path d="M8 10.2c.2 1.9-.4 3.4-1.7 4.6"/>',
    heart: '<path d="M8 13.5S2.2 10 2.2 6.2A2.9 2.9 0 018 4.6a2.9 2.9 0 015.8 1.6C13.8 10 8 13.5 8 13.5z"/>',
    chat: '<path d="M2.5 3.5h11v7.5H7l-3 2.5V11H2.5z"/>',
    flag: '<path d="M3.5 14V2.5M3.5 3h8l-1.6 2.7 1.6 2.8h-8"/>',
    dots: '<path d="M3.5 8h.01M8 8h.01M12.5 8h.01" stroke-width="2.6"/>',
    share: '<path d="M8 10V2.5M5 5.2L8 2.3l3 2.9"/><path d="M3.5 8.5v4.5h9V8.5"/>',
    bell: '<path d="M4 11.5V7a4 4 0 018 0v4.5l1.2 1.3H2.8z"/><path d="M6.7 14a1.4 1.4 0 002.6 0"/>',
  };
  const svg = (d, size, cls) => `<svg class="ic${cls ? ` ${cls}` : ""}" viewBox="0 0 16 16" width="${size}" height="${size}" fill="none"
    stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${d}</svg>`;
  const ico = (name, size = 16) => (P[name] ? svg(P[name], size) : icon(name, size));
  const SPORT_ICON = { nfl: "shield", cfb: "football", mlb: "baseball", nba: "basketball", wnba: "basketball",
                       nhl: "hockey", ufc: "octagon", soccer: "soccer" };
  const sportIcon = (k, size = 18) => ico(SPORT_ICON[k] || "dot", size);

  const VERIFIED = `<svg class="fd-ver" viewBox="0 0 16 16" width="15" height="15" role="img" aria-label="Verified">
    <path fill="currentColor" d="M8 .9l1.9 1.4 2.3-.1.7 2.2 1.9 1.3-.8 2.2.8 2.2-1.9 1.3-.7 2.2-2.3-.1L8 15.1l-1.9-1.4-2.3.1-.7-2.2-1.9-1.3.8-2.2-.8-2.2 1.9-1.3.7-2.2 2.3.1z"/>
    <path d="M5.3 8.2l1.8 1.8 3.6-3.8" fill="none" stroke="var(--brand-ink)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

  // ── small helpers ─────────────────────────────────────────────────────────
  function strong() {
    try { return localStorage.getItem(STRONG_KEY) === "1"; } catch (e) { return false; }
  }

  function ago(ts) {
    const s = Math.max(0, Date.now() / 1000 - Number(ts || 0));
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
    return new Date(Number(ts) * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  const since = (ts) => new Date(Number(ts || 0) * 1000).toLocaleDateString(undefined, { month: "long", year: "numeric" });

  function big(n) {
    const v = Number(n || 0);
    if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M`;
    if (v >= 1e4) return `${(v / 1e3).toFixed(0)}K`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return String(v);
  }

  function units(u) {
    if (u == null) return "—";
    const n = Number(u);
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}u`;
  }

  const px = (o) => (o == null || o === "" ? "" : trueMinus(oddsTxt(o)));

  async function api(path, body) {
    const q = !body && strong() ? `${path.includes("?") ? "&" : "?"}strong=1` : "";
    try {
      const r = await fetch(`/api/feed/${path}${q}`, body
        ? { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
        : { credentials: "same-origin", cache: "no-store" });
      return { ok: r.ok, status: r.status, out: await r.json().catch(() => ({})) };
    } catch (e) {
      return { ok: false, status: 0, out: { error: "Could not reach the server." } };
    }
  }

  const go = (r) => { location.hash = r ? `#feed/${r}` : "#feed"; };
  const route = () => (location.hash.startsWith("#feed/") ? decodeURIComponent(location.hash.slice(6)) : "");
  const host = () => document.getElementById("view-feed");
  const inAccount = () => typeof state !== "undefined" && state.view === "account";
  const isMe = (h) => !!(F.me && h && String(h).toLowerCase() === F.me.handle.toLowerCase());
  const profHref = (h) => (isMe(h) ? "#account" : `#feed/u/${encodeURIComponent(h || "")}`);

  function needProfile(what) {
    if (!F.signedIn) { tfToast(`Sign in (free) to ${what}.`); switchView("account", true); return true; }
    if (!F.me) { tfToast("Make your profile first — it’s the name you post under."); switchView("account", true); return true; }
    return false;
  }

  /* Text a person wrote: escaped FIRST, then @handles and #tags become
     links — so nothing the writer typed is ever markup. */
  function rich(s) {
    return escapeHtml(String(s || ""))
      .replace(/(^|[^A-Za-z0-9_])@([A-Za-z0-9_]{3,20})/g,
        (m, pre, h) => `${pre}<a class="fd-mention" href="${profHref(h)}">@${h}</a>`)
      .replace(/(^|[^A-Za-z0-9_#&;])#([A-Za-z][A-Za-z0-9_]{1,29})/g,
        (m, pre, t) => `${pre}<a class="fd-hash" href="#feed/tag/${encodeURIComponent(t)}">#${t}</a>`);
  }

  function initials(p) {
    const src = String((p && (p.name || p.handle)) || "?").trim();
    const parts = src.split(/[\s_]+/).filter(Boolean);
    return ((parts[0] || "?")[0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
  }

  /* Initials on the profile's own colour; the site's account wears the
     site's mark (server: verified AND a "qellys" name only the owner's
     claim hands out). */
  function avatar(p, size) {
    const sz = size || "md";
    if (p && p.official) {
      return `<span class="fd-av fd-av-${sz} fd-av-site" aria-hidden="true"><img src="logo-qb.png" alt="" decoding="async"></span>`;
    }
    const c = Math.abs(Number((p && p.color) || 0)) % 8;
    return `<span class="fd-av fd-av-${sz} fd-c${c}" aria-hidden="true">${escapeHtml(initials(p))}</span>`;
  }

  const displayName = (p) => escapeHtml((p && (p.name || p.handle)) || "someone");
  const badge = (p) => (p && p.verified ? VERIFIED : "");

  function teamMap(sport) {
    const maps = { nfl: typeof TEAMS !== "undefined" ? TEAMS : null,
                   mlb: typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : null,
                   nba: typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : null,
                   wnba: typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : null,
                   nhl: typeof NHL_TEAMS !== "undefined" ? NHL_TEAMS : null };
    return maps[sport] || {};
  }

  function teamLogo(abbr, sport, size) {
    try {
      if (!abbr) return leagueMark(sport, size);
      return teamMark(abbr, size, teamMap(sport), sport);
    } catch (e) { return ""; }
  }

  function legLogo(l, sport, size) {
    const m = String(l.market || "").toLowerCase();
    if (l.kind === "game" && (m === "total" || !l.team)) return teamLogo("", sport, size);
    return teamLogo(l.team, sport, size);
  }

  function sportPill(s) {
    if (!s || s === "all" || !SPORT_NAME[s]) return "";
    return `<a class="fd-sport fd-sp-${escapeAttr(s)}" href="#feed/s/${escapeAttr(s)}">${SPORT_NAME[s]}</a>`;
  }

  // A leg in the slip's own words: OVER 5.5 RECEPTIONS, ANYTIME TOUCHDOWN.
  function legLine(l) {
    if (l.kind === "game") return `${l.label || ""}${l.market_label ? ` · ${l.market_label}` : ""}`;
    const mk = String(l.market || "").toLowerCase();
    const side = String(l.side || "").toUpperCase();
    if (mk.includes("anytime") || side === "YES") return `${side === "NO" ? "No " : ""}${l.market_label || "Anytime"}`;
    const line = l.line == null || l.line === "" ? "" : ` ${l.line}`;
    return `${side === "OVER" ? "Over" : side === "UNDER" ? "Under" : side}${line} ${l.market_label || ""}`.trim();
  }

  // The rail's short form: "Jahmyr Gibbs ATD", "Luka Doncic O 28.5 pts".
  const SHORT = { anytime_td: "ATD", player_anytime_td: "ATD", rec: "rec", receptions: "rec", rec_yds: "rec yds",
                  rush_yds: "rush yds", pass_yds: "pass yds", pass_tds: "pass TD", rush_att: "carries",
                  pass_att: "att", pass_comp: "comp", interceptions: "INT", points: "pts", rebounds: "reb",
                  assists: "ast", threes: "3PM", pra: "PRA", hits: "hits", total_bases: "TB", home_runs: "HR",
                  strikeouts: "K", rbis: "RBI", runs: "runs", goals: "goals", shots: "SOG", saves: "saves" };
  function shortLeg(l) {
    if (l.locked) return `${l.player || l.matchup || "Members’ pick"}`;
    if (l.kind === "game") return l.label || l.matchup || "";
    const mk = String(l.market || "").toLowerCase();
    const short = SHORT[mk] || String(l.market_label || mk).toLowerCase();
    const side = String(l.side || "").toUpperCase();
    if (short === "ATD" || side === "YES") return `${l.player} ${side === "NO" ? "No " : ""}${short}`;
    return `${l.player} ${side === "OVER" ? "O" : side === "UNDER" ? "U" : side} ${l.line ?? ""} ${short}`.replace(/\s+/g, " ").trim();
  }

  // ── the frame: nav, banner, main column, rail ────────────────────────────
  function navInner(active) {
    const row = ([k, href, ic, label]) => `<a class="fd-navi${active === k ? " on" : ""}" href="${href}"${
      active === k ? ' aria-current="page"' : ""}>${ico(ic, 18)}<span>${label}</span>${
      k === "activity" && F.unseen ? `<b class="fd-badge">${F.unseen > 99 ? "99+" : F.unseen}</b>` : ""}</a>`;
    return `<button class="fd-postbtn" data-fd="compose" type="button">${ico("edit", 18)}<span>Post</span></button>
      <div class="fd-navlist">${NAV.map(row).join("")}</div>
      <div class="fd-navh">Sports</div>
      <div class="fd-navlist">${SPORTS.map(([k, t]) => `<a class="fd-navi${active === `s:${k}` ? " on" : ""}" href="#feed/s/${k}">${
        sportIcon(k)}<span>${t}</span></a>`).join("")}</div>`;
  }

  // The same seven doors on a phone or a tablet, where the nav column is not.
  function tabsHTML(active) {
    return `<nav class="fd-tabs" aria-label="Social">${NAV.map(([k, href, ic, label]) => `<a class="fd-tab${
      active === k ? " on" : ""}" href="${href}">${ico(ic, 15)}<span>${label}</span>${
      k === "activity" && F.unseen ? `<b class="fd-badge">${F.unseen > 99 ? "99+" : F.unseen}</b>` : ""}</a>`).join("")}</nav>`;
  }

  function heroInner() {
    // Ethan's own backdrop (2026-10-07: "the render for the backdrop photo
    // I circled"): the crown and the wordmark are in the art, so nothing is
    // drawn over them. Not the page render's athletes — real people's faces.
    // The tagline says sweat, not win: the one promise this site never
    // prints is a profit.
    return `<img class="fd-hero-art" src="img/social/banner.webp" srcset="img/social/banner@900.webp 900w, img/social/banner.webp 1800w"
        sizes="(min-width: 1200px) 980px, 100vw" alt="Qellys Book" decoding="async">
      <div class="fd-hero-in"><p class="fd-hero-tag">Post your plays. Talk sports. Sweat together.</p></div>`;
  }

  function ensureFrame(el) {
    let wrap = el.querySelector(":scope > .fd-wrap");
    if (wrap) return wrap;
    el.innerHTML = `<div class="fd-wrap"><div class="fd-page">
      <nav class="fd-nav" id="fd-nav" aria-label="Social"></nav>
      <header class="fd-hero" id="fd-hero">${heroInner()}</header>
      <div class="fd-main" id="fd-main"></div>
      <aside class="fd-rail" id="fd-rail" aria-label="Trending and top bettors"></aside></div></div>`;
    return el.querySelector(":scope > .fd-wrap");
  }

  let _drawSeq = 0;
  function paint(seq, active, mainHTML, opts) {
    if (seq !== _drawSeq) return;
    const el = host();
    if (!el) return;
    const wrap = ensureFrame(el);
    wrap.querySelector(".fd-page").classList.toggle("no-hero", !(opts && opts.hero));
    document.getElementById("fd-nav").innerHTML = navInner(active);
    document.getElementById("fd-main").innerHTML = tabsHTML(active) + mainHTML;
    paintRail();
    armMore();
  }

  function paintRail() {
    const el = document.getElementById("fd-rail");
    if (el) el.innerHTML = railHTML();
  }

  // ── the composer ──────────────────────────────────────────────────────────
  function composerHTML() {
    const c = F.comp;
    const ph = "Share your parlay, pick or take with the community…";
    if (!F.signedIn || !F.me) {
      const why = !F.signedIn ? "Sign in (free) to post" : "Make your profile to post";
      return `<section class="fd-card fd-comp locked-out">
        <div class="fd-comp-row">${avatar(F.me || { handle: "?", color: 7 }, "md")}
          <a class="fd-comp-fake" href="#account">${ph}</a></div>
        <div class="fd-comp-bar">${toolsHTML(true)}<a class="fd-send" href="#account">${ico("up", 15)} ${why}</a></div>
      </section>`;
    }
    const parlay = c.mode === "parlay";
    return `<section class="fd-card fd-comp${c.open || c.mode ? " open" : ""}" id="fd-comp">
      <div class="fd-comp-row"><a href="#account" aria-label="Your profile">${avatar(F.me, "md")}</a>
        <textarea class="fd-comp-in" id="fd-comp-text" rows="${c.open || c.mode ? 3 : 1}" maxlength="${parlay ? 280 : 2000}"
          placeholder="${parlay ? "Say something about it (optional) — #tags and @handles work" : ph}"
          aria-label="Write a post">${escapeHtml(c.text)}</textarea></div>
      ${parlay ? pickerHTML() : c.mode === "poll" ? pollEditHTML() : c.mode === "link" ? linkEditHTML() : ""}
      <div class="fd-comp-bar">${toolsHTML(false)}
        ${parlay ? "" : `<select class="fd-comp-sport" id="fd-comp-sport" aria-label="Sport">
          <option value="">Any sport</option>${SPORTS.map(([k, t]) => `<option value="${k}"${c.talkSport === k ? " selected" : ""}>${t}</option>`).join("")}</select>`}
        <button class="fd-send" data-fd="send" type="button">${ico("up", 15)} Post</button></div>
    </section>`;
  }

  function toolsHTML(off) {
    const m = F.comp.mode;
    const t = (k, ic, label) => off
      ? `<a class="fd-tool" href="#account">${ico(ic, 17)}<span>${label}</span></a>`
      : `<button class="fd-tool${m === k ? " on" : ""}" data-fd="mode" data-v="${k}" type="button" aria-pressed="${m === k}">${ico(ic, 17)}<span>${label}</span></button>`;
    return `<div class="fd-tools">${t("parlay", "slip", "Parlay")}${t("poll", "poll", "Poll")}${t("link", "link", "Link")}</div>`;
  }

  function pickerHTML() {
    const c = F.comp;
    const chosen = c.legs.map((l, i) => `<div class="fd-pl">${legLogo(l, c.sport, 26)}
      <span class="fd-pl-t"><b>${escapeHtml(l.kind === "game" ? l.matchup || l.label : l.player)}</b><span>${escapeHtml(legLine(l))}</span></span>
      <span class="fd-pl-px">${escapeHtml(px(l.odds))}</span>
      <button class="fd-x" data-fd="leg-del" data-i="${i}" type="button" aria-label="Remove leg">${ico("x", 14)}</button></div>`).join("");
    const res = c.results;
    const rows = !res ? `<p class="fd-fine">Loading today’s board…</p>`
      : !res.open ? `<p class="fd-fine">The ${escapeHtml(SPORT_NAME[c.sport] || "")} board has nothing on it right now.</p>`
      : !res.legs.length ? `<p class="fd-fine">Nothing on today’s board matches that.</p>`
      : res.legs.map((l, i) => {
        const have = c.legs.some((x) => legKey(x) === legKey(l));
        return `<button class="fd-pr${have ? " on" : ""}" data-fd="leg-add" data-i="${i}" type="button"${have ? " disabled" : ""}>
          ${legLogo(l, c.sport, 26)}<span class="fd-pl-t"><b>${escapeHtml(l.kind === "game" ? l.matchup || l.label : l.player)}</b>
          <span>${escapeHtml(legLine(l))}</span></span><span class="fd-pl-px">${escapeHtml(px(l.odds))}</span>
          <span class="fd-pr-add">${have ? ico("check", 14) : ico("plus", 14)}</span></button>`;
      }).join("");
    return `<div class="fd-pick">
      <div class="fd-pick-top"><div class="fd-seg" role="tablist" aria-label="Board">${BOARD_SPORTS.map((k) =>
        `<button class="${c.sport === k ? "on" : ""}" data-fd="pick-sport" data-v="${k}" type="button">${SPORT_NAME[k]}</button>`).join("")}</div>
        <input class="fd-input fd-pick-q" id="fd-pick-q" maxlength="60" value="${escapeAttr(c.q)}"
          placeholder="Search today’s board — player, team or game" aria-label="Search today’s board"></div>
      ${chosen ? `<div class="fd-pick-legs"><div class="fd-pick-h">Your ${c.legs.length === 1 ? "pick" : `${c.legs.length}-leg parlay`}</div>${chosen}</div>` : ""}
      <div class="fd-pick-res">${rows}</div>
      <p class="fd-fine">Up to ${MAX_LEGS} legs from today’s board. They lock at kickoff and grade themselves on your profile.</p>
    </div>`;
  }

  function pollEditHTML() {
    const o = F.comp.poll;
    return `<div class="fd-polled">${o.map((v, i) => `<div class="fd-polled-row">
        <input class="fd-input" data-poll="${i}" maxlength="60" value="${escapeAttr(v)}" placeholder="Option ${i + 1}" aria-label="Option ${i + 1}">
        ${o.length > 2 ? `<button class="fd-x" data-fd="poll-del" data-i="${i}" type="button" aria-label="Remove option">${ico("x", 14)}</button>` : ""}</div>`).join("")}
      ${o.length < 4 ? `<button class="fd-addopt" data-fd="poll-add" type="button">${ico("plus", 14)} Add option</button>` : ""}
      <p class="fd-fine">One vote each, final once cast. Closes in three days.</p></div>`;
  }

  function linkEditHTML() {
    return `<div class="fd-linked"><input class="fd-input" id="fd-comp-link" maxlength="300" value="${escapeAttr(F.comp.link)}"
        placeholder="https://" aria-label="Link" inputmode="url">
      <p class="fd-fine">One https link per post. New accounts can post links after their first day.</p></div>`;
  }

  const legKey = (l) => (l.gid ? `g:${l.gid}` : `p:${l.player}|${l.market}|${l.side}|${l.line}`);

  async function loadLegs() {
    const c = F.comp;
    const want = `${c.sport}|${c.q}`;
    c._want = want;
    const r = await api(`legs?sport=${encodeURIComponent(c.sport)}&q=${encodeURIComponent(c.q)}`);
    if (c._want !== want) return;
    c.results = r.ok ? r.out : { legs: [], open: false };
    const box = document.querySelector("#fd-comp .fd-pick-res");
    if (box) {
      const keep = document.getElementById("fd-pick-q");
      const had = keep && document.activeElement === keep;
      redrawComposer();
      if (had) { const q = document.getElementById("fd-pick-q"); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }
    }
  }

  function focusComposer() {
    const ta = document.getElementById("fd-comp-text");
    if (!ta) return;
    ta.focus({ preventScroll: true });
    ta.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function redrawComposer() {
    const old = document.getElementById("fd-comp");
    if (!old) return;
    const t = document.getElementById("fd-comp-text");
    if (t) F.comp.text = t.value;
    old.outerHTML = composerHTML();
  }

  async function send(btn) {
    const c = F.comp;
    const t = document.getElementById("fd-comp-text");
    c.text = t ? t.value : c.text;
    const sp = document.getElementById("fd-comp-sport");
    if (sp) c.talkSport = sp.value;
    let res;
    btn.disabled = true;
    if (c.mode === "parlay") {
      if (!c.legs.length) { btn.disabled = false; tfToast("Add a leg from the board first."); return; }
      res = await api("post", { sport: c.sport, caption: c.text, legs: c.legs.map((l) => (l.gid ? { gid: l.gid }
        : { player: l.player, market: l.market, side: l.side, line: l.line })) });
    } else {
      document.querySelectorAll("[data-poll]").forEach((i) => { c.poll[Number(i.dataset.poll)] = i.value; });
      const li = document.getElementById("fd-comp-link");
      if (li) c.link = li.value;
      res = await api("talk", { sport: c.talkSport, title: "", body: c.text,
        poll: c.mode === "poll" ? c.poll.filter((o) => o.trim()) : null,
        link: c.mode === "link" ? c.link.trim() : "" });
    }
    btn.disabled = false;
    if (res.out && res.out.need_handle) { tfToast(res.out.error); switchView("account", true); return; }
    if (!res.ok) { tfToast((res.out && res.out.error) || "That did not post."); return; }
    tfToast(res.out.already ? "Already on the feed." : "Posted.");
    F.comp = { text: "", mode: "", legs: [], sport: c.sport, q: "", results: null, open: false,
               poll: ["", ""], link: "", talkSport: c.talkSport };
    F.posts = []; F.rail = null;
    go(`post/${res.out.id}`);
  }

  // ── a post ────────────────────────────────────────────────────────────────
  function resultPill(p) {
    if (p.kind === "text" || !p.result || p.result === "pending") return "";
    const word = { won: "Won", lost: "Lost", push: "Push", nograde: "No grade" }[p.result] || p.result;
    const u = (p.result === "won" || p.result === "lost") && p.units != null ? ` ${units(p.units)}` : "";
    return `<span class="fd-res fd-res-${escapeAttr(p.result)}">${word}${u}</span>`;
  }

  function legMark(l) {
    if (l.result === "won") return `<span class="fd-lr won" title="Won">${icon("check", 12)}</span>`;
    if (l.result === "lost") return `<span class="fd-lr lost" title="Lost">${icon("cross", 12)}</span>`;
    if (l.result === "push" || l.result === "void") return `<span class="fd-lr push" title="${l.result === "void" ? "Void" : "Push"}">${icon("dash", 12)}</span>`;
    return "";
  }

  function legHTML(l, sport) {
    if (l.locked) {
      return `<div class="fd-leg locked">${legLogo(l, sport, 34)}<div class="fd-leg-t"><b>${escapeHtml(l.player || l.matchup || "")}</b>
        <span>${escapeHtml(l.market_label || "")}</span></div><span class="fd-leg-lock">${icon("lock", 12)} Members</span></div>`;
    }
    const name = l.kind === "game" ? (l.matchup || l.label || "") : (l.player || "");
    return `<div class="fd-leg${l.result ? ` r-${escapeAttr(l.result)}` : ""}">${legLogo(l, sport, 34)}
      <div class="fd-leg-t"><b>${escapeHtml(name)}</b><span>${escapeHtml(legLine(l))}</span></div>
      <span class="fd-leg-px">${legMark(l)}${escapeHtml(px(l.odds))}</span></div>`;
  }

  function slipHTML(p, full) {
    const n = (p.legs || []).length;
    const price = n > 1 ? (p.combined != null ? px(p.combined) : "") : (p.legs[0] && p.legs[0].odds != null ? px(p.legs[0].odds) : "");
    const inner = `<div class="fd-slip-h"><b>${n === 1 ? "Single" : `${n} Leg Parlay`}</b>${price
      ? `<span class="fd-slip-px">${escapeHtml(price)}</span>` : p.locked ? `<span class="fd-slip-px lock">${icon("lock", 13)}</span>` : ""}</div>
      ${(p.legs || []).map((l) => legHTML(l, p.sport)).join("")}`;
    return full ? `<div class="fd-slip">${inner}</div>`
      : `<a class="fd-slip" href="#feed/post/${p.id}" aria-label="Open this ${n === 1 ? "pick" : "parlay"}">${inner}</a>`;
  }

  function pollHTML(p) {
    const v = p.poll;
    const voted = v.mine != null || v.closed || p.mine;
    const rows = v.options.map((o, i) => {
      const n = v.counts[i] || 0;
      const pc = v.total ? Math.round((n / v.total) * 100) : 0;
      return voted
        ? `<div class="fd-pollrow${v.mine === i ? " mine" : ""}"><span class="fd-pollbar" style="width:${pc}%"></span>
            <span class="fd-pollt">${escapeHtml(o)}${v.mine === i ? ` ${icon("check", 12)}` : ""}</span><b>${pc}%</b></div>`
        : `<button class="fd-pollbtn" data-fd="vote" data-id="${p.id}" data-v="${i}" type="button">${escapeHtml(o)}</button>`;
    }).join("");
    const left = Math.max(0, v.closes_at - Date.now() / 1000);
    const when = v.closed ? "Final" : left > 86400 ? `${Math.ceil(left / 86400)} days left` : `${Math.max(1, Math.ceil(left / 3600))}h left`;
    return `<div class="fd-poll">${rows}<div class="fd-pollmeta">${v.total} vote${v.total === 1 ? "" : "s"} · ${when}</div></div>`;
  }

  function linkHTML(p) {
    return `<a class="fd-linkcard" href="${safeHref(p.link)}" target="_blank" rel="noopener noreferrer nofollow ugc">
      ${ico("link", 16)}<span class="fd-linkcard-t"><b>${escapeHtml(p.domain || "Link")}</b><span>${escapeHtml(p.link)}</span></span>${ico("chevr", 14)}</a>`;
  }

  function postHTML(p, full) {
    const open = `#feed/post/${p.id}`;
    const words = p.kind === "text"
      ? `${p.title ? `<a class="fd-title" href="${open}">${rich(p.title)}</a>` : ""}${p.body ? `<p class="fd-text${full ? "" : " clamp"}">${rich(p.body)}</p>` : ""}`
      : (p.caption ? `<p class="fd-text">${rich(p.caption)}</p>` : "");
    const tail = p.kind === "text" ? ""
      : p.closed ? `<span class="fd-tailed" title="Tail closes when the games begin">${ico("whale", 16)} ${p.tails} tailed</span>`
      : `<button class="fd-tail${p.tailed ? " on" : ""}${p.locked ? " locked" : ""}" data-fd="tail" data-id="${p.id}" type="button"
          title="${p.locked ? "Members can tail this one" : "Open this parlay at your book"}">${ico("whale", 17)}<b>Tail</b>${
          p.tails ? `<span class="fd-n">${big(p.tails)}</span>` : ""}</button>`;
    return `<article class="fd-card fd-post" data-post="${p.id}">
      <header class="fd-ph"><a class="fd-ph-av" href="${profHref(p.handle)}" aria-label="${escapeAttr(p.name || p.handle)}">${avatar(p, "md")}</a>
        <div class="fd-ph-t"><a class="fd-name" href="${profHref(p.handle)}">${displayName(p)}</a>${badge(p)}
          <span class="fd-ago">${ago(p.at)}${p.edited ? " · edited" : ""}</span></div>
        <div class="fd-ph-r">${resultPill(p)}${sportPill(p.sport)}
          <button class="fd-dots" data-fd="menu" data-id="${p.id}" type="button" aria-label="More" aria-haspopup="menu">${ico("dots", 18)}</button></div>
      </header>
      ${words}
      ${(p.legs || []).length ? slipHTML(p, full) : ""}
      ${p.poll ? pollHTML(p) : ""}
      ${p.link ? linkHTML(p) : ""}
      <footer class="fd-pf">
        <button class="fd-act fd-like${p.liked ? " on" : ""}" data-fd="like" data-id="${p.id}" type="button"
          aria-pressed="${p.liked ? "true" : "false"}" aria-label="Like">${ico("heart", 18)}<span>${big(p.likes)}</span></button>
        <a class="fd-act" href="${open}" aria-label="Comments">${ico("chat", 18)}<span>${big(p.comments)}</span></a>
        <button class="fd-act" data-fd="share" data-id="${p.id}" type="button" aria-label="Share">${ico("share", 18)}</button>
        ${tail}
      </footer>
      <div class="fd-slot"></div>
    </article>`;
  }

  function tailHTML(res) {
    const n = res.n_legs || 0;
    const fine = `<p class="fd-fine">Each tap opens that book’s bet slip in a new tab. One link carries every leg only
      where the book’s link takes them all (FanDuel’s does); elsewhere add the legs one by one and they stack on the
      same slip. Prices move — check before you place. 21+ · Gambling problem? 1-800-GAMBLER</p>`;
    const books = res.books || [];
    if (!books.length) {
      return `<div class="fd-tailbox"><p class="fd-fine">No book has handed us a bet-slip link for these legs yet —
        the legs above are everything you need to key it in.</p>${fine}</div>`;
    }
    const a = (url, inner, cls) => `<a class="${cls}" href="${safeHref(url)}" target="_blank"
      rel="noopener noreferrer nofollow">${inner}</a>`;
    const rows = books.map((b) => (b.combined
      ? a(b.combined, `<b>${escapeHtml(b.book)}</b><span>all ${n} legs · one slip</span>${ico("chevr", 14)}`, "fd-book one")
      : `<div class="fd-book"><b>${escapeHtml(b.book)}</b><span>${b.have} of ${n} leg${n === 1 ? "" : "s"}</span>
          <div class="fd-book-legs">${b.legs.map((c, i) => (c
            ? a(c.url, `Leg ${i + 1}${c.price != null ? ` · ${escapeHtml(american(c.price))}` : ""}`, "fd-chip")
            : `<span class="fd-chip off">Leg ${i + 1} not offered</span>`)).join("")}</div></div>`)).join("");
    return `<div class="fd-tailbox"><div class="fd-tailbox-h">${ico("whale", 16)} Tail it at</div>${rows}${fine}</div>`;
  }

  function menuHTML(p) {
    const items = [`<button data-fd="copy" data-id="${p.id}" type="button" role="menuitem">Copy link</button>`];
    if (p.mine) {
      if (p.editable) items.push(`<button data-fd="edit-post" data-id="${p.id}" type="button" role="menuitem">Edit</button>`);
      items.push(`<button class="danger" data-fd="del-post" data-id="${p.id}" type="button" role="menuitem">Delete</button>`);
    } else if (F.signedIn) {
      items.push(`<button data-fd="report-open" data-id="${p.id}" type="button" role="menuitem">${ico("flag", 13)} Report</button>`,
        `<button class="danger" data-fd="block" data-handle="${escapeAttr(p.handle)}" type="button" role="menuitem">Block @${escapeHtml(p.handle)}</button>`);
    }
    return `<div class="fd-menu" role="menu">${items.join("")}</div>`;
  }

  function reportHTML(kind, id) {
    return `<div class="fd-menu" role="menu"><div class="fd-menu-h">Why report this?</div>${REASONS.map(([k, t]) =>
      `<button data-fd="report" data-kind="${kind}" data-id="${id}" data-v="${k}" type="button" role="menuitem">${t}</button>`).join("")}</div>`;
  }

  function editHTML(p) {
    const v = p.kind === "text" ? p.body : p.caption;
    return `<div class="fd-editbox"><textarea class="fd-input fd-e" maxlength="${p.kind === "text" ? 2000 : 280}" rows="3"
        aria-label="Edit">${escapeHtml(v)}</textarea>
      <div class="fd-row-end"><button class="fd-btn ghost" data-fd="edit-cancel" data-id="${p.id}" type="button">Cancel</button>
        <button class="fd-btn" data-fd="save-post" data-id="${p.id}" type="button">Save</button></div>
      <p class="fd-fine">Words edit for 15 minutes after posting. Legs, polls and links never change.</p></div>`;
  }

  // ── comments ──────────────────────────────────────────────────────────────
  function commentHTML(c, postId, reply) {
    const acts = `<button class="fd-cact${c.liked ? " on" : ""}" data-fd="clike" data-id="${c.id}" type="button">${ico("heart", 13)}${c.likes ? ` ${c.likes}` : ""}</button>
      ${reply ? "" : `<button class="fd-cact" data-fd="reply" data-id="${c.id}" type="button">Reply</button>`}
      ${c.can_delete ? `<button class="fd-cact" data-fd="del-comment" data-id="${c.id}" type="button">Delete</button>`
        : F.signedIn ? `<button class="fd-cact" data-fd="creport" data-id="${c.id}" type="button">Report</button>` : ""}`;
    return `<div class="fd-com${reply ? " reply" : ""}" id="fd-com-${c.id}">
      <a href="${profHref(c.handle)}">${avatar(c, "sm")}</a>
      <div class="fd-com-b"><div class="fd-com-bubble"><div class="fd-com-h"><a href="${profHref(c.handle)}"><b>${displayName(c)}</b></a>
        <span class="fd-ago">${ago(c.at)}</span></div><p>${rich(c.body)}</p></div>
        <div class="fd-cacts">${acts}</div>
        <div class="fd-rslot" id="fd-rslot-${c.id}"></div>
        ${(c.replies || []).map((r) => commentHTML(r, postId, true)).join("")}</div></div>`;
  }

  function commentBoxHTML(postId, parent) {
    if (!F.signedIn) return `<p class="fd-fine"><a href="#account">Sign in</a> to join the conversation.</p>`;
    if (!F.me) return `<p class="fd-fine"><a href="#account">Make your profile</a> to comment.</p>`;
    const id = parent ? `fd-rc-${parent}` : `fd-cc-${postId}`;
    return `<div class="fd-cbox">${parent ? "" : avatar(F.me, "sm")}<textarea class="fd-input" id="${id}" maxlength="500" rows="1"
        placeholder="${parent ? "Write a reply" : "Add a comment — @handle to mention someone"}" aria-label="Comment"></textarea>
      <button class="fd-btn" data-fd="comment" data-id="${postId}"${parent ? ` data-parent="${parent}"` : ""} type="button">${parent ? "Reply" : "Post"}</button></div>`;
  }

  // ── the rail ──────────────────────────────────────────────────────────────
  function railHTML() {
    const r = F.rail || {};
    const loading = !F.rail;
    return `<form class="fd-search" data-fd-form="search" role="search">${icon("search", 15)}
        <input name="q" maxlength="40" placeholder="Search people, posts and #tags" aria-label="Search Social"
          value="${escapeAttr((F.search && F.search.q) || "")}"></form>
      ${trendCardHTML(r.trending, loading)}
      ${bettorsCardHTML(r.leaders, loading)}
      <section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${sportIcon("nba", 17)} Popular Sports</h3></div>
        <div class="fd-sports">${POPULAR.map((k) => `<a class="fd-sporttile" href="#feed/s/${k}"><span>${sportIcon(k, 22)}</span><b>${SPORT_NAME[k]}</b></a>`).join("")}</div></section>
      ${statsCardHTML(r.stats)}
      <a class="fd-card fd-discord" href="#discord"><span class="fd-discord-ic">${icon("discord", 26)}</span>
        <span class="fd-discord-t"><b>Join the Qellys Book Discord</b><span>Live picks, chat and more.</span></span>${ico("chevr", 16)}</a>`;
  }

  function trendRows(list, active, big2) {
    return list.map((t, i) => {
      const l = t.leg || {};
      const label = active >= 10 ? `${t.pct}% tailing` : `${t.people} of ${active} tailing`;
      return `<li><a class="fd-trend${big2 ? " big" : ""}" href="#feed/post/${t.post_id}" title="${t.people} of ${active} people on today’s posts have this leg — they posted it or tailed it">
        <span class="fd-rank">${i + 1}</span>${legLogo(l, t.sport, big2 ? 34 : 28)}
        <span class="fd-trend-t"><b>${escapeHtml(shortLeg(l))}${l.locked ? ` ${icon("lock", 11)}` : ""}</b><span>${label}${
          big2 ? ` · ${SPORT_NAME[t.sport] || ""}` : ""}</span></span>${big2 && l.odds != null ? `<span class="fd-trend-px">${escapeHtml(px(l.odds))}</span>` : ""}</a></li>`;
    }).join("");
  }

  function trendCardHTML(T, loading) {
    const list = (T && T.picks) || [];
    return `<section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${ico("fire", 17)} Trending Picks</h3><a href="#feed/trending">View All</a></div>
      ${loading ? `<p class="fd-fine">Loading…</p>` : list.length ? `<ol class="fd-trends">${trendRows(list, T.active)}</ol>`
        : `<p class="fd-fine">No open picks in the last two days. Post a parlay and it shows up here.</p>`}</section>`;
  }

  function bettorValue(p, metric) {
    if (metric === "win") return `${p.win}%`;
    if (metric === "units") return units(p.units);
    return big(p.followers);
  }

  function bettorsCardHTML(list, loading) {
    return `<section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${icon("trophy", 17)} Top Bettors</h3>
        <select class="fd-days" data-fd-sel="rail-days" aria-label="Window">${DAYS.map(([k, t]) =>
          `<option value="${k}"${F.railDays === k ? " selected" : ""}>${t}</option>`).join("")}</select></div>
      <div class="fd-seg wide" role="tablist" aria-label="Rank by">${METRICS.map(([k, t]) =>
        `<button class="${F.railMetric === k ? "on" : ""}" data-fd="rail-metric" data-v="${k}" type="button">${t}</button>`).join("")}</div>
      ${loading ? `<p class="fd-fine">Loading…</p>` : (list || []).length ? `<ol class="fd-bettors">${list.map((p, i) => `<li>
        <a href="${profHref(p.handle)}"><span class="fd-rank">${i + 1}</span>${avatar(p, "sm")}<span class="fd-bn">${displayName(p)}${badge(p)}</span>
        <b class="fd-bv${F.railMetric === "units" ? (p.units >= 0 ? " up" : " down") : ""}">${bettorValue(p, F.railMetric)}</b></a></li>`).join("")}</ol>`
        : `<p class="fd-fine">${F.railMetric === "followers" ? "No follows in this window yet."
          : "Nobody has five graded picks in this window yet — every post is graded automatically, so the board fills itself."}</p>`}
      <a class="fd-rc-more" href="#feed/leaders">Full leaderboard</a></section>`;
  }

  function statsCardHTML(s) {
    const st = s || {};
    return `<section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${icon("people", 17)} Community Stats</h3></div>
      <div class="fd-stats3"><div><b>${s ? big(st.members) : "—"}</b><span>Members</span></div>
        <div><b>${s ? big(st.posts) : "—"}</b><span>Posts</span></div>
        <div title="${st.win_rate == null ? `Shown once ten parlays are graded (${st.graded || 0} so far)` : `${st.graded} graded parlays`}">
          <b>${st.win_rate == null ? "—" : `${st.win_rate}%`}</b><span>Win rate<br>(graded picks)</span></div></div></section>`;
  }

  // ── pages ─────────────────────────────────────────────────────────────────
  function chipsHTML(cur) {
    const list = [["foryou", "For You", "#feed"], ["following", "Following", "#feed/following"],
                  ...SPORTS.map(([k, t]) => [k, t, `#feed/s/${k}`])];
    return `<nav class="fd-chips" aria-label="Filter">${list.map(([k, t, href]) =>
      `<a class="fd-chip${cur === k ? " on" : ""}" href="${href}"${cur === k ? ' aria-current="true"' : ""}>${t}</a>`).join("")}</nav>`;
  }

  // On a phone the rail is not there, so its first card rides along.
  function phoneTrendHTML() {
    const T = (F.rail || {}).trending;
    if (!T || !(T.picks || []).length) return "";
    return `<div class="fd-mtrend"><div class="fd-mtrend-h">${ico("fire", 15)} Trending Picks <a href="#feed/trending">View all</a></div>
      <div class="fd-mtrend-row">${T.picks.map((t) => `<a class="fd-mtrend-c" href="#feed/post/${t.post_id}">${legLogo(t.leg || {}, t.sport, 24)}
        <span><b>${escapeHtml(shortLeg(t.leg || {}))}</b><span>${T.active >= 10 ? `${t.pct}%` : `${t.people}`} tailing</span></span></a>`).join("")}</div></div>`;
  }

  function listHTML(posts, empty) {
    return posts.length ? posts.map((p) => postHTML(p)).join("") : `<div class="fd-card fd-empty">${empty}</div>`;
  }

  function moreHTML() {
    return F.more ? `<button class="fd-btn ghost fd-load" data-fd="load" type="button">More posts</button>` : "";
  }

  function headHTML(title, sub, back) {
    return `<div class="fd-head">${back ? `<button class="fd-back" data-fd="back" type="button" aria-label="Back">${ico("back", 18)}</button>` : ""}
      ${title || sub ? `<div>${title ? `<h2>${title}</h2>` : ""}${sub ? `<p>${sub}</p>` : ""}</div>` : ""}</div>`;
  }

  function feedPage(cur, title, empty) {
    return `${title || ""}${composerHTML()}${chipsHTML(cur)}${cur === "foryou" ? phoneTrendHTML() : ""}
      <div class="fd-list">${listHTML(F.posts, empty)}</div>${moreHTML()}`;
  }

  function searchResultsHTML() {
    const s = F.search;
    const people = (s.people || []).map((p) => `<a class="fd-person" href="${profHref(p.handle)}">${avatar(p, "sm")}
      <span><b>${displayName(p)}${badge(p)}</b><span>@${escapeHtml(p.handle)}</span></span></a>`).join("");
    return `<div class="fd-card fd-results"><div class="fd-row-between"><b>Results for “${escapeHtml(s.q)}”</b>
        <button class="fd-btn ghost" data-fd="clear-search" type="button">Clear</button></div>
      ${people ? `<div class="fd-people">${people}</div>` : ""}
      ${people || (s.posts || []).length ? "" : `<p class="fd-fine">Nothing matched.</p>`}</div>
      <div class="fd-list">${(s.posts || []).map((p) => postHTML(p)).join("")}</div>`;
  }

  function postPageHTML() {
    const p = F.post;
    if (!p) return `${headHTML("Post", "", true)}<div class="fd-card fd-empty">That post is gone.</div>`;
    return `${headHTML("Post", "", true)}${postHTML(p, true)}
      <section class="fd-card fd-thread"><h3>${p.comments} Comment${p.comments === 1 ? "" : "s"}</h3>
        ${commentBoxHTML(p.id)}
        ${(p.comment_list || []).map((c) => commentHTML(c, p.id)).join("") || `<p class="fd-fine">No comments yet — start it off.</p>`}
      </section>`;
  }

  /* THE ONE PROFILE HEADER. Everybody's profile wears it, and so does your
     own Account page (mine: true) — one identity, drawn one way. */
  function profileHeaderHTML(p, opts) {
    const o = opts || {};
    const rec = p.record || {};
    const r30 = p.record30 || {};
    const decided = (rec.w || 0) + (rec.l || 0);
    const win = decided ? `${Math.round((rec.w / decided) * 100)}%` : "—";
    const recTxt = rec.n ? `${rec.w}-${rec.l}${rec.p ? `-${rec.p}` : ""}` : "—";
    const tone = rec.units > 0 ? " up" : rec.units < 0 ? " down" : "";
    const [lg, abbr] = String(p.team || "").split(":");
    const btns = o.mine
      ? `<button class="fd-btn" data-fd="acct-edit" type="button">${ico("edit", 15)} Edit profile</button>
         <button class="fd-btn ghost" data-fd="share-profile" data-handle="${escapeAttr(p.handle)}" type="button">${ico("share", 15)} Share</button>`
      : F.signedIn ? `<button class="fd-btn${p.following ? " ghost" : ""}" data-fd="follow" data-handle="${escapeAttr(p.handle)}" type="button">${p.following ? "Following" : "Follow"}</button>
          ${p.friend ? `<a class="fd-btn ghost" href="#messages">Message</a>`
            : `<button class="fd-btn ghost" data-fd="friend" data-handle="${escapeAttr(p.handle)}" type="button">Add friend</button>`}
          <button class="fd-btn ghost icon" data-fd="pmenu" data-handle="${escapeAttr(p.handle)}" type="button" aria-label="More">${ico("dots", 16)}</button>`
      : `<a class="fd-btn" href="#account">Sign in to follow</a>`;
    const stat = (v, label, cls, act) => {
      const inner = `<b class="${cls || ""}">${v}</b><span>${label}</span>`;
      return act ? `<button class="fd-pstat" data-fd="${act}" data-handle="${escapeAttr(p.handle)}" type="button">${inner}</button>`
        : `<div class="fd-pstat">${inner}</div>`;
    };
    return `<section class="fd-card fd-prof">
      <div class="fd-prof-ban fd-c${(p.color || 0) % 8}"><img src="img/social/cover@900.webp" srcset="img/social/cover@900.webp 900w, img/social/cover.webp 1500w" sizes="(min-width: 1000px) 880px, 100vw" alt="" decoding="async"></div>
      <div class="fd-prof-body">
        <div class="fd-prof-top">${avatar(p, "xl")}<div class="fd-prof-btns">${btns}</div></div>
        <h2 class="fd-prof-name">${displayName(p)}${badge(p)}</h2>
        <p class="fd-prof-h">@${escapeHtml(p.handle)}${p.follows_you ? ` <span class="fd-tag">Follows you</span>` : ""}${
          p.streak ? ` <span class="fd-tag ${p.streak[0] === "W" ? "up" : "down"}">${escapeHtml(p.streak)} streak</span>` : ""}</p>
        ${p.bio ? `<p class="fd-prof-bio">${rich(p.bio)}</p>` : o.mine ? `<p class="fd-prof-bio dim">Add a bio — who you are, what you bet.</p>` : ""}
        <p class="fd-prof-meta">${abbr ? `<span>${teamLogo(abbr, lg, 18)}${escapeHtml(abbr)} · ${escapeHtml((lg || "").toUpperCase())}</span>` : ""}
          <span>${ico("cal", 14)} Joined ${escapeHtml(since(p.since))}</span></p>
        <div class="fd-pstats">${stat(recTxt, "Record")}${stat(units(rec.units), "Units", tone)}${stat(win, "Win %")}
          ${stat(big(p.followers), "Followers", "", "follows")}${stat(big(p.following_count), "Following", "", "following-list")}${stat(big(p.tails), "Tails")}</div>
        ${r30.n ? `<p class="fd-prof-30">Last 30 days <b>${r30.w}-${r30.l}${r30.p ? `-${r30.p}` : ""}</b> · ${units(r30.units)}${
          r30.roi != null ? ` · ${r30.roi > 0 ? "+" : ""}${r30.roi}% ROI` : ""}</p>` : ""}
        <p class="fd-fine">One unit a post at the posted price, graded from the same results as the Record page. Picks lock at kickoff — nobody can type in a result.</p>
      </div></section>`;
  }

  function followsHTML() {
    if (!F.follows) return "";
    return `<section class="fd-card fd-follows"><div class="fd-row-between"><b>${F.follows.which === "followers" ? "Followers" : "Following"}</b>
        <button class="fd-btn ghost" data-fd="close-follows" type="button">Close</button></div>
      ${(F.follows.people || []).map((q) => `<a class="fd-person" href="${profHref(q.handle)}">${avatar(q, "sm")}
        <span><b>${displayName(q)}${badge(q)}</b><span>@${escapeHtml(q.handle)}</span></span></a>`).join("") || `<p class="fd-fine">Nobody yet.</p>`}</section>`;
  }

  function profileTabs(tab, base) {
    return `<nav class="fd-ptabs" aria-label="Profile">${[["posts", "Posts"], ["picks", "Graded picks"]].map(([k, t]) =>
      `<a class="${tab === k ? "on" : ""}" href="${base}${k === "picks" ? "/picks" : ""}">${t}</a>`).join("")}</nav>`;
  }

  function profilePageHTML(tab) {
    const p = F.profile;
    if (!p) return `${headHTML("Profile", "", true)}<div class="fd-card fd-empty">Nobody has that handle.</div>`;
    const empty = tab === "picks" ? "No graded picks yet — results land here once their games are final." : "No posts yet.";
    return `${headHTML("", "", true)}${profileHeaderHTML(p, {})}${followsHTML()}
      ${profileTabs(tab, `#feed/u/${encodeURIComponent(p.handle)}`)}
      <div class="fd-list">${listHTML(F.posts, empty)}</div>${tab === "picks" ? "" : moreHTML()}`;
  }

  const NOTE_WORDS = {
    like: "liked your post", tail: "tailed your parlay", comment: "commented on your post",
    reply: "replied to your comment", mention: "mentioned you", follow: "started following you",
    comment_like: "liked your comment", won: "Your parlay won", lost: "Your parlay lost",
  };

  function activityHTML(items) {
    const rows = (items || []).map((n) => {
      const actor = n.handle ? `<b>${escapeHtml(n.name || n.handle)}</b> ` : "";
      const href = n.post_id ? `#feed/post/${n.post_id}` : n.handle ? profHref(n.handle) : "#feed";
      const mark = n.handle ? avatar(n, "sm") : `<span class="fd-av fd-av-sm fd-note-ic ${escapeAttr(n.kind)}">${icon(n.kind === "won" ? "check" : "cross", 13)}</span>`;
      return `<a class="fd-note${n.seen ? "" : " unseen"}" href="${href}">${mark}
        <span class="fd-note-t">${actor}${NOTE_WORDS[n.kind] || escapeHtml(n.kind)}${n.snippet ? `: <i>${escapeHtml(n.snippet)}</i>` : ""}
        <span class="fd-ago">${ago(n.at)}</span></span></a>`;
    }).join("");
    return `${headHTML("Activity", "Likes, tails, comments, follows and your graded parlays.")}
      <section class="fd-card fd-notes">${rows || `<p class="fd-fine">Nothing yet. Likes, comments, tails, new followers and your graded parlays show up here.</p>`}</section>`;
  }

  function leadersPageHTML(L) {
    const metric = F.metric;
    const followBtn = (p) => (F.signedIn && !isMe(p.handle)
      ? `<button class="fd-btn ghost sm" data-fd="follow" data-handle="${escapeAttr(p.handle)}" type="button">${p.following ? "Following" : "Follow"}</button>` : "");
    const top = ((L && L.top) || []).map((p, i) => `<div class="fd-lead"><span class="fd-rank${i < 3 ? ` top${i + 1}` : ""}">${i + 1}</span>
      <a class="fd-person" href="${profHref(p.handle)}">${avatar(p, "sm")}<span><b>${displayName(p)}${badge(p)}</b><span>@${escapeHtml(p.handle)}</span></span></a>
      ${metric === "followers" ? "" : `<span class="fd-lead-rec">${p.w}-${p.l}${p.p ? `-${p.p}` : ""}</span>`}
      <b class="fd-lead-v${metric === "units" ? (p.units >= 0 ? " up" : " down") : ""}">${bettorValue(p, metric)}</b>${followBtn(p)}</div>`).join("");
    const tailed = ((L && L.tailed) || []).map((p, i) => `<div class="fd-lead"><span class="fd-rank">${i + 1}</span>
      <a class="fd-person" href="${profHref(p.handle)}">${avatar(p, "sm")}<span><b>${displayName(p)}${badge(p)}</b><span>@${escapeHtml(p.handle)}</span></span></a>
      <b class="fd-lead-v">${p.tails} tail${p.tails === 1 ? "" : "s"}</b>${followBtn(p)}</div>`).join("");
    const what = metric === "win" ? "won ÷ decided, pushes left out" : metric === "units" ? "one unit a post at the posted price" : "new follows in the window";
    return `${headHTML("Top Bettors", `Ranked by ${METRICS.find((m) => m[0] === metric)[1]} — ${what}. Win % and Units need ${(L && L.min) || 5}+ graded picks.`)}
      <div class="fd-lbar"><div class="fd-seg wide" role="tablist" aria-label="Rank by">${METRICS.map(([k, t]) =>
        `<button class="${metric === k ? "on" : ""}" data-fd="lb-metric" data-v="${k}" type="button">${t}</button>`).join("")}</div>
        <div class="fd-seg" role="tablist" aria-label="Window">${DAYS.map(([k, t]) =>
          `<button class="${F.days === k ? "on" : ""}" data-fd="lb-days" data-v="${k}" type="button">${t}</button>`).join("")}</div></div>
      <section class="fd-card fd-leads">${top || `<p class="fd-fine">Nobody qualifies in this window yet.</p>`}</section>
      <section class="fd-card fd-leads"><h3>${ico("whale", 17)} Most tailed this week</h3>${tailed || `<p class="fd-fine">No tails this week yet.</p>`}</section>
      <p class="fd-fine">Graded automatically from the journal — nobody can type in a result.</p>`;
  }

  function trendingPageHTML(T) {
    const picks = (T && T.picks) || [];
    const tags = (T && T.tags) || [];
    return `${headHTML("Trending", "What the room is on right now: open picks from the last two days, counted by people, and this week’s tags.")}
      <section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${ico("fire", 17)} Trending Picks</h3></div>
        ${picks.length ? `<ol class="fd-trends">${trendRows(picks, T.active, true)}</ol>` : `<p class="fd-fine">No open picks in the last two days.</p>`}</section>
      ${tags.length ? `<section class="fd-card fd-rc"><div class="fd-rc-h"><h3>${icon("tag", 17)} Trending tags</h3><a href="#feed/tags">All tags</a></div>
        <div class="fd-tagcloud">${tags.map((t) => `<a class="fd-chip" href="#feed/tag/${encodeURIComponent(t.tag)}">#${escapeHtml(t.tag)} <small>${t.posts}</small></a>`).join("")}</div></section>` : ""}
      <h3 class="fd-sub">Hot right now</h3><div class="fd-list">${listHTML(F.posts, "Nothing hot yet.")}</div>${moreHTML()}`;
  }

  function tagsPageHTML(tags) {
    return `${headHTML("Tags", "Write #anything in a post and it lands here. The last 30 days, busiest first.")}
      <section class="fd-card fd-tagsl">${(tags || []).map((t, i) => `<a class="fd-tagrow" href="#feed/tag/${encodeURIComponent(t.tag)}">
        <span class="fd-rank">${i + 1}</span><b>#${escapeHtml(t.tag)}</b><span>${t.posts} post${t.posts === 1 ? "" : "s"}</span>${ico("chevr", 14)}</a>`).join("")
        || `<p class="fd-fine">No tags yet — put a #tag in your next post.</p>`}</section>`;
  }

  // ── loading ───────────────────────────────────────────────────────────────
  async function loadRail() {
    const r = await api(`rail?metric=${F.railMetric}&days=${F.railDays}`);
    if (r.ok) F.rail = r.out;
  }

  function takeList(o, append) {
    F.posts = append ? F.posts.concat(o.posts || []) : (o.posts || []);
    F.more = !!o.more;
    F.next = o.next || 0;
    F.paged = o.paged || "offset";
    if ("me" in o) F.me = o.me || null;
    if ("signed_in" in o) F.signedIn = !!o.signed_in;
    if ("unseen" in o) F.unseen = o.unseen || 0;
    syncBadge();
  }

  async function loadList(params, append) {
    const p = new URLSearchParams(params);
    if (append) p.set(F.paged === "before" ? "before" : "offset", String(F.next || 0));
    const r = await api(`list?${p}`);
    if (!r.ok) { tfToast(r.out.error || "The feed did not load."); return false; }
    takeList(r.out, append);
    return true;
  }

  async function ensureMe(force) {
    if (!force && F._meAt && Date.now() - F._meAt < 30000) return;
    const r = await api("me");
    if (r.ok) {
      F.me = r.out.me || null;
      F.signedIn = !!r.out.signed_in;
      F.unseen = r.out.unseen || 0;
      F._meAt = Date.now();
      syncBadge();
    }
  }

  function syncBadge() {
    const btn = document.querySelector('#sidebar [data-view="feed"]');
    if (!btn) return;
    let b = btn.querySelector(".sb-badge");
    if (!F.unseen) { if (b) b.hidden = true; return; }
    if (!b) { b = document.createElement("span"); b.className = "sb-badge"; btn.appendChild(b); }
    b.hidden = false;
    b.textContent = F.unseen > 99 ? "99+" : String(F.unseen);
  }

  /* The "More posts" button loads itself when it scrolls into view — the
     feed reads like every feed people know, and the button stays for
     keyboards and for anybody whose browser has no observer. */
  let _io = null;
  function armMore() {
    if (!("IntersectionObserver" in window)) return;
    if (_io) _io.disconnect();
    const b = document.querySelector("#fd-main .fd-load");
    if (!b) return;
    _io = new IntersectionObserver((ents) => {
      if (ents.some((e) => e.isIntersecting) && !b.disabled) { b.disabled = true; render(true); }
    }, { rootMargin: "400px" });
    _io.observe(b);
  }

  // ── drawing a route ───────────────────────────────────────────────────────
  async function render(append) {
    const el = host();
    if (!el) return;
    const seq = ++_drawSeq;
    if (window._feedWant) {
      const want = window._feedWant;
      window._feedWant = null;
      if (location.hash !== want) {
        try { history.replaceState(history.state, "", want); } catch (e) { /* file:// */ }
      }
    }
    const [kind, arg, sub] = route().split("/");
    if (kind === "edit") { window._acctEdit = true; switchView("account", true); return; }
    if (!el.querySelector(".fd-wrap")) paint(seq, "feed", `<div class="fd-card fd-empty">Loading…</div>`, { hero: true });
    const railP = F.rail ? null : loadRail();
    if (!kind || kind === "following" || kind === "mine" || kind === "s" || kind === "tag") {
      const params = { order: kind === "following" ? "following" : "hot" };
      let cur = "foryou", active = "feed", title = "", empty = "Nothing here yet — be the first to post.";
      if (kind === "following") {
        cur = "following"; active = "following";
        empty = F.signedIn ? "Nobody you follow has posted yet. Find people on Top Bettors or in search." : "Sign in to see posts from people you follow.";
      } else if (kind === "s" && SPORT_NAME[arg]) {
        params.sport = arg; cur = arg; active = `s:${arg}`;
        empty = `No ${SPORT_NAME[arg]} posts yet — be the first.`;
      } else if (kind === "tag" && arg) {
        params.tag = arg; cur = ""; active = "tags";
        title = headHTML(`#${escapeHtml(arg)}`, "Every post that carries this tag, hottest first.", true);
        empty = "No posts carry this tag right now.";
      } else if (kind === "mine") {
        await ensureMe();
        active = "mine"; cur = "";
        if (!F.me) {
          await railP;
          paint(seq, active, `${headHTML("My Posts", "")}<div class="fd-card fd-empty">${F.signedIn
            ? `<a href="#account">Make your profile</a> to start posting.` : `<a href="#account">Sign in</a> to see your posts.`}</div>`, { hero: false });
          return;
        }
        params.handle = F.me.handle; params.order = "new";
        title = headHTML("My Posts", `Everything you’ve posted, newest first. <a href="#account">Your profile</a> holds your record.`);
        empty = "You haven’t posted yet. Share a take or build a parlay above.";
      }
      // Search has its own page (#feed/search/…); a feed is never results.
      F.search = null;
      const okP = loadList(params, append);
      await Promise.all([okP, railP]);
      paint(seq, active, feedPage(cur, title, empty), { hero: !kind || kind === "following" || kind === "s" });
      if (F._focusComp && seq === _drawSeq) { F._focusComp = false; focusComposer(); }
      return;
    }
    await ensureMe();
    if (kind === "post") {
      const res = await api(`post?id=${encodeURIComponent(arg || "")}`);
      F.post = res.ok ? res.out.post : null;
      await railP;
      paint(seq, "feed", postPageHTML(), { hero: false });
      return;
    }
    if (kind === "u") {
      if (isMe(arg)) { switchView("account", true); return; }
      const tab = sub === "picks" || sub === "record" ? "picks" : "posts";
      const p = new URLSearchParams({ handle: arg || "", tab: tab === "picks" ? "record" : "posts" });
      if (append && F.next) p.set("before", String(F.next));
      const res = await api(`profile?${p}`);
      if (res.ok) {
        F.profile = res.out.profile;
        takeList(res.out, append);
      } else { F.profile = null; F.posts = []; F.more = false; }
      if (!append) F.follows = null;
      await railP;
      paint(seq, "", profilePageHTML(tab), { hero: false });
      return;
    }
    if (kind === "activity" || kind === "notifications") {
      if (!F.signedIn) {
        await railP;
        paint(seq, "activity", `${headHTML("Activity", "")}<div class="fd-card fd-empty"><a href="#account">Sign in</a> to see your activity.</div>`, { hero: false });
        return;
      }
      const res = await api("notifications");
      await railP;
      paint(seq, "activity", activityHTML(res.ok ? res.out.items : []), { hero: false });
      if (res.ok && res.out.unseen) { await api("seen", {}); F.unseen = 0; syncBadge(); }
      return;
    }
    if (kind === "leaders") {
      const res = await api(`leaders?metric=${F.metric}&days=${F.days}`);
      await railP;
      paint(seq, "leaders", leadersPageHTML(res.ok ? res.out : {}), { hero: false });
      return;
    }
    if (kind === "trending") {
      const [res] = await Promise.all([api("trending"), loadList({ order: "hot" }, append), railP]);
      paint(seq, "trending", trendingPageHTML(res.ok ? res.out : {}), { hero: false });
      return;
    }
    if (kind === "tags") {
      const res = await api("tags");
      await railP;
      paint(seq, "tags", tagsPageHTML(res.ok ? res.out.tags : []), { hero: false });
      return;
    }
    if (kind === "search" && arg) {
      const res = await api(`search?q=${encodeURIComponent(arg)}`);
      F.search = res.ok ? { q: arg, ...res.out } : { q: arg, people: [], posts: [] };
      await railP;
      paint(seq, "feed", `${headHTML("Search", "", true)}${searchResultsHTML()}`, { hero: false });
      return;
    }
    go("");
  }

  // Whichever surface is showing redraws: the feed, or the Account page.
  function refresh() {
    if (inAccount() && ACCT.el && document.body.contains(ACCT.el)) return mountAccount(ACCT.el);
    return render();
  }

  // ── finding things on the page ────────────────────────────────────────────
  const allPosts = () => [...F.posts, ...ACCT.posts, ...(F.search ? F.search.posts || [] : []), ...(F.post ? [F.post] : [])];
  const findPost = (id) => allPosts().find((p) => p.id === Number(id));

  /* A post can be on the page twice at once — in the Social view and on
     the Account page, whichever is hidden — so a card is always found from
     the button that was pressed, never by an id the two copies share. */
  const cardsOf = (id) => [...document.querySelectorAll(`.fd-post[data-post="${id}"]`)];
  const slotIn = (card) => (card ? card.querySelector(".fd-slot") : null);

  // Redraws every copy of a post, keeping whatever was open under each;
  // returns the new cards in the same order.
  function redraw(id) {
    const p = findPost(id);
    if (!p) return [];
    return cardsOf(id).map((el) => {
      const slot = slotIn(el);
      const keep = slot ? slot.innerHTML : "";
      const open = slot ? slot.dataset.open || "" : "";
      const full = !!(F.post && F.post.id === Number(id) && route().startsWith("post/"));
      el.insertAdjacentHTML("afterend", postHTML(p, full));
      const fresh = el.nextElementSibling;
      el.remove();
      const s2 = slotIn(fresh);
      if (s2) { s2.innerHTML = keep; s2.dataset.open = open; }
      return fresh;
    });
  }

  const sameAll = (id, fn) => allPosts().filter((p) => p.id === Number(id)).forEach(fn);
  const postUrl = (id) => `${location.origin}${location.pathname}#feed/post/${id}`;

  function closeMenus(except) {
    document.querySelectorAll(".fd-popover").forEach((m) => { if (m !== except) m.remove(); });
  }

  function popover(anchor, html) {
    closeMenus();
    const pop = document.createElement("div");
    pop.className = "fd-popover";
    pop.innerHTML = html;
    const head = anchor.closest(".fd-ph, .fd-prof-btns") || anchor.parentElement;
    head.appendChild(pop);
    const b = pop.querySelector("button");
    if (b) b.focus({ preventScroll: true });
    return pop;
  }

  function slotToggle(card, what, html) {
    const slot = slotIn(card);
    if (!slot) return null;
    if (slot.dataset.open === what) { slot.innerHTML = ""; slot.dataset.open = ""; return null; }
    slot.innerHTML = html; slot.dataset.open = what;
    return slot;
  }

  // ── actions ───────────────────────────────────────────────────────────────
  async function onAction(t) {
    const d = t.dataset;
    const act = d.fd;
    const id = d.id;
    if (act === "compose") {
      F.comp.open = true;
      if (inAccount() || route()) {
        // The feed draws first; render() focuses the box once it has.
        F._focusComp = true;
        if (inAccount()) location.hash = "#feed"; else go("");
        return;
      }
      redrawComposer();
      focusComposer();
      return;
    }
    if (act === "mode") {
      if (needProfile("post")) return;
      const c = F.comp;
      const t2 = document.getElementById("fd-comp-text");
      if (t2) c.text = t2.value;
      c.mode = c.mode === d.v ? "" : d.v;
      c.open = true;
      redrawComposer();
      if (c.mode === "parlay" && !c.results) loadLegs();
      return;
    }
    if (act === "pick-sport") { F.comp.sport = d.v; F.comp.results = null; F.comp.legs = []; redrawComposer(); loadLegs(); return; }
    if (act === "leg-add") {
      const l = F.comp.results && F.comp.results.legs[Number(d.i)];
      if (!l) return;
      if (F.comp.legs.length >= MAX_LEGS) { tfToast(`A post carries up to ${MAX_LEGS} legs.`); return; }
      F.comp.legs.push(l); buzz("tap"); redrawComposer(); return;
    }
    if (act === "leg-del") { F.comp.legs.splice(Number(d.i), 1); redrawComposer(); return; }
    if (act === "poll-add") { syncPoll(); if (F.comp.poll.length < 4) F.comp.poll.push(""); redrawComposer(); return; }
    if (act === "poll-del") { syncPoll(); F.comp.poll.splice(Number(d.i), 1); redrawComposer(); return; }
    if (act === "send") return send(t);
    if (act === "rail-metric") { F.railMetric = d.v; await refreshLeaders(); return; }
    if (act === "lb-metric" || act === "lb-days") {
      if (act === "lb-metric") F.metric = d.v; else F.days = d.v;
      return render();
    }
    if (act === "load") return inAccount() ? acctMore() : render(true);
    if (act === "back") { if (history.length > 1) history.back(); else go(""); return; }
    if (act === "clear-search") { F.search = null; return go(""); }
    if (act === "like") {
      if (needProfile("like posts")) return;
      const res = await api("like", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      sameAll(id, (p) => { p.likes = res.out.likes; p.liked = res.out.liked; });
      buzz("tap"); redraw(id); return;
    }
    if (act === "vote") {
      if (needProfile("vote")) return;
      const res = await api("vote", { id: Number(id), option: Number(d.v) });
      if (!res.ok) { tfToast(res.out.error || "That vote did not count."); return; }
      sameAll(id, (p) => { p.poll = res.out.poll; });
      buzz("tap"); redraw(id); return;
    }
    if (act === "tail") {
      if (needProfile("tail parlays")) return;
      const card = t.closest(".fd-post");
      const slot = slotIn(card);
      if (slot && slot.dataset.open === "tail") { slot.innerHTML = ""; slot.dataset.open = ""; return; }
      const at = cardsOf(id).indexOf(card);
      const res = await api("tail", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "Could not tail that."); return; }
      sameAll(id, (p) => { p.tails = res.out.tails; p.tailed = true; });
      buzz("tap");
      const fresh = redraw(id);
      const s2 = slotIn(fresh[at] || fresh[0]);
      if (s2) { s2.innerHTML = tailHTML(res.out); s2.dataset.open = "tail"; }
      return;
    }
    if (act === "share" || act === "copy") {
      closeMenus();
      const url = postUrl(id);
      if (act === "share" && navigator.share) {
        try { await navigator.share({ title: "Qellys Book", url }); } catch (err) { /* dismissed */ }
        return;
      }
      copyPlainText(url, null);
      return;
    }
    if (act === "share-profile") {
      const url = `${location.origin}${location.pathname}#feed/u/${encodeURIComponent(d.handle)}`;
      if (navigator.share) { try { await navigator.share({ title: "Qellys Book", url }); } catch (err) { /* dismissed */ } return; }
      copyPlainText(url, null);
      return;
    }
    if (act === "menu") {
      const p = findPost(id);
      if (!p) return;
      const open = t.parentElement.querySelector(".fd-popover");
      if (open) { open.remove(); return; }
      popover(t, menuHTML(p));
      return;
    }
    if (act === "pmenu") {
      const p = F.profile;
      if (!p) return;
      const open = t.parentElement.querySelector(".fd-popover");
      if (open) { open.remove(); return; }
      popover(t, `<div class="fd-menu" role="menu"><button data-fd="share-profile" data-handle="${escapeAttr(p.handle)}" type="button" role="menuitem">Share profile</button>
        <button class="danger" data-fd="block" data-handle="${escapeAttr(p.handle)}" type="button" role="menuitem">${p.blocked ? "Unblock" : "Block"} @${escapeHtml(p.handle)}</button></div>`);
      return;
    }
    if (act === "report-open") { const pop = t.closest(".fd-popover"); if (pop) pop.innerHTML = reportHTML("post", id); return; }
    if (act === "creport") { popover(t, reportHTML("comment", id)); return; }
    if (act === "edit-post") {
      const card = t.closest(".fd-post");
      closeMenus();
      const p = findPost(id);
      if (p) slotToggle(card, "edit", editHTML(p));
      return;
    }
    if (act === "edit-cancel") { slotToggle(t.closest(".fd-post"), "edit", ""); return; }
    if (act === "save-post") {
      const p = findPost(id);
      const card = t.closest(".fd-post");
      const v = ((card && card.querySelector(".fd-e")) || {}).value || "";
      const body = p && p.kind === "text" ? { id: Number(id), title: p.title || "", body: v } : { id: Number(id), caption: v };
      const res = await api("edit", body);
      if (!res.ok) { tfToast(res.out.error || "That did not save."); return; }
      sameAll(id, (q) => { if (q.kind === "text") q.body = v; else q.caption = v; q.edited = true; });
      const slot = slotIn(card); if (slot) { slot.innerHTML = ""; slot.dataset.open = ""; }
      redraw(id); return;
    }
    if (act === "del-post") {
      closeMenus();
      if (!confirm("Delete this post? Its likes, tails and comments go with it.")) return;
      const res = await api("delete", { kind: "post", id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not delete."); return; }
      F.posts = F.posts.filter((p) => p.id !== Number(id));
      ACCT.posts = ACCT.posts.filter((p) => p.id !== Number(id));
      F.rail = null;
      tfToast("Deleted.");
      if (route().startsWith("post/") && !inAccount()) return go("");
      return refresh();
    }
    if (act === "report") {
      closeMenus();
      const res = await api("report", { kind: d.kind, id: Number(id), reason: d.v || "other" });
      tfToast(res.ok ? "Reported — thanks. Three reports hide it until it’s reviewed." : (res.out.error || "That did not go through."));
      return;
    }
    if (act === "block") {
      closeMenus();
      const h = d.handle;
      const was = F.profile && F.profile.handle === h && F.profile.blocked;
      if (!was && !confirm(`Block @${h}? You won’t see each other’s posts or comments, and neither of you can follow the other.`)) return;
      const res = await api("block", { handle: h });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      tfToast(res.out.blocked ? `Blocked @${h}.` : `Unblocked @${h}.`);
      F.posts = []; F.rail = null;
      return res.out.blocked ? go("") : render();
    }
    if (act === "follow") {
      if (needProfile("follow people")) return;
      const res = await api("follow", { handle: d.handle });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      if (F.profile && F.profile.handle === d.handle) { F.profile.following = res.out.following; F.profile.followers = res.out.followers; }
      [...((F.rail || {}).leaders || []), ...((F.rail || {}).suggest || [])].forEach((p) => { if (p.handle === d.handle) p.following = res.out.following; });
      document.querySelectorAll(`[data-fd="follow"][data-handle="${CSS.escape(d.handle)}"]`).forEach((b) => {
        b.textContent = res.out.following ? "Following" : "Follow";
        b.classList.toggle("ghost", res.out.following || b.classList.contains("sm"));
      });
      if (route().startsWith("u/")) render();
      return;
    }
    if (act === "friend") {
      const res = await api("friend", { handle: d.handle });
      tfToast(res.ok ? (res.out.already ? "Request already sent." : res.out.already_friends ? "You’re already friends."
        : "Friend request sent — it lands in their inbox.") : (res.out.error || "That did not go through."));
      return;
    }
    if (act === "follows" || act === "following-list") {
      const which = act === "follows" ? "followers" : "following";
      const res = await api(`follows?handle=${encodeURIComponent(d.handle)}&which=${which}`);
      F.follows = res.ok ? { which, people: res.out.people } : null;
      if (inAccount()) { const box = document.getElementById("acct-follows"); if (box) box.innerHTML = followsHTML(); return; }
      return render();
    }
    if (act === "close-follows") {
      F.follows = null;
      if (inAccount()) { const box = document.getElementById("acct-follows"); if (box) box.innerHTML = ""; return; }
      return render();
    }
    if (act === "reply") {
      const slot = document.getElementById(`fd-rslot-${id}`);
      if (!slot) return;
      if (slot.innerHTML) { slot.innerHTML = ""; return; }
      slot.innerHTML = commentBoxHTML(F.post ? F.post.id : 0, Number(id));
      const ta = slot.querySelector("textarea"); if (ta) ta.focus();
      return;
    }
    if (act === "comment") {
      const parent = d.parent ? Number(d.parent) : null;
      const box = document.getElementById(parent ? `fd-rc-${parent}` : `fd-cc-${id}`);
      const res = await api("comment", { id: Number(id), body: box ? box.value : "", parent });
      if (!res.ok) { tfToast(res.out.error || "That did not post."); return; }
      return render();
    }
    if (act === "clike") {
      if (needProfile("like comments")) return;
      const res = await api("comment-like", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      t.classList.toggle("on", res.out.liked);
      t.innerHTML = `${ico("heart", 13)}${res.out.likes ? ` ${res.out.likes}` : ""}`;
      return;
    }
    if (act === "del-comment") {
      const res = await api("delete", { kind: "comment", id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not delete."); return; }
      return render();
    }
    // ── the Account page's own buttons ──
    if (act === "acct-tab") { ACCT.tab = d.v; try { sessionStorage.setItem("qb_acct_tab", d.v); } catch (e) {} return mountAccount(ACCT.el); }
    if (act === "acct-edit") { ACCT.edit = !ACCT.edit; return mountAccount(ACCT.el); }
    if (act === "save-profile") return saveProfile(t);
  }

  function syncPoll() {
    document.querySelectorAll("[data-poll]").forEach((i) => { F.comp.poll[Number(i.dataset.poll)] = i.value; });
  }

  async function refreshLeaders() {
    const r = await api(`leaders?metric=${F.railMetric}&days=${F.railDays}`);
    if (r.ok && F.rail) F.rail.leaders = (r.out.top || []).slice(0, 5);
    paintRail();
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest && e.target.closest("[data-fd]");
    if (!t || !t.closest("#view-feed, #acct-prof")) {
      if (!(e.target.closest && e.target.closest(".fd-popover"))) closeMenus();
      return;
    }
    e.preventDefault();
    if (!t.closest(".fd-popover") && t.dataset.fd !== "menu" && t.dataset.fd !== "pmenu") closeMenus();
    onAction(t);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenus();
    if (e.key === "Enter" && e.target && e.target.id === "fd-pick-q") e.preventDefault();
    // Enter posts a comment; Shift+Enter is a new line.
    if (e.key === "Enter" && !e.shiftKey && e.target && /^fd-(cc|rc)-/.test(e.target.id || "")) {
      e.preventDefault();
      const btn = e.target.parentElement.querySelector('[data-fd="comment"]');
      if (btn) onAction(btn);
    }
  });

  document.addEventListener("submit", (e) => {
    const f = e.target.closest && e.target.closest('[data-fd-form="search"]');
    if (!f) return;
    e.preventDefault();
    const q = ((f.querySelector("input") || {}).value || "").trim();
    if (q.startsWith("#") && q.length > 2) { go(`tag/${encodeURIComponent(q.slice(1))}`); return; }
    if (q.length < 2) { tfToast("Type at least two letters to search."); return; }
    go(`search/${encodeURIComponent(q)}`);
  });

  document.addEventListener("change", (e) => {
    const t = e.target;
    if (!t) return;
    if (t.matches && t.matches('[data-fd-sel="rail-days"]')) { F.railDays = t.value; refreshLeaders(); return; }
    if (t.id === "fd-comp-sport") { F.comp.talkSport = t.value; return; }
    if (t.id === "fd-strong") {
      try { localStorage.setItem(STRONG_KEY, t.checked ? "1" : "0"); } catch (err) {}
      F.posts = []; refresh();
      return;
    }
    if (t.name === "fd-color") {
      const prev = document.querySelector(".fd-editp-prev .fd-av");
      if (prev) prev.className = prev.className.replace(/fd-c\d/, `fd-c${t.value}`);
    }
  });

  let _qTimer = null;
  document.addEventListener("input", (e) => {
    const t = e.target;
    if (!t) return;
    if (t.id === "fd-comp-text") {
      F.comp.text = t.value;
      t.style.height = "auto";
      t.style.height = `${Math.min(t.scrollHeight, 320)}px`;
    }
    if (t.id === "fd-pick-q") {
      F.comp.q = t.value;
      clearTimeout(_qTimer);
      _qTimer = setTimeout(loadLegs, 220);
    }
    if (t.id === "fd-p-bio") {
      const c = document.getElementById("fd-p-count");
      if (c) c.textContent = `${t.value.length}/200`;
    }
  });

  document.addEventListener("focusin", (e) => {
    if (e.target && e.target.id === "fd-comp-text" && !F.comp.open) {
      F.comp.open = true;
      const card = document.getElementById("fd-comp");
      if (card) card.classList.add("open");
      e.target.rows = 3;
    }
  });

  // ── the Account page: your one profile ────────────────────────────────────
  const TEAM_LEAGUES = [["", "None"], ["nfl", "NFL"], ["cfb", "CFB"], ["mlb", "MLB"], ["nba", "NBA"], ["wnba", "WNBA"], ["nhl", "NHL"]];

  function profileFormHTML(m, suggest, creating) {
    const [lg, abbr] = (m.team || "").split(":");
    const cur = { ...m, handle: m.handle || suggest || "you" };
    return `<section class="fd-card fd-editp">
      <div class="fd-editp-head"><div class="fd-editp-prev">${avatar(cur, "xl")}</div>
        <div><h2>${creating ? "Make your profile" : "Edit profile"}</h2>
          <p class="fd-fine">${creating ? "One profile for the whole site — your posts, comments, the streak board and your friends all show this name. Your email is never shown."
            : "This is the one profile the whole site shows: Social, the streak board and your friends’ inbox."}</p></div></div>
      <div class="fd-editp-grid">
        <label>Display name<input class="fd-input" id="fd-p-name" maxlength="30" value="${escapeAttr(m.name || "")}" placeholder="How your name shows"></label>
        <label>Handle<span class="fd-at-in"><span>@</span><input class="fd-input" id="fd-p-handle" maxlength="20" value="${escapeAttr(m.handle || suggest || "")}"
          placeholder="3–20 letters, numbers or _"${m.verified ? " readonly" : ""}></span></label>
        <label class="wide"><span class="fd-lab">Bio <small id="fd-p-count">${(m.bio || "").length}/200</small></span><textarea class="fd-input" id="fd-p-bio" maxlength="200" rows="3"
          placeholder="Who you are, what you bet">${escapeHtml(m.bio || "")}</textarea></label>
        <fieldset class="fd-colors wide"><legend>Colour</legend>${[0, 1, 2, 3, 4, 5, 6, 7].map((i) =>
          `<label class="fd-swatch fd-c${i}"><input type="radio" name="fd-color" value="${i}"${(m.color || 0) === i ? " checked" : ""}><span class="sr-only">Colour ${i + 1}</span></label>`).join("")}</fieldset>
        <label>Favourite team<select class="fd-input" id="fd-p-lg">${TEAM_LEAGUES.map(([k, t]) =>
          `<option value="${k}"${k === (lg || "") ? " selected" : ""}>${t}</option>`).join("")}</select></label>
        <label>Team code<input class="fd-input" id="fd-p-abbr" maxlength="12" value="${escapeAttr(abbr || "")}" placeholder="DET"></label>
      </div>
      ${m.verified ? `<p class="fd-fine">${VERIFIED} Verified handles stay put — ask the site owner to change one.</p>` : ""}
      <p class="fd-fine">Slurs are refused in names and bios. Swearing in a bio is hidden unless a reader turns on strong language.</p>
      <div class="fd-row-end">${creating ? "" : `<button class="fd-btn ghost" data-fd="acct-edit" type="button">Cancel</button>`}
        <button class="fd-btn" data-fd="save-profile" type="button">${creating ? "Create profile" : "Save profile"}</button></div>
    </section>`;
  }

  async function saveProfile(btn) {
    const lg = (document.getElementById("fd-p-lg") || {}).value || "";
    const abbr = ((document.getElementById("fd-p-abbr") || {}).value || "").trim().toUpperCase();
    const color = (document.querySelector('input[name="fd-color"]:checked') || {}).value;
    btn.disabled = true;
    const res = await api("profile", {
      handle: (document.getElementById("fd-p-handle") || {}).value || "",
      name: (document.getElementById("fd-p-name") || {}).value || "",
      bio: (document.getElementById("fd-p-bio") || {}).value || "",
      color: Number(color || 0), team: lg && abbr ? `${lg}:${abbr}` : "" });
    btn.disabled = false;
    if (!res.ok) { tfToast(res.out.error || "That did not save."); return; }
    F.me = res.out.profile; F._meAt = Date.now(); F.rail = null;
    ACCT.edit = false;
    ACCT.prof = null;          // the header redraws from the saved row
    if (typeof _acctUser !== "undefined" && _acctUser) _acctUser.profile = res.out.profile;
    if (typeof acctChipPaint === "function") acctChipPaint();
    tfToast("Profile saved.");
    mountAccount(ACCT.el);
  }

  function acctTabsHTML() {
    const tabs = [["posts", "Posts"], ["picks", "Graded picks"], ["friends", "Friends"], ["settings", "Settings"]];
    return `<nav class="fd-ptabs acct" aria-label="Your account">${tabs.map(([k, t]) =>
      `<button class="${ACCT.tab === k ? "on" : ""}" data-fd="acct-tab" data-v="${k}" type="button"${ACCT.tab === k ? ' aria-current="page"' : ""}>${t}</button>`).join("")}</nav>`;
  }

  // The panels app.js drew (friends, plan, sign-in, settings) show by tab.
  function showAcctPanels(tab) {
    document.querySelectorAll("#account-body [data-acct-tab]").forEach((el) => {
      el.hidden = !(tab === "all" || el.dataset.acctTab === tab);
    });
  }

  async function acctMore() {
    const p = new URLSearchParams({ handle: F.me.handle, tab: "posts", before: String(ACCT.next || 0) });
    const res = await api(`profile?${p}`);
    if (!res.ok) return;
    ACCT.posts = ACCT.posts.concat(res.out.posts || []);
    ACCT.more = !!res.out.more; ACCT.next = res.out.next || 0;
    mountAccount(ACCT.el, null, true);
  }

  /* app.js renderAccount calls this with the box at the top of the Account
     page. Signed in with no profile: the one place to make it. With one:
     the header everybody sees, then Posts / Graded picks / Friends /
     Settings. */
  async function mountAccount(el, acct, keepPosts) {
    if (!el) return;
    ACCT.el = el;
    if (window._acctEdit) { ACCT.edit = true; window._acctEdit = false; }
    if (window._acctTab) { ACCT.tab = window._acctTab; window._acctTab = null; }
    else if (!ACCT._tabRead) {
      ACCT._tabRead = true;
      try { ACCT.tab = sessionStorage.getItem("qb_acct_tab") || "posts"; } catch (e) { ACCT.tab = "posts"; }
    }
    await ensureMe(!keepPosts);
    if (!document.body.contains(el)) return;
    if (!F.me) {
      const u = acct || (typeof _acctUser !== "undefined" ? _acctUser : null) || {};
      el.innerHTML = profileFormHTML({}, u.suggest_handle || "", true);
      showAcctPanels("all");
      return;
    }
    if (!keepPosts && (ACCT.tab === "posts" || ACCT.tab === "picks" || !ACCT.prof)) {
      const res = await api(`profile?handle=${encodeURIComponent(F.me.handle)}&tab=${ACCT.tab === "picks" ? "record" : "posts"}`);
      if (res.ok) {
        ACCT.prof = res.out.profile;
        ACCT.posts = res.out.posts || [];
        ACCT.more = !!res.out.more && ACCT.tab === "posts";
        ACCT.next = res.out.next || 0;
      }
    }
    if (!document.body.contains(el)) return;
    const p = ACCT.prof || { ...F.me, record: {}, followers: 0, following_count: 0, tails: 0 };
    const list = ACCT.tab === "posts" || ACCT.tab === "picks"
      ? `<div class="fd-list">${ACCT.posts.length ? ACCT.posts.map((q) => postHTML(q)).join("")
          : `<div class="fd-card fd-empty">${ACCT.tab === "picks" ? "No graded picks yet — results land here once their games are final."
            : `Nothing posted yet. <a href="#feed">Head to Social</a> to share a take or build a parlay.`}</div>`}</div>
         ${ACCT.more && ACCT.tab === "posts" ? `<button class="fd-btn ghost fd-load" data-fd="load" type="button">More posts</button>` : ""}`
      : "";
    el.innerHTML = `${ACCT.edit ? profileFormHTML(F.me, "", false) : profileHeaderHTML(p, { mine: true })}
      <div id="acct-follows">${followsHTML()}</div>${acctTabsHTML()}${list}`;
    showAcctPanels(ACCT.tab === "friends" || ACCT.tab === "settings" ? ACCT.tab : "none");
  }

  // ── posting from the parlay slip ──────────────────────────────────────────
  function slipPostStart(slot) {
    slot.innerHTML = `<input class="fr-note fd-caption" maxlength="280"
        placeholder="Say something about it (optional) — #tags and @handles work" aria-label="Caption">
      <div class="fr-send-row"><button class="btn" id="slip-feed-go" type="button">Post</button></div>
      <p class="set-note">It locks at kickoff and is graded on your profile automatically.</p>`;
    const i = slot.querySelector("input"); if (i) i.focus();
  }

  async function slipPost(btn) {
    const s = slipState();
    const cap = (document.querySelector("#slip-send-slot .fd-caption") || {}).value || "";
    btn.textContent = "Posting…";
    const res = await api("post", { sport: s.sport, date: s.date, caption: cap,
      legs: s.legs.map((l) => (l.gid ? { gid: l.gid }
        : { player: l.player, market: l.market, side: l.side, line: l.line })) });
    btn.textContent = "Post";
    if (res.out.need_handle) { tfToast(res.out.error); switchView("account", true); return; }
    if (!res.ok) { tfToast(res.out.error || "That did not post."); return; }
    tfToast(res.out.already ? "Already on the feed." : "Posted to the feed.");
    F.posts = []; F.rail = null;
    location.hash = `#feed/post/${res.out.id}`;
  }

  window.QBSocial = { render, slipPostStart, slipPost, mountAccount, avatar };
})();
