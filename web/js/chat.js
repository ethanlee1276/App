/* THE GAME CHAT — a room for every game, a thread on every play.

   Ethan, 2026-10-25: "my buddy was telling me about an app that is better
   than ESPN ... it has like live chats on each game for the play-by-plays
   ... make it where we have like a live chat for each game so users can
   talk about their props". The app is Real; the parts taken, and whose:

   * Real — the play is the spine. Every big play carries a reaction
     counter and its own thread (the Plays tab here, and the bubble on each
     row of the play-by-play); the comments can be read All, Plays only or
     Game only; the chat is a full screen of its own.
   * theScore — the scoreboard pinned over the chat, and reacting to a play
     from inside it.
   * Yahoo Game Discussions — an account to post, the rules said once on
     the way in, Report on every message.
   * Sofascore and Real — "Who wins?" asked of the room, the split shown.
   * Sideline — a reader scrolled up is not yanked to the bottom; new
     messages wait under a pill.

   Opened from the floating Chat button on every game page (football,
   baseball, basketball, hockey — one button, so the four layouts need no
   seat of their own) or from a play's bubble, which opens that play's
   thread. The server is engine/gamechat; this file draws, polls and posts.
   Loaded with css/chat.css the first time a game page mounts it. */

const CHAT_POLL_MS = 3000;          // while the sheet is open
const CHAT_IDLE_MS = 12000;         // while it is closed: the badge and the play bubbles
const CHAT_RULES_KEY = "qb_chat_rules_v1";
const CHAT_FACES = [["fire", "\u{1F525}"], ["wow", "\u{1F62E}"], ["lol", "\u{1F602}"], ["ugh", "\u{1F629}"]];
const CHAT_FACE = Object.fromEntries(CHAT_FACES);
const CHAT_REASONS = [["spam", "Spam"], ["abuse", "Abuse"], ["hate", "Hate"], ["scam", "Selling picks or a scam"], ["other", "Something else"]];

const CH = {
  room: "", league: "", event: "", d: null,
  msgs: [], byId: new Map(), lastId: 0, firstId: 0, older: false, since: 0,
  plays: {}, threads: {}, minePlays: {}, votes: null, potg: null, remind: null, votePath: [], here: 0, me: null, friends: [],
  open: false, tab: "all", thread: "", replyTo: 0, bet: null, betOpen: false,
  unread: 0, timer: 0, busy: false, loaded: false, err: "", menu: 0,
  // A watch party (engine/gamechat): the reader's parties in this game, the
  // one on the Party tab, its messages (kept apart from the room's), and an
  // invite read off the address waiting for an account.
  parties: [], party: null, pmsgs: [], pLastId: 0, invite: "",
  // Karma (engine/karma): the room's heat, and the watching clock.
  hype: null, wtimer: 0, wfirst: false,
};

const chEsc = (s) => escapeHtml(String(s == null ? "" : s));

/* A PLAY IN WORDS, AND WHETHER IT IS A BIG ONE — one reading for the chat's
   play cards and the Live tab's feed of every game's big plays (Real's
   main screen). Football says it through footballWords (yards mean yards
   gained only on a run or a pass: a flag on a kick carries the try's
   distance and a punt its return); hockey's own events carry a kind
   rather than a word. */
const PLAY_RINK_WORD = { goal: "Goal", sog: "Shot on goal", miss: "Missed shot", block: "Blocked shot", hit: "Hit",
                         penalty: "Penalty", faceoff: "Faceoff win", takeaway: "Takeaway", giveaway: "Giveaway" };
function playTitleOf(p, d) {
  if (!p) return "this play";
  if (PLAY_RINK_WORD[p.kind]) return `${p.team ? `${p.team} ` : ""}${PLAY_RINK_WORD[p.kind]}${p.player ? ` — ${p.player}` : ""}`;
  if (p.kind === "football") {
    const w = footballWords(p, d || {});
    return `${p.team ? `${p.team} ` : ""}${w.title || p.event || "Play"}`;
  }
  if (p.kind === "atbat") return `${p.batter || "At-bat"}: ${p.event || ""}`.trim();
  const who = p.player || "";
  return `${who ? `${who} — ` : ""}${p.event || "Play"}`;
}
function playIsBig(p) {
  if (!p) return false;
  // Any play that moved the game, whatever kind (engine/playmoments.BIG).
  if (Number(p.rating) >= 4.5) return true;
  const e = String(p.event || "");
  if (p.kind === "football") {
    const gain = /rush|run|pass|reception|scramble/i.test(e) && !p.penalty ? Math.abs(Number(p.yards) || 0) : 0;
    const ret = /return|punt|kickoff/i.test(e) ? Number(p.yards) || 0 : 0;
    return !!(p.scoring || p.turnover || gain >= 20 || ret >= 40 || /sack|interception|fumble|blocked|safety/i.test(e));
  }
  // NOT `p.hit`: the rail's at-bats carry batted-ball data on every ball in
  // play, a groundout too. A run in, a homer, an extra-base hit, a double play.
  if (p.kind === "atbat") return !!(Number(p.rbi) > 0 || /home run|double play|triple play|^double$|^triple$/i.test(e));
  if (p.kind === "hoops") return !!((p.scoring && Number(p.points) === 3) || /dunk|block|steal|alley|technical|flagrant/i.test(e));
  if (PLAY_RINK_WORD[p.kind]) return p.kind === "goal" || p.kind === "penalty";
  return !!(p.scoring || /goal|penalty|fight/i.test(e));
}

/* REAL'S PLAY CARD, AND TWO THINGS IT DOESN'T SAY (Ethan's screenshot of
   Real, 2026-10-25: a walk-off homer's card — the score and the inning, a
   9.8 in the corner, "Walk-off 3-run 416' homer", the batter's and the
   pitcher's lines so far, "15th homer this season", the reactions, the
   comments, a share). Ours carries each of those where the feed has it,
   and adds the win chance before and after the play (the feed's own number,
   engine/playmoments) and whether it tied the game, put a side ahead or
   ended it. Every fact is counted off the game's own plays and box score;
   none is the model's. */
const PC_SWING = { walkoff: "Walk-off", go_ahead: "Go-ahead", tying: "Ties it" };
const PC_SFX = ["th", "st", "nd", "rd"];
const pcOrd = (n) => { const v = n % 100; return n + (PC_SFX[(v - 20) % 10] || PC_SFX[v] || "th"); };
const pcShort = (n) => { const w = String(n || "").trim().split(/\s+/); return w.length > 1 ? `${w[0][0]}. ${w.slice(1).join(" ")}` : w[0] || ""; };
const pcNorm = (n) => String(n || "").toLowerCase().replace(/[^a-z]/g, "");
function pcBox(players, name) {
  const k = pcNorm(name);
  return k ? (players || []).find((r) => pcNorm(r && r.player) === k) || null : null;
}

// His line so far, the way a box score says it: "1/5, 3 RBI", "0.1 IP, 1 K, 2 ER, 11 P".
function pcLine(r) {
  if (!r) return "";
  const L = r.line || {}, s = r.stats || {};
  const n = (v) => Math.round(Number(v) || 0);
  const join = (a) => a.filter(Boolean).join(", ");
  if (L.batting) { const b = L.batting; return join([`${n(b.h)}/${n(b.ab)}`, b.hr ? `${b.hr} HR` : "", b.rbi ? `${b.rbi} RBI` : "", b.bb ? `${b.bb} BB` : ""]); }
  if (L.pitching) { const q = L.pitching; return join([q.ip ? `${q.ip} IP` : "", `${n(q.k)} K`, q.er != null ? `${n(q.er)} ER` : "", q.p ? `${q.p} P` : ""]); }
  if (s.pass_att) return join([`${n(s.pass_cmp)}/${n(s.pass_att)}, ${n(s.pass_yds)} yds`, s.pass_td ? `${n(s.pass_td)} TD` : "", s.pass_int ? `${n(s.pass_int)} INT` : ""]);
  if (s.carries) return join([`${n(s.carries)} car, ${n(s.rush_yds)} yds`, s.rush_td ? `${n(s.rush_td)} TD` : ""]);
  if (s.receptions || s.rec_yds) return join([`${n(s.receptions)} rec, ${n(s.rec_yds)} yds`, s.rec_td ? `${n(s.rec_td)} TD` : ""]);
  if (s.pts != null) return join([`${n(s.pts)} pts`, s.reb ? `${n(s.reb)} reb` : "", s.ast ? `${n(s.ast)} ast` : ""]);
  return "";
}

// Who the card is about: the batter and the pitcher; a passer and his
// receiver; otherwise the one who did it (a kick's holder is not news).
function pcPeople(p) {
  if (p.kind === "atbat") return [p.batter, p.pitcher].filter(Boolean);
  const who = Array.isArray(p.players) && p.players.length ? p.players : p.player ? [p.player] : [];
  return /pass|reception/i.test(String(p.event || "")) ? who.slice(0, 2) : who.slice(0, 1);
}

function pcTitle(p, d) {
  const e = String(p.event || "");
  if (p.kind === "atbat" && /home run/i.test(e)) {
    const runs = Number(p.rbi) || 1;
    const t = [{ walkoff: "walk-off", go_ahead: "go-ahead", tying: "game-tying" }[p.swing] || "",
      p.distance ? `${p.distance}-ft` : "", runs >= 4 ? "grand slam" : `${runs > 1 ? `${runs}-run` : "solo"} homer`].filter(Boolean).join(" ");
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  if (p.kind === "atbat") return `${e}${Number(p.rbi) ? `, ${p.rbi} run${p.rbi > 1 ? "s" : ""} in` : ""}`;
  return playTitleOf(p, d);
}

// The win chance it moved, for the side that made the play — only where the
// feed gave one and the move is worth a line.
function pcWin(p, d) {
  if (typeof p.wp !== "number" || typeof p.wpa !== "number") return "";
  const side = p.kind === "atbat" ? (p.half === "T" ? "away" : "home")
    : p.team && p.team === d.away ? "away" : p.team && p.team === d.home ? "home" : p.wpa >= 0 ? "home" : "away";
  const was = p.wp - p.wpa;
  const [before, after] = side === "home" ? [was, p.wp] : [100 - was, 100 - p.wp];
  if (Math.abs(after - before) < 3) return "";
  return `${d[side] || ""} win chance ${Math.round(before)}% → ${Math.round(after)}%`.trim();
}

// The facts under it: a season count, a night's count, a run of points.
// `plays` is the game's list when the whole of it is in hand (the room);
// the Live tab's feed has only the recent big plays, which still hold
// every homer and touchdown.
function pcFacts(p, d, plays, full) {
  const out = [];
  const key = chatPlayKey(p);
  const i = (plays || []).findIndex((q) => chatPlayKey(q) === key);
  const upTo = i >= 0 ? plays.slice(0, i + 1) : [p];
  const e = String(p.event || "");
  if (p.kind === "atbat" && /home run/i.test(e)) {
    const tonight = upTo.filter((q) => q.batter === p.batter && /home run/i.test(q.event || "")).length || 1;
    const r = pcBox(d.players, p.batter);
    if (r && Number.isInteger(r.season_hr)) {
      // The box may be a pass behind the play, or ahead of it: his season as
      // of this homer is the box's season less the box's game, plus tonight's.
      const season = r.season_hr - Number(((r.line || {}).batting || {}).hr || 0) + tonight;
      if (season > 0) out.push(`${pcOrd(season)} homer this season`);
    }
    if (tonight >= 2) out.push(`${pcOrd(tonight)} homer tonight`);
  } else if (full && p.kind === "atbat" && /strikeout/i.test(e)) {
    const k = upTo.filter((q) => q.pitcher === p.pitcher && /strikeout/i.test(q.event || "")).length;
    if (k >= 5) out.push(`${pcShort(p.pitcher)}’s ${pcOrd(k)} strikeout tonight`);
  } else if (p.kind === "football" && p.scoring && /touchdown/i.test(e)) {
    const who = (p.players || [])[/pass/i.test(e) ? 1 : 0];
    const n = who ? upTo.filter((q) => q.scoring && /touchdown/i.test(q.event || "") && (q.players || []).includes(who)).length : 0;
    if (n >= 2) out.push(`${pcShort(who)}’s ${pcOrd(n)} touchdown today`);
  } else if (p.kind === "hoops" && p.scoring) {
    const pts = Number(((pcBox(d.players, p.player) || {}).stats || {}).pts);
    if (pts >= 20) out.push(`${pcShort(p.player)} has ${Math.round(pts)} points`);
  }
  return out;
}

function pcBodyHTML(p, d, plays, full) {
  d = d || {};
  const people = pcPeople(p);
  // Football and baseball name the player whether or not the box has his
  // line yet (a kicker's often has none); basketball's and hockey's
  // headlines carry the name already.
  const named = p.kind === "football" || p.kind === "atbat";
  const lines = people.map((n) => {
    const ln = pcLine(pcBox(d.players, n));
    return ln || named ? `<span class="pcard-line"><b>${chEsc(pcShort(n))}</b>${ln ? ` · ${chEsc(ln)}` : ""}</span>` : "";
  }).join("");
  const team = p.kind === "atbat" ? (p.half === "T" ? d.away : d.home) : p.team;
  const face = people[0] && typeof playerAvatar === "function" ? playerAvatar(people[0], team, { size: 40 }) : "";
  const win = pcWin(p, d);
  const chip = p.swing && !(p.kind === "atbat" && /home run/i.test(String(p.event || ""))) ? PC_SWING[p.swing] : "";
  return `<div class="pcard-row">${face ? `<span class="pcard-face">${face}</span>` : ""}<div class="pcard-main">
      ${chip ? `<span class="pcard-swing" data-swing="${chEsc(p.swing)}">${chip}</span>` : ""}
      <p class="pcard-title">${chEsc(pcTitle(p, d))}</p>${lines}
      ${win ? `<span class="pcard-win">${chEsc(win)}</span>` : ""}
      ${pcFacts(p, d, plays, full).map((f) => `<span class="pcard-fact">${chEsc(f)}</span>`).join("")}</div></div>`;
}

const pcRate = (p) => (p.rating != null
  ? `<span class="pcard-rate" title="How much this play moved the game, out of 10">${Number(p.rating).toFixed(1)}</span>` : "");
const PC_SHARE = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 8.5 13.5 3l-3 10.5-2.5-4.5z"/></svg>`;
function pcShareHTML(league, event, p, text) {
  return `<button type="button" class="pcard-share" data-pc-share data-league="${chEsc(league)}" data-event="${chEsc(event)}"
    data-play="${chEsc(chatPlayKey(p))}" data-text="${chEsc(text)}" aria-label="Share this play">${PC_SHARE}</button>`;
}

/* A play's own link — the game, opened on that play's thread (app.js
   openPbpHash keeps the play for chatMount) — by the phone's own share
   sheet, or copied where there is none. */
async function pcShare(btn) {
  const b = btn.dataset;
  const url = `${location.origin}/#pbp/${encodeURIComponent(b.league)}/${encodeURIComponent(b.event)}/play/${encodeURIComponent(b.play)}`;
  try {
    if (navigator.share) { await navigator.share({ title: b.text, text: b.text, url }); return; }
  } catch (e) { if (e && e.name === "AbortError") return; }
  try {
    await navigator.clipboard.writeText(`${b.text} ${url}`);
    btn.classList.add("done");
    btn.setAttribute("aria-label", "Link copied");
    setTimeout(() => { btn.classList.remove("done"); btn.setAttribute("aria-label", "Share this play"); }, 1600);
  } catch (e) {}
}

/* THE PLAY FEED (Real's main screen, 2026-10-25 — Ethan: "look at all
   these other play-by-play apps ... and basically just copy them"). Every
   game in progress, one list: the big plays (playIsBig), newest first by
   ESPN's own stamp (`at`, espnplays._wallclock) where a play carries one
   and by when this page first saw it where it does not, each with its
   thread's bubble and a door into the game (app.js keeps the Games/Feed
   switch and loads this room when Feed is chosen). */
const _pfSeen = new Map();

function playFeedItems(games) {
  const out = [];
  const now = Date.now();
  for (const { sport, g } of games || []) {
    const room = pfRoom(sport, g);
    if (!room) continue;
    // The card's recent big plays (livescore_build.BIG_PER_GAME) and its
    // last few, once each.
    const seen = new Set();
    for (const p of [...(g.big || []), ...(g.plays || [])]) {
      const key = chatPlayKey(p);
      if (!key || seen.has(key) || !playIsBig(p)) continue;
      seen.add(key);
      const id = `${room}:${key}`;
      if (!_pfSeen.has(id)) _pfSeen.set(id, now);
      out.push({ sport, g, p, room, at: Date.parse(p.at || "") || _pfSeen.get(id) });
    }
  }
  return out.sort((a, b) => b.at - a.at).slice(0, 60);
}

function pfItemHTML(x) {
  const { sport, g, p, room } = x;
  const lv = g.live || {};
  const [a, h] = p.away_score != null ? [p.away_score, p.home_score] : [lv.away_score, lv.home_score];
  const per = p.kind === "atbat" ? `${p.half === "T" ? "Top" : "Bot"} ${p.inning || ""}`
    : p.period ? (sport === "nhl" ? hockeyPeriod(p.period) : p.period <= 4 ? `Q${p.period}` : "OT") : "";
  const when = [per, p.kind === "football" ? fbClock(p.clock) : p.clock].filter(Boolean).join(" ");
  const secs = p.at ? Math.max(0, Math.round((Date.now() - Date.parse(p.at)) / 1000)) : null;
  const ago = secs == null || isNaN(secs) ? "" : secs < 60 ? "now" : secs < 3600 ? `${Math.round(secs / 60)}m` : `${Math.round(secs / 3600)}h`;
  const event = String(g.event_id || g.game_pk);
  const score = `${g.away || ""} ${a != null ? a : ""}–${h != null ? h : ""} ${g.home || ""}`;
  return `<article class="pf-item${p.scoring || p.kind === "goal" ? " pf-scored" : ""}${p.turnover ? " pf-turned" : ""}"
      data-pf-sport="${escapeAttr(sport)}" data-pf-event="${escapeAttr(event)}">
    <div class="pf-top"><span class="pf-lg">${(SPORT_META[sport] || {}).logo || ""}</span>
      <b>${escapeHtml(score)}</b>
      <span class="pf-when">${escapeHtml(when)}</span>${ago ? `<time class="pf-ago">${ago}</time>` : ""}${pcRate(p)}</div>
    ${pcBodyHTML(p, g, g.big || [], false)}
    <div class="pf-acts">${chatPlayBadge(room, p)}${pcShareHTML(sport, event, p, `${pcTitle(p, g)} · ${score}`)}<button type="button" class="pf-open">Open the game →</button></div>
  </article>`;
}

function playFeedHTML(games) {
  const items = playFeedItems(games);
  if (!items.length) {
    return `<div class="hd-quiet pf-quiet">No big plays yet. Scores, turnovers and the plays that swing a game land
      here from every game in progress, each with its own thread.</div>`;
  }
  return `<div class="pf-list">${items.map(pfItemHTML).join("")}</div>`;
}

/* Drawn into the Live tab's own slot, each card a door into its game (the
   bubble on it opens the play's thread instead — app.js captures it). */
function playFeedMount(host, games) {
  host.innerHTML = playFeedHTML(games);
  host.querySelectorAll(".pf-item").forEach((el) =>
    el.addEventListener("click", (e) => {
      const share = e.target.closest && e.target.closest("[data-pc-share]");
      if (share) { e.stopPropagation(); pcShare(share); return; }
      openPbp(el.dataset.pfSport, el.dataset.pfEvent);
    }));
}

let _pfCountsAt = 0;
/* The threads' sizes for every game on the tab, from the chat's own count
   (engine/gamechat.counts) — at most every fifteen seconds, and written
   into the bubbles already drawn rather than redrawing the tab. */
async function liveChatCounts(games) {
  if (Date.now() - _pfCountsAt < 15000) return;
  const rooms = [...new Set((games || []).map((x) => pfRoom(x.sport, x.g)).filter(Boolean))].slice(0, 40);
  if (!rooms.length) return;
  _pfCountsAt = Date.now();
  let v = null;
  try {
    const r = await fetch(`/api/chat/counts?rooms=${encodeURIComponent(rooms.join(","))}`, { cache: "no-store" });
    if (r.ok) v = await r.json();
  } catch (e) { v = null; }
  if (!v) return;
  window._chatPlayCounts = window._chatPlayCounts || {};
  for (const [room, c] of Object.entries(v.rooms || {})) {
    window._chatPlayCounts[room] = { ...(window._chatPlayCounts[room] || {}), ...((c || {}).plays || {}) };
  }
  document.querySelectorAll(".pr-chat[data-chat-room]").forEach((b) => {
    const n = ((window._chatPlayCounts[b.dataset.chatRoom] || {})[b.dataset.chatPlay]) || 0;
    const el = b.querySelector(".pr-chat-n");
    if (el) el.textContent = n ? String(n) : "";
    b.classList.toggle("has", n > 0);
  });
}

/* YOUR PLAYERS, LIVE (2026-10-25). Each player the reader follows, his
   line in the game he is in right now, every league on one strip at the
   top of the Live tab (engine/yourplayers, GET /api/alerts/live). The
   last strip is drawn at once on each poll's redraw, then refreshed, so
   it never blinks out while the tab repaints. */
let _ypLast = "";
function ypHTML(rows) {
  // A game saved for later (app.js spoiledG) keeps its players' lines to itself.
  rows = rows.filter((r) => !spoiledG(r.league, { event_id: r.event_id }));
  if (!rows.length) return "";
  return `<div class="yp"><div class="section-title">Your players
      <span class="sub">— their lines right now, from every game</span></div>
    <div class="yp-row">${rows.map((r) => `<button type="button" class="yp-item${r.state === "final" ? " is-final" : ""}"
        data-yp-sport="${chEsc(r.league)}" data-yp-event="${chEsc(r.event_id)}">
      <span class="yp-who">${chEsc(r.player)}</span>
      <span class="yp-line">${chEsc(r.line)}</span>
      <span class="yp-when">${chEsc(r.team)}${r.opp ? ` vs ${chEsc(r.opp)}` : ""} · ${chEsc(r.status)}</span>
      ${r.lineup ? `<span class="yp-ff">${ffPtsText(r.player)}</span>` : ""}
    </button>`).join("")}</div></div>`;
}

/* YOUR FANTASY LINEUP, LIVE (2026-10-28; docs/IDEAS.md). A Sleeper league
   linked on this device (ff_user, ff_league): the matchup as it stands
   over the strip (GET /api/leaguedesk?live=1, engine/fantasy_live:
   Sleeper's own points so far, the rest projected, the win chance), and
   the starters' box lines on the strip beside the players followed, each
   with his fantasy points so far (`lineup`, engine/yourplayers). Asked
   once a minute while a game is on and every five minutes otherwise,
   however often Live redraws. A starter in a game saved for later (app.js
   spoiledG) holds the matchup's score back. */
let _ffLive = null, _ffAt = 0;
async function ffLiveLoad() {
  let user = "", league = "";
  try { user = localStorage.getItem("ff_user") || ""; league = localStorage.getItem("ff_league") || ""; } catch (e) { /* storage off */ }
  const key = `${league}|${user}`;
  if (!user || !league) { _ffLive = null; return; }
  const wait = _ffLive && _ffLive.live && _ffLive.live.in_progress ? 60000 : 300000;
  if (_ffLive && _ffLive.key === key && Date.now() - _ffAt < wait) return;
  _ffAt = Date.now();
  try {
    const r = await fetch(`/api/leaguedesk?live=1&platform=sleeper&league=${encodeURIComponent(league)}`
      + `&user=${encodeURIComponent(user)}`, { credentials: "same-origin", cache: "no-store" });
    if (r.ok) _ffLive = { ...(await r.json()), key };
  } catch (e) { /* the last matchup stands until the next ask */ }
}
// The starters' names for the strip's own ask: only once a game is on.
function ffLineupQuery() {
  const me = _ffLive && _ffLive.live && _ffLive.live.me;
  const names = ((me && me.players) || []).map((p) => p.player).filter(Boolean);
  return names.length ? `?lineup=${encodeURIComponent(names.join("|"))}` : "";
}
const ffKey = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "").replace(/(jr|sr|ii|iii|iv|v)$/, "");
function ffPtsText(name) {
  const me = (_ffLive && _ffLive.live && _ffLive.live.me) || {};
  const p = (me.players || []).find((x) => x.player && ffKey(x.player) === ffKey(name));
  return p && p.points != null ? `In your lineup · ${Number(p.points).toFixed(1)} pts` : "In your lineup";
}
function ffHeld(v) {
  let all = {};
  try { all = JSON.parse(localStorage.getItem(SPOIL_KEY) || "{}") || {}; } catch (e) { all = {}; }
  const teams = new Set([...(v.me.players || []), ...((v.them || {}).players || [])].map((p) => p.team).filter(Boolean));
  const now = Date.now();
  return Object.values(all).some((x) => x && x.exp > now && x.l === "nfl" && (teams.has(x.a) || teams.has(x.h)));
}
function ffLiveHTML() {
  const v = _ffLive && _ffLive.live;
  if (!v || !v.me) return "";
  const them = v.them || {}, held = ffHeld(v);
  const pts = (n) => (held ? "–" : (Number(n) || 0).toFixed(1));
  const wp = v.win_prob == null || held ? "" : ` · <b class="${v.win_prob >= 0.5 ? "ffl-up" : "ffl-down"}">${Math.round(v.win_prob * 100)}%</b> to win`;
  const sub = held ? "Spoiler-free: a game in it is saved for later"
    : v.done ? "Final" : `Projected ${pts(v.me.projected)}–${pts(them.projected)}`;
  return `<a class="ffl" href="#fantasy">
    <span class="ffl-k">Your matchup · ${chEsc(_ffLive.league || "your league")}${_ffLive.week ? ` · week ${chEsc(_ffLive.week)}` : ""}</span>
    <span class="ffl-s"><span>You <b>${pts(v.me.points)}</b></span> <span>${chEsc(v.opponent || "Them")} <b>${pts(them.points)}</b></span></span>
    <span class="ffl-sub">${sub}${wp}</span></a>`;
}
/* Karma (js/karma.js): the level, the way to the next and the day's quests,
   in a strip over Your players. */
function ypKarma(host) {
  let kh = host.previousElementSibling;
  if (!(kh && kh.classList.contains("kr-strip-host"))) {
    kh = document.createElement("div");
    kh.className = "kr-strip-host";
    host.before(kh);
  }
  if (typeof loadRoom === "function") {
    loadRoom("js/karma.js", "css/karma.css").then((ok) => { if (ok && typeof karmaStripMount === "function") karmaStripMount(kh); });
  }
}
function ypBind(host) {
  host.querySelectorAll(".yp-item").forEach((b) =>
    b.addEventListener("click", () => openPbp(b.dataset.ypSport, b.dataset.ypEvent)));
}
async function yourPlayersMount(host) {
  if (!host || !(typeof _acctUser !== "undefined" && _acctUser && _acctUser.signed_in)) return;
  ypKarma(host);
  if (_ypLast || _lvmLast) { host.innerHTML = _lvmLast + _ypLast; ypBind(host); }
  let v = null;
  try {
    const [r] = await Promise.all([ffLiveLoad().then(() => fetch("/api/alerts/live" + ffLineupQuery(),
      { credentials: "same-origin", cache: "no-store" })), lvmLoad()]);
    if (r.ok) v = await r.json();
  } catch (e) { v = null; }
  if (!host.isConnected) return;
  if (v) _ypLast = ffLiveHTML() + ypHTML(v.players || []);
  host.innerHTML = _lvmLast + _ypLast;
  ypBind(host);
}

/* THE WAY INTO THE PAID SITE FROM THE FREE ONE (Ethan, 2026-10-25, the Live
   tab on his phone: "make sure there's [a way] to get into the paid site
   from this free version"). Over the strip, for a signed-in reader without
   a plan: how many picks are up today, by league, and the door to the
   plans. A count, never a pick (engine/firstlook); asked again at most
   every five minutes however often Live redraws. Named lvm*, never mb*:
   mbLoad is My Bets' loader, and a second one here replaced it. */
let _lvmLast = "";
let _lvmAt = 0;
async function lvmLoad() {
  const trial = lvmTrialHTML(typeof _pwStatus !== "undefined" ? _pwStatus : null);
  if (trial) { _lvmLast = trial; return; }
  const want = typeof isWalled === "function" && isWalled() && (typeof storeSells !== "function" || storeSells());
  if (!want) { _lvmLast = ""; return; }
  if (_lvmLast && Date.now() - _lvmAt < 300000) return;
  let fl = null;
  try {
    const r = await fetch("/api/firstlook", { credentials: "same-origin", cache: "no-store" });
    if (r.ok) fl = await r.json();
  } catch (e) { fl = null; }
  _lvmAt = Date.now();
  _lvmLast = lvmHTML(fl);
}

function lvmHTML(fl) {
  const t = ((fl && fl.tonight) || []).filter((x) => Number(x.picks) > 0);
  const n = t.reduce((a, x) => a + Number(x.picks), 0);
  return `<a class="lvm-strip" href="#paywall">
    <span class="lvm-ic" aria-hidden="true">${icon("lock", 14)}</span>
    <span class="lvm-txt"><b>${n ? `${n} pick${n === 1 ? "" : "s"} up for members today` : "Members get every pick before the game"}</b>
      <span>${n ? t.slice(0, 4).map((x) => `${chEsc(x.league)} ${Number(x.picks)}`).join(" · ")
        : "Most Likely, parlays, Ask Qellys and Zeno’s bets"}</span></span>
    <span class="lvm-go">Get picks</span></a>`;
}

/* A member on the free trial, in its place: when the trial turns into a
   charge, what is charged, and the way to cancel. The Live tab's half of
   engine/trialnote's day-before email, and the only half a phone account
   (no address) gets. Gone once they cancel, and in a store build that sells
   nothing. In the reader's own zone (tzTime), not Eastern: it is their card. */
function lvmTrialHTML(s) {
  if (!s || s.status !== "trialing" || !Number(s.period_end) || s.cancel_at_end) return "";
  if (typeof storeSells === "function" && !storeSells()) return "";
  const t = Number(s.period_end) * 1000;
  if (t <= Date.now()) return "";
  // Days counted in the zone every clock on the site reads in (tzOpts).
  const ymd = (x) => Date.parse(new Intl.DateTimeFormat("en-CA", tzOpts({})).format(new Date(x)));
  const days = Math.round((ymd(t) - ymd(Date.now())) / 864e5);
  const day = days <= 0 ? "today" : days === 1 ? "tomorrow"
    : `on ${new Date(t).toLocaleDateString(undefined, tzOpts({ weekday: "long", month: "short", day: "numeric" }))}`;
  const clock = tzTime(t);
  const pl = (typeof PLANS !== "undefined" ? PLANS : []).find((p) => p.id === (s.plan || "monthly"));
  const then = pl ? `Then $${pl.price} ${pl.months === 1 ? "a month" : pl.months === 12 ? "a year" : `every ${pl.months} months`}. ` : "";
  return `<a class="lvm-strip lvm-trial" href="#account">
    <span class="lvm-ic" aria-hidden="true">${icon("clock", 14)}</span>
    <span class="lvm-txt"><b>Your free trial ends ${chEsc(day)} at ${chEsc(clock)}</b>
      <span>${chEsc(then)}Cancel before then and you pay nothing.</span></span>
    <span class="lvm-go">Manage</span></a>`;
}

/* The fast scoreboard's row for a room, so a thread opened from the Live
   tab can name its play before the game's own file is open. */
function chatRowFor(room) {
  const m = /^([a-z]+)_(\d+)$/.exec(String(room || ""));
  if (!m) return null;
  const hit = ((typeof _liveAll !== "undefined" && _liveAll.all) || [])
    .find((x) => x.sport === m[1] && String(x.g.event_id || x.g.game_pk || "") === m[2]);
  return hit ? hit.g : null;
}
/* ---------------- mounting ---------------- */

/* The game page calls this on every draw. A new game resets the room; the
   same game only refreshes what the sheet shows of it (the scoreboard, the
   plays) and leaves the conversation where it is. */
function chatMount(league, event, d) {
  const room = league && event ? `${league}_${event}` : "";
  if (!/^(nfl|cfb|nba|wnba|nhl|mlb)_\d{1,14}$/.test(room)) return;
  if (room !== CH.room) {
    chatReset();
    Object.assign(CH, { room, league, event });
  }
  CH.d = d || CH.d;
  chatFab();
  if (CH.open) { chatDrawHead(); if (CH.tab === "plays" || CH.thread) chatDrawBody(); }
  if (!CH.timer) chatSchedule(0);
  // Karma: the tiers' colours for the levels beside names, and the
  // watching clock (chatWatchTick).
  if (typeof loadRoom === "function") loadRoom("js/karma.js", "css/karma.css");
  if (!CH.wtimer) chatWatchArm();
  // A shared play's link lands on its thread (pcShare; app.js openPbpHash).
  const want = window._chatWantPlay;
  if (want && want.room === room) { window._chatWantPlay = null; chatOpen({ play: want.play }); }
  // A watch party's invite, #pbp/{league}/{event}/party/{token} (chatPartyLink),
  // handed over by app.js openPbpHash before the page's own address replaced it.
  const inv = window._chatWantParty;
  if (inv && inv.room === room) window._chatWantParty = null;
  let kept = null;
  try { kept = JSON.parse(localStorage.getItem(PARTY_INVITE_KEY) || "null"); } catch (e) { kept = null; }
  const token = inv && inv.room === room && /^[A-Za-z0-9_-]{8,40}$/.test(inv.token) ? inv.token
    : kept && kept.room === room && Date.now() - kept.at < 86400000
      && typeof _acctUser !== "undefined" && _acctUser && _acctUser.signed_in ? kept.token : "";
  if (token && token !== CH.invite) { CH.invite = token; chatJoinParty(); }
}

/* WATCH PARTIES (2026-10-28, engine/gamechat; docs/IDEAS.md). A private
   thread inside the game's room for a group of friends: start one on the
   Party tab, send its link, and whoever opens it with a free account is in.
   Its messages are its members' alone; the room's rules hold in it. */
function chatPartyLink(p) {
  return `${location.origin}/#pbp/${encodeURIComponent(CH.league)}/${encodeURIComponent(CH.event)}/party/${encodeURIComponent(p.token)}`;
}
const PARTY_INVITE_KEY = "qb_party_invite";
async function chatJoinParty() {
  const out = await chatPost("join", { token: CH.invite });
  if (out.status === 401) {
    // Kept for when this game is opened again with an account (a day at most).
    try { localStorage.setItem(PARTY_INVITE_KEY, JSON.stringify({ room: CH.room, token: CH.invite, at: Date.now() })); } catch (e) {}
    chatOpen({ tab: "party" });  // the composer becomes the account door
    return;
  }
  try { localStorage.removeItem(PARTY_INVITE_KEY); } catch (e) {}
  if (out.status !== 200) { CH.err = out.error || ""; chatOpen({ tab: "party" }); return; }
  CH.invite = "";
  chatUseParty(out);
  chatOpen({ tab: "party" });
}
function chatUseParty(p) {
  if (p && CH.party && CH.party.id === p.id) { CH.party = { ...CH.party, ...p }; return; }
  (CH.pmsgs || []).forEach((m) => CH.byId.delete(m.id));
  CH.party = p || null;
  CH.pmsgs = [];
  CH.pLastId = 0;
}

/* Open the sheet — on a play's thread when one is named. */
function chatOpen(opts) {
  const o = opts || {};
  if (o.room && o.room !== CH.room) {
    const m = /^([a-z]+)_(\d+)$/.exec(o.room);
    if (!m) return;
    chatMount(m[1], m[2], o.d || chatRowFor(o.room));
  } else if (o.d && !CH.d) CH.d = o.d;
  if (!CH.room) return;
  CH.open = true;
  CH.thread = o.play ? String(o.play) : "";
  if (!o.play && o.tab) CH.tab = o.tab;
  CH.unread = 0;
  chatSheet();
  chatSchedule(0);
}

/* The who-wins vote through the game, [at, home, away] a mark (the server's
   chat_vote_marks), for the game page's win-chance chart. */
function chatVotePath() {
  return CH.votePath || [];
}

function chatReset() {
  clearTimeout(CH.timer);
  clearTimeout(CH.wtimer);
  Object.assign(CH, { room: "", league: "", event: "", d: null, msgs: [], byId: new Map(), lastId: 0,
    firstId: 0, older: false, since: 0, plays: {}, threads: {}, minePlays: {}, votes: null, potg: null, remind: null, votePath: [], here: 0, friends: [],
    open: false, tab: "all", thread: "", replyTo: 0, bet: null, betOpen: false, unread: 0, timer: 0,
    loaded: false, err: "", menu: 0, parties: [], party: null, pmsgs: [], pLastId: 0, invite: "",
    hype: null, wtimer: 0, wfirst: false });
  const s = document.getElementById("gch-sheet");
  if (s) s.remove();
  document.body.classList.remove("gch-on");
}

/* Off a game page, the button goes; off the Live tab too (where a play's
   bubble can open a thread), the sheet goes and the clock stops. */
const chatOnGame = () => state.view === "pbp" || state.view === "game";
function chatGone() {
  return !(chatOnGame() || state.view === "live");
}
function chatTeardown() {
  chatReset();
  const f = document.getElementById("gch-fab");
  if (f) f.remove();
}
// Read off the address, not state.view: on a computer the page switch runs
// through a view transition and state.view is still the game for a moment,
// which left the chat bar sitting on the Live tab.
window.addEventListener("hashchange", () => setTimeout(() => {
  const v = (location.hash || "").replace(/^#/, "").split("/")[0];
  const game = v === "pbp" || v === "game";
  if (!game && v !== "live") chatTeardown();
  else if (!game) { const f = document.getElementById("gch-fab"); if (f) f.remove(); }
}, 0));

/* ---------------- the poll ---------------- */

function chatSchedule(ms) {
  clearTimeout(CH.timer);
  CH.timer = setTimeout(chatTick, ms);
}

async function chatTick() {
  CH.timer = 0;
  if (chatGone()) { chatTeardown(); return; }
  if (!CH.room) return;
  if (document.hidden) { chatSchedule(CHAT_IDLE_MS); return; }
  await chatPull();
  chatSchedule(CH.open ? CHAT_POLL_MS : CHAT_IDLE_MS);
}

async function chatPull(older) {
  if (CH.busy) return;
  CH.busy = true;
  const q = new URLSearchParams({ room: CH.room });
  const asked = CH.party ? CH.party.id : 0;
  if (older) q.set("before", String(CH.firstId));
  else if (CH.lastId) { q.set("after", String(CH.lastId)); q.set("since", String(CH.since)); }
  // The feed's own switch for strong language (Social settings): the reader's choice, kept in one place.
  try { if (localStorage.getItem("qb_feed_strong") === "1") q.set("strong", "1"); } catch (e) {}
  if (CH.party) { q.set("party", String(CH.party.id)); if (CH.pLastId) q.set("pafter", String(CH.pLastId)); }
  let v = null;
  try {
    const r = await fetch(`/api/chat/room?${q}`, { credentials: "same-origin", cache: "no-store" });
    if (r.ok) v = await r.json();
  } catch (e) { v = null; }
  CH.busy = false;
  if (!v || v.room !== CH.room) return;
  const fresh = [];
  for (const m of v.messages || []) {
    if (CH.byId.has(m.id)) continue;
    CH.byId.set(m.id, m);
    fresh.push(m);
  }
  if (older) {
    CH.msgs = fresh.concat(CH.msgs);
    CH.older = !!v.older;
  } else {
    CH.msgs = CH.msgs.concat(fresh);
    if (!CH.loaded) CH.older = !!v.older;
  }
  CH.msgs.sort((a, b) => a.id - b.id);
  if (CH.msgs.length) { CH.firstId = CH.msgs[0].id; CH.lastId = CH.msgs[CH.msgs.length - 1].id; }
  // Faces that moved on messages already on screen since the last ask —
  // to zero too, which is why the server reports a taken-back face as an
  // emptied row rather than a deleted one.
  for (const [id, faces] of Object.entries(v.reacts || {})) {
    const m = CH.byId.get(Number(id));
    if (m) m.reacts = faces;
  }
  Object.assign(CH.plays, v.plays || {});
  Object.assign(CH.threads, v.threads || {});
  Object.assign(CH.minePlays, v.mine_plays || {});
  CH.votes = v.votes || CH.votes;
  // The game is final: the fans' player of the game (engine/gamechat potg).
  CH.potg = v.potg || CH.potg || null;
  // Not started yet: the bell (engine/gamechat remind); gone once it starts.
  CH.remind = v.remind || null;
  CH.votePath = v.vote_path || CH.votePath || [];
  // The room against the math: the game page's chart draws the vote
  // through the game (js/detail.js pbpRoomLine) whenever it moves.
  if (typeof pbpRoomLine === "function") pbpRoomLine();
  CH.here = v.here || 0;
  CH.friends = Array.isArray(v.friends) ? v.friends : [];
  CH.me = v.me || CH.me;
  CH.hype = v.hype || null;
  if (CH.hype && CH.hype.karma) chatKarma(CH.hype.karma);
  // The reader's parties: the newest joined is the Party tab's, unless one is chosen.
  // (Not when a party was started, joined or left while this ask was out.)
  if (Array.isArray(v.parties) && (CH.party ? CH.party.id : 0) === asked) {
    CH.parties = v.parties;
    chatUseParty((CH.party && v.parties.find((p) => p.id === CH.party.id)) || v.parties[0] || null);
  }
  let pfresh = [];
  if (v.party && CH.party && v.party.id === CH.party.id) {
    pfresh = (v.party.messages || []).filter((m) => !CH.byId.has(m.id));
    pfresh.forEach((m) => CH.byId.set(m.id, m));
    CH.pmsgs = CH.pmsgs.concat(pfresh).sort((a, b) => a.id - b.id);
    if (CH.pmsgs.length) CH.pLastId = CH.pmsgs[CH.pmsgs.length - 1].id;
  }
  if (!older) CH.since = v.t || CH.since;
  // The play bubbles on the page read these (app.js chatPlayBadge).
  chatShareCounts();
  if (!CH.open && CH.loaded) CH.unread += fresh.filter((m) => !m.own).length;
  const first = !CH.loaded;
  CH.loaded = true;
  chatFab();
  if (CH.open) {
    // Opened before the first answer (an invite does): who is reading is known now.
    if (first) chatDrawFoot();
    if (first || older) chatDrawBody({ keep: older });
    else if (CH.tab === "party" && !CH.thread) { if (pfresh.length) chatDrawBody(); }
    else chatAppend(fresh, v);
    chatDrawHead();
    chatDrawTabs();
  }
}

function chatShareCounts() {
  const out = {};
  for (const [k, faces] of Object.entries(CH.plays)) {
    out[k] = Object.values(faces || {}).reduce((a, b) => a + b, 0);
  }
  for (const [k, n] of Object.entries(CH.threads)) out[k] = (out[k] || 0) + n;
  window._chatPlayCounts = window._chatPlayCounts || {};
  window._chatPlayCounts[CH.room] = out;
  document.querySelectorAll(`[data-chat-room="${CH.room}"][data-chat-play]`).forEach((b) => {
    const n = out[b.dataset.chatPlay] || 0;
    const el = b.querySelector(".pr-chat-n");
    if (el) el.textContent = n ? String(n) : "";
    b.classList.toggle("has", n > 0);
  });
}

/* Every write names the room; the server rebuilds each field it keeps, so
   nothing else in the body lands anywhere. The answer comes back with its
   status beside it, so a caller can tell "sign in" (401) from "pick a
   username" (409) from "slow down" (429) without a second read. */
async function chatPost(path, body) {
  try {
    const r = await fetch(`/api/chat/${path}`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room: CH.room, ...body }),
    });
    let out = {};
    try { out = await r.json(); } catch (e) { out = {}; }
    // What it earned (engine/karma): a message, a reaction, a vote, a party.
    if (out && out.karma) chatKarma(out.karma);
    return { status: r.status, ...out };
  } catch (e) {
    return { status: 0, error: "No connection — try again." };
  }
}

/* ---------------- the floating button ---------------- */

/* THE WAY IN (2026-10-25, Ethan: "it's hidden in the corner of the live
   page, so it's hard to see"). Two doors, both live:
     - a card on the game page itself, under the scoreboard (chatEntryPaint):
       how many are watching, the last few messages, the room's who-wins
       split, and Join — Twitch's and YouTube's chat sits beside the
       picture, not behind a button;
     - on a phone, a bar across the bottom above the tab bar with the
       newest message in it (YouTube's collapsed live chat), not a pill in
       the corner. On a computer the same bar is a labelled button. */
function chatLast() {
  const ok = CH.msgs.filter((m) => m.body && chatReady(m));
  return ok.length ? ok[ok.length - 1] : null;
}
function chatFab() {
  let f = document.getElementById("gch-fab");
  chatEntryPaint();
  if (!chatOnGame() || !CH.room) { if (f) f.remove(); return; }
  if (!f) {
    f = document.createElement("button");
    f.type = "button";
    f.id = "gch-fab";
    f.className = "gch-fab";
    f.addEventListener("click", () => chatOpen({}));
    document.body.appendChild(f);
  }
  f.hidden = CH.open;
  const n = CH.unread, last = chatLast();
  f.setAttribute("aria-label", `Open the game chat${n ? `, ${n} new` : ""}${CH.here ? `, ${CH.here} watching` : ""}`);
  const html = `<span class="gch-fab-ico">${chatIcon()}</span><span class="gch-fab-main"><b>Game chat${
    CH.here > 1 ? `<span class="gch-fab-here"><i></i>${CH.here}</span>` : ""}</b><span class="gch-fab-last">${last
    ? `<b>@${chEsc((last.by || {}).handle || "")}</b> ${chEsc(String(last.body).slice(0, 80))}` : "Say something about the game"}</span></span>${
    n ? `<span class="gch-fab-new">${n > 99 ? "99+" : n}</span>` : ""}<span class="gch-fab-go" aria-hidden="true">›</span>`;
  // Rewritten only when it says something new: a tap that lands while the
  // bar is being rewritten hits a node that is gone, and does nothing.
  if (f._html !== html) { f._html = html; f.innerHTML = html; }
}

/* The card on the game page (detail.js, hoopscast.js and rinkcast.js leave
   an empty `.gch-entry-slot` under the scoreboard).

   ONE CARD, KEPT (2026-10-26, Ethan: the buttons to the game chat "glitch
   out"). The game page redraws on every play and the room polls every few
   seconds, and the card used to be rebuilt on each — about every two
   seconds — so a tap that landed mid-rebuild hit a button that no longer
   existed. Now one button lives for the whole visit: a redraw moves it into
   the new slot, and only what it says changes, only when it changes. */
function chatEntryPaint() {
  const slot = document.querySelector(".gch-entry-slot");
  if (!slot) return;
  const rows = CH.msgs.filter((m) => m.body && chatReady(m)).slice(-3);
  const d = CH.d || {}, v = CH.votes;
  const total = v ? (v.away || 0) + (v.home || 0) : 0;
  const pct = (x) => (total ? Math.round((100 * x) / total) : 50);
  const poll = v && total && d.home && d.away ? `<div class="gch-entry-poll"><span>${chEsc(d.away)} ${pct(v.away || 0)}%</span>
      <span class="gch-entry-bar" style="--gch-away:${pct(v.away || 0)}%"></span><span>${pct(v.home || 0)}% ${chEsc(d.home)}</span></div>` : "";
  const html = `<span class="gch-entry-h"><span class="gch-entry-ico">${chatIcon()}</span><b>Game chat</b>${
        CH.here > 1 ? `<span class="gch-entry-live"><i></i>${CH.here} watching</span>` : ""}<span class="gch-entry-go">${
        CH.unread ? `${CH.unread} new · ` : ""}Join</span></span>
      <span class="gch-entry-msgs">${rows.length ? rows.map((m) => {
        const c = Math.abs(Number((m.by || {}).color || 0)) % 8;
        return `<span class="gch-entry-m"><b class="gch-c${c}">@${chEsc((m.by || {}).handle || "")}</b> ${chEsc(String(m.body).slice(0, 90))}</span>`;
      }).join("") : `<span class="gch-entry-m gch-entry-quiet">${CH.loaded ? "Nobody has said anything yet — start it off." : "Opening the room…"}</span>`}</span>
      ${poll}`;
  if (!CH.card) {
    CH.card = document.createElement("button");
    CH.card.type = "button";
    CH.card.className = "gch-entry";
    CH.card.dataset.gchEntry = "1";
    CH.card.addEventListener("click", () => chatOpen({}));
    // While the card is on screen the bar at the bottom would say the same
    // thing twice; it comes back once the card scrolls away.
    if (typeof IntersectionObserver === "function") {
      new IntersectionObserver((seen) => {
        document.body.classList.toggle("gch-card-in", seen.some((x) => x.isIntersecting));
      }).observe(CH.card);
    }
  }
  if (CH.cardHTML !== html) { CH.cardHTML = html; CH.card.innerHTML = html; }
  if (CH.card.parentNode !== slot) slot.replaceChildren(CH.card);
  chatBellPaint(slot);
}

/* REMIND ME (theScore's "notify me"): on a game that has not started, a
   bell under the chat card; set, the phones signed in to the account hear
   ten minutes before it starts (engine/gamechat remind). */
function chatBellPaint(slot) {
  let el = slot.querySelector(".gch-bell");
  const r = CH.remind;
  if (!r) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement("button");
    el.type = "button";
    el.className = "gch-bell";
    el.addEventListener("click", chatBellToggle);
    slot.appendChild(el);
  }
  const html = `<span aria-hidden="true">🔔</span><span>${r.on ? "Reminder set: a push 10 minutes before it starts"
    : "Remind me 10 minutes before it starts"}</span>${r.on ? "<b>On</b>" : ""}`;
  if (el._html !== html) { el._html = html; el.innerHTML = html; }
  el.classList.toggle("on", !!r.on);
  el.setAttribute("aria-pressed", String(!!r.on));
}

async function chatBellToggle() {
  const r = CH.remind;
  if (!r) return;
  const out = await chatPost("remind", { on: !r.on });
  if (out.status === 401) return chatNeedAccount();
  if (out.status !== 200) { if (out.error && typeof tfToast === "function") tfToast(out.error); return; }
  CH.remind = { ...r, on: !!out.on };
  chatEntryPaint();
  if (typeof tfToast === "function") {
    tfToast(!out.on ? "Reminder off." : Number(out.phones) ? "Set: your phone hears 10 minutes before it starts."
      : "Set. Turn on alerts for this phone in Settings, under Alerts, and the reminder comes with them.");
  }
}

const chatIcon = () => `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>`;

/* ---------------- the sheet ---------------- */

function chatSheet() {
  let s = document.getElementById("gch-sheet");
  if (!s) {
    s = document.createElement("section");
    s.id = "gch-sheet";
    s.className = "gch-sheet";
    s.setAttribute("role", "dialog");
    s.setAttribute("aria-label", "Game chat");
    s.innerHTML = `<header class="gch-head"></header><div class="gch-poll"></div><div class="gch-heat" hidden></div><div class="gch-tix" hidden></div>
      <nav class="gch-tabs" role="tablist"></nav>
      <div class="gch-body" tabindex="-1"></div>
      <button type="button" class="gch-newpill" hidden></button>
      <footer class="gch-foot"></footer>`;
    document.body.appendChild(s);
    s.addEventListener("click", chatClick);
    s.addEventListener("keydown", (e) => { if (e.key === "Escape") chatClose(); });
    s.querySelector(".gch-body").addEventListener("scroll", chatScrolled, { passive: true });
  }
  document.body.classList.add("gch-on");
  chatFab();
  chatDrawHead();
  chatDrawTabs();
  chatDrawBody();
  chatDrawFoot();
  const box = s.querySelector(".gch-input");
  if (box && window.matchMedia("(pointer: fine)").matches) box.focus();
}

function chatClose() {
  CH.open = false;
  CH.thread = "";
  CH.menu = 0;
  const s = document.getElementById("gch-sheet");
  if (s) s.remove();
  document.body.classList.remove("gch-on");
  chatFab();
  chatSchedule(CHAT_IDLE_MS);
}

/* The scoreboard, pinned (theScore): both sides, the score, the clock. */
function chatDrawHead() {
  const s = document.getElementById("gch-sheet");
  if (!s) return;
  const d = CH.d || {};
  const lv = d.live || {};
  const lg = CH.league;
  const side = (abbr, score, home) => `<div class="gch-side${home ? " home" : ""}">${
    typeof teamMarkIn === "function" && abbr ? teamMarkIn(lg, abbr, 26) : ""}<b>${chEsc(abbr || "")}</b><span class="gch-score">${
    score != null ? chEsc(score) : ""}</span></div>`;
  const mid = lv.state === "live"
    ? `<span class="gch-live"><i></i>LIVE</span><span class="gch-clock">${chEsc(lv.detail || [lv.period, lv.clock].filter(Boolean).join(" "))}</span>`
    : lv.state === "final" ? `<span class="gch-clock">FINAL</span>`
    : `<span class="gch-clock">${chEsc(lv.detail || "Pregame")}</span>`;
  s.querySelector(".gch-head").innerHTML = `
    <div class="gch-headrow"><span class="gch-title">${chatIcon()}Game chat</span><span class="gch-here">${
      CH.here ? `<i></i>${CH.here} watching` : ""}${chatFriendsHere()}</span>
      <button type="button" class="gch-x" data-gch="close" aria-label="Close the chat">${typeof icon === "function" ? icon("cross", 16) : "×"}</button></div>
    <div class="gch-board">${side(d.away, lv.away_score, false)}<div class="gch-mid">${mid}</div>${side(d.home, lv.home_score, true)}</div>`;
  chatDrawPoll();
  chatDrawHeat();
  chatDrawTix();
}

/* FRIENDS HERE (engine/karma friends_watching): the reader's friends on
   this game's page now — Discord's "playing now" — unless they hid it. */
function chatFriendsHere() {
  const f = CH.friends || [];
  if (!f.length) return "";
  const who = `@${chEsc(f[0])}${f.length > 1 ? ` and ${f.length - 1} friend${f.length > 2 ? "s" : ""}` : ""}`;
  return `<span class="gch-friends"> · ${who} here</span>`;
}

/* THE ROOM'S HEAT (Twitch's Hype Train; engine/karma hype): the last five
   minutes of messages and reactions, from three people or more, as five
   levels. Everyone taking part while it climbs earns karma for each. */
function chatDrawHeat() {
  const s = document.getElementById("gch-sheet");
  const box = s && s.querySelector(".gch-heat");
  if (!box) return;
  const h = CH.hype;
  if (!h || CH.thread || !(h.level || h.n)) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const lvl = Math.min(5, Number(h.level) || 0);
  const pct = lvl >= 5 ? 100 : Math.round(Math.max(0, Math.min(1, Number(h.progress) || 0)) * 100);
  box.innerHTML = `<span class="gch-heat-l">${lvl ? "🔥".repeat(lvl) : "🔥"} Room heat${lvl ? ` · level ${lvl}` : ""}</span>
    <span class="gch-heat-bar lv${lvl}"><i style="--p:${pct}%"></i></span>
    <span class="gch-heat-n">${lvl >= 5 ? "On fire" : lvl ? "Keep it going" : "Three of you talking lights it"}</span>`;
}

/* KARMA FOR WATCHING (engine/karma, 2026-10-28: Real's karma for a live
   game opened, Twitch's points by the five minutes watched). While a live
   game's page is open and in view, a signed-in reader's page says so about
   once a minute; the server pays the game joined, each five minutes and a
   big play seen while here. Nothing is sent when the game is not on, the
   tab is out of sight or nobody is signed in. */
const CHAT_WATCH_MS = 60000;
function chatWatchArm() {
  clearTimeout(CH.wtimer);
  CH.wtimer = setTimeout(chatWatchTick, CH.wfirst ? CHAT_WATCH_MS : 4000);
}
async function chatWatchTick() {
  CH.wtimer = 0;
  if (!CH.room || !chatOnGame()) return;
  const live = ((CH.d || {}).live || {}).state === "live";
  const signed = typeof _acctUser !== "undefined" && _acctUser && _acctUser.signed_in;
  if (live && signed && !document.hidden) {
    CH.wfirst = true;
    try {
      const r = await fetch("/api/karma/watch", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ room: CH.room }) });
      const v = r.ok ? await r.json() : null;
      if (v && v.karma) chatKarma(v.karma);
    } catch (e) { /* the next minute asks again */ }
  }
  if (CH.room) chatWatchArm();
}
/* What an action earned, as js/karma.js's note (and a level crossed). */
function chatKarma(k) {
  if (!k || !k.got || typeof loadRoom !== "function") return;
  loadRoom("js/karma.js", "css/karma.css").then((ok) => { if (ok && typeof karmaNote === "function") karmaNote(k); });
}

/* YOUR TICKETS IN THIS GAME (2026-10-25). The reader's saved slips from My
   Bets, each leg in this game with the box's number so far — "Chase o71.5
   rec yds · 58, 14 to go" — off the live loop's own files
   (engine/sliplive.room_tickets, POST /api/chat/ticket). The score's facts,
   free; the chance and the hedge stay on the Live tab for members. One tap
   puts the ticket on the reader's next message. Asked at most every thirty
   seconds while the sheet is open. */
function chatTixMine() {
  if (typeof mbLoad !== "function") return [];
  return mbLoad().filter((b) => b && b.result === "pending" && b.src === "slip" && Array.isArray(b.legs) && b.legs.length)
    .slice(-10);
}
function chatTixLegHTML(l) {
  const word = typeof marketWord === "function" ? marketWord(l.market) : l.market;
  const side = l.side ? `${String(l.side)[0].toLowerCase()}` : "";
  const cur = Number(l.current), line = Number(l.line);
  let now = "";
  if (Number.isFinite(cur)) {
    const over = String(l.side).toUpperCase() === "OVER", under = String(l.side).toUpperCase() === "UNDER";
    const go = over && Number.isFinite(line) && !l.result ? `, ${Math.max(0, Math.floor(line) + 1 - cur)} to go`
      : under && Number.isFinite(line) && !l.result ? `, ${Math.max(0, Math.floor(line) - cur)} to spare` : "";
    now = `<span class="gch-tik-now">${chEsc(cur)}${chEsc(go)}</span>`;
  } else if (l.state === "scheduled" || !l.state) now = `<span class="gch-tik-now">not started</span>`;
  const res = l.result === "won" ? " r-won" : l.result === "lost" ? " r-lost" : "";
  return `<li class="gch-tik-leg${res}"><b>${chEsc(l.player)}</b> ${chEsc(side)}${Number.isFinite(line) ? chEsc(line) : ""} ${
    chEsc(word || "")}${now}${l.result ? `<span class="gch-tik-res">${l.result === "won" ? "✓" : l.result === "lost" ? "✗" : "push"}</span>` : ""}</li>`;
}
async function chatDrawTix() {
  const s = document.getElementById("gch-sheet");
  const box = s && s.querySelector(".gch-tix");
  if (!box) return;
  const mine = chatTixMine();
  if (!mine.length || CH.thread) { box.hidden = true; return; }
  const paint = () => {
    const t = (CH.tix && CH.tix.room === CH.room && CH.tix.list) || [];
    box.hidden = !t.length;
    box.innerHTML = !t.length ? "" : `<div class="gch-tix-h">Your ${t.length === 1 ? "ticket" : "tickets"} in this game</div>${
      t.map((k) => `<div class="gch-tik"><div class="gch-tik-top"><span>${chEsc(String(k.desc || "").slice(0, 70))}</span>
        ${(CH.me || {}).signed_in ? `<button type="button" class="gch-tik-share" data-gch="tikshare" data-tik="${chEsc(k.id)}">Share</button>` : ""}</div>
        <ul>${k.legs.map(chatTixLegHTML).join("")}</ul>${k.of > k.legs.length
          ? `<span class="gch-tik-more">${k.of - k.legs.length} more leg${k.of - k.legs.length === 1 ? "" : "s"} in other games</span>` : ""}</div>`).join("")}`;
  };
  paint();
  if (CH.tixAt && Date.now() - CH.tixAt < 30000 && CH.tix && CH.tix.room === CH.room) return;
  CH.tixAt = Date.now();
  const room = CH.room;
  try {
    const r = await fetch("/api/chat/ticket", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room, tickets: mine.map((b) => ({ id: b.id, desc: b.desc, legs: b.legs })) }) });
    const v = r.ok ? await r.json() : null;
    if (v && room === CH.room) { CH.tix = { room, list: v.tickets || [] }; paint(); }
  } catch (e) { /* the next draw asks again */ }
}

/* Who wins? (Sofascore, Real) — the split, and the reader's own pick. */
function chatDrawPoll() {
  const s = document.getElementById("gch-sheet");
  if (!s) return;
  const v = CH.votes;
  const d = CH.d || {};
  const box = s.querySelector(".gch-poll");
  if (!v || !d.home || !d.away || CH.thread) { box.innerHTML = ""; box.hidden = true; return; }
  box.hidden = false;
  if (!v.open && CH.potg && (CH.potg.options || []).length) { box.innerHTML = chatPotgHTML(CH.potg); return; }
  const total = (v.away || 0) + (v.home || 0);
  const pct = (n) => (total ? Math.round((100 * n) / total) : 0);
  const btn = (key, abbr) => `<button type="button" class="gch-vote${v.mine === key ? " mine" : ""}" data-gch="vote" data-side="${key}"
      ${v.open ? "" : "disabled"}><b>${chEsc(abbr)}</b>${total ? `<span>${pct(v[key] || 0)}%</span>` : ""}</button>`;
  box.innerHTML = `<span class="gch-poll-q">${v.open ? "Who wins?" : "The room picked"}</span>
    ${btn("away", d.away)}${btn("home", d.home)}
    <span class="gch-poll-n">${total ? `${total} vote${total === 1 ? "" : "s"}` : v.open ? "Be the first" : ""}</span>
    ${total ? `<span class="gch-poll-bar" style="--gch-away:${pct(v.away || 0)}%"></span>` : ""}`;
}

/* THE FANS' PLAYER OF THE GAME (theScore's and ESPN's fan vote): once the
   game is final the who-wins bar becomes this, the four players in its
   biggest plays; how the room voted shows once you have. */
function chatPotgHTML(p) {
  const counts = p.counts || [];
  const total = counts.reduce((a, b) => a + b, 0);
  const shown = p.mine != null || !p.open;
  const pct = (i) => (total ? Math.round((100 * (counts[i] || 0)) / total) : 0);
  const lead = shown && total ? counts.indexOf(Math.max(...counts)) : -1;
  return `<span class="gch-poll-q">${p.open && p.mine == null ? "Player of the game?" : "Fans' player of the game"}</span>
    <span class="gch-potg">${p.options.map((o, i) => `<button type="button" class="gch-vote${p.mine === i ? " mine" : ""}${i === lead ? " lead" : ""}"
      data-gch="potg" data-i="${i}"${p.open && p.mine == null ? "" : " disabled"}><b>${chEsc(o.name)}</b>${
      shown ? `<span>${pct(i)}%</span>` : o.team ? `<span>${chEsc(o.team)}</span>` : ""}</button>`).join("")}</span>
    <span class="gch-poll-n">${shown ? `${total} vote${total === 1 ? "" : "s"}` : "+5 karma"}</span>`;
}

function chatDrawTabs() {
  const s = document.getElementById("gch-sheet");
  if (!s) return;
  const nav = s.querySelector(".gch-tabs");
  if (CH.thread) { nav.innerHTML = ""; nav.hidden = true; return; }
  nav.hidden = false;
  const tabs = [["all", "All"], ["plays", "Big plays"], ["game", "Game talk"],
    ["party", CH.party ? `Party · ${CH.party.name}` : "Watch party"]];
  nav.innerHTML = tabs.map(([k, l]) => `<button type="button" role="tab" aria-selected="${CH.tab === k}"
    class="gch-tab${CH.tab === k ? " on" : ""}" data-gch="tab" data-tab="${k}">${chEsc(l)}</button>`).join("");
}

/* ---------------- what the body shows ---------------- */

function chatBody() {
  const s = document.getElementById("gch-sheet");
  return s ? s.querySelector(".gch-body") : null;
}

function chatDrawBody(opts) {
  const body = chatBody();
  if (!body) return;
  const keep = opts && opts.keep;
  const before = keep ? body.scrollHeight - body.scrollTop : 0;
  if (CH.thread) body.innerHTML = chatThreadHTML();
  else if (CH.tab === "party") body.innerHTML = chatPartyHTML();
  else if (CH.tab === "plays") body.innerHTML = chatPlaysHTML();
  else body.innerHTML = chatListHTML(CH.tab === "game" ? (m) => !m.play : () => true);
  if (keep) body.scrollTop = body.scrollHeight - before;
  else if (CH.tab !== "plays" || CH.thread) body.scrollTop = body.scrollHeight;
  else body.scrollTop = 0;
  chatPill(0);
}

/* New messages land at the bottom — and wait under a pill when the reader
   has scrolled up to read something older (Sideline's pause). */
function chatAppend(fresh, v) {
  const body = chatBody();
  if (!body) return;
  if (CH.tab === "plays" && !CH.thread) {
    if (Object.keys(v.plays || {}).length || Object.keys(v.threads || {}).length) chatDrawBody();
    return;
  }
  const near = body.scrollHeight - body.scrollTop - body.clientHeight < 80;
  const want = CH.thread ? (m) => m.play === CH.thread : CH.tab === "game" ? (m) => !m.play : () => true;
  // Held for a TV delay (chatReady) until their time, then appended once.
  const pool = [...(CH.held || []), ...fresh];
  CH.held = pool.filter((m) => !chatReady(m));
  const add = pool.filter((m) => chatReady(m) && want(m) && !body.querySelector(`.gch-msg[data-id="${Number(m.id)}"]`));
  if (add.length) {
    const empty = body.querySelector(".gch-empty");
    if (empty) empty.remove();
    const shown = CH.msgs.filter(want).filter(chatReady);
    body.insertAdjacentHTML("beforeend", add.map((m) => chatMsgHTML(m, shown[shown.indexOf(m) - 1])).join(""));
  }
  for (const id of Object.keys(v.reacts || {})) {
    const m = CH.byId.get(Number(id));
    const el = body.querySelector(`.gch-msg[data-id="${Number(id)}"] .gch-faces`);
    if (m && el) el.outerHTML = chatFacesHTML(m);
  }
  if (CH.thread && v.plays && v.plays[CH.thread]) {
    const top = body.querySelector(".gch-playcard .gch-faces");
    if (top) top.outerHTML = chatPlayFacesHTML(CH.thread);
  }
  if (!add.length) return;
  if (near || add.some((m) => m.own)) body.scrollTop = body.scrollHeight;
  else chatPill(add.length);
}

function chatScrolled() {
  const body = chatBody();
  if (!body) return;
  if (body.scrollHeight - body.scrollTop - body.clientHeight < 40) chatPill(0);
}

function chatPill(add) {
  const s = document.getElementById("gch-sheet");
  if (!s) return;
  const p = s.querySelector(".gch-newpill");
  const n = add ? (Number(p.dataset.n) || 0) + add : 0;
  p.dataset.n = String(n);
  p.hidden = !n;
  p.textContent = n ? `${n} new message${n === 1 ? "" : "s"} ↓` : "";
}

function chatPartyHTML() {
  const me = CH.me || {};
  const p = CH.party;
  if (!p) {
    return `<div class="gch-party-start"><b>Watch with your friends</b>
      <span>A private thread inside this game's chat: only the people you send the link to can read it.</span>
      ${me.signed_in ? `<button type="button" class="btn" data-gch="party-new">Start a watch party</button>`
        : `<span class="gch-party-note">Make a free account below to start one or join one.</span>`}${
      CH.err ? `<p class="gch-err">${chEsc(CH.err)}</p>` : ""}</div>`;
  }
  const link = chatPartyLink(p);
  const strip = `<div class="gch-party-bar"><div class="gch-party-who"><b>${chEsc(p.name)}</b>
      <span>${chEsc(p.members)} in it · only they can read it</span></div>
    <div class="gch-party-acts"><button type="button" class="gch-party-btn" data-gch="party-share" data-link="${chEsc(link)}">Invite</button>
      <button type="button" class="gch-party-btn quiet" data-gch="party-leave">Leave</button></div></div>`;
  const rows = CH.pmsgs.filter(chatReady);
  return strip + (rows.length ? rows.map((m, i) => chatMsgHTML(m, rows[i - 1])).join("")
    : `<div class="gch-empty"><b>Just you so far.</b><span>Tap Invite and send the link — it opens this game with the party on.</span></div>`);
}

function chatListHTML(want) {
  const rows = CH.msgs.filter(want).filter(chatReady);
  const more = CH.older ? `<button type="button" class="gch-older" data-gch="older">Load earlier messages</button>` : "";
  if (!rows.length) {
    return `${more}<div class="gch-empty">${CH.loaded
      ? `<b>Nobody has said anything yet.</b><span>Call the next play, share the bet you’re on, or pick a side above.</span>`
      : "Loading the chat…"}</div>`;
  }
  return more + rows.map((m, i) => chatMsgHTML(m, rows[i - 1])).join("");
}

const chatAgo = (t) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - Number(t || 0)));
  return s < 45 ? "now" : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 ? `${Math.round(s / 3600)}h` : `${Math.round(s / 86400)}d`;
};

function chatInitials(p) {
  const src = String((p && (p.name || p.handle)) || "?").trim();
  const parts = src.split(/[\s_]+/).filter(Boolean);
  return ((parts[0] || "?")[0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
}

/* @handles light up; everything else is text. */
function chatText(s) {
  return chEsc(s).replace(/(^|[^A-Za-z0-9_])@([A-Za-z0-9_]{3,20})/g,
    (m, a, h) => `${a}<span class="gch-at${CH.me && CH.me.handle && h.toLowerCase() === String(CH.me.handle).toLowerCase() ? " me" : ""}">@${h}</span>`);
}

function chatBetHTML(b) {
  if (!b) return "";
  const line = b.line != null ? ` ${b.line}` : "";
  const odds = b.odds != null ? ` ${b.odds > 0 ? "+" : "−"}${Math.abs(b.odds)}` : "";
  return `<div class="gch-bet"><span class="gch-bet-k">On it</span><b>${chEsc(b.player || "")}</b>
    <span>${chEsc([b.side, line.trim(), b.market].filter(Boolean).join(" "))}${chEsc(odds)}</span>${
    b.book ? `<span class="gch-bet-book">${chEsc(b.book)}</span>` : ""}</div>`;
}

/* A message's faces, as the chat apps draw them (Discord, Slack, iMessage's
   tapbacks): only the ones somebody used, each with its count. The four to
   choose from live in the message's tools, shown on hover with a mouse and
   on a tap on a phone (chatSel), so a quiet room is a list of words, not a
   wall of emoji. */
function chatFacesHTML(m) {
  const faces = m.reacts || {};
  return `<span class="gch-faces">${CHAT_FACES.filter(([k]) => (faces[k] || 0) > 0).map(([k, e]) => {
    const n = faces[k];
    return `<button type="button" class="gch-face${m.mine === k ? " mine" : ""}" data-gch="react" data-id="${m.id}" data-kind="${k}"
      aria-label="${k} ${n}">${e}<span>${n}</span></button>`;
  }).join("")}</span>`;
}
const chatPickHTML = (m) => `<span class="gch-pick" role="group" aria-label="React">${CHAT_FACES.map(([k, e]) =>
  `<button type="button" class="gch-pk${m.mine === k ? " mine" : ""}" data-gch="react" data-id="${m.id}" data-kind="${k}" aria-label="${k}">${e}</button>`).join("")}</span>`;
function chatSel(id) {
  CH.sel = CH.sel === id ? 0 : id;
  document.querySelectorAll("#gch-sheet .gch-msg.sel").forEach((el) => el.classList.remove("sel"));
  if (CH.sel) {
    const el = document.querySelector(`#gch-sheet .gch-msg[data-id="${CH.sel}"]`);
    if (el) el.classList.add("sel");
  }
}
/* WATCHING ON TV (js/detail.js tvPick): a message younger than the reader's
   delay waits, their own excepted, so the room cannot spoil a play their
   TV has not shown. */
function chatReady(m) {
  const dl = Number((typeof window !== "undefined" && window.QB_TV_DELAY) || 0);
  return !dl || !m || m.own || Date.now() / 1000 - Number(m.at || 0) >= dl;
}
/* The message before this one in what the list shows, for grouping. */
function chatPrevOf(id) {
  const el = document.querySelector(`#gch-sheet .gch-msg[data-id="${Number(id)}"]`);
  const prev = el && el.previousElementSibling;
  return prev && prev.dataset && prev.dataset.id ? CH.byId.get(Number(prev.dataset.id)) : null;
}
/* One author's run of messages inside three minutes reads as one block:
   the name and the face on the first, the rest beneath it (Discord). */
const chatJoins = (m, prev) => !!prev && (prev.by || {}).handle === (m.by || {}).handle && !m.reply_to
  && !(m.play && !CH.thread) && Math.abs(Number(m.at) - Number(prev.at)) < 180;
const chatClock = (t) => {
  const d = new Date(Number(t || 0) * 1000);
  return `${((d.getHours() + 11) % 12) + 1}:${String(d.getMinutes()).padStart(2, "0")}`;
};

function chatMsgHTML(m, prev) {
  const p = m.by || {};
  const c = Math.abs(Number(p.color || 0)) % 8;
  const reply = m.reply_to ? CH.byId.get(m.reply_to) : null;
  const play = m.play && !CH.thread ? chatPlayOf(m.play) : null;
  const badge = (p.verified ? `<span class="gch-tick" title="Verified">${typeof icon === "function" ? icon("check", 10) : "✓"}</span>` : "")
    + (p.founder ? `<span class="gch-founder">Founder</span>` : "")
    // Call it's flame: this many calls right in a row now (engine/callit).
    + (Number(p.streak) >= 3 ? `<span class="gch-flame" title="${Number(p.streak)} Call it calls right in a row">🔥${Number(p.streak)}</span>` : "")
    // The writer's karma level, and the flair level 3 opens (engine/karma).
    + (Number(p.lv) ? `<span class="gch-lv kr-lv kr-${chEsc(p.cls || "t1")}${Number(p.lv) >= 10 ? " hi" : ""}" title="Karma level ${
      Number(p.lv)}">${Number(p.lv)}</span>` : "")
    + (p.flair ? `<span class="gch-flair" aria-hidden="true">${chEsc(p.flair)}</span>` : "");
  const menu = CH.menu === m.id ? chatMenuHTML(m) : "";
  const cont = chatJoins(m, prev && typeof prev === "object" ? prev : null);
  // The site's own account (engine/housepost posts each big play as it) wears the site's mark.
  return `<article class="gch-msg${m.own ? " own" : ""}${cont ? " cont" : ""}${CH.sel === m.id ? " sel" : ""}${p.founder ? " staff" : ""}${p.official ? " house" : ""}" data-id="${m.id}">
    ${cont ? `<time class="gch-gutter" aria-hidden="true">${chatClock(m.at)}</time>`
      : p.official ? `<span class="gch-av gch-house" aria-hidden="true">${brandMarkHTML(24)}</span>`
      : `<span class="gch-av gch-c${c}${p.founder ? " gold" : ""}${Number(p.lv) >= 20 ? ` kr-glow kr-${chEsc(p.cls || "t5")}` : ""}" aria-hidden="true">${chEsc(chatInitials(p))}</span>`}
    <div class="gch-bub">
      ${cont ? "" : `<div class="gch-meta"><b class="gch-name gch-c${c}">@${chEsc(p.handle || "")}</b>${badge}${
        p.team ? `<span class="gch-team">${chEsc(p.team)}</span>` : ""}<time>${chatAgo(m.at)}</time></div>`}
      ${reply ? `<div class="gch-quote"><span>↪ @${chEsc((reply.by || {}).handle || "")}</span> ${chEsc(String(reply.body || "").slice(0, 90))}</div>` : ""}
      ${play ? `<button type="button" class="gch-on-play" data-gch="thread" data-play="${chEsc(m.play)}">on ${chEsc(chatPlayTitle(play))}</button>` : ""}
      ${m.body ? `<p class="gch-text">${chatText(m.body)}</p>` : ""}
      ${chatBetHTML(m.bet)}
      <div class="gch-acts">${chatFacesHTML(m)}</div>
      <div class="gch-tools">${chatPickHTML(m)}
        <button type="button" class="gch-act" data-gch="reply" data-id="${m.id}">Reply</button>
        <button type="button" class="gch-act" data-gch="menu" data-id="${m.id}" aria-label="More">⋯</button></div>
      ${menu}
    </div></article>`;
}

function chatMenuHTML(m) {
  const items = [];
  if (m.own) items.push(`<button type="button" data-gch="delete" data-id="${m.id}">Delete</button>`);
  else {
    items.push(...CHAT_REASONS.map(([k, l]) => `<button type="button" data-gch="report" data-id="${m.id}" data-reason="${k}">Report: ${l}</button>`));
    items.push(`<button type="button" data-gch="block" data-handle="${chEsc((m.by || {}).handle || "")}">Block @${chEsc((m.by || {}).handle || "")}</button>`);
  }
  if (CH.me && CH.me.founder) items.push(`<button type="button" data-gch="hide" data-id="${m.id}">Hide for everyone</button>`);
  return `<div class="gch-menu">${items.join("")}</div>`;
}

/* ---------------- the plays ---------------- */

/* The rows the game's own file carries, newest last, each with the key
   its thread is filed under (app.js chatPlayKey, the same key the play's
   bubble on the page carries). */
function chatAllPlays() {
  const d = CH.d || {};
  if (CH.league === "mlb") return (d.events || []).filter((r) => r && r.kind === "atbat");
  if (CH.league === "nhl" && d.rink && (d.rink.events || []).length) return d.rink.events;
  return (d.plays || []).filter((r) => r && (r.kind === "football" || r.kind === "hoops" || r.kind === "hockey"));
}

function chatPlayOf(key) {
  return chatAllPlays().find((p) => chatPlayKey(p) === key) || null;
}

// The play's words, shared with the Live tab's feed (app.js playTitleOf).
const chatPlayTitle = (p) => playTitleOf(p, CH.d || {});

function chatPlayWhen(p) {
  if (p.kind === "atbat") return `${p.half === "T" ? "Top" : "Bottom"} ${p.inning || ""}`;
  const per = p.period ? (CH.league === "nhl" ? `P${p.period}` : `Q${p.period}`) : "";
  return [per, p.clock].filter(Boolean).join(" ");
}

// What counts as a big play, by sport (app.js playIsBig, the feed's too).
const chatBig = (p) => playIsBig(p);

function chatPlayFacesHTML(key) {
  const faces = CH.plays[key] || {};
  const mine = CH.minePlays[key] || "";
  return `<span class="gch-faces">${CHAT_FACES.map(([k, e]) => {
    const n = faces[k] || 0;
    return `<button type="button" class="gch-face${mine === k ? " mine" : ""}${n ? "" : " none"}" data-gch="playface" data-play="${chEsc(key)}" data-kind="${k}"
      aria-label="${k}${n ? ` ${n}` : ""}">${e}${n ? `<span>${n}</span>` : ""}</button>`;
  }).join("")}</span>`;
}

function chatPlayCardHTML(p, inThread) {
  const key = chatPlayKey(p);
  const n = CH.threads[key] || 0;
  const [sa, sh] = p.away_score != null ? [p.away_score, p.home_score] : (p.score || []);
  const score = sa != null && sh != null && (CH.d || {}).away ? `${CH.d.away} ${sa} – ${sh} ${CH.d.home}` : "";
  const d = CH.d || {};
  return `<article class="gch-playcard${p.scoring || p.kind === "goal" ? " gch-scored" : ""}${p.turnover ? " gch-turned" : ""}" data-play="${chEsc(key)}">
    <div class="gch-play-when">${chEsc(chatPlayWhen(p))}${score ? `<span>${chEsc(score)}</span>` : ""}${pcRate(p)}</div>
    ${pcBodyHTML(p, d, chatAllPlays(), true)}
    <div class="gch-acts">${chatPlayFacesHTML(key)}${inThread ? "" : `<button type="button" class="gch-act gch-thread-btn" data-gch="thread" data-play="${chEsc(key)}">${
      n ? `${n} repl${n === 1 ? "y" : "ies"}` : "Talk about it"}</button>`}${pcShareHTML(CH.league, CH.event, p, `${pcTitle(p, d)}${score ? ` · ${score}` : ""}`)}</div></article>`;
}

/* Real's feed, for this game: the big plays, newest first, each with its
   faces and its thread. */
function chatPlaysHTML() {
  const big = chatAllPlays().filter(chatBig).slice(-40).reverse();
  if (!big.length) {
    return `<div class="gch-empty"><b>No big plays yet.</b><span>Scores, turnovers and the plays that swing a game land here, each with its own thread.</span></div>`;
  }
  return big.map((p) => chatPlayCardHTML(p, false)).join("");
}

function chatThreadHTML() {
  const p = chatPlayOf(CH.thread);
  const rows = CH.msgs.filter((m) => m.play === CH.thread);
  return `<div class="gch-thread-top"><button type="button" class="gch-back" data-gch="unthread">← All of the chat</button></div>
    ${p ? chatPlayCardHTML(p, true) : `<p class="gch-empty">This play’s thread.</p>`}
    ${rows.length ? rows.map((m, i) => chatMsgHTML(m, rows[i - 1])).join("") : `<div class="gch-empty"><span>Be the first to say something about this play.</span></div>`}`;
}

/* ---------------- the composer ---------------- */

function chatDrawFoot() {
  const s = document.getElementById("gch-sheet");
  if (!s) return;
  const foot = s.querySelector(".gch-foot");
  const me = CH.me || {};
  if (!me.signed_in) {
    foot.innerHTML = `<div class="gch-join"><span>Reading is free. Make a free account to chat, react and vote — no card.</span>
      <button type="button" class="btn" data-gch="signup">Make a free account</button>
      <button type="button" class="btn ghost" data-gch="login">Log in</button></div>`;
    return;
  }
  if (!me.handle) {
    foot.innerHTML = `<form class="gch-handle" data-gch-form="handle"><label for="gch-handle-in">Pick a username to chat</label>
      <div class="gch-row"><span class="gch-atsign">@</span><input id="gch-handle-in" name="handle" autocomplete="username" maxlength="20" placeholder="username" pattern="[A-Za-z0-9_]{3,20}" required>
      <button type="submit" class="btn">Save</button></div><p class="gch-err">${chEsc(CH.err)}</p></form>`;
    return;
  }
  if (CH.tab === "party" && !CH.party && !CH.thread) { foot.innerHTML = ""; return; }
  let rules = "";
  try { rules = localStorage.getItem(CHAT_RULES_KEY) ? "" : "show"; } catch (e) { rules = ""; }
  const reply = CH.replyTo ? CH.byId.get(CH.replyTo) : null;
  const thread = CH.thread ? chatPlayOf(CH.thread) : null;
  foot.innerHTML = `${rules ? `<div class="gch-rules"><span><b>The room's rules.</b> Talk about the game and your bets. No slurs, no spam, no selling picks —
      report anything that crosses the line.</span><button type="button" class="btn ghost" data-gch="rules">Got it</button></div>` : ""}
    ${reply ? `<div class="gch-replying">Replying to @${chEsc((reply.by || {}).handle || "")}<button type="button" data-gch="unreply" aria-label="Cancel the reply">×</button></div>` : ""}
    ${thread && !reply ? `<div class="gch-replying">On: ${chEsc(chatPlayTitle(thread))}</div>` : ""}
    ${CH.bet ? `<div class="gch-betdraft">${chatBetHTML(CH.bet)}<button type="button" data-gch="unbet" aria-label="Remove the bet">×</button></div>` : ""}
    ${CH.betOpen ? chatBetFormHTML() : ""}
    <form class="gch-compose" data-gch-form="send">
      <button type="button" class="gch-addbet" data-gch="bet" aria-label="Add the bet you’re on" title="Add the bet you’re on">+</button>
      <textarea class="gch-input" name="body" rows="1" maxlength="280" placeholder="${thread ? "Reply about this play…" : CH.tab === "party" && CH.party ? "Message the party" : "Send a message"}"
        aria-label="Message"></textarea>
      <button type="submit" class="gch-send" aria-label="Send"><svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M2 8.6 14 2.5l-3.6 11.2-2.3-4.4z"/></svg></button>
    </form><p class="gch-err">${chEsc(CH.err)}</p>`;
}

/* The bet a reader says they are on: their pending bets from My Bets with
   one tap, or typed. Their own words — the server keeps it to the fields a
   chip shows, and never a link. */
function chatBetFormHTML() {
  const mine = typeof mbLoad === "function" ? mbLoad().filter((b) => b && b.result === "pending").slice(-6).reverse() : [];
  const picks = mine.length ? `<div class="gch-mybets"><span>From My Bets</span>${mine.map((b) => `<button type="button" data-gch="usebet"
      data-desc="${chEsc(String(b.desc || "").slice(0, 60))}" data-odds="${chEsc(b.odds || "")}" data-book="${chEsc(String(b.book || "").slice(0, 24))}">${chEsc(String(b.desc || "").slice(0, 48))}</button>`).join("")}</div>` : "";
  return `<form class="gch-betform" data-gch-form="bet">${picks}
    <div class="gch-betgrid">
      <input name="player" maxlength="60" placeholder="Player or team" aria-label="Player or team" required>
      <input name="market" maxlength="40" placeholder="Bet (e.g. rush yds)" aria-label="The bet">
      <select name="side" aria-label="Side"><option value="">Side</option><option>OVER</option><option>UNDER</option><option>YES</option><option>NO</option></select>
      <input name="line" inputmode="decimal" maxlength="7" placeholder="Line" aria-label="Line">
      <input name="odds" inputmode="numeric" maxlength="7" placeholder="Odds (−110)" aria-label="Odds">
      <input name="book" maxlength="24" placeholder="Book" aria-label="Book">
    </div><button type="submit" class="btn ghost">Add to my message</button></form>`;
}

async function chatSend(form) {
  const box = form.querySelector(".gch-input");
  const text = (box.value || "").trim();
  if (!text && !CH.bet) return;
  const btn = form.querySelector(".gch-send");
  btn.disabled = true;
  const party = CH.tab === "party" && !CH.thread && CH.party ? CH.party.id : 0;
  const out = await chatPost("send", { body: text, play: CH.thread || "", reply_to: CH.replyTo || 0, bet: CH.bet || undefined, party });
  btn.disabled = false;
  if (out.status === 200) {
    box.value = "";
    CH.err = "";
    CH.replyTo = 0;
    CH.bet = null;
    CH.betOpen = false;
    chatDrawFoot();
    await chatPull();
    const b = chatBody();
    if (b) b.scrollTop = b.scrollHeight;
    const nb = document.querySelector("#gch-sheet .gch-input");
    if (nb && window.matchMedia("(pointer: fine)").matches) nb.focus();
    return;
  }
  if (out.need_handle && CH.me) CH.me.handle = null;
  if (out.status === 401 && CH.me) CH.me.signed_in = false;
  CH.err = out.error || "That did not send — try again.";
  const keep = text;
  chatDrawFoot();
  const nb = document.querySelector("#gch-sheet .gch-input");
  if (nb) nb.value = keep;
}

/* ---------------- taps ---------------- */

async function chatClick(e) {
  const share = e.target.closest("[data-pc-share]");
  if (share) return pcShare(share);
  const t = e.target.closest("[data-gch]");
  if (!t) {
    // A tap on a message (not on one of its buttons) shows its tools on a
    // phone, as a long-press does in a messaging app; a second tap, or a
    // tap on another, moves them (chatSel).
    const msg = e.target.closest(".gch-msg");
    if (msg && !e.target.closest("a, button, input, textarea, select")) chatSel(Number(msg.dataset.id));
    return;
  }
  const act = t.dataset.gch;
  if (act === "close") return chatClose();
  if (act === "at") return chatAtPut(t.dataset.handle);
  if (act === "tab") { CH.tab = t.dataset.tab; CH.menu = 0; chatDrawTabs(); chatDrawBody(); chatDrawFoot(); return; }
  if (act === "thread") { CH.thread = t.dataset.play; CH.menu = 0; chatDrawPoll(); chatDrawTabs(); chatDrawBody(); chatDrawFoot(); return; }
  if (act === "unthread") { CH.thread = ""; chatDrawPoll(); chatDrawTabs(); chatDrawBody(); chatDrawFoot(); return; }
  if (act === "older") { await chatPull(true); return; }
  if (act === "signup" || act === "login") {
    chatClose();
    location.hash = act === "signup" ? "#signup" : "#account";
    return;
  }
  if (act === "rules") { try { localStorage.setItem(CHAT_RULES_KEY, "1"); } catch (err) {} chatDrawFoot(); return; }
  if (act === "party-new") {
    const out = await chatPost("party", {});
    if (out.status === 401) return chatNeedAccount();
    if (out.need_handle && CH.me) { CH.me.handle = null; chatDrawFoot(); return; }
    CH.err = out.status === 200 ? "" : out.error || "That didn’t go through — try again.";
    if (out.status === 200) chatUseParty(out);
    chatDrawTabs(); chatDrawBody(); chatDrawFoot();
    return;
  }
  if (act === "party-share") {
    const link = t.dataset.link, text = `Watch ${CH.d ? `${CH.d.away} at ${CH.d.home}` : "the game"} with me on Qellys Book:`;
    try {
      if (navigator.share) await navigator.share({ title: "Watch party", text, url: link });
      else { await navigator.clipboard.writeText(link); t.textContent = "Link copied"; }
    } catch (err) { /* the reader closed the sheet */ }
    return;
  }
  if (act === "party-leave") {
    if (!CH.party) return;
    await chatPost("leave", { party: CH.party.id });
    CH.parties = CH.parties.filter((p) => p.id !== CH.party.id);
    chatUseParty(CH.parties[0] || null);
    chatDrawTabs(); chatDrawBody(); chatDrawFoot();
    return;
  }
  if (act === "reply") { CH.replyTo = Number(t.dataset.id); chatDrawFoot(); const b = document.querySelector("#gch-sheet .gch-input"); if (b) b.focus(); return; }
  if (act === "unreply") { CH.replyTo = 0; chatDrawFoot(); return; }
  if (act === "bet") { CH.betOpen = !CH.betOpen; chatDrawFoot(); return; }
  if (act === "unbet") { CH.bet = null; chatDrawFoot(); return; }
  if (act === "tikshare") {
    const b = chatTixMine().find((x) => String(x.id) === t.dataset.tik);
    if (b) { CH.bet = { player: String(b.desc || "").slice(0, 60), odds: Number(b.odds) || undefined, book: String(b.book || "").slice(0, 24) || undefined }; }
    CH.betOpen = false;
    chatDrawFoot();
    const inp = document.querySelector("#gch-sheet .gch-input");
    if (inp) inp.focus();
    return;
  }
  if (act === "usebet") {
    CH.bet = { player: t.dataset.desc, odds: Number(t.dataset.odds) || undefined, book: t.dataset.book || undefined };
    CH.betOpen = false;
    chatDrawFoot();
    return;
  }
  if (act === "menu") {
    const id = Number(t.dataset.id);
    CH.menu = CH.menu === id ? 0 : id;
    const el = t.closest(".gch-msg");
    const m = CH.byId.get(id);
    if (el && m) el.outerHTML = chatMsgHTML(m, chatPrevOf(id));
    return;
  }
  /* A face is drawn the moment the server takes it, from its own answer
     (`mine`), rather than waiting for the next poll — the count a reader
     just changed should move under their thumb. */
  if (act === "react") {
    const id = Number(t.dataset.id);
    const out = await chatPost("react", { id, kind: t.dataset.kind });
    if (out.status === 401) return chatNeedAccount();
    const m = CH.byId.get(id);
    if (out.status === 200 && m) {
      const faces = { ...(m.reacts || {}) };
      if (m.mine) faces[m.mine] = Math.max(0, (faces[m.mine] || 1) - 1);
      if (out.mine) faces[out.mine] = (faces[out.mine] || 0) + 1;
      m.reacts = faces;
      m.mine = out.mine;
      if (CH.sel === id) chatSel(id);
      const el = document.querySelector(`#gch-sheet .gch-msg[data-id="${id}"] .gch-faces`);
      if (el) el.outerHTML = chatFacesHTML(m);
    }
    return;
  }
  if (act === "playface") {
    const key = t.dataset.play;
    const out = await chatPost("play", { play: key, kind: t.dataset.kind });
    if (out.status === 401) return chatNeedAccount();
    if (out.status === 200) {
      const faces = { ...(CH.plays[key] || {}) };
      const was = CH.minePlays[key];
      if (was) faces[was] = Math.max(0, (faces[was] || 1) - 1);
      if (out.mine) faces[out.mine] = (faces[out.mine] || 0) + 1;
      CH.plays[key] = faces;
      CH.minePlays[key] = out.mine;
      chatShareCounts();
      document.querySelectorAll(`#gch-sheet .gch-playcard[data-play="${CSS.escape(key)}"] .gch-faces`).forEach((el) => { el.outerHTML = chatPlayFacesHTML(key); });
    }
    return;
  }
  if (act === "potg") {
    const out = await chatPost("potg", { pick: Number(t.dataset.i) });
    if (out.status === 401) return chatNeedAccount();
    if (out.status === 200 && out.options) { CH.potg = out; chatDrawPoll(); }
    else if (out.error && typeof tfToast === "function") tfToast(out.error);
    return;
  }
  if (act === "vote") {
    const out = await chatPost("vote", { side: t.dataset.side });
    if (out.status === 401) return chatNeedAccount();
    if (out.status === 200 && CH.votes) {
      const v = CH.votes;
      if (v.mine) v[v.mine] = Math.max(0, (v[v.mine] || 1) - 1);
      v[out.mine] = (v[out.mine] || 0) + 1;
      v.mine = out.mine;
      chatDrawPoll();
    }
    return;
  }
  if (act === "report" || act === "delete" || act === "hide") {
    const id = Number(t.dataset.id);
    const out = await chatPost(act, act === "report" ? { id, reason: t.dataset.reason } : act === "hide" ? { id, hidden: true } : { id });
    if (out.status === 401) return chatNeedAccount();
    if (out.status === 200) {
      // Reported, deleted or hidden, it leaves this reader's screen now.
      CH.byId.delete(id);
      CH.msgs = CH.msgs.filter((m) => m.id !== id);
      CH.pmsgs = CH.pmsgs.filter((m) => m.id !== id);
      CH.menu = 0;
      const el = document.querySelector(`#gch-sheet .gch-msg[data-id="${id}"]`);
      if (el) el.remove();
      if (act === "report" && typeof tfToast === "function") tfToast("Reported — thanks. It's hidden for you.");
    } else if (out.error && typeof tfToast === "function") tfToast(out.error);
    return;
  }
  if (act === "block") {
    const handle = t.dataset.handle;
    try {
      const r = await fetch("/api/feed/block", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ handle }) });
      if (r.ok) {
        CH.msgs = CH.msgs.filter((m) => (m.by || {}).handle !== handle);
        CH.pmsgs = CH.pmsgs.filter((m) => (m.by || {}).handle !== handle);
        CH.byId = new Map([...CH.msgs, ...CH.pmsgs].map((m) => [m.id, m]));
        CH.menu = 0;
        chatDrawBody();
        if (typeof tfToast === "function") tfToast(`@${handle} is blocked. Neither of you will see the other.`);
      }
    } catch (err) {}
  }
}

/* A write answered 401: the session ended or never began. The composer
   turns into the free-account door instead of an error line. */
function chatNeedAccount() {
  if (CH.me) CH.me.signed_in = false;
  CH.err = "";
  chatDrawFoot();
}

document.addEventListener("submit", async (e) => {
  const f = e.target.closest && e.target.closest("[data-gch-form]");
  if (!f) return;
  e.preventDefault();
  const kind = f.dataset.gchForm;
  if (kind === "send") return chatSend(f);
  if (kind === "bet") {
    const g = (n) => (f.elements[n] ? f.elements[n].value.trim() : "");
    CH.bet = { player: g("player"), market: g("market"), side: g("side"),
               line: g("line") ? Number(g("line")) : undefined, odds: g("odds") ? Number(g("odds").replace("−", "-")) : undefined,
               book: g("book") };
    CH.betOpen = false;
    chatDrawFoot();
    return;
  }
  if (kind === "handle") {
    const handle = (f.elements.handle.value || "").trim().replace(/^@/, "");
    try {
      const r = await fetch("/api/feed/profile", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ handle }) });
      const out = await r.json().catch(() => ({}));
      if (r.ok) { CH.me = { ...(CH.me || {}), handle: (out.profile && out.profile.handle) || handle }; CH.err = ""; }
      else CH.err = out.error || "That username did not save.";
    } catch (err) { CH.err = "No connection — try again."; }
    chatDrawFoot();
  }
});

/* @ SUGGESTIONS (Discord's and Slack's): an @ and the start of a name
   offers up to five, your friends here and the room's latest writers
   first; a tap puts the name in (engine/gamechat tells whoever is named). */
function chatAtWord(box) {
  const upto = box.value.slice(0, box.selectionStart == null ? box.value.length : box.selectionStart);
  const m = /(^|\s)@([A-Za-z0-9_]{0,20})$/.exec(upto);
  return m ? { q: m[2].toLowerCase(), at: upto.length - m[2].length - 1, end: upto.length } : null;
}
function chatAtNames(q) {
  const me = String((CH.me || {}).handle || "").toLowerCase();
  const seen = new Set(), out = [];
  const add = (h) => {
    const k = String(h || "").toLowerCase();
    if (k && k !== me && !seen.has(k) && k.startsWith(q)) { seen.add(k); out.push(String(h)); }
  };
  (CH.friends || []).forEach(add);
  [...CH.byId.values()].sort((a, b) => (b.at || 0) - (a.at || 0)).forEach((m) => add((m.by || {}).handle));
  return out.slice(0, 5);
}
function chatAtDraw(box) {
  const f = box.closest("form");
  if (!f) return;
  let row = f.parentNode.querySelector(".gch-atrow");
  const w = chatAtWord(box);
  const names = w ? chatAtNames(w.q) : [];
  if (!names.length) { if (row) row.remove(); return; }
  if (!row) {
    row = document.createElement("div");
    row.className = "gch-atrow";
    row.setAttribute("aria-label", "Names to mention");
    // Keep the keyboard up: a tap here must not take the focus away.
    row.addEventListener("mousedown", (e) => e.preventDefault());
    f.parentNode.insertBefore(row, f);
  }
  row.innerHTML = names.map((h) => `<button type="button" data-gch="at" data-handle="${chEsc(h)}">@${chEsc(h)}</button>`).join("");
}
function chatAtPut(handle) {
  const box = document.querySelector("#gch-sheet .gch-input");
  if (!box || !/^[A-Za-z0-9_]{3,20}$/.test(handle || "")) return;
  const w = chatAtWord(box);
  if (w) {
    box.value = `${box.value.slice(0, w.at)}@${handle} ${box.value.slice(w.end)}`.slice(0, 280);
    const pos = Math.min(box.value.length, w.at + handle.length + 2);
    box.setSelectionRange(pos, pos);
  }
  box.focus();
  chatAtDraw(box);
}
document.addEventListener("input", (e) => {
  if (e.target.classList && e.target.classList.contains("gch-input")) chatAtDraw(e.target);
});

/* Enter sends on a keyboard, Shift+Enter breaks the line; on a phone the
   return key always breaks the line and the Send button sends. */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey || !e.target.classList || !e.target.classList.contains("gch-input")) return;
  if (!window.matchMedia("(pointer: fine)").matches) return;      // a phone's return key is a new line
  e.preventDefault();
  const f = e.target.closest("form");
  if (f) chatSend(f);
});

document.addEventListener("click", (e) => {
  const p = e.target.closest && e.target.closest(".gch-newpill");
  if (!p) return;
  const b = chatBody();
  if (b) b.scrollTop = b.scrollHeight;
  chatPill(0);
});
