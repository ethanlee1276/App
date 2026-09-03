# CFB readiness audit — 2026-09-02, for Saturday 2026-09-05

Branch: `qa/cfb-readiness`. Brief: `CFB_READINESS_PROMPT.md` (Ethan). The
question: can this produce a correct, complete, edge-having card for this
Saturday, and is there any proof the edge is real? Every number below says
where it came from and how big its sample is; "unverified" is used in
those words where nothing measures it.

Sandbox note: this container's proxy blocks ESPN (the schedule, teams,
conferences and results feed) and CollegeFootballData (recruiting,
returning production, portal, venues), and has no Odds API key — so the
live build **cannot run here**. The cfbfastR mirror on GitHub IS
reachable, so the 2026 schedule and rosters were pulled and checked
directly, and `data/history.db` holds 3,132 finished FBS games 2022–2025
with closing spread, total and moneyline, which is what the leak-free
replay in Phase 4 runs on. Everything that needs the droplet is marked.

## Phase 0 — Inventory

### The CFB system, file by file
| file | role |
|---|---|
| `docs/CFB_MODEL.md` | the instruction set ("Website Edition, 2026") + Implementation Map |
| `cfb_build.py` | the pipeline: ESPN schedule/teams/conferences → results ingest → ratings → talent prior → QB status → weather → prices → plays → TD long shots → `web/data/cfb.json` |
| `engine/cfb/model.py` | attention tier, haircut dial, min edge by tier, §9 grade, Kelly, per-play/game/slate caps, December window, QB gate |
| `engine/cfb/pipeline.py` | `evaluate_play` (devig → haircut → bar → grade → stake → conditional/hold), `run_cfb_slate`, volatility |
| `engine/cfb/ratings.py` | fitted margin/total spread, home field (solved jointly), scoring baseline; probation under 400 games |
| `engine/cfb/talent.py` + `engine/sources/cfbd.py` | recruiting composite, blue-chip ratio, returning production, portal → preseason prior (25% → 5%) — **key-gated** |
| `engine/cfb/context.py` | letdown / lookahead / short-week / late-season rivalry from the surrounding boards; the five context scores |
| `engine/cfb/status.py` | manual QB confirmations (`python3 launch.py --confirm-qb TEAM`), date-scoped store `data/cfb_qb_status.json` |
| `engine/cfb/wx.py` | kickoff weather: ESPN venue → CFBD venue lat/lon (key) → Open-Meteo |
| `engine/cfb/tds.py`, `engine/cfbtdfit.py`, `engine/cfbusage.py` | anytime-TD long shots and watch rows, roles from cfbfastR player stats, transfer bridge from rosters |
| `engine/teamrates.py`, `engine/gamebets.py`, `engine/odds.py`, `engine/staking.py`, `engine/ledger.py`, `engine/parlays.py` | the shared spine (ratings, pricing, devig, Kelly, journal/CLV, parlay taxonomy) |
| `engine/sources/cfbdata.py` (ESPN), `cfbfastr.py` (schedules), `cfbstats.py` (player stats, rosters), `cfblines.py` (closing lines) | feeds |
| `launch.py refresh_cfb` (600 s ceiling), `web/js/app.js` CFB tab, `web/data/cfb.json` | ops and the page |
| tests: 25 `tests/test_cfb*.py` files + `test_td_board.py`, `test_cfblines.py`, `test_cfbtdfit.py`, `test_lab_cfb.py` | |

### Data sources — what, how, how often, reachable here, on failure
| source | provides | fetch | cadence | here | on failure |
|---|---|---|---|---|---|
| ESPN college scoreboard/teams/groups (keyless) | schedule, kickoffs (UTC → ET in `to_eastern`), conferences, rankings, venue, results, divisions | HTTP JSON, `fetch_json` cache | every cycle, TTL 300 s | **blocked** | keeps the last board rather than publishing empty; `listed` vs `kept` counters catch a parse failure |
| CollegeFootballData (key) | team talent, blue-chip, returning production, portal, venues (for weather) | HTTP JSON, 30-day cache | per season | **blocked, no key** | "no prior", said on the page; no weather |
| cfbfastR mirror (GitHub raw) | season schedules (2022–2026), rosters (2022–2026), player stats (2022–2025; **2026 not published yet, 404**), closing lines | CSV, 7-day / 3-day cache | nightly harvest | reachable | history stays at last pull |
| The Odds API (key) | full-game spread/total/ML for the whole board in one call, 3 credits | bulk, pacer-gated | each cycle when affordable | no key | `--cached-odds` reuses the last paid pull |
| Open-Meteo (keyless) | hourly kickoff forecast | per venue | each build | blocked (needs CFBD venues first) | `weather_checked` False, environment score 0.45/0.6 |

### Hardcoded season / week / date
None that matter: the build is DATE-keyed (`cfb_build.py 2026-09-05`), season = the date's year, weeks come from the feed. Only prose mentions years (`ratings.py` "2022–2025", `tds.py` season pairs in a fitted table). `december_window` is month-based. ✓

### Copied from the NFL set and not adapted — the brief's prime suspects
- **Ratings**: `engine/teamrates.compute_team_ratings` is the NFL/MLB rating (points for/against vs baseline, shrunk n/(n+shrink)), used unchanged with shrink 8. It is **not opponent-adjusted**, which §5 calls "everything" in college. Consequence measured in Phase 5. Not a copy defect — a shared spine — but the college wrapper adds nothing for schedule strength.
- **Margin width, home field, baseline**: college-specific and FITTED (`cfb/ratings.py`), not borrowed. ✓ (16.5 / 2.47 / 26.9 vs the NFL's 13.5 / 1.6 / 22).
- **Season scoping**: NFL and MLB builds carry last season until this one stands up (`ratings_for_season`); the CFB build alone asked for this season only. **P1, fixed (5ec38ce).**
- **Tier / haircut / grade / caps**: rebuilt for college (attention dial, 12% slate cap, information-certainty weight). ✓
- **Parlay rules**: the shared taxonomy with a CFB `SportRules` (2.5 / 4.0 points, blowout 17). Conflicts probed in Phase 3. ✓
- **Grade vocabulary**: the CFB board grades A+/A/B+/Pass on its own 0–100 (`model.grade`), consistent with the 2026-09-02 site-wide decision.

## Phase 1 — This Saturday's card

The live build could not run here (ESPN blocked). What could be checked
was checked against the 2026 cfbfastR schedule and rosters pulled from
the mirror; the build's own feed is ESPN, which agrees with cfbfastR on
ids (cfbfastR ids ARE ESPN ids — Kansas State 2306 in both).

| check | result |
|---|---|
| 2026 schedule loads, right teams | 888 games, **138 FBS programs**, 11 conferences (ACC 112 games, American 87, Big 12 108, Big Ten 127, CUSA 59, Independents 14, MAC 77, MWC 61, **Pac-12 46** — the rebuilt Pac-12 exists in the feed, SEC 113, Sun Belt 84) |
| this Saturday | **68 games on Sat 9/5 (ET), 19 on Thu/Fri 9/3–4.** Kickoff windows 12:00 (10), 15:30 (12), 19:00 (13), 19:30, 20:00, 22:00 — Eastern via `to_eastern`, DST-aware. 1 neutral site (Auburn–Baylor, Mercedes-Benz Stadium) → `neutral_site` → no home field applied. **The brief calls this Week 2; the feed labels Aug 29–Sep 7 as Week 1** (Week 2 = Sep 11–13). Not a code matter — the build is date-keyed — but the Phase 4 early/late split uses the feed's weeks |
| FBS-only universe, FCS handled | **38 of the 68 Saturday games are FBS-vs-FCS.** ESPN's FBS feed lists them; the FCS side arrives without an abbreviation and is keyed `espn:{id}` (the 2026-08-31 fix that stopped opening Saturday from vanishing). They are shown and can be priced if a book quotes them; **until today they also entered the FBS host's rating at full weight — P1, fixed (5ec38ce)**, excluded once the teams feed says who is FBS |
| team identity in a realigned landscape | conferences come from ESPN's groups feed every cycle, not a checked-in list — nothing to go stale. Name map: **no two FBS programs share a key** in the 2025 or 2026 schedule names (`tests/test_cfb_names.py` sweeps it); both Miamis resolve to their own abbreviation from the odds feed's spellings. **P2 found and fixed (b9013d3): "Hawai'i" (ESPN) vs "Hawaii" (odds feed) never joined — the school was a counted miss on every board** |
| rosters reflect 2026 | cfbfastR 2026 rosters: **223 quarterbacks are on a different school than in 2025** (e.g. Mikey Keene Michigan → Arizona State, Billy Edwards Jr. Wisconsin → North Carolina, Walker Howard Louisiana → Ole Miss, Mitch Griffis Texas Tech → East Carolina, Jake Garcia Michigan → Furman). The RATINGS are team-level and cannot put a player at the wrong program; the TD board's roles are built from 2025 logs and bridged to 2026 rosters (`transfers` census, `cfbusage`). 2026 player stats are not yet published by the mirror (404), so every TD role is a 2025 role until they are — disclosed on the row ("Role built from 2025 logs") |
| coaching / coordinator changes | no feed; nothing in code is keyed to a named coach or coordinator, so nothing can be stale. §7's coaching layer is 📋 in the map and stays so |
| injury / availability | **no feed, by design.** §2.3 makes QB confirmation a GATE: with `data/cfb_qb_status.json` empty every play is a **Conditional** (number, price, edge, no stake). `--confirm-qb TEAM` per game per date is the only way a CFB bet is ever staked. No rule assumes an NFL-style designation; the spec's own gate is the only injury rule and it is executable (manually) |
| odds pulled, timestamped, stored | one bulk pull per cycle; `linemoves.record_snapshots` per book with game start; closes harvested nightly from cfblines for CLV. Not exercisable here (no key) |
| renders with correct labels | the CFB tab rendered clean in the 2026-09-01 QA walk; grades are `model.grade` letters |

## Phase 2 — Instruction set audit, CFB differences front and center

- **Talent dispersion / 40-point spreads.** Pricing is a normal CDF on a fitted 16.5-point margin width — no NFL-sized assumption. The credibility guard (>10% raw disagreement = rating error, not edge) is what actually handles blowout mismatches, and in Phase 5 it refused **55% of sides** because the ratings, not the market, were wrong.
- **Sample size / preseason priors (Week 2).** Spec: last 4 games 40% · season 35% · prior 25% decaying to 5%. Code: prior = talent composite (+ portal nudge) at 25% − 2%/game, scaled by returning production; results = this season's games shrunk n/(n+8). **Last year's efficiency — the first term of §5's own prior — was not in the prior at all**, and the prior is key-gated. **Fixed: the previous season is pooled until this one averages four games a team (5ec38ce).** FCS results: were at full weight — fixed, same commit. The 40/35 recency split is not implemented (one shrunk average).
- **Recruiting / high-school data.** Fetched (CFBD talent, blue-chip, returning, portal), current to the season's class, and USED — as a prior blended into the rating at a stated weight, not as a direct predictor of this week's margin. ✓ per spec. Whether it loaded on the droplet this week is on the page (`talent.available`). Not verifiable here (no key) — **Ask Ethan for the `talent` block of the live `cfb.json`**.
- **Motivation / situational.** Letdown, lookahead, short week and late-season conference rivalry are proved from the schedule; body-clock, bowl eligibility, mid-season coaching change, opt-outs are 📋. Logged as gaps, not invented.
- **Weather / venue.** Per-venue forecast via CFBD venues + Open-Meteo, used in the environment score and the totals' wind bands. Altitude: not modelled (gap). Venue-specific HFA: **§7 says "never a flat number"; the code has one league-wide number** (2.47, solved jointly with team strength). The map row read ✅ — corrected to 🟡 (7d68bfc).
- **Market structure / timing.** Open→close movement and key-number shopping are 📋; the attention dial is the market-structure rule that exists. Low-limit concentration: Phase 4 shows the model's bets concentrate in *low* attention games (1,892 of 2,902) — exactly the games with the lowest limits; noted, not measurable against real limits.
- **Sizing.** All explicit: quarter Kelly (half for A+ in a low-attention spot), 2% per play, 5% per game, **12% per slate applied in grade order** (`apply_caps`), drawdown halving. Pinned in Phase 3. Max bets per Saturday: not a rule; the slate cap bounds exposure, not count.
- **Parlays.** 3-leg cap in engine, slip and share; CFB conflicts (team total vs game total, favourite vs own under, both sides) killed or priced — pinned.
- **Undefined terms.** "Well-covered game" (§2.6) — code: attention tier. "Sanity-check … double digits" — code: the 10% credibility guard. "Clear outlier prices" (§8 Tier 3) — no number.

## Phase 3 — CFB-specific math (`tests/test_cfb_readiness_math.py`, 12 pins, 7d68bfc)

| check | hand | code |
|---|---|---|
| −2000 → 0.952381 / 1.05; round-trip; ends of the scale (±100000) | no overflow, no /0 | same |
| −2000/+1000 devig | 0.952381/1.043290 = 0.91286 | same (the CFB copy rounds to 4 places) |
| EV of a 95% favourite at −2000 | 0.0475 − 0.05 = **−0.0025** — a loser at 95% | same |
| Kelly at −2000 with p = 0.94 | negative → 0 | 0 |
| per-play cap | p = 0.99 at −110, quarter 0.245 → **0.02** | same |
| half Kelly | only A+ (≥90) in LOW: p = 0.55 → 0.01375 quarter, 0.02 capped half | same |
| 12% slate cap on seven 2% plays | the lowest-graded goes to 0 | same; 5% game cap → 2 + 2 + 1 |
| CLV | −2000 → −2500 = +0.00916 pts; −24 → −27 = +3 pts, signed by side | same |
| grade boundaries | 69/70/79/80/89/90; edge at the bar = 0.5 → 80 with full context, 56 with neutral | same |
| haircut by tier | +6% raw → 3.0 / 3.9 / 4.5 | same |
| 24-point spread | Φ(24/16.5) = **0.927** college vs Φ(24/13.5) = 0.962 NFL | college width installed |
| parlays | +264 / +596; −2000² → −976; 4th leg refused; conflicts killed/priced | same |

## Phase 4 — Is it actually making money?

**Profitability is unverified as a live record**: no 2025 CFB bet history
exists (the journal starts at build day; the sandbox ledger has none).
What exists is enough for a leak-free replay, so here it is.

### The replay (scratch `cfb_walk.py`; leak-free by construction)
3,132 FBS games 2022–2025 with closing spread, total and moneyline
(cfblines consensus). For each slate date, ratings from games strictly
before it; margin/total width, home field and baseline fitted from
strictly earlier seasons (2023 from 2022: hfa 1.79, sd 15.12; 2025 from
2022–24: hfa 2.47, sd 16.24). Priced through the production code
(`gamebets.price_*` → `cfb/pipeline.evaluate_play`: attention tier from
conferences and weekday, haircut, tier bar, grade, Kelly). Spreads and
totals at −110 against the CLOSE; moneylines at the closing pair. QB
status cannot be replayed, so every play is a Conditional and is counted
as a bet at its `stake_if_confirmed` — a generous assumption. No talent
prior in any variant (key-gated).

**Variant A — what the build did until today (season-only ratings):**

| slice | bets | hit | breakeven | ROI @ close | ±1 se |
|---|---|---|---|---|---|
| all | 2,306 | 42.6% | 32.3% | **−6.1%** | 3.2% |
| sides | 1,043 | 50.0% | 52.4% | −4.6% | 3.0% |
| totals | 575 | 52.6% | 52.4% | +0.4% | 4.0% |
| moneylines | 688 | 23.4% | 17.0% | −13.5% | 9.5% |
| standard attention | 698 | | | −11.8% | 6.8% |
| low attention | 1,608 | | | −3.6% | 3.5% |
| early (weeks 1–4) | 638 | | | −6.9% | 7.0% |
| late (weeks 5+) | 1,668 | | | −5.8% | 3.5% |
| 2023 / 2024 / 2025 | 892 / 731 / 683 | | | −9.4% / −1.9% / −6.2% | |

Flat max drawdown 144 u, longest losing streak 15. Kelly-sized ROI
−5.9% (Kelly does not rescue it). Moneyline Brier 0.1731 vs 0.1793
always-guess (mild skill — the model is a long-dog picker: 23% hit at
17% breakeven). Marquee tier: 0 bets (the 50% haircut and 4% bar never
cleared). Refused as not credible: 1,189 of 2,154 sides, 826 totals.

**Variant B — after 5ec38ce (previous season pooled until 4 games/team):**
2,902 bets, ROI −5.1% ± 2.8%; sides 1,274 at 50.0% / −4.6%; totals 795
at +0.2%; ML 833 at −10.9%; **early −3.1% (1,163 bets) vs A's −6.9%**;
late −6.5%; max drawdown 154 u; streak 24 on ML. The change is
structural (the rule the other builds run, and §5's own prior); its
effect is reported out-of-sample and it does not make the model
profitable.

**Variant C — FCS results excluded:** identical to B here, because the
sandbox history holds only games with a close, which are all FBS-vs-FBS.
The FCS effect exists on the droplet, where ESPN's ingest stores the buy
games; it cannot be measured in this container.

**Verdict, in the brief's words: the edge is not distinguishable from
zero — it is distinguishable from zero on the wrong side.** Sides lose
the vig exactly (50.0% against a 52.4% breakeven on 1,274 bets, 1.5 se
below zero); totals are a coin flip; moneylines lose 11% on long dogs.
Nothing here is above 10% — the too-good check passes trivially. Early
vs late: **no better in September** (−3.1% vs −6.5% after the fix, both
inside noise of each other and both negative). A model that only worked
after Week 6 would at least argue for sitting out; this one does not
work in either half.

### What is in place to verify from Saturday
Same as the NFL: every play journaled at build (timestamp, book, price,
line, model probability, devigged fair, EV, stake, attention tier,
conditions), prices snapshotted per book, closes harvested nightly
(`cfblines`), CLV and process grade at settle, the Record page's CFB
section empty until bets settle, no track record implied. Conditionals
are journaled as holds, not bets.

## Phase 5 — Ratings and projection sanity

**Power ratings, end of 2025, season-only, shrink 8 (`cfb_walk.py`):**
top 25 — Indiana +17.7, Texas Tech +15.6, Notre Dame +14.7, Ohio State
+12.8, Utah +11.8, Oregon +10.9, **James Madison +10.8, North Texas
+10.0**, Miami +9.4, South Florida +8.7, Georgia +8.6, Ole Miss +8.6,
**Toledo +8.4**, Vanderbilt +8.1, USC +7.9, Iowa +7.2, Washington +7.0,
Old Dominion +6.3, Texas +6.3, SMU +6.2, Texas A&M +5.9, Arizona +5.7,
Virginia +5.6, East Carolina +5.5, Oklahoma +5.4. Bottom 25 runs from
Colorado −5.8 to Massachusetts −17.3, with Oklahoma State −13.2,
Charlotte −14.3, Georgia State −12.3. No FCS team and no wrong-conference
team in the FBS list (0 non-FBS rows carry a rating in this history).

**What the eyeball says:** the top and bottom are plausible programs, but
**James Madison, North Texas, Toledo, Old Dominion and East Carolina in
the top 25 ahead of Georgia's neighbours is the schedule-strength error
in one line** — margins against G5 schedules are not adjusted for who
they came against. This is not a data bug; it is the model.

**Model spreads vs market spreads (2025 Week 2, the closest analogue to
this Saturday; variant B, pooled):** the twenty largest disagreements
are, every one, a Group of Five or FCS-adjacent visitor at a power
program — LSU −6.0 model vs **−36.5** close (Louisiana Tech), Auburn
−14.3 vs −42.75 (Ball State), Penn State −14.0 vs −41.75 (FIU), Texas
Tech −23.0 vs −48.0 (Kent State), Texas A&M −10.4 vs −34.5 (Utah State),
Texas −13.9 vs −36.75 (San José State) … Nebraska, Kansas State,
Clemson, Alabama, USC, Wisconsin, Florida. **The model is finding
rating compression, not value:** a 12-game shrink of n/(n+8) keeps only
60% of a team's own margin, no opponent adjustment credits a power team
for beating good teams, and the sum is a model that thinks LSU is a
touchdown better than Louisiana Tech. Overall model-vs-close spread RMSE
**8.2 points** (11.1 in weeks 1–4, 6.6 later) — for comparison the NFL
model's was 4.05 on the same measure. The credibility guard is doing its
job by refusing these; the board that reaches the page is the residue.

**Home field:** one league-wide number, 2.47 solved jointly with team
strength (the plain mean home margin, +4.73, was the buy-game bias and
was replaced). Not per venue or per tier — §7's gap, now on the map.

**Totals:** fitted 15.6-point width around a projection that is each
side's scoring deviation, with no pace or possession model — §5's
"single most important totals input" is 📋. Totals still graded a coin
flip at the close (+0.2% on 795), the one market not actively losing.

**Returning production:** fetched (CFBD) and used — it scales how fast
the talent prior decays, not the rating's size (the map explains why).
Verifiable on the droplet only.

## Phase 6 — Defects, worst first

| sev | what was wrong | status | commit |
|---|---|---|---|
| P1 | Week-2 ratings were one result shrunk to a ninth: the build asked for this season only and bypassed `ratings_for_season`, the pooled rule NFL/MLB run; §5's own prior includes last year's efficiency | **fixed**; early RMSE 11.97→11.06, early ROI −6.9%→−3.1% (out-of-sample, still losing) | 5ec38ce |
| P1 | FBS-vs-FCS buy games counted in the FBS host's rating at full weight (`espn:`-keyed visitors) | **fixed**, excluded once the FBS map loaded; not measurable here, watch the droplet's `fcs_excluded` flag | 5ec38ce |
| P2 | "Hawai'i" never joined the odds feed's "Hawaii" — every Hawai'i price a counted miss | **fixed**, pinned with the feed's spellings for 13 programs | b9013d3 |
| P2 | ratings are not opponent-adjusted (§5 "everything"); the 20 largest Week-2 disagreements are all schedule-strength errors | **not changed** — a solver is a modelling project, not an audit fix; map row corrected; **Ask Ethan** | 7d68bfc (doc) |
| P2 | §7 home field: one number where the spec says "never a flat number"; map claimed ✅ | doc corrected to 🟡 | 7d68bfc |
| P3 | brief says Sept 5 is Week 2; the feed labels it Week 1 | not a defect; noted | — |
| — | no name collision between programs; both Miamis resolve correctly | pinned | b9013d3 |
| — | Phase 3 pins | added | 7d68bfc |

Nothing removed or simplified; no threshold tuned; the one structural
change is reported before/after on the holdout it does not fix.

## Phase 7 — Verdict for Saturday 2026-09-05

**NO-GO for real money. The single biggest reason: on 1,274 walk-forward
spread bets against the close the model hits 50.0% at a 52.4% breakeven
(−4.6%, 1.5 se below zero), and the ratings that produce those bets
disagree with the market by 8 points RMSE because they are not
opponent-adjusted.** Nothing about this Saturday changes that: it is
early September, every FBS team has 0–2 games of 2026 data, 38 of the 68
games are FCS buy games, and the pooling fix only narrows the early-week
error from 12 to 11 points.

- **P0:** none found. **P1:** two, both fixed today (5ec38ce). **P2:**
  three, one fixed (b9013d3), two documented.
- **Backtest numbers:** above. Profitability is **unverified** as a
  record and **negative** in replay.
- **Ratings and projection:** plausible ends, schedule-strength
  compression in the middle; G5 programs rated above power programs
  they would be three-touchdown dogs to; home field one number; totals
  with no pace model.
- **Early-season judgment:** not trustworthy right now, and — unlike a
  model that improves with data — not measurably better after Week 4
  either. Sitting out September costs nothing the replay can find.
- **What was not testable and what it would take:** the live build
  (ESPN blocked → run `python3 cfb_build.py 2026-09-05 --cached-odds` on
  the droplet and paste `ratings`, `talent`, `qb`, `feed` and the play
  count); the talent prior's contribution (CFBD key); the FCS-exclusion
  effect (droplet history); weather (CFBD venues); real limits at the
  low-attention books.
- **Confident because it ran:** every number in Phases 3–5, the 2026
  schedule and roster checks, the name-map sweep, the three fixes'
  tests. **Assumed:** that the droplet's ESPN/CFBD feeds answer as the
  code expects (they did on 2026-08-30/31 per the journal), and that
  conditionals would be confirmed as bets — the replay's generous case.

**What the site should do Saturday:** publish what it already publishes
— conditionals with number, price and edge and no stake, the TD watch
rows, the most-likely board — with the probation and no-track-record
copy that is already on the page. Do not `--confirm-qb` anything into a
staked bet this week on this evidence.

**Ask Ethan (money decisions, not decided here):**
1. Bet Group of Five at all? The replay's bets are 65% low-attention
   games, and they lose 5% at the close; the marquee tier never
   qualifies. On this evidence, no — but it is the model losing, not
   the tier.
2. Sit out September (and, on this evidence, October)? Recommended:
   paper only until a settled sample beats the close.
3. Opponent-adjusted ratings: commission the solver (a ridge/Massey
   rating on margins is a week's work and is what §5 asks for) before
   any CFB money.
4. Bankroll / Kelly / books for CFB: the same defaults as the NFL
   answer (quarter Kelly, 1u = 1%, caps, harvested books) — nothing here
   argues for more.
5. Manual QB confirmation is the only path to a staked CFB bet. Keep
   it, or accept unconfirmed conditionals? Keep it.
6. Paste from the droplet: the live `cfb.json` `ratings` (incl. the new
   `seasons_used` / `fcs_excluded`), `talent`, `qb`, `feed` blocks and
   the play/conditional counts for 9/5, so Phase 1 can be closed on the
   real feed.

## Phase 8 — Ethan's decisions (2026-09-02) and what shipped for each

Ethan's answers to the six Ask-Ethan items, verbatim: "Ok merge that if
u didn't. And 1. No 2.no 3. Whatever u think. 4. whatever u think 5. Idk
what ur saying". The audit branch was merged as it stood (4b3c853); the
work below followed on the same branch.

**1. Bet Group of Five at all? — "No."** Shipped: `model.BET_GROUP_OF_FIVE
= False`. A game in which neither side is a power-conference team is
priced, shown with its number, edge and the reason, and never a play —
in `pipeline.evaluate_play` for sides, totals and moneylines, and on the
touchdown board, where such a pick keeps its reasoning and lands on the
watch. A power opponent lifts a game out of the rule (a buy game IS a
power-conference game); an Independents-vs-G5 game stays under it. The
attention dial is untouched. Effect on the replay: the bet count falls
from 2,902 to 1,324 (the 65% of bets that were low-attention games), and
what remains still loses at the close (−4.1%). Pinned in
`tests/test_cfb_group_of_five.py`.

*Which four, and how far the rule reaches.* `POWER_CONFERENCES` is
**SEC, Big Ten, Big 12, ACC** — four of the eleven conferences the feed
can name. The seven it leaves out are American, Conference USA, **FBS
Independents**, MAC, Mountain West, **Pac-12** and Sun Belt, which is
why the replay loses 65% of its bets to one line of set membership. The
two in bold are the ones the rule's name does not predict: FBS
Independents is Notre Dame's conference (deliberate, and stated above),
and the Pac-12 is a judgement about what that league is after the 2024
realignment rather than a fact about its name. Both are pinned so that
moving either is a deliberate change to a betting rule. The sentence a
reader sees says what was tested — "Neither side is in a power
conference (SEC, Big Ten, Big 12, ACC)" — rather than "Group of Five
game", which would be wrong over Notre Dame at Navy; it lives once, as
`model.NOT_A_POWER_GAME`, because the game board and the touchdown board
both show it.

*Open for Ethan — and now answerable.* The Pac-12 call has never
actually been asked. It was inherited from a set literal written before
the realignment settled, and nobody has decided whether a 2026 Pac-12
game should be bettable. It is still not decided here.

What changed is that it CAN be. One set was doing two jobs: the money
gate (`is_group_of_five`) and the attention dial (`attention_tier`) both
read `POWER_CONFERENCES`, so adding "Pac-12" to it did two opposite
things at once — opened the money gate, and moved those games LOW →
STANDARD, taking the haircut 25% → 35% and the bar 2.5% → 3.0%. The
games it made bettable became harder to bet in the same stroke, and no
replay of "should we bet the Pac-12" could mean anything. The rule's own
note had promised the two were separate; both read one set, so they were
not.

They are two sets now — `POWER_CONFERENCES` (attention) and
`BETTABLE_CONFERENCES` (money) — with identical membership, so today's
board is unchanged. The switch is `"Pac-12"` into `BETTABLE_CONFERENCES`
and nothing else.

**But only half the measurement is available, and an earlier version of
this paragraph got that wrong.** It said to "replay, and read the bet
count and the ROI at the close the way Phase 8 read them". The bet
count, yes. The ROI, no: college football's stored closes come off the
cfbfastR mirror, which publishes every book's *number* and none of their
prices. `gamebacktest.schedule_closes` says it outright — "that is fatal
for a backtest, which has to price a bet" — and `backtest_game_lines`
refuses to default them to −110, because "defaulting them to −110 would
publish an ROI computed against a price no book ever offered, which is
the one thing this replay exists to avoid".

What a replay can answer today, with no invented price:

- how many games the switch newly admits, and
- how far the model's number sits from the market's on them — which is
  `engine.gamecal`'s question and never reads a price.

What it cannot answer is whether those bets would have **made money**.
That needs priced closes, and the only priced CFB closes are harvested
rows in `odds_history` (`game_line_closes` skips any row missing either
price). The line ledger has been writing them at game-market scale since
late August; a paid `harvest_odds.py` backfill is the other route.

*And this casts a shadow backwards.* Phase 8's own CFB figures quote an
ROI at the close (−4.1%), and `engine/cfb/model.py`'s §3.6 note quotes
41-30-2 and +10.2% on totals. Both need prices the mirror does not
carry. Whether they came from harvested rows or from an assumed −110 is
not written down anywhere. `SELECT COUNT(*) FROM odds_history WHERE
sport='cfb' AND over_odds IS NOT NULL` on the droplet settles it. Until
it does, a college ROI-at-the-close in this document is unprovenanced —
including the one two paragraphs above.

*What the 2026 feed says about the league itself,* since the answer used
to be "two schools": the rebuilt Pac-12 is real and in the feed — **46
games** of 888, alongside 138 FBS programs across 11 conferences (the
table at the top of this document). The premise in
`assets.probe_conference_table` that called it "two schools rather than
a conference" was true of 2024-25 and is corrected.

**2. Sit out September? — "no."** Nothing changes: the board publishes
in September as it does in November. Recorded so the evidence is next to
the decision: weeks 1–4 replayed at −5.1% (adjusted, 692 bets) against
+0.1% later (570). The QB gate (item 5) means nothing is staked without
a confirmation either way.

**3. Opponent-adjusted ratings — "whatever u think." Built and adopted.**
`teamrates.compute_adjusted_ratings`: offense and defence solved jointly
with the opponent taken out (coordinate descent, no matrix library), the
same n/(n+8) shrink, the home field the variance fit solves first, zero on
a neutral site; `adjusted_ratings_for_season` applies the same pooling
rule. The build prices on it and re-fits the variance around the
projection actually priced. Rule 2 (no tuning; before/after on the
holdout), same replay, same gates, same dates, Group of Five off in both:

| | plain, pooled (B) | opponent-adjusted (D) |
|---|---|---|
| model-vs-close spread RMSE, all / weeks 1–4 / later | 8.23 / 11.06 / 6.60 | **7.62 / 9.86 / 6.39** |
| bets, ROI at the close | 1,324, −4.1% ± 4.5 | 1,262, **−2.7%** ± 4.2 |
| sides | 646, −4.4% | 634, −5.0% |
| totals | 295, +4.3% | 311, +0.7% |
| moneylines | 383, −9.9% | 317, −1.6% |
| early / late | −8.1% / +1.1% | −5.1% / +0.1% |
| 2023 / 2024 / 2025 | −4.6 / −3.3 / −4.3 | −7.6 / **+1.1** / −1.8 |
| max drawdown (flat) | 80.7 u | 66.4 u |
| ML Brier vs base | 0.1674 vs 0.1865 | 0.1750 vs 0.1918 |

Less wrong about the market, smaller drawdown, still not a profitable
model — adopted for the first reason, reported with the third. The
end-of-2025 adjusted top 25 moves Miami, Georgia, Alabama, Penn State
and Michigan up and James Madison, North Texas and Toledo down, which is
the direction the schedule says. The twenty largest Week-2
disagreements are still buy games (Auburn −16 vs −42.75), now 5–10
points closer. Pinned: a planted four-team structure is recovered
exactly; a team that beat a strong opponent by 3 ranks above one that
beat a weak opponent by 20.

**4. Bankroll / Kelly / books — "whatever u think."** Unchanged: quarter
Kelly, half only for an A+ in a low-attention spot, 2% / 5% / 12% caps,
drawdown halving, the harvested books. Nothing in the replay argues for
more, and the model is not one to size up on.

**5. Manual QB confirmation — "Idk what ur saying."** In plain words:
college football has no injury report, so the site cannot know who is
starting at quarterback. The spec's rule (§2.3) is that a bet is not a
bet until both starting quarterbacks are confirmed. The site publishes
every qualifying college play as a **Conditional** — the number, the
price, the edge, and a note saying it is waiting on the quarterbacks —
with no stake. To turn one into a real, staked bet you run
`python3 launch.py --confirm-qb TEAM` for BOTH teams on the droplet once
you have seen who is starting (beat writers, the broadcast, the school's
availability report). If you never run it, no college bet is ever
staked or journaled as a bet; the conditionals still show. **Decision
taken for you: keep the gate.** It is the one rule in this spec that
protects you from the biggest single price-mover in the sport, and on
this week's evidence there is nothing worth un-gating.

Verdict after the decisions: unchanged — **NO-GO for real money.** The
model is less wrong than it was this morning and Group of Five is off
the board; neither makes the remaining bets profitable at the close.
