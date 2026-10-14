/* Qellys Book — every league's role chart (js/chart-role.js).
   ==========================================================================
   Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
   done, then make sure they are all routed correctly like nfl." Loaded by
   js/carrychart.js the first time a role chart is drawn, and drawn in its
   frame (the games row, the By game | season tabs, the numbers beside the
   drawing, the long tail folded), so it reads like every other chart.

   THE ROLE CHART (kind "role", engine/role.chart): how much he is used,
   game by game — an NFL player's snap share, targets, carries, his share
   of his team's and his red-zone looks; a college player's carries,
   catches and attempts; a basketball player's minutes, starts and shots;
   a hitter's plate appearances and spot in the order, a pitcher's pitch
   count, batters faced and rest; a skater's ice time and shots, a
   goalie's shots faced. One strip per number, every game in order from
   the left, his season's average dashed across it. By game lights the
   game picked above it (a bar is a door to its game); the season tab
   lights his last three. A number not on file is a gap, never a zero.

   No inline handlers: the page's CSP forbids them. */
(function () {
  "use strict";
  const Q = window.QBCarry && window.QBCarry.plug;
  if (!Q) return;
  const { esc, tile, tableHTML, pct, num1, ord, state } = Q.h;
  const st = () => state() || {};
  const now = () => st().data || {};
  const sel = (i) => (st().sel === i ? " sel" : "");

  /* ---------------- words ---------------- */
  const clock = (v) => {
    let m = Math.floor(v), s = Math.round((v - m) * 60);
    if (s === 60) { m += 1; s = 0; }
    return `${m}:${String(s).padStart(2, "0")}`;
  };
  /* A game's number as the box score writes it; an average one place
     further (a share stays a percentage, a spot in the order stays 2nd). */
  function fmt(m, v, sport, avg) {
    if (v == null) return "—";
    if (m.unit === "pct") return pct(v);
    if (m.unit === "min") return sport === "nhl" ? clock(v) : avg ? num1(v) : `${Math.round(v)}`;
    if (m.unit === "spot") return avg ? num1(v) : ord(Math.round(v));
    return avg ? num1(v) : `${Math.round(v)}`;
  }
  //: What the games row says under each game: his lead number that night.
  const CHIP = { snap: "snaps", att: "att", tgt: "tgt", car: "car", rec: "rec", min: "min", pa: "PA",
                 pitches: "pitches", outs: "outs", toi: "TOI", sa: "faced" };
  //: A spot in the order is better low; everything else, high.
  const better = (m, a, b) => (m.unit === "spot" ? a < b : a > b);
  const lead = (d) => (d.metrics || []).find((m) => m.key === d.lead) || (d.metrics || [])[0];
  const startWord = (d, on) => {
    if (d.sport === "mlb") return on ? "Started" : d.lead === "pa" ? "Off the bench" : "In relief";
    if (d.sport === "nhl") return on ? "Started" : "In relief";
    return on ? "Started" : "Off the bench";
  };
  function gameName(g, d) {
    const when = d.sport === "nfl" && g.week ? `W${g.week}` : (() => {
      const t = g.date ? new Date(g.date + "T12:00:00") : null;
      return t && !isNaN(t) ? t.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
    })();
    return `${when} ${g.home === false ? "@" : g.home ? "vs" : "v"} ${g.opp}`.trim();
  }

  /* ---------------- the strips ---------------- */
  const W = 420, PAD = 6;
  /* A share is drawn against the most of it he had (a fifth of the
     targets would be a sliver against all of them), never past all. */
  function scale(m, vals) {
    const hi = Math.max(0, ...vals.filter((v) => v != null));
    if (m.unit === "pct") return Math.min(1, Math.max(0.2, hi * 1.12));
    if (m.unit === "spot") return 9;
    return hi > 0 ? hi * 1.08 : 1;
  }
  const frac = (m, v, top) => (m.unit === "spot" ? (10 - Math.min(9, Math.max(1, v))) / 9 : Math.max(0, v) / top);
  /* `on` is the oldest-first index of the game lit (By game), or -1 to
     light his last three (the season). */
  function strips(d, on, label) {
    const games = d.games.slice().reverse(), n = games.length;
    const slot = (W - 2 * PAD) / n, bw = Math.max(2, Math.min(24, slot * 0.66));
    const sport = d.sport, L = d.season_line || {}, game = on >= 0;
    let y = 0, body = "";
    d.metrics.forEach((m, mi) => {
      const H = m.key === d.lead ? 74 : 40;
      const vals = games.map((g) => (g.v || {})[m.key]);
      const top = scale(m, vals), avg = (L.avg || {})[m.key];
      const base = y + 30 + H;
      const right = game ? (vals[on] == null ? "—" : `${fmt(m, vals[on], sport)} · avg ${fmt(m, avg, sport, true)}`)
        : `avg ${fmt(m, avg, sport, true)} · last 3 ${fmt(m, (L.last3 || {})[m.key], sport, true)}`;
      body += `<g class="cc-carry rl-strip" data-i="${mi}"><rect class="rl-hit" x="0" y="${y}" width="${W}" height="${H + 40}"/>
        <text class="rl-name" x="${PAD}" y="${y + 14}">${esc(m.name)}</text>
        <text class="rl-avg" x="${W - PAD}" y="${y + 14}" text-anchor="end">${esc(right)}</text>
        <line class="rl-base" x1="${PAD}" x2="${W - PAD}" y1="${base}" y2="${base}"/>`;
      // His average under the bars, so a game's number reads over it.
      if (avg != null) {
        const ay = base - frac(m, avg, top) * H;
        body += `<line class="rl-mean" x1="${PAD}" x2="${W - PAD}" y1="${ay.toFixed(1)}" y2="${ay.toFixed(1)}"/>`;
      }
      // Each game's number over its bar, where every one of them fits.
      const words = vals.map((v) => (v == null ? "" : fmt(m, v, sport)));
      const label = n <= 12 && Math.max(...words.map((x) => x.length)) * 6.8 <= slot - 2;
      vals.forEach((v, i) => {
        if (v == null) return;
        const h = Math.max(2, frac(m, v, top) * H), x = PAD + slot * i + (slot - bw) / 2;
        const lit = game ? i === on : i >= n - 3;
        const cls = `rl-bar${lit ? " on" : ""}${game && i === on ? ` cx-mark${sel(mi)}` : ""}`;
        body += `<rect class="${cls}"${game ? ` data-gi="${n - 1 - i}"` : ""} x="${x.toFixed(1)}" y="${(base - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2"/>`;
        if (label) {
          body += `<text class="rl-val${lit ? " on" : ""}" x="${(x + bw / 2).toFixed(1)}" y="${(base - h - 3).toFixed(1)}" text-anchor="middle">${esc(words[i])}</text>`;
        }
      });
      body += "</g>";
      y = base + 12;
    });
    /* Under the strips: each game's name where they fit, else the first
       and the last; and whether he started, where the box says. */
    const every = n <= 9, few = n <= 18;
    games.forEach((g, i) => {
      const x = PAD + slot * i + slot / 2;
      const show = every || (few && i % 2 === (n - 1) % 2) || i === 0 || i === n - 1;
      if (show) {
        const t = d.sport === "nfl" && g.week ? `W${g.week}` : (g.date || "").slice(5).replace("-", "/");
        body += `<text class="rl-x${game && i === on ? " on" : ""}" x="${x.toFixed(1)}" y="${y + 10}" text-anchor="middle">${esc(t)}</text>`;
      }
      if (g.start != null) {
        body += `<circle class="rl-start${g.start ? " s" : ""}" cx="${x.toFixed(1)}" cy="${y + 20}" r="${Math.min(3.4, slot / 3).toFixed(1)}"/>`;
      }
    });
    const tall = y + (games.some((g) => g.start != null) ? 28 : 16);
    return `<svg class="cc-svg rl-svg" viewBox="0 0 ${W} ${tall}" role="img" aria-label="${esc(label)}">${body}</svg>`;
  }
  const S_LIT = { game: "This game", season: "His last 3" };
  function legend(d) {
    const starts = d.games.some((g) => g.start != null);
    return `<div class="cc-legend" aria-hidden="true"><span><i class="dt rl-k"></i>${S_LIT[st().view] || "This game"}</span>
      <span><i class="dt rl-m"></i>His average</span>${starts ? `<span><i class="dt rl-s"></i>${esc(startWord(d, true))}</span>` : ""}</div>`;
  }
  /* ---------------- the numbers ---------------- */
  function gameTiles(g, d) {
    const L = d.season_line || {};
    const t = d.metrics.slice(0, 6).map((m) => tile(m.short, fmt(m, (g.v || {})[m.key], d.sport),
      `avg ${fmt(m, (L.avg || {})[m.key], d.sport, true)}`));
    if (g.start != null && t.length < 6) t.push(tile("Role", g.start ? "Started" : startWord(d, false).replace("Off the bench", "Bench")));
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function seasonTiles(d) {
    const L = d.season_line || {}, m = lead(d), k = m.key;
    const second = d.metrics.find((x) => x.key !== k && x.unit !== "pct");
    const t = [tile("Games", L.games, L.starts != null ? `${L.starts} started` : ""),
               tile(m.short, fmt(m, L.avg[k], d.sport, true), "a game"),
               tile("Last 3", fmt(m, L.last3[k], d.sport, true), trend(m, L.last3[k], L.avg[k])),
               tile("Last 5", fmt(m, L.last5[k], d.sport, true), trend(m, L.last5[k], L.avg[k])),
               tile(m.unit === "spot" ? "Highest" : "High", fmt(m, m.unit === "spot" ? L.low[k] : L.high[k], d.sport))];
    if (second) t.push(tile(second.short, fmt(second, L.avg[second.key], d.sport, true), "a game"));
    return `<div class="cc-tiles cc-tiles-6">${t.join("")}</div>`;
  }
  function trend(m, a, b) {
    if (a == null || b == null || Math.abs(a - b) < 1e-9) return "even with his season";
    return better(m, a, b) ? "up on his season" : "down on his season";
  }
  function rowList(g, d) {
    const L = d.season_line || {};
    return `<div class="cc-list" role="list">${d.metrics.map((m, i) => {
      const v = (g.v || {})[m.key], a = (L.avg || {})[m.key];
      const b = v == null || a == null || Math.abs(v - a) < 1e-9 ? "short" : better(m, v, a) ? "gain" : "loss";
      return `<button type="button" role="listitem" class="cc-row${sel(i)}" data-i="${i}">
        <i class="dot ${b}"></i>
        <span class="cc-r-h">${esc(m.name)}</span>
        <span class="cc-r-dd">avg ${esc(fmt(m, a, d.sport, true))}</span>
        <b class="cc-r-y ${b}">${esc(fmt(m, v, d.sport))}</b>
        <span class="cc-r-tags"><em>last 3 ${esc(fmt(m, (L.last3 || {})[m.key], d.sport, true))}</em><em>${esc(m.unit === "spot" ? "highest" : "high")} ${esc(fmt(m, m.unit === "spot" ? (L.low || {})[m.key] : (L.high || {})[m.key], d.sport))}</em></span>
      </button>`;
    }).join("")}</div>`;
  }
  function tables(d) {
    const L = d.season_line || {}, f = (m, v) => fmt(m, v, d.sport, true), out = [];
    out.push(tableHTML("His stretch, beside his season", ["", "Last 3", "Last 5", "Season", "High"],
      d.metrics.map((m) => [m.name, f(m, L.last3[m.key]), f(m, L.last5[m.key]), f(m, L.avg[m.key]),
        fmt(m, m.unit === "spot" ? L.low[m.key] : L.high[m.key], d.sport)])));
    const two = (rows, cap) => {
      if (!rows || rows.length < 2) return;
      out.push(tableHTML(cap, ["", ...rows.map((r) => `${r.name} (${r.n})`)],
        d.metrics.map((m) => [m.name, ...rows.map((r) => f(m, (r.avg || {})[m.key]))])));
    };
    two((d.splits || {}).place, "Home and away");
    two((d.splits || {}).start, d.sport === "mlb" && d.lead === "pa" ? "In the lineup or off the bench" : "Started or not");
    return out.join("");
  }

  /* ---------------- how it's drawn ---------------- */
  const NOTE = {
    nfl: "Snap share is his share of the offence’s snaps (nflverse’s snap counts). Target and carry shares are of every target or carry his team’s players were credited with that game. Red-zone looks are his targets and carries inside the 20, from the play-by-play. Air yards are how far past the line the passes thrown his way travelled.",
    cfb: "Carries, catches and attempts are the box score’s. Shares are of every carry or catch his team’s players were credited with that game; red-zone touches are his carries and catches inside the 20, from the play file (it names no college target).",
    nba: "Minutes and whether he started are the box score’s; shots from the floor, threes and free throws tried are from the NBA’s play-by-play (the shot chart’s).",
    wnba: "Minutes and whether she started are the box score’s.",
    mlb: "Plate appearances and outs are the box score’s. His spot in the order is where he came up among his side’s first nine batters; pitches seen or thrown, batters faced and whether he started are from the play-by-play (the pitch chart’s). Days of rest count every game he pitched.",
    nhl: "Ice time, shots on goal and shots faced are the box score’s; shot attempts (on goal, missed and blocked) and those on the power play are from the play-by-play the expected-goals model reads.",
  };

  Q.draw("role", {
    one: "number", splitsTitle: "Every split · his stretch, home and away, started or not",
    listTitle: (g, d = now()) => `That game beside his season · ${(d.metrics || []).length} numbers`,
    items: (g, d = now()) => d.metrics || [],
    count: (L, d = now()) => {
      const m = lead(d), a = (L.avg || {})[m.key];
      if (m.unit === "pct") return `${pct(a)} of ${m.short.toLowerCase()}`;
      if (m.unit === "min") return `${fmt(m, a, d.sport, true)} ${d.sport === "nhl" ? "a night" : "minutes a game"}`;
      if (m.unit === "spot") return `batting ${num1(a)} on average`;
      const total = (d.games || []).reduce((s, g) => s + ((g.v || {})[m.key] || 0), 0);
      return `${Math.round(total).toLocaleString()} ${m.name.toLowerCase()}`;
    },
    chip: (g, d = now()) => {
      const m = lead(d), v = (g.v || {})[m.key];
      return v == null ? "—" : `${fmt(m, v, d.sport)} ${CHIP[m.key] || ""}`.trim();
    },
    game: (g, d) => strips(d, d.games.length - 1 - d.games.indexOf(g),
      `His role by game, ${gameName(g, d)} lit: ${d.metrics.map((m) => m.name.toLowerCase()).join(", ")}. Every number is listed below.`),
    season: (d) => strips(d, -1, `His role over the season, game by game: ${d.metrics.map((m) => m.name.toLowerCase()).join(", ")}.`),
    gameSide: (g, d) => `${legend(d)}${gameTiles(g, d)}`,
    seasonSide: (d) => `${legend(d)}${seasonTiles(d)}`,
    list: (g, d) => rowList(g, d),
    splits: (d) => tables(d),
    note: (d) => `<p class="cc-note">Each bar is one of his games, the oldest on the left; the dashed line is his average over the season’s games on file. A gap is a game with that number not on file, never a zero. ${NOTE[d.sport] || ""} The chart describes his role; it does not move any price on the site.</p>`,
    tip: (m, g, d) => {
      const L = d.season_line || {}, v = (g.v || {})[m.key];
      return `<b>${esc(m.name)} ${esc(fmt(m, v, d.sport))}</b> · ${esc(gameName(g, d))}
        <span>${esc([`his season ${fmt(m, (L.avg || {})[m.key], d.sport, true)}`, `last 3 ${fmt(m, (L.last3 || {})[m.key], d.sport, true)}`,
          `${m.unit === "spot" ? "highest" : "high"} ${fmt(m, m.unit === "spot" ? (L.low || {})[m.key] : (L.high || {})[m.key], d.sport)}`].join(" · "))}</span>`;
    },
  });
})();
