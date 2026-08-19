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
| 6/7 — Fantasy Calendar three-column | next |
| 8/9 — Player Profile (fantasy) | next |
| 3 — Dashboard | partial (top picks, stadiums, perf panel exist; quick-tools row + sports-breakdown donut pending) |
| 12 — Bet Tracker | mostly exists (My Bets); render adds summary strip |
| 13 — Account & Settings | exists; render adds stats card |
| 14 — Alerts Center | page exists; render adds per-alert toggles list |
| 21 — Pricing | billing exists (Paddle); render’s 3-plan cards pending |
| 1/2 — Login / Sign up | exists (accounts); render styling pending |
| 23/24 — 404 / Maintenance | pending, small |
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

### Fantasy Calendar (render 6/7 + full render)
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

### Player Profile (render 8/9 + full render)
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

### Dashboard deltas (render 3)
Greeting row exists. Add: Quick Tools chip row (Fantasy Optimizer =
lineup builder, Props Scanner = scanner, Bet Tracker = My Bets);
Sports Breakdown donut beside the perf panel (pick counts per sport —
sourced from the board); Recent Results mini-list (last graded days
with +/- units — record.json curve tail).

### Small screens
* **Pricing (21):** three plan cards (Free / Premium / Elite), center
  card raised + "Most Popular" band, feature checklists, CTA per card.
  Wire to the real Paddle plans only — never invent prices.
* **404 (23):** giant numeral, "Go Back Home" brand button, four quick
  links. **Maintenance (24):** wrench mark, "We'll Be Right Back!",
  Check Status button.
* **Login/Sign up (1/2):** centered card on dark stadium wash,
  wordmark + "DATA. EDGE. PROFITS."-style tagline (write our own
  honest one), fields, brand CTA, switch link.
* **Alerts (14):** list rows: icon chip, alert title + condition sub,
  toggle right; filter chips; "Create New Alert" button.
* **Bet Tracker (12):** summary strip (bets, win rate, profit, ROI) —
  exists in My Bets tiles; add the render's table variant with
  date/pick/type/odds/stake/result columns (mb table exists; restyle).
