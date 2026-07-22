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
function team(abbr) { return (typeof TEAMS !== "undefined" && TEAMS[abbr]) || DEFAULT_TEAM; }

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
function playerAvatar(name, abbr, opts = {}) {
  const size = opts.size || 56;
  const t = team(abbr);
  const uid = "a" + Math.random().toString(36).slice(2, 8);
  const ini = initials(name);
  const stripe = t.secondary;
  const mask = "#c9d2e8";
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

/* ---------------- Animated wind gauge ------------------------------------ */
const COMPASS = { N:0, NNE:22.5, NE:45, ENE:67.5, E:90, ESE:112.5, SE:135, SSE:157.5,
  S:180, SSW:202.5, SW:225, WSW:247.5, W:270, WNW:292.5, NW:315, NNW:337.5 };

function windGauge(weather, opts = {}) {
  const size = opts.size || 92;
  if (weather.dome) {
    return `
    <div class="wind dome" title="Climate-controlled dome">
      <svg width="${size}" height="${size}" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r="40" fill="#141b33" stroke="#2b365a" stroke-width="2"/>
        <path d="M22 52 a24 20 0 0 1 48 0 z" fill="#1d2647" stroke="#3a4a7a" stroke-width="1.5"/>
        <text x="46" y="44" text-anchor="middle" font-size="15">🏟️</text>
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
      <text x="46" y="44" text-anchor="middle" font-size="13" font-weight="800" fill="#eaeefb"
            font-family="system-ui">${Math.round(mph)}</text>
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
    ${yardLines}
    <!-- midfield badge -->
    <circle cx="120" cy="80" r="13" fill="#0c1020" opacity="0.55"/>
    <text x="120" y="84" text-anchor="middle" font-size="10" font-weight="800"
          fill="#ffffff" font-family="system-ui">${escapeAttr(game.home)}</text>
    ${roofOverlay}
  </svg>`;
}

/* ---------------- Sparkline (game-log trend) ----------------------------- */
function sparkline(values, opts = {}) {
  // values come newest-first from the API; chart oldest -> newest.
  const data = [...values].reverse();
  const w = opts.w || 240, h = opts.h || 64, pad = 8;
  const line = opts.line;                    // optional threshold (the prop line)
  const stroke = opts.stroke || "var(--brand)";
  const uid = "sp" + Math.random().toString(36).slice(2, 7);
  if (data.length < 2) return `<svg width="${w}" height="${h}"></svg>`;

  const lo = Math.min(...data, line ?? Infinity);
  const hi = Math.max(...data, line ?? -Infinity);
  const span = (hi - lo) || 1;
  const x = (i) => pad + (i / (data.length - 1)) * (w - pad * 2);
  const y = (v) => h - pad - ((v - lo) / span) * (h - pad * 2);

  const pts = data.map((v, i) => `${x(i)},${y(v)}`);
  const linePath = "M" + pts.join(" L");
  const areaPath = `M${x(0)},${h - pad} L` + pts.join(" L") + ` L${x(data.length - 1)},${h - pad} Z`;
  const dots = data.map((v, i) => {
    const above = line == null ? true : v > line;
    const c = line == null ? stroke : (above ? "var(--good)" : "var(--bad)");
    return `<circle cx="${x(i)}" cy="${y(v)}" r="${i === data.length - 1 ? 3.2 : 2.1}" fill="${c}"/>`;
  }).join("");
  const thresh = line == null ? "" :
    `<line x1="${pad}" y1="${y(line)}" x2="${w - pad}" y2="${y(line)}"
       stroke="var(--warn)" stroke-width="1" stroke-dasharray="4 4" opacity="0.8"/>`;

  return `
  <svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="${uid}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${stroke}" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#${uid}a)"/>
    ${thresh}
    <path class="spark-line" d="${linePath}" fill="none" stroke="${stroke}"
          stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots}
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
