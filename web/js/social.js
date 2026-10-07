/* Qellys Book — the social feed, profiles and the Tail button.
   ==========================================================================
   Ethan, 2026-10-06: a social page where people post parlays, a whale-tail
   Tail button with a counter, likes, comments, a bio. 2026-10-07: "go
   deeper … a full social feature … take reference from something like
   facebook or reddit … there needs to be profiles for users." The audit
   is docs/SOCIAL_AUDIT.md; the server is engine/socialfeed.py behind
   /api/feed/.

   LOADED ON FIRST USE (app.js loadSocial), like the chart library: a
   reader who never opens The Feed downloads none of this. It runs in the
   page's global scope beside app.js and visuals.js, and uses their
   helpers (escapeHtml, icon, betMark, tfToast, switchView …) by name.

   ROUTES live in the address bar so back, forward and shared links work:
     #feed                    the feed
     #feed/post/<id>          one post with its comments
     #feed/u/<handle>[/record] a profile
     #feed/edit               edit your profile
     #feed/notifications      what happened to your posts
     #feed/leaders            top bettors

   THE PAGE SENDS WHICH ROWS, NEVER WHAT THEY SAY. A posted leg is a game id
   or player · market · side · line; the server reads every number off its
   own board, locks a paid leg for a reader who has not paid, and hands out
   bet-slip links only on Tail. */
(function () {
  "use strict";

  const STRONG_KEY = "qb_feed_strong";
  const SPORTS = [["", "All"], ["nfl", "NFL"], ["cfb", "CFB"], ["mlb", "MLB"],
                  ["nba", "NBA"], ["wnba", "WNBA"], ["nhl", "NHL"]];
  const WINDOWS = [["day", "Today"], ["week", "This week"], ["month", "This month"], ["all", "All time"]];
  const REASONS = [["spam", "Spam"], ["abuse", "Harassment"], ["hate", "Hate"],
                   ["scam", "Scam or selling picks"], ["other", "Something else"]];
  const F = { order: "hot", window: "week", sport: "", kind: "", posts: [], more: false,
              next: 0, paged: "offset", me: null, signedIn: false, unseen: 0, rail: null,
              search: null, profile: null, follows: null, post: null };

  // ── small helpers ──────────────────────────────────────────────────────────
  function strong() {
    try { return localStorage.getItem(STRONG_KEY) === "1"; } catch (e) { return false; }
  }

  function ago(ts) {
    const s = Math.max(0, Date.now() / 1000 - Number(ts || 0));
    if (s < 60) return "now";
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`;
    return new Date(Number(ts) * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function since(ts) {
    return new Date(Number(ts || 0) * 1000).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }

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

  const go = (route) => { location.hash = route ? `#feed/${route}` : "#feed"; };
  const route = () => (location.hash.startsWith("#feed/") ? decodeURIComponent(location.hash.slice(6)) : "");
  const host = () => document.getElementById("view-feed");
  const signedInOrSay = (what) => {
    if (F.signedIn) return true;
    tfToast(`Sign in (free) to ${what}.`);
    return false;
  };

  /* Text a person wrote: escaped first, then @handles become links. The
     escape runs before the link so nothing the writer typed is markup. */
  function rich(s) {
    return escapeHtml(String(s || "")).replace(/(^|[^A-Za-z0-9_])@([A-Za-z0-9_]{3,20})/g,
      (m, pre, h) => `${pre}<a class="fd-mention" href="#feed/u/${h}">@${h}</a>`);
  }

  function initials(p) {
    const src = String((p && (p.name || p.handle)) || "?").trim();
    const parts = src.split(/[\s_]+/).filter(Boolean);
    return ((parts[0] || "?")[0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
  }

  function avatar(p, size) {
    const c = Math.abs(Number((p && p.color) || 0)) % 8;
    return `<span class="fd-av fd-c${c}${size ? ` fd-av-${size}` : ""}" aria-hidden="true">${escapeHtml(initials(p))}</span>`;
  }

  function who(p, opts) {
    const h = escapeHtml(p.handle || "someone");
    const name = p.name ? `<b>${escapeHtml(p.name)}</b> ` : "";
    return `<a class="fd-who" href="#feed/u/${encodeURIComponent(p.handle || "")}">${avatar(p, opts && opts.size)}
      <span class="fd-who-t">${name || `<b>@${h}</b>`}${name ? `<span class="fd-at">@${h}</span>` : ""}</span></a>`;
  }

  function teamChip(team) {
    if (!team || !team.includes(":")) return "";
    const [lg, abbr] = team.split(":");
    let mark = "";
    try { mark = teamMark(abbr, 16, null, lg); } catch (e) { mark = ""; }
    return `<span class="fd-team">${mark}${escapeHtml(abbr)} <small>${escapeHtml(lg.toUpperCase())}</small></span>`;
  }

  function units(u) {
    if (u == null) return "";
    const n = Number(u);
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(2)}u`;
  }

  function resultBadge(p) {
    if (p.kind === "text") return "";
    const r = p.result || "pending";
    const word = { won: "Won", lost: "Lost", push: "Push", pending: "Pending", nograde: "Not graded" }[r] || r;
    const u = (r === "won" || r === "lost") ? ` ${units(p.units)}` : "";
    return `<span class="fd-res fd-res-${escapeAttr(r)}">${word}${u}</span>`;
  }

  function legMark(l) {
    if (l.result === "won") return `<span class="fd-lr won" title="Won">${icon("check", 12)}</span>`;
    if (l.result === "lost") return `<span class="fd-lr lost" title="Lost">${icon("cross", 12)}</span>`;
    if (l.result === "push" || l.result === "void") return `<span class="fd-lr push" title="${l.result === "void" ? "Void" : "Push"}">${icon("dash", 12)}</span>`;
    return "";
  }

  function legHTML(l) {
    if (l.locked) {
      return `<div class="fd-leg locked"><span class="fd-leg-who"><b>${escapeHtml(l.player || l.matchup || "")}</b>
        <span>${escapeHtml(l.market_label || "")}</span></span>
        <span class="fd-lock">${icon("lock", 12)} Members</span></div>`;
    }
    const name = l.kind === "game" ? (l.matchup || "") : (l.player || "");
    return `<div class="fd-leg${l.result ? ` r-${escapeAttr(l.result)}` : ""}"><span class="slip-leg-mark">${betMark(l, 24)}</span>
      <span class="fd-leg-who"><b>${escapeHtml(name)}</b><span>${escapeHtml(l.label || "")}</span></span>
      <span class="fd-leg-odds">${legMark(l)}${l.odds != null ? escapeHtml(trueMinus(oddsTxt(l.odds))) : ""}${
        l.book ? `<small>${escapeHtml(l.book)}</small>` : ""}</span></div>`;
  }

  // ── a post ─────────────────────────────────────────────────────────────────
  function postHTML(p, full) {
    const n = (p.legs || []).length;
    const open = `href="#feed/post/${p.id}"`;
    const meta = `<span class="fd-meta">· ${ago(p.at)}${p.sport && p.sport !== "all"
      ? ` · ${escapeHtml(String(p.sport).toUpperCase())}` : ""}${p.edited ? " · edited" : ""}</span>`;
    const body = p.kind === "text"
      ? `<a class="fd-title" ${open}>${rich(p.title)}</a>
         ${p.body ? `<p class="fd-body${full ? "" : " clamp"}">${rich(p.body)}</p>` : ""}`
      : `${p.caption ? `<p class="fd-cap">${rich(p.caption)}</p>` : ""}
         <a class="fd-legs" ${open} aria-label="Open this post">${(p.legs || []).map(legHTML).join("")}</a>
         ${p.combined != null && n > 1 ? `<div class="fd-total">${n}-leg parlay · <b>${escapeHtml(trueMinus(oddsTxt(p.combined)))}</b>
           <span>at the prices when posted</span></div>` : ""}`;
    return `<article class="card fd-post" data-post="${p.id}">
      <header class="fd-head">${who(p)}${meta}<span class="fd-head-r">${resultBadge(p)}
        <button class="fd-more" data-fd="menu" data-id="${p.id}" type="button" aria-label="More">${icon("dots", 16)}</button></span></header>
      ${body}
      <div class="fd-acts">
        <button class="fd-act${p.liked ? " on" : ""}" data-fd="like" data-id="${p.id}" type="button"
          aria-pressed="${p.liked ? "true" : "false"}" aria-label="Like">${icon("heart", 16)}<span>${p.likes}</span></button>
        <a class="fd-act" ${open} aria-label="Comments">${icon("chat", 16)}<span>${p.comments}</span></a>
        <button class="fd-act" data-fd="share" data-id="${p.id}" type="button" aria-label="Share">${icon("share", 16)}</button>
        ${p.kind === "text" ? "" : p.closed ? `<span class="fd-tailed">${icon("whale", 16)} ${p.tails} tailed</span>` : `<button class="fd-tail${p.tailed ? " on" : ""}${p.locked ? " locked" : ""}" data-fd="tail" data-id="${p.id}" type="button"
          title="${p.locked ? "Members can tail this one" : "Open this parlay at your book"}">${icon("whale", 18)}<b>Tail</b>
          <span class="fd-n">${p.tails}</span></button>`}
      </div>
      <div class="fd-slot" id="fd-slot-${p.id}"></div>
    </article>`;
  }

  function tailHTML(res) {
    const n = res.n_legs || 0;
    const fine = `<p class="betit-fine">Each tap opens that book’s bet slip in a new tab. One link carries
      every leg only where the book’s link format takes them (FanDuel’s does); at the others add the
      legs one by one and they stack on the same slip. Prices move — check before you place.
      21+ · Gambling problem? 1-800-GAMBLER</p>`;
    const books = res.books || [];
    if (!books.length) {
      return `<div class="betit-list fd-tailbox"><p class="set-empty">No book has handed us a bet-slip
        link for these legs yet — the legs above are everything you need to key it in.</p>${fine}</div>`;
    }
    const a = (url, inner, cls) => `<a class="${cls}" href="${safeHref(url)}" target="_blank"
      rel="noopener noreferrer nofollow">${inner}</a>`;
    const rows = books.map((b) => (b.combined
      ? a(b.combined, `<b>${escapeHtml(b.book)}</b><span class="betit-px">all ${n} legs</span><i>one slip</i>`, "betit-row")
      : `<div class="fd-book"><b>${escapeHtml(b.book)}</b><i>${b.have} of ${n} leg${n === 1 ? "" : "s"}</i>
          <div class="fd-book-legs">${b.legs.map((c, i) => (c
            ? a(c.url, `Leg ${i + 1}${c.price != null ? ` · ${escapeHtml(american(c.price))}` : ""}`, "chip")
            : `<span class="chip off">Leg ${i + 1} not offered</span>`)).join("")}</div></div>`)).join("");
    return `<div class="betit-list fd-tailbox"><p class="betit-h">Tail it at</p>${rows}${fine}</div>`;
  }

  function menuHTML(p) {
    const items = [`<button class="btn ghost" data-fd="copy" data-id="${p.id}" type="button">Copy link</button>`];
    if (p.mine) {
      if (p.editable) items.push(`<button class="btn ghost" data-fd="edit-post" data-id="${p.id}" type="button">Edit</button>`);
      items.push(`<button class="btn ghost" data-fd="del-post" data-id="${p.id}" type="button">Delete</button>`);
    } else if (F.signedIn) {
      items.push(`<select class="fd-input fd-reason" aria-label="Why report this">${REASONS.map(([k, t]) =>
        `<option value="${k}">${t}</option>`).join("")}</select>
        <button class="btn ghost" data-fd="report" data-kind="post" data-id="${p.id}" type="button">${icon("flag", 12)} Report</button>
        <button class="btn ghost" data-fd="block" data-handle="${escapeAttr(p.handle)}" type="button">Block @${escapeHtml(p.handle)}</button>`);
    }
    return `<div class="fd-menu">${items.join("")}</div>`;
  }

  function editHTML(p) {
    if (p.kind === "text") {
      return `<div class="fd-form col"><input class="fd-input" id="fd-et-${p.id}" maxlength="120" value="${escapeAttr(p.title)}" aria-label="Title">
        <textarea class="fd-input" id="fd-eb-${p.id}" maxlength="2000" rows="4" aria-label="Body">${escapeHtml(p.body)}</textarea>
        <button class="btn" data-fd="save-post" data-id="${p.id}" type="button">Save</button></div>`;
    }
    return `<div class="fd-form"><input class="fd-input" id="fd-ec-${p.id}" maxlength="280" value="${escapeAttr(p.caption)}" aria-label="Caption">
      <button class="btn" data-fd="save-post" data-id="${p.id}" type="button">Save</button></div>`;
  }

  // ── comments ───────────────────────────────────────────────────────────────
  function commentHTML(c, postId, reply) {
    const acts = `<button class="fd-cact${c.liked ? " on" : ""}" data-fd="clike" data-id="${c.id}" type="button">${icon("heart", 12)} ${c.likes || ""}</button>
      ${reply ? "" : `<button class="fd-cact" data-fd="reply" data-id="${c.id}" type="button">Reply</button>`}
      ${c.can_delete ? `<button class="fd-cact" data-fd="del-comment" data-id="${c.id}" type="button">Delete</button>`
        : F.signedIn ? `<button class="fd-cact" data-fd="report" data-kind="comment" data-id="${c.id}" type="button">Report</button>` : ""}`;
    return `<div class="fd-com${reply ? " reply" : ""}" id="fd-com-${c.id}">
      ${avatar(c, "sm")}
      <div class="fd-com-b"><div class="fd-com-h"><a href="#feed/u/${encodeURIComponent(c.handle)}"><b>${escapeHtml(c.name || c.handle)}</b></a>
        <span class="fd-meta">@${escapeHtml(c.handle)} · ${ago(c.at)}</span></div>
        <p>${rich(c.body)}</p><div class="fd-cacts">${acts}</div>
        <div class="fd-rslot" id="fd-rslot-${c.id}"></div>
        ${(c.replies || []).map((r) => commentHTML(r, postId, true)).join("")}</div></div>`;
  }

  function composerFor(postId, parent) {
    if (!F.signedIn) return `<p class="set-note"><a href="#account">Sign in</a> to join the conversation.</p>`;
    if (!F.me) return `<p class="set-note"><a href="#feed/edit">Pick a handle</a> to comment.</p>`;
    const id = parent ? `fd-rc-${parent}` : `fd-cc-${postId}`;
    return `<div class="fd-compose"><textarea class="fd-input" id="${id}" maxlength="500" rows="${parent ? 1 : 2}"
        placeholder="${parent ? "Write a reply" : "Add a comment — @handle to mention someone"}" aria-label="Comment"></textarea>
      <button class="btn" data-fd="comment" data-id="${postId}"${parent ? ` data-parent="${parent}"` : ""} type="button">${parent ? "Reply" : "Post"}</button></div>`;
  }

  // ── the pieces of the feed page ────────────────────────────────────────────
  function chips(list, cur, act) {
    return list.map(([k, t]) => `<button class="rec-win${cur === k ? " active" : ""}" data-fd="${act}" data-v="${k}" type="button">${t}</button>`).join("");
  }

  function headHTML(title, sub) {
    return `<div class="fd-top">
      <div class="section-title">${title}${sub ? `<span class="sub">— ${sub}</span>` : ""}</div>
      <div class="fd-tools">
        <form class="fd-search" data-fd-form="search" role="search">
          <input class="fd-input" name="q" maxlength="40" placeholder="Search people and posts" aria-label="Search people and posts"
            value="${escapeAttr((F.search && F.search.q) || "")}"></form>
        <a class="fd-bell" href="#feed/notifications" aria-label="Notifications">${icon("bell", 18)}${F.unseen
          ? `<span class="fd-dot">${F.unseen > 99 ? "99+" : F.unseen}</span>` : ""}</a>
        ${F.me ? `<a class="fd-me-av" href="#feed/u/${encodeURIComponent(F.me.handle)}" aria-label="Your profile">${avatar(F.me, "sm")}</a>` : ""}
      </div></div>`;
  }

  function meCardHTML() {
    if (!F.signedIn) {
      return `<div class="card fd-me"><p><b>Join the conversation.</b> <a href="#account">Sign in</a>
        (free) to post, follow people, like, comment and tail.</p></div>`;
    }
    if (!F.me) {
      return `<div class="card fd-me"><p><b>Set up your profile.</b> Pick a handle — it is the name your posts
        and comments go out under. Your email is never shown.</p>
        <a class="btn" href="#feed/edit">Create your profile</a></div>`;
    }
    return `<div class="card fd-compose-card">
      <div class="fd-compose-row">${avatar(F.me)}<button class="fd-fake-input" data-fd="talk-open" type="button">Start a discussion…</button></div>
      <div class="fd-talk" id="fd-talk" hidden>
        <select class="fd-input" id="fd-talk-sport" aria-label="Sport">${SPORTS.map(([k, t]) =>
          `<option value="${k}">${k ? t : "Any sport"}</option>`).join("")}</select>
        <input class="fd-input" id="fd-talk-title" maxlength="120" placeholder="Title" aria-label="Title">
        <textarea class="fd-input" id="fd-talk-body" maxlength="2000" rows="4" placeholder="What’s on your mind? @handle to mention someone" aria-label="Body"></textarea>
        <div class="fd-row-end"><button class="btn ghost" data-fd="talk-close" type="button">Cancel</button>
          <button class="btn" data-fd="talk-post" type="button">Post</button></div>
      </div>
      <p class="set-note">To post a parlay: add legs with <b>+ Parlay</b> on any board, open the slip, tap <b>Post to the feed</b>.
        Picks lock at kickoff and every parlay is graded automatically.</p></div>`;
  }

  function railHTML() {
    const r = F.rail;
    if (!r) return "";
    const row = (p, right) => `<div class="fd-rail-row">${who(p, { size: "sm" })}${right}</div>`;
    const followBtn = (p) => (F.signedIn && (!F.me || p.handle !== F.me.handle)
      ? `<button class="btn ghost fd-follow-sm" data-fd="follow" data-handle="${escapeAttr(p.handle)}" type="button">${p.following ? "Following" : "Follow"}</button>` : "");
    return `<aside class="fd-rail">
      <div class="card fd-rail-card"><h3>Top bettors <small>30 days</small></h3>
        ${(r.leaders || []).length ? r.leaders.map((p, i) => row(p, `<span class="fd-rank-u">${i + 1}. ${units(p.units)}</span>`)).join("")
          : `<p class="set-note">Nobody has five graded posts yet. Post parlays and the board fills itself.</p>`}
        <a class="fd-more-link" href="#feed/leaders">Full leaderboard</a></div>
      ${(r.suggest || []).length ? `<div class="card fd-rail-card"><h3>Who to follow</h3>
        ${r.suggest.map((p) => row(p, followBtn(p))).join("")}</div>` : ""}
      <div class="card fd-rail-card fd-rules"><h3>House rules</h3>
        <p>Picks lock at kickoff and can’t be edited — every parlay is graded from the same results as our Record page.</p>
        <p>Slurs are never posted. Swearing is hidden unless you turn on strong language.</p>
        <p>Three reports hide a post until it is reviewed. Block anyone, any time.</p></div>
    </aside>`;
  }

  function listHTML(posts, emptyMsg) {
    return posts.length ? posts.map((p) => postHTML(p)).join("")
      : `<p class="set-empty">${emptyMsg}</p>`;
  }

  function homeHTML() {
    const top = F.order === "top" ? `<div class="rec-windows fd-sub">${chips(WINDOWS, F.window, "window")}</div>` : "";
    const empty = F.order === "following"
      ? (F.signedIn ? "Nobody you follow has posted yet. Find people on the leaderboard or in search." : "Sign in to see posts from people you follow.")
      : "Nothing here yet — be the first to post.";
    const results = F.search ? `<div class="card fd-results">
        <div class="fd-row-between"><b>Results for “${escapeHtml(F.search.q)}”</b><button class="btn ghost" data-fd="clear-search" type="button">Clear</button></div>
        ${(F.search.people || []).length ? `<div class="fd-people">${F.search.people.map((p) =>
          `<div class="fd-rail-row">${who(p, { size: "sm" })}</div>`).join("")}</div>` : ""}
        ${(F.search.people || []).length || (F.search.posts || []).length ? "" : `<p class="set-empty">Nothing matched.</p>`}
      </div>${(F.search.posts || []).map((p) => postHTML(p)).join("")}` : "";
    return `${headHTML("The Feed", "parlays and talk from the room. Tap the whale to tail one at your book.")}
      <div class="fd-grid"><div class="fd-main">
        ${meCardHTML()}
        ${results || `<div class="fd-bar">
          <div class="rec-windows" role="group" aria-label="Sort">${chips([["hot", "Hot"], ["new", "New"], ["top", "Top"], ["following", "Following"]], F.order, "order")}</div>
          <label class="fd-toggle"><input type="checkbox" id="fd-strong"${strong() ? " checked" : ""}> Strong language</label>
        </div>${top}
        <div class="rec-windows fd-sub">${chips(SPORTS, F.sport, "sport")}<span class="fd-sep"></span>${chips([["", "Everything"], ["parlay", "Picks"], ["text", "Talk"]], F.kind, "kind")}</div>
        <div class="fd-list">${listHTML(F.posts, empty)}</div>
        ${F.more ? `<button class="btn ghost fd-load" data-fd="load" type="button">More posts</button>` : ""}`}
      </div>${railHTML()}</div>`;
  }

  function backBar(label) {
    return `<button class="btn ghost fd-back" data-fd="back" type="button">← ${label || "Back"}</button>`;
  }

  function postPageHTML() {
    const p = F.post;
    if (!p) return `${backBar("The Feed")}<p class="set-empty">That post is gone.</p>`;
    return `${headHTML("Post", "")}${backBar("The Feed")}
      <div class="fd-grid"><div class="fd-main">${postHTML(p, true)}
        <div class="card fd-thread"><h3>${p.comments} comment${p.comments === 1 ? "" : "s"}</h3>
          ${composerFor(p.id)}
          ${(p.comment_list || []).map((c) => commentHTML(c, p.id)).join("") || `<p class="set-note">No comments yet — start it off.</p>`}
        </div></div>${railHTML()}</div>`;
  }

  function stat(n, label, cls, act, handle) {
    const inner = `<b>${n}</b><span>${label}</span>`;
    return act ? `<button class="fd-stat${cls ? ` ${cls}` : ""}" data-fd="${act}" data-handle="${escapeAttr(handle)}" type="button">${inner}</button>`
      : `<div class="fd-stat${cls ? ` ${cls}` : ""}">${inner}</div>`;
  }

  function profileHTML(tab) {
    const p = F.profile;
    if (!p) return `${backBar("The Feed")}<p class="set-empty">Nobody has that handle.</p>`;
    const rec = p.record || {};
    const r30 = p.record30 || {};
    const recTxt = rec.n ? `${rec.w}-${rec.l}${rec.p ? `-${rec.p}` : ""}` : "—";
    const unitsCls = rec.units > 0 ? "up" : rec.units < 0 ? "down" : "";
    const btns = p.mine
      ? `<a class="btn" href="#feed/edit">Edit profile</a>`
      : F.signedIn ? `<button class="btn${p.following ? " ghost" : ""}" data-fd="follow" data-handle="${escapeAttr(p.handle)}" type="button">${p.following ? "Following" : "Follow"}</button>
          ${p.friend ? `<a class="btn ghost" href="#messages">Message</a>`
            : `<button class="btn ghost" data-fd="friend" data-handle="${escapeAttr(p.handle)}" type="button">Add friend</button>`}
          <button class="btn ghost" data-fd="block" data-handle="${escapeAttr(p.handle)}" type="button">${p.blocked ? "Unblock" : "Block"}</button>`
      : `<a class="btn" href="#account">Sign in to follow</a>`;
    const follows = F.follows ? `<div class="card fd-follows"><div class="fd-row-between"><b>${F.follows.which === "followers" ? "Followers" : "Following"}</b>
        <button class="btn ghost" data-fd="close-follows" type="button">Close</button></div>
        ${(F.follows.people || []).map((q) => `<div class="fd-rail-row">${who(q, { size: "sm" })}</div>`).join("") || `<p class="set-note">Nobody yet.</p>`}</div>` : "";
    const empty = tab === "record" ? "No graded parlays yet — results appear here once their games are final." : "No posts yet.";
    return `${headHTML("Profile", "")}${backBar("The Feed")}
      <div class="fd-grid"><div class="fd-main">
      <section class="card fd-prof">
        <div class="fd-banner fd-c${(p.color || 0) % 8}"></div>
        <div class="fd-prof-top">${avatar(p, "xl")}<div class="fd-prof-btns">${btns}</div></div>
        <h2 class="fd-prof-name">${escapeHtml(p.name || p.handle)}</h2>
        <p class="fd-prof-h">@${escapeHtml(p.handle)}${p.follows_you ? ` <span class="fd-tag">Follows you</span>` : ""}${p.streak ? ` <span class="fd-tag ${p.streak[0] === "W" ? "up" : "down"}">${escapeHtml(p.streak)} streak</span>` : ""}</p>
        ${p.bio ? `<p class="fd-prof-bio">${rich(p.bio)}</p>` : ""}
        <p class="fd-prof-meta">${teamChip(p.team)}<span>Joined ${escapeHtml(since(p.since))}</span></p>
        <div class="fd-stats">
          ${stat(recTxt, "Record")}${stat(units(rec.units) || "0.00u", "Units", unitsCls)}
          ${stat(rec.roi == null ? "—" : `${rec.roi > 0 ? "+" : ""}${rec.roi}%`, "ROI", unitsCls)}
          ${stat(p.followers, "Followers", "", "follows", p.handle)}${stat(p.following_count, "Following", "", "following-list", p.handle)}
          ${stat(p.tails, "Tails")}
        </div>
        ${r30.n ? `<p class="fd-prof-30">Last 30 days: <b>${r30.w}-${r30.l}${r30.p ? `-${r30.p}` : ""}</b> · ${units(r30.units)}${r30.roi != null ? ` · ${r30.roi > 0 ? "+" : ""}${r30.roi}% ROI` : ""}</p>` : ""}
        <p class="set-note fd-prof-note">One unit per post at the posted price, graded from the same results as the Record page. Picks lock at kickoff.</p>
      </section>
      ${follows}
      <div class="rec-windows fd-sub">${chips([["posts", "Posts"], ["record", "Graded picks"]], tab, "ptab")}</div>
      <div class="fd-list">${listHTML(F.posts, empty)}</div>
      ${F.more && tab !== "record" ? `<button class="btn ghost fd-load" data-fd="load" type="button">More posts</button>` : ""}
      </div>${railHTML()}</div>`;
  }

  function editProfileHTML() {
    if (!F.signedIn) return `${backBar("The Feed")}<p class="set-empty"><a href="#account">Sign in</a> to make a profile.</p>`;
    const m = F.me || {};
    const [lg, abbr] = (m.team || "").split(":");
    return `${headHTML(F.me ? "Edit profile" : "Create your profile", "")}${backBar(F.me ? "Your profile" : "The Feed")}
      <section class="card fd-edit">
        <div class="fd-edit-prev">${avatar({ ...m, handle: m.handle || "you" }, "xl")}</div>
        <label>Display name<input class="fd-input" id="fd-p-name" maxlength="30" value="${escapeAttr(m.name || "")}" placeholder="How your name shows"></label>
        <label>Handle<input class="fd-input" id="fd-p-handle" maxlength="20" value="${escapeAttr(m.handle || "")}" placeholder="3–20 letters, numbers or _"></label>
        <label>Bio <small id="fd-p-count">${(m.bio || "").length}/200</small><textarea class="fd-input" id="fd-p-bio" maxlength="200" rows="3" placeholder="Who you are, what you bet">${escapeHtml(m.bio || "")}</textarea></label>
        <fieldset class="fd-colors"><legend>Colour</legend>${[0, 1, 2, 3, 4, 5, 6, 7].map((i) =>
          `<label class="fd-swatch fd-c${i}"><input type="radio" name="fd-color" value="${i}"${(m.color || 0) === i ? " checked" : ""}><span class="sr-only">Colour ${i + 1}</span></label>`).join("")}</fieldset>
        <div class="fd-team-pick"><label>Favourite team<select class="fd-input" id="fd-p-lg">${SPORTS.map(([k, t]) =>
          `<option value="${k}"${k === (lg || "") ? " selected" : ""}>${k ? t : "None"}</option>`).join("")}</select></label>
          <label>Team code<input class="fd-input" id="fd-p-abbr" maxlength="12" value="${escapeAttr(abbr || "")}" placeholder="DET"></label></div>
        <p class="set-note">Your email is never shown. Slurs are refused in names and bios.</p>
        <div class="fd-row-end"><button class="btn" data-fd="save-profile" type="button">Save profile</button></div>
      </section>`;
  }

  const NOTE_WORDS = {
    like: "liked your post", tail: "tailed your parlay", comment: "commented on your post",
    reply: "replied to your comment", mention: "mentioned you", follow: "started following you",
    comment_like: "liked your comment", won: "Your parlay won", lost: "Your parlay lost",
  };

  function notesHTML(items) {
    const rows = (items || []).map((n) => {
      const actor = n.handle ? `<b>${escapeHtml(n.name || n.handle)}</b> ` : "";
      const href = n.post_id ? `#feed/post/${n.post_id}` : n.handle ? `#feed/u/${encodeURIComponent(n.handle)}` : "#feed";
      const mark = n.handle ? avatar(n, "sm") : `<span class="fd-av fd-av-sm fd-note-ic ${n.kind}">${icon(n.kind === "won" ? "check" : "cross", 12)}</span>`;
      return `<a class="fd-note${n.seen ? "" : " unseen"}" href="${href}">${mark}
        <span class="fd-note-t">${actor}${NOTE_WORDS[n.kind] || n.kind}${n.snippet ? `: <i>${escapeHtml(n.snippet)}</i>` : ""}
        <span class="fd-meta">${ago(n.at)}</span></span></a>`;
    }).join("");
    return `${headHTML("Notifications", "")}${backBar("The Feed")}
      <section class="card fd-notes">${rows || `<p class="set-empty">Nothing yet. Likes, comments, tails, new followers and your graded parlays show up here.</p>`}</section>`;
  }

  function leadersHTML(L) {
    const followBtn = (p) => (F.signedIn && (!F.me || p.handle !== F.me.handle)
      ? `<button class="btn ghost fd-follow-sm" data-fd="follow" data-handle="${escapeAttr(p.handle)}" type="button">${p.following ? "Following" : "Follow"}</button>` : "");
    const top = (L.top || []).map((p, i) => `<div class="fd-lead"><span class="fd-rank">${i + 1}</span>${who(p, { size: "sm" })}
      <span class="fd-lead-rec">${p.w}-${p.l}${p.p ? `-${p.p}` : ""}</span>
      <span class="fd-lead-u ${p.units >= 0 ? "up" : "down"}">${units(p.units)}</span>
      <span class="fd-lead-roi">${p.roi > 0 ? "+" : ""}${p.roi}%</span>${followBtn(p)}</div>`).join("");
    const tailed = (L.tailed || []).map((p, i) => `<div class="fd-lead"><span class="fd-rank">${i + 1}</span>${who(p, { size: "sm" })}
      <span class="fd-lead-u">${p.tails} tail${p.tails === 1 ? "" : "s"}</span>${followBtn(p)}</div>`).join("");
    return `${headHTML("Leaderboard", `units won over the last ${L.days || 30} days, ${L.min || 5}+ graded parlays to qualify`)}${backBar("The Feed")}
      <section class="card fd-leads"><h3>${icon("trophy", 16)} Top bettors</h3>${top || `<p class="set-empty">Nobody qualifies yet.</p>`}</section>
      <section class="card fd-leads"><h3>${icon("whale", 16)} Most tailed this week</h3>${tailed || `<p class="set-empty">No tails this week yet.</p>`}</section>
      <p class="set-note">One unit per post at the posted price. Graded automatically from the journal — nobody can type in a result.</p>`;
  }

  // ── loading and drawing ────────────────────────────────────────────────────
  async function loadRail() {
    const r = await api("rail");
    if (r.ok) F.rail = r.out;
  }

  async function loadHome(append) {
    const p = new URLSearchParams({ order: F.order, window: F.window, sport: F.sport, kind: F.kind });
    if (append) p.set(F.paged === "before" ? "before" : "offset", String(F.next || 0));
    const r = await api(`list?${p}`);
    if (!r.ok) { tfToast(r.out.error || "The feed did not load."); return; }
    const o = r.out;
    F.posts = append ? F.posts.concat(o.posts || []) : (o.posts || []);
    F.more = !!o.more;
    F.next = o.next || 0;
    F.paged = o.paged || "offset";
    F.me = o.me || null;
    F.signedIn = !!o.signed_in;
    F.unseen = o.unseen || 0;
    syncBadge();
  }

  async function ensureMe() {
    if (F._meAt && Date.now() - F._meAt < 30000) return;
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

  let _drawSeq = 0;
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
    const r = route();
    const [kind, arg, sub] = r.split("/");
    const paint = (html) => { if (seq === _drawSeq) el.innerHTML = html; };
    if (!r) {
      if (!append && !F.posts.length) paint(`${headHTML("The Feed", "")}<p class="set-note">Loading the feed…</p>`);
      await Promise.all([loadHome(append), F.rail ? null : loadRail()]);
      paint(homeHTML());
      return;
    }
    await ensureMe();
    if (kind === "post") {
      const res = await api(`post?id=${encodeURIComponent(arg || "")}`);
      F.post = res.ok ? res.out.post : null;
      if (!F.rail) await loadRail();
      paint(postPageHTML());
      return;
    }
    if (kind === "u") {
      const tab = sub === "record" ? "record" : "posts";
      const p = new URLSearchParams({ handle: arg || "", tab });
      if (append && F.next) p.set("before", String(F.next));
      const res = await api(`profile?${p}`);
      if (res.ok) {
        F.profile = res.out.profile;
        F.posts = append ? F.posts.concat(res.out.posts || []) : (res.out.posts || []);
        F.more = !!res.out.more;
        F.next = res.out.next || 0;
      } else {
        F.profile = null;
        F.posts = [];
      }
      if (!append) F.follows = null;
      if (!F.rail) await loadRail();
      paint(profileHTML(tab));
      return;
    }
    if (kind === "edit") { paint(editProfileHTML()); return; }
    if (kind === "notifications") {
      if (!F.signedIn) { paint(`${backBar("The Feed")}<p class="set-empty"><a href="#account">Sign in</a> to see your notifications.</p>`); return; }
      const res = await api("notifications");
      paint(notesHTML(res.ok ? res.out.items : []));
      if (res.ok && res.out.unseen) { await api("seen", {}); F.unseen = 0; syncBadge(); }
      return;
    }
    if (kind === "leaders") {
      const res = await api("leaders");
      paint(leadersHTML(res.ok ? res.out : {}));
      return;
    }
    go("");
  }

  // ── finding things on the page ─────────────────────────────────────────────
  const allPosts = () => [...F.posts, ...(F.search ? F.search.posts || [] : []), ...(F.post ? [F.post] : [])];
  const findPost = (id) => allPosts().find((p) => p.id === Number(id));

  function redraw(id) {
    const p = findPost(id);
    document.querySelectorAll(`.fd-post[data-post="${id}"]`).forEach((el) => {
      const slot = el.querySelector(".fd-slot");
      const keep = slot ? slot.innerHTML : "";
      const full = !!(F.post && F.post.id === Number(id) && route().startsWith("post/"));
      el.outerHTML = postHTML(p, full);
      const fresh = document.getElementById(`fd-slot-${id}`);
      if (fresh) fresh.innerHTML = keep;
    });
  }

  function sameAll(id, fn) { allPosts().filter((p) => p.id === Number(id)).forEach(fn); }

  const postUrl = (id) => `${location.origin}${location.pathname}#feed/post/${id}`;

  // ── actions ────────────────────────────────────────────────────────────────
  async function onAction(t, e) {
    const d = t.dataset;
    const act = d.fd;
    const id = d.id;
    if (act === "order" || act === "sport" || act === "kind" || act === "window") {
      F[act] = d.v; F.posts = []; F.search = null; return render();
    }
    if (act === "ptab") { const h = (F.profile || {}).handle || ""; return go(`u/${h}${d.v === "record" ? "/record" : ""}`); }
    if (act === "load") return render(true);
    if (act === "back") { if (history.length > 1) history.back(); else go(""); return; }
    if (act === "clear-search") { F.search = null; return render(); }
    if (act === "talk-open") { const f = document.getElementById("fd-talk"); if (f) { f.hidden = false; const ti = document.getElementById("fd-talk-title"); if (ti) ti.focus(); } return; }
    if (act === "talk-close") { const f = document.getElementById("fd-talk"); if (f) f.hidden = true; return; }
    if (act === "talk-post") {
      const res = await api("talk", { sport: (document.getElementById("fd-talk-sport") || {}).value || "",
        title: (document.getElementById("fd-talk-title") || {}).value || "",
        body: (document.getElementById("fd-talk-body") || {}).value || "" });
      if (!res.ok) { tfToast(res.out.error || "That did not post."); return; }
      tfToast("Posted.");
      F.order = "new"; F.posts = [];
      return go(`post/${res.out.id}`);
    }
    if (act === "like") {
      if (!signedInOrSay("like posts")) return;
      const res = await api("like", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      sameAll(id, (p) => { p.likes = res.out.likes; p.liked = res.out.liked; });
      buzz("tap"); redraw(id); return;
    }
    if (act === "tail") {
      if (!signedInOrSay("tail parlays")) return;
      const slot = document.getElementById(`fd-slot-${id}`);
      if (slot && slot.dataset.open === "tail") { slot.innerHTML = ""; slot.dataset.open = ""; return; }
      const res = await api("tail", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "Could not tail that."); return; }
      sameAll(id, (p) => { p.tails = res.out.tails; p.tailed = true; });
      buzz("tap"); redraw(id);
      const s2 = document.getElementById(`fd-slot-${id}`);
      if (s2) { s2.innerHTML = tailHTML(res.out); s2.dataset.open = "tail"; }
      return;
    }
    if (act === "share" || act === "copy") {
      const url = postUrl(id);
      if (act === "share" && navigator.share) {
        try { await navigator.share({ title: "Qellys Book", url }); } catch (err) { /* dismissed */ }
        return;
      }
      copyPlainText(url, act === "copy" ? t : null);
      return;
    }
    if (act === "menu") {
      const p = findPost(id);
      const slot = document.getElementById(`fd-slot-${id}`);
      if (!p || !slot) return;
      if (slot.dataset.open === "menu") { slot.innerHTML = ""; slot.dataset.open = ""; return; }
      slot.innerHTML = menuHTML(p); slot.dataset.open = "menu"; return;
    }
    if (act === "edit-post") {
      const p = findPost(id); const slot = document.getElementById(`fd-slot-${id}`);
      if (p && slot) { slot.innerHTML = editHTML(p); slot.dataset.open = "edit"; }
      return;
    }
    if (act === "save-post") {
      const p = findPost(id);
      const body = p && p.kind === "text"
        ? { id: Number(id), title: (document.getElementById(`fd-et-${id}`) || {}).value, body: (document.getElementById(`fd-eb-${id}`) || {}).value }
        : { id: Number(id), caption: (document.getElementById(`fd-ec-${id}`) || {}).value };
      const res = await api("edit", body);
      if (!res.ok) { tfToast(res.out.error || "That did not save."); return; }
      sameAll(id, (q) => { if (body.title != null) { q.title = body.title; q.body = body.body; } else q.caption = body.caption; q.edited = true; });
      const slot = document.getElementById(`fd-slot-${id}`); if (slot) { slot.innerHTML = ""; slot.dataset.open = ""; }
      redraw(id); return;
    }
    if (act === "del-post") {
      if (!confirm("Delete this post? Its likes, tails and comments go with it.")) return;
      const res = await api("delete", { kind: "post", id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not delete."); return; }
      F.posts = F.posts.filter((p) => p.id !== Number(id));
      tfToast("Deleted.");
      if (route().startsWith("post/")) return go("");
      return render();
    }
    if (act === "report") {
      const box = t.closest(".fd-menu");
      const reason = box && box.querySelector(".fd-reason") ? box.querySelector(".fd-reason").value : "other";
      const res = await api("report", { kind: d.kind, id: Number(id), reason });
      tfToast(res.ok ? "Reported — thanks. Three reports hide it until it is reviewed." : (res.out.error || "That did not go through."));
      return;
    }
    if (act === "block") {
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
      if (!signedInOrSay("follow people")) return;
      const res = await api("follow", { handle: d.handle });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      if (F.profile && F.profile.handle === d.handle) { F.profile.following = res.out.following; F.profile.followers = res.out.followers; }
      [...((F.rail || {}).leaders || []), ...((F.rail || {}).suggest || [])].forEach((p) => { if (p.handle === d.handle) p.following = res.out.following; });
      document.querySelectorAll(`[data-fd="follow"][data-handle="${CSS.escape(d.handle)}"]`).forEach((b) => {
        b.textContent = res.out.following ? "Following" : "Follow";
        b.classList.toggle("ghost", res.out.following || b.classList.contains("fd-follow-sm"));
      });
      if (route().startsWith("u/")) render();
      return;
    }
    if (act === "friend") {
      const res = await api("friend", { handle: d.handle });
      tfToast(res.ok ? (res.out.already ? "Request already sent." : "Friend request sent — it lands in their inbox.") : (res.out.error || "That did not go through."));
      return;
    }
    if (act === "follows" || act === "following-list") {
      const which = act === "follows" ? "followers" : "following";
      const res = await api(`follows?handle=${encodeURIComponent(d.handle)}&which=${which}`);
      F.follows = res.ok ? { which, people: res.out.people } : null;
      return render();
    }
    if (act === "close-follows") { F.follows = null; return render(); }
    if (act === "reply") {
      const slot = document.getElementById(`fd-rslot-${id}`);
      if (!slot) return;
      if (slot.innerHTML) { slot.innerHTML = ""; return; }
      slot.innerHTML = composerFor(F.post ? F.post.id : 0, Number(id));
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
      if (!signedInOrSay("like comments")) return;
      const res = await api("comment-like", { id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not go through."); return; }
      t.classList.toggle("on", res.out.liked);
      t.innerHTML = `${icon("heart", 12)} ${res.out.likes || ""}`;
      return;
    }
    if (act === "del-comment") {
      const res = await api("delete", { kind: "comment", id: Number(id) });
      if (!res.ok) { tfToast(res.out.error || "That did not delete."); return; }
      return render();
    }
    if (act === "save-profile") {
      const lg = (document.getElementById("fd-p-lg") || {}).value || "";
      const abbr = ((document.getElementById("fd-p-abbr") || {}).value || "").trim().toUpperCase();
      const color = (document.querySelector('input[name="fd-color"]:checked') || {}).value;
      const res = await api("profile", {
        handle: (document.getElementById("fd-p-handle") || {}).value || "",
        name: (document.getElementById("fd-p-name") || {}).value || "",
        bio: (document.getElementById("fd-p-bio") || {}).value || "",
        color: Number(color || 0), team: lg && abbr ? `${lg}:${abbr}` : "" });
      if (!res.ok) { tfToast(res.out.error || "That did not save."); return; }
      F.me = res.out.profile; F._meAt = Date.now(); F.rail = null;
      tfToast("Profile saved.");
      return go(`u/${F.me.handle}`);
    }
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest && e.target.closest("[data-fd]");
    if (!t || !t.closest("#view-feed")) return;
    e.preventDefault();
    onAction(t, e);
  });

  document.addEventListener("submit", async (e) => {
    const f = e.target.closest && e.target.closest('[data-fd-form="search"]');
    if (!f) return;
    e.preventDefault();
    const q = (f.querySelector("input") || {}).value || "";
    if (q.trim().length < 2) { F.search = null; render(); return; }
    const res = await api(`search?q=${encodeURIComponent(q.trim())}`);
    F.search = res.ok ? { q: q.trim(), ...res.out } : null;
    if (route()) { go(""); } else { render(); }
  });

  document.addEventListener("change", (e) => {
    if (e.target && e.target.id === "fd-strong") {
      try { localStorage.setItem(STRONG_KEY, e.target.checked ? "1" : "0"); } catch (err) {}
      F.posts = []; render();
    }
    if (e.target && e.target.name === "fd-color") {
      const prev = document.querySelector(".fd-edit-prev .fd-av");
      if (prev) prev.className = prev.className.replace(/fd-c\d/, `fd-c${e.target.value}`);
    }
  });

  document.addEventListener("input", (e) => {
    if (e.target && e.target.id === "fd-p-bio") {
      const c = document.getElementById("fd-p-count");
      if (c) c.textContent = `${e.target.value.length}/200`;
    }
  });

  // ── posting from the parlay slip ───────────────────────────────────────────
  function slipPostStart(slot) {
    slot.innerHTML = `<input class="fr-note fd-caption" maxlength="280"
        placeholder="Say something about it (optional) — @handle to mention" aria-label="Caption">
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
    if (res.out.need_handle) { tfToast(res.out.error); location.hash = "#feed/edit"; return; }
    if (!res.ok) { tfToast(res.out.error || "That did not post."); return; }
    tfToast(res.out.already ? "Already on the feed." : "Posted to the feed.");
    F.order = "new"; F.posts = [];
    location.hash = `#feed/post/${res.out.id}`;
  }

  window.QBSocial = { render, slipPostStart, slipPost };
})();
