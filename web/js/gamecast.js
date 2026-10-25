/* Qellys Book — Gamecast: the live game page's rooms, in ESPN's layout.
   ==========================================================================
   Ethan, 2026-10-08, with three screenshots of ESPN's app on a live
   Bucs–Cowboys game: "I want the page to look like ESPN's app looks … see
   the game and stadium like I have now then scroll down and see the live
   game leaders and shit and see the actual play by play and all of that.
   We should have the box score and all of that."

   WHAT IS HERE: the panels under the tabs — Gamecast (the drive in
   progress, the last play with the players in it and their lines so far,
   the game leaders), Box score (every group ESPN's box carries, by team),
   Play-by-play (drive by drive, newest first, how each ended), Team stats
   (the two sides' totals as a comparison), Odds & picks. The hero, the
   field and the tabs stay in app.js (renderPbpPage), which loads this the
   first time a live game is opened (loadGamecast), like the Feed.

   THE NUMBERS, NEVER THE WRITING. Every line is composed from the deep
   file's fields — a play's type, yards, down and distance, the names the
   builder matched against the box score, a box row's stats under ESPN's
   own column labels, a team stat's label and value. ESPN's sentences are
   not in the file (livescore_build.pbp_doc) and could not be drawn if they
   were. The win percentage on the last play is OUR model's (live.win_prob),
   never a number read off somebody else's page.

   Runs in the page's global scope beside app.js and uses its helpers
   (escapeHtml, escapeAttr, icon, teamMarkIn, teamNameIn, playsHTML,
   pbpGroups, pbpOrd, pbpAgo, pbpPropsHTML, lineTrackHTML …) by name. */
(function () {
  "use strict";
  const FOOTBALL = new Set(["nfl", "cfb"]);
  //: ESPN's own headshot folders, by league — the same CDN path
  //: engine/sources/nflverse.ESPN_HEADSHOT draws NFL faces from. A face is
  //: the board's own first (the deep file's `faces`), this second, blank
  //: third.
  const FACE_DIR = { nfl: "nfl", cfb: "college-football", nba: "nba", wnba: "wnba", nhl: "nhl" };
  //: The box score's open side (the team toggle), kept across redraws.
  let _team = "";

  const esc = (v) => escapeHtml(String(v == null ? "" : v));
  const num = (s) => { const m = /-?\d+(\.\d+)?/.exec(String(s == null ? "" : s)); return m ? Number(m[0]) : NaN; };
  const plain = (s) => /^-?\d+(\.\d+)?$/.test(String(s == null ? "" : s).trim());
  const lower = (s) => String(s || "").toLowerCase();
  const titleCase = (v) => String(v || "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  /* ---------------- faces ---------------- */
  function faceURL(league, row, faces) {
    if (typeof QB_STORE_APP !== "undefined" && QB_STORE_APP) return "";   // the store app draws no photos (boot.js)
    const own = row && row.name ? (faces || {})[lower(row.name)] : "";
    if (own) return own;
    const dir = FACE_DIR[league];
    return dir && row && row.id
      ? `https://a.espncdn.com/i/headshots/${dir}/players/full/${encodeURIComponent(row.id)}.png` : "";
  }
  /* The blank mark sits UNDER the photograph, so a face that fails to load
     (alt is empty, so nothing is drawn) leaves the mark showing — no inline
     handler, which the page's CSP forbids. */
  function faceHTML(league, row, faces) {
    const src = faceURL(league, row, faces);
    if (!src) return `<span class="gc-face">${icon("user", 16)}</span>`;
    /* AT THE SIZE IT IS DRAWN (the lag, 2026-10-09: "all the logos and
       headshots take a while to load"). ESPN's full headshot is about
       200 KB and the box score drew forty of them at 28px — megabytes of
       face on one tab. visuals.js `facePreview` asks ESPN's own resize for
       twice the drawn size; the full file is the first fallback
       (swapFull), and only a second miss leaves the mark showing. */
    const small = typeof facePreview === "function" ? facePreview(src, 40) : src;
    const fall = small !== src ? ` data-full="${escapeAttr(src)}" data-onerr="swapFull"` : "";
    return `<span class="gc-face">${icon("user", 16)}<img src="${escapeAttr(small)}" alt="" loading="lazy" decoding="async"${fall}></span>`;
  }

  /* ---------------- the box score, read ----------------
     The deep file's `box` is ESPN's own box score with its own column
     labels (livescore_build.pbp_doc → espnplays.summary_box): one entry
     per side, one group per table ("passing", "rushing", "defensive" …),
     each with its `labels` and its rows of stat strings. Nothing here
     knows what a column MEANS beyond its label — a line is "value label"
     under the group's labels, and a leader is the most of one column —
     so a group ESPN adds next week draws as a table on its own, and a
     column it renames reads under the new name. That is the same stance
     the Player stats room took with `marketWord`: the record's own
     vocabulary labels the numbers, never a mapping of ours. */
  const teamBox = (d, team) => (((d || {}).box || []).find((b) => b.team === team) || {}).groups || [];
  const col = (g, label) => (g.labels || []).findIndex((l) => String(l).toUpperCase() === String(label).toUpperCase());
  const cell = (g, row, label) => { const i = col(g, label); return i >= 0 ? (row.stats || [])[i] : undefined; };
  const rowOf = (g, name) => (g.rows || []).find((r) => lower(r.name) === lower(name)) || null;

  /* The columns a line is made of, per group, in ESPN's labels. "C/ATT"
     stands alone ("3/4"); everything else reads value then label ("26
     YDS"), and a zero is said ("0 TD") the way ESPN's chips say it. */
  const LINE_LABELS = {
    passing: ["C/ATT", "YDS", "TD", "INT"], rushing: ["CAR", "YDS", "TD"],
    receiving: ["REC", "YDS", "TD"], defensive: ["TOT", "SOLO", "SACKS"],
    interceptions: ["INT", "YDS", "TD"], kicking: ["FG", "XP", "PTS"], punting: ["NO", "AVG"],
    kickreturns: ["NO", "YDS", "TD"], puntreturns: ["NO", "YDS", "TD"], fumbles: ["FUM", "LOST"],
    goalies: ["SV", "GA"], skaters: ["G", "A", "SOG"],
  };
  const BARE = new Set(["C/ATT", "FG", "XP"]);
  function lineFor(g, row) {
    const want = LINE_LABELS[lower(g.name).replace(/\s+/g, "")] || (g.labels || []).slice(0, 3);
    const bits = [];
    want.forEach((label) => {
      const v = cell(g, row, label);
      if (v == null || v === "" || v === "--") return;
      bits.push(BARE.has(String(label).toUpperCase()) ? esc(v) : `${esc(v)} ${esc(label)}`);
    });
    return bits.join(", ");
  }
  /* A player's line so far, from the first group he has a row in — the
     group his role on the play points at first (a passer's passing line,
     a receiver's receiving line), the rest in the order a football reader
     expects. "" when the box has not seen him. */
  const ROLE_ORDER = {
    pass0: ["passing", "rushing", "receiving", "defensive"],
    pass1: ["receiving", "rushing", "passing", "defensive"],
    any: ["rushing", "receiving", "passing", "defensive", "interceptions", "kicking", "punting",
          "kickReturns", "puntReturns"],
  };
  function playerLine(d, name, role) {
    const groups = [...teamBox(d, d.away), ...teamBox(d, d.home)];
    const order = ROLE_ORDER[role] || ROLE_ORDER.any;
    const ranked = order.map((n) => groups.filter((g) => lower(g.name) === lower(n))).flat()
      .concat(groups.filter((g) => !order.some((n) => lower(n) === lower(g.name))));
    for (const g of ranked) {
      const r = rowOf(g, name);
      if (r) return { line: lineFor(g, r), row: r, group: g };
    }
    return { line: "", row: null, group: null };
  }
  const teamOf = (d, name) => (teamBox(d, d.away).some((g) => rowOf(g, name)) ? d.away
    : teamBox(d, d.home).some((g) => rowOf(g, name)) ? d.home : "");

  /* ---------------- the spot, in words ----------------
     ESPN writes "TB 4"; the deep file carries the yard as the site's own
     number, 0-100 from the home goal line (engine/models.py, the strip's
     convention — see pbpFieldPosHTML for why the raw `yardLine` is never
     drawn). The word is derived here once and used by the tiles and the
     last play alike, so the two can never disagree about which half of
     the field a number names. */
  /* `yard` counts up from the home goal line (engine/models.py): under
     fifty is home's half, over is away's, and the number a person says
     counts back from midfield — the strip's own arithmetic. */
  function spotWord(d, yard) {
    const y = Number(yard);
    if (!isFinite(y) || y < 0 || y > 100) return "";
    if (y === 50) return "50";
    const side = y < 50 ? (d.home || "") : (d.away || "");
    return `${side} ${Math.round(y > 50 ? 100 - y : y)}`.trim();
  }
  const downWord = (p) => p && p.down
    ? `${pbpOrd(Number(p.down))} & ${p.distance == null ? "?" : (Number(p.distance) === 0 ? "Goal" : p.distance)}` : "";

  /* ---------------- the drive in progress ----------------
     ESPN's card: the mark, "9 plays, 70 yards, 4:09", then DOWN and BALL
     ON. The drive comes from the summary's `drives.current`
     (espnplays.current_drive) when the builder saw one, and otherwise
     from the last drive on file while the game is live — a deep file
     written before `drive` existed still gets the card. The tiles read
     the SCOREBOARD's words for the next snap (`live.detail`, "2nd & Goal
     at TB 4"), split at " at " — not the last play's down, which is the
     snap that already happened. With no words, the ball-on tile falls
     back to the strip's own spot, and a tile with nothing is not drawn:
     a dash where ESPN has a number is the honest version of "we do not
     know", and two empty tiles are furniture. */
  function currentDrive(d) {
    const lv = d.live || {};
    if (d.drive && d.drive.team) return d.drive;
    const drives = d.drives || [];
    const last = drives[drives.length - 1];
    if (lv.state === "live" && last && last.team) {
      return { team: last.team, plays: last.offensive_plays || (last.plays || []).length,
               yards: last.yards || 0, elapsed: last.elapsed || "", period: last.period };
    }
    return null;
  }
  function driveWords(dr) {
    const n = Number(dr.plays || 0);
    return [`${n} play${n === 1 ? "" : "s"}`, `${Number(dr.yards || 0)} yard${Number(dr.yards) === 1 ? "" : "s"}`,
            dr.elapsed || ""].filter(Boolean).join(", ");
  }
  function currentDriveHTML(d, league, lastPlay) {
    const lv = d.live || {};
    const dr = currentDrive(d);
    if (!dr || lv.state !== "live") return "";
    // The drive on the field (below), between the head and the tiles.
    const fd = driveFieldHTML(d, league, dr);
    return `<div class="card gc-drive">
      <div class="gc-drive-head">${teamMarkIn(league, dr.team, 28)}
        <div><div class="gc-k">Current drive</div><b>${esc(driveWords(dr))}</b></div>
        <span class="gc-drive-end">${fd.rz ? `<span class="gc-rz">Red zone</span>` : ""}${dr.period ? `<span class="gc-q">Q${esc(dr.period)}</span>` : ""}${fd.html ? fd.replay : ""}</span></div>
      ${fd.html}</div>`;
  }

  /* ---------------- the drive on the field ----------------
     Ethan, 2026-10-15, with the hockey page open: "Are we able too do like
     a animation of a hockey puck moving back and forth across the ice …
     Also think and do any other ideas you have for the tracking of the
     live games for all sports." Football's is the drive tracker every
     broadcast draws: the field from above, each play of the drive in
     progress a bar from where it was snapped to where it ended, the ball
     running the drive play by play and coming to rest on the line of
     scrimmage, the line to gain in gold, the red zone lit once the offence
     is inside the twenty. The Play-by-play tab leads with the whole game
     the same way, a drive a row.

     EVERY MARK IS A NUMBER THE FILE HOLDS. A play starts at its snap
     (`spot`, 0-100 from the home goal line — espnplays._football_row) and
     runs its own `yards`; when the next snap is not where the play ended,
     a flag was walked off, and the difference is drawn dashed. The ball at
     rest is the scoreboard's `live.yard_line` and the line to gain its own
     words' distance ("2nd & 7"). A kickoff, a try or a timeout is not a
     snap at a line of scrimmage (a kickoff's spot is the kicking side's),
     so none is drawn; a drive with no spot draws no field, and the card is
     what it was. Where a pass was caught is not in the file, so a pass is
     an arc over the whole gain, not a throw and a run after it. */
  const NO_SNAP = /kickoff|extra point|two[- ]?point|2pt|conversion|timeout|end of|end period|coin toss|two[- ]minute|warning/i;
  //: [kind, word]: how a snap is drawn, and what the field calls it.
  function snapKind(p) {
    const e = String(p.event || "");
    if (/field goal/i.test(e)) return /good/i.test(e) && !/no good/i.test(e) ? ["fg", "FG"] : ["kick", "NO GOOD"];
    if (/punt/i.test(e)) return ["kick", "PUNT"];
    if (/interception/i.test(e)) return ["to", "INT"];
    if (p.turnover) return ["to", /fumble/i.test(e) ? "FUM" : "TURNOVER"];
    if (/safety/i.test(e)) return ["loss", "SAFETY"];
    if (/sack/i.test(e)) return ["loss", "SACK"];
    if (/incompl/i.test(e)) return ["inc", "INC"];
    if (/penalty/i.test(e)) return ["flag", "FLAG"];
    if (/pass|reception/i.test(e)) return ["pass", "PASS"];
    return ["run", "RUN"];
  }
  const ydClamp = (v) => Math.max(0, Math.min(100, v));
  /* A drive's snaps as the field draws them: from, to, the flag's walk
     (`ext`), the word. Home drives toward 100, away toward 0. */
  function driveRows(d, dr) {
    const dir = dr && dr.team === d.home ? 1 : dr && dr.team === d.away ? -1 : 0;
    if (!dir) return [];
    const snaps = (dr.plays || []).filter((p) => p && p.kind === "football" && p.spot != null && isFinite(Number(p.spot))
      && Number(p.spot) >= 0 && Number(p.spot) <= 100 && !NO_SNAP.test(String(p.event || "")));
    return snaps.map((p, i) => {
      const [k0, word] = snapKind(p);
      const from = Number(p.spot), gain = Number(p.yards) || 0;
      const air = k0 === "pass";
      const td = !!p.scoring && (k0 === "run" || k0 === "pass");
      const kind = td ? "td" : (k0 === "run" || k0 === "pass") && gain < 0 ? "loss" : k0;
      const stays = kind === "kick" || kind === "fg" || kind === "to" || kind === "inc";
      const to = td ? (dir > 0 ? 100 : 0) : stays ? from : ydClamp(from + gain * dir);
      const next = snaps[i + 1] ? Number(snaps[i + 1].spot) : null;
      const ext = next != null && kind !== "kick" && kind !== "fg" && kind !== "to" && !td && Math.abs(next - to) >= 2 ? next : null;
      const n = Math.round((to - from) * dir);
      const label = td ? (n > 0 ? `+${n} TD` : "TD") : stays ? word : `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)} ${word}`;
      // A punt flies its own yards when they read as a punt's; a kick at the posts flies to them.
      // A punt's `yards` is its RETURN (a real game read 2026-10-25: −3, 0,
      // 20), so it is not drawn as a flight of that length; it sits at its
      // spot like any kick whose distance the file does not hold.
      const fly = kind === "fg" || word === "NO GOOD" ? (dir > 0 ? 110 : -10) : null;
      // The down and the distance it was snapped on: the photograph draws
      // each snap's own line to gain.
      const at = (v) => (v != null && isFinite(Number(v)) ? Number(v) : null);
      return { id: String(p.id || i), kind, word, label, from, to, ext, fly, dir, air, period: p.period,
               down: at(p.down), togo: at(p.distance) };
    });
  }
  /* How long each part of a snap takes. One table for the card's field and
     the photograph, so the ball reaches every play's end on both at the
     same moment: the card's drop to the next row is the photograph's cut
     to the next snap (out, across, in: twice 0.2 and 0.01). */
  const SNAP = { leg: 0.41, hold: 0.12 }, EXT = { leg: 0.35, hold: 0.2 };
  function beat(r) {
    if (r.fly != null) return { leg: 0.85, hold: 0.35, how: "fly" };
    if (r.kind === "inc" || r.kind === "to") return { leg: 0.45, hold: 0.25, how: "hop" };
    if (r.to !== r.from) return { leg: Math.min(1.1, Math.max(0.35, Math.abs(r.to - r.from) / 40)), hold: 0.3, how: "move" };
    return { leg: 0.05, hold: 0.35, how: "stay" };
  }
  //: The scoreboard's next snap: the line of scrimmage, the line to gain
  //: ("& Goal" is the goal line itself) and the words for it.
  function nextSnap(d, dir) {
    const lv = d.live || {};
    const los = Number(lv.yard_line);
    if (lv.yard_line == null || !isFinite(los) || los < 0 || los > 100) return null;
    const m = /^(.*?)\s+at\s+/.exec(String(lv.detail || ""));
    const words = m ? m[1].trim() : "";
    const g = /&\s*(goal|\d+)/i.exec(words);
    const goal = !!(g && /goal/i.test(g[1]));
    const gain = g && !goal && dir ? ydClamp(los + dir * Number(g[1])) : null;
    return { los, gain, goal, words };
  }
  /* Each side's colour on the turf: the club's first colour with some hue
     to it (black or silver says nothing on dark grass), the away side
     taking another of its own when the two would look alike. The
     stylesheet mixes it toward the page's text, so a navy still reads. */
  const hexRGB = (h) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(h || "").trim()); if (!m) return null; const n = parseInt(m[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
  const rgbHex = (c) => "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  function fieldColours(d, league) {
    const table = typeof teamsForSport === "function" ? (teamsForSport(league) || {}) : {};
    const hues = (abbr) => { const t = table[abbr] || {}; return [t.primary, t.secondary, t.tertiary].map(hexRGB).filter((c) => c && Math.max(...c) - Math.min(...c) >= 40); };
    const far = (a, b) => !a || !b || Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) >= 90;
    const hs = hues(d.home), as = hues(d.away);
    const home = hs[0] || null, away = as.find((c) => far(c, home)) || as[0] || null;
    return { home: home ? rgbHex(home) : "", away: away ? rgbHex(away) : "" };
  }
  /* Two drawings of one field, the narrow one for a phone — the words on
     a field drawn for a desktop would be six pixels high on a phone — and
     the card shows the one that fits it (gamecast.css, a container query). */
  const FIELD = {
    wide: { U: 5.4, row: 24, top: 22, gut: 0, fs: 13, ball: [8.6, 5.4] },
    narrow: { U: 3, row: 21, top: 18, gut: 0, fs: 11, ball: [7.2, 4.6] },
  };
  const f1 = (v) => Number(v).toFixed(1);
  function fieldSVG(g, cls, d, cols, rowsN, body, label, opts) {
    const o = opts || {};
    const X = (y) => g.gut + (y + 10) * g.U, W = g.gut + 120 * g.U, H = g.top + rowsN * g.row + 6;
    let mow = "", five = "", ten = "", nums = "";
    for (let k = 1; k < 10; k += 2) mow += `<rect class="gc-fd-mow" x="${f1(X(k * 10))}" y="0" width="${f1(10 * g.U)}" height="${H}"/>`;
    for (let y = 5; y < 100; y += 5) {
      if (y % 10) five += `M${f1(X(y))} ${g.top - 3}V${H}`; else ten += `M${f1(X(y))} ${g.top - 3}V${H}`;
    }
    for (let y = 10; y < 100; y += 10) nums += `<text class="gc-fd-num" x="${f1(X(y))}" y="${g.top - 7}">${y > 50 ? 100 - y : y}</text>`;
    const ez = (side, x0) => {
      const cx = x0 + 5 * g.U, cy = H / 2, c = cols[side];
      // A chart whose rows fill the field names the end zones over it, in the
      // numbers' band, so a row's words never sit on a name.
      const name = o.band ? `<text class="gc-fd-ezt band" x="${f1(cx)}" y="${g.top - 7}">${esc(d[side] || "")}</text>`
        : `<text class="gc-fd-ezt" x="${f1(cx)}" y="${f1(cy)}" transform="rotate(${side === "home" ? -90 : 90} ${f1(cx)} ${f1(cy)})">${esc(d[side] || "")}</text>`;
      return `<rect class="gc-fd-ez" x="${f1(x0)}" y="0" width="${f1(10 * g.U)}" height="${H}"${c ? ` style="--tm:${c}"` : ""}/>${name}`;
    };
    return `<svg class="gc-fd-svg ${cls}" viewBox="0 0 ${f1(W)} ${H}" role="img" aria-label="${escapeAttr(label)}"${o.tm ? ` style="--tm:${o.tm}"` : ""}>`
      + `<rect class="gc-fd-turf" x="${f1(X(0))}" y="0" width="${f1(100 * g.U)}" height="${H}"/>${mow}${ez("home", X(-10))}${ez("away", X(100))}`
      + `<path class="gc-fd-yl" d="${five}"/><path class="gc-fd-yl ten" d="${ten}"/>`
      + `<path class="gc-fd-goal" d="M${f1(X(0))} 0V${H}M${f1(X(100))} 0V${H}"/>${nums}${body}</svg>`;
  }
  const ballSVG = (g, x, y, motion) => {
    const [rx, ry] = g.ball;
    return `<g class="gc-fd-ball" transform="translate(${f1(x)} ${f1(y)})"><ellipse class="glow" rx="${f1(rx * 1.9)}" ry="${f1(rx * 1.5)}"/>`
      + `<ellipse class="skin" rx="${rx}" ry="${ry}"/><path class="lace" d="M${f1(-rx * 0.45)} 0H${f1(rx * 0.45)}M${f1(-rx * 0.22)} ${f1(-ry * 0.38)}v${f1(ry * 0.76)}M0 ${f1(-ry * 0.38)}v${f1(ry * 0.76)}M${f1(rx * 0.22)} ${f1(-ry * 0.38)}v${f1(ry * 0.76)}"/>${motion || ""}</g>`;
  };
  /* Where a row's words go: past the far end of what it drew in the
     direction of the drive, or before its start when that runs off the
     field. */
  function labelAt(g, r, text) {
    const X = (y) => g.gut + (y + 10) * g.U;
    const ys = [r.from, r.to, r.ext, r.fly].filter((v) => v != null);
    // The cross an incompletion or a turnover draws just past the snap.
    if (r.kind === "inc" || r.kind === "to") ys.push(r.from + r.dir * (g.row * 0.7) / g.U);
    const lo = Math.min(...ys), hi = Math.max(...ys), w = text.length * g.fs * 0.62, pad = g.fs * 0.7;
    const ahead = r.dir > 0 ? X(hi) + pad : X(lo) - pad;
    // In front when it fits before the goal line; behind the start when not.
    const fits = r.dir > 0 ? ahead + w <= X(100) - 2 : ahead - w >= X(0) + 2;
    if (r.fly != null) return { x: X(r.from) - r.dir * pad, anchor: r.dir > 0 ? "end" : "start" };
    if (fits) return { x: ahead, anchor: r.dir > 0 ? "start" : "end" };
    return { x: r.dir > 0 ? X(lo) - pad : X(hi) + pad, anchor: r.dir > 0 ? "end" : "start" };
  }
  /* The run's bookkeeping, as on the hockey and basketball pages: a first
     look runs the newest plays, a new play runs from the last one seen,
     Replay runs them all again, and the redraw every few seconds carries
     on from where the run is rather than starting over. */
  const DRIVE_RUN = 6, DRIVE_ROWS = 12;
  let _run = null, _replay = false, _last = null;
  function driveRun(d, end, ids) {
    const now = Date.now(), r = _run, game = String(d.event_id || "");
    if (_replay || !r || r.game !== game) _run = { game, upto: end, from: null, start: now };
    else if (r.upto !== end) {
      const prev = String(r.upto).split("|")[0];
      _run = { game, upto: end, from: ids.includes(prev) ? prev : null, start: now };
    }
    _replay = false;
    return { from: _run.from, elapsed: (now - _run.start) / 1000 };
  }
  function trackerBody(g, m, run) {
    const { rows, nx, startAt } = m;
    const X = (y) => g.gut + (y + 10) * g.U, Y = (i) => g.top + i * g.row + g.row / 2;
    const n = rows.length, H = g.top + (n + (nx ? 1 : 0)) * g.row + 6;
    // The run: the ball from the first new snap through every play after
    // it, down to the line of scrimmage.
    const pts = [];
    rows.forEach((r, i) => {
      if (i < startAt) return;
      const y = Y(i), x0 = X(r.from), bt = beat(r);
      pts.push({ x: x0, y, leg: SNAP.leg, hold: SNAP.hold, i, at: "snap" });
      if (bt.how === "fly") {
        const x1 = X(r.fly);
        pts.push({ x: x1, y, leg: bt.leg, hold: bt.hold, via: [(x0 + x1) / 2, y - g.row * 1.6], i, at: "end" });
      } else if (bt.how === "hop") {
        pts.push({ x: x0, y, leg: bt.leg, hold: bt.hold, via: [x0 + r.dir * 4 * g.U, y - g.row * 0.9], i, at: "end" });
      } else if (bt.how === "move") {
        const x1 = X(r.to);
        pts.push({ x: x1, y, leg: bt.leg, hold: bt.hold, via: r.air ? [(x0 + x1) / 2, y - g.row * 1.15] : null, i, at: "end" });
      } else {
        pts.push({ x: x0, y, leg: bt.leg, hold: bt.hold, i, at: "end" });
      }
      if (r.ext != null) pts.push({ x: X(r.ext), y, leg: EXT.leg, hold: EXT.hold, i, at: "ext" });
    });
    if (nx) pts.push({ x: X(nx.los), y: Y(n), leg: SNAP.leg, hold: SNAP.hold, i: n, at: "now" });
    const T = track(pts, { elapsed: run.elapsed });
    const moving = !T.still;
    const ix = (i, at) => pts.findIndex((p) => p.i === i && p.at === at);
    const arrive = (i, at) => { const k = ix(i, at); return moving && k > 0 ? T.at[k] : null; };
    const leave = (i, at) => { const k = ix(i, at); return moving && k > 0 ? T.go[k] : null; };
    const pop = (t, inner) => (t == null || T.past(t) ? inner
      : `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.2s" begin="${T.begin(t)}" fill="freeze"/>${inner}</g>`);
    // A line drawn whole once the ball is past it, and drawing itself
    // behind the ball while it is on it (from where it is now, after a redraw).
    const reveal = (x1, x2, y, t0, t1, cls) => {
      const len = Math.abs(x2 - x1);
      const on = t0 != null && t1 != null && !T.past(t1);
      const left = on ? len * Math.min(1, (t1 - Math.max(t0, T.elapsed)) / Math.max(0.01, t1 - t0)) : 0;
      // The gap a little longer than the line, so the next dash's round cap
      // never dots the far end before the ball gets there.
      const draw = on ? ` stroke-dasharray="${f1(len)} ${f1(len + 2)}" stroke-dashoffset="${f1(left)}"` : "";
      const anim = on ? `<animate attributeName="stroke-dashoffset" from="${f1(left)}" to="0" begin="${T.begin(t0)}" dur="${Math.max(0.05, t1 - Math.max(t0, T.elapsed)).toFixed(2)}s" fill="freeze"/>` : "";
      return pop(on ? t0 : null, `<line class="gc-fd-halo" x1="${f1(x1)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y)}"${draw}>${anim}</line>`
        + `<line class="${cls}" x1="${f1(x1)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y)}"${draw}>${anim}</line>`);
    };
    const head = (x, y, s, kind) => {
      const h = g.row * 0.26;
      return `<path class="gc-fd-head ${kind}" d="M${f1(x + s * h * 0.9)} ${f1(y)}L${f1(x - s * h * 0.5)} ${f1(y - h)}V${f1(y + h)}Z"/>`;
    };
    const cross = (x, y, cls) => { const r = g.row * 0.2; return `<path class="gc-fd-x ${cls}" d="M${f1(x - r)} ${f1(y - r)}l${f1(2 * r)} ${f1(2 * r)}m0 ${f1(-2 * r)}l${f1(-2 * r)} ${f1(2 * r)}"/>`; };
    let marks = "";
    rows.forEach((r, i) => {
      const y = Y(i), x0 = X(r.from), x1 = X(r.to);
      const t0 = leave(i, "end"), t1 = arrive(i, "end");
      const lastAt = r.ext != null ? arrive(i, "ext") : t1;
      let out = pop(arrive(i, "snap"), `<circle class="gc-fd-snap" cx="${f1(x0)}" cy="${f1(y)}" r="${f1(g.row * 0.14)}"/>`);
      if (r.fly != null) {
        const x2 = X(r.fly), up = y - g.row * 1.6;
        out += pop(t1, `<path class="gc-fd-kick" d="M${f1(x0)} ${f1(y)}Q${f1((x0 + x2) / 2)} ${f1(up)} ${f1(x2)} ${f1(y)}"/>`);
      } else if (r.kind === "inc" || r.kind === "to") {
        out += pop(t1, cross(x0 + r.dir * g.row * 0.45, y, r.kind));
      } else if (x1 !== x0) {
        const s = x1 > x0 ? 1 : -1;
        out += r.kind === "flag" ? pop(t0, `<line class="gc-fd-bar flag" x1="${f1(x0)}" y1="${f1(y)}" x2="${f1(x1)}" y2="${f1(y)}"/>`)
          : reveal(x0, x1, y, t0, t1, `gc-fd-bar ${r.kind}`);
        out += pop(t1, head(x1, y, s, r.kind));
      }
      if (r.ext != null) {
        const tx = arrive(i, "ext");
        out += pop(leave(i, "ext"), `<line class="gc-fd-ext" x1="${f1(x1)}" y1="${f1(y)}" x2="${f1(X(r.ext))}" y2="${f1(y)}"/>`);
        out += pop(tx, `<circle class="gc-fd-flag" cx="${f1(X(r.ext))}" cy="${f1(y)}" r="${f1(g.row * 0.16)}"/>`);
      }
      const at = labelAt(g, r, r.label);
      out += pop(lastAt, `<text class="gc-fd-lbl ${r.kind}" x="${f1(at.x)}" y="${f1(y + g.fs * 0.36)}" text-anchor="${at.anchor}">${esc(r.label)}</text>`);
      marks += out;
    });
    // The next snap: the line of scrimmage, the line to gain, the red zone
    // once the offence is inside the twenty, and the down beside the ball.
    let lines = "", words = "";
    const last = rows[n - 1];
    const dir = last.dir;
    if (nx) {
      const top = g.top - 3, xl = X(nx.los);
      const rz = dir > 0 ? nx.los >= 80 : nx.los <= 20;
      if (rz) lines += `<rect class="gc-fd-rz" x="${f1(dir > 0 ? X(80) : X(0))}" y="${top}" width="${f1(20 * g.U)}" height="${H - top}"/>`;
      lines += `<line class="gc-fd-lh los" x1="${f1(xl)}" y1="${top}" x2="${f1(xl)}" y2="${H}"/><line class="gc-fd-los" x1="${f1(xl)}" y1="${top}" x2="${f1(xl)}" y2="${H}"/>`;
      if (nx.gain != null && nx.gain > 0 && nx.gain < 100) {
        const xg = X(nx.gain);
        lines += `<line class="gc-fd-lh gain" x1="${f1(xg)}" y1="${top}" x2="${f1(xg)}" y2="${H}"/><line class="gc-fd-gain" x1="${f1(xg)}" y1="${top}" x2="${f1(xg)}" y2="${H}"/>`;
      }
      if (nx.words) {
        const w = nx.words.length * g.fs * 0.62, back = xl - dir * (g.ball[0] + g.fs * 0.8);
        const fits = dir > 0 ? back - w >= X(-10) + 2 : back + w <= X(110) - 2;
        const x = fits ? back : xl + dir * (g.ball[0] + g.fs * 0.8);
        const anchor = (dir > 0) === fits ? "end" : "start";
        words = pop(arrive(n, "now"), `<text class="gc-fd-dn" x="${f1(x)}" y="${f1(Y(n) + g.fs * 0.36)}" text-anchor="${anchor}">${esc(nx.words)}</text>`);
      }
    }
    // The ball, on top: at rest on the line of scrimmage while the drive is
    // on, or where the last play left it.
    const rest = nx ? [X(nx.los), Y(n)] : (() => {
      const r = last; return [X(r.fly != null ? r.fly : r.ext != null ? r.ext : r.to), Y(n - 1)];
    })();
    const ring = nx ? pop(moving ? T.dur : null, `<circle class="gc-fd-ring" cx="${f1(rest[0])}" cy="${f1(rest[1])}" r="${f1(g.ball[0] * 1.6)}"/>`) : "";
    return { body: `${lines}${marks}${words}${ring}${ballSVG(g, rest[0], rest[1], moving ? T.motion : "")}`, moving };
  }
  /* The drive both drawings run: the last drive on file, its last
     DRIVE_ROWS snaps, the next snap while the scoreboard is still on it,
     and where the run is. One clock for the card and the photograph. */
  function driveModel(d) {
    const drives = d.drives || [];
    const last = drives[drives.length - 1];
    if (!last) return null;
    const all = driveRows(d, last);
    if (!all.length) return null;
    const rows = all.slice(-DRIVE_ROWS);
    const lv = d.live || {};
    const dir = rows[0].dir;
    const nx = lv.state === "live" && !last.result && (!lv.possession || lv.possession === last.team) ? nextSnap(d, dir) : null;
    const ids = rows.map((r) => r.id);
    const run = driveRun(d, `${ids[ids.length - 1]}|${nx ? nx.los : ""}`, ids);
    const seen = run.from != null ? ids.indexOf(run.from) : -1;
    const startAt = seen >= 0 ? seen + 1 : Math.max(0, rows.length - DRIVE_RUN);
    return { last, all, rows, nx, dir, run, startAt };
  }
  /* The tracker for the Gamecast tab's drive card: the drive on file that
     the scoreboard's drive belongs to, its last DRIVE_ROWS snaps. Empty
     when no snap of it has a spot. */
  function driveFieldHTML(d, league, dr) {
    const md = driveModel(d);
    if (!md || !dr || md.last.team !== dr.team) return { html: "", rz: false, replay: "" };
    const { all, rows, nx, dir, run, startAt } = md;
    _last = { d, league, dr };
    const cols = fieldColours(d, league);
    const m = { rows, nx, startAt };
    const label = `${dr.team} drive: ${rows.map((r) => r.label).join(", ")}${nx && nx.words ? `; ${nx.words} next` : ""}`;
    let moving = false;
    const svgs = Object.entries(FIELD).map(([cls, g]) => {
      const t = trackerBody(g, m, run);
      moving = moving || t.moving;
      return fieldSVG(g, cls, d, cols, rows.length + (nx ? 1 : 0), t.body, label, { tm: cols[dir > 0 ? "home" : "away"] });
    }).join("");
    const rz = !!nx && (dir > 0 ? nx.los >= 80 : nx.los <= 20);
    const replay = `<button type="button" class="gc-replay" data-gc-replay aria-label="Replay the drive">${REPLAY}</button>`;
    const more = all.length > rows.length ? `<span>${all.length - rows.length} earlier play${all.length - rows.length === 1 ? "" : "s"} not drawn</span>` : "";
    return {
      html: `<div class="gc-fd" data-gc-fd>${svgs}</div>
        <div class="gc-fd-key"><span class="los">Line of scrimmage</span>${nx && nx.gain != null ? `<span class="gain">Line to gain</span>` : ""}${more}</div>`,
      rz, replay,
    };
  }
  const REPLAY = `<svg class="ic" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3.2 8a4.8 4.8 0 1 0 1.4-3.4"/><path d="M3 2.6v3h3"/></svg>`;
  /* Replay redraws in place everything that runs the same clock — the
     card's field and the photograph's drawing, or the zone and the
     photograph's pitches — so the two start together again. The page's own
     redraw would come round in a few seconds anyway, and the click is the
     module's to take (no inline handler under the page's CSP). */
  const swap = (sel, html) => {
    const box = document.querySelector(sel);
    if (!box || !html) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    const next = tmp.querySelector(sel);
    if (next) box.replaceWith(next);
  };
  const reArt = () => { if (_artLast) swap("[data-gc-art]", art(_artLast.d, _artLast.league, _artLast.hit, _artLast.game)); };
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("click", (e) => {
      const z = e.target && e.target.closest ? e.target.closest("[data-gc-pz-replay]") : null;
      if (z) {
        _pzReplay = true;
        if (_pzLast) swap("[data-gc-pz]", zone(_pzLast));
        reArt();
        _pzReplay = false;
        return;
      }
      const b = e.target && e.target.closest ? e.target.closest("[data-gc-replay]") : null;
      if (!b) return;
      _replay = true;
      if (_last) swap(".gc-drive [data-gc-fd]", driveFieldHTML(_last.d, _last.league, _last.dr).html);
      reArt();
      _replay = false;
    });
  }

  /* ---------------- on Ethan's photographs ----------------
     Ethan, 2026-10-15: "are we still using all our renders I've been giving
     you for the stadium art … All the animations should work flawlessly
     with the stadium art and field art and shit we already have." So the
     drive and the at-bat run on his photographs as well as on the cards,
     on one clock with them: the field render cuts to each snap of the
     drive the card is running, and the ballpark render throws each pitch
     the zone is drawing, at the same moment. app.js asks for the drawing
     (`art`) and keeps its own single play or batted ball when there is
     none. A photograph is a night game in either theme, so what is drawn
     on it keeps its own colours (gamecast.css, `.gc-art`).

     THE FIELD'S CAMERA IS MEASURED. The render is a broadcast angle from
     behind the offence, the ball on its own 30 under the centre. Fifteen
     painted five-yard lines, found by their brightness down the photograph
     (scratch: fieldcal), fit `y = A + B / (yards + C)` — the shape a lens
     gives a flat field — pinned at the painted line the ball sits on: from
     there to forty yards on, no drawn yard is more than 0.6 of a unit
     (about a fifth of a yard at the line) off a painted one, so a ten-yard
     gain ends on the painted line ten yards on. Behind the line it is 2.9
     units a yard, straight, through the painted line five yards back. All
     four frames share it: the away frame's lines sit within a unit of the
     home frame's, and the college pair is the home pair's to a tenth.

     IT IS THE CAMERA THAT MOVES. The players are pixels and stand where
     they stand, so every snap is drawn from their line: the painted
     numbers are not the field position (the strip under the photograph
     and the card's field are), but a play's length is real — it is
     measured against lines that really are that far apart.

     Where across the field a play went is not in the file, so the ball
     goes straight down the field from the centre. A pass rises over its
     gain (height, not a direction); a field goal climbs to the posts in the
     picture, a punt drops where its yards say; an incompletion and a
     turnover hop back to the line with a cross. The next snap ends the run:
     the line of scrimmage blue, the line to gain gold (a white goal line
     when it is "& Goal"), the down beside the ball. */
  const CAM = { A: 37.775, B: 2279.86, C: 29.37, los: 115.4, back: 2.9, vx: 120, ball: [117.6, 117.4],
                qb: 131, hold: 135.7, punt: 146, posts: [119.8, 47], bar: 54.5 };
  const artY = (yd) => (yd < 0 ? Math.min(146, CAM.los - CAM.back * yd) : Math.max(57, CAM.A + CAM.B / (yd + CAM.C)));
  const artS = (y) => (y - CAM.A) / (CAM.los - CAM.A);                    // size, against the line of scrimmage
  const artX = (y) => CAM.vx + (CAM.ball[0] - CAM.vx) * artS(y);          // the ball's line, to the far end
  const sz = (y) => Math.max(0.42, Math.min(1.4, artS(y)));
  // A line across the field: sideline to sideline (measured off the same
  // photograph), or the picture's edge where the field runs past it.
  const across = (y, cls) => {
    const half = 2.952 * (y - 42.35);
    return `<line class="${cls}" x1="${f1(Math.max(0, 120 - half))}" y1="${f1(y)}" x2="${f1(Math.min(240, 120 + half))}" y2="${f1(y)}"`
      + ` stroke-width="${(1.15 * Math.max(0.45, artS(y))).toFixed(2)}"/>`;
  };
  //: A caption beside a mark: up and to the right, flipped left at the
  //: edge, dropped below where there is no sky (app.js pbpCalloutBox's rule).
  function chipAt(L, cw, ch) {
    let x = L[0] + 7;
    if (x + cw > 236) x = L[0] - cw - 7;
    let y = L[1] - ch - 6;
    if (y < 4) y = L[1] + 6;
    return [Math.max(4, Math.min(236 - cw, x)), Math.max(4, Math.min(146 - ch, y))];
  }
  function chip(L, title, detail) {
    const cw = Math.max(34, Math.min(110, 10 + Math.max(title.length * 3.45, detail.length * 2.75)));
    const ch = detail ? 17 : 11;
    const [x, y] = chipAt(L, cw, ch);
    return `<g class="gc-art-chip"><rect x="${f1(x)}" y="${f1(y)}" width="${f1(cw)}" height="${ch}" rx="2.6"/>`
      + `<text class="t" x="${f1(x + 4.5)}" y="${f1(y + 7.3)}">${esc(title)}</text>`
      + (detail ? `<text class="s" x="${f1(x + 4.5)}" y="${f1(y + 13.6)}">${esc(detail)}</text>` : "") + `</g>`;
  }
  const rings = (L, s) => `<circle class="gc-art-mark" cx="${f1(L[0])}" cy="${f1(L[1])}" r="${f1(6.4 * s)}" stroke-width=".7" opacity=".45"/>`
    + `<circle class="gc-art-mark" cx="${f1(L[0])}" cy="${f1(L[1])}" r="${f1(3.6 * s)}" stroke-width="1"/>`;
  const crossAt = (L, s) => { const k = 2.4 * s; return `<path class="gc-art-x" d="M${f1(L[0] - k)} ${f1(L[1] - k)}l${f1(2 * k)} ${f1(2 * k)}m0 ${f1(-2 * k)}l${f1(-2 * k)} ${f1(2 * k)}"/>`; };
  const artBall = (x, y, s, motion) => `<g class="gc-art-ball" transform="translate(${f1(x)} ${f1(y)}) scale(${s.toFixed(3)})">`
    + `<circle class="glow" r="4.2"/><ellipse class="skin" rx="2.1" ry="1.6"/>${motion || ""}</g>`;
  /* One snap on the photograph: where the ball goes first (back to the
     passer, the holder or the punter), where it ends, the arc's control
     point, a flag's walk after it, the line it was snapped to gain. */
  function artPlay(r) {
    const yd = (v) => (v - r.from) * r.dir;
    const ytg = r.dir > 0 ? 100 - r.from : r.from;
    const bt = beat(r), on = (y) => [artX(y), y];
    let pre = null, to = CAM.ball, via = null;
    if (bt.how === "fly") {
      const posts = r.kind === "fg" || r.word === "NO GOOD";
      pre = [CAM.ball[0], posts ? CAM.hold : CAM.punt];
      to = posts ? (r.kind === "fg" ? CAM.posts : [CAM.posts[0], CAM.bar]) : on(artY(yd(r.fly)));
      via = [(pre[0] + to[0]) / 2, Math.max(4, to[1] - (posts ? 43 : 45))];
    } else if (bt.how === "hop") {
      pre = [CAM.ball[0], CAM.qb];
      to = [CAM.ball[0], CAM.los];
      via = [CAM.ball[0], CAM.los - 14];
    } else if (bt.how === "move") {
      const g = r.kind === "td" ? ytg : yd(r.to);
      to = on(artY(g));
      if (r.kind !== "flag") pre = [CAM.ball[0], CAM.qb];
      if (r.air && g > 0) via = [(CAM.ball[0] + to[0]) / 2, to[1] - Math.min(40, 18 + g)];
    }
    const goalToGo = r.togo != null && r.togo >= ytg;
    return {
      bt, pre, to, via, ytg,
      ext: r.ext != null ? on(artY(yd(r.ext))) : null,
      gain: r.togo != null && r.togo > 0 && !goalToGo ? artY(r.togo) : null,
      goal: (goalToGo || r.kind === "td") && ytg <= 70 ? artY(ytg) : null,
      words: r.down ? downWord({ down: r.down, distance: goalToGo ? 0 : r.togo }) : "",
    };
  }
  function driveArt(d, league, hitRow) {
    const md = driveModel(d);
    if (!md) return null;
    const lv = d.live || {};
    // The frame app.js draws (pbpFieldHTML): the away side's ball is the
    // away frame, anything else the home one. A drive that is not the
    // frame's offence is not drawn over it.
    const who = (hitRow && hitRow.team) || lv.possession || "";
    if (md.last.team !== (who && who === d.away ? d.away : d.home)) return null;
    const { rows, nx, dir, run, startAt } = md;
    const plan = [], pts = [];
    rows.forEach((r, i) => {
      if (i < startAt) return;
      const p = artPlay(r);
      plan.push({ i, r, p });
      pts.push({ x: CAM.ball[0], y: CAM.ball[1], size: 1, jump: true, hold: SNAP.hold, i, at: "snap" });
      const lead = !p.pre ? 0 : p.bt.how === "fly" ? 0.2 : 0.16;
      if (p.pre) pts.push({ x: p.pre[0], y: p.pre[1], size: sz(p.pre[1]), leg: lead, hold: 0, i, at: "pre" });
      pts.push({ x: p.to[0], y: p.to[1], size: sz(p.to[1]), leg: p.bt.leg - lead, hold: p.bt.hold, via: p.via, i, at: "end" });
      if (p.ext) pts.push({ x: p.ext[0], y: p.ext[1], size: sz(p.ext[1]), leg: EXT.leg, hold: EXT.hold, i, at: "ext" });
    });
    if (nx) pts.push({ x: CAM.ball[0], y: CAM.ball[1], size: 1, jump: true, hold: SNAP.hold, i: rows.length, at: "now" });
    const T = track(pts, { elapsed: run.elapsed });
    const moving = !T.still;
    const k = (i, at) => pts.findIndex((q) => q.i === i && q.at === at);
    const arrive = (i, at) => { const n = k(i, at); return n >= 0 ? T.at[n] : null; };
    const leave = (i, at) => { const n = k(i, at); return n >= 0 ? T.go[n] : null; };
    // Shown from t0 to t1 (seconds into the run; null, from the start or to
    // the end), fading in and out as the camera cuts.
    const win = (t0, t1, inner) => {
      if (!inner || (t1 != null && T.past(t1 + 0.2))) return "";
      const on = t0 == null || T.past(t0);
      const a = (on ? "" : `<animate attributeName="opacity" from="0" to="1" dur="0.2s" begin="${T.begin(t0)}" fill="freeze"/>`)
        + (t1 != null ? `<animate attributeName="opacity" to="0" dur="0.2s" begin="${T.begin(t1)}" fill="freeze"/>` : "");
      return a ? `<g opacity="${on ? 1 : 0}">${a}${inner}</g>` : inner;
    };
    // The play's line along the ground, drawn behind the ball as it goes.
    const bar = (a, b, kind, t0, t1) => {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (len < 0.5) return "";
      const on = moving && t0 != null && t1 != null && !T.past(t1) && kind !== "flag" && kind !== "loss";
      const left = on ? len * Math.min(1, (t1 - Math.max(t0, T.elapsed)) / Math.max(0.01, t1 - t0)) : 0;
      const draw = on ? ` stroke-dasharray="${f1(len)} ${f1(len + 2)}" stroke-dashoffset="${f1(left)}"` : "";
      const anim = on ? `<animate attributeName="stroke-dashoffset" from="${f1(left)}" to="0" begin="${T.begin(t0)}" dur="${Math.max(0.05, t1 - Math.max(t0, T.elapsed)).toFixed(2)}s" fill="freeze"/>` : "";
      const seg = (cls) => `<line class="${cls}" x1="${f1(a[0])}" y1="${f1(a[1])}" x2="${f1(b[0])}" y2="${f1(b[1])}"${draw}>${anim}</line>`;
      return seg("gc-art-halo") + seg(`gc-art-bar ${kind}`);
    };
    // A play's marks: everything but the line to gain, each from when the
    // ball gets to it (all of them at once on a drawing at rest). A cross
    // goes over the ball, which comes to rest on it.
    const marks = (e, show) => {
      const { r, p, i } = e;
      const los = [artX(CAM.los), CAM.los];
      const t1 = arrive(i, "end"), lastAt = p.ext ? arrive(i, "ext") : t1;
      let out = "", over = "";
      if (p.bt.how === "fly") {
        const from = p.pre || CAM.ball;
        out += show(t1, `<path class="gc-art-kick" d="M${f1(from[0])} ${f1(from[1])}Q${f1(p.via[0])} ${f1(p.via[1])} ${f1(p.to[0])} ${f1(p.to[1])}"/>`)
          + (r.word === "NO GOOD" ? "" : show(t1, rings(p.to, sz(p.to[1]))));
        if (r.word === "NO GOOD") over += show(t1, crossAt(p.to, 0.8));
      } else if (p.bt.how === "hop") {
        over += show(t1, crossAt(p.to, 1));
      } else if (p.bt.how === "move") {
        // From the line (or the snap, for a flag) to where the play ended;
        // drawn as the ball crosses the line, or whole on arrival for a loss.
        const a = r.kind === "flag" ? CAM.ball : los;
        const t0 = leave(i, "end");
        const cross = t0 != null && t1 != null && p.pre ? t0 + (t1 - t0) * Math.max(0, Math.min(1, (p.pre[1] - CAM.los) / Math.max(1, p.pre[1] - p.to[1]))) : t0;
        out += show(r.kind === "flag" ? t0 : r.kind === "loss" ? t1 : cross, bar(a, p.to, r.kind, cross, t1))
          + show(t1, rings(p.to, sz(p.to[1])));
      }
      if (p.ext) {
        out += show(leave(i, "ext"), `<line class="gc-art-bar flag" x1="${f1(p.to[0])}" y1="${f1(p.to[1])}" x2="${f1(p.ext[0])}" y2="${f1(p.ext[1])}"/>`)
          + show(arrive(i, "ext"), `<circle class="gc-art-flag" cx="${f1(p.ext[0])}" cy="${f1(p.ext[1])}" r="${f1(1.6 * sz(p.ext[1]))}"/>`);
      }
      out += show(lastAt, chip(p.ext || p.to, r.label, p.words));
      return { out, over };
    };
    let body = across(CAM.los, "gc-art-los"), top = "";
    const nowAt = nx ? leave(rows.length, "now") : null;
    if (moving) {
      plan.forEach((e, j) => {
        // From the moment the camera cuts to this snap to the next cut.
        const tIn = j ? leave(e.i, "snap") + 0.21 : null;
        const nextGo = plan[j + 1] ? leave(plan[j + 1].i, "snap") : nowAt;
        // The last snap of a drive that is over keeps its goal line when it
        // scored, and lets its line to gain go: that line is spent.
        const ends = nextGo == null && j === plan.length - 1, kept = ends && e.r.kind === "td";
        const gain = e.p.gain != null ? across(e.p.gain, "gc-art-gain") : "", goal = e.p.goal != null ? across(e.p.goal, "gc-art-goal") : "";
        const m = marks(e, (t, inner) => win(t, null, inner));
        body += win(tIn, nextGo != null ? nextGo : ends ? T.dur : null, kept ? gain : gain + goal) + (kept ? win(tIn, null, goal) : "");
        body += win(tIn, nextGo, `<g class="gc-art-play ${e.r.kind}">${m.out}</g>`);
        if (m.over) top += win(tIn, nextGo, `<g class="gc-art-play ${e.r.kind}">${m.over}</g>`);
      });
    } else if (!nx && rows.length) {
      // At rest after a drive that ended: its last play, as it finished.
      const e = { i: rows.length - 1, r: rows[rows.length - 1], p: artPlay(rows[rows.length - 1]) };
      const m = marks(e, (t, inner) => inner);
      body += (e.p.goal != null && e.r.kind === "td" ? across(e.p.goal, "gc-art-goal") : "")
        + `<g class="gc-art-play ${e.r.kind}">${m.out}</g>`;
      if (m.over) top = `<g class="gc-art-play ${e.r.kind}">${m.over}</g>`;
    }
    let rest;
    if (nx) {
      const ytg = dir > 0 ? 100 - nx.los : nx.los;
      const rz = ytg <= 20;
      const lineY = nx.goal ? (ytg <= 70 ? artY(ytg) : null) : nx.gain != null ? artY(Math.abs(nx.gain - nx.los)) : null;
      const lines = lineY == null ? "" : across(lineY, nx.goal ? "gc-art-goal" : "gc-art-gain");
      const words = [rz ? "Red zone" : "", spotWord(d, nx.los)].filter(Boolean).join(" · ");
      // The down rides on the line it is going for, as a broadcast's does.
      const now = `${lines}<g class="gc-art-play now${rz ? " rz" : ""}">${chip([CAM.ball[0], lineY != null ? lineY : CAM.los], nx.words || "Next snap", words)}</g>`
        + `<circle class="gc-art-ring" cx="${f1(CAM.ball[0])}" cy="${f1(CAM.ball[1])}" r="3.4"/>`;
      body += moving ? win(nowAt + 0.21, null, now) : now;
      rest = [CAM.ball[0], CAM.ball[1], 1];
    } else {
      const p = artPlay(rows[rows.length - 1]), at = p.ext || p.to;
      rest = [at[0], at[1], sz(at[1])];
    }
    // Replay on the photograph too: the card's button is a tab away.
    return `<svg class="gc-art" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true" data-gc-art>`
      + `${body}${artBall(rest[0], rest[1], rest[2], moving ? T.motion : "")}${top}</svg>`
      + `<button type="button" class="gc-replay gc-art-replay" data-gc-replay aria-label="Replay the drive">${REPLAY}</button>`;
  }

  /* THE BALLPARK'S PITCHES. The same photograph's points app.js measured
     for the batted ball (PBP_PHOTO), and two more read off it the same way
     (scratch: fieldcal/grid_park_zoom.png): the pitcher's hand over the
     mound and the plate between the batter's boxes. A foot across is 2.73
     units there — the boxes' inside lines are 29 inches apart and 6.6 units
     — and a foot up 2.1, off the batter's stance; so every pitch the zone
     below draws crosses the plate in the picture where it crossed it in the
     game, the strike zone the batter's own. A pitch the cameras did not
     track is not thrown (it has no place to land). After the at-bat, a ball
     in play flies on from the plate the way app.js draws one
     (pbpFlight), and an earlier batted ball stays faint under the pitches
     the tiles below still describe. */
  const PARK = { hand: [119.5, 95.5], plate: [119.5, 131], fx: 2.73, fz: 2.1 };
  const parkPt = (p) => [PARK.plate[0] + Math.max(-2.5, Math.min(2.5, Number(p.px))) * PARK.fx,
    PARK.plate[1] - Math.max(-0.5, Math.min(5.5, Number(p.pz))) * PARK.fz];
  function pitchArt(d, hitRow, game) {
    const lv = d.live || {};
    const ev = (d.events || []).filter((r) => r && (r.kind === "pitch" || r.kind === "atbat"));
    if (lv.state !== "live" || !ev.length) return null;
    const ab = ev[ev.length - 1].at_bat;
    const ps = ev.filter((r) => r.kind === "pitch" && r.at_bat === ab);
    if (!ps.length) return null;
    const done = ev.find((r) => r.kind === "atbat" && r.at_bat === ab);
    const run = pitchRun(d, ab, ps.length);
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const FLY = 0.42, GAP = 0.75;                        // the zone's own beat
    const t = (s) => `${Math.max(0, s).toFixed(2)}s`;
    const pop = (s, inner) => (s != null && s > 0 ? `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.12s" begin="${t(s)}" fill="freeze"/>${inner}</g>` : inner);
    // Each located pitch, and when (from now) it leaves the hand: the zone's
    // schedule exactly, so the two land together.
    let n = 0;
    const thrown = ps.map((p, i) => {
      const at = p.px != null && p.pz != null ? parkPt(p) : null;
      const b = at && i >= run.from && !calm ? (n++) * GAP + 0.15 - run.elapsed : null;
      return { p, i, at, b: b != null && b > 0 ? b : null, o: pzOutcome(p.code) };
    });
    const tops = ps.map((p) => (p.sz || [])[0]).filter((v) => v != null), bots = ps.map((p) => (p.sz || [])[1]).filter((v) => v != null);
    const top = tops.length ? tops.reduce((a, b) => a + b, 0) / tops.length : 3.4;
    const bot = bots.length ? bots.reduce((a, b) => a + b, 0) / bots.length : 1.6;
    const z0 = parkPt({ px: -PZ_HALF, pz: top }), z1 = parkPt({ px: PZ_HALF, pz: bot });
    let body = thrown.some((q) => q.at) ? `<rect class="gc-art-zone" x="${f1(z0[0])}" y="${f1(z0[1])}" width="${f1(z1[0] - z0[0])}" height="${f1(z1[1] - z0[1])}"/>` : "";
    const fly = thrown.filter((q) => q.b != null);
    thrown.forEach((q) => {
      if (!q.at) return;
      const [x, y] = q.at, h = PARK.hand;
      if (q.b != null) {
        const len = Math.hypot(x - h[0], y - h[1]);
        body += `<line class="gc-art-trail" x1="${f1(h[0])}" y1="${f1(h[1])}" x2="${f1(x)}" y2="${f1(y)}" opacity="0" stroke-dasharray="${f1(len)} ${f1(len + 2)}" stroke-dashoffset="${f1(len)}">`
          + `<animate attributeName="stroke-dashoffset" from="${f1(len)}" to="0" begin="${t(q.b)}" dur="${FLY}s" fill="freeze"/>`
          + `<animate attributeName="opacity" values="0;.85;.85;0" keyTimes="0;0.06;0.65;1" begin="${t(q.b)}" dur="${(FLY + 0.5).toFixed(2)}s" fill="freeze"/></line>`
          + `<circle class="gc-art-pitch" cx="${f1(x)}" cy="${f1(y)}" r="1.7" opacity="0">`
          + `<animate attributeName="cx" from="${f1(h[0])}" to="${f1(x)}" begin="${t(q.b)}" dur="${FLY}s" fill="freeze"/>`
          + `<animate attributeName="cy" from="${f1(h[1])}" to="${f1(y)}" begin="${t(q.b)}" dur="${FLY}s" fill="freeze"/>`
          + `<animate attributeName="r" from="0.9" to="1.7" begin="${t(q.b)}" dur="${FLY}s" fill="freeze"/>`
          + `<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.05;0.8;1" begin="${t(q.b)}" dur="${(FLY + 0.12).toFixed(2)}s" fill="freeze"/></circle>`;
      }
      body += pop(q.b != null ? q.b + FLY : null, `<circle class="gc-art-dot ${q.o}" cx="${f1(x)}" cy="${f1(y)}" r="1.25"/>`);
    });
    // The caption: each pitch as it lands, until the next one does; the
    // newest (and how the at-bat ended) last, and kept.
    const last = thrown[thrown.length - 1], lastP = last.p;
    const words = (p) => [p.speed != null ? `${Math.round(Number(p.speed))} mph` : "", p.pitch || "",
      p.balls != null && p.strikes != null ? `${p.balls}-${p.strikes}` : ""].filter(Boolean).join(" · ");
    const at = (q) => q.at || [PARK.plate[0], PARK.plate[1] - 2.5 * PARK.fz];
    const endAt = last.b != null ? last.b + FLY : fly.length ? fly[fly.length - 1].b + FLY : null;
    fly.forEach((q, j) => {
      if (q === last) return;
      const until = j + 1 < fly.length ? fly[j + 1].b + FLY : endAt;
      body += `<g class="gc-art-play pz ${q.o}" opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.12s" begin="${t(q.b + FLY)}" fill="freeze"/>`
        + `<animate attributeName="opacity" to="0" dur="0.12s" begin="${t(until)}" fill="freeze"/>${chip(at(q), `${q.i + 1} · ${lastWord(q.p)}`, words(q.p))}</g>`;
    });
    const endTitle = done && done.event ? String(done.event) : `${last.i + 1} · ${lastWord(lastP)}`;
    body += pop(endAt, `<g class="gc-art-play pz ${done && done.scoring ? "score" : last.o}">${chip(at(last), endTitle, done ? `Pitch ${last.i + 1} · ${words(lastP)}` : words(lastP))}</g>`);
    // The ball in play, on from the plate; or the last one hit, faint.
    const park = (game || {}).park;
    const flight = (hit, from, faint) => {
      const f = typeof pbpFlight === "function" ? pbpFlight(hit, park, { photo: true }) : null;
      if (!f) return "";
      const path = `M${f1(f.H[0])} ${f1(f.H[1])}Q${f1(f.C[0])} ${f1(f.C[1])} ${f1(f.L[0])} ${f1(f.L[1])}`;
      if (faint) return `<g class="gc-art-old"><path class="gc-art-arc" d="${path}"/><circle class="gc-art-mark" cx="${f1(f.L[0])}" cy="${f1(f.L[1])}" r="3.6" stroke-width="1"/></g>`;
      const title = (typeof PBP_TRAJ === "object" && PBP_TRAJ[hit.trajectory]) || String(hit.trajectory || "").replace(/_/g, " ");
      const detail = [hit.launch_speed != null ? `${Number(hit.launch_speed).toFixed(1)} MPH` : "", hit.distance != null ? `${Math.round(hit.distance)} FT` : ""].filter(Boolean).join(" · ");
      const end = rings(f.L, 1) + chip(f.L, title || "In play", detail);
      if (from == null) return `<path class="gc-art-arc" d="${path}"/>${end}<circle class="gc-art-pitch" cx="${f1(f.L[0])}" cy="${f1(f.L[1])}" r="1.7"/>`;
      const id = "gcarc" + Math.random().toString(36).slice(2, 7);
      return `<path id="${id}" class="gc-art-arc" d="${path}" stroke-dasharray="${f1(f.len)} ${f1(f.len + 2)}" stroke-dashoffset="${f1(f.len)}">`
        + `<animate attributeName="stroke-dashoffset" from="${f1(f.len)}" to="0" begin="${t(from)}" dur="1.2s" fill="freeze"/></path>`
        + `<circle class="gc-art-pitch" r="1.7" opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.05s" begin="${t(from)}" fill="freeze"/>`
        + `<animateMotion begin="${t(from)}" dur="1.2s" fill="freeze"><mpath href="#${id}"/></animateMotion></circle>`
        + pop(from + 1.2, end);
    };
    if (done && done.hit) body += flight(done.hit, endAt != null ? endAt + 0.1 : null, false);
    else if (hitRow && hitRow.hit && hitRow.at_bat !== ab) body = flight(hitRow.hit, null, true) + body;
    return `<svg class="gc-art" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true" data-gc-art>${body}</svg>`
      + `<button type="button" class="gc-replay gc-art-replay" data-gc-pz-replay aria-label="Replay the at-bat">${REPLAY}</button>`;
  }
  const lastWord = (p) => p.call || PZ_WORDS[pzOutcome(p.code)];

  /* What app.js draws over the render it is showing: the drive on the
     field, the at-bat in the ballpark — or null, and it draws its own. */
  let _artLast = null;
  function art(d, league, hitRow, game) {
    _artLast = { d, league, hit: hitRow, game };
    try {
      if (FOOTBALL.has(league)) return driveArt(d, league, hitRow);
      if (league === "mlb") return pitchArt(d, hitRow, game);
    } catch (e) { if (typeof console !== "undefined") console.error("gamecast art", e); }
    return null;
  }

  /* ---------------- the whole game, a drive a row ----------------
     The Play-by-play tab's chart: every drive from where it started to
     where it ended, in its side's colour, how it ended at the end of it —
     a touchdown at the goal line, a kick or a turnover where the ball was
     snapped, any other drive where its last play left the ball, the drive
     in progress where the scoreboard has the ball now. Quarters are
     marked down the left. It draws itself in once, the first time a game
     is opened, not on every redraw. */
  const RESULT_TAGS = [[/missed|no good|blocked f/i, "NO GOOD", "bad"], [/interception|\bint\b/i, "INT", "bad"],
    [/fumble/i, "FUM", "bad"], [/downs/i, "DOWNS", "bad"], [/safety/i, "SAFETY", "bad"], [/touchdown|\btd\b/i, "TD", "score"],
    [/field goal|\bfg\b/i, "FG", "score"], [/punt/i, "PUNT", ""], [/half/i, "HALF", ""], [/end/i, "END", ""]];
  const _drawn = new Set();
  function driveEnd(d, dr, rows, now) {
    const last = rows[rows.length - 1];
    if (now) return now.los;
    if (last.kind === "td") return last.to;
    if (last.kind === "kick" || last.kind === "fg" || last.kind === "to") return last.from;
    return last.ext != null ? last.ext : last.to;
  }
  function gameChartHTML(d, league) {
    const lv = d.live || {};
    const drives = (d.drives || []).map((dr) => ({ dr, rows: driveRows(d, dr) })).filter((x) => x.rows.length);
    if (!drives.length) return "";
    const cols = fieldColours(d, league);
    const game = String(d.event_id || "");
    const grow = !_drawn.has(game) && !(typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
    _drawn.add(game);
    const GEO = { wide: Object.assign({}, FIELD.wide, { row: 19, gut: 30 }), narrow: Object.assign({}, FIELD.narrow, { row: 17, gut: 22 }) };
    const svgs = Object.entries(GEO).map(([cls, g]) => {
      const X = (y) => g.gut + (y + 10) * g.U, Y = (i) => g.top + i * g.row + g.row / 2;
      let body = "", period = null;
      drives.forEach(({ dr, rows }, i) => {
        const y = Y(i), dir = rows[0].dir, side = dir > 0 ? "home" : "away";
        const live = lv.state === "live" && i === drives.length - 1 && !dr.result && (!lv.possession || lv.possession === dr.team);
        const now = live ? nextSnap(d, dir) : null;
        const a = rows[0].from, b = driveEnd(d, dr, rows, now);
        const pr = dr.period || rows[0].period;              // the quarter the drive began in
        if (pr && pr !== period) {
          if (period != null) body += `<line class="gc-dc-q" x1="0" y1="${f1(y - g.row / 2)}" x2="${f1(X(110))}" y2="${f1(y - g.row / 2)}"/>`;
          body += `<text class="gc-dc-ql" x="${f1(g.gut / 2)}" y="${f1(y + g.fs * 0.36)}">${pr <= 4 ? `Q${pr}` : "OT"}</text>`;
          period = pr;
        }
        const hit = RESULT_TAGS.find(([re]) => re.test(String(dr.result || "")));
        const tag = now ? ["NOW", "now"] : hit ? [hit[1], hit[2]] : (rows[rows.length - 1].kind === "td" ? ["TD", "score"] : ["", ""]);
        const c = cols[side];
        const x1 = X(a), x2 = X(b), s = x2 >= x1 ? 1 : -1;
        const grown = grow ? ` style="--i:${i}"` : "";
        body += `<g class="gc-dc-row ${side}${grow ? " grow" : ""}"${c ? ` style="--tm:${c}${grow ? `;--i:${i}` : ""}"` : grown}>`
          + `<line class="gc-dc-halo" x1="${f1(x1)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y)}"/>`
          + `<line class="gc-dc-bar" x1="${f1(x1)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y)}"/>`
          + (Math.abs(x2 - x1) > 4 ? `<path class="gc-dc-head" d="M${f1(x2 + s * 5)} ${f1(y)}L${f1(x2 - s * 3)} ${f1(y - 4.6)}V${f1(y + 4.6)}Z"/>` : `<circle class="gc-dc-dot" cx="${f1(x2)}" cy="${f1(y)}" r="3.4"/>`)
          + (tag[0] ? (() => {
            // Past the end of the drive, or before its start when that runs off the field.
            const w = tag[0].length * g.fs * 0.62, ahead = x2 + dir * 9;
            const fits = dir > 0 ? ahead + w <= X(110) - 2 : ahead - w >= X(-10) + 2;
            const x = fits ? ahead : x1 - dir * 9, anchor = (dir > 0) === fits ? "start" : "end";
            return `<text class="gc-dc-tag ${tag[1]}" x="${f1(x)}" y="${f1(y + g.fs * 0.32)}" text-anchor="${anchor}">${tag[0]}</text>`;
          })() : "")
          + `</g>`;
        if (now) body += `<circle class="gc-fd-ring" cx="${f1(x2)}" cy="${f1(y)}" r="${f1(g.ball[0] * 1.3)}"/>` + ballSVG(Object.assign({}, g, { ball: [g.ball[0] * 0.8, g.ball[1] * 0.8] }), x2, y, "");
      });
      return fieldSVG(g, cls, d, cols, drives.length, body, `Drive chart: ${drives.length} drives`, { band: true });
    }).join("");
    const key = (side) => `<span class="gc-dc-key"${cols[side] ? ` style="--tm:${cols[side]}"` : ""}>${esc(d[side] || "")}</span>`;
    return `<div class="card gc-chart"><div class="gc-head">Drive chart</div>
      <div class="gc-fd${grow ? " grow" : ""}">${svgs}</div>
      <div class="gc-fd-key">${key("away")}${key("home")}<span>${esc(d.home || "")} drives right, ${esc(d.away || "")} left</span></div></div>`;
  }

  /* ---------------- the at-bat, pitch by pitch (baseball) ----------------
     Baseball's tracker (Ethan, 2026-10-15: "any other ideas you have for
     the tracking of the live games for all sports"): the strike zone from
     the catcher's side with every pitch of the at-bat where it crossed,
     numbered in order and coloured by what came of it — the pitch
     chart's colours: a called strike amber, a whiff red, a ball in play
     green, a foul grey, a ball an open ring — the newest flying in from
     the mound. Between at-bats it keeps the last one, with how it ended.
     Every mark is the league's own pitch tracking (`px`, `pz` and the
     batter's zone on each pitch row, engine/mlb/sources/pbp.game_events);
     a pitch it did not track is in the list and not on the zone. */
  const PZ = { F: 54, X: 120, G: 246 };                // px a foot, the plate's middle, the ground
  const pzx = (px) => Math.max(10, Math.min(230, PZ.X + px * PZ.F));
  const pzy = (pz) => Math.max(10, Math.min(236, PZ.G - pz * PZ.F));
  const PZ_HALF = 17 / 24;                             // half the plate, in feet
  const PZ_WHIFF = new Set(["S", "W", "M", "Q"]), PZ_FOUL = new Set(["F", "T", "L", "O", "R"]), PZ_PLAY = new Set(["X", "D", "E"]);
  const pzOutcome = (code) => (code === "C" ? "c" : PZ_WHIFF.has(code) ? "w" : PZ_PLAY.has(code) ? "x" : PZ_FOUL.has(code) ? "f" : "b");
  const PZ_WORDS = { c: "Called strike", w: "Whiff", x: "In play", f: "Foul", b: "Ball" };
  let _pz = null, _pzReplay = false, _pzLast = null;
  /* The pitches that fly on this draw: every one on a first look or a
     Replay, the new ones when the at-bat grows, and none on a redraw. */
  function pitchRun(d, ab, n) {
    const now = Date.now(), r = _pz, game = String(d.event_id || "");
    if (_pzReplay || !r || r.game !== game || r.ab !== ab) _pz = { game, ab, n, from: 0, start: now };
    else if (r.n !== n) _pz = { game, ab, n, from: Math.min(r.n, n), start: now };
    _pzReplay = false;
    return { from: _pz.from, elapsed: (now - _pz.start) / 1000 };
  }
  /* THE NEXT PITCH (engine/mlb/nextpitch, 2026-10-15): what the man on
     the mound has thrown in this count, this season and last, against
     batters on this one's side — his own record, not a forecast. Shown
     for the at-bat in progress (its count after the newest pitch), or at
     0-0 for the batter just up. */
  const NP_SIDE = { L: "left-handed batters", R: "right-handed batters" };
  const NP_FAM = { ahead: "when he is ahead", behind: "when he is behind", even: "in even counts" };
  function nextPitch(d, ps, done) {
    const np = d.next_pitch, cur = d.current;
    if (!np || !cur || np.pitcher_id !== cur.pitcher_id) return "";
    const last = ps[ps.length - 1];
    const key = !done && last && last.balls != null && last.strikes != null && last.balls < 4 && last.strikes < 3
      ? `${last.balls}-${last.strikes}` : done && !cur.pitches ? "0-0" : "";
    const row = key && (np.counts || {})[key];
    if (!row || !(row.mix || []).length) return "";
    const side = NP_SIDE[np.side] || "every batter";
    const said = { count: `in ${key} counts to ${side}`, count_all: `in ${key} counts to every batter`,
                   family: `${NP_FAM[row.fam] || ""} against ${side}`, family_all: `${NP_FAM[row.fam] || ""} against every batter`,
                   all: `to ${np.side ? side : "every batter"}, every count` }[row.basis] || "";
    return `<div class="gc-np"><div class="gc-k">Next pitch · ${esc(key)}${cur.pitcher ? ` · ${esc(cur.pitcher)}` : ""}</div>
      <div class="gc-np-bars">${row.mix.map(([, name, sh]) => `<div class="gc-np-row"><span>${esc(name)}</span><i><b style="width:${(100 * sh).toFixed(1)}%"></b></i><em>${Math.round(100 * sh)}%</em></div>`).join("")}</div>
      <p class="gc-np-cap">His own mix ${esc(said)}, this season and last (${row.n} pitch${row.n === 1 ? "" : "es"}). A record of what he throws, not a forecast.</p></div>`;
  }
  function zone(d) {
    const lv = d.live || {};
    const ev = (d.events || []).filter((r) => r && (r.kind === "pitch" || r.kind === "atbat"));
    if (lv.state !== "live" || !ev.length) return "";
    const ab = ev[ev.length - 1].at_bat;
    const ps = ev.filter((r) => r.kind === "pitch" && r.at_bat === ab);
    if (!ps.length) return "";
    const done = ev.find((r) => r.kind === "atbat" && r.at_bat === ab);
    _pzLast = d;
    const run = pitchRun(d, ab, ps.length);
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const tops = ps.map((p) => (p.sz || [])[0]).filter((v) => v != null), bots = ps.map((p) => (p.sz || [])[1]).filter((v) => v != null);
    const top = tops.length ? tops.reduce((a, b) => a + b, 0) / tops.length : 3.4;
    const bot = bots.length ? bots.reduce((a, b) => a + b, 0) / bots.length : 1.6;
    const zx0 = pzx(-PZ_HALF), zx1 = pzx(PZ_HALF), zy0 = pzy(top), zy1 = pzy(bot), cw = (zx1 - zx0) / 3, ch = (zy1 - zy0) / 3;
    let grid = "";
    for (let i = 1; i < 3; i++) {
      grid += `<line class="gc-pz-grid" x1="${f1(zx0 + cw * i)}" y1="${f1(zy0)}" x2="${f1(zx0 + cw * i)}" y2="${f1(zy1)}"/>`
        + `<line class="gc-pz-grid" x1="${f1(zx0)}" y1="${f1(zy0 + ch * i)}" x2="${f1(zx1)}" y2="${f1(zy0 + ch * i)}"/>`;
    }
    const plate = `M${f1(zx0)} ${PZ.G + 2}H${f1(zx1)}V${PZ.G + 8}L${PZ.X} ${PZ.G + 14}L${f1(zx0)} ${PZ.G + 8}Z`;
    // Each pitch in order; the ones flying on this draw leave the mound a
    // beat apart and land where they crossed, the number showing as they do.
    const FLY = 0.42, GAP = 0.75;
    let marks = "", k = 0;
    ps.forEach((p, i) => {
      if (p.px == null || p.pz == null) return;
      const o = pzOutcome(p.code), x = pzx(p.px), y = pzy(p.pz), newest = i === ps.length - 1;
      const b = i >= run.from && !calm ? (k++) * GAP + 0.15 - run.elapsed : null;
      const flies = b != null && b > 0;
      const t = (s) => `${Math.max(0, s).toFixed(2)}s`;
      const ball = flies
        ? `<circle class="gc-pz-dot ${o}" cx="${f1(x)}" cy="${f1(y)}" r="8.5"><animate attributeName="cx" from="${PZ.X}" to="${f1(x)}" dur="${FLY}s" begin="${t(b)}" fill="freeze"/>`
          + `<animate attributeName="cy" from="14" to="${f1(y)}" dur="${FLY}s" begin="${t(b)}" fill="freeze"/><animate attributeName="r" from="2.5" to="8.5" dur="${FLY}s" begin="${t(b)}" fill="freeze"/></circle>`
        : `<circle class="gc-pz-dot ${o}" cx="${f1(x)}" cy="${f1(y)}" r="8.5"/>`;
      const num = `<text class="gc-pz-num ${o}" x="${f1(x)}" y="${f1(y + 3.6)}">${i + 1}</text>`;
      const ring = newest ? `<circle class="gc-pz-ring" cx="${f1(x)}" cy="${f1(y)}" r="13"/>` : "";
      const pop = (s, inner) => (flies ? `<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur="0.12s" begin="${t(s)}" fill="freeze"/>${inner}</g>` : inner);
      marks += pop(b, ball) + pop(b + FLY, num + ring);
    });
    const located = ps.some((p) => p.px != null && p.pz != null);
    const svg = `<svg class="gc-pz-svg" viewBox="0 0 240 262" role="img" aria-label="${escapeAttr(`Pitches this at-bat: ${ps.map((p, i) => `${i + 1} ${PZ_WORDS[pzOutcome(p.code)]}`).join(", ")}`)}">`
      + `<rect class="gc-pz-glow" x="${f1(zx0)}" y="${f1(zy0)}" width="${f1(zx1 - zx0)}" height="${f1(zy1 - zy0)}"/>`
      + `<rect class="gc-pz-box" x="${f1(zx0)}" y="${f1(zy0)}" width="${f1(zx1 - zx0)}" height="${f1(zy1 - zy0)}"/>${grid}`
      + `<path class="gc-pz-plate" d="${plate}"/><text class="gc-pz-view" x="8" y="18">Catcher’s view</text>${marks}`
      + (located ? "" : `<text class="gc-pz-view" x="120" y="132" text-anchor="middle">No pitch locations in the feed yet</text>`) + `</svg>`;
    const list = ps.map((p, i) => {
      const o = pzOutcome(p.code);
      const what = [p.speed != null ? `${Math.round(Number(p.speed))} mph` : "", p.pitch || ""].filter(Boolean).join(" ");
      const cnt = p.balls != null && p.strikes != null ? `${p.balls}-${p.strikes}` : "";
      return `<li class="gc-pz-row${i === ps.length - 1 ? " now" : ""}"><span class="gc-pz-n ${o}">${i + 1}</span>`
        + `<span class="gc-pz-t"><b>${esc(p.call || PZ_WORDS[o])}</b>${what ? `<span>${esc(what)}</span>` : ""}</span>${cnt ? `<em>${esc(cnt)}</em>` : ""}</li>`;
    }).join("");
    const last = ps[ps.length - 1];
    const tag = done ? `<span class="gc-tag${done.scoring ? "" : " quiet"}">${esc(done.event || "")}</span>` : "";
    const replay = calm ? "" : `<button type="button" class="gc-replay" data-gc-pz-replay aria-label="Replay the at-bat">${REPLAY}</button>`;
    return `<div class="gc-pz" data-gc-pz>
      <div class="gc-pz-head"><div><div class="gc-k">${done ? "Last at-bat" : "This at-bat"} · ${ps.length} pitch${ps.length === 1 ? "" : "es"}</div>
        <b>${esc(last.batter || "")}</b><span class="mini"> vs ${esc(last.pitcher || "")}</span>${tag}</div>${replay}</div>
      <div class="gc-pz-body">${svg}<ol class="gc-pz-list">${list}</ol></div>
      <div class="gc-pz-key">${["c", "w", "x", "f", "b"].map((o) => `<span class="${o}">${PZ_WORDS[o]}</span>`).join("")}</div>${nextPitch(d, ps, done)}</div>`;
  }

  /* ---------------- the last play ----------------
     ESPN's card under the field: the title ("1-yd Touchdown Run"), the
     win percentage, the sentence, the two players with their lines so
     far, and the snap it came from ("2nd & Goal at TB 1").

     OURS HAS NO SENTENCE, BY DESIGN. ESPN's `text` is their writing and
     is not in the file (docs/LAUNCH.md; test_prose_never_reaches_a_deep_
     file). What the row carries is the type, the yards, the down and
     distance, the snap spot and the NAMES the builder matched against the
     box score's roster (espnplays._football_players) — so the card is the
     type and the yards as its title, the names as chips, and each man's
     line from the box score under his name. A pass resolves to thrower
     then catcher, so the first chip reads his passing line and the second
     his receiving line; a run reads the rushing line first. Ethan,
     2026-09-10, on the rail: "show what player got what reception or
     yard" — this is that, with the player's whole game beside it.

     THE WIN PERCENTAGE IS OURS. ESPN prints theirs; the site's own live
     model writes `live.win_prob` for every game in progress
     (livescore_build._win_prob), and that is the number drawn, with the
     mark of the side it favours. No reading is no badge. */
  /* Football's newest SNAP: a timeout or a quarter's end is a moment in
     the game, not a play (app.js footballWords), and the card names it
     under the play rather than in its place — "Last play: Timeout, 0 yds"
     was the card the live page used to draw. */
  const isSnap = (p, d) => typeof footballWords !== "function" || footballWords(p, d).snap;
  function newestPlay(d, league) {
    const plays = d.plays || [];
    if (FOOTBALL.has(league)) {
      const foot = plays.filter((p) => p && p.kind === "football");
      return foot.slice().reverse().find((p) => isSnap(p, d)) || foot[foot.length - 1] || null;
    }
    return plays.slice().reverse().find((p) => p && p.event) || null;
  }
  //: The moments since the newest snap ("Timeout", "End of the 1st quarter").
  function sinceSnap(d, p) {
    const foot = (d.plays || []).filter((r) => r && r.kind === "football");
    const i = foot.indexOf(p);
    return i < 0 ? [] : foot.slice(i + 1).filter((r) => !isSnap(r, d)).map((r) => footballWords(r, d).title);
  }
  /* "1-yd Touchdown Run" is ESPN's title; ours is the type and the yards
     ("Rushing Touchdown · 1 yd"), composed from the two fields and
     nothing else. */
  function playTitle(p, d) {
    return esc(typeof footballWords === "function" ? footballWords(p, d).title : (p.event || "Play"));
  }
  function winPct(d, league) {
    const wp = (d.live || {}).win_prob;
    if (!wp || wp.home_win_prob == null) return "";
    const home = Number(wp.home_win_prob), away = wp.away_win_prob != null ? Number(wp.away_win_prob) : 1 - home;
    const [team, p] = home >= away ? [d.home, home] : [d.away, away];
    return `<span class="gc-win"><span class="gc-k">Win % (our model)</span>${teamMarkIn(league, team, 18)} <b>${(p * 100).toFixed(1)}</b></span>`;
  }
  function lastPlayHTML(d, league, faces) {
    const p = newestPlay(d, league);
    if (!p) return "";
    const foot = p.kind === "football";
    const when = foot ? `${p.period ? `Q${p.period}` : ""}${p.clock ? ` ${typeof fbClock === "function" ? fbClock(p.clock) : p.clock}` : ""}`.trim()
      : `${p.period ? (league === "nhl" ? hockeyPeriod(p.period) : (p.period <= 4 ? `Q${p.period}` : `OT${p.period - 4}`)) : ""}${p.clock ? ` ${p.clock}` : ""}`.trim();
    const words = foot && typeof footballWords === "function" ? footballWords(p, d) : null;
    const tag = p.turnover ? `<span class="gc-tag turnover">Turnover</span>`
      : p.scoring ? `<span class="gc-tag">${foot ? ({ TD: "Touchdown", FG: "Field goal" }[words && words.tag] || "Score") : (league === "nhl" ? "Goal" : `+${p.points || ""}`)}</span>` : p.penalty ? `<span class="gc-tag">Flag</span>` : "";
    const names = foot ? (p.players || []).filter(Boolean) : [p.player].filter(Boolean);
    const pass = foot && /pass|reception/i.test(String(p.event || ""));
    const chips = names.map((name, i) => {
      const got = playerLine(d, name, foot ? (pass ? (i === 0 ? "pass0" : "pass1") : "any") : "any");
      const team = (got.row && teamOf(d, name)) || p.team || "";
      const pos = got.row && got.row.pos ? ` ${esc(got.row.pos)}` : "";
      return `<div class="gc-chip">${faceHTML(league, got.row || { name }, faces)}
        <div class="gc-chip-t"><b>${esc(name)}</b><span class="mini">${esc(team)}${pos}</span>
          ${got.line ? `<span class="gc-chip-line">${got.line}</span>` : ""}</div></div>`;
    }).join("");
    const snap = foot && p.down ? `${esc(downWord(p))}${p.spot != null ? ` at ${esc(spotWord(d, p.spot))}` : ""}` : "";
    const since = foot ? sinceSnap(d, p) : [];
    const score = (p.away_score != null && p.home_score != null)
      ? `<span class="gc-score">${esc(d.away)} ${esc(p.away_score)} – ${esc(p.home_score)} ${esc(d.home)}</span>` : "";
    return `<div class="card gc-last">
      <div class="gc-last-head"><div><div class="gc-k">Last play${when ? ` · ${esc(when)}` : ""}</div>
        <b class="gc-last-title">${foot ? playTitle(p, d) : esc(p.event || "Play")}</b>${tag}</div>
        ${winPct(d, league)}</div>
      ${foot && p.team && (!words || words.snap) ? `<div class="gc-last-team">${teamMarkIn(league, p.team, 18)} ${esc(teamNameIn(league, p.team))}${
        ` <span class="mini">${esc((words && ROLE_WORD[words.role]) || "on offense")}</span>`}</div>` : ""}
      ${chips ? `<div class="gc-chips">${chips}</div>` : ""}
      <div class="gc-last-foot">${snap ? `<span>${snap}</span>` : ""}${score}</div>${
        since.length ? `<div class="gc-last-since">${since.map((w) => `<span>${esc(w)}</span>`).join("")}</div>` : ""}</div>`;
  }
  //: Which side the team on the card was, for the play it is named on.
  const ROLE_WORD = { receiving: "receiving", punting: "punting", kicking: "kicking" };

  /* ---------------- the game leaders ----------------
     ESPN's GAME LEADERS: five rows for football (passing, rushing,
     receiving, sacks, tackles), the away side's man on the left and the
     home side's on the right, each with his face, the big number and his
     line. The rows are composed from the box score above, not read off a
     `leaders` block: a leader IS the row with the most of one column, and
     the box score is already on the page. Hoops reads points, rebounds
     and assists; hockey goals, assists, shots and saves. A category with
     nobody over zero on either side is left out (no sacks in the first
     quarter is not a row of two dashes), and a side with nobody shows a
     blank mark and "None", which is what ESPN draws. */
  /* Each category reads one group's one column; the leader is the row
     with the most of it, and the line beside him is his group line. A
     category with nobody over zero on either side is not drawn. */
  const LEADERS = {
    football: [["Passing", "passing", "YDS"], ["Rushing", "rushing", "YDS"], ["Receiving", "receiving", "YDS"],
               ["Sacks", "defensive", "SACKS"], ["Tackles", "defensive", "TOT"]],
    hoops: [["Points", "", "PTS"], ["Rebounds", "", "REB"], ["Assists", "", "AST"]],
    hockey: [["Goals", "", "G"], ["Assists", "", "A"], ["Shots", "", "SOG"], ["Saves", "", "SV"]],
  };
  function leaderOf(d, team, groupName, label) {
    const groups = teamBox(d, team).filter((g) => (!groupName || lower(g.name) === lower(groupName)) && col(g, label) >= 0);
    let best = null;
    groups.forEach((g) => (g.rows || []).forEach((r) => {
      const v = num(cell(g, r, label));
      if (isFinite(v) && v > 0 && (!best || v > best.v)) best = { v, row: r, group: g };
    }));
    return best;
  }
  function leadersHTML(d, league, faces) {
    const set = FOOTBALL.has(league) ? LEADERS.football : league === "nhl" ? LEADERS.hockey : LEADERS.hoops;
    const side = (team, best, right) => best
      ? `<div class="gc-lead${right ? " right" : ""}">${faceHTML(league, best.row, faces)}
          <div class="gc-lead-t"><b class="gc-lead-v">${esc(best.v % 1 ? best.v.toFixed(1) : best.v)}</b>
            <span class="gc-lead-n">${esc(best.row.name)}${best.row.pos ? ` <span class="mini">${esc(best.row.pos)}</span>` : ""}</span>
            <span class="mini">${lineFor(best.group, best.row)}</span></div></div>`
      : `<div class="gc-lead${right ? " right" : ""} none"><span class="gc-face">${icon("user", 16)}</span><div class="gc-lead-t"><span class="mini">None</span></div></div>`;
    const rows = set.map(([label, group, stat]) => {
      const a = leaderOf(d, d.away, group, stat), h = leaderOf(d, d.home, group, stat);
      if (!a && !h) return "";
      return `<div class="gc-lead-row">${side(d.away, a, false)}<span class="gc-lead-k">${esc(label)}</span>${side(d.home, h, true)}</div>`;
    }).filter(Boolean).join("");
    if (!rows) return "";
    return `<div class="card gc-leaders">
      <div class="gc-head">Game leaders</div>
      <div class="gc-lead-teams"><span>${teamMarkIn(league, d.away, 22)} ${esc(d.away)}</span>
        <span>${esc(d.home)} ${teamMarkIn(league, d.home, 22)}</span></div>${rows}</div>`;
  }

  /* ---------------- the box score ----------------
     ESPN's BOX SCORE tab: one side at a time behind a team toggle, every
     group as its own table under ESPN's labels, a face beside each name.
     The toggle's choice lives in this module (`_team`), so a redraw on
     the twelve-second clock keeps the side the reader chose. A deep file
     from before `box` existed falls back to the Player stats room's own
     table (pbpPlayersHTML), which read the four markets the tracker
     grades on — thinner, never wrong. */
  function boxHTML(d, league, faces) {
    const box = d.box || [];
    if (!box.length) return typeof pbpPlayersHTML === "function" ? pbpPlayersHTML(d, league)
      : `<p class="rail-quiet">No box score on file yet.</p>`;
    const sides = [d.away, d.home].filter((t) => box.some((b) => b.team === t));
    if (!sides.length) return `<p class="rail-quiet">No box score on file yet.</p>`;
    if (!sides.includes(_team)) _team = sides[0];
    const toggle = `<div class="gc-toggle">${sides.map((t) => `<button type="button" class="gc-tog${t === _team ? " active" : ""}" data-gc-team="${escapeAttr(t)}">${
      teamMarkIn(league, t, 18)} ${esc(teamNameIn(league, t))}</button>`).join("")}</div>`;
    const groups = teamBox(d, _team);
    const tables = groups.map((g) => {
      const rows = (g.rows || []).filter((r) => (r.stats || []).some((s) => s && s !== "--"));
      if (!rows.length) return "";
      return `<div class="pbp-bx-wrap"><table class="pbp-bx gc-bx">
        <thead><tr><th scope="col" class="pbp-bx-who">${esc(titleCase(g.name))}</th>${
          (g.labels || []).map((l) => `<th scope="col">${esc(l)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr><th scope="row" class="pbp-bx-who">${faceHTML(league, r, faces)}<span>${esc(r.name)}${
          r.pos ? ` <span class="mini">${esc(r.pos)}</span>` : ""}</span></th>${
          (g.labels || []).map((_l, i) => `<td>${esc((r.stats || [])[i] == null ? "—" : (r.stats || [])[i])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }).join("");
    return `${toggle}${tables || `<p class="rail-quiet">Nothing logged for this club yet.</p>`}
      <p class="mini" style="opacity:.6">Box score ${esc(pbpAgo(d.generated_at))}.</p>`;
  }

  /* ---------------- team stats ----------------
     ESPN's TEAM STATS tab: the two sides' totals as a comparison — the
     away value, the stat's name, the home value, and a split bar under
     the plain numbers (first downs, total yards) showing the share each
     side has. A bar is drawn only where both values are a bare number: a
     "5-12" third-down line or a "31:12" possession clock is shown as it
     is, not parsed into a fraction and drawn as if it were yards. Rows
     are the away side's order, with anything only the home side lists
     appended, so the two never drift apart. A deep file without
     `team_stats` falls back to the totals the page adds up from its own
     drives (pbpTotalsHTML). */
  function teamStatsHTML(d, league) {
    const ts = d.team_stats || {};
    const A = ts[d.away] || [], H = ts[d.home] || [];
    if (!A.length && !H.length) return typeof pbpTotalsHTML === "function" ? (pbpTotalsHTML(d, league)
      || `<p class="rail-quiet">Team totals fill in as the game is played.</p>`) : "";
    const byKey = (rows) => { const m = {}; rows.forEach((r) => { m[r.name || r.label] = r; }); return m; };
    const h = byKey(H), seen = new Set();
    const order = [...A, ...H.filter((r) => !A.some((a) => (a.name || a.label) === (r.name || r.label)))];
    const rows = order.map((r) => {
      const key = r.name || r.label;
      if (seen.has(key)) return "";
      seen.add(key);
      const a = A.find((x) => (x.name || x.label) === key), b = h[key];
      const av = a ? a.value : "—", hv = b ? b.value : "—";
      let bar = "";
      if (plain(av) && plain(hv)) {
        const x = Number(av), y = Number(hv), tot = x + y;
        const left = tot > 0 ? Math.round((x / tot) * 100) : 50;
        bar = `<div class="gc-bar"><span style="width:${left}%"></span><span style="width:${100 - left}%"></span></div>`;
      }
      return `<div class="gc-ts"><div class="gc-ts-row"><b>${esc(av)}</b><span class="gc-ts-k">${esc(r.label || key)}</span><b>${esc(hv)}</b></div>${bar}</div>`;
    }).join("");
    return `<div class="card gc-tstats"><div class="gc-ts-head"><span>${teamMarkIn(league, d.away, 20)} ${esc(d.away)}</span>
      <span class="gc-head">Team stats</span><span>${esc(d.home)} ${teamMarkIn(league, d.home, 20)}</span></div>${rows}</div>`;
  }

  /* ---------------- play by play, drive by drive ----------------
     ESPN's PLAY-BY-PLAY tab: each drive a card, newest first, headed by
     the mark, the team, "7 plays · 66 yd · 3:23 · Q1", how it ended
     ("Touchdown", "Punt" — the summary's `displayResult`, read by
     espnplays as a label and refused as a sentence) and the score it
     left, with every play of it under the head in the order it was
     played (a drive reads forwards; playsHTML draws the rows the rail
     draws, so a row is the same row in both places). A drive from a file
     without `result` falls back to the rail's derived tag — Score,
     Turnover, In progress. The other sports draw their periods the way
     the rail groups them (pbpGroups), every play of each. */
  function drivesHTML(d, league) {
    const lv = d.live || {};
    const drives = (d.drives || []).slice().reverse();
    if (!drives.length) return `<div class="card">${panelEmpty("Nothing has happened yet.")}</div>`;
    return gameChartHTML(d, league) + drives.map((dr, i) => {
      const rows = dr.plays || [];
      const n = dr.offensive_plays || rows.length;
      const result = (typeof driveResultWord === "function" ? driveResultWord(dr) : dr.result) || (dr.scoring ? "Score" : rows.some((p) => p.turnover) ? "Turnover"
        : (i === 0 && lv.state === "live") ? "In progress" : "");
      const last = rows[rows.length - 1] || {};
      const score = (last.away_score != null && last.home_score != null) ? `${last.away_score}–${last.home_score}` : "";
      return `<div class="card gc-dr${dr.scoring ? " scoring" : ""}">
        <div class="gc-dr-head">${teamMarkIn(league, dr.team, 22)}
          <div><b>${esc(dr.team || "—")}</b><span class="mini"> · ${n} play${n === 1 ? "" : "s"}, ${dr.yards || 0} yd${dr.yards === 1 ? "" : "s"}${
            dr.elapsed ? `, ${esc(dr.elapsed)}` : ""}${dr.period ? ` · Q${esc(dr.period)}` : ""}</span></div>
          ${result ? `<span class="gc-tag${/turnover|interception|fumble|safety/i.test(result) ? " turnover" : /touchdown|field goal|score/i.test(result) ? "" : " quiet"}">${esc(result)}</span>` : ""}
          ${score ? `<span class="gc-dr-score">${esc(score)}</span>` : ""}</div>
        ${playsHTML({ plays: rows, home: d.home, away: d.away }) || `<p class="rail-quiet" style="margin:0 0 8px">No plays yet.</p>`}</div>`;
    }).join("");
  }
  function playsTabHTML(d, league) {
    if (FOOTBALL.has(league)) return drivesHTML(d, league);
    const groups = pbpGroups(d);
    if (!groups.length) return `<div class="card">${panelEmpty("Nothing has happened yet.")}</div>`;
    return groups.map((g) => `<div class="card gc-dr"><div class="gc-dr-head"><div><b>${esc(g.head)}</b>${
      g.sub ? `<span class="mini"> — ${esc(g.sub)}</span>` : ""}</div>${g.tag ? `<span class="gc-tag">${esc(g.tag)}</span>` : ""}</div>
      ${playsHTML({ plays: g.rows }) || `<p class="rail-quiet" style="margin:0 0 8px">No plays yet.</p>`}</div>`).join("");
  }

  /* ---------------- odds & picks ----------------
     ESPN's ODDS tab is a sportsbook's lines; ours is the site's own
     reading of this game — the live line track off the board (the
     opened → now chart the game page draws) and the two boards' picks on
     the game as the Live tab words them (pbpPropsHTML: Pick of the Day,
     Most Likely, Edge, each with the tracker's word), with the door to
     the full game page for the lines, the props and the long shots. */
  function oddsHTML(d, league, boardGame) {
    const picks = typeof pbpPropsHTML === "function" ? pbpPropsHTML(d, league) : "";
    const track = boardGame && boardGame.line_track && typeof lineTrackHTML === "function"
      ? `<div class="card">${lineTrackHTML(boardGame)}</div>` : "";
    const door = boardGame ? `<button type="button" class="btn ghost" id="pbp-game-door" data-gid="${escapeAttr(gameId(boardGame))}">Full game page — lines, props, long shots →</button>` : "";
    return `${track}${picks}${door}`;
  }

  /* ---------------- the Gamecast tab ----------------
     ESPN's first tab, top to bottom: the drive in progress, the field
     (app.js draws it above the tabs, on the park card, so it is on every
     tab), the last play, the leaders. A final has no drive and says so in
     one line over the leaders; a scheduled game draws nothing here, and
     the page's own empty state covers it. */
  function gamecastHTML(d, league, faces) {
    const last = newestPlay(d, league);
    const lv = d.live || {};
    const quiet = lv.state === "live" ? "" : lv.state === "final"
      ? `<p class="rail-quiet">Final. The leaders, the box score and every drive are below.</p>` : "";
    return `${currentDriveHTML(d, league, last)}${lastPlayHTML(d, league, faces)}${leadersHTML(d, league, faces)}${quiet}`;
  }

  function panel(tab, ctx) {
    const { d, league, faces, boardGame } = ctx || {};
    if (!d) return "";
    switch (tab) {
      case "box": return boxHTML(d, league, faces || {});
      case "plays": return playsTabHTML(d, league);
      case "team": return teamStatsHTML(d, league);
      case "odds": return oddsHTML(d, league, boardGame);
      default: return gamecastHTML(d, league, faces || {});
    }
  }

  /* ---------------- the basketball page ----------------
     Ethan's NBA render (2026-10-15) is its own page — js/hoopscast.js and
     css/hoopscast.css, loaded the first time a basketball game opens —
     handed the strip, the way back and app.js's own wiring. Until it lands
     the page says so; a file that will not load leaves basketball on the
     rooms above, as it was. */
  const HOOPS = new Set(["nba", "wnba"]);
  let _hoops = null, _hoopsFailed = false;
  function hoops(host, ctx) {
    if (host && ctx && ctx.league === "nhl") return rink(host, ctx);
    if (!host || !ctx || !HOOPS.has(ctx.league) || _hoopsFailed) return false;
    // A page that throws leaves the host as it was and hands back to the
    // old rooms for this pass; the next refresh tries the new page again.
    if (window.QBHoops) {
      try { return window.QBHoops.render(host, ctx); } catch (e) { console.error("hoopscast", e); return false; }
    }
    if (!_hoops) {
      _hoops = new Promise((resolve) => {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "css/hoopscast.css";
        document.head.appendChild(css);
        const el = document.createElement("script");
        el.src = "js/hoopscast.js";
        el.addEventListener("load", () => resolve(true));
        el.addEventListener("error", () => { _hoopsFailed = true; resolve(false); });
        document.head.appendChild(el);
      }).then(() => { if (state.view === "pbp") renderPbpPage(); });
    }
    host.innerHTML = `${ctx.stripHTML || ""}<div class="card"><p class="rail-quiet">Loading the court…</p></div>${ctx.back || ""}`;
    if (typeof ctx.wire === "function") ctx.wire();
    return true;
  }

  /* ---------------- the hockey page ----------------
     Ethan's NHL render (2026-10-15), the same way: js/rinkcast.js and
     css/rinkcast.css, loaded the first time a hockey game opens whose file
     carries the league's own events (`rink`, written by
     livescore_build.nhl_rink_pass). A game without them, or a file that
     will not load, stays on the rooms above. */
  let _rink = null, _rinkFailed = false;
  function rink(host, ctx) {
    if (!ctx.d || !ctx.d.rink || _rinkFailed) return false;
    if (window.QBRink) {
      try { return window.QBRink.render(host, ctx); } catch (e) { console.error("rinkcast", e); return false; }
    }
    if (!_rink) {
      _rink = new Promise((resolve) => {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "css/rinkcast.css";
        document.head.appendChild(css);
        const el = document.createElement("script");
        el.src = "js/rinkcast.js";
        el.addEventListener("load", () => resolve(true));
        el.addEventListener("error", () => { _rinkFailed = true; resolve(false); });
        document.head.appendChild(el);
      }).then(() => { if (state.view === "pbp") renderPbpPage(); });
    }
    host.innerHTML = `${ctx.stripHTML || ""}<div class="card"><p class="rail-quiet">Loading the rink…</p></div>${ctx.back || ""}`;
    if (typeof ctx.wire === "function") ctx.wire();
    return true;
  }

  /* ---------------- the moving mark ----------------
     Ethan, 2026-10-15, drawing a line across the rink: "Are we able too do
     like a animation of a hockey puck moving back and forth across the ice
     when we show the switching of positions". One timeline for every live
     page that moves something over its art: the puck from event to event,
     the ball from shot to shot, the ball down the field play by play.

     `points` are the art's own pixels, in order, each {x, y}. `jump` on a
     point says the feed does not join it to the one before (a whistle, a
     new drive): the mark fades out, moves, and fades back in, where a
     joined point is a glide at a pace set by the distance (`leg` sets one
     leg's seconds outright; `via`, a control point, bends the glide into
     an arc, as a shot's flight to the rim). `hold` is how long it rests
     on arrival. The
     answer is when the mark leaves for each point (`go`) and reaches it
     (`at`), so a page can show each event's mark as the moving one gets
     there; how long the run is; and the SVG to put inside the moving
     element — SVG's own animation, nothing running in script. `elapsed`
     is how far into the run the page already is: each redraw (the page
     polls every five seconds and redraws when the file moves) rebuilds the drawing, and a run begun before it carries on
     from where it was. The animation is cut at that moment and starts
     from the mark's position then, rather than with a negative begin: a
     browser does not hold the end of an animation that finished before
     its drawing existed, so anything already past is drawn as it is
     (`past`), and `begin` gives a time from now. `steps` switches an
     attribute as the mark sets off on each leg (a glow in the colour of
     the side moving it) and settles on the end value. A reader who asked
     for less motion, or a run already over, gets the end state with no
     animation (`still`), and the page draws every mark where it is.

     `size` on a point is the mark's size there, against its drawn size: on a
     photograph the ball is smaller the further down the field it is, and
     a point with one gives the run a scale as well as a place (an arc's
     size goes evenly from one end to the other, since its rise is height,
     not distance from the camera). */
  function track(points, opts) {
    const o = Object.assign({ speed: 900, min: 0.35, max: 1.1, hold: 0.3, fade: 0.2, elapsed: 0 }, opts || {});
    const pts = (points || []).filter((p) => p && isFinite(p.x) && isFinite(p.y));
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const sized = pts.some((p) => p.size != null), S = (p) => (p.size != null ? p.size : 1);
    const at = [], go = [], keys = [];                       // keys: [seconds, x, y, opacity, size]
    let t = 0;
    pts.forEach((p, i) => {
      if (!i) {
        keys.push([0, p.x, p.y, 0, S(p)], [o.fade, p.x, p.y, 1, S(p)]);
        t = o.fade;
        go.push(0); at.push(0);
      } else {
        const q = pts[i - 1];
        go.push(t);
        if (p.jump) {
          keys.push([t + o.fade, q.x, q.y, 0, S(q)], [t + o.fade + 0.01, p.x, p.y, 0, S(p)], [t + 2 * o.fade + 0.01, p.x, p.y, 1, S(p)]);
          t += 2 * o.fade + 0.01;
        } else {
          const leg = p.leg != null ? p.leg : Math.min(o.max, Math.max(o.min, Math.hypot(p.x - q.x, p.y - q.y) / o.speed));
          if (p.via) {
            // An arc, as six short glides along the curve.
            for (let j = 1; j < 6; j++) {
              const f = j / 6, u = 1 - f;
              keys.push([t + leg * f, u * u * q.x + 2 * u * f * p.via[0] + f * f * p.x, u * u * q.y + 2 * u * f * p.via[1] + f * f * p.y, 1,
                S(q) + (S(p) - S(q)) * f]);
            }
          }
          t += leg;
          keys.push([t, p.x, p.y, 1, S(p)]);
        }
        at.push(t);
      }
      const hold = p.hold != null ? p.hold : o.hold;
      if (hold > 0) { t += hold; keys.push([t, p.x, p.y, 1, S(p)]); }
    });
    const dur = t, el = Math.max(0, Number(o.elapsed) || 0), left = dur - el;
    const past = (s) => s <= el;
    const begin = (s) => `${Math.max(0, s - el).toFixed(2)}s`;
    if (!pts.length || calm || left <= 0.05) {
      return { at, go, dur, left: 0, elapsed: el, still: true, motion: "", begin, past: () => true, steps: () => "" };
    }
    // One value per point, taken as the mark leaves for it; from now on.
    const steps = (attr, vals, end) => {
      let cur = vals[0];
      const v = [], kt = [];
      vals.forEach((val, n) => {
        if (!n) return;
        if (go[n] <= el) cur = val;
        else { v.push(val); kt.push(((go[n] - el) / left).toFixed(4)); }
      });
      v.unshift(cur); kt.unshift("0"); v.push(end); kt.push("1");
      return `<animate attributeName="${attr}" calcMode="discrete" values="${v.join(";")}" keyTimes="${kt.join(";")}" dur="${left.toFixed(2)}s" begin="0s" fill="freeze"/>`;
    };
    // From now on: where the mark is at this moment, then every key to come.
    const k0 = keys.findIndex((k) => k[0] > el);
    const a = keys[k0 - 1], b = keys[k0], f = (el - a[0]) / (b[0] - a[0]);
    const rest = [[0, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f, a[4] + (b[4] - a[4]) * f]]
      .concat(keys.slice(k0).map(([s2, x, y, op, sz]) => [s2 - el, x, y, op, sz]));
    const timing = `keyTimes="${rest.map(([s2]) => (s2 / left).toFixed(4)).join(";")}" dur="${left.toFixed(2)}s" begin="0s" fill="freeze"`;
    // The size rides on the place (`additive="sum"`: scaled where it stands).
    const motion = `<animateTransform attributeName="transform" type="translate" calcMode="linear" values="${
      rest.map(([, x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(";")}" ${timing}/>`
      + (sized ? `<animateTransform attributeName="transform" type="scale" additive="sum" calcMode="linear" values="${
        rest.map((k) => k[4].toFixed(3)).join(";")}" ${timing}/>` : "")
      + `<animate attributeName="opacity" calcMode="linear" values="${rest.map((k) => +k[3].toFixed(3)).join(";")}" ${timing}/>`;
    return { at, go, dur, left, elapsed: el, still: false, motion, begin, past, steps };
  }

  window.QBGamecast = {
    panel, hoops, setTeam: (t) => { _team = String(t || ""); }, team: () => _team,
    // The moving mark, for the pages that move something over their art.
    track,
    // Baseball's at-bat, pitch by pitch, under the MLB page's at-bat card.
    zone,
    // The drive and the at-bat on the photographs (app.js pbpParkHTML).
    art,
    // Exposed for the tests and for Ask: the readers, not the markup.
    spotWord, playerLine, leaderOf, currentDrive, newestPlay, lineFor, faceURL, driveRows, nextSnap,
  };
})();
