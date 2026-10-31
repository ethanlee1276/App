/* Qellys Book — Ask Qellys, the chat room.
   ==========================================================================
   Loaded the first time Ask opens (app.js renderAsk, loadRoom), 2026-10-27:
   moved whole out of app.js, in order, with its own comments, so a first
   visit to any other page carries none of it. A classic script like app.js:
   it shares the page's globals (state, escapeHtml, the conversation's
   askState/askSave, the mascot's qbotHTML/askAva, askErrorText,
   ASK_THINK_MS, loadSlip), and its renderAsk replaces app.js's loader of the
   same name. */
const ASK_SUGGEST = ["What’s the best bet on tonight’s board?",
                     "Who is most likely to hit tonight?",
                     "How has our record been lately?"];
/* Asked from a prop page: the three questions a reader has about one bet.
   Fixed wording on purpose — the same words are the same cached answer. */
const ASK_SUGGEST_PICK = ["Why this pick?", "How has this player done lately?", "What could go wrong?"];
/* Asked about your own open bets (askOpenBets): the three questions a bettor
   has about a ticket in play. */
const ASK_SUGGEST_BETS = ["How are my bets doing?", "Which of my bets is in the most trouble?",
                          "Should I hedge any of them?"];

/* YOUR TEAMS AND PLAYERS, WHEN YOU ATTACH THEM (docs/IDEAS.md round three):
   the teams you follow (Settings) and the players you watch (Alerts) go with
   the question, this visit only, and the answer is about them first
   (engine/askbot follows_facts: their games tonight and our picks on them). */
const ASK_SUGGEST_FOLLOWS = ["What’s on for my teams tonight?", "Any picks on my players tonight?",
                             "Which of my teams has the best bet tonight?"];
function askFollows() {
  const teams = (typeof settings === "function" ? settings().teams : []) || [];
  const watches = ((typeof _alertsCache !== "undefined" && _alertsCache) || {}).watches || [];
  const players = watches.filter((w) => w && w.kind === "player" && w.value).map((w) => String(w.value));
  return { teams: teams.slice(0, 24), players: players.slice(0, 24) };
}
const askFollowCount = () => { const f = askFollows(); return f.teams.length + f.players.length; };

/* YOUR OPEN BETS, WHEN YOU ATTACH THEM (2026-10-27). FanDuel's AceAI knows
   your bets because it is the book; this knows them across every book, and
   only when you say so: the paperclip's "My open bets" attaches the pending
   tickets in My Bets, newest first, and only they go with the question
   (server.py _bets_standing grades each one the box can follow, live, the
   way the Live tab does; engine/askbot never caches an answer about them). */
function askOpenBets() {
  return (typeof mbLoad === "function" ? mbLoad() : [])
    .filter((b) => b && b.result === "pending" && b.desc)
    .sort((x, y) => String(y.id).localeCompare(String(x.id)))
    .slice(0, 8)
    .map((b) => ({ desc: b.desc, odds: b.odds, stake: b.stake, book: b.book, sport: b.sport, date: b.date,
                   legs: Array.isArray(b.legs) ? b.legs : undefined }));
}

/* THE CHAT ROOM. Ethan, 2026-09-23, the site footer circled on his phone:
   "Get rid of all this shit down here and make this look more like an
   actual ai chat room." One column pinned between the top bar and the tab
   bar (askRoomSize measures it, as msgThreadSize does for a message
   thread): a header, the conversation — the only thing that scrolls — and
   the composer at the foot. The site footer leaves while it is open
   (body.ask-open); the league row stays as text tabs, as Ethan's render
   draws it. The one line of the footer that must stay — not advice, 21+,
   the helpline — rides in the intro card. */

/* Which face the room wears: see the mascot's note above. */
function askBotState(mode) {
  const room = document.getElementById("ask-room");
  if (room) room.dataset.bot = mode;
}

/* LAID OUT, NOT RUN TOGETHER. Ethan, 2026-09-23, a top-ten answer circled:
   "Everything we ask is all jumbled up in one paragraph so it makes it hard
   to read." Only blank lines used to split an answer, so a ranking written
   one team to a line arrived as one run-on block. Now each line keeps its
   break, lines starting "1." or "- " become a real numbered or bulleted
   list, and **bold** is bold. A ranking crammed onto one line ("1. Bills …
   2. Panthers … 3. …") is split back into its items. Everything is escaped
   first; only these three shapes ever become markup. */
const ASK_ITEM = /^\s*(?:(\d{1,2})[.)]|[-•*–])\s+/;

function askUncram(line) {
  // "1. A 2. B 3. C" on one line: split where the numbers run 1, 2, 3 …
  // Ties skip numbers (4, 4, 4, then 7), so each must only be larger, by a little.
  const at = [];
  const re = /(^|\s)(\d{1,2})[.)]\s+(?=\S)/g;
  let m, last = 0;
  while ((m = re.exec(line))) {
    const n = Number(m[2]);
    if (at.length ? n > last && n <= last + 4 : n === 1) { at.push(m.index + m[1].length); last = n; }
  }
  if (at.length < 3 || at[0] > 0 && !/[:\-–—]\s*$/.test(line.slice(0, at[0]))) return [line];
  const cut = [line.slice(0, at[0])].concat(at.map((a, i) => line.slice(a, at[i + 1])));
  return cut.map((x) => x.trim()).filter(Boolean);
}

function askInline(text) {
  return String(text).split(/\*\*(.+?)\*\*/g)
    .map((t, i) => ({ t: i % 2 ? t : t.replace(/\*\*/g, ""), b: i % 2 === 1 }))
    .filter((r) => r.t);
}

function askBlocks(text) {
  const out = [];
  String(text || "").replace(/\r/g, "").split(/\n\s*\n/).forEach((chunk) => {
    let cur = null;
    chunk.split("\n").flatMap(askUncram).forEach((raw) => {
      const line = raw.replace(/^\s*#{1,6}\s+/, "").trim();
      if (!line) return;
      const m = line.match(ASK_ITEM);
      const tag = !m ? "p" : m[1] ? "ol" : "ul";
      if (!cur || cur.tag !== tag) {
        cur = { tag, rows: [] };
        out.push(cur);
      }
      const body = m ? line.slice(m[0].length) : line;
      const runs = askInline(/^#/.test(raw.trim()) ? `**${body.replace(/\*\*/g, "")}**` : body);
      if (runs.length) cur.rows.push({ runs, n: m && m[1] ? Number(m[1]) : 0 });
    });
  });
  return out.filter((b) => b.rows.length);
}

function askRunsHTML(runs) {
  return runs.map((r) => r.b ? `<strong>${escapeHtml(r.t)}</strong>` : escapeHtml(r.t)).join("");
}

function askBlockOpen(b) {
  return b.tag === "p" ? "<p>" : `<${b.tag} class="ask-list">`;
}

// A ranked item carries its own number, so a tie (4, 4, 4, 7) reads as written.
function askItemOpen(r) {
  return r.n ? `<li value="${r.n}">` : "<li>";
}

function askBodyHTML(text) {
  return askBlocks(text).map((b) => askBlockOpen(b) + (b.tag === "p"
    ? b.rows.map((r) => askRunsHTML(r.runs)).join("<br>")
    : b.rows.map((r) => askItemOpen(r) + askRunsHTML(r.runs) + "</li>").join("")) + `</${b.tag}>`).join("");
}

/* UNDER AN ANSWER, TWO LABELLED ROWS. Ethan, 2026-09-23, a Josh Allen
   answer with ten chips circled under it: "What exactly are we showing
   here, this is just cluttered garbage and we are not explaining what this
   is." The chips were every board row the question's words touched —
   Nick Allen's hits among them — in one unlabelled pile.

   Now: SOURCES, what the answer read (a lookup, a web page, a game's lines,
   the injury board); and ON TONIGHT'S BOARD, at most three of tonight's
   picks for the player or game the answer is about, each a door to its
   pick page. The server chooses which (engine/askbot.shown_sources); a
   saved answer from before carries its chips unmarked, so a chip with a
   pick id counts as a pick here too.

   A web page is a link to that page: citing it is the condition of
   showing the answer at all. Only an http(s) address becomes a link. */
function askSourcesHTML(t) {
  const src = (t.sources || []).filter((s) => s && s.label);
  const isPick = (s) => s.kind === "pick" || !!s.prop;
  const read = src.filter((s) => !isPick(s)).slice(0, 6);
  const picks = src.filter(isPick).slice(0, 3);
  const chip = (s) => /^https?:\/\//i.test(String(s.url || ""))
    ? `<a class="ask-chip web" href="${escapeAttr(s.url)}" target="_blank" rel="noopener noreferrer"
         title="A web page, not our data">web · ${escapeHtml(s.label)} ↗</a>`
    : s.prop
    ? `<span class="ask-chip pick" data-prop="${escapeAttr(s.prop)}" tabindex="0" role="link">${
      escapeHtml(s.label)} ›</span>`
    : `<span class="ask-chip${isPick(s) ? " pick" : ""}">${escapeHtml(s.label)}</span>`;
  const row = (head, list, cls) => list.length
    ? `<div class="ask-src${cls}"><span class="ask-src-h">${head}</span>${list.map(chip).join("")}</div>` : "";
  return row("Sources", read, "")
    + row("On tonight’s board <em>tap one for our full read</em>", picks, " ask-src-picks");
}

function askTurnHTML(t, live = false) {
  const who = t.role === "user" ? "me" : t.error ? "err" : "bot";
  // The answer about to be typed out arrives as an empty bubble; askTypeOut fills it.
  if (t === _askTyping) {
    return `<div class="ask-row bot">${askAva(true)}<div class="ask-turn bot typing" id="ask-typing"></div></div>`;
  }
  return `<div class="ask-row ${who}">${who === "me" ? "" : askAva(live)}<div class="ask-turn ${who}${t.slip ? " has-slip" : ""}">${
    t.slip ? askSlipCard(t) : askBodyHTML(t.text)}${askCardsHTML(t)}${askSourcesHTML(t)}</div></div>${
    live ? askNextHTML(t) : ""}`;
}

/* THE NUMBERS, DRAWN (2026-10-27, engine/askcards). Under an answer, the
   lookups' own numbers as cards: how often he has cleared the line (the
   last five, the last ten, the season, every stored game) with his last
   ten games as bars against it; every book's price with the best marked;
   our record; a start/sit's projections and its call. Built on the server
   from what the tools returned, never from the model's words, so a card
   cannot say a number the data does not. */
const ASK_CARD = {
  hits(c, tail = "") {
    const over = c.side !== "under";
    const line = Number(c.line);
    const pct = (r) => (r == null ? "–" : `${Math.round(r * 100)}%`);
    const games = (c.games || []).slice().reverse();               // oldest first, newest at the right
    const top = Math.max(line, ...games.map((g) => Number(g.value) || 0)) * 1.15 || 1;
    const hit = (v) => (over ? v > line : v < line) ? "hit" : v === line ? "push" : "miss";
    return `<div class="ask-card ask-hits">
      <div class="ask-card-h"><b>${escapeHtml(c.player || "")}</b><span>${escapeHtml(c.stat || "")} · ${
        over ? "over" : "under"} ${escapeHtml(String(c.line))}</span></div>
      <div class="ask-hw-row">${(c.windows || []).map((w) => `<span class="ask-hw${w.rate != null && w.rate >= .5 ? " up" : ""}">
        <b>${pct(w.rate)}</b><em>${w.hit}/${w.of}</em><small>${escapeHtml(String(w.label))}</small></span>`).join("")}</div>
      ${games.length ? `<div class="ask-bars" role="img" aria-label="${escapeAttr(`Last ${games.length} games: ${
          games.map((g) => g.value).join(", ")}; the line is ${c.line}`)}">${games.map((g) => {
          const h = Math.max(4, Math.round((Number(g.value) / top) * 100));
          // A tall bar carries its number inside its top, clear of the line.
          return `<span class="ask-bar ${hit(Number(g.value))}${h >= 30 ? " in" : ""}" style="height:${h}%"><i>${
            escapeHtml(String(g.value))}</i></span>`;
        }).join("")}<span class="ask-line" style="bottom:${
          Math.round((line / top) * 100)}%"></span></div>
        <div class="ask-bars-x">${games.map((g) => `<span>${escapeHtml(g.vs || "")}</span>`).join("")}</div>` : ""}
      ${tail}
    </div>`;
  },
  prices(c, tail = "") {
    const pick = String(c.pick || "");
    const side = /\bunder\b/i.test(pick) ? "under_odds" : /\bover\b/i.test(pick) ? "over_odds" : "";
    const odds = (n) => (n == null ? "–" : n > 0 ? `+${n}` : String(n));
    return `<div class="ask-card ask-prices">
      <div class="ask-card-h"><b>Every book’s price</b><span>${escapeHtml(pick)}</span></div>
      ${(c.books || []).map((b) => `<div class="ask-pr${b.book === c.best ? " best" : ""}"><b>${escapeHtml(b.book)}</b>
        <span>${b.line != null ? escapeHtml(String(b.line)) : ""}</span><em>${side ? odds(b[side])
          : `${odds(b.over_odds)} / ${odds(b.under_odds)}`}</em>${b.book === c.best ? `<small>best</small>` : ""}</div>`).join("")}
      ${askTapeHTML(c.tape)}
      ${c.move ? `<div class="ask-card-f">Line ${escapeHtml(String(c.move.open))} at open, ${
        escapeHtml(String(c.move.current))} now</div>` : ""}
      ${tail}
    </div>`;
  },
  record(c) {
    const roi = c.roi == null ? null : Number(c.roi) * 100;
    const l30 = c.last_30 || null;
    return `<div class="ask-card ask-record">
      <div class="ask-card-h"><b>Our record</b><span>${c.since ? `since ${escapeHtml(String(c.since))}` : "every graded pick"}</span></div>
      <div class="ask-rec"><span><b>${c.wins ?? 0}–${c.losses ?? 0}${c.pushes ? `–${c.pushes}` : ""}</b><small>won–lost</small></span>
        ${roi == null ? "" : `<span><b class="${roi >= 0 ? "pos" : "neg"}">${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%</b><small>ROI</small></span>`}
        ${c.units == null ? "" : `<span><b class="${c.units >= 0 ? "pos" : "neg"}">${c.units >= 0 ? "+" : ""}${
          Number(c.units).toFixed(1)}u</b><small>units</small></span>`}</div>
      ${l30 ? `<div class="ask-card-f">Last 30 days: ${l30.wins ?? 0}–${l30.losses ?? 0}, ${
        Number(l30.net_units || 0) >= 0 ? "+" : ""}${Number(l30.net_units || 0).toFixed(1)}u</div>` : ""}
    </div>`;
  },
  startsit(c) {
    const lead = (c.call || {}).start;
    return `<div class="ask-card ask-ss">
      <div class="ask-card-h"><b>Start or sit</b><span>${escapeHtml(c.scoring || "")}</span></div>
      ${(c.players || []).map((p) => `<div class="ask-ss-r${p.player === lead ? " lead" : ""}"><b>${escapeHtml(p.player || "")}</b>
        <span>${escapeHtml([p.position, p.team && p.opponent ? `${p.team} vs ${p.opponent}` : p.team, p.injury]
          .filter(Boolean).join(" · "))}</span><em>${p.points == null ? "–" : Number(p.points).toFixed(1)}</em></div>`).join("")}
      ${c.call && c.call.text ? `<div class="ask-card-f">${escapeHtml(c.call.text)}</div>` : ""}
    </div>`;
  },
};
/* THE LINE'S PATH (docs/IDEAS.md round three): the line since it opened as
   a step chart, the open on the left and now on the right, each change a
   step, the latest number marked. */
function askTapeHTML(tape) {
  const pts = (tape || []).map((p) => Number(p.line)).filter(Number.isFinite);
  if (pts.length < 2) return "";
  const W = 260, H = 46, lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
  const x = (i) => Math.round((i / (pts.length - 1)) * (W - 8)) + 4;
  const y = (v) => (hi === lo ? H / 2 : Math.round(H - 6 - ((v - lo) / span) * (H - 12)));
  const d = pts.map((v, i) => (i ? `H${x(i)}V${y(v)}` : `M${x(0)} ${y(v)}`)).join("");
  const last = pts[pts.length - 1];
  return `<div class="ask-tape"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeAttr(
    `The line since it opened: ${pts.join(", ")}`)}"><path d="${d}"/><circle cx="${x(pts.length - 1)}" cy="${y(last)}" r="3.5"/></svg>
    <span><em>${escapeHtml(String(pts[0]))}</em><b>${escapeHtml(String(last))}</b></span></div>`;
}
function askCardsHTML(t) {
  const cards = (t.cards || []).filter((c) => c && ASK_CARD[c.kind]);
  // One card carries the buttons: the last one about a bet (the price card,
  // when there is one, has the best price on it).
  const acts = cards.map((c) => !!(c.bet && c.bet.player)).lastIndexOf(true);
  return cards.map((c, i) => ASK_CARD[c.kind](c, i === acts ? askActsHTML(c.bet, c.kind) : "")).join("");
}

/* WHAT TO ASK NEXT: up to three questions from what the answer looked up
   and who it was about (engine/askcards.follow_ups). A tap asks it. */
function askNextHTML(t) {
  const qs = (t.follow || []).filter(Boolean).slice(0, 3);
  return qs.length ? `<div class="ask-next" aria-label="Ask next">${qs.map((q) =>
    `<button type="button" class="ask-next-q" data-ask-q="${escapeAttr(q)}">${escapeHtml(q)}</button>`).join("")}</div>` : "";
}

/* AN ANSWER YOU CAN ACT ON (2026-10-27; Ethan: "look at other apps that use
   AI betting ... and do it better"). FanDuel's AceAI puts a bet on its slip
   and Action Network's Playbook pre-fills one; neither follows it once it
   is placed. Under a card about tonight's player line, three buttons:

     Add to slip  the leg the board's own slip chip adds (slipToggle), on
                  the board it is on: the slip holds one board at a time, so
                  an answer about another league's player leaves it off.
     Track it     a My Bets entry of one leg in the screenshot checker's shape
                  (src "slip", the leg in engine/slipgrade's words), so the
                  Live tab follows it, the box settles it off the box score
                  and the member's phones hear "your bet is on" and how it
                  ended (engine/slipwatch, engine/pushmine). The stake is
                  typed; the price is the card's and can be changed to the
                  one they got. A market the checker cannot follow is logged
                  as a hand-entered bet instead, and says so.
     Watch        the player as an Alerts watch: his line moving, a pick on
                  him posting (engine/alerts; on the phone where asked).

   Each button says what is already done when the answer is drawn again: in
   the slip, tracked, watched. */
function askBetRow(b) {
  return { player: b.player, market: b.market, market_label: b.market_label || b.market, side: b.side,
           line: b.line, odds: b.odds, team: b.team || "", book: b.book || "", opponent: b.opponent || "",
           game_date: b.game_date || "" };
}
function askBetName(b) {
  const side = String(b.side || "").toLowerCase();
  return `${b.player} ${side.charAt(0).toUpperCase()}${side.slice(1)} ${b.line} ${b.market_label || b.market}`;
}
function askBetKey(b) {
  return `ask-${slugify(b.player)}-${slugify(b.market)}-${String(b.side || "").toLowerCase()}-${b.line}-${
    String(b.game_date || "").slice(0, 10)}`;
}
function askOdds(n) {
  return n > 0 ? `+${n}` : `−${Math.abs(n)}`;
}
function askToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
/* The My Bets entry. A trackable bet is a ticket of one leg the box can
   follow; any other is the hand-logged kind, graded by its owner. */
/* YOUR STAKE, FILLED IN (docs/IDEAS.md round three): your unit from the
   Bankroll page times our stake for the pick, when a bankroll is set. */
function askStakeGuess(b) {
  const u = typeof unitDollars === "function" ? unitDollars() : 0;
  return u > 0 ? String(Math.max(1, Math.round(u * (Number(b.stake_units) || 1)))) : "";
}
function askBetEntry(b, stake, odds, book) {
  const e = { id: Date.now() + "" + Math.floor(Math.random() * 1e4), book: book || "Other",
              sport: String(b.sport || "").toUpperCase(), date: String(b.game_date || "").slice(0, 10) || askToday(),
              desc: askBetName(b), stake, odds, result: "pending", slip_key: askBetKey(b) };
  if (!b.trackable) return e;
  return Object.assign(e, { src: "slip", legs: [{
    sport: b.sport, player: b.player, team: b.team || "", game: / @ /.test(b.matchup || "") ? b.matchup : "",
    market: b.market, side: String(b.side || "").toLowerCase(), line: b.line, odds, text: askBetName(b) }] });
}
function askWatching(player) {
  const ws = ((typeof _alertsCache !== "undefined" && _alertsCache) || {}).watches || [];
  const me = String(player || "").toLowerCase();
  return ws.some((w) => w && w.kind === "player" && String(w.value || "").toLowerCase() === me);
}
/* A PRICE ALERT ON THIS BET (engine/alerts, the "price" shape): its player,
   market and side, at the price the reader wants. On the price card the
   third button sets one instead of watching the player; it starts one notch
   better than the best price there is. */
function askPriceKey(b) {
  return `${b.player}|${b.market}|${String(b.side || "").toUpperCase()}|`;
}
function askAlerted(b) {
  const ws = ((typeof _alertsCache !== "undefined" && _alertsCache) || {}).watches || [];
  return ws.some((w) => w && w.kind === "price" && String(w.value || "").startsWith(askPriceKey(b)));
}
function askNotchBetter(odds) {
  const o = Number(odds);
  let t = o + 5;
  if (o < 0) {
    t = Math.floor(t / 5) * 5;                    // to a round number: −108 asks for −105
    if (t > -100) t = 200 + t;                    // past even money: −95 is +105
  }
  return t > 0 ? Math.ceil(t / 5) * 5 : t;
}
let _askWatchesRead = false;
function askActsHTML(b, kind = "") {
  if (!b || !b.player) return "";
  // What the reader already watches, read once a visit; the buttons are
  // drawn again when it lands.
  if (!_askWatchesRead && typeof alertsFetch === "function") {
    _askWatchesRead = true;
    alertsFetch().then(() => askActsPaint());
  }
  const tracked = mbLoad().find((x) => x && x.slip_key === askBetKey(b));
  const slipOk = b.sport === state.sport && typeof slipToggle === "function";
  const inSlip = slipOk && slipHas(askBetRow(b));
  const watching = askWatching(b.player);
  const priced = kind === "prices";
  const alerted = priced && askAlerted(b);
  const side = String(b.side || "").toLowerCase();
  // An action bar: each button its icon over a word or two, three to a row
  // on the narrowest phone; the words say what is already done.
  const act = (name, on, ic, word, done, attrs) => `<button type="button" class="ask-act${on ? " on" : ""}" data-ask-act="${
    name}"${attrs}>${icon(on ? "check" : ic, 16)}<span>${on ? done : word}</span></button>`;
  return `<div class="ask-acts" data-ask-bet="${escapeAttr(JSON.stringify(b))}" data-ask-kind="${escapeAttr(kind)}">
      <div class="ask-acts-bet"><span><b>${escapeHtml(`${side.charAt(0).toUpperCase()}${side.slice(1)} ${b.line}`)}</b> ${
        escapeHtml(b.market_label || b.market)}</span><span class="ask-acts-px"><b>${escapeHtml(askOdds(b.odds))}</b>${
        b.book ? ` ${escapeHtml(b.book)}` : ""}</span></div>
      <div class="ask-acts-row">
        ${slipOk ? act("slip", inSlip, "ticket", "Add to slip", "In your slip", ` aria-pressed="${inSlip ? "true" : "false"}"`) : ""}
        ${act("track", !!tracked, "chart", "Track it", "In My Bets", `${tracked ? " disabled" : ""} aria-expanded="false"`)}
        ${priced ? act("alert", alerted, "bell", "Price alert", "Alert set", `${alerted ? " disabled" : ""} aria-expanded="false"`)
          : act("watch", watching, "bell", "Watch", "Watching", `${watching ? " disabled" : ""} aria-label="${
          escapeAttr(`${watching ? "Watching" : "Watch"} ${b.player}`)}"`)}
      </div>
      ${priced ? `<form class="ask-track ask-alert" hidden>
        <label>Tell me at <input inputmode="text" data-ask-target value="${escapeAttr(askOdds(askNotchBetter(b.odds)))}"
          aria-label="The price you want"></label>
        <button type="submit" class="ask-act primary">Set the alert</button>
        <p class="ask-track-note">When any book has it at that price or better, or its line moves: on Alerts, and on your
          phone if alerts are on.</p>
      </form>` : ""}
      <form class="ask-track ask-save" hidden>
        <label>Stake $<input inputmode="decimal" data-ask-stake placeholder="10" value="${askStakeGuess(b)}" aria-label="Stake in dollars"></label>
        <label>Price <input inputmode="text" data-ask-odds value="${escapeAttr(askOdds(b.odds))}" aria-label="American price"></label>
        <button type="submit" class="ask-act primary">Save to My Bets</button>
        <p class="ask-track-note">${b.trackable
          ? "We follow it on the Live tab and settle it in My Bets off the box score."
          : "Logged in My Bets for you to grade: we can’t follow this market live yet."}</p>
      </form>
    </div>`;
}
/* Every action row on the page, drawn again from the state it reads. */
function askActsPaint() {
  document.querySelectorAll(".ask-acts").forEach((box) => {
    let b = null;
    try { b = JSON.parse(box.dataset.askBet || "null"); } catch (e) { b = null; }
    const open = [...box.querySelectorAll(".ask-track")].some((f) => !f.hidden);
    if (b && !open) box.outerHTML = askActsHTML(b, box.dataset.askKind || "");   // never under a number being typed
  });
}
async function askActAlert(form, b) {
  const note = form.querySelector(".ask-track-note");
  const typed = String((form.querySelector("[data-ask-target]") || {}).value || "").replace(/[−–]/g, "-").replace(/[^\d+-]/g, "");
  const odds = parseInt(typed, 10);
  if (!odds || Math.abs(odds) < 100) { note.textContent = "Type an American price, like −105 or +120."; return; }
  const out = await alertsPost("watch", { kind: "price", value: `${askPriceKey(b)}${odds}` });
  if (out.error) { note.textContent = out.error; return; }
  if (typeof _alertsCache !== "undefined") _alertsCache = Object.assign(_alertsCache || {}, { watches: out.watches || [] });
  form.hidden = true;
  tfToast(`Alert set: ${b.player} ${String(b.side || "").toLowerCase()} at ${askOdds(odds)} or better.`);
  askActsPaint();
}
function askActTrack(form, b) {
  const note = form.querySelector(".ask-track-note");
  const stake = Number(String((form.querySelector("[data-ask-stake]") || {}).value || "").replace(/[$,\s]/g, ""));
  const typed = String((form.querySelector("[data-ask-odds]") || {}).value || "").replace(/[−–]/g, "-").replace(/[^\d+-]/g, "");
  const odds = parseInt(typed, 10);
  if (!(stake > 0)) { note.textContent = "Type the stake you placed it for."; return; }
  if (!odds || Math.abs(odds) < 100) { note.textContent = "Type the American price you got, like −110 or +120."; return; }
  const bets = mbLoad();
  if (!bets.some((x) => x && x.slip_key === askBetKey(b))) {
    // The card's book, unless the price typed is another one's.
    bets.push(askBetEntry(b, stake, odds, odds === b.odds ? b.book : ""));
    mbSave(bets);
  }
  form.hidden = true;
  tfToast(b.trackable ? "In My Bets: we follow it on the Live tab." : "In My Bets.");
  track("bet_logged", "ask");
  if (typeof pushAskTick === "function") pushAskTick({ bet: true });
  askActsPaint();
}
async function askActWatch(b) {
  const out = await alertsPost("watch", { kind: "player", value: b.player });
  if (out.error) { tfToast(out.error); return; }
  if (typeof _alertsCache !== "undefined") _alertsCache = Object.assign(_alertsCache || {}, { watches: out.watches || [] });
  tfToast(`Watching ${b.player}: Alerts has what moves.`);
  askActsPaint();
}
document.addEventListener("click", (e) => {
  const btn = e.target && e.target.closest && e.target.closest("[data-ask-act]");
  const box = btn && btn.closest(".ask-acts");
  if (!box) return;
  let b = null;
  try { b = JSON.parse(box.dataset.askBet || "null"); } catch (x) { b = null; }
  if (!b) return;
  const act = btn.dataset.askAct;
  if (act === "slip") {
    // The slip's pill appears now: measured afresh, it sits above the box.
    if (b.sport === state.sport && slipToggle(askBetRow(b))) { askActsPaint(); askRoomSize(); }
  } else if (act === "track" || act === "alert") {
    const form = box.querySelector(act === "track" ? ".ask-save" : ".ask-alert");
    form.hidden = !form.hidden;
    btn.setAttribute("aria-expanded", form.hidden ? "false" : "true");
    if (!form.hidden) {
      form.scrollIntoView({ block: "nearest" });
      const first = form.querySelector("[data-ask-stake], [data-ask-target]");
      if (first) first.focus({ preventScroll: true });
    }
  } else if (act === "watch") {
    btn.disabled = true;
    askActWatch(b).finally(() => { btn.disabled = false; });
  }
});
document.addEventListener("submit", (e) => {
  const form = e.target && e.target.closest && e.target.closest(".ask-track");
  const box = form && form.closest(".ask-acts");
  if (!box) return;
  e.preventDefault();
  let b = null;
  try { b = JSON.parse(box.dataset.askBet || "null"); } catch (x) { b = null; }
  if (b) (form.classList.contains("ask-alert") ? askActAlert : askActTrack)(form, b);
});

function askSlipCard(t) {
  if (window.QBSlip) return window.QBSlip.card(t.slip);
  loadSlip().then((S) => { if (S && state.view === "ask") renderAsk(); });
  return askBodyHTML(t.text);
}

/* TYPED, NOT DROPPED IN. Ethan, 2026-09-23: "We should add the 3 dots that
   wiggle when the chat bot is thinking and typing too to make it feel more
   real." While the question is out, a bubble of three bouncing dots and
   nothing else; when the answer lands it writes itself out a word at a
   time behind a caret, a beat longer after each sentence, and its source
   chips arrive when it finishes. Only the newest answer, only once — a
   re-render mid-sentence just shows it whole — and never for a reader who
   has asked for reduced motion. */

const ASK_WORD_MS = 24;
const ASK_SENTENCE_MS = 110;
let _askTyping = null;

function askTypeOut() {
  const t = _askTyping;
  const bub = document.getElementById("ask-typing");
  const log = document.getElementById("ask-log");
  if (!t || !bub || !log) return;
  const done = () => {
    if (_askTyping === t) _askTyping = null;
    askBotState("happy");                          // a hop when it finishes, then back to idle
    setTimeout(() => {
      const room = document.getElementById("ask-room");
      if (room && room.dataset.bot === "happy") room.dataset.bot = "idle";
    }, 1300);
    bub.classList.remove("typing");
    bub.removeAttribute("id");
    bub.innerHTML = askBodyHTML(t.text) + askCardsHTML(t) + askSourcesHTML(t);
    const row = bub.closest(".ask-row");
    if (row && !(row.nextElementSibling && row.nextElementSibling.classList.contains("ask-next"))) {
      row.insertAdjacentHTML("afterend", askNextHTML(t));
      const next = row.nextElementSibling;
      if (next && next.classList.contains("ask-next")) {
        next.querySelectorAll("[data-ask-q]").forEach((b) => b.addEventListener("click", () => askSend(b.dataset.askQ)));
      }
    }
    log.removeAttribute("aria-busy");
    log.scrollTop = log.scrollHeight;
  };
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { done(); return; }
  // Written into the same shape it will end in: each line or list item
  // appears when its turn comes, and a bold run is bold as it is typed.
  const rows = [];
  askBlocks(t.text).forEach((b, bi) => b.rows.forEach((r, i) => rows.push({ b, bi, i, runs: r.runs, n: r.n })));
  let ri = 0, ui = 0, wi = 0, words = null, host = null, into = null, block = null, blockAt = -1;
  askBotState("talking");
  log.setAttribute("aria-busy", "true");        // one announcement when it is whole, not one per word
  const step = () => {
    if (!bub.isConnected || _askTyping !== t) return;          // re-rendered: it is showing whole
    if (ri >= rows.length) { done(); return; }
    const row = rows[ri];
    if (!host) {
      if (row.bi !== blockAt) {
        const tmp = document.createElement("div");
        tmp.innerHTML = askBlockOpen(row.b) + `</${row.b.tag}>`;
        block = bub.appendChild(tmp.firstChild);
        blockAt = row.bi;
      }
      if (row.b.tag === "p") {
        if (row.i) block.appendChild(document.createElement("br"));
        host = block;
      } else {
        host = block.appendChild(document.createElement("li"));
        if (row.n) host.value = row.n;
      }
      ui = 0;
      words = null;
    }
    if (!words) {
      const run = row.runs[ui];
      into = host.appendChild(run.b ? document.createElement("strong") : document.createTextNode(""));
      words = run.t.split(/(\s+)/).filter(Boolean);
      wi = 0;
    }
    const low = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
    let word = words[wi++];
    if (/^\s+$/.test(word) && wi < words.length) word += words[wi++];
    if (into.nodeType === 3) into.data += word; else into.textContent += word;
    if (low) log.scrollTop = log.scrollHeight;
    if (wi >= words.length) {
      words = null;
      ui += 1;
      if (ui >= row.runs.length) { ri += 1; host = null; }
    }
    setTimeout(step, /[.!?:]["’”)]?\s*$/.test(word) || !host ? ASK_SENTENCE_MS : ASK_WORD_MS);
  };
  step();
}

/* The room's height: the measured space from its own top to the highest
   thing on the tab bar (the raised Live button stands 14px proud of it).
   While the keyboard is up, askKeyboard sizes it instead. */
function askRoomSize() {
  const el = document.getElementById("ask-room");
  if (!el || state.view !== "ask" || document.body.classList.contains("ask-typing")) return;
  const tab = document.querySelector(".tabbar");
  let bottom = window.innerHeight;
  if (tab && getComputedStyle(tab).display !== "none") {
    bottom = Math.min(tab.getBoundingClientRect().top,
      ...[...tab.querySelectorAll("*")].filter((x) => x.offsetParent !== null)
        .map((x) => x.getBoundingClientRect().top));
  }
  const top = el.getBoundingClientRect().top + window.scrollY;
  el.style.height = `${Math.max(300, Math.floor(bottom - top - 8))}px`;
  // Where the parlay slip's dock sits while the room is open: just above the composer.
  const dock = el.querySelector(".ask-dock");
  if (dock) {
    document.documentElement.style.setProperty("--ask-foot",
      `${Math.max(0, Math.round(window.innerHeight - dock.getBoundingClientRect().top))}px`);
  }
  // A conversation opens on its newest message; the empty room on its title.
  const log = document.getElementById("ask-log");
  if (log) log.scrollTop = el.classList.contains("is-empty") ? 0 : log.scrollHeight;
}

/* THE KEYBOARD. Ethan, 2026-09-23, a screenshot from his phone: "Fix how
   every time I click on the keyboard it makes the screen do this" — the
   box shoved up under the clock, a screen of nothing under it and the tab
   bar floating over the keys. An iPhone does not shrink the page for its
   keyboard: it scrolls the page to reach the box, and the fixed tab bar
   rides up with what is left of the view. The old sizing then measured
   the room from where the scroll had left it and made it taller still.

   So while the keyboard is up the room takes the part of the screen the
   keyboard leaves — the visual viewport, tracked through its own resize
   and scroll events — as a fixed layer over the page, the way a chat app
   does: the conversation above, the box sitting on the keys, the tab bar
   out of the way. When the keyboard goes, the room goes back into the
   page and is measured the ordinary way. */
function askKeyboard() {
  const vv = window.visualViewport;
  const room = document.getElementById("ask-room");
  const input = document.getElementById("ask-input");
  if (!room || state.view !== "ask") {
    document.body.classList.remove("ask-typing");
    return;
  }
  const up = !!vv && !!input && document.activeElement === input
    && window.innerHeight - vv.height > 120;
  const was = document.body.classList.contains("ask-typing");
  document.body.classList.toggle("ask-typing", up);
  if (up) {
    room.style.top = `${Math.round(vv.offsetTop)}px`;
    room.style.height = `${Math.floor(vv.height)}px`;
    const log = document.getElementById("ask-log");
    if (log && !was && !room.classList.contains("is-empty")) log.scrollTop = log.scrollHeight;
  } else if (was) {
    room.style.top = "";
    askRoomSize();
  }
}

window.addEventListener("resize", () => { if (state.view === "ask") { askKeyboard(); askRoomSize(); } });
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => { if (state.view === "ask") askKeyboard(); });
  window.visualViewport.addEventListener("scroll", () => { if (state.view === "ask") askKeyboard(); });
}

/* ETHAN'S RENDER, 2026-09-23: "Here is a render of what the Qellys chat
   room need[s] to look like." Its parts, top to bottom: an "AI" pill, the
   title with Qellys in gold, "Your AI betting assistant." and a line under
   it; a card with a robot that says what Ask is; three question cards with
   icons, side by side; and at the foot, across a hairline, the box with a
   paperclip, a divider and a gold send button with a paper plane. Once a
   conversation starts the title folds into one line above it.

   THE PAPERCLIP ATTACHES ONE OF TONIGHT'S PICKS — the same attachment a
   prop page's Ask button makes — so it is a working control and not a
   drawing of one. The render's second line still read "Questions about
   tonight's board"; it says what Ask does now. The footer line that must
   stay (not advice, 21+, the helpline) moved into the intro card, since
   the render has nothing under the box. */
const ASK_ICONS = {
  robot: `<path d="M12 3.2v2.6"/><circle cx="12" cy="2.4" r=".9" fill="currentColor" stroke="none"/>
    <rect x="4.6" y="6.4" width="14.8" height="12.2" rx="4"/><path d="M2.6 11.2v3.6M21.4 11.2v3.6"/>
    <circle cx="9.3" cy="11.7" r="1.25" fill="currentColor" stroke="none"/>
    <circle cx="14.7" cy="11.7" r="1.25" fill="currentColor" stroke="none"/><path d="M9.6 15.2c1.4.9 3.4.9 4.8 0"/>`,
  bars: `<rect x="4" y="13" width="4" height="7.5" rx="1" fill="currentColor" stroke="none"/>
    <rect x="10" y="8.6" width="4" height="11.9" rx="1" fill="currentColor" stroke="none"/>
    <rect x="16" y="3.6" width="4" height="16.9" rx="1" fill="currentColor" stroke="none"/>`,
  doc: `<rect x="5" y="3" width="14" height="18" rx="2.6"/><path d="M8.6 8h6.8M8.6 12h6.8M8.6 16h4.4"/>`,
  trend: `<path d="M3 17.2l6-6 4 4 8-8"/><path d="M15.2 7.2H21v5.8"/>`,
  clip: `<path d="M20.4 11.6l-8.1 8.1a5 5 0 01-7.1-7.1l8.4-8.4a3.3 3.3 0 014.7 4.7l-8.4 8.4a1.7 1.7 0 01-2.4-2.4l7.7-7.7"/>`,
  plane: `<path d="M21.6 2.4 2.7 9.9l7.4 3.2 3.2 7.4z" fill="currentColor" stroke="none"/>`,
};
function askIcon(name, size = 24) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor"
    stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${
    ASK_ICONS[name] || ""}</svg>`;
}
const ASK_SUGGEST_ICONS = ["bars", "doc", "trend"];

/* The picks the paperclip offers: tonight's props on the open league's
   board, likeliest first — the Over / Under page's own list. */
function askAttachable() {
  return propsRows(state.data).slice(0, 12).map((r) => ({
    id: propId(r),
    label: `${r.player || ""} ${r.side || ""} ${r.line ?? ""} ${r.market_label || ""}`.replace(/\s+/g, " ").trim(),
    pct: r.hit_prob == null ? "" : `${Math.round(Number(r.hit_prob) * 100)}%`,
  }));
}

/* Filled when the paperclip is tapped, not when the room is drawn: the room
   can be drawn before tonight's board has arrived. */
function askAttachHTML() {
  const picks = askAttachable();
  const bets = askOpenBets().length;
  const follows = askFollowCount();
  return `${bets ? `<button type="button" class="ask-attach-row ask-attach-bets" data-ask-bets><span>My open bets
      <small>How they stand, from the box score</small></span><b>${bets}</b></button>` : ""}${
    follows ? `<button type="button" class="ask-attach-row ask-attach-bets" data-ask-follows><span>My teams and players
      <small>The teams you follow and the players you watch</small></span><b>${follows}</b></button>` : ""}
    <label class="ask-attach-row"><span>Grade a parlay screenshot</span><b>Upload</b>
    <input type="file" accept="image/*" class="ask-sr" data-ask-slip></label>
    <div class="ask-attach-h">Ask about one of tonight’s picks</div>${picks.length
    ? picks.map((p) => `<button type="button" class="ask-attach-row" data-ask-attach="${escapeAttr(p.id)}"
        data-ask-label="${escapeAttr(p.label)}"><span>${escapeHtml(p.label)}</span>${
        p.pct ? `<b>${escapeHtml(p.pct)}</b>` : ""}</button>`).join("")
    : `<p class="ask-attach-none">Nothing on tonight’s board to attach yet.</p>`}`;
}

/* GATED BEFORE TYPING (audit V-20). With the paywall on, a signed-out
   reader could write a whole question and only then meet the 401. The
   composer is replaced, up front, by what it takes to ask — and the one
   line saying what is free. The server still refuses on its own. */
function askLocked() {
  return !!(_pwStatus && _pwStatus.paywall && !_pwStatus.entitled);
}

function askLockedHTML() {
  const signedIn = !!(_pwStatus && _pwStatus.signed_in);
  return `<div class="ask-locked">
    <p><b>Ask is part of the plan.</b> ${signedIn ? "Your account is signed in without one."
      : "Sign in with a subscription to ask."}</p>
    ${freeVsPlanHTML("ask")}
    <div class="ask-locked-acts">
      <a class="btn primary" href="#paywall" data-view="paywall">See the plans</a>
      ${signedIn ? "" : `<a class="btn ghost" href="#account" data-view="account">Log in</a>`}
    </div>
  </div>`;
}

/* THE FIRST CARD IS TONIGHT'S GAME (2026-10-27): the next game on the
   league's board that has not finished, in the teams' own names ("Who has
   the edge in Bills at Chiefs?"), so the room opens on a question about
   tonight rather than a sample. No game, the three as drawn. */
function askSuggest() {
  const done = (g) => /post|final/i.test(String(((g || {}).live || {}).state || ""));
  const g = ((state.data || {}).games || []).find((x) => x && x.away && x.home && !done(x));
  if (!g) return ASK_SUGGEST;
  const nick = (abbr) => (typeof team === "function" && team(abbr).nick) || abbr;
  return [`Who has the edge in ${nick(g.away)} at ${nick(g.home)}?`, ASK_SUGGEST[0], ASK_SUGGEST[2]];
}

function renderAsk() {
  const host = document.getElementById("ask-body");
  if (!host) return;
  const a = askState();
  const empty = !a.turns.length;
  const sug = a.bets ? ASK_SUGGEST_BETS : a.follows ? ASK_SUGGEST_FOLLOWS : a.pick ? ASK_SUGGEST_PICK : askSuggest();
  const title = `<span class="ask-pill">AI</span>`;
  const mood = a.busy ? "thinking" : _askTyping ? "talking" : "idle";
  // The newest answer's robot is the one that reacts; older ones hold still.
  const lastBot = a.turns.map((t) => t.role !== "user").lastIndexOf(true);
  host.innerHTML = `<div class="ask-room${empty ? " is-empty" : ""}" id="ask-room" data-bot="${mood}">
    ${empty ? "" : `<div class="ask-head">${qbotHTML("head", "ask-head-bot")}${title}
      <b class="ask-title-sm">Ask <em>Qellys</em></b>
      <button type="button" class="ask-new" data-ask-reset>New chat</button>
    </div>`}
    <div class="ask-log" id="ask-log" aria-live="polite">${empty ? `
      <div class="ask-empty"><div class="ask-hero"><div class="ask-hero-words">${title}
        <h2 class="ask-title">Ask <em>Qellys</em></h2>
        <p class="ask-sub"><span>Your AI betting assistant.</span>
          <span>Any team, any player, any sport, answered from our numbers.</span></p></div>
        ${qbotHTML("body", "ask-hero-bot live")}</div>
        <div class="ask-intro"><span class="ask-intro-ic">${askIcon("robot", 34)}</span>
          <div><b>Ask about any team, player or game.</b>
            <p>Tonight’s boards in every sport and every past game we have stored — the answer
              comes from our own numbers and says so when they have nothing on it.</p>
            <p>Fantasy too: who to start, projected points, waiver pickups and the matchups to target.</p>
            <p class="ask-fine">Not betting advice. <span class="ask-help">21+ · 1-800-GAMBLER</span></p></div></div>
        <div class="ask-suggest">${sug.map((s, n) =>
          `<button type="button" class="ask-sug" data-ask-q="${escapeAttr(s)}"><span class="ask-sug-ic">${
            askIcon(ASK_SUGGEST_ICONS[n % ASK_SUGGEST_ICONS.length], 26)}</span><span>${escapeHtml(s)}</span></button>`).join("")}</div>
      </div>` : a.turns.map((t, i) => askTurnHTML(t, i === lastBot && !a.busy)).join("")}${a.busy ? `
      <div class="ask-row bot">${askAva(true)}<div class="ask-turn bot wait"><span class="ask-dots"
        aria-hidden="true"><i></i><i></i><i></i></span><span class="ask-sr">Looking it up…</span>${askStepsHTML()}</div></div>` : ""}</div>
    <div class="ask-dock">
      ${a.pick ? `<div class="ask-focus"><span>About <b>${escapeHtml(a.pickLabel || a.pick)}</b></span>
        <button type="button" class="ask-x" data-ask-clear-pick aria-label="Stop asking about this pick">&#215;</button></div>` : ""}
      ${a.bets ? `<div class="ask-focus"><span>About <b>your ${askOpenBets().length} open bet${
        askOpenBets().length === 1 ? "" : "s"}</b></span>
        <button type="button" class="ask-x" data-ask-clear-bets aria-label="Stop asking about your bets">&#215;</button></div>` : ""}
      ${a.follows ? `<div class="ask-focus"><span>About <b>your teams and players</b></span>
        <button type="button" class="ask-x" data-ask-clear-follows aria-label="Stop asking about your teams">&#215;</button></div>` : ""}
      <div class="ask-attach" id="ask-attach" role="dialog" aria-label="Attach a pick" hidden></div>
      ${askLocked() ? askLockedHTML() : `<form class="ask-form" id="ask-form">
        <button type="button" class="ask-clip" data-ask-clip aria-label="Attach a pick or a parlay screenshot"
          aria-controls="ask-attach" aria-expanded="false">${askIcon("clip", 22)}</button>
        <textarea id="ask-input" rows="1" maxlength="400" placeholder="Ask about a player, game or bet"
          aria-label="Your question"${a.busy ? " disabled" : ""}></textarea>
        <button class="ask-send" type="submit" aria-label="Send" disabled>${askIcon("plane", 22)}</button>
      </form>`}
    </div>
  </div>`;
  const form = host.querySelector("#ask-form");
  const input = host.querySelector("#ask-input");
  const send = host.querySelector(".ask-send");
  if (form) form.addEventListener("submit", (e) => { e.preventDefault(); askSend(input ? input.value : ""); });
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askSend(input.value); }
    });
    // The keyboard takes a moment to arrive and to leave; ask again once it has.
    input.addEventListener("focus", () => { askKeyboard(); setTimeout(askKeyboard, 350); });
    input.addEventListener("blur", () => setTimeout(askKeyboard, 120));
    // The box grows with what is typed, to five lines, and Send wakes up —
    // and the robot looks down at what you are writing.
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
      if (send) send.disabled = a.busy || !input.value.trim();
      if (!a.busy && !_askTyping) askBotState(input.value.trim() ? "listening" : "idle");
    });
    input.addEventListener("blur", () => {
      const room = document.getElementById("ask-room");
      if (room && room.dataset.bot === "listening") room.dataset.bot = "idle";
    });
  }
  const clip = host.querySelector("[data-ask-clip]");
  const sheet = host.querySelector("#ask-attach");
  const attachOpen = (open) => {
    if (!sheet || !clip) return;
    if (open) {
      sheet.innerHTML = askAttachHTML();
      sheet.querySelectorAll("[data-ask-slip]").forEach((f) => f.addEventListener("change", () => {
        attachOpen(false);
        if (f.files && f.files[0]) askSlipSend(f.files[0]);
      }));
      sheet.querySelectorAll("[data-ask-attach]").forEach((b) => b.addEventListener("click", () => {
        a.pick = b.dataset.askAttach || "";
        a.pickLabel = b.dataset.askLabel || "";
        a.bets = false;
        askSave(); renderAsk();
      }));
      sheet.querySelectorAll("[data-ask-bets]").forEach((b) => b.addEventListener("click", () => {
        a.bets = true;                 // this visit only: never written to storage
        a.follows = false; a.pick = ""; a.pickLabel = "";
        askSave(); renderAsk();
      }));
      sheet.querySelectorAll("[data-ask-follows]").forEach((b) => b.addEventListener("click", () => {
        a.follows = true;              // this visit only, like the bets
        a.bets = false; a.pick = ""; a.pickLabel = "";
        askSave(); renderAsk();
      }));
    }
    sheet.hidden = !open;
    clip.setAttribute("aria-expanded", open ? "true" : "false");
  };
  if (clip) clip.addEventListener("click", (e) => { e.stopPropagation(); attachOpen(sheet.hidden); });
  askKeyboard();                       // a redraw mid-typing keeps the room above the keys, or lets it go
  askRoomSize();
  setTimeout(askRoomSize, 400);        // again once the view's slide-in has settled
  askTypeOut();
  host.querySelectorAll("[data-ask-q]").forEach((b) => b.addEventListener("click", () => askSend(b.dataset.askQ)));
  host.querySelectorAll("[data-ask-reset]").forEach((b) => b.addEventListener("click", () => {
    a.turns = []; askSave(); renderAsk();
  }));
  host.querySelectorAll("[data-ask-clear-pick]").forEach((b) => b.addEventListener("click", () => {
    a.pick = ""; a.pickLabel = ""; askSave(); renderAsk();
  }));
  host.querySelectorAll("[data-ask-clear-bets]").forEach((b) => b.addEventListener("click", () => {
    a.bets = false; renderAsk();
  }));
  host.querySelectorAll("[data-ask-clear-follows]").forEach((b) => b.addEventListener("click", () => {
    a.follows = false; renderAsk();
  }));
  // A door elsewhere (a player's card) sent a question: it waits in the box,
  // ready to send or to change.
  if (input && typeof _askDraft !== "undefined" && _askDraft && !a.busy) {
    input.value = _askDraft;
    _askDraft = "";
    input.dispatchEvent(new Event("input"));
    if (window.matchMedia && matchMedia("(pointer: fine)").matches) input.focus();
  }
}

/* The attach list closes on a tap anywhere else, or Escape. */
document.addEventListener("click", (e) => {
  const sheet = document.getElementById("ask-attach");
  if (!sheet || sheet.hidden || sheet.contains(e.target)) return;
  sheet.hidden = true;
  const clip = document.querySelector("[data-ask-clip]");
  if (clip) clip.setAttribute("aria-expanded", "false");
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const sheet = document.getElementById("ask-attach");
  if (sheet && !sheet.hidden) {
    sheet.hidden = true;
    const clip = document.querySelector("[data-ask-clip]");
    if (clip) { clip.setAttribute("aria-expanded", "false"); clip.focus(); }
  }
});

async function askSend(text) {
  const a = askState();
  const question = String(text || "").trim().slice(0, 400);
  const meta = SPORT_META[state.sport];
  if (!question || a.busy || !meta) return;
  // An answer goes back with the server's tag on it; one without (an old
  // saved conversation) is dropped as context by the server (audit C-3).
  const history = a.turns.filter((t) => !t.error).slice(-6)
    .map((t) => (t.sig ? { role: t.role, text: t.text, sig: t.sig } : { role: t.role, text: t.text }));
  a.turns.push({ role: "user", text: question });
  a.busy = true;
  _askSteps = [];
  track("ask", state.sport);
  renderAsk();
  const asked = Date.now();
  let turn = null;
  try {
    const res = await fetch("/api/ask", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board: boardNameFor(meta), question, history, pick: a.pick, stream: ASK_STREAMS,
                             bets: a.bets ? askOpenBets() : undefined, follows: a.follows ? askFollows() : undefined }),
    });
    let body = {};
    if (res.ok && /event-stream/.test(res.headers.get("Content-Type") || "")) {
      const end = await askReadStream(res);
      body = end.kind === "answer" ? end.data : { error: true, ...(end.data || {}) };
      if (end.kind !== "answer") {
        turn = { role: "assistant", text: askErrorText((end.data || {}).status || 0, end.data), error: true };
      }
    } else {
      try { body = await res.json(); } catch (e) { body = {}; }
      if (!res.ok) turn = { role: "assistant", text: askErrorText(res.status, body), error: true };
    }
    if (!turn) {
      turn = body.text ? { role: "assistant", text: body.text, sources: body.sources || [], sig: body.sig || "",
                           cards: body.cards || [], follow: body.follow || [] }
        : { role: "assistant", text: askErrorText(0, null), error: true };
    }
  } catch (e) {
    turn = { role: "assistant", text: askErrorText(0, null), error: true };
  }
  const beat = ASK_THINK_MS - (Date.now() - asked);
  if (beat > 0) await new Promise((r) => setTimeout(r, beat));
  if (!turn.error) _askTyping = turn;
  _askSteps = [];
  a.turns.push(turn);
  a.busy = false;
  askSave();
  if (state.view === "ask") renderAsk();
}

/* THE STEPS, AS THEY HAPPEN (2026-10-27; Ethan: "look at other apps that
   use AI betting ... and do it better"). Every assistant we looked at
   shows a spinner and then an answer. This one says what it is reading
   while it reads it: the server streams each lookup as it starts
   (server.py _ask_stream, engine/askcards.step_label), and the waiting
   bubble lists them, the newest one turning. A browser that cannot read a
   stream asks the old way and gets the same answer. */
const ASK_STREAMS = typeof ReadableStream !== "undefined" && typeof TextDecoder !== "undefined";
let _askSteps = [];

async function askReadStream(res) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", end = { kind: "fail", data: { status: 0 } };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      const kind = (/^event: (.*)$/m.exec(chunk) || [])[1];
      const raw = (/^data: (.*)$/m.exec(chunk) || [])[1];
      let data = null;
      try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
      if (kind === "step" && data && data.label) {
        _askSteps.push(String(data.label));
        askStepsPaint();
      } else if (kind === "answer" || kind === "fail") {
        end = { kind, data: data || {} };
      }
    }
  }
  return end;
}

function askStepsHTML() {
  if (!_askSteps.length) return "";
  return `<ol class="ask-steps">${_askSteps.map((s, i) => `<li class="${i === _askSteps.length - 1 ? "now" : "done"}">${
    escapeHtml(s)}</li>`).join("")}</ol>`;
}

/* Only the waiting bubble redraws: the conversation above it holds still. */
function askStepsPaint() {
  const wait = document.querySelector(".ask-turn.bot.wait");
  if (!wait) return;
  let box = wait.querySelector(".ask-steps");
  const html = askStepsHTML();
  if (box) box.outerHTML = html;
  else wait.insertAdjacentHTML("beforeend", html);
  const log = document.getElementById("ask-log");
  if (log) log.scrollTop = log.scrollHeight;
}
