# The Zenos render pack — the layout spec Qellys follows

Ethan, 2026-08-18, with four render images (a 24-screen grid plus full
renders of Prediction Markets, Fantasy Calendar, and Player Profile):
"here is complete renders you should be following for the site … i like
the colors and name of our site so we should keep that but i really
love the graphics and layouts of these renders so i wanna follow that
pixel for pixel."

**The standing translation rules** (settled in that conversation):

* **Layouts and graphics: copy pixel-for-pixel.** Structure, card
  grids, information order, chart placements.
* **Colors and name: OURS.** Qellys violet/gold token system, QELLYS
  BOOK wordmark. The renders' blue accent maps to `--brand`; their
  green/red map to `--good`/`--bad` (already aligned).
* **The one thing that never crosses: order tickets.** The renders'
  "Trade Position / Trade Yes 62¢" block places wagers. Qellys takes
  no wagers (test-pinned bans on bet slips / Place Bet / To Win).
  Replace with a venue link-out plus "This panel is a read, not an
  order ticket."
* **No invented numbers.** Where a render shows a stat we cannot
  source (DFS salaries, ownership %, boom %, 7-day hit rate we do not
  measure), the element is omitted or replaced with a sourced
  equivalent — same rule as the fantasy render pass of 2026-08-18.
* Marketing bullets become MEASURED bullets (e.g. the market detail's
  "ZenOS Analysis" checklist ships as the desk's actual gate
  conditions, pass/fail with numbers).

The images themselves live in the chat of 2026-08-18 (a cloud session
cannot persist them); this file is the durable description.

## Status

| Screen | Status |
| --- | --- |
| 10/PM detail — Prediction Markets, table + detail panel | **SHIPPED 2026-08-18** |
| 6/7 — Fantasy Calendar three-column | **SHIPPED 2026-08-19** |
| 8/9 — Player Profile (fantasy) | **SHIPPED 2026-08-19** (built 08-18; close pass added HT/WT/College + trend) |
| 3 — Dashboard | **SHIPPED 2026-08-19** (quick tools, sports donut, recent results added to the existing panels) |
| 12 — Bet Tracker | mostly exists (My Bets); render adds summary strip |
| 13 — Account & Settings | exists; render adds stats card |
| 14 — Alerts Center | **SHIPPED 2026-08-19** (filter chips + condition rows; the render's toggles never cross) |
| 21 — Pricing | billing exists (Paddle); render’s 3-plan cards pending |
| 1/2 — Login / Sign up | **SHIPPED 2026-08-19** (wordmark + tagline hero over the card) |
| 23/24 — 404 / Maintenance | **SHIPPED 2026-08-19** (web/404.html, web/maintenance.html) |
| 20/22 — Mobile app promo | not applicable yet (no store apps) |

## Screen specs

### Prediction Markets (SHIPPED — the reference implementation)
Header + sub. Category chip row (Top opportunities / All markets / one
chip per sport present). Four stat tiles: markets tracked, priced by
our model, average gap, 24h volume. Two-column `pm-layout`: left the
market table (venue chip · title+sub · YES¢ green · NO¢ red · model % ·
edge ± · $vol · VIEW button · price meter), selected row gets a brand
left-bar; right a sticky `pm-detail` panel: venue chip, title
(link-out when Polymarket), big YES/NO cents, "QELLYS EDGE" figure,
one-line model read, Market summary rows (venue/type/resolves/matched
game/volume/basis), **The desk's gate** checklist (edge vs 6-pt bar,
two-sided book, $250 volume floor, 6¢ spread cap — mirrored in
`PM_GATE`, keep in sync with engine/sources/kalshi.py), verdict line,
link-out button, no-wagers note. Phone: detail stacks above the table.

### Fantasy Calendar (render 6/7 + full render) — SHIPPED
As-built notes: `.ffcal-layout` three-column grid (calendar+summary /
ranked cards / sticky `ffcal-panel`); cards are compact pickers
(`data-calpick`), the why-checklist moved into the panel; matchup
tiles are the market's implied-points split (the honest version of the
render's offense/defense tiles); per-sport chips became per-position
chips (this calendar is NFL only). Phone: calendar → read panel →
list. Kickoff venue and Watchlist omitted (no source / no feature).
Three columns. **Left:** "Fantasy Calendar — the best fantasy plays
for every day"; legend (Elite/Top/Good day); month grid card with
dot/star day markers, Today button, month nav; below it a selected-day
summary card: date + ELITE DAY chip, one-line slate read, per-sport
count chips, total plays tile. **Middle:** "Top Fantasy Plays" +
date chip; sport filter chips; ranked cards 1–5: face, name,
pos · team vs opp, FPPG, big green "Projected — N points" block;
"View Full Player Pool" button. **Right:** selected player panel:
face, name, pos · team, opp + kickoff + venue, big Projected tile
(+FPPG), tabs (Overview/Game log/Matchup/News/Trends), "Why he's a
top play" checklist (sourced reasons — the ffcal why-list), Matchup
Breakdown (two team tiles: offense pts/gm + rank vs defense allowed +
rank — teamshape/def-rank data), Key stats row, Projected range strip
(floor/median/ceiling — exists as ffp-range), Add to Watchlist.
Omit: salary, ownership %, boom % (unsourceable — decided 2026-08-18).

### Player Profile (render 8/9 + full render) — SHIPPED
As-built notes: most of this page shipped in the fantasy render pass
of 2026-08-18 (ffp-* overlay: hero, season tiles with league ranks,
projection tile with tier dots, FP chart, weekly range, matchup
strength, utilization ring, game log, upcoming game, takeaways). The
2026-08-19 close pass added the hero's HT/WT/College chips (kept from
the roster feed in engine/rosters.py — missing bio drops the chip) and
the projection tile's 4-week trend line (his own last four PPR weeks).
The render's tab strip is deliberately one scrolling overview grid —
every tab we can source is already a panel; empty tabs would be
chrome. Advanced-metrics list stays limited to measured metrics (xFP,
snap share) inside Utilization.
Hero: photo left; name + pos · team · number; HT/WT · AGE · EXP ·
COLLEGE strip; Add to Watchlist. Right of hero: season-stats card
(6-8 stat tiles each with a league-rank sub) and a projection tile
(big green FPPG projection, position rank, confidence dots, 4-week
trend line). Tab strip (Overview/Game log/Matchups/Props/News/
Trends). Overview grid: Fantasy Points last-10 area chart (gloss);
Matchup Strength next-4 (opp + def-rank + bar + projected FP);
Player Utilization (donut + attempts/red-zone/snap rows); Advanced
Metrics ranked list (only metrics we measure — xFP/red-zone from pbp);
Game Log table; Upcoming Game card (logos, kickoff, venue, spread /
total / implied); Key Takeaways checklist footer (sourced one-liners).

### Dashboard deltas (render 3) — SHIPPED
As-built: Quick Tools row above the performance grid (`qt-row`, four
doors: Fantasy room, Props scanner, Bet tracker, Bankroll — all
existing rooms, no new features); Sports Breakdown donut as a third
perf card, fed by record.json's `by_sport` blocks (whole book always,
labelled, needs >= 2 sports with settled bets); Recent Results list in
the W/L card, the curve's own last five graded days with each day's
record and units (hidden when the stored curve predates per-day
records). The render's "Fantasy Optimizer" maps to the fantasy room —
we do not build DFS lineups.

### Small screens
* **Pricing (21):** three plan cards (Free / Premium / Elite), center
  card raised + "Most Popular" band, feature checklists, CTA per card.
  Wire to the real Paddle plans only — never invent prices.
* **404 (23) / Maintenance (24): SHIPPED.** `web/404.html` and
  `web/maintenance.html` — giant brand-ramp numeral / clock mark, one
  honest sentence, brand CTA, quick links. They skip `.shell` (no
  sidebar to reserve). server.py serves 404.html for page-shaped
  misses only; an asset miss keeps the bare body, so a missing script
  stays a console error instead of becoming a blank screen. The
  maintenance page quotes no ETA — it says what is true (nothing
  settled is touched) and when to go look at the machine.
* **Login/Sign up (1/2): SHIPPED.** `.acct-hero` — mark, wordmark, and
  our own tagline **"Priced by a model. Graded in public."** (theirs
  was "DATA. EDGE. PROFITS."; a promise of profit is the one thing this
  site will not print) over the existing sign-in card. The old
  duplicate `<h2>` folded into the hero's sub-line so the screen names
  itself once. Card, fields, log-in/sign-up order and the honesty copy
  underneath are unchanged.
* **Alerts (14): SHIPPED.** Filter chips with counts (All / Line moves
  / Injuries / The desk) over rows carrying an icon chip, the alert,
  and the CONDITION that fired it. The render's per-row toggle and
  "Create New Alert" never cross: this page is a digest of three feeds
  we already hold, not a subscription service, and a switch that turns
  nothing on is a lie you can click (pinned in test_stub_pages).
* **Bet Tracker (12):** summary strip (bets, win rate, profit, ROI) —
  exists in My Bets tiles; add the render's table variant with
  date/pick/type/odds/stake/result columns (mb table exists; restyle).
