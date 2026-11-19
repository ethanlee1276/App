/* Qellys Book — the game report, drawn on the game page.
   ==========================================================================
   Ethan, 2026-10-19: "I want a full layed out detailed explanation for
   every nfl game just like how the report is. Obv keep out the prop picks
   but everything else it valuable information too have typed out so the
   user can just read it."

   engine/gamereport writes the report from what the board holds and this
   draws it block by block: paragraphs, headings, lists, tables, notes, and
   the players in the scan's own card shape. Each player opens his player
   page. Since 2026-11-14 the report also carries each game's parlays
   (engine/gameparlays; Ethan: "for each game ... make 4 3-leg parlays ...
   and 3 2-leg touchdown parlays"), the one place it names a price: every
   leg is a pick the board already posts, and the ticket says the price to
   take it at.

   LOADED ON FIRST USE (app.js loadReport), like js/extras.js and
   js/slip.js: the first game page with a report asks for it, so the
   site's first paint carries none of it. It runs in the page's global
   scope beside app.js and uses its helpers (escapeHtml, escapeAttr,
   slugify, teamName, playerAvatar) by name, only when drawing. */
(function () {
  "use strict";

  const TONE = { favorable: "up", unfavorable: "down", up: "up", down: "down" };

  /* WHO GETS THE BALL, IN COLOUR (Ethan, 2026-11-15, circling DET's "who
     gets the ball" line: "we can make the letters of there name green or
     red depending on in they are a breakout or favorite candidate or a
     unfavorable matchup"), AND THEN THE WHOLE REPORT ("Make the game report
     less confusing too I liked the names colored it made it easier to
     read"). A block's `names` (engine/gamereport.color_names) says each
     named player's matchup read: his name is green for a breakout
     candidate or a favorable matchup, red for an unfavorable one, plain for
     a neutral one, the same in every section, and every one opens the
     player's page. Its `marks` colour the injury words (out and doubtful
     red, questionable amber); a line's lead-in ("Who gets the targets:",
     "Kickoff:") is bold, so its subject stands out; and a rank is green in
     the league's top third and red in its bottom third, in a table and in a
     sentence alike (Ethan, 2026-11-15, "(3rd in the league)" and "(28th)"
     circled: "if it's good, then green, if it's bad, then red"). */
  const isWordChar = (ch) => !!ch && /[\p{L}\p{N}]/u.test(ch);
  const MARK = { down: "down", warn: "warn", up: "up" };
  function nameTag(name, v, inner) {
    const tone = TONE[(v || {}).tone] || "";
    const label = String((v || {}).label || "");
    return `<span class="gr-name${tone ? ` ${tone}` : ""}" data-open="player:${escapeAttr(slugify(name))}"${
      label ? ` title="${escapeAttr(label)}"` : ""}>${inner}${tone && label
      ? `<span class="gr-sr"> (${escapeHtml(label.toLowerCase())})</span>` : ""}</span>`;
  }
  /* The league's size for the report being drawn (engine/gamereport
     "rank_of"): a rank in a sentence is judged against it. */
  let RANK_OF = 0;
  /* A FINISHED GAME'S RESULTS (app.js pickResult, engine/gameresults;
     Ethan, 2026-11-16: "show ... if these props won or lost and if the
     parlays won or lost and what legs won and lost and if our game report
     and reads was correct"): the game page hands the report its grader
     once the game is over ({final, home, away, grade, words, ticket}), and
     every pick, read pick, parlay leg and ticket, and the call, says how it
     went. Null before the final, and on a page that grades nothing. */
  let RESULTS = null;
  /* A GAME UNDER WAY OR OVER (engine/reportkeep: its report and tickets kept
     from before the start, `kept`): its tickets are still drawn, each saying
     how it went, but there is nothing left to bet, so no "Bet it". */
  let CLOSED = false;
  const RES_TAG = { won: "gr-res won", lost: "gr-res lost", push: "gr-res even", void: "gr-res even",
                    pending: "gr-res even" };
  function resTag(bet) {
    if (!RESULTS || !bet || typeof RESULTS.grade !== "function") return "";
    const x = RESULTS.grade(bet);
    if (!x) return "";
    const words = typeof RESULTS.words === "function" ? RESULTS.words(x, bet) : x.status;
    return ` <span class="${RES_TAG[x.status] || RES_TAG.pending}">${escapeHtml(words)}</span>`;
  }
  //: A go-to scorer's touchdown on a finished game, once the record has graded
  //: one on him ("Scored", "Didn't score"); nothing before, and nothing when
  //: the record has none.
  function scorerTag(bet) {
    const x = RESULTS && bet && typeof RESULTS.grade === "function" ? RESULTS.grade(bet) : null;
    if (!x || !["won", "lost", "void"].includes(x.status)) return "";
    const words = x.status === "void" ? "Didn’t play" : x.status === "won"
      ? `Scored${Number(x.actual) > 1 ? ` ${Number(x.actual)}` : ""}` : "Didn’t score";
    return ` <span class="${RES_TAG[x.status]}">${escapeHtml(words)}</span>`;
  }
  /* WAS THE READ RIGHT (engine/reportgrade, 2026-11-16; Ethan: "we should
     report on if they actually did good or not, and if we were correct in our
     game report"). A finished game's report carries each read's grade: a
     player's number in the stat his read leans on against his own average, a
     team's against its own; right in green, wrong in red, the rest plain. */
  function gradeLine(gr) {
    if (!gr || !gr.words) return "";
    // A touchdown chance that scored reads as a hit (engine/reportfacts): a
    // chance is never right or wrong, but a reader wants the hit in green.
    const cls = gr.status === "right" || gr.status === "hit" ? "gr-graded won"
      : gr.status === "wrong" ? "gr-graded lost" : "gr-graded";
    return `<span class="${cls}">${escapeHtml(gr.words)}</span>`;
  }
  /* THE LINES AGAINST THE FINAL (engine/reportfacts.score_check, 2026-11-16;
     Ethan: "see if the data we were giving them were correct or not"): what
     the spread and the total said, what happened, who covered, which side of
     the total. Off the call's own `expect`, read before the game. */
  function winnerLinesHTML(b) {
    const f = RESULTS && RESULTS.final, e = b && b.expect;
    if (!f || f.home == null || f.away == null || !e) return "";
    const sp = Number(e.spread), tot = Number(e.total), home = RESULTS.home, away = RESULTS.away;
    const h = Number(f.home), a = Number(f.away), bits = [], after = [];
    if (e.spread != null && Number.isFinite(sp) && sp !== 0) {
      const fav = sp < 0 ? home : away, dog = fav === home ? away : home, line = Math.abs(sp);
      const fm = fav === home ? h - a : a - h;
      bits.push(`${teamName(fav)} ${e.fixed ? `−${line}` : `by ${line}`}`);
      after.push(fm > line ? `${teamName(fav)} covered` : fm === line ? "a push on the spread"
        : `${teamName(dog)} covered${fm < 0 ? " and won outright" : ""}`);
    }
    if (e.total != null && Number.isFinite(tot)) {
      bits.push(`total ${tot}`);
      after.push(h + a > tot ? "it went over" : h + a < tot ? "it went under" : "a push on the total");
    }
    if (!bits.length) return "";
    return `<div class="gr-res-lines">The lines: ${escapeHtml(bits.join(", "))} — ${escapeHtml(after.join("; "))}</div>`;
  }
  //: A ticket's verdict from its legs (app.js ticketResult): every leg that played won, or one lost.
  function ticketTag(legs) {
    if (!RESULTS || typeof RESULTS.ticket !== "function") return "";
    const bets = (legs || []).map((l) => l.bet || l);
    const x = bets.length && bets.every(Boolean) ? RESULTS.ticket(bets) : null;
    if (!x) return "";
    const won = (x.legs || []).filter((y) => y.status === "won").length;
    const words = { won: "Ticket won", lost: `Ticket lost · ${won} of ${bets.length} legs hit`, push: "Ticket void",
                    pending: "Final — waiting on the box score" }[x.status] || "";
    return words ? ` <span class="${RES_TAG[x.status] || RES_TAG.pending}">${escapeHtml(words)}</span>` : "";
  }
  const resNormR = (s) => String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
  //: The same fighter, as two feeds spell him: accents, case, a "Jr." and
  //: the order of his names aside, else the same surname and initial.
  function sameFighter(x, y) {
    const w = (s) => String(s || "").split(/\s+/).map(resNormR).filter((t) => t && !/^(jr|sr|ii|iii|iv)$/.test(t));
    const a = w(x), b = w(y);
    if (!a.length || !b.length) return false;
    if (a.join("") === b.join("") || [...a].sort().join(" ") === [...b].sort().join(" ")) return true;
    return a[a.length - 1] === b[b.length - 1] && a[0][0] === b[0][0];
  }
  //: Under the call on a finished game: right or wrong, with the score, and our ratings' own.
  function winnerResultHTML(b) {
    // A UFC fight (more.js ufcOutcome): right or wrong by who won, or no
    // winner; nothing when the winner is neither name the call says.
    if (RESULTS && RESULTS.ufc) {
      if (!RESULTS.winner) return `<div class="gr-res-call">${escapeHtml(RESULTS.how || "No winner")}</div>`;
      const mine = sameFighter(RESULTS.winner, b.team), theirs = sameFighter(RESULTS.winner, b.other);
      if (mine === theirs) return "";
      return `<div class="${mine ? "gr-res-call won" : "gr-res-call lost"}">${mine ? "Right" : "Wrong"}: ${
        escapeHtml(RESULTS.how || `${RESULTS.winner} won`)}</div>`;
    }
    const f = RESULTS && RESULTS.final;
    if (!f || f.home == null || f.away == null) return "";
    const score = `${teamName(RESULTS.away)} ${f.away}, ${teamName(RESULTS.home)} ${f.home}`;
    if (f.home === f.away) return `<div class="gr-res-call even">Final: ${escapeHtml(score)} — a tie</div>`;
    const won = f.home > f.away ? RESULTS.home : RESULTS.away;
    const right = won === b.team;
    const r = b.ratings;
    const ratings = r && !r.even ? ` · our ratings alone: ${r.team === won ? "right" : "wrong"}` : "";
    return `<div class="${right ? "gr-res-call won" : "gr-res-call lost"}">${right ? "Right" : "Wrong"}: ${
      escapeHtml(teamName(won))} won — ${escapeHtml(score)}${escapeHtml(ratings)}</div>`;
  }
  /* Green in the top third of a league of n, red in the bottom third. */
  function rankTone(r, n) {
    if (!(r > 0) || !(n > 0)) return "";
    const q = Math.ceil(n / 3);
    return r <= q ? "up" : r > n - q ? "down" : "";
  }
  /* THE RANKS IN A SENTENCE, where 1st is the best: "(4th)", "(3rd in the
     league)", "(12th in the country)", "(30th in the league; 13th this
     season alone)", "(24th, allowing 3.4 a carry)", "(13th of 49 running
     backs)", "ranks 22nd", "the league's 5th-ranked pass rush", and "the
     third-worst", "the best rate". A rank with no good or bad side of its
     own ("8th-most plays", "the 11th-fewest shots", "the third-highest
     total") is left plain. */
  const RANK_RE = "\\(\\d+(?:st|nd|rd|th)(?=(?: in the (?:league|country))?[);]|,| of \\d)"
    + "|ranks \\d+(?:st|nd|rd|th)\\b"
    + "|\\d+(?:st|nd|rd|th)(?= this season alone\\b|-ranked\\b)"
    + "|(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|\\d+(?:st|nd|rd|th))-(?:best|worst)\\b"
    + "|the (?:best|worst)(?= rate| in the)";
  function rankPaint(m, rest) {
    if (/(best|worst)$/.test(m)) {
      return m.replace(/(?:[a-z0-9]+-)?(?:best|worst)$/, (w) => `<span class="gr-rank ${/best/.test(w) ? "up" : "down"}">${w}</span>`);
    }
    const k = /(\d+)(?:st|nd|rd|th)/.exec(m);
    const tone = rankTone(Number(k[1]), Number((/^ of (\d+)/.exec(rest) || [])[1]) || RANK_OF);
    return tone ? m.replace(k[0], `<span class="gr-rank ${tone}">${k[0]}</span>`) : m;
  }
  /* THE OTHER NUMBERS WITH A GOOD AND A BAD SIDE, each for the team or
     player its sentence is about: what a defense gives up ("gives up the
     second-most points" red, "allows the sixth-fewest" green — the near
     third of the league only, as a rank), a result ("W 23-13" green, "L
     21-45" red), a goalie's form ("has stopped 4.2 more goals than expected"
     green, "has let in 3.4" red), a lineup against tonight's hand ("5%
     better than its average" green), and rest ("the rest edge" green, "the
     second night of a back-to-back" and a bullpen that "is tired" red). No
     capture groups: the painter reads the match's offset off its arguments. */
  const ORD = "(?:second|third|fourth|fifth|sixth|seventh|eighth|ninth|\\d+(?:st|nd|rd|th))";
  const GOOD_RE = `(?:gives? up|allows?|allowed|gave up) the (?:${ORD}-)?(?:most|fewest)\\b`
    + "|[WL] \\d+-\\d+"
    + "|(?:stopped|let in) \\d+(?:\\.\\d+)? more goals? than expected"
    + "|\\d+% (?:better|worse) than its average"
    + "|the rest edge|the second night of a back-to-back|is tired";
  const GOOD_ONE = new RegExp(`^(?:${GOOD_RE})$`);
  const WORD_ORD = { second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9 };
  function goodPaint(m) {
    const give = /^(.* the )((?:([a-z0-9]+)-)?(most|fewest))$/.exec(m);
    if (give) {
      const n = give[3] ? WORD_ORD[give[3]] || parseInt(give[3], 10) : 1;
      const q = RANK_OF > 0 ? Math.ceil(RANK_OF / 3) : 0;
      if (!(n > 0) || n > q) return m;
      return `${give[1]}<span class="gr-rank ${give[4] === "most" ? "down" : "up"}">${give[2]}</span>`;
    }
    const up = /^(?:W |stopped |\d+% better|the rest edge)/.test(m);
    return `<span class="gr-mark ${up ? "up" : "down"}">${m}</span>`;
  }
  /* Text with its named players, marked words and ranks drawn: one pass,
     longest first, so a name inside a longer one is left alone, and only
     where it stands whole. A table's cell passes ranks false: its table
     says its own league size (`rankCell`), or its ranks have no good side. */
  function painted(text, names, marks, ranks = true) {
    const out = escapeHtml(text);
    const by = new Map();
    Object.keys(names || {}).filter(Boolean).forEach((k) => by.set(escapeHtml(k), ["name", k]));
    Object.keys(marks || {}).filter((k) => k && MARK[marks[k]]).forEach((k) => {
      if (!by.has(escapeHtml(k))) by.set(escapeHtml(k), ["mark", k]);
    });
    const keys = [...by.keys()].sort((x, y) => y.length - x.length);
    const alts = keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).concat(ranks ? [RANK_RE, GOOD_RE] : []);
    if (!alts.length) return out;
    const re = new RegExp(alts.join("|"), "g");
    return out.replace(re, (m, at, str) => {
      if (isWordChar(str[at - 1]) || isWordChar(str[at + m.length])) return m;
      const hit = by.get(m);
      if (!hit) return GOOD_ONE.test(m) ? goodPaint(m) : rankPaint(m, str.slice(at + m.length));
      const [kind, k] = hit;
      return kind === "name" ? nameTag(k, names[k], m) : `<span class="gr-mark ${MARK[marks[k]]}">${m}</span>`;
    });
  }
  /* A line's lead-in, up to its first colon, in bold: "Who gets the
     targets:", "Kickoff:", "Script A, DET controls it (17% of …):",
     "Amon-Ra St. Brown (WR):". Only a short one with no sentence inside it
     (a sentence ends on a word or a number, not on "St." or "D.J."). */
  function named(text, names, marks, lead, ranks = true) {
    const t = String(text == null ? "" : text);
    const m = lead ? /^([^:]{2,60}?):\s/.exec(t) : null;
    if (!m || /(?:[a-z]{3,}|\d)[.!?]\s/.test(m[1])) return painted(t, names, marks, ranks);
    const head = t.slice(0, m[1].length + 1);
    return `<b class="gr-lead">${painted(head, names, marks, ranks)}</b>${painted(t.slice(head.length), names, marks, ranks)}`;
  }
  /* A rank in a table ("+0.19 · 4th", "3.60 (3rd)") in its colour: the
     top third of the league green, the bottom third red (`rankTone`). */
  /* OUR RATINGS ALONE, ON THE CALL (Ethan, 2026-11-16, asked whether to show
     our own ratings' pick beside the call anyway: "Yes"). Shown, never
     followed: tagged unproven, and the call's own list says why
     (engine/gamereport.ratings_why). */
  function winnerRatingsHTML(r, pct) {
    if (!r || r.chance == null) return "";
    const p = Math.max(0, Math.min(1, Number(r.chance) || 0));
    const what = r.even ? "an even game" : `<b>${escapeHtml(r.name || teamName(r.team))}</b> ${pct(p)}`;
    return `<div class="gr-winner-alt"><span>Our ratings alone: ${what}${r.same === false ? ", the other side" : ""}</span>`
      + `<span class="gr-winner-tag">Unproven</span></div>`;
  }
  function rankCell(cell, of) {
    const t = String(cell == null ? "" : cell);
    const m = /^(.*?)( · |\s\()(\d+)(st|nd|rd|th)(\)?)$/.exec(t);
    const n = Number(of) || 0;
    if (!m || !n) return null;
    const tone = rankTone(Number(m[3]), n);
    return `${escapeHtml(m[1] + m[2])}${tone ? `<span class="gr-rank ${tone}">` : ""}${escapeHtml(m[3] + m[4])}${
      tone ? "</span>" : ""}${escapeHtml(m[5])}`;
  }
  /* The key, once, at the top of a report that colours anything: read off
     the drawn sections, so it names only the colours a reader will see. */
  function colourKey(body) {
    const has = (cls, tones) => new RegExp(`class="${cls} (?:${tones})"`).test(body);
    const names = has("gr-name", "up|down");
    const ranks = has("gr-rank", "up|down");
    const words = has("gr-mark", "up|down");
    const amber = has("gr-mark", "warn");
    if (!names && !ranks && !words && !amber) return "";
    const bits = [];
    if (names || ranks || words) {
      bits.push(`<span class="gr-name up">Green</span> is good for the team or player it’s about and
        <span class="gr-name down">red</span> is bad, so a red number on a defense is good news for the
        offense facing it.`);
    }
    if (names) {
      bits.push(`<span class="gr-name up">Green names</span> are a breakout candidate or a favorable matchup,
        <span class="gr-name down">red names</span> an unfavorable one; tap a name for the player’s page.`);
    }
    if (ranks) {
      bits.push(`A <span class="gr-rank up">green rank</span> is in the league’s top third, a
        <span class="gr-rank down">red rank</span> in its bottom third (1st is the best).`);
    }
    if (amber) bits.push(`<span class="gr-mark warn">Amber</span> is a player listed as questionable.`);
    return `<p class="gr-key"><b class="gr-lead">Reading the colors:</b> ${bits.join(" ")}</p>`;
  }

  /* What a league's report holds, for the reader without the paid key
     (engine/gamereport, engine/leaguereport). */
  const HOOPS = "the line and what it means, rest and travel, who carries each team, where each " +
    "defense gives, the injury report and what to check before tip-off";
  const HOLDS = {
    nfl: "the line and what it means, how the units rank, how each team plays, who is out and what it " +
      "opens, who’s guarding who, the trenches, the red zone, coaching and the schedule, how the game " +
      "could go and the players to watch",
    mlb: "the line and what it means, the pitching matchup, how each lineup hits tonight’s hand, the pens, " +
      "the park, the weather and the umpire, and the hitters set up to shine or struggle",
    nhl: "the line and what it means, the tale of the tape, the goalies, the injury report, and the " +
      "skaters set up to shine or struggle",
    nba: HOOPS, wnba: HOOPS, cbb: HOOPS,
  };
  HOLDS.cfb = HOLDS.nfl;

  /* His season, his last games, a trend and his red-zone work
     (engine/gamereport.form_lines): [[label, [lines]]]. */
  function form(rows) {
    if (!(rows || []).length) return "";
    return `<dl class="gr-form">${rows.map(([k, lines]) => `<div class="gr-form-row"><dt>${escapeHtml(k)}</dt>
      <dd>${(lines || []).map((l) => `<span>${escapeHtml(l)}</span>`).join("")}</dd></div>`).join("")}</dl>`;
  }

  /* The sections that read open — our picks for the game (the research's
     card, engine/gamereport.sec_card) and the short version; the rest fold
     to their titles. */
  // How the report did, on a finished game (engine/reportgrade), reads first.
  const OPEN_SECTIONS = ["graded", "card", "short"];

  /* A rank as a bar's length: 1st the longest, last the shortest. */
  function rankWidth(rank, n) {
    const r = Number(rank), of = Number(n);
    if (!(r > 0) || !(of > 0)) return 0;
    return Math.max(4, Math.round(((of - r + 1) / of) * 100));
  }
  /* EACH OFFENSE AGAINST THE DEFENSE IT FACES, unit by unit (engine/
     gamereport._edge_chart): two bars a row, the longer the better, in
     the rank's own colour — and the edge, where the ranks sit far apart. */
  function matchbars(b) {
    const n = Number(b.rank_of) || RANK_OF;
    const bar = (rank, who) => {
      const tone = rankTone(Number(rank), n);
      return `<div class="gr-bar${tone ? ` ${tone}` : ""}"><span class="gr-bar-fill" style="--w:${rankWidth(rank, n)}%"></span>
        <span class="gr-bar-txt">${escapeHtml(who)} <b>${escapeHtml(ordinal(rank))}</b></span></div>`;
    };
    return `<div class="gr-chart gr-match">${(b.sides || []).map((sd) => `<div class="gr-match-side">
      <div class="gr-chart-head">${escapeHtml(teamName(sd.off))} offense <span>vs ${escapeHtml(teamName(sd.def))} defense</span></div>
      ${(sd.rows || []).map((row) => `<div class="gr-match-row">
        <div class="gr-match-label">${escapeHtml(row.label)}${row.edge
          ? ` <span class="gr-edge">edge ${escapeHtml(row.edge)}</span>` : ""}</div>
        ${bar(row.off, sd.off)}${bar(row.def, sd.def)}</div>`).join("")}</div>`).join("")}
      ${b.note ? `<p class="gr-note">${escapeHtml(b.note)}</p>` : ""}</div>`;
  }
  function ordinal(n) {
    const k = Math.abs(Number(n)) % 100;
    const suf = k >= 11 && k <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[k % 10] || "th");
    return `${n}${suf}`;
  }

  /* ONE SLIP FOR THE WHOLE TICKET (engine/socialfeed.combine_links, the
     feed's tail, here for the page): every leg's link at the same address,
     each carrying its selection as `name[0]=value` keys (FanDuel's
     `marketId[0]` / `selectionId[0]`), renumbered [0], [1], [2] and joined.
     Any other shape — another path, an unindexed selection, keys that
     disagree — is "" and the legs are offered one by one, never guessed. */
  function slipCombine(urls) {
    if (!(urls || []).length || urls.some((u) => !u)) return "";
    if (urls.length === 1) return urls[0];
    let base = null, plain = null;
    const indexed = [];
    for (let i = 0; i < urls.length; i++) {
      let u;
      try { u = new URL(urls[i]); } catch (e) { return ""; }
      if (u.protocol !== "https:" || u.hash) return "";
      const here = u.origin + u.pathname;
      if (base === null) base = here; else if (here !== base) return "";
      const q = [...u.searchParams.entries()];
      const idx = q.filter(([k]) => /^\w+\[0\]$/.test(k));
      const rest = q.filter(([k]) => !/^\w+\[\d+\]$/.test(k)).map(([k, v]) => `${k}=${v}`).sort().join("&");
      if (!idx.length || idx.length + q.filter(([k]) => !/^\w+\[\d+\]$/.test(k)).length !== q.length) return "";
      if (plain === null) plain = rest; else if (rest !== plain) return "";
      idx.forEach(([k, v]) => indexed.push([`${k.slice(0, -3)}[${i}]`, v]));
    }
    const enc = (x) => encodeURIComponent(x).replace(/%5B/g, "[").replace(/%5D/g, "]");
    const keep = plain ? plain.split("&").map((kv) => kv.split("=")).map(([k, v]) => `${enc(k)}=${enc(v || "")}`) : [];
    return `${base}?${keep.concat(indexed.map(([k, v]) => `${enc(k)}=${enc(v)}`)).join("&")}`;
  }
  /* BET THE WHOLE TICKET (Ethan, 2026-11-15: "add bet it buttons that adds the
     whole parlay too your sports book. Both td parlays and player prop
     parlays"). The ticket's legs carry the books that hold each one
     (engine/betlinks, `bet_links`); a book holding every leg in a form that
     joins gets one tile for the whole slip, a book holding every leg in a
     form that does not gets a tile per leg (they stack on the book's slip),
     and the rest are front doors. The sheet is the site's own Bet it sheet
     (app.js betSheetShow); no store app opens a sportsbook. */
  function parlayBet(legs, what) {
    if (typeof bookTileHTML !== "function" || typeof bookHomeTilesHTML !== "function") return "";
    if ((typeof storeApp === "function" && storeApp()) || !(legs || []).length) return "";
    const n = legs.length;
    const ok = (u) => typeof u === "string" && u.toLowerCase().startsWith("https://");
    const per = legs.map((l) => {
      const m = new Map();
      (l.bet_links || []).forEach((x) => { if (x && ok(x[1]) && !m.has(x[0])) m.set(x[0], [x[1], x[2]]); });
      return m;
    });
    const books = [];
    per.forEach((m) => m.forEach((_, t) => { if (!books.includes(t)) books.push(t); }));
    const rows = books.map((t) => {
      const cells = per.map((m) => m.get(t) || null);
      const have = cells.filter(Boolean).length;
      return { t, cells, have, one: have === n ? slipCombine(cells.map((c) => c[0])) : "" };
    }).sort((a, b) => (b.have - a.have) || ((b.one ? 1 : 0) - (a.one ? 1 : 0)) || String(a.t).localeCompare(String(b.t)));
    const whole = rows.filter((r) => r.one);
    const each = rows.filter((r) => !r.one && r.have === n);
    const tile1 = whole.map((r) => bookTileHTML(r.t, r.one, null, `all ${n} legs · one slip`, ""));
    const tile2 = each.flatMap((r) => r.cells.map((c, i) => bookTileHTML(r.t, c[0], c[1], "bet slip", `Leg ${i + 1} of ${n}`)));
    const doors = bookHomeTilesHTML(whole.concat(each).map((r) => (typeof bookKey === "function" ? bookKey(r.t) : r.t)));
    return `<span class="betit-box gr-betit"><button type="button" class="betit" aria-haspopup="dialog">Bet it</button>
      <template class="betit-tpl"><div class="betit-head"><b>Bet it</b><span>${escapeHtml(what || "")}</span></div>
        ${tile1.length ? `<p class="betit-h">The whole ticket, one slip</p><div class="betit-grid">${tile1.join("")}</div>` : ""}
        ${tile2.length ? `<p class="betit-h">${tile1.length ? "Or leg by leg" : "Leg by leg"}</p><div class="betit-grid">${tile2.join("")}</div>` : ""}
        ${doors ? `<p class="betit-h">${tile1.length || tile2.length ? "Or key it in at" : "Key it in at"}</p><div class="betit-grid pages">${doors}</div>` : ""}
        <p class="betit-fine">${tile2.length ? "A tile tagged by leg carries that leg only; add each one and they stack on the same slip as a parlay. " : ""}A same-game parlay is priced by the book, and pays less than the legs' own prices multiplied. Opens the book in a new tab; you place the bet there. Prices move — check before you place. 21+ · Gambling problem? 1-800-GAMBLER</p></template></span>`;
  }

  function block(b) {
    if (!b || !b.type) return "";
    if (b.type === "matchbars") return matchbars(b);
    /* WHO WE THINK WINS (engine/gamereport.sec_verdict, Ethan 2026-11-16): the
       call, and its chance as a bar split between the two clubs. */
    if (b.type === "winner") {
      const p = Math.max(0, Math.min(1, Number(b.chance) || 0)), pct = (x) => `${Math.round(x * 100)}%`;
      // The other side's share is what the call's leaves, so the two say 100 (70% and 30%, never 31%).
      const rest = `${100 - Math.round(p * 100)}%`;
      const us = b.name || teamName(b.team), them = b.other_name || teamName(b.other);
      return `<div class="gr-winner">
        <div class="gr-winner-head"><span class="gr-winner-k">${escapeHtml(b.word || "Our call")}</span>
          <b class="gr-winner-team">${escapeHtml(us)}</b><span class="gr-winner-p">${pct(p)} to win</span></div>
        <div class="gr-winner-bar" role="img" aria-label="${escapeAttr(`${us} ${pct(p)}, ${them} ${rest}`)}"><i style="width:${(p * 100).toFixed(1)}%"></i></div>
        <div class="gr-winner-legend"><span>${escapeHtml(us)} ${pct(p)}</span><span>${escapeHtml(them)} ${rest}</span></div>
        ${winnerRatingsHTML(b.ratings, pct)}
        ${winnerResultHTML(b)}
        ${winnerLinesHTML(b)}
      </div>`;
    }
    if (b.type === "p") return `<p class="gr-p">${named(b.text, b.names, b.marks, true)}${gradeLine(b.grade)}</p>`;
    /* HOW THESE READS HAVE DONE (engine/reportrecord.track_lines): a graded
       section's kind of read, its record on finished games so far. */
    if (b.type === "track") return `<p class="gr-track">${escapeHtml(b.text)}</p>`;
    if (b.type === "h") return `<h4 class="gr-h">${escapeHtml(b.text)}</h4>`;
    /* THE NEWS ABOUT THE TWO CLUBS (engine/gamereport.sec_news): each
       headline as its publisher wrote it, opening on their site. */
    if (b.type === "headlines") return newsListHTML(b.items || []);
    if (b.type === "note") return `<p class="gr-note">${named(b.text, b.names, b.marks)}</p>`;
    if (b.type === "list") {
      return `<ul class="gr-list">${(b.items || []).map((t, i) => `<li>${named(t, b.names, b.marks, true)}${
        gradeLine((b.grades || [])[i])}</li>`).join("")}</ul>`;
    }
    if (b.type === "table" && b.fold) {
      // EVERY NUMBER, ONE TAP UNDER THE CHART that draws its ranks.
      return `<details class="gr-fold-tbl"><summary>Every number: ${escapeHtml(b.title || "the table")}</summary>${
        block(Object.assign({}, b, { fold: false }))}</details>`;
    }
    if (b.type === "table") {
      const head = b.head || [];
      return `<div class="gr-table-wrap">${b.title ? `<div class="gr-table-title">${escapeHtml(b.title)}</div>` : ""}
        <table class="agate gr-table"><thead><tr>${head.map((h, i) =>
          `<th${i ? ' class="num"' : ""}>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${(b.rows || []).map((r) => `<tr>${r.map((c, i) =>
          `<td${i ? ' class="num"' : ""}>${(i && b.rank_of && !(b.rank_skip || []).includes(r[0])
            && rankCell(c, b.rank_of)) || named(String(c), b.names, null, false, false)}</td>`).join("")}</tr>`).join("")}</tbody></table>
        ${b.note ? `<p class="gr-note">${escapeHtml(b.note)}</p>` : ""}</div>`;
    }
    if (b.type === "verdicts" || b.type === "players") {
      return `<div class="gr-people">${(b.items || []).map((v) => {
        const tone = TONE[v.verdict || v.tone] || "";
        const door = v.player ? ` data-open="player:${escapeAttr(slugify(v.player))}"` : "";
        const who = [v.team ? teamName(v.team) : "", v.pos, v.role].filter(Boolean).join(" · ");
        // His name in his read's colour where the block says it (the
        // basketball report's "Who carries each team"); the card opens him.
        const nt = b.type === "players" ? ((b.names || {})[v.player] || {}) : {};
        const ntone = TONE[nt.tone] || "";
        return `<div class="gr-person ${tone}"${door}>
          <div class="gr-person-head">${playerAvatar(v.player, v.team, { size: 36, headshot: v.headshot })}
            <span class="gr-person-who"><b${ntone ? ` class="gr-name ${ntone}" title="${escapeAttr(nt.label || "")}"` : ""}>${
              b.type === "verdicts" ? named(v.title, b.names) : escapeHtml(v.player)}${ntone && nt.label
              ? `<span class="gr-sr"> (${escapeHtml(String(nt.label).toLowerCase())})</span>` : ""}</b>
              <span>${escapeHtml(who)}</span></span>
            ${v.label ? `<span class="ms-read-tag ${tone}">${escapeHtml(v.label)}</span>` : ""}
            ${v.status ? `<span class="ms-read-tag gr-status">${escapeHtml(v.status)}</span>` : ""}</div>
          ${b.type === "verdicts"
            ? ((v.why || []).length ? `<ul class="gr-why">${v.why.map((w, i) => `<li>${named(w, b.names, null, true)}${
                i === 0 && v.scorer_bet ? scorerTag(v.scorer_bet) : ""}</li>`).join("")}</ul>` : "")
            : v.text ? `<p class="gr-person-text">${named(v.text, b.names)}</p>` : ""}
          ${v.pick ? `<p class="gr-person-pick">${named(v.pick, b.names)}${v.bet ? resTag(v.bet) : ""}</p>` : ""}
          ${gradeLine(v.grade)}
          ${form(v.form)}
        </div>`;
      }).join("")}</div>`;
    }
    /* OUR PICKS FOR THIS GAME (engine/gamereport.sec_card, 2026-11-15): the
       research's card — each pick, best first, with its price, our chance,
       the most to pay, how often he cleared it, why, and how its kind hit. */
    if (b.type === "picks") {
      return `<ol class="gr-picks">${(b.items || []).map((v) => `<li class="gr-pick"${v.player
        ? ` data-open="player:${escapeAttr(slugify(v.player))}"` : ""}>
        <div class="gr-pick-head"><span class="gr-pick-n">${escapeHtml(String(v.rank || ""))}</span>
          <b class="gr-pick-what">${named(v.pick || "", b.names)}</b>${v.price
            ? ` <span class="gr-pick-px">${escapeHtml(v.price)}</span>` : ""}${v.tier
            ? ` <span class="gr-pick-tier">${escapeHtml(v.tier)}</span>` : ""}${v.bet ? resTag(v.bet) : ""}</div>
        ${v.numbers ? `<p class="gr-pick-num">${escapeHtml(v.numbers)}</p>` : ""}
        ${v.form ? `<p class="gr-pick-form">${escapeHtml(v.form)}</p>` : ""}
        ${(v.why || []).length ? `<ul class="gr-why">${v.why.map((w) => `<li>${named(w, b.names, b.marks, true)}</li>`).join("")}</ul>` : ""}
        ${v.kind ? `<p class="gr-pick-kind">${escapeHtml(v.kind)}</p>` : ""}</li>`).join("")}</ol>`;
    }
    /* EACH GAME'S PARLAYS (engine/gameparlays, 2026-11-14): its two strongest
       picks as two-leg tickets (2026-11-18), two or three three-leg tickets and
       three scorer pairs, each leg with its price, our chance and why, the
       script the ticket needs, its backups and caveats. */
    if (b.type === "parlays") {
      const items = (xs) => (xs || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
      return `<div class="gr-parlays">${(b.items || []).map((t) => `<div class="gr-parlay">
        <div class="gr-parlay-head"><b>${escapeHtml(t.title || "")}</b>${ticketTag(t.legs)}${(t.bet_legs || []).length && !CLOSED
          ? parlayBet(t.bet_legs, `${t.title || "Parlay"} · ${(t.legs || []).map((l) => l.pick).filter(Boolean).join(" + ")}`) : ""}</div>
        ${t.price_line ? `<p class="gr-parlay-price">${escapeHtml(t.price_line)}</p>` : ""}
        <ol class="gr-parlay-legs">${(t.legs || []).map((l) => `<li${l.player
          ? ` data-open="player:${escapeAttr(slugify(l.player))}"` : ""}>
          <span class="gr-parlay-pick"><b>${named(l.pick || "", b.names)}</b>${l.price
            ? ` <span class="gr-parlay-px">${escapeHtml(l.price)}</span>` : ""}${l.chance
            ? ` <span class="gr-parlay-p">${Math.round(Number(l.chance) * 100)}%</span>` : ""}${l.research != null
            ? ` <span class="gr-parlay-r" title="Our research score: the team’s expected points, the defense faced, the usage and red-zone work, the matchup read and the game script">research score ${escapeHtml(String(l.research))} of ${escapeHtml(String(l.research_of || 13))}</span>` : ""}${
            l.bet ? resTag(l.bet) : ""}</span>
          ${(l.why || []).length ? `<ul class="gr-why">${items(l.why)}</ul>` : ""}</li>`).join("")}</ol>
        ${t.script ? `<p class="gr-parlay-script">${escapeHtml(t.script)}</p>` : ""}
        ${t.rule_note ? `<p class="gr-parlay-rule${t.td_rule ? " ok" : ""}">${escapeHtml(t.rule_note)}</p>` : ""}
        ${(t.links || []).length ? `<ul class="gr-list gr-parlay-links">${items(t.links)}</ul>` : ""}
        ${(t.backups || []).length ? `<div class="gr-parlay-sub">Backups</div><ul class="gr-list">${items(t.backups)}</ul>` : ""}
        ${(t.caveats || []).length ? `<div class="gr-parlay-sub">Caveats</div><ul class="gr-list">${items(t.caveats)}</ul>` : ""}
      </div>`).join("")}</div>`;
    }
    return "";
  }

  /* THE REPORT AS PLAIN TEXT — what "Copy the report" puts on the
     clipboard, in the page's reading order (engine/gamereport.to_text is
     the box's copy of the same walk). Tables go row by row with dots
     between the cells: a message app's font is not monospaced, so padded
     columns would not line up anyway. */
  function toText(r, url) {
    const out = [r.title + (r.when ? ` — ${r.when}` : ""), "The Qellys Book game report"];
    for (const s of r.sections || []) {
      out.push("", String(s.title || "").toUpperCase());
      for (const b of s.blocks || []) {
        if (!b || !b.type) continue;
        if (b.type === "p" || b.type === "note" || b.type === "track") out.push(b.text);
        else if (b.type === "winner") {
          out.push(`${b.word || "Our call"}: ${b.name || b.team} — ${Math.round(Number(b.chance || 0) * 100)}% to win`);
          const r = b.ratings;
          if (r && r.chance != null) out.push(`Our ratings alone (unproven): ${r.even ? "an even game" : `${r.name || r.team} ${Math.round(Number(r.chance) * 100)}%`}`);
        }
        else if (b.type === "h") out.push("", b.text);
        else if (b.type === "headlines") (b.items || []).forEach((n) => out.push(`• ${n.source ? `${n.source}: ` : ""}${n.headline}${n.href ? ` (${n.href})` : ""}`));
        else if (b.type === "list") (b.items || []).forEach((t) => out.push(`• ${t}`));
        else if (b.type === "table") {
          if (b.title) out.push(b.title);
          [b.head || [], ...(b.rows || [])].forEach((row) => out.push(row.join("  ·  ")));
          if (b.note) out.push(`(${b.note})`);
        } else if (b.type === "verdicts" || b.type === "players") {
          for (const v of b.items || []) {
            const who = [v.team, v.pos].filter(Boolean).join(" ");
            out.push(b.type === "verdicts"
              ? `• ${v.title} — ${v.label}${v.role ? ` (${v.role})` : ""}`
              : `• ${v.player}${who ? ` (${who})` : ""}${v.label ? ` — ${v.label}` : ""}${v.status ? ` (${v.status})` : ""}${v.text ? `: ${v.text}` : ""}`);
            (v.why || []).forEach((w) => out.push(`    – ${w}`));
            if (v.pick) out.push(`    ${v.pick}`);
            (v.form || []).forEach(([k, lines]) => out.push(`    ${k}: ${(lines || []).join(" | ")}`));
          }
        } else if (b.type === "picks") {
          for (const v of b.items || []) {
            out.push(`${v.rank}. ${v.pick}${v.price ? ` — ${v.price}` : ""}${v.tier ? ` [${v.tier}]` : ""}`);
            [v.numbers, v.form].filter(Boolean).forEach((x) => out.push(`    ${x}`));
            (v.why || []).forEach((w) => out.push(`    – ${w}`));
            if (v.kind) out.push(`    ${v.kind}`);
          }
        } else if (b.type === "parlays") {
          for (const t of b.items || []) {
            out.push(`• ${t.title}: ${t.price_line || ""}`);
            for (const l of t.legs || []) {
              out.push(`    – ${l.pick}${l.price ? ` (${l.price})` : ""}${l.chance ? `, ${Math.round(Number(l.chance) * 100)}%` : ""}${
                l.research != null ? `, our research score ${l.research} of ${l.research_of || 13}` : ""}`);
              (l.why || []).forEach((w) => out.push(`        · ${w}`));
            }
            if (t.script) out.push(`    ${t.script}`);
            if (t.rule_note) out.push(`    ${t.rule_note}`);
            (t.backups || []).forEach((x) => out.push(`    Backup: ${x}`));
            (t.caveats || []).forEach((x) => out.push(`    Caveat: ${x}`));
          }
        }
      }
    }
    if (url) out.push("", url);
    return out.join("\n");
  }

  /* WHAT SHARE SENDS: the game, its kickoff and its line, and the link —
     the public facts and nothing of the report. Whoever it is forwarded
     to reads the share text before anybody has paid for anything (the
     same rule as app.js pickSlug). */
  function teaser(r) {
    return [r.title + (r.when ? ` — ${r.when}` : ""), r.line ? r.line[0].toUpperCase() + r.line.slice(1) : "",
            "Our full game report is on Qellys Book."].filter(Boolean).join(". ").replace(/\.\./g, ".");
  }

  function said(btn, msg) {
    const was = btn.textContent;
    btn.textContent = msg;
    setTimeout(() => { btn.textContent = was; }, 1600);
  }

  /* The clipboard first, on a phone too: "Copy" that opens a share sheet
     is not what the button says. Where there is no clipboard (an insecure
     context, an app without the permission) the share sheet is the way
     out; where there is neither, the button says so. */
  async function copy(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      said(btn, "Copied");
      return;
    } catch (e) { /* no clipboard here */ }
    if (navigator.share) {
      try { await navigator.share({ text }); } catch (e) { /* dismissed */ }
      return;
    }
    said(btn, "Copy didn’t work");
  }

  async function share(r, url, btn) {
    const text = teaser(r);
    if (navigator.share) {
      try { await navigator.share({ title: r.title, text, url }); } catch (e) { /* dismissed */ }
      return;
    }
    copy(url ? `${text}\n${url}` : text, btn);
  }

  /* The reports drawn this visit, by game, for the two buttons. */
  const shown = new Map();
  if (typeof document !== "undefined") {
    document.addEventListener("click", (e) => {
      const all = e.target.closest && e.target.closest("[data-gr-all]");
      if (all && all.dataset && all.dataset.grAll) {
        // EVERY SECTION AT ONCE: open them all, or fold them back.
        const box = typeof all.closest === "function" ? all.closest(".gr") : null;
        const card = box && box.querySelector(".gr-card");
        const folds = card ? [...card.querySelectorAll("details.gr-fold")] : [];
        const open = folds.some((d) => !d.open);
        folds.forEach((d) => { d.open = open; });
        all.textContent = open ? "Fold the sections" : "Open every section";
        return;
      }
      const b = e.target.closest && e.target.closest("[data-gr-copy], [data-gr-share]");
      if (!b) return;
      const hit = shown.get(b.dataset.grCopy || b.dataset.grShare);
      if (!hit) return;
      e.preventDefault();
      if (b.dataset.grCopy) copy(toText(hit.r, hit.url), b);
      else share(hit.r, hit.url, b);
    });
  }

  /* The report (r), or — for a reader without the paid key — what it
     holds. */
  /* ---------------- the watch between builds ----------------
     Ethan, 2026-11-17: "make sure the game reports keep a constant watch and
     update on nfl news and injuries". engine/reportwatch looks at the injury
     report and the news every five minutes; the report's own "Latest news
     and injury moves" holds what it saw when the report was built
     (`watch_at`), and this card, at the top, what has landed since. The game
     page reads the watch again while it stays open (detail.js
     reportWatchFor), so a player ruled out at noon is on the page at noon. */
  const AGO = (t) => {
    const s = Math.max(0, (Date.now() - t) / 1000);
    return s < 90 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} hr ago`
      : `${Math.round(s / 86400)} d ago`;
  };
  const FLAG = { injury: "Injury", roster: "Roster" };
  function newsListHTML(items) {
    return `<ul class="gr-news">${items.map((n) => {
      const at = Date.parse(n.at || "");
      const flag = FLAG[n.flag] ? `<span class="gr-news-flag ${escapeAttr(n.flag)}">${FLAG[n.flag]}</span>` : "";
      const head = escapeHtml(n.headline || n.title || "");
      const link = String(n.href || n.link || "");
      return `<li>${flag}${/^https?:\/\//.test(link)
        ? `<a href="${escapeAttr(link)}" target="_blank" rel="noopener noreferrer">${head}</a>` : head}
        <span class="gr-news-src">${escapeHtml(n.source || "")}${Number.isFinite(at) ? ` · ${AGO(at)}` : ""}</span></li>`;
    }).join("")}</ul>`;
  }
  function moveWords(u) {
    const was = String(u.from || "").toLowerCase(), now = String(u.to || "").toLowerCase();
    if (now === "active") return was ? `cleared to play (was ${was})` : "cleared to play";
    return `${was ? `${was} to ${now}` : `newly listed ${now}`}${u.injury ? ` (${String(u.injury).toLowerCase()})` : ""}`;
  }
  /* WHAT A MOVE TOUCHES (2026-11-17). A player ruled out at noon may be in
     the report's own bets: its picks, a read's pick, a parlay's leg. The card
     names each beside the move, with the parlay's backup leg for that player
     where the ticket has one, so a reader does not bet a pick the next update
     will change. Keyed by the name's slug, as the page's player links are. */
  function stakesOf(r) {
    const out = new Map();
    const put = (name, line) => {
      const k = slugify(name || "");
      if (!k || !line) return;
      if (!out.has(k)) out.set(k, []);
      if (!out.get(k).includes(line)) out.get(k).push(line);
    };
    ((r && r.sections) || []).forEach((s) => ((s && s.blocks) || []).forEach((b) => ((b && b.items) || []).forEach((it) => {
      if (!it) return;
      if (b.type === "parlays") {
        (it.legs || []).forEach((l) => {
          if (!l || !l.player) return;
          const lead = `If ${l.player} is out or that number moves: `;
          const backup = (it.backups || []).find((x) => String(x).startsWith(lead));
          put(l.player, `${it.title}: ${l.pick}${backup ? ` (its backup: ${String(backup).slice(lead.length)})` : ""}`);
        });
      } else if (it.player && it.pick) put(it.player, it.pick);
    })));
    return out;
  }
  function watchCardHTML(w, since, stakes) {
    const t0 = Date.parse(since || "") || 0;
    const fresh = (x) => (Date.parse(x.at || "") || 0) > t0;
    const ups = (w.updates || []).filter(fresh).slice(0, 5);
    const news = (w.news || []).filter(fresh).slice(0, 4);
    const checked = Date.parse(w.checked_at || "");
    const when = Number.isFinite(checked) ? `checked ${AGO(checked)}` : "";
    if (!ups.length && !news.length) {
      return `<p class="gr-watch-quiet">${icon("check", 13)} No new injury moves or headlines since this report was written${
        when ? ` · ${when}` : ""}</p>`;
    }
    const tone = (u) => /out|reserve|ir\b|doubtful|suspend/i.test(u.to || "") ? "down"
      : /active/i.test(u.to || "") ? "up" : "warn";
    return `<div class="card gr-watch" role="status">
      <div class="gr-watch-h"><b>Since this report was written</b>${when ? `<span>${escapeHtml(when)}</span>` : ""}</div>
      ${ups.length ? `<ul class="gr-watch-ups">${ups.map((u) => {
        const bets = tone(u) === "up" ? [] : ((stakes && stakes.get(slugify(u.player || ""))) || []);
        return `<li class="${tone(u)}"><span class="gr-name" data-open="player:${
          escapeAttr(slugify(u.player || ""))}">${escapeHtml(u.player || "")}</span> <span class="gr-watch-team">${
          escapeHtml(u.team || "")}</span> ${escapeHtml(moveWords(u))}${bets.length
          ? `<span class="gr-watch-stake">In this report: ${bets.map(escapeHtml).join("; ")}. Wait for the next update
            before betting ${bets.length > 1 ? "these" : "it"}.</span>` : ""}</li>`;
      }).join("")}</ul>` : ""}
      ${news.length ? newsListHTML(news) : ""}
    </div>`;
  }

  /* A FEATURED GAME SAYS SO AT ITS TOP (engine/featured.badge, FEATURED1, 2026-11-19). Ethan: "the main game
     reports that I want to focus on is any game reports that has to do with a Lions game, any game reports on a
     Thursday night, or any game reports on a Monday night". Its kinds, and how the reports on games like it have
     done so far; their whole record is on the Record and Report Picks pages. */
  function featuredHTML(f) {
    if (!f || !f.words) return "";
    const lines = (f.lines || []).map((l) => `<p class="gr-featured-line">${escapeHtml(l)}</p>`).join("");
    return `<div class="gr-featured"><span class="gr-featured-tag"><span aria-hidden="true">★</span>Featured · ${
      escapeHtml(f.words)}</span>${lines}</div>`;
  }

  function html(r, extras) {
    // A UFC fight's report (engine/ufc/report, 2026-11-16; Ethan: "Yes" to a
    // written fight report), drawn inside its card on the UFC tab: several
    // on one page, so no page-wide ids, and no game page to share.
    const fight = !!(extras && extras.fight);
    // AN OLD GAME'S REPORT (engine/reportarchive), drawn on its play-by-play
    // page beside whatever else is open: no page-wide ids, nothing to share.
    const solo = fight || !!(extras && extras.embedded);
    const head = fight ? `<div class="section-title">The fight report
      <span class="sub">— ${r ? `about ${r.minutes} min to read · ` : ""}the fight written out from the card’s
      own numbers</span></div>` : `<div class="section-title">The game report
      <span class="sub">— ${r ? `about ${r.minutes} min to read · ` : ""}${r && r.kept
        // A started game's report is the one it had before the start (engine/reportkeep).
        ? `as written before the game started, last updated ${escapeHtml(r.kept)}`
        // A finished game's locked teaser: it was written before the game, not from tonight's board.
        : !r && extras && extras.results ? "the whole game written out before it started"
        : "the whole game written out from tonight’s board"}</span></div>`;
    if (!r) {
      const holds = HOLDS[(extras && extras.sport) || ""] || HOLDS.nfl;
      // The heading above names it; the card says what it holds, once.
      return `<div id="gp-sec-report" class="gr">${head}<div class="card ms-locked">What it holds — ${holds} — is
        part of the subscription.</div></div>`;
    }
    RANK_OF = Number(r.rank_of) || 0;
    RESULTS = (extras && extras.results) || null;
    CLOSED = !!(r.kept || RESULTS);
    const secs = (r.sections || []).filter((s) => s && (s.blocks || []).length);
    const body = secs.map((s) => {
      let blocks = s.blocks || [];
      let extra = "";
      // The simulation card draws the same simulated games the report's
      // table lists, as a gauge and a histogram; with it here the table
      // steps aside.
      if (s.key === "scripts" && extras && extras.scripts) {
        blocks = blocks.filter((b) => b.type !== "table");
        extra = `<div class="gr-extra">${extras.scripts}</div>`;
      }
      // Each ticket's legs, with the books that hold them, from the board's
      // game parlays (the report's cards are in the tickets' own order).
      const gp = extras && extras.parlays;
      if (gp && s.key === "parlays") {
        blocks = blocks.map((b) => b.type !== "parlays" ? b : Object.assign({}, b, {
          items: (b.items || []).map((t, i) => Object.assign({}, t, {
            bet_legs: ((gp[{ three: "threes", two: "twos" }[b.kind] || "scorers"] || [])[i] || {}).legs || [] })) }));
      }
      const inner = `${blocks.map(block).join("")}${extra}`;
      // ONE SECTION OPEN, THE REST ONE TAP AWAY (Ethan, 2026-11-15: "it still
      // feels all cluttered and hard to digest everything"). The short
      // version reads first; every other section folds to its title, and
      // the titles are the report's contents.
      if (OPEN_SECTIONS.includes(s.key) || secs.length < 3) {
        return `<section class="gr-sec"${solo ? "" : ` id="gr-${escapeAttr(s.key)}"`}><h3 class="gr-title">${escapeHtml(s.title)}</h3>
        ${inner}</section>`;
      }
      return `<details class="gr-sec gr-fold"${solo ? "" : ` id="gr-${escapeAttr(s.key)}"`}><summary class="gr-title">${
        escapeHtml(s.title)}<span class="row-fold-chev" aria-hidden="true"></span></summary><div class="gr-fold-body">${
        inner}</div></details>`;
    }).join("");
    const url = (extras && extras.url) || "";
    shown.set(r.game, { r, url });
    const folded = secs.length >= 3;
    const tools = `<div class="gr-tools">
      <button type="button" class="btn ghost" data-gr-copy="${escapeAttr(r.game)}">Copy the report</button>${
        solo ? "" : `<button type="button" class="btn ghost" data-gr-share="${escapeAttr(r.game)}">Share this game</button>`}${
        folded ? `<button type="button" class="btn ghost" data-gr-all="1">Open every section</button>` : ""}</div>`;
    // The watch's newest, over the report, until the game is under way.
    const watch = extras && extras.watch && !CLOSED && !solo ? watchCardHTML(extras.watch, r.watch_at, stakesOf(r)) : "";
    return `<div${solo ? "" : ' id="gp-sec-report"'} class="gr">${head}${featuredHTML(r.featured)}${tools}${watch}<div class="card gr-card">${colourKey(body)}${body}</div></div>`;
  }

  /* EACH GAME'S PARLAYS, AS THE REPORT'S OWN CARDS (gameTickets, drawn on the
     Report Picks page): the board's tickets (engine/gameparlays) in the words
     engine/gameparlays.card writes for the report. The Parlays page that drew
     every game's at once left 2026-11-16, and its renderer with it. */
  const SCORE = { anytime_td: "to score a touchdown", anytime_goal: "to score a goal", goals: "to score a goal" };
  function pickWords(l) {
    const m = String(l.market || "");
    if (SCORE[m]) return `${l.player} ${SCORE[m]}`;
    const line = l.line == null ? "" : ` ${l.line}`;
    return `${l.player || ""} ${String(l.side || "").toLowerCase()}${line} ${
      String(l.market_label || m.replace(/_/g, " ")).toLowerCase()}`.replace(/\s+/g, " ").trim();
  }
  function oddsWords(o) {
    const n = Number(o);
    return Number.isFinite(n) && n ? (n > 0 ? `+${n}` : String(n)) : "";
  }
  function card(t, n, kind, sport) {
    const pct = (x) => `${Math.round(Number(x || 0) * 100)}%`;
    const title = kind === "three" ? `Parlay ${n}` : kind === "two" ? `Two-leg parlay ${n}`
      : `${["nfl", "cfb"].includes(sport) ? "Touchdown" : "Scorer"} pair ${n}`;
    // The legs-unrelated chance only where it differs (a link counted): beside an equal number it says it twice.
    const unrel = pct(t.independent) !== pct(t.joint) ? ` (${pct(t.independent)} if the legs were unrelated)` : "";
    let price = `${pct(t.joint)} by our numbers${unrel} · fair ${
      t.fair_words || ""} · take it at ${t.take_words || ""} or better`;
    if (t.naive_words) price += ` · the legs’ own prices multiplied pay ${t.naive_words}, and a book’s same-game price pays less`;
    const script = t.script ? `What it needs: ${t.script}${t.script_chance != null
      ? ` — about ${pct(t.script_chance)} likely by the lines` : ""}` : "";
    /* The touchdown rule on a pair (engine/gameparlays.card: each scorer 40%
       or better), the same words the report prints. */
    const low = !["three", "two"].includes(kind) && ["nfl", "cfb"].includes(sport)
      ? (t.legs || []).filter((l) => Number(l.p || 0) < 0.40) : null;
    const rule = low == null ? {} : { td_rule: !low.length, rule_note: !low.length
      ? "Both scorers are 40% or better — our touchdown rule"
      : `Below our touchdown rule (40% a scorer): ${low.map((l) => `${l.player} ${pct(l.p)}`).join(", ")}` };
    return {
      title, price_line: price, script, links: t.links || [], caveats: t.caveats || [], ...rule,
      legs: (t.legs || []).map((l) => ({ pick: pickWords(l), player: l.player,
        price: [oddsWords(l.odds), l.book || ""].filter(Boolean).join(" "), chance: l.p, why: l.why || [],
        research: l.research, research_of: l.research_of, bet: l })),
      backups: (t.backups || []).map((b) => `If ${b.for} is out or that number moves: ${pickWords(b.leg || {})} (${
        oddsWords((b.leg || {}).odds)}, ${pct((b.leg || {}).p)})`),
      bet_legs: t.legs || [],
    };
  }
  //: One game's tickets, its two-leg parlays, its three-leg ones, then its scorer pairs, each
  //: graded once the game is over (opts.results: game → the grader, app.js);
  //: the Report Picks page draws them under the game's bets (js/reportpicks.js).
  function gameTickets(g, sport, opts) {
    const was = RESULTS, shut = CLOSED;
    RESULTS = (opts && typeof opts.results === "function" && opts.results(g)) || null;
    CLOSED = !!((g && g.kept) || RESULTS);
    try {
      // Every game posts two or three three-leg tickets (THREELEG1, 2026-11-19); a game that could make
      // fewer than two says why under the ones it made (engine/gameparlays._report_note). "On paper" is a
      // game from before 19 November, when a league's three-leg tickets could be held (engine/parlayhold).
      // The two strongest picks together lead (GPWIN1, engine/gameparlays.tickets_of): two legs hit far
      // more often than three. Fewer than two, or none: the note says why.
      const twos = (g.twos || []).length
        ? block({ type: "parlays", items: g.twos.map((t, i) => card(t, i + 1, "two", sport)) })
          + (g.twos_note ? `<p class="gr-note">${escapeHtml(g.twos_note)}</p>` : "")
        : g.twos_paper ? `<p class="gr-note">Two-leg parlays: on paper for now, built and graded but not posted.</p>`
        : g.twos_note ? `<p class="gr-note">No two-leg parlay: ${escapeHtml(g.twos_note)}</p>` : "";
      return `${twos}${(g.threes || []).length ? block({ type: "parlays", items: g.threes.map((t, i) => card(t, i + 1, "three", sport)) })
          + (g.threes_note ? `<p class="gr-note">${escapeHtml(g.threes_note)}</p>` : "")
        : g.threes_paper ? `<p class="gr-note">Three-leg parlays: on paper for now, built and graded but not posted.</p>`
        : `<p class="gr-note">${escapeHtml(g.threes_note || "No three-leg ticket without a conflict in this game.")}</p>`}
        ${(g.scorers || []).length ? block({ type: "parlays", items: g.scorers.map((t, i) => card(t, i + 1, "scorers", sport)) })
          : (g.scorers_note ? `<p class="gr-note">${escapeHtml(g.scorers_note)}</p>` : "")}`;
    } finally { RESULTS = was; CLOSED = shut; }
  }
  window.QBReport = { html, block, toText, teaser, gameTickets, slipCombine };
})();
