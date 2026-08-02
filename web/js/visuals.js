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
function playerAvatar(name, abbr, opts = {}) {
  const size = opts.size || 56;
  if (opts.headshot) {
    const inner = playerAvatar(name, abbr, { ...opts, headshot: null });
    return `<span class="avatar-stack" style="width:${size}px;height:${size}px">${inner}
      <img class="avatar-photo" src="${escapeAttr(opts.headshot)}" alt="" loading="lazy"
           onerror="this.remove()"/></span>`;
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
function teamMark(abbr, size = 20, src = null) {
  const t = team(abbr, src);
  const uid = "tm" + Math.random().toString(36).slice(2, 7);
  return `
  <svg class="team-mark" width="${size}" height="${size}" viewBox="0 0 24 24" role="img"
       aria-label="${escapeAttr(abbr)}">
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
  </svg>`;
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
  <svg class="stadium" width="${w}" height="${h}" viewBox="0 0 240 150" preserveAspectRatio="xMidYMid meet">
    <defs>
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
    ${Array.from({ length: 5 }, (_, i) =>
      `<path d="M120 132 L${44 + i * 16} ${56 - i * 2} A116 92 0 0 1 ${72 + i * 20} 34 Z"
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
    <!-- bases + mound + plate -->
    <g fill="#ffffff">
      <rect x="93" y="97" width="6" height="6" transform="rotate(45 96 100)"/>
      <rect x="117" y="73" width="6" height="6" transform="rotate(45 120 76)"/>
      <rect x="141" y="97" width="6" height="6" transform="rotate(45 144 100)"/>
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

/* ---------------- Mini base-state diamond (MLB live) --------------------- */
function baseDiamond(bases, outs, opts = {}) {
  const size = opts.size || 46;
  const occ = new Set(bases || []);
  const on = "#ffd24a", off = "#2c3557", edge = "#0c1020";
  // rotated-square base at (cx,cy); occupied bases glow gold.
  const base = (cx, cy, n) => {
    const lit = occ.has(n);
    return `<rect x="${cx - 5}" y="${cy - 5}" width="10" height="10" rx="1.5"
      transform="rotate(45 ${cx} ${cy})" fill="${lit ? on : off}"
      stroke="${lit ? shade(on, -30) : edge}" stroke-width="1.2"
      ${lit ? 'filter="url(#baseglow)"' : ""}/>`;
  };
  const outDot = (cx, filled) =>
    `<circle cx="${cx}" cy="43" r="2.6" fill="${filled ? "#fb2c46" : off}"/>`;
  const nOuts = outs == null ? 0 : outs;
  return `
  <svg class="basediamond" width="${size}" height="${size}" viewBox="0 0 48 50" aria-label="base state">
    <defs><filter id="baseglow" x="-50%" y="-50%" width="200%" height="200%">
      <feDropShadow dx="0" dy="0" stdDeviation="1.6" flood-color="${on}" flood-opacity="0.9"/>
    </filter></defs>
    ${base(24, 12, 2)}   <!-- 2B top -->
    ${base(36, 24, 1)}   <!-- 1B right -->
    ${base(12, 24, 3)}   <!-- 3B left -->
    ${outDot(18, nOuts >= 1)}
    ${outDot(30, nOuts >= 2)}
  </svg>`;
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
