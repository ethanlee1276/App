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
    /* Same rule as the team marks: a headshot is a CUT-OUT on transparent
       ground, so the drawn helmet showed through every real face. The
       drawing steps aside on load and the stack keeps a plain disc for the
       face to sit on; on error the photo removes itself and the helmet is
       back, which is the whole point of drawing one. */
    return `<span class="avatar-stack" style="width:${size}px;height:${size}px">${inner}
      <img class="avatar-photo" src="${escapeAttr(small)}" alt="" loading="lazy"
           decoding="async"${small === opts.headshot ? ""
             : ` data-full="${escapeAttr(opts.headshot)}"`}
           onload="this.parentNode.classList.add('art-on')"
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
  /* The monogram stays underneath, and STEPS ASIDE once a real logo
     paints. Ethan, 2026-08-12, with the rows circled: "the logos overlap
     whatever is underneath". A team logo is a transparent PNG, so the
     chip's diagonal band, colour block and abbreviation showed straight
     through every one of them. `onload` is the whole fix — the drawing is
     a FALLBACK, so it must be visible exactly when the image is not.
     `onerror` still removes only the image, so a bad abbreviation or a
     dead CDN lands on the chip this used to be. */
  const img = url
    ? `<img class="team-logo" src="${escapeAttr(url)}" width="${size}"
            height="${size}" alt="" loading="lazy" decoding="async"
            onload="this.parentNode.classList.add('art-on')"
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

/* The league's own mark, for bets that belong to the GAME rather than to a
   team or a player — an over/under has no side to wear. Same combiner
   resize the team logos use; the drawn monogram underneath (the same
   chip shape teamMark falls back to, in house neutrals) shows only when
   the CDN image is absent, so a dead host changes nothing. */
function leagueMark(sport, size = 20) {
  const s = (sport || "").toLowerCase();
  const key = ESPN_LEAGUE[s];
  const uid = "lm" + Math.random().toString(36).slice(2, 7);
  const label = (key === "ncaa" ? "NCAA" : s.toUpperCase() || "?");
  const img = key
    ? `<img class="team-logo" src="https://a.espncdn.com/combiner/i?img=/i/teamlogos/leagues/500/${key}.png&w=${size * 2}&h=${size * 2}"
            width="${size}" height="${size}" alt="" loading="lazy"
            decoding="async" onload="this.parentNode.classList.add('art-on')"
            onerror="this.remove()">`
    : "";
  return `<span class="team-mark-wrap league-mark" style="width:${size}px;height:${size}px"
                role="img" aria-label="${escapeAttr(label)}">
  <svg class="team-mark" width="${size}" height="${size}" viewBox="0 0 24 24"
       aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#3a4668"/>
        <stop offset="100%" stop-color="#232c49"/>
      </linearGradient>
    </defs>
    <rect x="1" y="1" width="22" height="22" rx="6.5" fill="url(#${uid})"
          stroke="#1a2138" stroke-width="1"/>
    <text x="12" y="15.4" text-anchor="middle" font-family="system-ui, sans-serif"
          font-size="${label.length > 3 ? 6 : 7.5}" font-weight="800"
          fill="#ffffff">${escapeAttr(label.slice(0, 4))}</text>
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


/* ---------------- Night atmosphere (NEW LOOK, 2026-08-11) ----------------
   Ethan's render draws every stadium as a NIGHT scene: floodlight bloom,
   the two teams' colours washing the air from either side, and darkness
   pooling at the edges. This helper is that mood as three layers —
   defs (filters + gradients), under (painted right after the sky, below
   the architecture) and over (vignette + lens bloom, above everything) —
   so all three venue drawings share ONE night rather than three
   approximations of it. Geometry is untouched: Coors is still Coors.
   No <rect> inside a <g> — the plaque rule in the stylesheet hollows
   those (fill:none), which is exactly the bug the on-base comment below
   documents. Ellipses and paths only. */
function nightFx(uid, home, away, opts = {}) {
  const defs = `
    <filter id="${uid}bloom" x="-160%" y="-160%" width="420%" height="420%">
      <feGaussianBlur stdDeviation="5"/>
    </filter>
    <filter id="${uid}soft" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="9"/>
    </filter>
    <filter id="${uid}grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2"
        stitchTiles="stitch" result="n"/>
      <feColorMatrix in="n" type="matrix"
        values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0.55 0 0 0 0"/>
    </filter>
    <radialGradient id="${uid}gA" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${away.primary}" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="${away.primary}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="${uid}gH" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${home.primary}" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="${home.primary}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="${uid}vig" cx="50%" cy="44%" r="74%">
      <stop offset="0%" stop-color="#000000" stop-opacity="0"/>
      <stop offset="58%" stop-color="#000000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#010208" stop-opacity="0.94"/>
    </radialGradient>
    <radialGradient id="${uid}pool" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#F4F8FF" stop-opacity="0.26"/>
      <stop offset="65%" stop-color="#F4F8FF" stop-opacity="0.07"/>
      <stop offset="100%" stop-color="#F4F8FF" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="${uid}rim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#DCE6FF" stop-opacity="0.34"/>
      <stop offset="45%" stop-color="#DCE6FF" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="#DCE6FF" stop-opacity="0"/>
    </linearGradient>`;
  // Under the architecture: each side's air carries its team, and a
  // soft haze hangs over the whole bowl the way stadium light does.
  const under = `
    <ellipse cx="26" cy="118" rx="122" ry="90" fill="url(#${uid}gA)"/>
    <ellipse cx="214" cy="118" rx="122" ry="90" fill="url(#${uid}gH)"/>
    <ellipse cx="120" cy="64" rx="120" ry="52" fill="#8FA8E8" opacity="0.07"
      filter="url(#${uid}soft)"/>`;
  // The bowl's rim light — the photographic tell of an aerial night
  // shot: the top edge of the stands catches the floodlights.
  const bowl = opts.bowl;
  const rim = bowl ? `
    <ellipse cx="${bowl.cx}" cy="${bowl.cy}" rx="${bowl.rx}" ry="${bowl.ry}"
      fill="none" stroke="url(#${uid}rim)" stroke-width="3.2"/>
    <ellipse cx="${bowl.cx}" cy="${bowl.cy}" rx="${bowl.rx * 0.82}" ry="${bowl.ry * 0.8}"
      fill="none" stroke="#050817" stroke-opacity="0.5" stroke-width="2"/>` : "";
  // The floodlights: bloomed halo, hard head, a lens streak, and the
  // cone falling toward the field. Then darkness at the edges, and a
  // pass of film grain so the scene reads as a photograph, not a chart.
  const heads = [[30, 26], [210, 26], [12, 96], [228, 96]];
  const over = `
    <ellipse cx="120" cy="86" rx="88" ry="44" fill="url(#${uid}pool)"/>
    ${rim}
    <rect x="0" y="0" width="240" height="150" fill="url(#${uid}vig)"/>
    ${heads.map(([x, y]) => `
      <ellipse cx="${x}" cy="${y}" rx="9" ry="4.4" fill="#FFF6D8" opacity="0.95" filter="url(#${uid}bloom)"/>
      <ellipse cx="${x}" cy="${y}" rx="3.6" ry="1.7" fill="#FFFDF4"/>
      <rect x="${x - 13}" y="${y - 0.6}" width="26" height="1.2" fill="#FFF6D8" opacity="0.5" filter="url(#${uid}bloom)"/>
      <path d="M${x} ${y} L${x + (x < 120 ? 46 : -46)} ${y + 54} L${x + (x < 120 ? 15 : -15)} ${y + 58} Z"
            fill="#F4F8FF" opacity="0.06"/>`).join("")}
    <rect x="0" y="0" width="240" height="150" filter="url(#${uid}grain)" opacity="0.1"/>`;
  return { defs, under, over };
}

/* ---------------- Aerial stadium ----------------------------------------- */
function stadium(game, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const home = team(game.home), away = team(game.away);
  const roof = (game.roof || "").toLowerCase();
  const covered = roof === "dome" || roof === "closed";
  const retractable = roof === "open";
  const turf = /turf|astro|matrix|sport/.test((game.surface || "grass").toLowerCase());
  // Night palette: the field reads as grass under lights, not daylight.
  const grass = turf ? "#0F4A2C" : "#136040";
  const grassDark = turf ? "#0A3A22" : "#0E4A30";
  const uid = "s" + Math.random().toString(36).slice(2, 7);
  const fx = nightFx(uid, team(game.home), team(game.away),
                     { bowl: { cx: 120, cy: 80, rx: 112, ry: 64 } });
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
        <stop offset="0%" stop-color="${covered ? "#0B1124" : "#0C1530"}"/>
        <stop offset="100%" stop-color="#05060F"/>
      </radialGradient>
      <linearGradient id="${uid}stand" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${shade(home.primary,-6)}"/>
        <stop offset="100%" stop-color="${shade(home.primary,-42)}"/>
      </linearGradient>
      <radialGradient id="${uid}roof" cx="50%" cy="40%" r="70%">
        <stop offset="0%" stop-color="${shade(home.primary,22)}"/>
        <stop offset="100%" stop-color="${shade(home.primary,-18)}"/>
      </radialGradient>
      ${fx.defs}
    </defs>
    <rect x="0" y="0" width="240" height="150" fill="url(#${uid}sky)"/>
    ${fx.under}
    <!-- outer stands bowl -->
    <ellipse cx="120" cy="80" rx="112" ry="64" fill="url(#${uid}stand)" stroke="${shade(home.primary,-40)}" stroke-width="2"/>
    <ellipse cx="120" cy="80" rx="92" ry="48" fill="${shade(home.secondary,-20)}" opacity="0.5"/>
    ${lights}
    <!-- field -->
    <rect x="52" y="50" width="136" height="60" rx="6" fill="${grass}"/>
    <!-- mow stripes -->
    ${Array.from({length:6},(_,i)=>`<rect x="${52+i*22.7}" y="50" width="11.3" height="60" fill="${grassDark}" opacity="0.22"/>`).join("")}
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
    ${fx.over}
    <!-- Last, and deliberately after the roof AND the vignette: a dome
         lays a 0.8-opacity ellipse over the whole field, and the night
         pass pools darkness at the edges — the ball spot must sit over
         both or the live fact reads dimmer than the decoration. -->
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
  const nfx = nightFx(uid, home, away,
                      { bowl: { cx: 120, cy: 80, rx: 114, ry: 62 } });
  return `
  <svg class="field" viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
       aria-label="${escapeAttr(game.away)} at ${escapeAttr(game.home)}">
    <defs>
      <radialGradient id="${uid}hall" cx="50%" cy="34%" r="85%">
        <stop offset="0%" stop-color="#101226"/>
        <stop offset="100%" stop-color="#05060F"/>
      </radialGradient>
      <linearGradient id="${uid}wood" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#B8875A"/>
        <stop offset="100%" stop-color="#8F6640"/>
      </linearGradient>
      ${nfx.defs}
    </defs>
    <rect x="0" y="0" width="240" height="150" fill="url(#${uid}hall)"/>
    ${nfx.under}
    <rect x="18" y="30" width="204" height="100" rx="8" fill="url(#${uid}wood)"
          stroke="#6E4E2F" stroke-width="2"/>
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
  ${nfx.over}
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


/* THE RUNNERS, AS AN OVERLAY ON A PHOTO.
//
// Ethan, 2026-08-13, third report of the same symptom: "also still having
// the stadium issue." The screenshot finally showed what the two previous
// fixes could not reach — a LIVE game was drawing the SVG ballpark while
// every other card showed a photo render, because live cards deliberately
// suppressed the photo. The drawing carried the lit bases, and the status
// line under it had been changed to stop repeating them, so the drawing
// could not simply be swapped out without losing the runners.
//
// His call: photo everywhere, runners on top. This is the "on top" half —
// a small corner diamond so a live card keeps the one thing the drawing
// was there for. It reads at a glance and it does not need the whole
// 240x150 scene to do it.
//
// COLOUR IS NOT THE ONLY ENCODING. An occupied base is a filled bag on a
// dark disc, an empty one is a hollow outline — a SHAPE difference, not a
// hue difference — and `runnerLabel` states the whole base state in words
// for anything that cannot see either. Same three-readings rule the bars
// on the prop card follow. */
function runnerOverlay(game) {
  const lv = (game || {}).live || {};
  if (lv.state !== "live") return "";
  const runners = new Set(lv.bases || []);
  // Home plate is bottom-centre; first, second and third read clockwise
  // from the right, the way they do on a scoreboard.
  const spots = { 1: [30, 20], 2: [20, 10], 3: [10, 20] };
  const bags = [1, 2, 3].map((n) => {
    const [cx, cy] = spots[n];
    return runners.has(n)
      ? `<rect class="on-base" x="${cx - 4}" y="${cy - 4}" width="8" height="8"
           transform="rotate(45 ${cx} ${cy})" fill="#ffd24a" stroke="#ffffff"
           stroke-width="1"/>`
      : `<rect x="${cx - 3.2}" y="${cy - 3.2}" width="6.4" height="6.4"
           transform="rotate(45 ${cx} ${cy})" fill="none" stroke="#ffffff"
           stroke-opacity=".85" stroke-width="1.4"/>`;
  }).join("");
  return `<svg class="venue-runners" viewBox="0 0 40 32" width="40" height="32"
       role="img" aria-label="${escapeAttr(runnerLabel(runners))}">
    <rect x="0" y="0" width="40" height="32" rx="6" fill="#0c1020" opacity=".62"/>
    ${bags}</svg>`;
}


function ballpark(game, opts = {}) {
  const w = opts.w || 240, h = opts.h || 150;
  const home = team(game.home), away = team(game.away);
  const roof = (game.roof || "open").toLowerCase();
  const covered = roof === "dome" || roof === "closed";
  const turf = /turf/.test((game.surface || "grass").toLowerCase());
  // Night palette — grass under floodlights, dirt gone dusk-warm.
  const grass = turf ? "#0F4A2C" : "#136040";
  const grassDark = turf ? "#0A3A22" : "#0E4A30";
  const dirt = "#7E5533";
  const uid = "bp" + Math.random().toString(36).slice(2, 7);
  const nfx = nightFx(uid, home, away);
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
        <stop offset="0%" stop-color="${covered ? "#0B1124" : "#0C1530"}"/>
        <stop offset="100%" stop-color="#05060F"/>
      </radialGradient>
      ${nfx.defs}
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
    ${nfx.under}
    <!-- stands: horseshoe bowl open toward the outfield (top) -->
    <path d="M120 152 m-116 -34 a116 96 0 1 1 232 0 l-26 12 a92 74 0 1 0 -180 0 z"
          fill="url(#${uid}stand)" stroke="${shade(home.primary, -40)}" stroke-width="2"/>
    <!-- The bowl owns the frame (2026-08-11, Ethan: the cards read
         "cheap" while the bright fan filled them — a night aerial is
         mostly darkness and seats). The seating apron fills the ring
         the shrink opens; the field scales as ONE group so every
         live marker keeps its geometry. -->
    <ellipse cx="120" cy="92" rx="102" ry="68" fill="${shade(home.primary, -38)}"/>
    <ellipse cx="120" cy="92" rx="102" ry="68" fill="#05060F" opacity="0.35"/>
    <g transform="translate(120,100) scale(0.76) translate(-120,-100)">
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
         fill="${grassDark}" opacity="0.12"/>`).join("")}
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
        </g>
    ${nfx.over}
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

/* ---------------- Prop analysis card (Ethan's render) -------------------- */
/* Ethan, 2026-08-16, with three renders: "use these renders for what I want
   the bar graphs too look like. I want the player faces in it as it looks
   more professional. Match these renders exactly."

   Everything in his render is drawn from data we already journal — the
   per-game values, the line, the price, the model's EV and its grade. The
   two HIT RATE tiles are the same fact twice (a count and a percentage),
   which is how the render has it, so it is how this has it.

   The chart area is the render's, element for element: y-axis labels on
   faint gridlines, the value printed above every bar, an OVER/UNDER
   legend, game numbers along the bottom, and the line drawn dashed with
   its own pill at the right edge.

   The pill and the legend matter beyond decoration. The site's status
   pair is ΔE 7.5 under deuteranopia, so cleared-vs-missed can never rest
   on colour alone: the drawn rule makes it positional, the value label
   makes it numeric, and the legend names both colours. Three readings,
   only one of which needs colour vision.                                */
function propAnalysis(r, opts = {}) {
  const vals = (r.recent_values || []).filter((v) => Number.isFinite(Number(v)));
  if (vals.length < 3) return "";
  // THE LINE, WHEN THE MARKET DOES NOT HAVE ONE.
  //
  // Ethan's Long Shots board, 2026-08-13: every card read "LINE NaN",
  // "0 / 10", "0%", with all ten bars red. Not a rendering bug — the
  // arithmetic was being done against NaN. A long shot is an ANYTIME
  // market ("does he homer at all"), so the row carries recent_values
  // and no `line` at all, and `v > NaN` is false for every game on
  // earth. The chart was confidently reporting that Brandon Nimmo has
  // not homered in ten games while drawing the bars that show he has.
  //
  // "1 or more" IS a threshold, it is just written down elsewhere: it is
  // 0.5. Deriving it here is not inventing a number, it is reading the
  // market's own definition. Anything we still cannot pin a threshold
  // for renders nothing, because a chart against an unknown line is the
  // failure above wearing a different coat.
  // Each field tested on its own. Joining them into one string and
  // anchoring with ^...$ matched nothing at all — caught by rendering the
  // exact rows off Ethan's board rather than by reading the pattern.
  const ANYTIME = /^(anytime_?td|home_?runs|to_?score|first_?td)$/i;
  const ANYTIME_LABEL = /\banytime\b|\bhome runs?\b|\b1\+|\bto score\b/i;
  let line = Number(r.line);
  if (!Number.isFinite(line)) {
    const mk = String(r.market || "").trim();
    const lb = String(r.market_label || "").trim();
    if (!ANYTIME.test(mk) && !ANYTIME_LABEL.test(lb)) return "";
    line = 0.5;
  }
  const data = vals.slice(0, 10).map(Number).reverse();   // oldest -> newest
  const n = data.length;
  const over = (r.side || "OVER").toUpperCase() === "OVER";
  // "Cleared" means the bet cashed, which for an UNDER is the value
  // falling BELOW the line. Colouring by `v > line` regardless of side
  // would paint an under-bet's winners red.
  const won = (v) => (over ? v > line : v < line);
  const hits = data.filter(won).length;
  // THE CARD TINT. Ethan's render alternates a red and a green card border
  // between two cards that are both OVER bets at similar confidence, so
  // there the alternation is decorative. A coloured border on a betting
  // card that means nothing is worse than no border, so this one carries
  // the same fact the bars do: whether recent form backs the side we took.
  // AGAINST THE PRICE, NOT AGAINST A COIN FLIP.
  //
  // This asked `hits * 2 >= n` — is the strike rate at least half — and
  // that is only the right question at even money. Ethan's Long Shots
  // board made the error obvious the moment the chart started working:
  // Brandon Nimmo homered in 3 of 10 at +550 and the card called it bad.
  // Break-even at +550 is 15.4%, so a 30% rate is roughly double what
  // the bet needs. Red on that is not a quibble, it is the card
  // contradicting the pick sitting above it.
  //
  // The honest threshold is the one the wager actually has to clear, so
  // the tint and the hit-rate tile both read against the offered price.
  // At -110 that is 52.4% and nothing about the old behaviour changes;
  // out at plus money it stops punishing bets for being long shots.
  const be = r.odds > 0 ? 100 / (r.odds + 100) : -r.odds / (-r.odds + 100);
  const backs = n > 0 && (hits / n) >= be;
  const tone = backs ? "good" : "bad";

  // GEOMETRY, BY VIEWPORT. The SVG scales to its column, so a wide
  // viewBox squeezed into a phone shrinks every label with it — ten
  // games at 520 units wide inside a 340px card renders 10-unit type at
  // 6.5px, which is not a label. A narrower box on a phone means less
  // downscale, so the type survives. Same precedent as the board's own
  // 760px cut in app.js.
  const narrow = typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(max-width: 760px)").matches : false;
  // Sized for the full card width, not a side column. Ethan, 2026-08-13:
  // "the graph should be bigger to." Widening the viewBox alone would
  // have made it SMALLER on the glass — the SVG scales to its container,
  // so more units across the same pixels means finer type. The height
  // grows with it so the plot keeps a readable aspect at full width.
  const W = narrow ? 360 : 720, H = narrow ? 200 : 260;
  const L = narrow ? 28 : 34, R = narrow ? 46 : 58, T = 18, B = 26;
  // Type is in viewBox units, so it has to grow as the box narrows to
  // land at the same physical size on the glass.
  const FS = narrow ? 13 : 10;
  const hi = Math.max(...data, line) * 1.12 || 1;
  // A ROUND AXIS THAT STILL FITS THE DATA. Rounding the tick to a power
  // of ten put a 90-yard game on an axis that ran to 400 — the bars used
  // the bottom quarter of the plot and every difference between them was
  // flattened to nothing. That is the same failure as a clipped baseline,
  // pointing the other way, so the step comes off a nice-number ladder
  // instead: the smallest round tick whose four gridlines still cover the
  // data. 90 now tops out at 120, not 400.
  //
  // AND THE AXIS HAS TO BE ABLE TO GO BELOW ZERO, which it never did
  // while the only thing charted was a player stat. Ethan, 2026-08-13,
  // circling a run line: "i should be able to click on this prop and it
  // shows more info … and it will show the bar graph too." A game bet's
  // quantity is a MARGIN, and a team that lost by three has a value of
  // −3. Clamping the floor at zero would have drawn that as a 3-unit
  // stub above the baseline — a loss rendered as a win, which is a
  // wrong chart rather than a missing one.
  const lo = Math.min(0, ...data, line);
  const raw = Math.max(hi, -lo * 1.12) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const norm = (raw || 1) / mag;
  const tick = ([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
    .find((c) => c >= norm - 1e-9) || 10) * mag;
  // Rungs are counted each way from zero so the baseline is always ON a
  // gridline: four above, and only as many below as the data needs.
  const upRungs = Math.max(1, Math.ceil((hi || 1) / tick - 1e-9));
  const downRungs = Math.max(0, Math.ceil(-lo / tick - 1e-9));
  const top = tick * upRungs, bottom = -tick * downRungs;
  const y = (v) => T + (1 - (v - bottom) / (top - bottom)) * (H - T - B);
  const slot = (W - L - R) / n, bw = Math.min(30, slot - 8);
  const bx = (i) => L + i * slot + (slot - bw) / 2;

  /* WHO EACH BAR WAS AGAINST. Ethan, 2026-08-13, circling the row of
     1-10 under the bars: "instead of showing 1-10 under the graphs, we
     should show 'vs whatever team they played that game'."

     He is right and the numbers were never information — they counted
     the bars, which the reader can already see. The opponent is the one
     thing a bar cannot say for itself and the first thing you ask about
     a three-strikeout game: three against WHO.

     The data needs no new source. `recent_values` is built as
     `[g.value for g in prop.logs]` in every pipeline, so `logs` is
     index-aligned with it — same order, same rows. The chart reverses
     to oldest-first, so the labels reverse with it or every bar would be
     captioned with the wrong game, which is worse than a number.

     `@` means away, nothing means home — the convention every box score
     uses, and it costs one character where there is no room for three.  */
  const labelsOf = (src) => {
    if (!Array.isArray(src) || src.length < n) return null;
    const out = src.slice(0, n).map((g) => {
      const opp = String((g && g.opponent) || "").toUpperCase();
      if (!opp) return null;
      return (g.home === false ? "@" : "") + opp;
    }).reverse();                       // oldest -> newest, as the bars are
    return out.every(Boolean) ? out : null;
  };
  // `opts.labels` arrives in the SAME order as `recent_values` — newest
  // first — so it is reversed here exactly like the log-derived ones.
  // Two orders for one argument is how a chart ends up captioning every
  // bar with the wrong game and looking fine while doing it.
  const labels = (opts.labels && opts.labels.length >= n
    ? opts.labels.slice(0, n).map(String).reverse()
    : null) || labelsOf(r.logs);
  // TYPE THAT DOES NOT FIT IS NOT A LABEL. Ten clubs under ten bars on a
  // phone is 28 viewBox units per name, and "@SDP" set to fill that
  // leaves under two units of gutter — legible in the abstract, a smear
  // in the hand.
  //
  // So the row STAGGERS before it shrinks: alternate names drop a line,
  // which doubles the room each one has and keeps the type at the size
  // every other label on the chart is set in. Shrinking to fit is the
  // fallback, not the first move, and below a floor the opponent is
  // dropped for the bar's number rather than printed too small to read.
  const CW = 0.58;                     // rough width per character, in ems
  const widest = labels ? Math.max(...labels.map((t) => t.length)) : 1;
  const fits = (room) => (room - 4) / (widest * CW);
  const stagger = !!labels && fits(slot) < FS && fits(2 * slot) >= FS * 0.85;
  const axisFS = labels
    ? Math.min(FS, Math.max(6.5, fits(stagger ? 2 * slot : slot))) : FS;
  const axisText = (i) => (labels && axisFS >= 6.6) ? labels[i] : String(i + 1);
  // Two rows live inside the bottom margin the plot already reserves, so
  // nothing overlaps the lowest gridline.
  const axisY = (i) => (stagger ? (i % 2 ? H - 4 : H - 16) : H - 8);

  let grid = "";
  for (let k = -downRungs; k <= upRungs; k++) {
    const v = tick * k;
    grid += `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}"
        stroke="var(--border-soft)" stroke-width="1" opacity=".6"/>
      <text x="${L - 6}" y="${y(v) + FS * .35}" text-anchor="end" font-size="${FS}"
        fill="var(--text-faint)" font-variant-numeric="tabular-nums">${
        Number(v.toFixed(2))}</text>`;
  }
  const bars = data.map((v, i) => {
    const c = won(v) ? "var(--good)" : "var(--bad)";
    // A bar hangs DOWN from the baseline when its value is negative. The
    // label follows it, or it would sit inside the bar it describes.
    const yt = y(v), y0 = y(0), down = v < 0;
    const h = Math.max(3, Math.abs(y0 - yt));
    return `<rect x="${bx(i).toFixed(1)}" y="${(down ? y0 : y0 - h).toFixed(1)}"
        width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${c}"
        data-tip="${escapeAttr(labels ? `${labels[i]} — ${v}`
          : `Game ${i + 1} — ${v}`)}" style="pointer-events:all;cursor:pointer"/>
      <text x="${(bx(i) + bw / 2).toFixed(1)}" y="${
        (down ? y0 + h + FS : yt - 5).toFixed(1)}"
        text-anchor="middle" font-size="${FS}" fill="${c}"
        paint-order="stroke" stroke="var(--panel)" stroke-width="3"
        font-variant-numeric="tabular-nums">${v}</text>
      <text x="${(bx(i) + bw / 2).toFixed(1)}" y="${axisY(i)}" text-anchor="middle"
        font-size="${axisFS.toFixed(1)}" fill="var(--text-faint)">${
        escapeHtml(axisText(i))}</text>`;
  }).join("");
  const ly = y(line);
  const pill = `<g>
      <rect x="${W - R + 6}" y="${ly - FS}" width="${R - 12}" height="${FS * 2}" rx="3"
        fill="var(--panel-3)" stroke="var(--border)"/>
      <text x="${W - R + (R - 12) / 2 + 6}" y="${ly + FS * .35}" text-anchor="middle" font-size="${FS}"
        fill="var(--text)" font-variant-numeric="tabular-nums">${line}</text>
      <text x="${W - R + (R - 12) / 2 + 6}" y="${ly + FS * 1.9}" text-anchor="middle" font-size="${FS * .8}"
        fill="var(--text-faint)">LINE</text></g>`;

  const tile = (v, k, tone) => `<div class="pa-tile">
      <div class="pa-v ${tone || ""}">${v}</div><div class="pa-k">${k}</div></div>`;
  const ev = r.ev_per_unit;
  const conf = r.confidence >= 8 ? "HIGH" : r.confidence >= 6 ? "MEDIUM" : "LOW";
  // Position and team are both journaled, so the render's "QB · KANSAS
  // CITY CHIEFS" line is real data rather than a caption. A prop missing
  // either prints what it has instead of an empty separator.
  const who = [r.position, (typeof teamName === "function"
    ? teamName(r.team) : r.team)].filter(Boolean).join(" · ");
  // ONE FACE PER CARD. Ethan, 2026-08-13, on the Long Shots board: "we
  // are definitely showing the players face too much here". He is right
  // and it is structural, not a one-page slip: every card that renders
  // this block already draws the player in its own head — the props
  // card, the long shot card and the top-picks card all lead with
  // `playerAvatar`. The 92px portrait his render asked for made sense as
  // a standalone card; inside a card that has already introduced the
  // player it is the same photograph twice, forty pixels apart.
  //
  // Dropping it is also what makes the chart bigger, which was his
  // second ask and the same fix: the identity column was eating a third
  // of the width to repeat information, and the plot now spans the card.
  // Name and team stay in the head where they already were; what this
  // block still owes the reader is the PROP / LINE / ODDS it is charting
  // against, so that becomes a slim bar over a full-width plot.
  return `
  <div class="prop-analysis pa-${tone}">
    <div class="pa-bar">
      <span class="pa-cell"><span class="pa-k">${escapeHtml(opts.what || "PROP")}</span>
        <span class="pa-m">${escapeHtml(r.market_label || r.market || "")}</span></span>
      <span class="pa-cell"><span class="pa-k">LINE</span>
        <span class="pa-big">${escapeHtml(String(line))}</span></span>
      <span class="pa-cell"><span class="pa-k">ODDS (${escapeHtml(
        opts.sideLabel || (over ? "OVER" : "UNDER"))})</span>
        <span class="pa-big ${tone === "good" ? "pos" : "neg"}">${
          r.odds > 0 ? "+" : ""}${r.odds}</span></span>
      ${who ? `<span class="pa-who2">${escapeHtml(who)}</span>` : ""}
    </div>
    <div class="pa-chart">
      <div class="pa-head"><span>${escapeHtml(
          opts.head || `LAST ${n} GAMES vs PROP LINE`)}</span>
        <span class="pa-legend"><i class="ok"></i>${escapeHtml(
          (opts.legend || ["OVER", "UNDER"])[0])}<i class="no"></i>${escapeHtml(
          (opts.legend || ["OVER", "UNDER"])[1])}</span></div>
      <svg viewBox="0 0 ${W} ${H}" role="img"
           aria-label="${escapeAttr(`${hits} of the last ${n} games cleared ${line}`)}">
        ${grid}
        <line x1="${L}" y1="${ly}" x2="${W - R + 4}" y2="${ly}" stroke="var(--text)"
          stroke-width="1" stroke-dasharray="5 4" opacity=".75"/>
        ${bars}${pill}
      </svg>
      <div class="pa-stats">
        ${tile(`${hits} / ${n}`, "HIT RATE", backs ? "pos" : "neg")}
        ${tile(`${Math.round((hits / n) * 100)}%`, "HIT %", backs ? "pos" : "neg")}
        ${tile(ev == null ? "—" : `${ev >= 0 ? "+" : ""}${ev.toFixed(2)}`, "EV",
               (ev || 0) >= 0 ? "pos" : "neg")}
        ${tile(conf, "CONFIDENCE", conf === "LOW" ? "neg" : "pos")}
      </div>
    </div>
  </div>`;
}

/* ---------------- Game-log bars (a prop against its line) ---------------- */
/* Ethan, 2026-08-16: "instead of line charts for the player stats we should
   be using bar graphs instead. They are easier to read and we can label
   things better."

   He is right, and the reason is stronger than preference. A line implies
   the value moved CONTINUOUSLY between two points, and there is no such
   thing between Tuesday's game and Thursday's — the player did not pass
   through 1.4 hits on Wednesday. These are independent measurements
   against a threshold, which is a bar's job: one mark per game, sitting
   on a common baseline, read against a rule.

   WHAT THE COLOUR IS ALLOWED TO CARRY. Cleared/missed is drawn in the
   site's status pair, and the validator is blunt about that pair:
   #42C268 against #DF5953 is ΔE 7.5 under deuteranopia — inside the 6–8
   floor band, which is legal ONLY with a second, non-colour encoding.
   Red-green is the textbook CVD collision and this is the textbook use
   of it.

   So colour here is REDUNDANT, never load-bearing. The threshold rule is
   drawn, and a bar clearing it is taller than it — position against a
   visible line reads with no colour vision at all. The count label says
   the same fact in words. Colour is the third telling, not the first.  */
function gamelogBars(values, opts = {}) {
  const w = opts.w || 260, h = opts.h || 46;
  const padX = 2, padTop = 4, base = h - 11;      // room for the count line
  const line = opts.line;
  const raw = [...(values || [])];
  const rawLabs = opts.labels ? [...opts.labels] : null;
  const keep = raw.map((v, i) => ({ v: Number(v), i }))
    .filter((d) => Number.isFinite(d.v));
  if (!keep.length) return `<svg width="${w}" height="${h}"></svg>`;
  // Newest-first in, oldest-first out — a bar chart reads left to right as
  // time, and the newest game is the one the eye should land on last.
  const capped = keep.slice(0, Math.max(3, Math.floor(w / 9))).reverse();
  const data = capped.map((d) => d.v);
  const labs = rawLabs ? capped.map((d) => rawLabs[d.i]) : null;

  // The scale starts at ZERO. A bar's length IS its value, so a clipped
  // baseline makes a 2 look twice a 1.5 — the single most common way a
  // bar chart lies, and the reason this is not just a restyled sparkline.
  const hi = Math.max(...data, line ?? 0) || 1;
  const n = data.length;
  const slot = (w - padX * 2) / n;
  const bw = Math.max(3, slot - 2);               // 2px surface gap
  const bx = (i) => padX + i * slot + (slot - bw) / 2;
  const by = (v) => base - (v / hi) * (base - padTop);

  /* WHOSE SIDE THE CHART IS ON.
     Ethan, 2026-08-25, pointing at an UNDER 1.5 Hits row reading
     "1/10 cleared 1.5": "The chart should Correlate to the prop being
     displayed obviously."

     It did not. `v > line` is "did the stat go over", which is the
     bet only when the bet is an OVER. On his row the single green bar
     was the one game the UNDER LOST and the nine red ones were the
     nine it won — the chart telling the reader the exact opposite of
     what it looked like it was saying, in the site's status colours.

     `propAnalysis` has always got this right; this compact version
     never took the side at all. With `opts.side` the bars mean "the
     bet cashed" and the caption states which direction it needed, so
     the number is unambiguous without the colours. Without it, the
     old over-the-line reading is kept for callers that genuinely have
     no side — a form sparkline on a player page is not a bet. */
  const side = String(opts.side || "").toUpperCase();
  const under = side === "UNDER";
  const won = (v) => (under ? v < line : v > line);
  const cleared = line == null ? null : data.filter(won).length;
  const bars = data.map((v, i) => {
    const top = by(v);
    // A ZERO IS DATA. At `Math.max(1, ...)` a 0-hit game rendered as a
    // 1px sliver, which on a dark panel is indistinguishable from empty
    // space — so a night the player was blanked read as a night he did
    // not play. Caught by looking at the render, not by any check: the
    // arithmetic was right and the picture lied. A floor of 3px makes a
    // blank game a visible, clearly-missed bar sitting on the baseline.
    const hgt = Math.max(3, base - top);
    const c = line == null ? (opts.stroke || "var(--brand)")
      : (won(v) ? "var(--good)" : "var(--bad)");
    const tip = (labs && labs[i] ? labs[i] + " — " : "") + v;
    // rx rounds the data-end; the bar is anchored to the baseline.
    return `<rect x="${bx(i).toFixed(1)}" y="${(base - hgt).toFixed(1)}"
      width="${bw.toFixed(1)}" height="${hgt.toFixed(1)}" rx="${Math.min(2, bw / 2)}"
      fill="${c}" opacity="${i === n - 1 ? 1 : 0.72}"
      data-tip="${escapeAttr(tip)}" style="pointer-events:all;cursor:pointer"/>`;
  }).join("");

  const rule = line == null ? "" : `
    <line x1="0" y1="${by(line).toFixed(1)}" x2="${w}" y2="${by(line).toFixed(1)}"
      stroke="var(--warn)" stroke-width="1" stroke-dasharray="4 3" opacity=".85"/>`;
  // The label Ethan asked for. Text in a text token, never the series
  // colour, and it states the fact the colours encode so the chart does
  // not depend on telling green from red.
  // "cleared 1.5" reads as "went over 1.5" whatever the bet was, so a
  // side-aware chart names the direction instead of reusing the word.
  const capt = side
    ? `${cleared}/${n} ${under ? "under" : "over"} ${line}`
    : `${cleared}/${n} cleared ${line}`;
  const label = cleared == null ? "" : `
    <text x="0" y="${h - 1}" fill="var(--text-mute)" font-size="9"
      font-variant-numeric="tabular-nums">${capt}</text>`;
  return `
  <svg class="glbars" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"
       role="img" aria-label="${escapeAttr(
         cleared == null ? `last ${n} games`
           : side
             ? `${cleared} of the last ${n} games came in ${under
                 ? "under" : "over"} ${line} — the side of this bet`
             : `${cleared} of the last ${n} games cleared ${line}`)}">
    ${rule}${bars}${label}
  </svg>`;
}

/* ---------------- Sparkline (game-log trend) ----------------------------- */
/* A RING WITH A COUNT IN IT — the record breakdown on Ethan's UFC
   render (2026-08-25). Wins, losses and pushes as arcs, the total in the
   middle, and a legend beside it that carries the actual numbers.

   DRAWN, NOT CHARTED. Every other proportion on this site is drawn in
   plain SVG for the same reason: a chart library is a network request
   between the reader and a number we already have, and the pages that
   depend on one go blank when the CDN does. This is four circles.

   A ZERO TOTAL IS A REAL STATE, not a divide-by-zero. A book with
   nothing settled draws an empty ring and says 0 — which is the honest
   picture on a Tuesday before the first card, and much better than the
   NaN arc that the obvious arithmetic produces there. */
function donutRing(segments, opts = {}) {
  const size = opts.size || 132;
  const stroke = opts.stroke || 15;
  const r = (size - stroke) / 2;
  const C = 2 * Math.PI * r;
  const rows = (segments || []).filter((s) => s && (s.value || 0) > 0);
  const total = (segments || []).reduce((a, s) => a + (s.value || 0), 0);
  let at = 0;
  const arcs = rows.map((sg) => {
    const len = C * ((sg.value || 0) / total);
    const el = `<circle cx="${size / 2}" cy="${size / 2}" r="${r}"
      fill="none" stroke="${sg.color}" stroke-width="${stroke}"
      stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}"
      stroke-dashoffset="${(-at).toFixed(2)}"/>`;
    at += len;
    return el;
  }).join("");
  return `<svg class="donut" viewBox="0 0 ${size} ${size}"
      width="${size}" height="${size}" role="img"
      aria-label="${escapeAttr(opts.alt || `${total} total`)}">
    <g transform="rotate(-90 ${size / 2} ${size / 2})">
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none"
        stroke="var(--border-soft)" stroke-width="${stroke}"/>
      ${arcs}
    </g>
    <text class="donut-n" x="${size / 2}" y="${size / 2 - 2}"
      text-anchor="middle" dominant-baseline="middle">${total}</text>
    <text class="donut-k" x="${size / 2}" y="${size / 2 + 16}"
      text-anchor="middle" dominant-baseline="middle">${
        escapeAttr(opts.caption || "")}</text>
  </svg>`;
}

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

  let lo = Math.min(...data, line ?? Infinity);
  let hi = Math.max(...data, line ?? -Infinity);
  // A sparkline autoscales to whatever it is given, which is right when
  // the caller has no idea what range to expect and WRONG when it does.
  // The live-line track knows: win probability moves on a 0-100 scale, so
  // a half-point wobble handed to a bare autoscale fills the full chart
  // height and draws a dramatic collapse where the market did nothing.
  // `minSpan` pins a floor on the vertical domain, centred on the data,
  // so small movement looks small. Default 0 = autoscale, unchanged for
  // every caller that does not ask.
  const minSpan = Number(opts.minSpan) || 0;
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
  }
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

  // Finger scrubbing (the shared engine below): the same words the hover
  // dots carry, snapped to wherever the finger is.
  const scrub = escapeAttr(JSON.stringify({
    padL: pad, padR: pad,
    l: labs || [], v: data.map((v) => String(v) + (opts.unit || "")),
  }));
  return `
  <svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" data-scrub="${scrub}">
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

/* WHAT A FINGERTIP AND THE HAND BEHIND IT HIDE, in CSS pixels. Shared by
   both tooltips on this page — the per-bar label and the line-chart
   scrubber — because they are answering the same question about the same
   finger, and two different numbers would mean one of them is wrong. */
const FINGER = 46;

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
  /* A FINGER IS NOT A CURSOR. Ethan, 2026-08-22, on the popup's bar
     chart: "when you hold your finger on the graph too see the number,
     my finger is in the way and i cant see the number."

     This placed the label 14px right and 30px above the pointer, which
     is correct for a mouse — the cursor is a few pixels of arrow and the
     hand is nowhere near the screen. A fingertip covers roughly 45px,
     and the hand behind it covers everything below and to the right of
     the contact point, which is exactly where those two offsets put the
     answer.

     So touch gets its own placement: centred on the finger horizontally
     and lifted clear of it vertically. When there is no room above — a
     chart near the top of the screen — it goes to the SIDE rather than
     below, because below is under the same finger. */
  function place(e) {
    const el = ensure();
    const touch = e.pointerType === "touch" || e.pointerType === "pen";
    const w = el.offsetWidth || 80, h = el.offsetHeight || 28;
    let lx, ly;
    if (touch) {
      lx = e.clientX - w / 2;
      ly = e.clientY - h - FINGER;
      if (ly < 8) {
        // No room above. Beside it, on whichever side has space.
        ly = Math.max(8, Math.min(window.innerHeight - h - 8,
                                  e.clientY - h / 2));
        lx = e.clientX + FINGER;
        if (lx + w > window.innerWidth - 8) lx = e.clientX - w - FINGER;
      }
    } else {
      lx = e.clientX + 14;
      ly = e.clientY - 30;
      if (lx + w > window.innerWidth - 8) lx = e.clientX - w - 14;
      if (ly < 8) ly = e.clientY + 14;
    }
    el.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, lx)) + "px";
    el.style.top = Math.max(8, ly) + "px";
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
  /* A touch that turns into a scroll fires `pointercancel` and no
     `pointerout`, which left the label stranded on screen over whatever
     scrolled underneath it. Scrolling hides it for the same reason. */
  ["pointercancel", "pointerup"].forEach((k) =>
    document.addEventListener(k, () => {
      if (tipEl) tipEl.style.display = "none";
    }, { passive: true }));
  document.addEventListener("scroll", () => {
    if (tipEl) tipEl.style.display = "none";
  }, { passive: true, capture: true });
})();


/* ---------------- finger scrubbing on line charts ----------------
   Ethan, 2026-08-18: "you can glide your finger across it an it will
   show the data for wherever your finger is gliding, we should have
   that for any line chart we have on the site."

   Any line chart opts in by carrying, on its <svg>:

       data-scrub='{"padL":46,"padR":14,"l":[labels],"v":[values],
                    "x":[optional 0..1 fractions for uneven spacing]}'

   One crosshair rail and one label serve every chart: the pointer's x
   maps through the svg's viewBox to the nearest point, the rail marks
   the snapped position, the label shows that point's own words. Works
   for a mouse for free — pointer events cover both.

   Touch keeps the page scrollable: `touch-action: pan-y` on these svgs
   means a horizontal glide reads the chart while a vertical drag still
   scrolls, which is why none of these handlers ever preventDefault. */
(function () {
  let tip = null, rail = null;
  function ensure() {
    if (tip) return;
    tip = document.createElement("div");
    tip.className = "graph-tip scrub-tip";
    tip.style.display = "none";
    rail = document.createElement("div");
    rail.className = "scrub-rail";
    rail.style.display = "none";
    document.body.append(tip, rail);
  }
  function hide() {
    if (tip) { tip.style.display = "none"; rail.style.display = "none"; }
  }
  function show(svg, clientX, clientY, touch) {
    ensure();
    let d = svg._scrub;
    if (!d) {
      try { d = svg._scrub = JSON.parse(svg.dataset.scrub); }
      catch (e) { return; }
    }
    const n = (d.v || []).length;
    const rect = svg.getBoundingClientRect();
    if (!n || rect.width < 10) return;
    const vw = Number((svg.getAttribute("viewBox") || "").split(/\s+/)[2])
      || rect.width;
    const padL = d.padL || 0, padR = d.padR || 0;
    const span = Math.max(1, vw - padL - padR);
    const frac = Math.min(1, Math.max(0,
      ((clientX - rect.left) * (vw / rect.width) - padL) / span));
    // Uneven series (the coin tape is one point per refresh) carry their
    // own x fractions; evenly spaced charts derive them.
    let i = 0;
    if (d.x && d.x.length === n) {
      let best = Infinity;
      for (let k = 0; k < n; k++) {
        const dist = Math.abs(d.x[k] - frac);
        if (dist < best) { best = dist; i = k; }
      }
    } else {
      i = Math.round(frac * (n - 1));
    }
    const fx = d.x && d.x.length === n ? d.x[i] : (n > 1 ? i / (n - 1) : 0);
    const snapX = rect.left + (padL + fx * span) * (rect.width / vw);
    tip.innerHTML = (d.l && d.l[i] != null
      ? `<span class="st-l">${escapeHtml(String(d.l[i]))}</span>` : "")
      + escapeHtml(String(d.v[i]));
    tip.style.display = "block";
    const tw = tip.offsetWidth || 90, th = tip.offsetHeight || 34;
    let lx = snapX - tw / 2;
    /* ABOVE THE CHART IS NOT THE SAME AS CLEAR OF THE FINGER. This put
       the label ten pixels above the svg's top edge, which is plenty on
       the tall record chart and nowhere near enough on a sparkline: at
       40px tall, a finger in the middle of it sits ~30px below the
       label, and a fingertip covers 46. Ethan reported the bar chart
       first and then "it also does that for to the line graph for the
       record page" — same complaint, different code path, because this
       one measured from the CHART and the other measured from the
       POINTER, and neither measured from the thing in the way. */
    let ly = rect.top - th - 10;
    if (touch) {
      ly = Math.min(ly, clientY - th - FINGER);
      if (ly < 8) {
        // No room above the finger. Beside it — below is the same finger.
        ly = Math.max(8, Math.min(window.innerHeight - th - 8, clientY - th / 2));
        lx = snapX + FINGER;
        if (lx + tw > window.innerWidth - 8) lx = snapX - tw - FINGER;
      }
    }
    tip.style.left = Math.min(window.innerWidth - tw - 6, Math.max(6, lx)) + "px";
    tip.style.top = Math.max(6, ly) + "px";
    rail.style.display = "block";
    rail.style.left = (snapX - 0.5) + "px";
    rail.style.top = rect.top + "px";
    rail.style.height = rect.height + "px";
  }
  const over = (e) => {
    const svg = e.target && e.target.closest
      ? e.target.closest("svg[data-scrub]") : null;
    if (svg) show(svg, e.clientX, e.clientY,
                  e.pointerType === "touch" || e.pointerType === "pen");
    else hide();
  };
  document.addEventListener("pointerdown", over, { passive: true });
  document.addEventListener("pointermove", over, { passive: true });
  ["pointerup", "pointercancel"].forEach((k) =>
    document.addEventListener(k, hide, { passive: true }));
  // On document with capture, not on window: scroll does not bubble, but
  // capture sees every scroller (the page AND the drawer), and the
  // headless test harness stubs document, not window.
  document.addEventListener("scroll", hide, { passive: true, capture: true });
})();

/* ---- Gloss charts — ApexCharts, vendored (web/vendor) -------------------
   Ethan, 2026-08-18: "no shiny good graphics like a real put together
   website and app would offer." The hand-drawn SVGs stay in the markup
   as the no-dependency fallback; when the vendored library is present,
   any element carrying data-gloss-curve is upgraded in place to an
   animated, crosshair-scrubbing gradient area chart. One mount function,
   one visual grammar, colors read from the live theme tokens so the
   charts recolor with the theme like everything else. */
function mountGlossCharts(root) {
  if (!window.ApexCharts) return;                 // vendored file absent
  ((root || document).querySelectorAll("[data-gloss-curve]")).forEach((el) => {
    if (el.dataset.glossed) return;
    let cfg;
    try { cfg = JSON.parse(el.getAttribute("data-gloss-curve")); }
    catch (e) { return; }
    const vals = (cfg.values || []).map(Number).filter((v) => isFinite(v));
    if (vals.length < 2) return;
    const labels = cfg.labels || vals.map((_, i) => String(i + 1));
    const css = getComputedStyle(document.documentElement);
    const tok = (n) => (css.getPropertyValue(n) || "").trim();
    const tone = cfg.tone === "down" ? tok("--bad")
      : cfg.tone === "up" ? tok("--good") : tok("--brand");
    const fmt = cfg.money
      ? (v) => `${v < 0 ? "\u2212" : ""}$${Math.abs(v).toFixed(2)}`
      : (v) => `${cfg.signed && v > 0 ? "+" : ""}${Number(v).toFixed(2)}${cfg.unit || ""}`;
    el.dataset.glossed = "1";
    el.innerHTML = "";
    const chart = new ApexCharts(el, {
      chart: {
        type: "area", height: cfg.h || 170, width: "100%",
        sparkline: { enabled: true }, parentHeightOffset: 0,
        animations: { enabled: true, speed: 650,
                      dynamicAnimation: { enabled: false } },
      },
      series: [{ name: cfg.name || "", data: vals }],
      colors: [tone],
      stroke: { curve: "smooth", width: 2.5, lineCap: "round" },
      fill: { type: "gradient", gradient: {
        shadeIntensity: 0, opacityFrom: 0.34, opacityTo: 0, stops: [0, 100] } },
      markers: { size: 0, strokeWidth: 0, hover: { size: 5 } },
      tooltip: {
        theme: "dark",
        x: { formatter: (i) => String(labels[i - 1] ?? "") },
        y: { formatter: fmt, title: { formatter: () => "" } },
      },
    });
    chart.render();
    el._gloss = chart;
  });
}

/* ---- ECharts panels — the showpiece layer (vendored, lazy) --------------
   Ethan, 2026-08-18: "start on the Echarts and work down." The engine is
   a megabyte, so unlike ApexCharts it is NOT in the boot path: the first
   panel that needs it injects /vendor/echarts.min.js once and every
   later mount reuses it. Same contract as the gloss charts — the
   hand-drawn markup stays as the fallback, the library only upgrades it
   in place, and every color is read live from the theme tokens. */
let _echartsLoading = null;
function loadECharts() {
  if (window.echarts) return Promise.resolve(window.echarts);
  if (_echartsLoading) return _echartsLoading;
  _echartsLoading = new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "vendor/echarts.min.js";
    // A missing vendor file resolves null and the fallbacks simply stay —
    // the library is an enhancement, never a dependency.
    s.onload = () => resolve(window.echarts || null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
  return _echartsLoading;
}

const _echartsLive = [];
// Guarded: the test harness executes this file in bare Node with a
// stubbed document and NO window (see the scroll listener below).
if (typeof window !== "undefined" && window.addEventListener) {
  window.addEventListener("resize", () => {
    for (const c of _echartsLive) { try { c.resize(); } catch (e) {} }
  });
}

async function mountEChartsPanels(root) {
  const host = root || document;
  const nodes = [...host.querySelectorAll(
    "[data-echart-gauge],[data-echart-hist],[data-echart-radar],"
    + "[data-echart-tape]")]
    .filter((el) => !el.dataset.echarted);
  if (!nodes.length) return;
  const ec = await loadECharts();
  if (!ec) return;
  const css = getComputedStyle(document.documentElement);
  const tok = (n) => (css.getPropertyValue(n) || "").trim();
  const font = tok("--font-sans") || "sans-serif";
  for (const el of nodes) {
    // Re-check under the await: a second concurrent mount (render call +
    // the delegated tab-click retry) captured its node list before this
    // one marked anything, and its innerHTML wipe would blank the chart
    // the first call just drew.
    if (el.dataset.echarted || ec.getInstanceByDom(el)) continue;
    let cfg;
    const kind = el.hasAttribute("data-echart-gauge") ? "gauge"
      : el.hasAttribute("data-echart-radar") ? "radar"
      : el.hasAttribute("data-echart-tape") ? "tape" : "hist";
    if (!el.clientWidth) continue;     // hidden room — retried on tab switch
    try {
      cfg = JSON.parse(el.getAttribute(`data-echart-${kind}`));
    } catch (e) { continue; }
    // Radar validity is checked BEFORE the wipe: a bad payload must
    // leave the fallback table standing, not an empty box.
    if (kind === "radar" && ((cfg.axes || []).length < 3
        || (cfg.series || []).length < 2)) continue;
    el.dataset.echarted = "1";
    el.innerHTML = "";
    const chart = ec.init(el, null, { renderer: "canvas" });
    if (kind === "gauge") {
      // Home win probability as a half-gauge: the arc runs the away
      // color into the home color, the progress needle-lessly fills to
      // the sim's share, the number sits in the middle.
      const v = Math.round(100 * (cfg.value || 0));
      chart.setOption({
        animationDuration: 700,
        series: [{
          type: "gauge", startAngle: 200, endAngle: -20,
          min: 0, max: 100, center: ["50%", "62%"], radius: "98%",
          pointer: { show: false },
          progress: { show: true, roundCap: true, width: 12,
            itemStyle: { color: new ec.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: tok("--brand-2") },
              { offset: 1, color: tok("--brand") }]) } },
          axisLine: { roundCap: true,
            lineStyle: { width: 12, color: [[1, tok("--panel-3")]] } },
          axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { show: false },
          anchor: { show: false },
          title: { show: true, offsetCenter: [0, "34%"],
            color: tok("--text-mute"), fontSize: 11, fontFamily: font },
          detail: { valueAnimation: true, offsetCenter: [0, "-8%"],
            formatter: (x) => `${Math.round(x)}%`,
            color: tok("--text"), fontSize: 30, fontWeight: 800,
            fontFamily: font },
          data: [{ value: v, name: cfg.title || "" }],
        }],
      });
    } else if (kind === "tape") {
      /* THE PRICE TAPE — Ethan, 2026-08-19, with a Polymarket screenshot:
         "add where we can click on the trade it's recommending and it
         will pull up a chart of the live odds just how Kalshi or
         Polymarket does it."

         Two lines, because a binary market has two sides and the render
         shows both: the YES side and its complement, each labelled at the
         right edge with its current number, the way both venues do it.

         EVERY POINT IS ONE WE OBSERVED. The series is our own 10-minute
         snapshot tape — no interpolation across gaps, no backfill before
         the day we started recording, because an order book cannot be
         reconstructed and a smooth line through hours we never saw is a
         picture of a market that did not exist. `connectNulls` stays
         FALSE for the same reason: a break in the line is the honest
         drawing of a break in the record. */
      const pts = (cfg.points || []).filter((p) => Array.isArray(p) && p.length > 1);
      if (pts.length < 2) { el.dataset.echarted = ""; continue; }
      const yes = pts.map((p) => [p[0] * 1000, +(p[1] * 100).toFixed(1)]);
      const no = pts.map((p) => [p[0] * 1000, +((1 - p[1]) * 100).toFixed(1)]);
      const yesName = cfg.yes_label || "Yes";
      const noName = cfg.no_label || "No";
      const line = (name, data, color) => ({
        name, type: "line", data, showSymbol: false, connectNulls: false,
        smooth: false, lineStyle: { width: 2, color },
        emphasis: { focus: "series" },
        endLabel: { show: true, color, fontFamily: font, fontSize: 11,
          fontWeight: 700, distance: 6,
          formatter: (o) => `${name} ${Math.round(o.value[1])}%` },
      });
      chart.setOption({
        animationDuration: 500,
        // The right gutter holds the end labels; too little and they
        // print over the line they belong to.
        grid: { left: 4, right: 104, top: 14, bottom: 20, containLabel: true },
        tooltip: { trigger: "axis", confine: true,
          backgroundColor: tok("--panel-2"),
          borderColor: tok("--border-soft"),
          textStyle: { color: tok("--text"), fontFamily: font, fontSize: 11 },
          valueFormatter: (v) => `${v}%` },
        // PINNED TO THE DATA. Left to itself the time axis rounds outward
        // to tidy hour boundaries, which leaves the line ending halfway
        // across an empty plot and reads as "the market stopped moving".
        // The axis is exactly as wide as what we recorded.
        xAxis: { type: "time", boundaryGap: false,
          min: yes[0][0], max: yes[yes.length - 1][0],
          axisLine: { lineStyle: { color: tok("--panel-3") } },
          axisTick: { show: false },
          axisLabel: { color: tok("--text-mute"), fontFamily: font,
            fontSize: 10, hideOverlap: true } },
        yAxis: { type: "value", min: 0, max: 100,
          splitLine: { lineStyle: { color: tok("--panel-3") } },
          axisLabel: { color: tok("--text-mute"), fontFamily: font,
            fontSize: 10, formatter: "{value}%" } },
        series: [line(yesName, yes, tok("--good")),
                 line(noName, no, tok("--bad"))],
      });
      _echartsLive.push(chart);
      continue;
    } else if (kind === "radar") {
      // The two-team shape. Every axis is a league percentile (0-100),
      // so the polygons share one honest scale; home wears the brand,
      // away the neutral, both translucent so the overlap reads.
      const axes = cfg.axes || [];
      const series = (cfg.series || []).slice(0, 2);
      chart.setOption({
        animationDuration: 700,
        legend: { bottom: 0, itemWidth: 10, itemHeight: 10,
          textStyle: { color: tok("--text-mute"), fontSize: 10,
                       fontFamily: font } },
        tooltip: { trigger: "item",
          backgroundColor: tok("--panel-3"), borderColor: tok("--border"),
          textStyle: { color: tok("--text"), fontSize: 11,
                       fontFamily: font } },
        radar: {
          indicator: axes.map((nm) => ({ name: nm, max: 100 })),
          radius: "66%", center: ["50%", "46%"],
          axisName: { color: tok("--text-mute"), fontSize: 10,
                      fontFamily: font },
          splitArea: { show: false },
          splitLine: { lineStyle: { color: tok("--border-soft") } },
          axisLine: { lineStyle: { color: tok("--border") } },
        },
        series: [{ type: "radar", symbolSize: 4,
          data: series.map((s, i) => {
            const c = i ? tok("--text-mute") : tok("--brand");
            return { name: s.name, value: s.values,
              lineStyle: { width: 2, color: c },
              itemStyle: { color: c },
              areaStyle: { color: c, opacity: 0.16 } };
          }) }],
      });
    } else {
      const labels = cfg.labels || [];
      const vals = (cfg.values || []).map((x) => +(100 * x).toFixed(1));
      const half = Math.ceil(vals.length / 2);
      const barColor = (i) => {
        const base = i < half ? tok("--brand") : tok("--text-mute");
        return new ec.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: base },
          { offset: 1, color: base + "33" }]);
      };
      chart.setOption({
        animationDuration: 650,
        grid: { left: 4, right: 4, top: 8, bottom: 22, containLabel: false },
        xAxis: { type: "category", data: labels,
          axisTick: { show: false }, axisLine: { show: false },
          axisLabel: { color: tok("--text-mute"), fontSize: 9,
            fontFamily: font, interval: 0 } },
        yAxis: { show: false },
        tooltip: { trigger: "axis",
          backgroundColor: tok("--panel-3"), borderColor: tok("--border"),
          textStyle: { color: tok("--text"), fontSize: 11, fontFamily: font },
          valueFormatter: (x) => `${x}% of replays` },
        series: [{
          type: "bar", data: vals.map((v, i) => ({
            value: v, itemStyle: { color: barColor(i),
              borderRadius: [3, 3, 0, 0] } })),
          barCategoryGap: "28%",
        }],
      });
    }
    _echartsLive.push(chart);
    if (_echartsLive.length > 24) {
      const old = _echartsLive.shift();
      try { old.dispose(); } catch (e) {}
    }
  }
}

/* Rungs two and three of the ECharts descent (Ethan: "keep going"):
   the Record page's reliability diagram and the Prediction Market's
   MODEL vs MARKET overhead. Same contract as every showpiece mount —
   the hand-drawn SVG ships in the wrapper and stays when the engine
   is missing; colors come from the live tokens. */
async function mountEChartsAnalytics(root) {
  const host = root || document;
  const nodes = [...host.querySelectorAll(
    "[data-echart-reliability],[data-echart-dumbbell]")]
    .filter((el) => !el.dataset.echarted);
  if (!nodes.length) return;
  const ec = await loadECharts();
  if (!ec) return;
  const css = getComputedStyle(document.documentElement);
  const tok = (n) => (css.getPropertyValue(n) || "").trim();
  const font = tok("--font-sans") || "sans-serif";
  const axis = {
    axisLine: { lineStyle: { color: tok("--border") } },
    axisLabel: { color: tok("--text-mute"), fontSize: 10, fontFamily: font },
    splitLine: { lineStyle: { color: tok("--border-soft") } },
  };
  const tip = {
    backgroundColor: tok("--panel-3"), borderColor: tok("--border"),
    textStyle: { color: tok("--text"), fontSize: 11, fontFamily: font },
  };
  for (const el of nodes) {
    // Same double-mount guard as mountEChartsPanels — see its comment.
    if (el.dataset.echarted || ec.getInstanceByDom(el)) continue;
    const kind = el.hasAttribute("data-echart-reliability")
      ? "reliability" : "dumbbell";
    if (!el.clientWidth) continue;     // hidden room — retried on tab switch
    let cfg;
    try { cfg = JSON.parse(el.getAttribute(`data-echart-${kind}`)); }
    catch (e) { continue; }
    el.dataset.echarted = "1";
    if (kind === "reliability") {
      const pts = (cfg.buckets || []).filter((b) => b.n > 0);
      if (pts.length < 2) { delete el.dataset.echarted; continue; }
      el.innerHTML = "";
      const maxN = Math.max(...pts.map((b) => b.n));
      const color = (b) => b.n < 20 ? tok("--text-mute")
        : b.in_band ? tok("--good") : tok("--warn");
      const chart = ec.init(el);
      chart.setOption({
        animationDuration: 600,
        grid: { left: 34, right: 16, top: 18, bottom: 30 },
        xAxis: { ...axis, min: 0, max: 100, name: "model said",
          nameLocation: "middle", nameGap: 20,
          nameTextStyle: { color: tok("--text-mute"), fontSize: 10 } },
        yAxis: { ...axis, min: 0, max: 100 },
        tooltip: { ...tip, trigger: "item",
          formatter: (p) => p.data.tt || "" },
        series: [
          { // The confidence whiskers, drawn as thin custom bars.
            type: "custom", z: 1,
            renderItem: (params, api) => {
              const xv = api.value(0);
              const lo = api.coord([xv, api.value(2)]);
              const hi = api.coord([xv, api.value(3)]);
              return { type: "line", shape: {
                  x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] },
                style: { stroke: api.value(4), lineWidth: 1.5,
                         opacity: 0.55 } };
            },
            data: pts.map((b) => [100 * b.predicted, 100 * b.actual,
              100 * Math.max(0, b.actual - b.ci),
              100 * Math.min(1, b.actual + b.ci), color(b)]),
          },
          { type: "scatter", z: 2,
            symbolSize: (d) => 7 + 15 * Math.sqrt((d[2] || 1) / maxN),
            itemStyle: { opacity: 0.8 },
            data: pts.map((b) => ({
              value: [100 * b.predicted, 100 * b.actual, b.n],
              itemStyle: { color: color(b) },
              tt: `Said ${(100 * b.predicted).toFixed(0)}%, hit `
                + `${(100 * b.actual).toFixed(0)}% — ${b.n} bets`,
            })),
            markLine: { silent: true, symbol: "none",
              label: { show: true, formatter: "perfect", position: "end",
                color: tok("--text-faint"), fontSize: 9 },
              lineStyle: { type: "dashed", color: tok("--text-faint") },
              data: [[{ coord: [0, 0] }, { coord: [100, 100] }]] },
          },
        ],
      });
      _echartsLive.push(chart);
    } else {
      const rows = (cfg.rows || []).slice(0, 12);
      if (rows.length < 2) { delete el.dataset.echarted; continue; }
      el.innerHTML = "";
      el.style.height = `${rows.length * 34 + 52}px`;
      el.style.width = "100%";
      const chart = ec.init(el);
      const tt = (r) => `${r.label}<br>market ${(100 * r.market).toFixed(0)}¢ `
        + `· model ${(100 * r.model).toFixed(0)}% · gap `
        + `${((r.model - r.market) * 100 >= 0 ? "+" : "")}`
        + `${((r.model - r.market) * 100).toFixed(0)}pt`;
      chart.setOption({
        animationDuration: 600,
        grid: { left: 8, right: 44, top: 6, bottom: 24, containLabel: true },
        xAxis: { ...axis, min: 0, max: 100, position: "bottom",
          axisLabel: { ...axis.axisLabel, formatter: "{value}¢" } },
        yAxis: { ...axis, type: "category", inverse: true,
          data: rows.map((r) => r.label.length > 30
            ? r.label.slice(0, 29) + "…" : r.label),
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { ...axis.axisLabel, fontSize: 10 } },
        tooltip: { ...tip, trigger: "item",
          formatter: (p) => p.data.tt || "" },
        series: [
          { // Invisible base up to whichever number is smaller…
            type: "bar", stack: "gap", barWidth: 4,
            itemStyle: { color: "rgba(0,0,0,0)" },
            emphasis: { disabled: true }, tooltip: { show: false },
            data: rows.map((r) => 100 * Math.min(r.market, r.model)),
          },
          { // …then the GAP itself, colored by which side is rich.
            type: "bar", stack: "gap", barWidth: 4,
            data: rows.map((r) => ({
              value: Math.abs(100 * (r.model - r.market)),
              itemStyle: { color: r.model > r.market
                ? tok("--good") : tok("--bad"), opacity: 0.65,
                borderRadius: 2 },
              tt: tt(r),
            })),
          },
          { type: "scatter", symbolSize: 9, z: 3,
            itemStyle: { color: tok("--panel-2"),
              borderColor: tok("--text-mute"), borderWidth: 2 },
            data: rows.map((r, i) => ({ value: [100 * r.market, i],
              tt: tt(r) })) },
          { type: "scatter", symbolSize: 9, z: 4,
            data: rows.map((r, i) => ({
              value: [100 * r.model, i],
              itemStyle: { color: r.model > r.market
                ? tok("--good") : tok("--bad") },
              tt: tt(r),
            })) },
        ],
      });
      _echartsLive.push(chart);
    }
  }
}


/* Subtab rooms are display:none until opened, and a chart mounted into a
   zero-width box stays invisible — so hidden wrappers are SKIPPED above
   and re-tried the moment any subtab (or view) is tapped. Delegated on
   the document once; the mounts are no-ops when nothing is waiting. */
document.addEventListener("click", (e) => {
  if (!e.target.closest) return;
  if (!e.target.closest("[data-subtab], .nav-btn, .sport-btn, .tb-item")) return;
  setTimeout(() => {
    try { mountEChartsPanels(); mountEChartsAnalytics(); } catch (err) {}
  }, 60);
});


/* ---------------- Live ticks: the numbers say when they moved ---------
   Ethan, 2026-08-19, asking for more animation. This is the half of that
   request with information in it.

   The board reloads on a timer, so until now a price could move four
   cents while you were looking straight at it and nothing on the page
   said so. The change was real and the render was silent.

   Any cell can opt in by carrying `data-tick` (a key that survives the
   re-render — the ticker, not the row index) and `data-tick-v` (the raw
   number). After a render, `mountLiveTicks` compares each cell against
   what it said last time and, where it moved, counts the digits from the
   old value to the new one and tints the cell in the direction it went.

   THE FIRST SIGHT OF A CELL IS NOT A CHANGE. A key we have never seen is
   recorded silently — otherwise every cell on the page would flare on
   first paint, which is an entrance animation wearing a data costume,
   and §3.4 has already thrown those out once.

   The count is cosmetic, so it is skipped entirely under reduced motion
   (the cell just shows its new value) and it never touches layout: the
   text is written into a fixed-width tabular cell, and the tint is a
   background that fades. */
const _tickSeen = new Map();
const TICK_MS = 420;          // the count itself
const _tickTimers = new Map();

function _tickParts(text) {
  // "34¢" -> ["", "34", "¢"];  "+7 pts" -> ["+", "7", " pts"]
  const m = String(text).match(/^(.*?)(-?[\d,]*\.?\d+)(.*)$/s);
  return m ? [m[1], m[2], m[3]] : null;
}

function mountLiveTicks(root) {
  const scope = root && root.querySelectorAll ? root : document;
  let cells;
  try { cells = scope.querySelectorAll("[data-tick]"); } catch (e) { return; }
  const quiet = typeof window !== "undefined" && window.matchMedia
    && matchMedia("(prefers-reduced-motion: reduce)").matches;
  for (const el of cells) {
    const key = el.getAttribute("data-tick");
    const now = parseFloat(el.getAttribute("data-tick-v"));
    if (!key || !isFinite(now)) continue;
    const was = _tickSeen.get(key);
    _tickSeen.set(key, now);
    if (was === undefined || was === now) continue;
    // DIRECTION IS NOT ALWAYS MEANING. A price rising is good or bad for
    // the reader and green/red says which. A SCORE only ever rises, and
    // tinting the opponent's score green would claim their run was good
    // news for you. Those cells ask for `neutral` and get "this changed"
    // in the brand colour, with no count — 3 to 4 has no in-between worth
    // animating.
    const mode = el.getAttribute("data-tick-mode") || "";
    const up = now > was;
    el.classList.remove("tick-up", "tick-down", "tick-move");
    if (mode === "neutral") {
      void el.offsetWidth;
      el.classList.add("tick-move");
      clearTimeout(_tickTimers.get(key));
      _tickTimers.set(key, setTimeout(() => {
        el.classList.remove("tick-move");
      }, 1500));
      continue;
    }
    // Reading offsetWidth restarts the fade when a cell moves twice in a
    // row; without it the second change re-adds a class that is already
    // there and no animation replays.
    void el.offsetWidth;
    el.classList.add(up ? "tick-up" : "tick-down");
    clearTimeout(_tickTimers.get(key));
    _tickTimers.set(key, setTimeout(() => {
      el.classList.remove("tick-up", "tick-down");
    }, 1500));
    if (quiet) continue;
    const parts = _tickParts(el.textContent);
    if (!parts) continue;
    const [pre, shown, post] = parts;
    const dp = (shown.split(".")[1] || "").length;
    const t0 = (typeof performance !== "undefined" ? performance.now() : Date.now());
    const step = (t) => {
      const k = Math.min(1, ((t || Date.now()) - t0) / TICK_MS);
      // ease-out: fast off the mark, settles onto the number.
      const v = was + (now - was) * (1 - Math.pow(1 - k, 3));
      el.textContent = pre + v.toFixed(dp) + post;
      if (k < 1) requestAnimationFrame(step);
      else el.textContent = pre + now.toFixed(dp) + post;
    };
    requestAnimationFrame(step);
  }
}

if (typeof window !== "undefined") window.mountLiveTicks = mountLiveTicks;
