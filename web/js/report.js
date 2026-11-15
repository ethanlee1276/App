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
    "defence gives, the injury report and what to check before tip-off";
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
  const OPEN_SECTIONS = ["card", "short"];

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
    if (b.type === "p") return `<p class="gr-p">${named(b.text, b.names, b.marks, true)}</p>`;
    if (b.type === "h") return `<h4 class="gr-h">${escapeHtml(b.text)}</h4>`;
    if (b.type === "note") return `<p class="gr-note">${named(b.text, b.names, b.marks)}</p>`;
    if (b.type === "list") {
      return `<ul class="gr-list">${(b.items || []).map((t) => `<li>${named(t, b.names, b.marks, true)}</li>`).join("")}</ul>`;
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
            ? ((v.why || []).length ? `<ul class="gr-why">${v.why.map((w) => `<li>${named(w, b.names, null, true)}</li>`).join("")}</ul>` : "")
            : v.text ? `<p class="gr-person-text">${named(v.text, b.names)}</p>` : ""}
          ${v.pick ? `<p class="gr-person-pick">${named(v.pick, b.names)}</p>` : ""}
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
            ? ` <span class="gr-pick-tier">${escapeHtml(v.tier)}</span>` : ""}</div>
        ${v.numbers ? `<p class="gr-pick-num">${escapeHtml(v.numbers)}</p>` : ""}
        ${v.form ? `<p class="gr-pick-form">${escapeHtml(v.form)}</p>` : ""}
        ${(v.why || []).length ? `<ul class="gr-why">${v.why.map((w) => `<li>${named(w, b.names, b.marks, true)}</li>`).join("")}</ul>` : ""}
        ${v.kind ? `<p class="gr-pick-kind">${escapeHtml(v.kind)}</p>` : ""}</li>`).join("")}</ol>`;
    }
    /* EACH GAME'S PARLAYS (engine/gameparlays, 2026-11-14): four three-leg
       tickets and three scorer pairs, each leg with its price, our chance
       and why, the script the ticket needs, its backups and caveats. */
    if (b.type === "parlays") {
      const items = (xs) => (xs || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
      return `<div class="gr-parlays">${(b.items || []).map((t) => `<div class="gr-parlay">
        <div class="gr-parlay-head"><b>${escapeHtml(t.title || "")}</b>${(t.bet_legs || []).length
          ? parlayBet(t.bet_legs, `${t.title || "Parlay"} · ${(t.legs || []).map((l) => l.pick).filter(Boolean).join(" + ")}`) : ""}</div>
        ${t.price_line ? `<p class="gr-parlay-price">${escapeHtml(t.price_line)}</p>` : ""}
        <ol class="gr-parlay-legs">${(t.legs || []).map((l) => `<li${l.player
          ? ` data-open="player:${escapeAttr(slugify(l.player))}"` : ""}>
          <span class="gr-parlay-pick"><b>${named(l.pick || "", b.names)}</b>${l.price
            ? ` <span class="gr-parlay-px">${escapeHtml(l.price)}</span>` : ""}${l.chance
            ? ` <span class="gr-parlay-p">${Math.round(Number(l.chance) * 100)}%</span>` : ""}${l.research != null
            ? ` <span class="gr-parlay-r" title="Our research score: his team’s expected points, the defense he faces, his usage and red-zone work, the matchup read and the game script">research score ${escapeHtml(String(l.research))} of ${escapeHtml(String(l.research_of || 13))}</span>` : ""}</span>
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
        if (b.type === "p" || b.type === "note") out.push(b.text);
        else if (b.type === "h") out.push("", b.text);
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
  function html(r, extras) {
    const head = `<div class="section-title">The game report
      <span class="sub">— ${r ? `about ${r.minutes} min to read · ` : ""}the whole game written out from
      tonight’s board; no prop picks in it</span></div>`;
    if (!r) {
      const holds = HOLDS[(extras && extras.sport) || ""] || HOLDS.nfl;
      return `<div id="gp-sec-report" class="gr">${head}<div class="card ms-locked"><b>The game report</b> —
        this game written out top to bottom: ${holds} — is part of the subscription.</div></div>`;
    }
    RANK_OF = Number(r.rank_of) || 0;
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
            bet_legs: ((gp[b.kind === "three" ? "threes" : "scorers"] || [])[i] || {}).legs || [] })) }));
      }
      const inner = `${blocks.map(block).join("")}${extra}`;
      // ONE SECTION OPEN, THE REST ONE TAP AWAY (Ethan, 2026-11-15: "it still
      // feels all cluttered and hard to digest everything"). The short
      // version reads first; every other section folds to its title, and
      // the titles are the report's contents.
      if (OPEN_SECTIONS.includes(s.key) || secs.length < 3) {
        return `<section class="gr-sec" id="gr-${escapeAttr(s.key)}"><h3 class="gr-title">${escapeHtml(s.title)}</h3>
        ${inner}</section>`;
      }
      return `<details class="gr-sec gr-fold" id="gr-${escapeAttr(s.key)}"><summary class="gr-title">${
        escapeHtml(s.title)}<span class="row-fold-chev" aria-hidden="true"></span></summary><div class="gr-fold-body">${
        inner}</div></details>`;
    }).join("");
    const url = (extras && extras.url) || "";
    shown.set(r.game, { r, url });
    const folded = secs.length >= 3;
    const tools = `<div class="gr-tools">
      <button type="button" class="btn ghost" data-gr-copy="${escapeAttr(r.game)}">Copy the report</button>
      <button type="button" class="btn ghost" data-gr-share="${escapeAttr(r.game)}">Share this game</button>${
        folded ? `<button type="button" class="btn ghost" data-gr-all="1">Open every section</button>` : ""}</div>`;
    return `<div id="gp-sec-report" class="gr">${head}${tools}<div class="card gr-card">${colourKey(body)}${body}</div></div>`;
  }

  /* EACH GAME'S PARLAYS ON THE PARLAYS PAGE (app.js fillGameParlays): the
     board's tickets (engine/gameparlays) as the report's own cards — the
     words engine/gameparlays.card writes for the report, here in the page. */
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
    const title = kind === "three" ? `Parlay ${n}`
      : `${["nfl", "cfb"].includes(sport) ? "Touchdown" : "Scorer"} pair ${n}`;
    let price = `${pct(t.joint)} by our numbers (${pct(t.independent)} if the legs were unrelated) · fair ${
      t.fair_words || ""} · take it at ${t.take_words || ""} or better`;
    if (t.naive_words) price += ` · the legs’ own prices multiplied pay ${t.naive_words}, and a book’s same-game price pays less`;
    const script = t.script ? `What it needs: ${t.script}${t.script_chance != null
      ? ` — about ${pct(t.script_chance)} likely by the lines` : ""}` : "";
    /* The touchdown rule on a pair (engine/gameparlays.card: each scorer 40%
       or better), the same words the report prints. */
    const low = kind !== "three" && ["nfl", "cfb"].includes(sport)
      ? (t.legs || []).filter((l) => Number(l.p || 0) < 0.40) : null;
    const rule = low == null ? {} : { td_rule: !low.length, rule_note: !low.length
      ? "Both scorers are 40% or better — our touchdown rule"
      : `Below our touchdown rule (40% a scorer): ${low.map((l) => `${l.player} ${pct(l.p)}`).join(", ")}` };
    return {
      title, price_line: price, script, links: t.links || [], caveats: t.caveats || [], ...rule,
      legs: (t.legs || []).map((l) => ({ pick: pickWords(l), player: l.player,
        price: [oddsWords(l.odds), l.book || ""].filter(Boolean).join(" "), chance: l.p, why: l.why || [],
        research: l.research, research_of: l.research_of })),
      backups: (t.backups || []).map((b) => `If ${b.for} is out or his number moves: ${pickWords(b.leg || {})} (${
        oddsWords((b.leg || {}).odds)}, ${pct((b.leg || {}).p)})`),
      bet_legs: t.legs || [],
    };
  }
  function gameParlays(gp, sport) {
    const games = (gp && gp.games) || [];
    if (!games.length) return "";
    const pair = ["nfl", "cfb"].includes(sport) ? "touchdown" : sport === "nhl" ? "goal-scorer" : "scorer";
    return `<div class="section-title">Each game’s parlays <span class="sub">— four three-leg tickets and three ${pair}
        pairs a game, from our own picks; every one tracked on the Record page, none staked</span></div>
      <div class="mini tl-rec" data-gp-rec="1"></div>
      ${gp.note ? `<p class="set-note tl-rule">${escapeHtml(gp.note)}</p>` : ""}
      ${games.map((g) => `<details class="gs-game gr-parlay-game"><summary><span class="gs-game-k">${
        escapeHtml(teamName(g.away))} @ ${escapeHtml(teamName(g.home))}</span>
        <span class="gs-game-n">${(g.threes || []).length} three-leg · ${(g.scorers || []).length} pairs</span></summary>
        ${(g.threes || []).length ? block({ type: "parlays", items: g.threes.map((t, i) => card(t, i + 1, "three", sport)) })
          : `<p class="gr-note">${escapeHtml(g.threes_note || "No three-leg ticket without a conflict in this game.")}</p>`}
        ${(g.scorers || []).length ? block({ type: "parlays", items: g.scorers.map((t, i) => card(t, i + 1, "scorers", sport)) })
          : (g.scorers_note ? `<p class="gr-note">${escapeHtml(g.scorers_note)}</p>` : "")}
      </details>`).join("")}`;
  }
  /* Their record so far (record.json two_leg.game, engine/parlayledger
     .report_game_parlays). */
  function gameParlaysRecord(rec) {
    const g = ((rec || {}).two_leg || {}).game || {};
    const bits = [["three", "three-leg"], ["scorers", "pairs"]].map(([k, w]) => {
      const x = g[k] || {};
      if (!x.graded) return x.open ? `${w}: ${x.open} open, none graded yet` : "";
      return `${w}: ${x.wins} of ${x.graded} hit, ${x.net_units >= 0 ? "+" : ""}${x.net_units} units at the take-it price`;
    }).filter(Boolean);
    return bits.length ? `Our record so far — ${bits.join(" · ")}` : "";
  }

  window.QBReport = { html, block, toText, teaser, gameParlays, gameParlaysRecord, slipCombine };
})();
