/* KARMA — levels and badges for watching live games and talking.

   Ethan, 2026-10-28: "diving back to the Real app there's a feature at
   hand where they give you karma for viewing live games and talking and
   chatting … it's like a type of a level up feature and you can get badges
   … see what other apps do like that as well then implement features like
   that". The rules, and whose they are, are engine/karma's docstring: Real's
   karma for a live game opened and the day's comment, its amount badges and
   leaderboards; Twitch's points by the five minutes watched and its Hype
   Train (the room's heat, drawn by js/chat.js); Duolingo's daily quests and
   its streak that a missed day freezes; Reddit's karma from the reactions
   your words get; MEE6's one message a minute.

   What this file draws, each loaded with css/karma.css the first time a
   page shows karma:
   * a "+10 · Joined a live game" note when something earns it, and the
     celebration when a level is crossed (karmaNote; js/chat.js calls it on
     every chat action's answer and the watching tick);
   * the Live tab's strip: the level, the way to the next, the days in a
     row and the day's three quests (karmaStripMount);
   * the Karma tab on the account page: everything (karmaPanelMount);
   * a profile's karma row: the level, the karma, the best badges
     (karmaProfileMount).
   Free for every account: nothing here is paid data. */

const KR = { me: null, at: 0, busy: null, scope: "week", lad: {} };
const KR_FRESH_MS = 60000;
const KR_SEEN_KEY = "qb_kr_level";
/* engine/karma TIERS: the first level of each, its name and its class. */
const KR_TIERS = [[1, "Rookie", "t1"], [5, "Starter", "t2"], [10, "Pro", "t3"], [15, "All-Star", "t4"],
  [20, "MVP", "t5"], [30, "Hall of Famer", "t6"], [40, "Legend", "t7"]];
/* engine/karma FLAIR_AT, COLOR_AT, RING_AT: what each level opens. */
const KR_UNLOCK = { 3: "A flair: an emoji worn beside your name in the chats.",
  10: "Your level badge shines in the chats.",
  20: "A glow in your tier's colour around your picture in the chats." };
const KR_QUEST_SHORT = { watch: "Watch 10 min", chat: "Chat", react: "React", call: "Call it", trivia: "Trivia", vote: "Vote" };
const KR_BADGE_ICON = { live: "📺", voice: "💬", crowd: "👏", caller: "🎯", hothand: "🔥", trivia: "🧠", winner: "🏆",
  streak: "📅", sports: "🌎", there: "⚡", host: "🎉", recruiter: "🤝", weeks: "🥇", season: "🎟️", karma: "✨",
  founding: "🌱", nightowl: "🦉" };
const KR_LEAGUE = { nfl: "NFL", cfb: "college football", nba: "NBA", wnba: "WNBA", nhl: "NHL", mlb: "MLB" };

const krEsc = (s) => escapeHtml(String(s == null ? "" : s));
const krNum = (n) => Number(n || 0).toLocaleString("en-US");
function krTier(level) {
  let out = KR_TIERS[0];
  for (const t of KR_TIERS) if (level >= t[0]) out = t;
  return { name: out[1], cls: out[2] };
}

async function krLoad(force) {
  if (!force && KR.me && Date.now() - KR.at < KR_FRESH_MS) return KR.me;
  if (KR.busy) return KR.busy;
  KR.busy = fetch("/api/karma/me", { credentials: "same-origin", cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    .then((v) => {
      KR.busy = null;
      if (v) {
        KR.me = v; KR.at = Date.now();
        if (v.up_from) krLevelUp(v.level);
      }
      return v;
    });
  return KR.busy;
}

/* A RING FOR THE LEVEL: the number in the middle, the way to the next
   level around it, in the tier's colour. */
function krRingHTML(v, size) {
  const t = v.cls ? { cls: v.cls } : krTier(v.level || 1);
  const p = Math.round(Math.max(0, Math.min(1, Number(v.progress) || 0)) * 100);
  return `<span class="kr-ring kr-${krEsc(t.cls)}${size ? ` ${size}` : ""}" style="--p:${p}%" aria-hidden="true"><b>${Number(v.level || 1)}</b></span>`;
}

/* ---------------- the note, and a level crossed ---------------- */

function karmaNote(k) {
  if (!k || !k.got) return;
  let box = document.querySelector(".kr-notes");
  if (!box) {
    box = document.createElement("div");
    box.className = "kr-notes";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = "kr-note";
  el.innerHTML = `<b>+${Number(k.got)}</b><span>${krEsc(k.why || "Karma")}</span>`;
  box.appendChild(el);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => el.classList.add("out"), 2300);
  setTimeout(() => el.remove(), 2800);
  KR.at = 0;                                   // the next look reads it fresh
  if (k.up) krLevelUp(k.level);
}

function krLevelUp(level) {
  let seen = 0;
  try { seen = Number(localStorage.getItem(KR_SEEN_KEY) || 0); } catch (e) { seen = 0; }
  if (!level || level <= seen) return;
  try { localStorage.setItem(KR_SEEN_KEY, String(level)); } catch (e) {}
  const t = krTier(level);
  const opened = Object.keys(KR_UNLOCK).map(Number).filter((n) => n === level);
  const newTier = KR_TIERS.some(([at]) => at === level && at > 1);
  const host = document.createElement("div");
  host.className = "kr-up";
  host.innerHTML = `<div class="kr-up-card" role="dialog" aria-modal="true" aria-label="Level ${level}">
      ${krRingHTML({ level, progress: 0, cls: t.cls }, "big")}
      <p class="kr-up-kick">Level up</p>
      <h3>Level ${level}${newTier ? ` · ${krEsc(t.name)}` : ""}</h3>
      <p class="kr-up-sub">${newTier ? `A new tier: you wear ${krEsc(t.name)} in every chat now.` : `${krEsc(t.name)} · keep watching and talking.`}</p>
      ${opened.map((n) => `<p class="kr-up-open">${krEsc(KR_UNLOCK[n])}</p>`).join("")}
      <button type="button" class="kr-btn" data-kr="up-close">Nice</button></div>`;
  document.body.appendChild(host);
  host.querySelector(".kr-btn").focus({ preventScroll: true });
  if (!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)) {
    const hues = ["var(--brand)", "var(--good)", "var(--sky)", "var(--bad)", "var(--warn)", "var(--brand-2)"];
    const rnd = (a, b) => Math.round(a + Math.random() * (b - a));
    const party = document.createElement("div");
    party.className = "win-party";
    party.setAttribute("aria-hidden", "true");
    party.innerHTML = Array.from({ length: 42 }, (_, i) => `<i style="--x:${rnd(-170, 170)}px;--y:${rnd(-360, -140)}px;--r:${
      rnd(-620, 620)}deg;--d:${rnd(0, 160)}ms;--c:${hues[i % hues.length]}"></i>`).join("");
    document.body.appendChild(party);
    setTimeout(() => party.remove(), 2400);
  }
}

/* ---------------- the Live tab's strip ---------------- */

/* FRIENDS WATCHING NOW (engine/karma friends_watching; Discord's "playing
   now"): a row under the strip, a tap into the game. */
function krFriendsHTML(v) {
  const f = v.friends || [];
  if (!f.length) return "";
  const byRoom = {};
  f.forEach((x) => { (byRoom[x.room] = byRoom[x.room] || []).push(x); });
  return `<div class="kr-friends">${Object.values(byRoom).slice(0, 3).map((g) => {
    const x = g[0];
    const [lg, ev] = String(x.room).split("_");
    const who = `@${krEsc(x.handle)}${g.length > 1 ? ` +${g.length - 1}` : ""}`;
    const game = x.away && x.home ? `${krEsc(x.away)} @ ${krEsc(x.home)}` : krEsc((KR_LEAGUE[lg] || lg).toUpperCase());
    return `<button type="button" class="kr-fr" data-kr="game" data-lg="${krEsc(lg)}" data-ev="${krEsc(ev)}">
      <i class="kr-fr-dot" aria-hidden="true"></i><b>${who}</b><span>watching ${game}</span></button>`;
  }).join("")}</div>`;
}

function krStripHTML(v) {
  const st = v.streak || {};
  // An account's first days: the next of its five firsts instead of the
  // day's quests (the Karma tab has all five).
  const camp = v.camp;
  const next = camp && camp.steps.find((x) => !x.done);
  const q = camp ? (next ? `<span class="kr-q">Next: ${krEsc(next.text)} · +${Number(camp.pts)}</span>` : "")
    : (v.quests || []).map((x) => `<span class="kr-q${x.done ? " done" : ""}" title="${krEsc(x.text)}">${
    x.done ? "✓" : `${x.n}/${x.goal}`} ${krEsc(KR_QUEST_SHORT[x.key] || x.text)}</span>`).join("");
  return `<button type="button" class="kr-strip" data-kr="open" aria-label="Your karma: level ${Number(v.level)}, open the Karma tab">
      ${krRingHTML(v)}
      <span class="kr-strip-main"><b>Level ${Number(v.level)} · ${krEsc(v.tier)}</b>
        <span class="kr-strip-sub">${krNum(v.points)} karma · ${krNum(v.to - v.points)} to level ${Number(v.level) + 1}${
          st.now ? ` · <span class="kr-fire">🔥 ${Number(st.now)}</span>` : ""}</span>
        ${camp ? `<span class="kr-camp-h">Getting started · ${camp.done} of ${camp.of}</span>` : ""}
        <span class="kr-qs">${q}</span></span>
      <span class="kr-go" aria-hidden="true">›</span></button>${krFriendsHTML(v)}`;
}

async function karmaStripMount(host) {
  if (!host) return;
  if (KR.me) host.innerHTML = krStripHTML(KR.me);
  const v = await krLoad();
  if (!host.isConnected || !v) return;
  host.innerHTML = krStripHTML(v);
}

/* ---------------- the Karma tab ---------------- */

/* GETTING STARTED (engine/karma camp): an account's five firsts, each
   +20 once and +50 for all five, shown its first two weeks or until done. */
function krCampHTML(v) {
  const c = v.camp;
  if (!c) return "";
  return `<section class="kr-card kr-camp"><div class="kr-h"><b>Getting started</b><span>${c.done} of ${c.of} · +${Number(c.pts)} each, +${Number(c.bonus)} for all five</span></div>
    <ul class="kr-quests">${c.steps.map((x) => `<li class="${x.done ? "done" : ""}"><span class="kr-tick" aria-hidden="true">${x.done ? "✓" : ""}</span>
      <span class="kr-qt">${krEsc(x.text)}</span><span class="kr-qn">${x.done ? `+${Number(c.pts)}` : ""}</span></li>`).join("")}</ul></section>`;
}

function krQuestsHTML(v) {
  const q = v.quests || [];
  const all = q.length && q.every((x) => x.done);
  return `<section class="kr-card"><div class="kr-h"><b>Today's quests</b><span>${all ? "All three done · +20" : "+10 each · +20 for all three"}</span></div>
    <ul class="kr-quests">${q.map((x) => `<li class="${x.done ? "done" : ""}"><span class="kr-tick" aria-hidden="true">${x.done ? "✓" : ""}</span>
      <span class="kr-qt">${krEsc(x.text)}</span><span class="kr-qn">${x.done ? "+10" : `${x.n} / ${x.goal}`}</span></li>`).join("")}</ul>
    <p class="kr-fine">New quests every day at midnight Eastern. Watching a live game is always one of them.</p></section>`;
}

function krBadgesHTML(v) {
  const rows = v.badges || [];
  const got = rows.filter((b) => b.tier).length;
  return `<section class="kr-card"><div class="kr-h"><b>Badges</b><span>${got} of ${rows.length} earned</span></div>
    <div class="kr-badges">${rows.map((b) => {
      const tier = b.one ? (b.tier ? "kr-b6" : "") : b.tier ? `kr-b${Math.min(6, b.tier)}` : "";
      const next = b.next != null && !b.one ? `${krNum(b.n)} / ${krNum(b.next)}` : b.one ? (b.tier ? "Earned" : "Not yet") : `${krNum(b.n)} · every tier`;
      const pct = b.next ? Math.round(Math.min(1, b.n / b.next) * 100) : 100;
      return `<div class="kr-badge${b.tier ? " on" : ""}" title="${krEsc(b.what)}">
        <span class="kr-medal ${tier}" aria-hidden="true">${KR_BADGE_ICON[b.key] || "★"}</span>
        <b>${krEsc(b.name)}</b><span class="kr-bt">${b.tier && !b.one ? krEsc(b.tier_name) : ""}</span>
        <span class="kr-bw">${krEsc(b.what)}</span>
        <span class="kr-bar"><i style="--p:${pct}%"></i></span><span class="kr-bn">${next}</span></div>`;
    }).join("")}</div></section>`;
}

function krLadderRowsHTML(lad) {
  if (!lad || !lad.rows) return `<p class="kr-fine">Loading…</p>`;
  const rows = lad.rows.length ? lad.rows.map((r) => `<li class="${r.me ? "me" : ""}"><span class="kr-rank">${r.rank}</span>
      <a href="#feed/u/${encodeURIComponent(r.handle)}">@${krEsc(r.handle)}</a><span class="kr-lv kr-${krEsc(krTier(r.level).cls)}">${Number(r.level)}</span>
      <span class="kr-pts">${krNum(r.points)}</span></li>`).join("")
    : `<li class="kr-empty">Nobody yet — the first karma this week puts you at the top.</li>`;
  const m = lad.mine || {};
  const mine = m.hidden ? `You are off the karma ladders. Turn it back on below.`
    : m.rank ? `You: #${m.rank} · ${krNum(m.points)} karma` : m.points ? `${krNum(m.points)} karma — make a username to stand on the ladder.` : "";
  return `<ol class="kr-ladder">${rows}</ol>${mine ? `<p class="kr-fine kr-mine">${krEsc(mine)}</p>` : ""}`;
}

/* The ways to earn, grouped the way a reader looks for them. */
const KR_RULE_GROUPS = [["Watching", ["watch_join", "watch", "witness"]],
  ["Talking", ["chat_day", "chat", "liked", "react_day", "hype"]],
  ["Playing along", ["vote", "vote_won", "call_won", "call_streak", "trivia"]],
  ["Every day", ["day", "quest", "quests_all"]],
  ["Friends", ["follow", "party_host", "party_join", "recruit"]],
  ["Your first two weeks", ["camp", "camp_done"]]];
function krRulesHTML(v) {
  const by = Object.fromEntries((v.rules || []).map((r) => [r.kind, r]));
  const row = (r) => `<li><span>${krEsc(r.why)}</span><b>+${Number(r.pts)}</b>${r.cap ? `<i>up to ${Number(r.cap)} a day</i>` : ""}</li>`;
  const groups = KR_RULE_GROUPS.map(([name, kinds]) => {
    const rows = kinds.filter((k) => by[k]).map((k) => row(by[k])).join("")
      + (name === "Every day" ? `<li><span>Days in a row: 3 · 7 · 14 · 30 · 50 · 100 · 200 · 365</span><b>+10 to +1,000</b><i>one missed day forgiven after seven</i></li>` : "");
    return rows ? `<li class="kr-rg">${krEsc(name)}</li>${rows}` : "";
  }).join("");
  return `<section class="kr-card"><div class="kr-h"><b>How karma works</b><span>Every way to earn it</span></div>
    <ul class="kr-rules">${groups}
      <li class="kr-rg">The week</li>
      <li><span>The week's top ten on the ladder</span><b>+25 to +100</b><i>a trophy, paid the Monday after</i></li></ul>
    <p class="kr-fine">Each thing pays once: the same message, game, call or day can't pay twice, and each kind has a daily limit. A message hidden for everyone gives back what it earned. Karma is never paid for a bet, a sportsbook, a parlay or a plan, and it buys nothing: it's your level, your badges and your flair.</p></section>`;
}

/* The site's own switch (Settings draws the same), or a checkbox. */
const krSwitch = (on, key, label) => (typeof setSwitch === "function"
  ? setSwitch(!!on, `data-kr="${key}" aria-label="${krEsc(label)}"`)
  : `<input type="checkbox" data-kr="${key}" aria-label="${krEsc(label)}"${on ? " checked" : ""}>`);

function krPrefsHTML(v) {
  const open = Number(v.level) >= Number((v.unlocks || {}).flair || 3);
  return `<section class="kr-card"><div class="kr-h"><b>Your flair</b><span>${open ? "Worn beside your name in every chat" : `Opens at level ${Number((v.unlocks || {}).flair || 3)}`}</span></div>
    <div class="kr-flairs${open ? "" : " locked"}">${(v.flairs || []).map((f) => `<button type="button" class="kr-flair${v.flair === f ? " on" : ""}"
      data-kr="flair" data-v="${krEsc(f)}"${open ? "" : " disabled"} aria-pressed="${v.flair === f}">${krEsc(f)}</button>`).join("")}${
      open && v.flair ? `<button type="button" class="kr-flair none" data-kr="flair" data-v="">None</button>` : ""}</div>
    <div class="kr-switch"><span><b>Show me on the karma ladders</b><span>Your username and karma on the week's and the all-time ladders.</span></span>
      ${krSwitch(v.ladder_on, "ladder", "Show me on the karma ladders")}</div>
    <div class="kr-switch"><span><b>Let friends see the game I'm watching</b><span>Your friends see which live game you have open, and you see theirs.</span></span>
      ${krSwitch(v.share !== false, "share", "Let friends see the game I'm watching")}</div>
    <div class="kr-switch"><span><b>Karma alerts</b><span>A nudge at 8 p.m. Eastern when your days in a row would end at midnight, your week's trophy and each new tier.</span>
      ${v.remind && !Number(v.phones) ? `<span class="kr-warn">Turn on alerts for this phone in Settings, under Alerts, and these come with them.</span>` : ""}</span>
      ${krSwitch(v.remind, "remind", "Karma alerts")}</div></section>`;
}

function krRecentHTML(v) {
  const rows = v.recent || [];
  if (!rows.length) return "";
  const when = (t) => {
    const d = new Date(Number(t) * 1000);
    return d.toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });
  };
  return `<section class="kr-card"><div class="kr-h"><b>Lately</b><span>+${krNum(v.today)} today</span></div>
    <ul class="kr-recent">${rows.map((r) => `<li><b>+${Number(r.pts)}</b><span>${krEsc(r.why)}</span><time>${krEsc(when(r.at))}</time></li>`).join("")}</ul></section>`;
}

function krPanelHTML(v) {
  const st = v.streak || {};
  const next = KR_TIERS.find(([at]) => at > Number(v.level));
  return `<section class="kr-card kr-hero kr-${krEsc(v.cls || "t1")}">
      ${krRingHTML(v, "big")}
      <div class="kr-hero-main"><p class="kr-kick">Your karma</p>
        <h2>Level ${Number(v.level)} · ${krEsc(v.tier)}</h2>
        <p class="kr-pts-big"><b>${krNum(v.points)}</b> karma</p>
        <span class="kr-bar wide"><i style="--p:${Math.round((Number(v.progress) || 0) * 100)}%"></i></span>
        <p class="kr-fine">${krNum(v.to - v.points)} to level ${Number(v.level) + 1}${next ? ` · ${krEsc(next[1])} at level ${next[0]}` : ""}</p></div>
      <div class="kr-streak${st.now ? " lit" : ""}"><b>🔥 ${Number(st.now || 0)}</b><span>day${st.now === 1 ? "" : "s"} in a row</span>
        <i>${st.best ? `best ${Number(st.best)}` : "earn karma today to start"}${st.rest ? " · a rest day in hand" : ""}</i></div>
    </section>
    ${krCampHTML(v)}
    ${krQuestsHTML(v)}
    ${krBadgesHTML(v)}
    <section class="kr-card"><div class="kr-h"><b>Karma ladder</b>
      <span class="kr-seg" role="group" aria-label="Which ladder"><button type="button" data-kr="scope" data-v="week" class="${KR.scope === "week" ? "on" : ""}">This week</button><button type="button" data-kr="scope" data-v="all" class="${KR.scope === "all" ? "on" : ""}">All time</button></span></div>
      <div class="kr-lad-host">${krLadderRowsHTML(KR.scope === "week" ? v.week : KR.lad.all)}</div>
      <p class="kr-fine">The week runs Monday to Sunday, Eastern. The top ten take a trophy and its karma on Monday.</p></section>
    ${krPrefsHTML(v)}
    ${krRulesHTML(v)}
    ${krRecentHTML(v)}
    <p class="kr-fine kr-tier-line">${KR_TIERS.map(([at, name, cls]) => `<span class="kr-lv kr-${cls}">${at}</span> ${krEsc(name)}`).join(" · ")}</p>`;
}

async function karmaPanelMount(el) {
  if (!el) return;
  el.innerHTML = KR.me ? krPanelHTML(KR.me) : `<section class="kr-card kr-wait"><p class="kr-fine">Loading your karma…</p></section>`;
  const v = await krLoad(true);
  if (!el.isConnected) return;
  if (!v) {
    el.innerHTML = `<section class="kr-card"><p class="kr-fine">Your karma could not load. Check your connection and open the tab again.</p></section>`;
    return;
  }
  el.innerHTML = krPanelHTML(v);
  if (KR.scope === "all") krLadder(el, "all");
}

async function krLadder(root, scope) {
  KR.scope = scope;
  const host = root.querySelector(".kr-lad-host");
  root.querySelectorAll('[data-kr="scope"]').forEach((b) => b.classList.toggle("on", b.dataset.v === scope));
  if (scope === "week" && KR.me) { if (host) host.innerHTML = krLadderRowsHTML(KR.me.week); return; }
  if (host && KR.lad[scope]) host.innerHTML = krLadderRowsHTML(KR.lad[scope]);
  try {
    const r = await fetch(`/api/karma/ladder?scope=${scope}`, { credentials: "same-origin", cache: "no-store" });
    if (r.ok) KR.lad[scope] = await r.json();
  } catch (e) { /* kept as it was */ }
  const h = root.querySelector(".kr-lad-host");
  if (h && KR.scope === scope) h.innerHTML = krLadderRowsHTML(KR.lad[scope]);
}

async function krPrefs(body, root) {
  try {
    const r = await fetch("/api/karma/prefs", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const out = await r.json().catch(() => ({}));
    if (!r.ok) { if (typeof tfToast === "function") tfToast(out.error || "That did not save."); return; }
    if (KR.me) Object.assign(KR.me, { flair: out.flair, ladder_on: out.ladder, remind: out.remind, phones: out.phones, share: out.share });
    if (root && KR.me) root.innerHTML = krPanelHTML(KR.me);
    const said = body.share !== undefined ? (out.share ? "Friends see your game" : "Your game is hidden from friends")
      : body.remind !== undefined ? (out.remind ? (out.phones ? "Karma alerts on" : "Karma alerts on — turn on this phone's alerts too")
      : "Karma alerts off")
      : body.ladder !== undefined ? (out.ladder ? "You're on the ladders" : "You're off the ladders")
      : out.flair ? `Wearing ${out.flair}` : "Flair off";
    if (typeof tfToast === "function") tfToast(said);
  } catch (e) {
    if (typeof tfToast === "function") tfToast("No connection — try again.");
  }
}

/* ---------------- a profile's row ---------------- */

function karmaProfileMount(host, k, mine) {
  if (!host || !k) return;
  const st = Number(k.streak || 0);
  const medals = (k.badges || []).map((b) => `<span class="kr-medal sm ${b.one ? "kr-b6" : `kr-b${Math.min(6, b.tier)}`}" title="${
    krEsc(b.name)}${b.tier_name && !b.one ? ` · ${krEsc(b.tier_name)}` : ""}">${KR_BADGE_ICON[b.key] || "★"}</span>`).join("");
  const inner = `${krRingHTML(k)}<span class="kr-prof-main"><b>Level ${Number(k.level)} · ${krEsc(k.tier)}${k.flair ? ` ${krEsc(k.flair)}` : ""}</b>
      <span>${krNum(k.points)} karma${st ? ` · 🔥 ${st} day${st === 1 ? "" : "s"}` : ""}</span></span>
    ${medals ? `<span class="kr-prof-medals">${medals}</span>` : ""}`;
  host.innerHTML = mine
    ? `<button type="button" class="kr-prof" data-kr="open" aria-label="Your karma: open the Karma tab">${inner}<span class="kr-go" aria-hidden="true">›</span></button>`
    : `<div class="kr-prof">${inner}</div>`;
}

/* ---------------- taps ---------------- */

function krOpenTab() {
  window._acctTab = "karma";
  const el = document.getElementById("acct-prof");
  if (location.hash.startsWith("#account") && el && el.isConnected && window.QBSocial && window.QBSocial.mountAccount) {
    window.QBSocial.mountAccount(el);
    return;
  }
  if (typeof switchView === "function") switchView("account", true);
  else location.hash = "#account";
}

document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("[data-kr]");
  if (!b) return;
  const act = b.dataset.kr;
  if (act === "open") { e.preventDefault(); krOpenTab(); return; }
  if (act === "up-close") { const up = b.closest(".kr-up"); if (up) up.remove(); return; }
  const root = b.closest(".kr-panel-host");
  if (act === "scope" && root) { krLadder(root, b.dataset.v === "all" ? "all" : "week"); return; }
  if (act === "flair" && root && !b.disabled) krPrefs({ flair: b.dataset.v || "" }, root);
  if (act === "game") { e.preventDefault(); if (typeof openPbp === "function") openPbp(b.dataset.lg, b.dataset.ev); return; }
  if ((act === "ladder" || act === "remind" || act === "share") && b.getAttribute("role") === "switch") {
    const on = b.getAttribute("aria-checked") !== "true";
    b.setAttribute("aria-checked", on ? "true" : "false");
    krPrefs({ [act]: on }, root);
  }
});
document.addEventListener("change", (e) => {
  const b = e.target.closest && e.target.closest('[data-kr="ladder"], [data-kr="remind"], [data-kr="share"]');
  if (b) krPrefs({ [b.dataset.kr]: !!b.checked }, b.closest(".kr-panel-host"));
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const up = document.querySelector(".kr-up");
  if (up) up.remove();
});
