# QA audit — qa/full-audit

Running log for the full audit requested 2026-09-01 (QA_AUDIT_PROMPT.md).
Everything here was run, not assumed; where something could not be run,
it says so and why.

## Phase 0 — Map

**Stack.** Python 3.11, standard library only for the site, engine and
every pipeline (the one third-party import, Pillow, is used only by
`tools/venues_ingest.py`, `tools/qbmark.py` and two tests). No package
manifest, no build step. Front end is a hand-written single-page app:
`web/index.html` (1,224 lines), `web/js/app.js` (~30k lines),
`web/js/visuals.js`, `web/css/styles.css` (9k lines), vendor
`apexcharts` + `echarts` under `web/vendor/`. `node_modules/` at the root
holds only Playwright, used by `rendercheck.py` (the site's own layout
check) — not by the site.

**Entry points.** `server.py` (HTTP server: static files + `/api/*`),
`launch.py` (the production process: runs the server AND the background
refresh loop; `--boards`, `--injuries`, `--check` etc. are its diagnostic
flags). Build scripts, one per board: `generate.py` (sample NFL slate),
`nfl_build.py`, `mlb_build.py`, `cfb_build.py`, `nba_build.py`
(`--league nba|wnba`), `ufc_build.py`, `injuries_build.py`,
`news_build.py`, `standings_build.py`, `rosters_build.py`, `pm_build.py`
(prediction markets), `memes_build.py`, `fantasy_build.py`,
`futures_build.py`, `live_build.py` (fast MLB scoreboard),
`ufc_live_build.py`. Daily/weekly chores: `engine/maintenance.py`
(called from the loop). Fitters (`formfit.py`, `playerfit.py`,
`calibrate.py`, `journalfit.py`, …) are run by maintenance on a weekly
schedule.

**Commands.** Tests: `python3 run_tests.py` (stdlib runner, 8,373 tests
in 502 files at audit start, all green). Health: `python3 doctor.py`
(`--code-only` for CI). Layout: `python3 rendercheck.py`. There was no
linter or type checker; `pyflakes` was installed for this audit
(tooling only, see Phase 1).

**Routes/pages.** Hash-routed views in `index.html` (39): recommended,
bankroll, live, tonight, game, prop, paywall, checkout, discord, signup,
record, lab, edge, intel, account, mybets, weather, alerts, messages,
streak, injuries, memes, ufc, fantasy, about, methodology, status, why,
scanner, likely, longshots, futures, rosters, standings, trending,
players. Entity URLs (`/player/…`, `/game/…`, `/pick/…`) are served as
share shells by `server.py` and re-enter the SPA.

**API prefixes** (`server.py`, 25): `/api/recommendations`,
`/api/{mlb,nba,wnba,cfb}/recommendations`, `/api/board/`,
`/api/players/{search,logs,versus,fantasy}`, `/api/account/`,
`/api/profile/`, `/api/social/`, `/api/streak/`, `/api/alerts/`,
`/api/billing/` (+ `/api/billing/webhook`), `/api/tailfade/`,
`/api/sleeper/`, `/api/yahoo/`, `/api/draftadvice`, `/api/leaguedesk`,
`/api/record/receipts.csv`, `/unsubscribe`, and a catch-all `/api/`.

**External data.** ESPN site API (injuries, live scores, NBA/WNBA box
scores, MMA, per-league RSS for news), MLB Stats API + Baseball Savant,
nflverse release assets (NFL logs, injuries, participation, pbp),
cfbfastr / CollegeFootballData (`CFBD_API_KEY`), The Odds API
(`ODDS_API_KEY`, budgeted), Polymarket + Kalshi (keyless), DexScreener /
GeckoTerminal / Solana RPC (meme board), Sleeper + Yahoo fantasy, Open-
Meteo weather, Stripe (billing), Anthropic API (digest prose, capped by
`QELLYS_LLM_CAP_USD`).

**Env vars** (from `os.environ` reads): `ODDS_API_KEY`, `CFBD_API_KEY`,
`ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_{ID,MONTHLY,SIXMONTH,YEARLY}`, `PADDLE_SANDBOX`,
`QB_ENV_FILE`, `QB_BACKUP_DIR`, `QB_MAX_INFLIGHT`, `QB_MLB_WORKERS`,
`QB_ODDS_WINDOWS`, `QB_PROMOS`, `QELLYS_LLM_CAP_USD`, `ENV_{HOST,USER,PASS}`.
Secrets live in `secrets.local` (gitignored with every backup spelling)
or `/etc/qellys/env` on the box; `engine/secrets.py` reads them.

**Deploy.** DigitalOcean droplet (`/srv/qellys`, reports 1 vCPU / 2 GB
at audit time), `deploy/qellys.service` runs `launch.py --bind
127.0.0.1 8000` behind Caddy (`deploy/Caddyfile`, TLS + gzip/zstd),
`qellys-update.timer` → `deploy/autoupdate.py` pulls the deploy branch
every 5 minutes and restarts. Boards are files under `web/data/`
(public, paywall-redacted copies) and `data/built/` (full copies).

## Phase 1 — Make it run, make the tools complain

(filled in as each step runs; see below)

### 1.1 Install / toolchain
- No dependencies to install for the site (stdlib). `node_modules/`
  contains only Playwright (2 packages) for `rendercheck.py`; no
  `package.json` at the root, so there is no lockfile to drift.
- Pillow is imported by two `tools/` scripts and two tests; it is present
  on this box. Not a site dependency.
- Installed `pyflakes 3.4.0` for this audit (no linter existed).

### 1.2 Syntax / lint / typecheck
- `python3 -m compileall` over the tree: clean.
- `node --check` on `app.js`, `visuals.js`, `teams*.js`, `register-sw.js`,
  `sw.js`: clean.
- `pyflakes` over all 500+ tracked `.py` files: **324 findings** —
  212 unused imports, 75 f-strings with no placeholders, 25 unused local
  variables, 10 redefinitions of an unused name, **2 undefined names**
  (the only category that can be a runtime error; triaged in Phase 2).
  Unused imports/variables are logged, not deleted (rule 1). Full list:
  kept in the audit scratch; the two undefined names are in the defect
  table.
- No type checker exists and the codebase carries no type-checking
  configuration; not added (the brief allows minimal tooling, but a
  first `mypy` pass on ~140k lines of untyped stdlib Python would be a
  project of its own, not a defect list — flagged for Ethan).

### 1.3 Existing checks
- `python3 run_tests.py`: 8,373 tests across 502 files, all green (253s).
- `python3 doctor.py --code-only`: "All clear", exit 0.

### 1.4 Pipelines, end to end (this sandbox's egress proxy blocks
ESPN, MLB Stats API and Polymarket; nflverse (GitHub) and keyless
sources that happen to be reachable ran for real)
| build | result | output |
|---|---|---|
| `generate.py` (sample slate) | exit 0, 6s | 162,690 B, recommendations present |
| `nfl_build.py 2026 1` (full) | exit 2, 4s | none — no nflverse weekly stats before Week 1 is played (documented state; the launcher's fallback handles it) |
| `nfl_build.py 2026 1 --games-only` | exit 0, 3s | 82,154 B, 16 games with lines, no props (by design) |
| `mlb_build.py 2026-09-01` | exit 2 | none — MLB Stats API unreachable from this sandbox (**could not verify here**; it builds on the droplet, 235s per cycle) |
| `cfb_build.py` | exit 0 | 3,706 B — empty board with its reason on it (no CFBD key here) |
| `nba_build.py --league {nba,wnba}` | exit 0 | small "unreachable" boards (ESPN blocked here) |
| `injuries_build.py` | exit 0 | 911 B (ESPN blocked here → empty per-league sections, page explains) |
| `news_build.py` | exit 0 | 174 B, 0 headlines (ESPN RSS blocked here) |
| `pm_build.py` | exit 2 | none — Polymarket unreachable here (**could not verify here**) |
| `memes_build.py` | exit 0 | 672 B |
| `fantasy_build.py` | exit 0, 5s | 350,414 B, 60 usage rows |
| `ufc_build.py` | exit 0 | 253 B, `no_card` |
| `live_build.py` | exit 0 | 496 B, 0 games |
| `standings_build.py`, `rosters_build.py` | exit 0 | write to `web/data/` directly |

Every build that ran wrote valid JSON the page's loaders accept (checked
by the page walk in Phase 2). Every feed-dependent build degraded the
way its own header says it should — empty board with a reason, or a
non-zero exit that the launcher treats as "keep the last board".

## Phase 2 — Systematic review

### 2.1 Numerical correctness (hand-verified; tests kept in `tests/test_qa_numerics.py`)
Every expected value was worked by hand from the formula's definition,
then compared with a margin. All 16 pass.

| check | result |
|---|---|
| American → implied prob (−110, +150, ±100, +400, −200, −1000) | correct; −100 and +100 both 0.5 |
| American → decimal, and `engine.parlays`' own copy | agree for every price tried |
| decimal → American round trip | correct for every price except the even-money seam: **−100 round-trips to +100** (decimal 2.0 cannot remember the spelling; identical money) — P3 display seam, documented in the test, not changed |
| two-way devig (−110/−110 → .5/.5; −120/+100 → .5217/.4783, sums to 1) | correct |
| one-sided devig uses the documented 1.06 hold, sums to 1 | correct |
| fabricated pair (+850/−110) treated as one-sided | correct (this was the 2026-09-01 "Under 0.5 HR" root cause; fixed earlier that day, verified here) |
| EV sign: +0.05 at p=.55/−110, −0.0455 at a fair coin, 0 at break-even, linear in stake | correct |
| net edge = model − break-even (not − fair) | correct |
| Kelly: 0.055 at p=.55/−110; **never negative** (max(0,·)); 0 at break-even (float noise ≤1e-9); 0 when the price beats the edge | correct |
| stake units: 0 at no edge, **capped at MAX_PRICED_U (1.25u)** across a p×odds sweep; a certainty at +800 still ≤ cap | correct |
| line CLV: over wants the line up, under wants it down; process grade good/flat/bad | correct |
| price CLV: positive when the close is shorter than we took; None without a close or price | correct |
| 3-leg parlay at −110×3 → +596; −110×+150 → +377 | correct |
| leg cap: `MAX_LEGS == 3`, ticket sizes enumerated only up to 3 | correct in the engine (see Ask Ethan on the user slip) |
| grade thresholds on the boundary: (8.0, .020) → Strong Play; a hair under either → next tier; (6.5, .010) → Play; below → Pass | correct, inclusive as the table reads |
| favourite surcharge: 0.021 at −200 (0.18 × (2/3 − .55)); 0 below the 55% floor; Strong at −200 needs .041 | correct |
| rounding/display: `pct()` → 1 decimal + %, `american()` uses a true minus, `toFixed` everywhere it prints | no mixed units seen; the 144-render walk found no `NaN`/`undefined`/`Infinity` in any view |

Latent (not a defect today): `american_to_prob(0)` returns 1.0 and
`expected_value(p, 0)` returns −(1−p). Every live caller guards a
missing price with `if odds` before calling, so no path reaches it;
noted so nobody removes a guard.

### 2.2 Data layer
- **P2 — fixed (0ec0bb4):** `launch._slate_date()` rolled the baseball
  day at 05:00 on the process's local clock. The droplet runs UTC, so
  the roll happened at 1 AM Eastern — during a west-coast game's last
  innings, the exact case the 5 AM offset exists for. Now computed in
  America/New_York like `engine/streak.py` and `engine/oddsbudget.py`.
- NFL week selection (`_current_nfl_week`) uses the UTC date and picks
  the nearest game by absolute day distance; checked by hand at the
  Monday-night seam (00:15 UTC Tuesday: Monday's game is 1 day away,
  Thursday's is 2) — stays on the current week. Not a defect.
- Missing/empty boards: every view rendered its own empty state with
  no JS error when `nba.json`, `wnba.json`, `ufc.json`, `news.json`,
  `memerecord.json`, `heartbeat.json` were absent (they are absent in
  this sandbox). 404s for those are logged by the browser as console
  errors; on the droplet the files exist. Not defects.
- Stale-as-current: the service worker is network-first with the cache
  as fallback only; boards fetch with `no-cache`/ETag revalidation; the
  page computes its Stale badge from the loop's measured cycle and
  shouts past 12h. Verified in code and in the walk.
- Duplicate records: the bets journal is UNIQUE on
  (sport, date, player, market, category) with INSERT OR IGNORE
  (verified in `engine/parlays.py`'s journaling note and `engine/ledger`).
- Secrets: none committed. `secrets.local*` is gitignored in every
  backup spelling; the only `sk_test_…` strings are test fixtures.
  Nothing secret reaches the client bundle (checked `app.js` for key
  patterns).

### 2.3 Every page and route
144 renders (36 views × 4 widths: 375, 768, 1024, 1440) in Chromium
against a local server: **0 JS errors, 0 horizontal overflow, 0
duplicate ids, 0 broken images, 0 template/escape leaks, every view
visible with content.** Entity URLs (`/player/…`, `/game/…`) are served
by `server.py._entity_page` through `engine/routes.document`, which
escapes `</` in the injected payload; a real file always wins over a
route; unknown paths fall to the real 404.
- **P3 — fixed (9927321):** anonymous visitors logged a 401 on every
  card render from `/api/tailfade/me`; the call is now skipped when the
  account probe has said signed-out (unknown state still asks).
- External asset hosts are only `a.espncdn.com` (headshots) and link
  targets; both blocked in this sandbox (ERR_TUNNEL), fine on the site.

### 2.4 Model instruction set pages
The brief assumes per-sport instruction-set pages. The site has none:
`docs/{NFL,MLB,CFB,UFC,PARLAY,MEMECOIN}_MODEL.md` are engineering
documents referenced from code comments, and the public Methodology and
About pages are prose generated by `renderMethodology()` /
`renderAbout()` from the live record. Both render fully at every width
with no raw markup. There is nothing to diff against the docs; if the
docs are meant to be published, that is a feature (Ask Ethan).

### 2.5 Forms and inputs
Bankroll and unit-% inputs were driven with "", whitespace, −500, 0,
"abc", 1e12, 99999999999, `<b>x</b>`, "12.345.6": no `NaN`, `undefined`,
`Infinity` or raw HTML anywhere in the view. Player search with a
script tag, an SQL-injection string, 300 chars, whitespace, emoji,
`%00` and an apostrophe: nothing rendered raw, the server caps `q` at
40 chars and parameterises every query. Sign-up shows Create account /
Log in; server caps password at 200 chars, email at 254, bodies at
1 MB, and throttles wrong passwords in memory.
- **P3 — fixed (bdbd7ef):** four inputs (bankroll, unit-pct,
  roster-search, player-search) had no accessible name. `aria-label`
  added; `tests/test_qa_a11y.py` pins every visible control.

### 2.6 UI and design
No overflow, cut-off, or overlap flagged at any of the four widths (the
walk measures `scrollWidth`). Fonts: every face declares a fallback
stack (`rendercheck.py` and `tests/test_typography.py` already guard
this). Contrast: not re-measured here; `contrast.py` exists for it and
was not run (no changes to the palette in scope). Focus states:
`:focus-visible` rule present. Touch targets: 5 links/buttons under
24 px on Recommended and 1 each on Record/Rosters/Standings (icon
links) — P3, not changed (design decision).

### 2.7 Async and state
`renderPlayers` carries a sequence token and checks it after every
await (3 checks, pinned by `tests/test_routes.py`); board polls carry
ETags; `window` has `error` and `unhandledrejection` handlers. Nine
`setInterval`s, seven `clearInterval`s: the two unpaired are page-
lifetime pollers (mark-seen, account sync) in a single-page app that
never unmounts them — intended. Slow-network behaviour: not
throttle-tested here (no network shaping in the sandbox).

### 2.8 Security basics
- SQL: every user value is bound (`?`); the f-strings in `execute(f"…")`
  interpolate only internal table/column identifiers (verified each).
- No `shell=True`, `eval` or `exec` in site code.
- Headers: CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, HSTS on https; session cookie HttpOnly + SameSite=Lax + Secure
  over https. Wrong-password throttle in `engine/accounts.py`. Bodies
  capped at `MAX_PROFILE_BYTES` (1 MB) on every POST path read.
- Dependency audit: no third-party site dependencies (stdlib); nothing
  for `pip-audit`/`npm audit` to scan. Pillow (tools only) not audited.
- CORS: no `Access-Control-Allow-Origin` is set (same-origin only);
  `Expose-Headers` only. Correct for this site.

### 2.9 Performance
`app.js` 1,536 KB raw / 499 KB gzip; `styles.css` 490 KB / 136 KB;
`apexcharts` 574 KB / 153 KB loaded eagerly; `echarts` (1 MB / 335 KB)
is injected lazily only by panels that need it (verified in
`visuals.js`). Caddy serves gzip/zstd. No bundler, no minification of
first-party JS — a P3 improvement candidate, not a defect. The 8 MB MLB
board is the heaviest fetch; the Live tab and Record page re-fetches
were switched to ETag revalidation earlier today. Lighthouse: **not
run** (no network for the CLI in this sandbox).

### 2.10 Accessibility and SEO
One `<h1>`; per-view titles are set by the router; one `<title>` and a
meta description; no duplicate ids in the static shell or any rendered
view. Keyboard: clickable cards (`.lb-card`, profile cards, stadium
SVGs) are `div`s with `cursor:pointer` and no `tabindex`/`role` — not
reachable by keyboard (697 such elements on Recommended, most of them
SVG parts). P3, not changed: giving hundreds of cards focus order is a
design decision (Ask Ethan).

### 2.11 Dead and broken code (flagged, nothing deleted)
- pyflakes: 212 unused imports, 25 unused locals, 10 shadowed names,
  75 placeholder-less f-strings. Two "undefined name" hits are guarded
  dead branches in tests (`tests/test_gate.py:484`,
  `tests/test_rosters.py:258`) — false positives, harmless.
- TODO/FIXME/HACK/XXX: 42 hits, 23 of them in `engine/todo.py` (the
  site's own to-do feature) and the rest in test prose. No real code-debt
  markers.
- `web/vendor/echarts.min.js` looked unused by grep of `index.html`; it
  is lazy-loaded from `visuals.js`. Not dead.

## Phase 3 — Fix (one defect per commit)
| commit | fix |
|---|---|
| 0ec0bb4 | fix(launch): MLB slate day rolled at 5 AM UTC (1 AM ET), not 5 AM Eastern |
| bdbd7ef | fix(a11y): four inputs had no accessible name |
| 9927321 | fix(tailfade): stop requesting /api/tailfade/me for a known signed-out visitor |
| a6ba916 | test(qa): hand-computed checks for odds, devig, EV, Kelly, CLV, parlays, grades |

After each fix the touched test file was rerun; the full suite ran once
on the finished branch from a fresh clone (Phase 4). No fix broke
anything; nothing was reverted.

## Phase 4 — Verify from zero
Fresh `git clone` of `qa/full-audit` (a6ba916) into a new directory:
`compileall` clean; `python3 run_tests.py` → **8,390 tests across 504
files, all green (280s)**; `server.py` started on a new port; every view
walked at 375 and 1440: **72 renders, 0 JS errors, 0 overflow, 0
duplicate ids, 0 broken images, 0 template leaks.** The only flags were
404s for boards a data-less clone does not have and blocked external
hosts — the same expected noise as Phase 2.

## Phase 5 — Report

### Defects by severity
- **P0:** 0
- **P1:** 0
- **P2:** 1 — slate-day rollover in the wrong timezone (**fixed**, 0ec0bb4)
- **P3:** 4 —
  unlabeled inputs (**fixed**, bdbd7ef);
  signed-out 401 console noise (**fixed**, 9927321);
  −100 → +100 even-money display seam (**documented in test, not changed** — identical money; changing the spelling is a product choice);
  cards not keyboard-reachable / a handful of sub-24px icon targets (**needs decision**).

### Ask Ethan
1. **Parlay cap on the user slip.** The brief says a hard cap of 3 with
   conflict detection "at every entry point". The ENGINE honours both
   (`MAX_LEGS = 3`, clash taxonomy). The user-built slip allows **8**
   legs (`SLIP_MAX = 8`, `social.MAX_PARLAY_LEGS = 8`) and prices
   correlation as if independent — and its own on-screen note says so
   ("correlation is not priced here"). Both sides of one prop cannot be
   added (the leg key ignores side, so the second tap toggles the first
   off). Is the 8-leg, uncorrelated user slip the intended product, or
   should it inherit the engine's cap and clash rules?
2. **Even-money spelling.** Should a −100 leg display as −100 rather
   than +100 after a decimal round trip? Same payout either way.
3. **Keyboard access to cards.** Making live/game/profile cards
   focusable changes tab order across hundreds of elements; it is a
   design change, not a patch.
4. **Model instruction set pages.** The docs exist only in `docs/`; no
   page publishes them. If they should be on the site, that is a
   feature.
5. **Type checking.** None exists; adding mypy to ~140k lines of
   untyped Python is a project. Worth scheduling, not a defect.

### Could not test, and why
- **Live feed builds** (MLB Stats API, ESPN, Polymarket) — the sandbox
  egress proxy blocks those hosts. Their degradation paths were
  exercised (each degraded exactly as its header says); their success
  paths were not run here. They run on the droplet every cycle.
- **The droplet itself** — no SSH from this session. The cycle timings
  quoted elsewhere today came from Ethan's pastes.
- **Lighthouse / network throttling** — no network for the CLI, no
  shaping in the sandbox.
- **Contrast measurement** — `contrast.py` exists; not run (palette not
  in scope).
- **Paid/entitled paths** — walked signed-out only (no Stripe keys, no
  account fixtures). The paywall code has its own 60+ tests in the suite.

### Confidence
Confident, because it was run: the money math (16 hand-computed
checks), every view at four widths with zero errors, the input fuzzing,
the security header/cookie/SQL-binding review, the fresh-clone suite,
and the three fixes' behaviour. Assumed, not verified: that the live
feeds behave on the droplet the way their offline degradation paths
suggest, and that the paid/entitled views render as cleanly as the
public ones (tests say so; I did not watch them).

Nothing here is "perfect." It is a site whose existing 8,373-test suite
had already caught most of what an audit finds, plus one real timezone
bug that only shows up on a UTC server at 1 AM, and three small polish
defects. The open questions above are product decisions, not bugs.
