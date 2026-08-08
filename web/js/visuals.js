/* visuals.js — procedural SVG art for the dashboard.
 *
 * Everything here is drawn as self-contained SVG (no external images, so it
 * works offline and inside a strict CSP): cartoony team-colored player avatars,
 * an animated wind gauge, and stylized aerial stadiums whose roof / surface /
 * colors reflect each game's real attributes.
 *
 * Real player headshots (nflverse/ESPN provide URLs) can be dropped in later:
 * playerAvatar() uses rec.headshot if present and falls back to the SVG.
 */

const DEFAULT_TEAM = { name: "", nick: "", primary: "#3a4668", secondary: "#8893b5", tertiary: "#dfe4f5" };
// app.js points window.ACTIVE_TEAMS at the current sport's color dict
// (NFL TEAMS or MLB_TEAMS) — abbreviations collide across leagues, so a
// page whose sport NEVER changes (Fantasy is always football) must pass
// its own map instead of inheriting whichever tab the user came from:
// arriving at Fantasy from the MLB board once rendered the Vikings as
// the Twins and the Ravens as the Orioles.
function team(abbr, src = null) {
  const dict = src
    || (typeof window !== "undefined" && window.ACTIVE_TEAMS)
    || (typeof TEAMS !== "undefined" ? TEAMS : {});
  return dict[abbr] || DEFAULT_TEAM;
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/);
  const a = parts[0]?.[0] || "";
  const b = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (a + b).toUpperCase();
}

// Readable text color for a given background hex.
function idealText(hex) {
  const h = (hex || "#000").replace("#", "");
  const r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#10152a" : "#ffffff";
}

/* ---------------- Player avatar (cartoony helmet headshot) --------------- */
/* When opts.headshot is a real photo URL (nflverse/ESPN), it is layered over
 * the SVG helmet; if the image fails to load it removes itself and the helmet
 * shows through — so offline/sample data degrades gracefully. */
/* A headshot at the size it is actually drawn.
   ------------------------------------------------------------------------
   nflverse ships the full-resolution file, and full resolution here means
   3,797,822 / 3,145,446 / 4,307,894 bytes — measured on Ethan's machine,
   2026-08-08, for the first three players in the roster. A board of twelve
   props draws them at 40px and would pull roughly 45MB to do it. That is
   not a polish feature, it is a stall.

   These are Cloudinary URLs — `/image/upload/<transforms>/league/<id>` —
   so the size goes in the path. WHICH transforms this account permits has
   not been verified: the probe asks, and until it answers this is a guess,
   which is the thing that has cost this session three times.

   So it is a guess that cannot fail closed. The <img> starts on the
   resized URL and carries the original in `data-full`; the first error
   swaps to the original, and only a second error gives up and reveals the
   initials avatar underneath. Wrong transform costs one 404 and a heavy
   image — the behaviour that shipped before. Dead host costs the initials,
   also the behaviour that shipped before. */
const FACE_TRANSFORM = "w_${W},h_${W},c_fill,g_face";

/* ESPN's own faces, which the NBA and WNBA boards draw.
   ------------------------------------------------------------------------
   Those URLs are TAKEN from the box score, so they are right — and they are
   the full-resolution file. Measured on Ethan's machine, 2026-08-08: one
   ESPN full headshot is 196,283 bytes. A dozen props is ~2.4MB of face to
   draw at 56px.

   The combiner is the same server-side resize the logos already use, where
   it measured 40,228 bytes against 11,537, and the request is built to
   match that verified call exactly: the path goes in raw, slashes and all,
   because that is the form that answered 200. Whether the combiner serves
   /i/headshots the way it serves /i/teamlogos is NOT verified, so this is
   still a guess — and it fails onto the untransformed href, which the probe
   did verify, and then onto the initials chip. */
function espnFacePreview(url, px) {
  const host = "a.espncdn.com";
  const i = url.indexOf(host);
  if (i < 0 || url.indexOf("/combiner/") >= 0) return url;   // already sized
  const path = url.slice(i + host.length).split("?")[0];
  if (!path) return url;
  const w = Math.max(48, Math.round(px * 2));
  return `https://${host}/combiner/i?img=${path}&w=${w}&h=${w}`;
}

function facePreview(url, px) {
  if (!url) return url;
  if (url.indexOf("a.espncdn.com") >= 0) return espnFacePreview(url, px);
  const marker = "/image/upload/";
  if (url.indexOf(marker) < 0) return url;           // not a Cloudinary URL
  const [head, tail] = url.split(marker);
  const id = tail.indexOf("/") >= 0 ? tail.slice(tail.indexOf("/") + 1) : tail;
  const w = Math.max(48, Math.round(px * 2));        // 2x for retina
  return `${head}${marker}f_auto,q_auto,${
    FACE_TRANSFORM.replace(/\$\{W\}/g, w)}/${id}`;
}

function playerAvatar(name, abbr, opts = {}) {
  const size = opts.size || 56;
  if (opts.headshot) {
    const inner = playerAvatar(name, abbr, { ...opts, headshot: null });
    const small = facePreview(opts.headshot, size);
    const swap = small === opts.headshot ? "this.remove()"
      : "if(this.dataset.full){this.src=this.dataset.full;this.removeAttribute('data-full');}"
        + "else{this.remove();}";
    return `<span class="avatar-stack" style="width:${size}px;height:${size}px">${inner}
      <img class="avatar-photo" src="${escapeAttr(small)}" alt="" loading="lazy"
           decoding="async"${small === opts.headshot ? ""
             : ` data-full="${escapeAttr(opts.headshot)}"`}
           onerror="${swap}"/></span>`;
  }
  const t = team(abbr, opts.map);
  const uid = "a" + Math.random().toString(36).slice(2, 8);
  const ini = initials(name);
  const stripe = t.secondary;
  const mask = "#c9d2e8";
  if ((window.ACTIVE_SPORT || "nfl") === "mlb") {
    // A stylized baseball cap in team colors — avatar, not a likeness.
    return `
  <svg class="avatar" width="${size}" height="${size}" viewBox="0 0 64 64" role="img"
       aria-label="${escapeAttr(name)}">
    <defs>
      <radialGradient id="${uid}bg" cx="50%" cy="35%" r="75%">
        <stop offset="0%" stop-color="${t.primary}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -28)}"/>
      </radialGradient>
      <linearGradient id="${uid}cp" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${shade(t.primary, 26)}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -14)}"/>
      </linearGradient>
    </defs>
    <circle cx="32" cy="32" r="32" fill="url(#${uid}bg)"/>
    <!-- cap crown -->
    <path d="M15 33 a17 15 0 0 1 34 0 l0 3 -34 0 z"
          fill="url(#${uid}cp)" stroke="${shade(t.primary,-38)}" stroke-width="1"/>
    <!-- panel seams -->
    <g fill="none" stroke="${shade(t.primary,-30)}" stroke-width="1" opacity="0.8">
      <path d="M32 18 v18"/>
      <path d="M23 21 q-2 7 -1 15"/>
      <path d="M41 21 q2 7 1 15"/>
    </g>
    <!-- button -->
    <circle cx="32" cy="18" r="1.8" fill="${stripe}"/>
    <!-- brim -->
    <path d="M14 36 q18 8 37 1 q1 3 -1 4 q-18 8 -37 -1 q0 -3 1 -4 z"
          fill="${shade(t.primary, -20)}" stroke="${shade(t.primary,-40)}" stroke-width="1"/>
    <!-- team letter on the crown -->
    <text x="32" y="33" text-anchor="middle" font-family="system-ui, sans-serif"
          font-size="10" font-weight="800" fill="${stripe}">${escapeAttr((abbr || "?")[0])}</text>
    <!-- initials nameplate -->
    <g>
      <rect x="17" y="52" width="30" height="11" rx="5.5" fill="${idealText(t.primary)==='#ffffff'?'#0c1020':'#ffffffcc'}" opacity="0.85"/>
      <text x="32" y="60.3" text-anchor="middle" font-family="system-ui, sans-serif"
            font-size="8" font-weight="700"
            fill="${idealText(t.primary)==='#ffffff'?'#ffffff':'#10152a'}">${ini}</text>
    </g>
  </svg>`;
  }
  if ((window.ACTIVE_SPORT || "nfl") === "nba") {
    // A stylized basketball in team colors — avatar, not a likeness.
    return `
  <svg class="avatar" width="${size}" height="${size}" viewBox="0 0 64 64" role="img"
       aria-label="${escapeAttr(name)}">
    <defs>
      <radialGradient id="${uid}bg" cx="50%" cy="35%" r="75%">
        <stop offset="0%" stop-color="${t.primary}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -30)}"/>
      </radialGradient>
      <radialGradient id="${uid}ball" cx="42%" cy="34%" r="72%">
        <stop offset="0%" stop-color="${shade(t.primary, 34)}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -8)}"/>
      </radialGradient>
    </defs>
    <circle cx="32" cy="32" r="32" fill="url(#${uid}bg)"/>
    <circle cx="32" cy="28" r="16" fill="url(#${uid}ball)"
            stroke="${shade(t.primary, -36)}" stroke-width="1.4"/>
    <g fill="none" stroke="${stripe}" stroke-width="1.5" opacity="0.9">
      <line x1="32" y1="12" x2="32" y2="44"/>
      <line x1="16" y1="28" x2="48" y2="28"/>
      <path d="M20 16 q6 12 0 24"/>
      <path d="M44 16 q-6 12 0 24"/>
    </g>
    <g>
      <rect x="17" y="50" width="30" height="11" rx="5.5"
            fill="${idealText(t.primary)==='#ffffff'?'#0c1020':'#ffffffcc'}" opacity="0.85"/>
      <text x="32" y="58.3" text-anchor="middle" font-family="system-ui, sans-serif"
            font-size="8" font-weight="700"
            fill="${idealText(t.primary)==='#ffffff'?'#ffffff':'#10152a'}">${ini}</text>
    </g>
  </svg>`;
  }
  // A stylized football helmet in team colors — avatar, not a likeness.
  return `
  <svg class="avatar" width="${size}" height="${size}" viewBox="0 0 64 64" role="img"
       aria-label="${escapeAttr(name)}">
    <defs>
      <radialGradient id="${uid}bg" cx="50%" cy="35%" r="75%">
        <stop offset="0%" stop-color="${t.primary}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -28)}"/>
      </radialGradient>
      <linearGradient id="${uid}sh" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${shade(t.primary, 22)}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -18)}"/>
      </linearGradient>
    </defs>
    <circle cx="32" cy="32" r="32" fill="url(#${uid}bg)"/>
    <!-- helmet shell -->
    <path d="M14 34 a18 17 0 0 1 36 -2 c0 6 -2 9 -4 11 l-2 -1 a15 14 0 0 0 -26 -12 z"
          fill="url(#${uid}sh)" stroke="${shade(t.primary,-35)}" stroke-width="1"/>
    <!-- center stripe -->
    <path d="M32 15 c7 0 12 5 13 12 l-4 1 c-1 -6 -4 -9 -9 -9 z" fill="${stripe}" opacity="0.95"/>
    <!-- jaw / chin area -->
    <path d="M24 43 a11 10 0 0 0 18 -3 l3 2 c-2 7 -9 12 -16 11 -4 -1 -7 -4 -8 -8 z"
          fill="${shade(t.primary,-22)}"/>
    <!-- facemask -->
    <g fill="none" stroke="${mask}" stroke-width="1.6" stroke-linecap="round" opacity="0.9">
      <path d="M42 34 q6 3 4 10"/>
      <path d="M40 40 q5 1 5 5"/>
      <path d="M30 45 h11"/>
    </g>
    <!-- ear hole -->
    <circle cx="26" cy="34" r="2.4" fill="${shade(t.primary,-40)}"/>
    <!-- initials nameplate -->
    <g>
      <rect x="17" y="52" width="30" height="11" rx="5.5" fill="${idealText(t.primary)==='#ffffff'?'#0c1020':'#ffffffcc'}" opacity="0.85"/>
      <text x="32" y="60.3" text-anchor="middle" font-family="system-ui, sans-serif"
            font-size="8" font-weight="700"
            fill="${idealText(t.primary)==='#ffffff'?'#ffffff':'#10152a'}">${ini}</text>
    </g>
  </svg>`;
}

/* ---------------- Team logo mark (procedural monogram) ------------------- */
/* ---------------- Real team logos ---------------------------------------
   ESPN's CDN serves every league we cover. Verified 2026-08-08 from
   Ethan's machine, all five keys, HTTP 200 image/png.

   THE COMBINER PATH, NOT THE RAW ONE. `/combiner/i?img=…&w=&h=` resizes
   server-side, and the difference is not small: the raw 500px NFL mark is
   40,228 bytes against 11,537 for the combiner, MLB 20,024 against 7,739.
   A board draws twenty of these, so it is the difference between ~800KB
   and ~230KB of logo on one page load.

   ESPN SPELLS SOME TEAMS DIFFERENTLY FROM US, and the map below is
   recalled rather than measured for everything except the five the probe
   actually tested. That is why `teamMark` layers the image OVER the
   existing monogram instead of replacing it: a wrong abbreviation, a dead
   host or no network at all removes the <img> and leaves exactly the chip
   that shipped before this change. There is no state in which this is
   worse than what it replaced.

   `assets.py --audit` walks every abbreviation in every teams file and
   reports which ones 404, so the misses get fixed from a measurement
   rather than from memory. Run it before trusting this map. */
const ESPN_LEAGUE = { nfl: "nfl", cfb: "ncaa", mlb: "mlb", nba: "nba", wnba: "wnba" };

const ESPN_ABBR = {
  nfl:  { WAS: "wsh", LA: "lar", ARZ: "ari", SD: "lac", STL: "lar", OAK: "lv" },
  mlb:  { CWS: "chw", TBR: "tb" },
  nba:  { NOP: "no", NYK: "ny", GSW: "gs", SAS: "sa", UTA: "utah", PHX: "phx" },
  wnba: { CON: "conn", GSV: "gs", LAS: "la", LVA: "lv", NYL: "ny", WAS: "wsh" },
  cfb:  {},
};

function logoUrl(abbr, sport, size = 48) {
  const key = ESPN_LEAGUE[(sport || "").toLowerCase()];
  if (!key || !abbr) return "";
  const a = (ESPN_ABBR[sport.toLowerCase()] || {})[String(abbr).toUpperCase()]
            || String(abbr).toLowerCase();
  return `https://a.espncdn.com/combiner/i?img=/i/teamlogos/${key}/500/${
    encodeURIComponent(a)}.png&w=${size * 2}&h=${size * 2}`;
}

/* `src` is the TEAM DICTIONARY — the same third argument `team()` takes —
   and `sport` is separate. They were briefly the same parameter, and the one
   call site that passes a real dictionary (offseasonHTML, which is always
   NFL whatever tab you came from) reached `(sport || "").toLowerCase()` with
   an object and threw, taking the whole coach-change section down with it. A
   string in `src` is still read as the sport, so neither reading breaks.

   The ESPN id wins over the abbreviation when the team record carries one.
   That is what makes college work: ESPN keys 134 schools numerically, the
   ids come off ESPN's own teams feed at build time and ride in the slate
   payload, and the alternative was a hand-written 134-row map that would rot
   the first time a school rebranded. Our other four sports have no id in
   their colour dicts, so they keep using the abbreviation. */
function teamMark(abbr, size = 20, src = null, sport = null) {
  const map = typeof src === "string" ? null : src;
  const t = team(abbr, map);
  const uid = "tm" + Math.random().toString(36).slice(2, 7);
  const league = sport || (typeof src === "string" ? src : "")
    || (typeof state !== "undefined" ? state.sport : "") || "nfl";
  const url = logoUrl(t.id || abbr, league, size);
  // The monogram stays underneath. `onerror` removes only the image, so a
  // bad abbreviation or a dead CDN lands on the chip this used to be.
  const img = url
    ? `<img class="team-logo" src="${escapeAttr(url)}" width="${size}"
            height="${size}" alt="" loading="lazy" decoding="async"
            onerror="this.remove()">`
    : "";
  return `<span class="team-mark-wrap" style="width:${size}px;height:${size}px"
                role="img" aria-label="${escapeAttr(abbr)}">
  <svg class="team-mark" width="${size}" height="${size}" viewBox="0 0 24 24"
       aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="${shade(t.primary, 20)}"/>
        <stop offset="100%" stop-color="${shade(t.primary, -24)}"/>
      </linearGradient>
    </defs>
    <rect x="1" y="1" width="22" height="22" rx="6.5" fill="url(#${uid})"
          stroke="${shade(t.primary, -40)}" stroke-width="1"/>
    <path d="M1 16 L23 7 L23 10.4 L1 19.4 Z" fill="${t.secondary}" opacity="0.4"/>
    <text x="12" y="15.8" text-anchor="middle" font-family="system-ui, sans-serif"
          font-size="8" font-weight="800"
          fill="${idealText(t.primary)}">${escapeAttr(String(abbr).slice(0, 3))}</text>
  </svg>${img}</span>`;
}

/* ---------------- Animated wind gauge ------------------------------------ */
const COMPASS = { N:0, NNE:22.5, NE:45, ENE:67.5, E:90, ESE:112.5, SE:135, SSE:157.5,
  S:180, SSW:202.5, SW:225, WSW:247.5, W:270, WNW:292.5, NW:315, NNW:337.5,
  // MLB park-relative directions: "out" = blowing toward the outfield (up).
  OUT:180, IN:0, CROSS:270 };

function windGauge(weather, opts = {}) {
  const size = opts.size || 92;
  if (weather.dome) {
    return `
    <div class="wind dome" title="Climate-controlled dome">
      <svg width="${size}" height="${size}" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r="40" fill="#141b33" stroke="#2b365a" stroke-width="2"/>
        <path d="M22 52 a24 20 0 0 1 48 0 z" fill="#1d2647" stroke="#3a4a7a" stroke-width="1.5"/>
        <!-- A diamond under the roof, not a stadium glyph inside a stadium:
             the arc above IS the dome, so repeating it here just read as an
             eye at render size. Screenshotted before and after. -->
        <path d="M46 37 L53 44 L46 51 L39 44 z" fill="none" stroke="#7f8dc4"
              stroke-width="1.6" stroke-linejoin="round"/>
        <text x="46" y="66" text-anchor="middle" font-size="9" fill="#9aa6c9" font-family="system-ui">DOME</text>
      </svg>
    </div>`;
  }
  const mph = weather.wind_mph || 0;
  const fromDeg = COMPASS[(weather.wind_dir || "").toUpperCase()] ?? null;
  const blowDeg = fromDeg == null ? 90 : (fromDeg + 180) % 360; // direction wind travels
  // Stronger wind -> faster streamlines and more of them.
  const dur = Math.max(0.5, 3.2 - Math.min(mph, 30) * 0.09).toFixed(2);
  const intensity = mph >= 20 ? "high" : mph >= 12 ? "med" : "low";
  const uid = "w" + Math.random().toString(36).slice(2, 7);
  const lines = [30, 40, 50, 60].map((y, i) => `
    <line class="stream s${i}" x1="14" y1="${y}" x2="70" y2="${y}"
          stroke="url(#${uid}g)" stroke-width="2.4" stroke-linecap="round"
          stroke-dasharray="10 14" style="animation-duration:${dur}s"/>`).join("");
  return `
  <div class="wind ${intensity}" title="Wind ${mph} mph${weather.wind_dir ? " from " + weather.wind_dir : ""}">
    <svg width="${size}" height="${size}" viewBox="0 0 92 92">
      <defs>
        <linearGradient id="${uid}g" x1="0" x2="1">
          <stop offset="0%" stop-color="#4f8cff" stop-opacity="0"/>
          <stop offset="45%" stop-color="#6fd3ff"/>
          <stop offset="100%" stop-color="#37d67a"/>
        </linearGradient>
      </defs>
      <circle cx="46" cy="46" r="40" fill="#0f1730" stroke="#2b365a" stroke-width="2"/>
      <!-- streamlines rotated to wind travel direction -->
      <g transform="rotate(${blowDeg} 46 46)">${lines}
        <polygon points="70,45 78,41 78,49" fill="#37d67a"/>
      </g>
      <!-- compass ticks + N -->
      <text x="46" y="15" text-anchor="middle" font-size="8" fill="#7c86a8" font-family="system-ui">N</text>
      <circle cx="46" cy="46" r="15" fill="#0c1020" opacity="0.7"/>
      <text class="num" x="46" y="44" text-anchor="middle" font-size="13" font-weight="800"
            fill="#eaeefb">${Math.round(mph)}</text>
      <text x="46" y="55" text-anchor="middle" font-size="7" fill="#9aa6c9" font-family="system-ui">MPH</text>
    </svg>
  </div>`;
}

/* ---------------- Aerial stadium ----------------------------------------- */
function stadium(game, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const home = team(game.home), away = team(game.away);
  const roof = (game.roof || "").toLowerCase();
  const covered = roof === "dome" || roof === "closed";
  const retractable = roof === "open";
  const turf = /turf|astro|matrix|sport/.test((game.surface || "grass").toLowerCase());
  const grass = turf ? "#1f7a46" : "#2a9d54";
  const grassDark = turf ? "#186038" : "#1f7d41";
  const uid = "s" + Math.random().toString(36).slice(2, 7);
  const yardLines = Array.from({ length: 9 }, (_, i) =>
    `<line x1="${70 + i * 12}" y1="52" x2="${70 + i * 12}" y2="108" stroke="#ffffff" stroke-opacity="0.5" stroke-width="1"/>`
  ).join("");
  const lights = covered ? "" : [[36,40],[204,40],[36,120],[204,120]].map(([x,y]) =>
    `<g><line x1="${x}" y1="${y}" x2="${x + (x<120?10:-10)}" y2="${y+(y<80?8:-8)}" stroke="#5b6b95" stroke-width="2"/>
      <circle cx="${x}" cy="${y}" r="3.4" fill="#fff4c2"/><circle cx="${x}" cy="${y}" r="6" fill="#fff4c2" opacity="0.25"/></g>`
  ).join("");
  // THE BALL, WHERE THE BALL IS.
  //
  // Ethan, 2026-08-08: "we can coninue that idea onto football by
  // displaying what yard line the players are on along with what down
  // they are on that the quarter and time left."
  //
  // The quarter and the clock are already in the LIVE badge over this
  // art, and the down and distance is already the footer line, so what
  // was actually missing is field position — the one thing prose is worst
  // at and a drawing is best at.
  //
  // Geometry, which is the whole trick: the field rect runs x=52..188
  // with an 18-wide end zone at each end, so goal line to goal line is
  // exactly x=70..170. `yard_line` is defined as 0-100 from the HOME
  // goal line and the home end zone is the left one, so the spot is
  // simply x = 70 + yard. No scaling, no offset, nothing to get backwards.
  //
  // FAILS OPEN, and it will be closed most of the time: `yard_line` is
  // null for every scheduled game, every final, every college game (that
  // feed is a different parser and does not carry a spot yet), and any
  // live game whose spot string does not resolve to a side. All of those
  // draw the field exactly as it was before this existed.
  const lv = game.live || {};
  const yard = lv.state === "live" && lv.yard_line != null ? Number(lv.yard_line) : null;
  let drive = "";
  if (yard != null && Number.isFinite(yard)) {
    const x = 70 + Math.max(0, Math.min(100, yard));
    // Home drives toward the away end zone, which is the right one.
    // Unknown possession draws the spot and no arrow rather than a
    // guessed direction — half the fact is better than a wrong one.
    const dir = lv.possession === game.away ? -1 : lv.possession === game.home ? 1 : 0;
    // The arrow sits 7px downfield of the spot and is dropped rather than
    // clamped when that lands past the goal line: an arrow pinned to the
    // end zone would read as a spot of its own.
    const ax = x + dir * 7;
    const arrow = dir && ax > 71 && ax < 169
      ? `<path d="M${ax} 55 l${dir * 5} 3 l${-dir * 5} 3 z" fill="#ffd24a" opacity="0.95"/>`
      : "";
    // The dark backing line is not decoration. The field is nine white
    // yard stripes on green; one more thin bright line among them is just
    // a tenth stripe. The dark edge is what makes this one read as a
    // marker laid ON the field rather than painted into it.
    drive = `
      <g>
        <line x1="${x}" y1="50" x2="${x}" y2="110" stroke="#0c1020" stroke-width="3.6" opacity="0.45"/>
        <line x1="${x}" y1="50" x2="${x}" y2="110" stroke="#ffd24a" stroke-width="1.8"/>
        <ellipse cx="${x}" cy="58" rx="4.2" ry="2.8" fill="#8a4b22" stroke="#ffffff" stroke-width="1"/>
        ${arrow}
      </g>`;
  }
  const roofOverlay = covered ? `
    <ellipse cx="120" cy="80" rx="108" ry="66" fill="url(#${uid}roof)" opacity="0.8"/>
    <ellipse cx="120" cy="80" rx="108" ry="66" fill="none" stroke="${shade(home.primary,20)}" stroke-width="2"/>
    <g stroke="#ffffff" stroke-opacity="0.12" stroke-width="1">
      <line x1="120" y1="16" x2="120" y2="144"/><line x1="24" y1="80" x2="216" y2="80"/>
      <line x1="52" y1="30" x2="188" y2="130"/><line x1="188" y1="30" x2="52" y2="130"/>
    </g>
    <text x="120" y="26" text-anchor="middle" font-size="9" fill="#dfe4f5" font-family="system-ui" opacity="0.85">
      ${roof === "closed" ? "RETRACTABLE · CLOSED" : "DOME"}</text>` :
    (retractable ? `<text x="120" y="24" text-anchor="middle" font-size="9" fill="#9aa6c9"
        font-family="system-ui">RETRACTABLE · OPEN</text>` : "");

  return `
  <svg class="stadium" width="${w}" height="${h}" viewBox="0 0 240 150" preserveAspectRatio="xMidYMid meet">
    <defs>
      <radialGradient id="${uid}sky" cx="50%" cy="30%" r="80%">
        <stop offset="0%" stop-color="${covered ? "#0f1730" : "#16233f"}"/>
        <stop offset="100%" stop-color="#0a0f22"/>
      </radialGradient>
      <linearGradient id="${uid}stand" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${shade(home.primary,10)}"/>
        <stop offset="100%" stop-color="${shade(home.primary,-30)}"/>
      </linearGradient>
      <radialGradient id="${uid}roof" cx="50%" cy="40%" r="70%">
        <stop offset="0%" stop-color="${shade(home.primary,35)}"/>
        <stop offset="100%" stop-color="${shade(home.primary,-10)}"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="240" height="150" fill="url(#${uid}sky)"/>
    <!-- outer stands bowl -->
    <ellipse cx="120" cy="80" rx="112" ry="64" fill="url(#${uid}stand)" stroke="${shade(home.primary,-40)}" stroke-width="2"/>
    <ellipse cx="120" cy="80" rx="92" ry="48" fill="${shade(home.secondary,-20)}" opacity="0.5"/>
    ${lights}
    <!-- field -->
    <rect x="52" y="50" width="136" height="60" rx="6" fill="${grass}"/>
    <!-- mow stripes -->
    ${Array.from({length:6},(_,i)=>`<rect x="${52+i*22.7}" y="50" width="11.3" height="60" fill="${grassDark}" opacity="0.35"/>`).join("")}
    <!-- end zones -->
    <rect x="52" y="50" width="18" height="60" rx="6" fill="${home.primary}"/>
    <rect x="170" y="50" width="18" height="60" rx="6" fill="${away.primary}"/>
    <text x="61" y="80" transform="rotate(-90 61 80)" text-anchor="middle" font-size="8.5"
          font-weight="800" fill="#ffffff" opacity="0.92" font-family="system-ui">${escapeAttr(game.home)}</text>
    <text x="179" y="80" transform="rotate(90 179 80)" text-anchor="middle" font-size="8.5"
          font-weight="800" fill="#ffffff" opacity="0.92" font-family="system-ui">${escapeAttr(game.away)}</text>
    ${yardLines}
    <!-- hash marks -->
    <g stroke="#ffffff" stroke-opacity="0.4" stroke-width="1">
      ${Array.from({length:9},(_,i)=>{const hx=72+i*12;return `<line x1="${hx}" y1="65" x2="${hx}" y2="68"/><line x1="${hx}" y1="92" x2="${hx}" y2="95"/>`;}).join("")}
    </g>
    <!-- goalposts -->
    <g stroke="#ffd24a" stroke-width="1.4" fill="none" opacity="0.95">
      <path d="M54 75 v10 M54 80 h-3 M51 76 v8"/>
      <path d="M186 75 v10 M186 80 h3 M189 76 v8"/>
    </g>
    <!-- midfield badge -->
    <circle cx="120" cy="80" r="13" fill="#0c1020" opacity="0.55"/>
    <circle cx="120" cy="80" r="13" fill="none" stroke="${shade(home.secondary,20)}" stroke-width="1.2" opacity="0.7"/>
    <text x="120" y="84" text-anchor="middle" font-size="10" font-weight="800"
          fill="#ffffff" font-family="system-ui">${escapeAttr(game.home)}</text>
    ${roofOverlay}
    <!-- Last, and deliberately after the roof: a dome lays a 0.8-opacity
         ellipse over the whole field, which would leave the ball spot
         dimmer indoors than out. -->
    ${drive}
  </svg>`;
}

/* ---------------- Aerial ballpark (MLB) ---------------------------------- */
/* A stylized NBA court for the hero strip — hardwood, arcs, and each
   team's paint in its own colors. Same 240x150 card art contract as
   stadium()/ballpark(). */
function court(game, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const home = team(game.home), away = team(game.away);
  const uid = "c" + Math.random().toString(36).slice(2, 7);
  return `
  <svg class="field" viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="${escapeAttr(game.away)} at ${escapeAttr(game.home)}">
    <defs>
      <linearGradient id="${uid}wood" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#c89b6a"/>
        <stop offset="100%" stop-color="#a97c4f"/>
      </linearGradient>
    </defs>
    <rect x="18" y="30" width="204" height="100" rx="8" fill="url(#${uid}wood)"
          stroke="#7c5a37" stroke-width="2"/>
    ${Array.from({ length: 10 }, (_, i) =>
      `<line x1="${28 + i * 19}" y1="32" x2="${24 + i * 19}" y2="128"
             stroke="#8f6a41" stroke-width="1" opacity="0.35"/>`).join("")}
    <line x1="120" y1="30" x2="120" y2="130" stroke="#f4e9d8" stroke-width="2" opacity="0.85"/>
    <circle cx="120" cy="80" r="16" fill="none" stroke="#f4e9d8" stroke-width="2" opacity="0.85"/>
    <circle cx="120" cy="80" r="6" fill="${shade(home.primary, 6)}" opacity="0.9"/>
    <!-- away paint (left) / home paint (right), team-colored -->
    <rect x="18" y="62" width="34" height="36" fill="${away.primary}" opacity="0.85"
          stroke="#f4e9d8" stroke-width="1.5"/>
    <rect x="188" y="62" width="34" height="36" fill="${home.primary}" opacity="0.85"
          stroke="#f4e9d8" stroke-width="1.5"/>
    <path d="M52 62 a18 18 0 0 1 0 36" fill="none" stroke="#f4e9d8" stroke-width="1.5" opacity="0.85"/>
    <path d="M188 62 a18 18 0 0 0 0 36" fill="none" stroke="#f4e9d8" stroke-width="1.5" opacity="0.85"/>
    <!-- three-point arcs -->
    <path d="M18 38 q52 42 0 84" fill="none" stroke="#f4e9d8" stroke-width="1.7" opacity="0.8"/>
    <path d="M222 38 q-52 42 0 84" fill="none" stroke="#f4e9d8" stroke-width="1.7" opacity="0.8"/>
    <text x="35" y="84" text-anchor="middle" font-family="system-ui, sans-serif" font-size="10"
          font-weight="800" fill="${idealText(away.primary)}" transform="rotate(-90 35 84)">${escapeAttr(game.away)}</text>
    <text x="205" y="84" text-anchor="middle" font-family="system-ui, sans-serif" font-size="10"
          font-weight="800" fill="${idealText(home.primary)}" transform="rotate(90 205 84)">${escapeAttr(game.home)}</text>
    <text x="120" y="24" text-anchor="middle" font-family="system-ui, sans-serif"
          font-size="10" font-weight="700" fill="#c9d2e8" opacity="0.9">${escapeAttr(team(game.home).nick || game.home)} home court</text>
  </svg>`;
}


// The base state, said in words. The lit bases are a colour difference on a
// 240px drawing, which is nothing at all to a screen reader — and the mini
// diamond that used to carry an aria-label is gone.
const BASE_NAMES = { 1: "first", 2: "second", 3: "third" };
function runnerLabel(runners) {
  const on = [1, 2, 3].filter((n) => runners && runners.has(n));
  if (!on.length) return "Ballpark";
  if (on.length === 3) return "Ballpark — bases loaded";
  return `Ballpark — runner${on.length > 1 ? "s" : ""} on `
    + on.map((n) => BASE_NAMES[n]).join(" and ");
}


function ballpark(game, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const home = team(game.home), away = team(game.away);
  const roof = (game.roof || "open").toLowerCase();
  const covered = roof === "dome" || roof === "closed";
  const turf = /turf/.test((game.surface || "grass").toLowerCase());
  const grass = turf ? "#1f7a46" : "#2a9d54";
  const grassDark = turf ? "#186038" : "#1f7d41";
  const dirt = "#b3814f";
  const uid = "bp" + Math.random().toString(36).slice(2, 7);
  // Occupied bases, live only. `live.bases` is [1], [2, 3], … — the same
  // shape the mini diamond has always read.
  const lv = game.live || {};
  const runners = new Set(lv.state === "live" ? (lv.bases || []) : []);
  const fx = (game.factors || {});
  const hrPct = fx.hr ? Math.round((fx.hr - 1) * 100) : 0;
  const hrBadge = hrPct ? `
    <g>
      <rect x="168" y="128" width="64" height="15" rx="7.5" fill="#0c1020" opacity="0.72"/>
      <text class="num" x="200" y="139" text-anchor="middle" font-size="8.5" font-weight="700"
            fill="${hrPct > 0 ? "#ffb547" : "#6fd3ff"}">HR ${hrPct > 0 ? "+" : ""}${hrPct}%</text>
    </g>` : "";
  const altBadge = (game.altitude_ft || 0) >= 3000 ? `
    <g>
      <rect x="8" y="128" width="70" height="15" rx="7.5" fill="#0c1020" opacity="0.72"/>
      <g transform="translate(12,131.6) scale(0.62)" fill="none" stroke="#8a6cff"
         stroke-width="2.2" stroke-linejoin="round">
        <path d="M1.4 12.9L5.9 5.3l3 4.7 1.9-2.9 3.8 5.8z"/>
      </g>
      <text class="num" x="50" y="139" text-anchor="middle" font-size="8.5" font-weight="700"
            fill="#8a6cff">${(game.altitude_ft / 1000).toFixed(1)}k ft</text>
    </g>` : "";
  const roofOverlay = covered ? `
    <ellipse cx="120" cy="82" rx="104" ry="64" fill="url(#${uid}roof)" opacity="0.78"/>
    <g stroke="#ffffff" stroke-opacity="0.12" stroke-width="1">
      <line x1="120" y1="20" x2="120" y2="144"/><line x1="28" y1="82" x2="212" y2="82"/>
      <line x1="56" y1="34" x2="184" y2="130"/><line x1="184" y1="34" x2="56" y2="130"/>
    </g>
    <text x="120" y="30" text-anchor="middle" font-size="9" fill="#dfe4f5"
          font-family="system-ui" opacity="0.85">${roof === "dome" ? "DOME" : "ROOF CLOSED"}</text>` :
    (roof === "retractable" ? `<text x="120" y="26" text-anchor="middle" font-size="9"
        fill="#9aa6c9" font-family="system-ui">RETRACTABLE · OPEN</text>` : "");

  return `
  <svg class="stadium" width="${w}" height="${h}" viewBox="0 0 240 150" preserveAspectRatio="xMidYMid meet"
       role="img" aria-label="${escapeAttr(runnerLabel(runners))}">
    <defs>
      <!-- The glow that makes an occupied base read as occupied at 240px.
           Gold, the colour the mini diamond used for the same fact, so the
           idea survived the diagram that used to carry it. -->
      <filter id="${uid}runner" x="-80%" y="-80%" width="260%" height="260%">
        <feDropShadow dx="0" dy="0" stdDeviation="2.2"
                      flood-color="#ffd24a" flood-opacity="0.95"/>
      </filter>
      <radialGradient id="${uid}sky" cx="50%" cy="30%" r="80%">
        <stop offset="0%" stop-color="${covered ? "#0f1730" : "#16233f"}"/>
        <stop offset="100%" stop-color="#0a0f22"/>
      </radialGradient>
      <linearGradient id="${uid}stand" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${shade(home.primary, 10)}"/>
        <stop offset="100%" stop-color="${shade(home.primary, -30)}"/>
      </linearGradient>
      <radialGradient id="${uid}roof" cx="50%" cy="40%" r="70%">
        <stop offset="0%" stop-color="${shade(home.primary, 35)}"/>
        <stop offset="100%" stop-color="${shade(home.primary, -10)}"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="240" height="150" fill="url(#${uid}sky)"/>
    <!-- stands: horseshoe bowl open toward the outfield (top) -->
    <path d="M120 152 m-116 -34 a116 96 0 1 1 232 0 l-26 12 a92 74 0 1 0 -180 0 z"
          fill="url(#${uid}stand)" stroke="${shade(home.primary, -40)}" stroke-width="2"/>
    <!-- field: outfield grass fan -->
    <path d="M120 132 L34 60 A116 92 0 0 1 206 60 Z" fill="${grass}"/>
    ${/* Mow stripes. Classed so the engraving layer can drop them: as FILLED
          wedges at 18% they read as faint stripes, but engraved — outline
          only — each one becomes an arc plus two radii, and five of those
          radiating from the plate is a cat's cradle over the infield. The
          football field's stripes survive the same treatment because they
          are rectangles, which outline into parallel lines. */""}
    ${Array.from({ length: 5 }, (_, i) =>
      `<path class="mow" d="M120 132 L${44 + i * 16} ${56 - i * 2} A116 92 0 0 1 ${72 + i * 20} 34 Z"
         fill="${grassDark}" opacity="0.18"/>`).join("")}
    <!-- outfield wall -->
    <path d="M34 60 A116 92 0 0 1 206 60" fill="none"
          stroke="${shade(home.secondary, -10)}" stroke-width="4" opacity="0.9"/>
    <!-- infield dirt diamond -->
    <path d="M120 132 L82 96 A54 54 0 0 1 158 96 Z" fill="${dirt}"/>
    <!-- infield grass -->
    <path d="M120 124 L96 100 L120 76 L144 100 Z" fill="${grass}"/>
    <!-- base paths -->
    <g stroke="#f3e5c9" stroke-width="2" fill="none" opacity="0.9">
      <path d="M120 124 L96 100 L120 76 L144 100 Z"/>
    </g>
    <!-- foul lines to the wall -->
    <g stroke="#f3e5c9" stroke-width="1.6" opacity="0.75">
      <line x1="120" y1="128" x2="40" y2="62"/>
      <line x1="120" y1="128" x2="200" y2="62"/>
    </g>
    <!-- BASES, LIT WHEN OCCUPIED.
         Ethan, 2026-08-08: "when games are live, can we highlight what
         batters are on base on the actual stadium."

         The art already drew these three squares at these three
         coordinates; the live feed already carried which of them are
         occupied. Nothing new is fetched — the two halves simply had
         never been introduced.

         An occupied base is filled with the same gold the mini diamond
         used and given a soft ring, so it reads at 240px without a
         legend. Off a live game every base is white, exactly as before,
         because the runner set is empty and the fill falls through.
         (No backticks in this comment: it lives inside a template
         literal, and one would end the string.) -->
    <g>
      ${[[96, 100, 3], [120, 76, 2], [144, 100, 1]].map(([bx, by, n]) => {
        if (!runners.has(n)) {
          return `<rect x="${bx - 3}" y="${by - 3}" width="6" height="6"
            transform="rotate(45 ${bx} ${by})" fill="#ffffff"/>`;
        }
        // MEASURED IN CHROMIUM, and it took two passes.
        //
        // First: the gold fill did not read. The bases sit ON the infield
        // dirt (#b3814f) and #ffd24a is the same warmth at nearly the same
        // value — at six pixels the occupied base and the empty one were
        // the same grain of rice, and a gold glow on tan only softened the
        // edge further. The dark disc is what does the work: it separates
        // the marker from the dirt so the gold has something to be bright
        // against. Bigger, too — a runner is a bigger deal than a bag.
        //
        // Second, and the one worth remembering: the gold was not merely
        // low-contrast, it was NOT THERE. `.stadium g rect` in the Night
        // Form stylesheet sets `fill: none` on every rect inside the art —
        // deliberately, to hollow out the plaques — and a presentation
        // attribute loses to any CSS rule. `getComputedStyle(rect).fill`
        // came back "none" while `fill="#ffd24a"` sat right there in the
        // markup. Hence the class: the styling of an occupied base lives
        // in the stylesheet, where it can out-specify the rule that would
        // otherwise erase it.
        return `<g>
          <circle cx="${bx}" cy="${by}" r="6.5" fill="#0c1020" opacity="0.55"/>
          <rect class="on-base" x="${bx - 4}" y="${by - 4}" width="8" height="8"
            transform="rotate(45 ${bx} ${by})" fill="#ffd24a"
            stroke="#ffffff" stroke-width="1" filter="url(#${uid}runner)"/>
        </g>`;
      }).join("")}
    </g>
    <circle cx="120" cy="100" r="5.5" fill="${dirt}" stroke="#caa06a" stroke-width="1"/>
    <circle cx="120" cy="100" r="1.8" fill="#ffffff"/>
    <path d="M116 129 h8 l-1.5 4 h-5 Z" fill="#ffffff"/>
    <!-- park name arc-ish label -->
    <text x="120" y="52" text-anchor="middle" font-size="8.5" font-weight="700"
          fill="#ffffff" opacity="0.85" font-family="system-ui">${escapeAttr(game.park_name || "")}</text>
    ${hrBadge}
    ${altBadge}
    ${roofOverlay}
  </svg>`;
}

/* ---------------- The Overhead, where there is no building ---------------
 *
 * See docs/THE_OVERHEAD.md. The Overhead is a plan view of the space a
 * price is set in. For MLB, NFL, CFB, NBA and WNBA that space is a
 * building, so the drawing is the building. Two of our markets have no
 * building, and they need the same asset rather than an exemption from it.
 *
 * The rule that decides both: draw the space, to scale, with the
 * conditions in the corners. What changes is what counts as space.
 */

/* UFC — the cage, at its real size.
 *
 * The first instinct was that an octagon is a constant and therefore
 * carries no data, which would make it decoration. That was wrong, and
 * engine/ufc/environment.py is why: the promotion's own facility uses a
 * 25-foot cage and arena events use 30. Less space means fewer places to
 * retreat to, so pressure fighters and wrestlers gain, out-fighters lose,
 * and finishes go up — a fact knowable from the venue name before a single
 * stat is consulted, and one the model already prices.
 *
 * So the octagon IS data-bearing, on exactly the same terms as an outfield
 * arc: it is a building whose dimensions vary and whose variation moves
 * the number. Drawn to scale, an Apex card is visibly smaller than an
 * arena card, which is the whole point. */
const CAGE_R = { 30: 52, 25: 43 };   // viewBox units per real foot, 240x150

function octagon(bout, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const env = bout.environment || {};
  const cage = env.cage || {};
  const alt = env.altitude || {};
  const feet = cage.feet === 25 || cage.feet === 30 ? cage.feet : 30;
  const r = CAGE_R[feet];
  const cx = 120, cy = 80;

  // Eight vertices, flat side facing the reader — the orientation every
  // broadcast uses, so it reads as a cage and not as a stop sign.
  const pts = Array.from({ length: 8 }, (_, i) => {
    const a = (Math.PI / 4) * i + Math.PI / 8;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
  const ring = (k) => "M" + pts.map(([x, y]) =>
    `${(cx + (x - cx) * k).toFixed(1)} ${(cy + (y - cy) * k).toFixed(1)}`).join("L") + "Z";

  /* Rounds sit where the roof state sits on a stadium: a categorical fact
     about the contest, top-centre, above the venue name. Five rounds is
     a different distribution, not a longer version of the same one. */
  const rounds = bout.rounds === 5 || bout.title_fight
    ? `<text x="120" y="26" text-anchor="middle" font-size="9">5 ROUNDS${
        bout.title_fight ? " · TITLE" : ""}</text>` : "";

  /* Plaques in the locked corners — altitude bottom-left exactly as the
     ballpark puts it, the varying dimension bottom-right where the park
     factor goes. */
  const plaque = (x, label) => `
    <g><rect x="${x}" y="128" width="70" height="15"/>
      <text class="num" x="${x + 35}" y="139" text-anchor="middle" font-size="8.5">${label}</text></g>`;

  return `
  <svg class="stadium" width="${w}" height="${h}" viewBox="0 0 240 150"
       preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="${escapeAttr(bout.venue || "Octagon")}, ${feet}-foot cage">
    <rect x="0" y="0" width="240" height="150"/>
    <path d="${ring(1)}"/>
    <path d="${ring(0.88)}"/>
    <circle cx="${cx}" cy="${cy}" r="9"/>
    ${/* y=60, not the ballpark's 52: the cage's inner ring tops out at ~38
          and a label on 52 lay across it. Inside the cage is the same
          place the park name sits — the open part of the playing
          surface — so the grammar holds, the number moves. */""}
    <text x="120" y="60" text-anchor="middle" font-size="8.5">${escapeAttr(bout.venue || "")}</text>
    ${rounds}
    ${alt.known && alt.meaningful ? plaque(8, `${(alt.feet / 1000).toFixed(1)}k ft`) : ""}
    ${cage.known ? plaque(162, `CAGE ${feet}FT`) : ""}
  </svg>`;
}

/* Prediction markets — the space is the probability line.
 *
 * Polymarket and Kalshi have no room to draw. What a price is set IN there
 * is the market itself, so the plan view is the 0-100 rule, and every
 * market on the board is a segment from the exchange's number to ours.
 * Length is disagreement. A board with no edges is a row of dots; a board
 * we disagree with violently is a row of long bars, at a glance, before a
 * single figure is read.
 *
 * This is deliberately ONE drawing for the whole board rather than one per
 * row: the Kalshi board is an agate table and a venue-card-sized diagram
 * on every line would bury it. It also makes the shape novel rather than
 * generic, which is the property the research says a visualisation needs
 * before it can become a recognisable asset. */
const RULE_ROWS = 8;                 // fits 240x150 at a legible pitch

function marketRule(rows, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const all = (rows || []).filter((r) => r && r.prob != null);
  const shown = all.slice(0, RULE_ROWS);
  const x = (p) => 24 + Math.max(0, Math.min(1, p)) * 192;
  /* The whole rule finishes above y=126: the plaques own the bottom
     corners at y=128 in every Overhead, and that is locked. A first pass
     put the axis on 118 with its numbers on 133, which ran the scale
     straight through both plaques. */
  const y = (i) => 38 + i * 7.5;
  const AXIS = 104;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((p) => `
    <line x1="${x(p)}" y1="${AXIS}" x2="${x(p)}" y2="${AXIS + 4}"/>
    <text x="${x(p)}" y="${AXIS + 13}" text-anchor="middle" font-size="7.5">${p * 100}</text>`).join("");

  /* Market end is an open tick, ours is the mark. Where we have no number
     the row is just the exchange's tick — an honest blank rather than a
     segment of length zero, which would read as agreement. */
  const bars = shown.map((r, i) => {
    const a = x(r.prob), b = r.model_p == null ? null : x(r.model_p);
    return `<g>
      <line x1="${a}" y1="${y(i)}" x2="${a}" y2="${y(i) + 4.5}"/>
      ${b == null ? "" : `<line x1="${a}" y1="${y(i) + 2.25}" x2="${b}" y2="${y(i) + 2.25}"/>
      <path d="M${b} ${y(i)} L${b + 2.4} ${y(i) + 2.25} L${b} ${y(i) + 4.5} L${b - 2.4} ${y(i) + 2.25} Z"/>`}
    </g>`;
  }).join("");

  const vol = all.reduce((s, r) => s + (Number(r.volume_24h) || 0), 0);
  const plaque = (px, label) => `
    <g><rect x="${px}" y="128" width="70" height="15"/>
      <text class="num" x="${px + 35}" y="139" text-anchor="middle" font-size="8.5">${label}</text></g>`;

  return `
  <svg class="stadium" width="${w}" height="${h}" viewBox="0 0 240 150"
       preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="${all.length} markets, exchange probability against ours">
    <rect x="0" y="0" width="240" height="150"/>
    <text x="120" y="26" text-anchor="middle" font-size="8.5">${escapeAttr(opts.title || "THE BOARD")}</text>
    <line x1="24" y1="${AXIS}" x2="216" y2="${AXIS}"/>
    ${ticks}
    ${bars}
    ${plaque(8, `${all.length} MKT`)}
    ${vol ? plaque(162, `$${vol >= 1000 ? (vol / 1000).toFixed(0) + "k" : vol}`) : ""}
  </svg>`;
}

/* ---------------- Count strip (MLB live) ---------------------------------
   This replaced a 46px base diamond that sat in the same spot.

   The diamond was the only place the base state was shown, so it earned
   its room. Now the park art above it lights the occupied bases where the
   runners actually are, and a second, smaller diagram forty pixels below
   was saying the same sentence twice — while the half of the situation it
   never said, the count, went unsaid on every card.

   FAILS OPEN. `balls`/`strikes` are new to the live parse; any payload
   built before it, or any game the feed is thin on, has them null. The
   count is dropped and the outs still render — which is exactly what the
   footer said before, minus the picture.                                 */
function countStrip(live) {
  const l = live || {};
  const outs = l.outs == null ? 0 : l.outs;
  const b = l.balls, s = l.strikes;
  const outDot = (cx, filled) =>
    `<circle cx="${cx}" cy="5.5" r="4" fill="${filled ? "#fb2c46" : "#2c3557"}"/>`;
  const count = (b == null || s == null) ? "" :
    `<span class="cnt" title="Balls and strikes">${b}<i>–</i>${s}</span>`;
  return `${count}
    <span class="cnt-outs">
      <svg class="outdots" width="23" height="11" viewBox="0 0 23 11" aria-hidden="true">
        ${outDot(5.5, outs >= 1)}${outDot(17.5, outs >= 2)}
      </svg>
      <span class="count-label">${outs} out${outs === 1 ? "" : "s"}</span>
    </span>`;
}

/* ---------------- Sparkline (game-log trend) ----------------------------- */
function sparkline(values, opts = {}) {
  const w = opts.w || 240, h = opts.h || 64, pad = 8;
  // A row-sized chart can't legibly hold a full season: cap the window to
  // ~6px per step and keep the NEWEST games — recent form is the story a
  // sparkline tells. (values arrive newest-first; chart oldest -> newest.)
  const maxPts = Math.max(2, Math.floor((w - pad * 2) / 6));
  // Missing games (null/undefined in the feed) must not poison the chart:
  // ONE NaN coordinate makes SVG abort the rest of the line path while the
  // per-point dots keep rendering — the "line stops, dots float" bug.
  // Non-finite points are dropped, labels kept in sync.
  const raw = [...values].slice(0, maxPts);
  const rawLabs = opts.labels ? [...opts.labels].slice(0, maxPts) : null;
  const keep = raw.map((v, i) => ({ v: Number(v), i }))
    .filter((d) => Number.isFinite(d.v));
  const data = keep.map((d) => d.v).reverse();
  // Mini mode (tight row charts): one thin line and one endpoint marker.
  // Per-point dots at this size render as noise, not data.
  const mini = opts.mini != null ? opts.mini : (w < 120 || h < 36);
  const line = opts.line;                    // optional threshold (the prop line)
  const stroke = opts.stroke || "var(--brand)";
  const uid = "sp" + Math.random().toString(36).slice(2, 7);
  if (data.length < 2) return `<svg width="${w}" height="${h}"></svg>`;

  const lo = Math.min(...data, line ?? Infinity);
  const hi = Math.max(...data, line ?? -Infinity);
  const span = (hi - lo) || 1;
  const x = (i) => pad + (i / (data.length - 1)) * (w - pad * 2);
  const y = (v) => h - pad - ((v - lo) / span) * (h - pad * 2);

  // Hover labels: opts.labels comes newest-first like values; filtered to
  // the same surviving points, reversed to match the charted order.
  const labs = rawLabs ? keep.map((d) => rawLabs[d.i]).reverse() : null;
  const tip = (i) => (labs && labs[i] ? labs[i] + " — " : "") + data[i];

  const pts = data.map((v, i) => `${x(i)},${y(v)}`);
  const linePath = "M" + pts.join(" L");
  const areaPath = `M${x(0)},${h - pad} L` + pts.join(" L") + ` L${x(data.length - 1)},${h - pad} Z`;
  const dots = mini ? "" : data.map((v, i) => {
    const above = line == null ? true : v > line;
    const c = line == null ? stroke : (above ? "var(--good)" : "var(--bad)");
    return `<circle cx="${x(i)}" cy="${y(v)}" r="${i === data.length - 1 ? 3.2 : 2.1}" fill="${c}"/>`;
  }).join("");
  // Invisible, generous hit targets. data-tip feeds the instant floating
  // tooltip below — native SVG <title> needs a second of frozen hover and
  // reads as "nothing happens", so it isn't used. Mini charts skip them:
  // 6px-apart targets just fight each other, and the row itself is the
  // clickable thing.
  const hits = mini ? "" : data.map((v, i) =>
    `<circle cx="${x(i)}" cy="${y(v)}" r="9" fill="transparent"
       style="pointer-events:all;cursor:pointer" data-tip="${escapeAttr(tip(i))}"/>`).join("");
  const thresh = line == null ? "" :
    `<line x1="${pad}" y1="${y(line)}" x2="${w - pad}" y2="${y(line)}"
       stroke="var(--warn)" stroke-width="1" stroke-dasharray="4 4" opacity="0.8"/>`;
  // radar "ping" behind the most recent game (the one selective marker a
  // mini chart keeps — endpoint only, per standard sparkline practice)
  const li = data.length - 1;
  const lastC = line == null ? stroke : (data[li] > line ? "var(--good)" : "var(--bad)");
  const ping = `<circle class="spark-pulse" cx="${x(li)}" cy="${y(data[li])}" r="3" fill="${lastC}"/>`;
  const endDot = mini
    ? `<circle cx="${x(li)}" cy="${y(data[li])}" r="2.4" fill="${lastC}"/>` : "";

  return `
  <svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="${uid}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${stroke}" stop-opacity="${mini ? 0.16 : 0.28}"/>
        <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#${uid}a)"/>
    ${thresh}
    ${ping}
    <path class="spark-line" d="${linePath}" fill="none" stroke="${stroke}"
          stroke-width="${mini ? 1.6 : 2}" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots}${endDot}
    ${hits}
  </svg>`;
}

/* ---------------- helpers ------------------------------------------------ */
function shade(hex, amt) {
  const h = (hex || "#333333").replace("#", "");
  let r = parseInt(h.substr(0,2),16), g = parseInt(h.substr(2,2),16), b = parseInt(h.substr(4,2),16);
  r = Math.max(0, Math.min(255, r + amt));
  g = Math.max(0, Math.min(255, g + amt));
  b = Math.max(0, Math.min(255, b + amt));
  return "#" + [r,g,b].map(x => x.toString(16).padStart(2,"0")).join("");
}
function escapeAttr(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}


/* ---------------- instant graph tooltip ----------------
   One floating label for every sparkline dot: appears the moment the
   pointer touches a hit target, follows the cursor, vanishes on leave. */
(function () {
  let tipEl = null;
  function ensure() {
    if (tipEl) return tipEl;
    tipEl = document.createElement("div");
    tipEl.className = "graph-tip";
    tipEl.style.display = "none";
    document.body.appendChild(tipEl);
    return tipEl;
  }
  function place(e) {
    const el = ensure();
    const pad = 14;
    let lx = e.clientX + pad, ly = e.clientY - 30;
    const w = el.offsetWidth || 80;
    if (lx + w > window.innerWidth - 8) lx = e.clientX - w - pad;
    if (ly < 8) ly = e.clientY + pad;
    el.style.left = lx + "px";
    el.style.top = ly + "px";
  }
  document.addEventListener("pointerover", (e) => {
    const t = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
    const el = ensure();
    if (!t) { el.style.display = "none"; return; }
    el.textContent = t.getAttribute("data-tip");
    el.style.display = "block";
    place(e);
  });
  document.addEventListener("pointermove", (e) => {
    if (tipEl && tipEl.style.display === "block") place(e);
  });
  document.addEventListener("pointerout", (e) => {
    if (!tipEl) return;
    const t = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
    if (t) tipEl.style.display = "none";
  });
})();
