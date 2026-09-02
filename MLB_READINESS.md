# MLB readiness audit — is Scalpy holding up down the stretch? (2026-09-02)

Branch: `qa/mlb-readiness`. Brief: `MLB_READINESS_PROMPT.md` (Ethan,
2026-09-01). The question: **is this model actually profitable on its
2026 record, and are its assumptions still valid for September and
October?** "Ready" is claimed only where a number says so; everywhere
else this log says **unverified** in those words.

## Read this first

**Profitability is unverified — in this sandbox.** The container this
audit ran in has no MLB history (`data/history.db`: 0 MLB games, 0
player logs, an empty `odds_history`), a stale copy of the bet journal
(33 MLB rows from July 6 to August 25, no closing prices, no stored
model probabilities), and an egress policy that blocks
`statsapi.mlb.com`, Baseball Savant, Open-Meteo and The Odds API. The
2026 record lives on the droplet at `/srv/qellys/data/ledger.db` and
only the droplet can score it.

So Phase 4, "the main event", is delivered as a **tool plus the exact
commands**, not as numbers. `engine/mlbrecord.py` computes every figure
the brief lists — count first, hit rate against breakeven, ROI at price
and at the close, CLV mean and beat share, Brier by bucket with the HR
5–15% band split in two, drawdown, losing streak, flat vs sized,
parlays apart from straights, month by month — from journal columns
that already exist, writes nothing, and refuses to state a verdict
under 100 settled bets. Ethan runs it on the droplet through Remote
Control (Phase 4 has the commands) and pastes the output back; the
verdict in Phase 8 is written to be filled from that output and says
"unverified" until it is.

Everything that does not need the droplet was done here and is listed
by phase below: the inventory, the adversarial read of Scalpy, 28
hand-computed arithmetic pins, the HR model walk-through, the parlay
correlation probes, the postseason gap, one defect fixed, and the
"Ask Ethan" decisions.

## Phase 0 — Inventory

### The five engines, what they consume, what they emit, and how they combine

Scalpy 2.0 (`docs/MLB_MODEL.md`, 589 lines) names five engines. In the
repo they are:

| engine | doc | code | consumes | emits |
|---|---|---|---|---|
| Pitching | §5 | `engine/mlb/projection.py` (K props), `engine/mlb/arsenal.py` (pitch mix, whiff by type, last-5-start drift), `engine/mlb/velocity.py`, `engine/mlb/openers.py`, `engine/mlb/matchup.py` | statsapi game logs, per-pitch play-by-play (`sources/pbp.py`), Savant pitcher boards | strikeout / outs projections; `pitcher_certainty` (15% of every grade); the opposing-pitcher multiplier for hitter props |
| Hitting | §6 | `engine/mlb/projection.py` (hits / TB), `engine/mlb/homeruns.py` (HR), `engine/mlb/statcast.py`, `engine/mlb/platoon.py`, `engine/mlb/streaks.py` | Savant expected stats + barrels (season CSVs, 6 h TTL), own game logs, official platoon splits | per-market mean + sd (normal / empirical), HR per-game rate → Poisson |
| Environment | §7 | `engine/mlb/parks.py`, `engine/mlb/weather.py`, `engine/mlb/umpires.py`, `engine/mlb/bullpen.py` | park table (30 parks, wind orientation, roof), Open-Meteo per park, boxscore officials (tonight's plate umpire), last-two-day relief innings from boxscores | multipliers per market with a stated reason each |
| Opportunity | §8 | `engine/mlb/opportunity.py` (expected PA from slot + run environment), `engine/mlb/gamesim.py` (lineup sim, **disabled** via `simjoint.ENABLED=False`) | confirmed lineups (statsapi), team totals | PA factor; lineup certainty |
| Learning / market | §4, §11 | `engine/mlb/ml.py` (learned multiplier), `engine/calibrate.py`, `engine/losspatterns.py`, `engine/linemoves.py`, `engine/holdwatch.py`, `engine/ledger.py`, `engine/clvboard.py` | settled journal rows, price snapshots | calibration curve, loss-pattern vetoes, movement grade points, measured one-sided hold |

**How they combine — the rule is defined, and it is a product.**
`projection.build_projection` multiplies park × weather × matchup ×
Statcast × umpire and clamps the product to [0.78, 1.28]; rare-event
markets (HR) damp the product further (`RARE_EVENT_ENV_DAMP = 0.5`,
i.e. the square root). Each engine's contribution is recorded as a
`chain.step` with its reason, so the card can show which dial moved the
number. **Where two engines can disagree, the learned model wins
outright**: when `ml.py` has a fitted model for the market, its
predicted multiplier *replaces* the whole hand-tuned product and the
hand modules supply only the prose. That is a defined resolution rule
(not a P1), but it means a fitted `ml.py` model silently dominates four
engines — logged as **F-2.1** (P2) below, because nothing on the card
says which regime priced it beyond the one "Learned model adjustment"
line.

### Every file that touches MLB

- Pipeline: `mlb_build.py` (date → schedule, probables, lineups, Open-Meteo, Savant, odds, holdwatch quote journal → `web/data/mlb_recommendations.json`), `engine/mlb/pipeline.py` (the slate: props, game bets, HR long shots, parlays, correlation flags, exposure caps), `launch.py refresh_mlb` (every cycle), `lineupwatch.py` (rebuild when lineup cards post), `live_build.py` / `engine/mlb/liveprops.py` (in-play tracking; the pre-game model refuses live prices via `block_live_games`).
- Sources: `engine/mlb/sources/mlbstats.py` (schedule with `gameNumber`, probables, lineups, boxscores, officials), `sources/savant.py`, `sources/pbp.py` (per-pitch), `sources/statslogs.py`, `sources/live.py`.
- Pricing: `engine/mlb/betting.py` (`evaluate_mlb_prop`: side pick, haircut, credibility guard, calibration gate, loss-pattern veto, tier bars 2.1% / 2.6% / 6%, favourite surcharge, MLB quality score and 66-floor), `engine/mlb/quality.py`, `engine/odds.py` (two-way and one-sided devig), `engine/devig.py` (market-sum devig, `expected_distinct_hr_hitters`), `engine/gamebets.py` (`price_total` etc. — normal model, shared with football), `engine/staking.py` (Kelly veto + price ladder).
- Correlation and parlays: `engine/correlation.py` (`flag_mlb_correlations`, `apply_exposure_caps`), `engine/parlays.py` (§3 taxonomy `relate`, `check_ticket`, `MAX_LEGS = 3`, `EXTREME_MARKETS`), `engine/mlb/simjoint.py` (disabled).
- Record: `engine/ledger.py` (`bets`, `_bet_price_clv`, `_bet_clv`, settle, `why_open`, `unplayed_bets`), `engine/parlayledger.py` (`parlays`, `parlay_legs`, singles P&L beside every ticket), `engine/clvboard.py`, `stakecheck.py`, `edge_audit.py`, `mlb_calibration.py`, `hr_backtest.py` / `engine/mlb/hrbacktest.py`, `engine/mlb/backtest.py`, `harvest_odds.py`, and now **`engine/mlbrecord.py`** (this audit).
- Pages: `web/js/app.js` MLB views (recommended, game bets, long shots / HR board, Most Likely, parlay zone, live, record); the slip (`slipAmerican`, `slipCheck` → `/api/parlay/check`).

### Data sources

| source | provides | fetch | cadence | reachable here | on failure |
|---|---|---|---|---|---|
| MLB Stats API schedule (`hydrate=probablePitcher,venue`) | games, `gameNumber`, probables, venue | keyless HTTPS | every launcher cycle | **no (403 via proxy)** | `mlb_build.py` exits 2 with the URL and the cache path it would accept; the launcher keeps the last board |
| MLB Stats API lineups / boxscores / officials | confirmed lineups with slot, relief innings, tonight's plate umpire | keyless | every cycle; `lineupwatch.py` polls until cards post | no | hitter props held (lineup hold); umpire neutral |
| Baseball Savant expected stats / barrels (season CSVs) | xBA/xSLG/xwOBA, barrel %, hard-hit % | keyless CSV, 6 h TTL | per cycle (cached) | no | contact multiplier neutral, reason says so |
| statsapi play-by-play | per-pitch type/speed for arsenal | keyless | per start | no | arsenal absent → matchup neutral |
| Open-Meteo | wind speed/direction, temp, humidity per park | keyless | per cycle | no | weather neutral |
| The Odds API | prop and game prices per book, timestamped into `odds_history` via `linemoves.record_snapshots` | key, budgeted | per cycle when affordable; `--cached-odds` otherwise | **no key here** | last paid pull reused; proxies never overwrite real prices |

### Hardcoded season / date

None in the pricing path. `mlb_build.py` takes the date as an argument;
the launcher supplies today. The only literal 2026 is the CLI default
in `sources/savant.py` (`year = int(sys.argv[1]) if … else 2026`), a
debugging entry point. Park notes mention renovation years as prose.

## Phase 1 — Tonight's slate, end to end (what could and could not run)

**Dry run here:** `python3 mlb_build.py 2026-09-02 --cached-odds` exits
2 in 0.4 s: "Live MLB data unavailable … Tunnel connection failed: 403
Forbidden … place a cached response at data/cache/mlb_schedule_2026-09-02.json".
That is the documented failure behaviour and it is correct (no fabricated
slate, exit code the launcher understands). The full card could not be
produced here. Each bullet of the brief is answered from the code:

- **Schedule / doubleheaders.** `gameNumber` is read from statsapi and carried as `game_number` + `doubleheader` on every game and prop; headlines get "(DH Game N)"; the situations map is keyed by `(home, away, game_number)`. Two games of a doubleheader are two games. First-pitch times are ISO with zone; the page converts. **Unverified live.**
- **Probable vs confirmed starter.** Probables come from the schedule hydrate every cycle (launcher sleep 60 s + a cycle of several minutes; the MLB build alone takes ~235 s on the droplet, task #93). `pitcher_certainty` is 15% of every MLB grade; a hitter prop whose opposing probable is unknown carries "Opposing starter not confirmed" and loses grade. **Gap (F-1.1, P2):** there is no explicit scratched-starter rule. A rebuilt board drops the card, but a strikeout prop already *journaled* on a pitcher who is then scratched stays open; `unplayed_bets` only voids games that were never played. On the droplet, `ledger.why_open` will list any such rows.
- **Confirmed lineups.** `lineups_confirmed` per game from statsapi; the lineup hold in `engine/mlb/rules.py` suppresses hitter props until the player is in a posted card; lineup certainty is 0.85 unconfirmed / 1.0 confirmed in the grade; the parlay screen kills every hitter leg of an unconfirmed lineup (pinned in `tests/test_parlays.py`); the HR caveat states when cards post ("~3h before first pitch"). Batting-order slot is captured and drives PA (`PA_BY_SPOT`). ✅ by code.
- **September roster expansion.** No September rule anywhere (grep of `engine/mlb` and the doc finds only a park note about cold nights). Thin samples are handled *generically*: the HR base rate weights a hitter's own rate by `min(n/40, 0.5)` against the league 3.3%/PA (a 12-game call-up gets 0.3 weight on his own rate), `RARE_EVENT_PRIOR_GAMES = 30`, `opportunity.MIN_GAMES = 10`, platoon `MIN_PER_SIDE = 8` with shrink 15. That is regression, not a September rule. **F-1.2 (P2, Ask Ethan).**
- **Bullpen state.** `bullpen.py` measures the last two days' relief innings from boxscores (yesterday full weight, the day before half) and nudges opposing hitters up to +6%. It does not track *which arms* are unavailable, and it has no notion of a contender resting arms or an eliminated team running bulk relievers. **F-1.3 (P2 gap).**
- **Park, weather, umpire.** Per game: all 30 parks carry coordinates, wind orientation and roof; Open-Meteo is fetched per park; wind is resolved relative to the park's orientation (Phase 2); the plate umpire is read from the boxscore officials for tonight's game, not a season average of someone else. ✅ by code.
- **Odds.** Pulled per cycle within budget, per book, and snapshotted into `odds_history` with `taken_at`; every journaled bet stores `ts`, `book`, `odds`, `line`, `hit_prob`, `stake_units`, `lead_min`; closes are harvested nightly into `closing_line` / `closing_odds`. ✅ by code; coverage is a Phase 4 number.
- **Render.** Grades on the MLB cards come from the same `quality` score that gates them (`mlb_letter` at 66/80/90). **Unverified here** (no payload to render).

## Phase 2 — Scalpy read adversarially

Numbered findings. Severity: P0 loses money tonight, P1 will lose money
or hide that it is, P2 wrong but bounded, P3 cosmetic / doc.

| id | sev | finding | where | status |
|---|---|---|---|---|
| F-2.1 | P2 | A fitted `ml.py` model replaces the entire hand product (park × weather × matchup × Statcast × ump). Defined rule, but four engines go silent behind one "Learned model adjustment ×1.07" line; the card cannot show a learned-vs-hand disagreement. | `projection.py` ~L244 | flagged; no change (rule 1) |
| F-2.2 | P2 | **Refusal named the wrong cause.** `mlb/betting.py` kept the one-branch `if not credible: NO_CREDIBLE_EDGE_REASON`, so an HR card with a real DraftKings price and a >10-point model/market disagreement was told "no real book line to price against". The NFL board was split on 2026-09-02; MLB was not. | `engine/mlb/betting.py` | **fixed** — `fix(mlb)` commit below, pinned in `tests/test_refusals.py` |
| F-2.3 | P2 | Two plate-appearance tables price the same fact: `homeruns.PA_BY_SPOT` (4.6 … 3.7, real money) and `gamesim.PA_BY_SPOT` (4.65 … 3.85, the disabled sim). They differ by 0.05–0.15 PA per slot (up to 4% of an HR rate for slots 6–9). Neither is home/away aware (a home team leading after 8½ does not bat in the ninth). | `homeruns.py:39`, `gamesim.py:52` | flagged + pinned (`test_two_pa_tables_disagree_and_that_is_logged`); reconciling is a parameter change → rule 2 → Ask Ethan |
| F-2.4 | P3 | Park factors are hand-curated constants (per outcome, roof-aware, handedness HR splits on six parks), not fitted from multi-year data. The doc's map said handedness splits were "📋 parked" — they are built. | `parks.py`, `docs/MLB_MODEL.md` map row | doc row corrected in this branch; factors unchanged |
| F-2.5 | P3 | CLV is computed on raw implied probabilities (`_bet_price_clv`, and the same in `mlbrecord.price_clv`), not de-vigged ones. Sign is unaffected; magnitude on a one-sided market is overstated by the hold (÷1.06). | `ledger.py:3021` | flagged; pinned (`test_clv_on_devigged_probabilities_keeps_the_sign_of_raw_clv`) |
| F-2.6 | P2 | HR + game-over and HR + opposing-K-under pairs are allowed at a +0.10 *prior* ("§1.1's floor"), not a measurement. HR + HR same lineup uses ρ = +0.186 measured on 27,613 games of lineup pairs — measured on total-bases outcomes and applied to HR outcomes. | `parlays.py` MEASURED, `relate` | flagged; pinned in `test_mlb_readiness_math.py` |
| F-2.7 | P2 | **The slip prices HR parlays at the independent product.** The engine's own tickets refuse HR legs (`EXTREME_MARKETS`), but a person can put two HR props on the slip: `check_ticket` warns "two bats in one lineup … +0.19", and the slip prints the naive combined price with "% if the legs were independent · correlation is not priced here". Disclosed, not priced. The modeled joint is never shown. | `app.js slipAmerican`, `parlays.check_ticket` | flagged; Ask Ethan (money decision) |
| F-2.8 | P2 | No drawdown behaviour. Sizing has a per-bet ladder (0.35–1.25u), 5u per game, 15u per slate (uniform scale — pinned), but nothing reduces size after a losing run or a bankroll drop. §10 of the doc lists "circuit breakers" as caps only. | `staking.py`, `correlation.py` | flagged; Ask Ethan |
| F-2.9 | P3 | Umpire effects are applied to K props at full weight and to hitter markets at half weight, shrunk over 8 games and clamped to ±10%. Plausible and small — no overfitting found. | `umpires.py` | none needed |
| F-2.10 | P3 | Batter-vs-pitcher career numbers: the field exists (`vs_pitcher_avg`), is shown on the card as history, and is **not priced** (`projection.py` L205: "no live source emits vs_pitcher_avg"). The amateur error is absent. | — | none |
| F-2.11 | P2 | Arsenal drift is in-season (last 5 starts vs a 4-start baseline, per-pitch from statsapi), batter-vs-pitch-type needs `MIN_BATTER_PA = 25` with pooled league whiff as the prior; but the *matchup multiplier* sits inside the [0.78, 1.28] product with no separate statement of how much of the clamp it may consume. | `arsenal.py`, `matchup.py` | flagged |
| F-2.12 | P1 | **No postseason rule of any kind** — see Phase 6. | doc + code | Ask Ethan |
| F-2.13 | P2 | No September rule — see Phase 1. | doc + code | Ask Ethan |

Undefined terms with no number: none found in the pricing path — every
multiplier here is a constant with a name (`TEMP_HR_PER_F = 0.0045`,
`TIRED_MIN = 6.0`, `FACTOR_CLAMP = (0.90, 1.10)`, …). The doc still
uses "favourable park" and "strong matchup" in §7/§8 prose, but the
code they describe is numeric.

Weather: wind direction relative to park orientation ✅ (threshold 8 mph,
+1.2%/mph blowing out for HR/TB); temperature ±0.45%/°F from 70 ✅;
humidity ≥70% at ≥70 °F a small carry bonus ✅. Magnitudes stated.

Statcast: barrel % ^0.6, hard-hit % ^0.4, xSLG−SLG gap; expected stats
are the input (they stabilise faster), own results are shrunk
(`min(n/40, 0.5)`). ✅

Sizing: 100u bankroll; Kelly is a **veto only** (`kelly_units` returns
0 at or below breakeven and otherwise the price ladder sets size); max
1.25u per bet; 5u/game; 15u/slate scaled uniformly (pinned: 20 props
asking 20u all become 0.75u). ✅ The cap is a total, not a per-bet
number. Drawdown: F-2.8.

Parlays: 3-leg cap in `MAX_LEGS`, `check_ticket` ("3 legs is the
ceiling"), the slip and the parlay zone ✅. "Conflicting" for baseball,
as the code defines it: two hitters in one lineup → allowed, priced at
+0.186 measured; hitter over + opposing pitcher K over → **killed**
(Type 7, "the same pitches cannot strike out the side and get hit");
hitter over + opposing K under → allowed at +0.10 prior; hitter over +
game over → allowed at +0.10 prior; two batters vs the same pitcher is
the same-lineup case. `flag_mlb_correlations` also rejects K-over vs
opposing hitter over at single-bet level and counts offence stacks as
one exposure. **Verdict on "correlated HR props priced as
independent":** the engine never builds one; the slip lets a person
build one and says the price ignores correlation (F-2.7).

## Phase 3 — MLB-specific math (`tests/test_mlb_readiness_math.py`, 28 pins)

Every expected value below was computed by hand before the assertion.

- Conversions: +300 → 25.0% / 4.00; +650 → 13.33%; +1000 → 9.09% / 11.0; −2000 → 95.24% / 1.05; ±100 both 50% / 2.0, no division by zero; decimal→American spells 2.0 as −100 (Ethan's call).
- Two-sided devig: −115/−105 → over 51.08%, sums to 1.
- One-sided HR devig: +400 alone → 20.0% ÷ 1.06 = 18.87%. **The naive method the brief warns about is refused:** pairing +400 with a fabricated −110 under and normalising would say 27.6% (six points *higher*); the code detects the impossible pair (`pair_is_sane`: .20 + .52 < .95) and prices it one-sided, identical to no under at all.
- Market-sum devig: a 9-run total supports 9 × 0.25 × 0.95 = 2.1375 distinct HR hitters; eight prices summing to 2.80 give a hold multiplier 1.3099 and a fair 15.27% for a 20% raw; a board summing to fewer hitters than the total supports is *unmeasurable* (None), never a multiplier below 1; fewer than 6 priced hitters is unmeasurable.
  - Which method: multiplicative (one hold multiplier, or the power method `power_exponent` where the game devig selects it — `DEFAULT_METHOD = POWER` in `engine/devig.py`), measured off tonight's own HR menu per game when ≥6 hitters are priced; otherwise the season's measured one-sided hold from the quote journal (`holdwatch`), otherwise the 1.06 assumption. Shin is parked (doc map), and that is fine: the market-sum method is the right shape for a one-sided menu with a known distinct-scorer count.
- EV sign: 35% at +150 → −0.125; 45% → +0.125.
- Kelly: 50% at −110 → 0; 20% at +400 (exactly breakeven) → 0; 25% at +400 → fraction 0.0625 → **0.38u from the ladder** regardless of how much edge above zero (40% at +400 is also 0.38u); 60% at −110 → 1.0u.
- Caps: 20 × 1u props → 0.75u each, 15u total; 6 × 1u in one game → ≤ 5u.
- CLV: +400 taken, +350 close → +2.22 points; the record tool and the ledger agree; line CLV on a 0.5 HR line is 0 forever (price CLV is the instrument); de-vigged CLV keeps the sign of raw CLV.
- Grades: 65.99 → Pass, 66 → B+, 79.99 → B+, 80 → A, 89.99 → A, 90 → A+.
- Parlays: −110 × −110 → +264; three → +596; a fourth leg refused ("3 legs is the ceiling"); two HR props from one lineup → ok with a +0.19 warning; HR + opposing K over → kill Type 7; HR + game over → ok, unmeasured prior; HR in `EXTREME_MARKETS`.
- Poisson: P(≥1) = 1 − e^−λ (λ = 0.2 → 18.13%, not 20%); the HR model computes `rate = per-PA × PA` and then `prob_at_least_one(rate)` — pinned on the source.
- Plate appearances: 4.6 (leadoff) down to 3.7 (ninth), monotone; default 4.0; **the function takes the slot alone** (no home/away) — pinned as a visible gap; the two PA tables differ by 0.05–0.15 — pinned.

**Distributional findings** (reported, nothing changed):
- Home runs: Poisson on a per-game λ — correct for a rare event; the doc's own measurement on TD counts shows ≤1-event markets are *under*-dispersed, so Poisson slightly understates P(≥1) and the calibration curve absorbs the residual. Tails: the rate is clamped to [0.002, 0.50] → P(≥1) ≤ 39.3%; the HR board floors at 12% (`MIN_MODEL_PROB`).
- Hits / total bases: empirical distribution from the hitter's own log blended with a normal (right skew handled — the doc records the 81% vs 58% error that motivated it). ✅
- Strikeouts: normal with floors. Acceptable for a count centred near 6.
- **Game totals: normal** (`gamebets.price_total`, shared with football, `TOTAL_SD` per sport). Run scoring is over-dispersed and discrete with key numbers at 7/8/9; a normal is the weakest distribution in the system for a market the brief calls among the sharpest in North America. **F-3.1 (P2)** — measure before touching: `python3 game_backtest.py` / `engine/lab.py game_lines` on the droplet report the totals record.

## Phase 4 — Is it actually making money? (the main event)

**Profitability is unverified** in this sandbox, for the reasons in
"Read this first". What the local journal copy shows, so nobody mistakes
it for a record: 32 settled `hits` bets (Jul 6 – Aug 25), 21–11, +24.0%
at price — with **no closing price and no stored model probability on
any row**, under the 100-bet floor, and a stale clone. `engine/mlbrecord.py`
prints exactly that and refuses the verdict.

### What is in place so it can be verified — the tool

`engine/mlbrecord.py` (19 pins in `tests/test_mlbrecord.py`, every
number hand-computed on a six-bet, three-parlay fixture):

- Population = the Record page's: `category IN ('main','paper') AND stake_units > 0`, settled. Measurement rows (`longshot`, `longshot_watch`) never enter an ROI; the HR ones are scored for calibration on a separate line marked "NOT money".
- Per population: n first; W–L, pushes; hit rate vs breakeven at the average price; ROI at price; **ROI at the close** (same results, same stakes, the closing price) on the subset with a close, with that subset's price-side ROI printed beside it; mean CLV in implied-probability points and beat share; flat-1u ROI with a 95% interval; max drawdown in units; longest losing streak.
- Breakouts: by market type (HR props / other player props / sides / totals / F5), by market, by month, and by type × month — the decay trend the brief wants first.
- Calibration: Brier and predicted-vs-actual by 10-point bucket for all bets; for HR props in 0–5 / 5–10 / 10–15 / 15–20 / 20+ buckets on money rows and, separately, on the measurement rows.
- Parlays apart from straights, against the journal's own `singles_pnl_units` (the same legs bet flat and separately).
- The verdict line is generated from the numbers and says "profitability is unverified" under 100 bets, flags ROI above 10% as a bug per rule 5, and states whether the flat-ROI interval excludes zero.
- Read-only (immutable connection; the test asserts no write verb in the source).

### The commands (droplet, via Remote Control)

```
cd /srv/qellys
git fetch origin qa/mlb-readiness && git checkout qa/mlb-readiness   # or after merge, the deploy branch
python3 -m engine.mlbrecord                          # the whole 2026 record, month by month
python3 -m engine.mlbrecord --since 2026-08-04       # post-rescale era only (stakes comparable)
python3 -m engine.mlbrecord --json > /tmp/mlbrecord.json
python3 stakecheck.py --sport mlb                    # sizing vs the rules; flat vs actual; edge AUC
python3 -m engine.clvboard                           # CLV by sport × market with coverage
python3 mlb_calibration.py                           # per-market calibration from the DB
python3 hr_backtest.py --seasons 2026                # walk-forward HR long-shot model vs harvested prices
python3 edge_audit.py                                # does claimed edge sort winners from losers
```

Paste the first two outputs back and Phase 8's first line gets its
number.

### Walk-forward backtest

`hr_backtest.py` and `engine/mlb/backtest.py` exist and walk forward on
`history.db` + harvested prices; both need the droplet's history. Their
leak status: the HR backtest prices each date from logs strictly before
it and from `odds_history` rows taken before first pitch (the harvest
stores `taken_at`); lineups in the replay are the *actual* lineups from
the boxscore, which a bettor at 2 pm did not have — so its ROI is an
upper bound on the confirmed-lineup strategy and should be read as such.
Not reported as real here.

## Phase 5 — HR prop model deep dive

Method (`engine/mlb/homeruns.py`, read line by line):

```
base/PA  = w · (own HR per game ÷ 4.0) + (1 − w) · 0.033,  w = min(n/40, 0.5)
× contact : (barrel/0.075)^0.6 · (hard-hit/0.40)^0.4 · xSLG−SLG gap        [Savant, current season, 6 h TTL]
× pitcher : starter power suppression incl. the hitter's own measured platoon split (official splits fallback, shrink 130 PA, ≥60 PA)
× park    : HR factor by batter hand where the park splits (6 parks), else one factor; roof state live
× weather : wind relative to orientation (≥8 mph, +1.2%/mph out), temp ±0.45%/°F from 70, humidity
× lineup  : PA by slot (4.6 → 3.7), certainty 0.85 unconfirmed
λ = base/PA × PA × product, clamped [0.002, 0.50];  P(≥1 HR) = 1 − e^−λ
```

| input the brief lists | fetched | current | referenced in pricing |
|---|---|---|---|
| barrel rate, hard-hit (EV proxy) | ✅ Savant | season-to-date, 6 h | ✅ |
| launch angle | ✗ | — | ✗ (barrel % subsumes it; not a bug, a choice) |
| HR/FB | ✗ | — | ✗ (own HR/game rate used instead) |
| pitcher HR vulnerability + arsenal | ✅ | in-season | ✅ `pitcher_multiplier` |
| handedness matchup | ✅ | measured own split | ✅ |
| park HR factor by hand | ✅ (6 parks) | hand table | ✅ |
| wind direction + temperature | ✅ Open-Meteo | per cycle | ✅ |
| slot + expected PAs | ✅ lineups | per cycle | ✅ |
| **bullpen HR rates for late innings** | ✗ | — | ✗ — `bullpen.py` is a *fatigue* nudge on hitter markets, not a HR-rate input. **F-5.1 (P2 gap)** |

Conversion: per-PA → per-game through λ = rate × PA and 1 − e^−λ, not
λ·PA as a probability. ✅ (pinned).

Sanity bounds: P(≥1) ≤ 39.3% by the λ clamp; the long-shot board floors
at 12% model probability and windows prices to +250 … +650; a hitter
not in the posted lineup is held (rules) and, on the HR board, carries
the "lineups post around H:MM" caveat with certainty 0.85. A light-hitting
middle infielder's own rate (say 0.02 HR/game → 0.5%/PA) gets at most
weight 0.5 against the league 3.3%, so he cannot be projected like a
slugger, and a call-up with 12 games gets 0.3 weight on his own rate.
✅ September call-ups are regressed; they are not *flagged* (F-2.13).

Market comparison for tonight's slate: **could not run here** (no
schedule, no prices). On the droplet the board itself is that list;
`hr_diagnose.py` prints the ten largest edges with the multiplier chain
for each.

Calibration on 2026 HR data: `python3 -m engine.mlbrecord` prints the
5–10 and 10–15 buckets on money rows and on the measurement rows;
`hr_backtest.py --seasons 2026` prints the walk-forward version. A
model that says 12% and hits 8% shows there as "said 12.0% hit 8.0%".

Parlay interaction: two HR props from one lineup — the engine refuses
to build the ticket (EXTREME); the slip allows it with the +0.19
warning and the "correlation is not priced here" line (F-2.7). HR +
game over — allowed at a +0.10 prior, unmeasured (F-2.6).

## Phase 6 — Postseason readiness

Nothing in the instruction set or the code addresses the postseason.
`grep -ri "postseason|playoff|wild card|short rest"` over `engine/mlb`,
`mlb_build.py` and `docs/MLB_MODEL.md` returns one park comment. Point
by point:

- Rotation and bullpen usage: the K/outs projection assumes a regular-season leash (`bullpen.leash_factor`, `tto_proj`); aces on short rest, starters in relief and high-leverage arms pitching daily are unmodelled. Pitcher props in October are priced on assumptions that do not hold.
- Opponent quality compression: the hitter/pitcher multipliers are relative to league averages, not to a playoff field; ratings for sides/totals are season-wide.
- Layoffs and travel: no rest/fatigue input for MLB (the doc's §7 travel engine is 📋 parked).
- Optimised lineups / aggressive platoons: lineup confirmation still gates, so props wait for the card — that part holds.
- Market sharpness: the haircut (`temper_edge`, `TIER_SHRINK`) is a constant per tier, not a function of market regime; nothing tightens it in October.

This is not a bug to fix by guessing. **Ask Ethan (A-1)** with a
recommendation below.

## Phase 7 — Fix and re-verify

One defect per commit on `qa/mlb-readiness`; the full suite
(`python3 run_tests.py`) is the gate for every commit.

| commit | what was wrong |
|---|---|
| `fix(mlb): the refusal named the wrong cause …` | F-2.2 — `engine/mlb/betting.py` split into the two truthful sentences shared with the NFL board; pinned in `tests/test_refusals.py` |
| `feat(mlb): the record tool the readiness audit needs` | `engine/mlbrecord.py` + 19 pins |
| `test(mlb): Phase 3 arithmetic checked by hand` | `tests/test_mlb_readiness_math.py`, 28 pins |
| `docs(mlb): the map said handedness park splits were parked` | F-2.4 |
| `docs(mlb): the readiness audit log` | this file |

No threshold or weight was changed (rule 2). Nothing was removed
(rule 1). No number in this file was estimated.

### Ask Ethan

- **A-1 Postseason.** Recommendation: **do not bet MLB player props or parlays in the postseason with this model**, and do not bet sides/totals in October unless `mlbrecord` shows a positive CLV on ≥100 settled game bets. The pitching engine's usage assumptions are the ones that break, and pitcher grade is 15% of every MLB grade.
- **A-2 September.** Keep betting? The lineup hold and the shrinkage handle call-ups mechanically, but nothing flags an eliminated team's bulk-relief games or a contender resting regulars. Options: (a) keep as is; (b) add a September flag that lowers lineup certainty for hitters with under 30 MLB PA this season and refuses K props on bulk-relief starts. (b) is a rule addition with a number in it — your call.
- **A-3 HR parlays on the slip.** The slip shows the independent price and says correlation is not priced. Options: (a) leave as disclosed; (b) show the modeled joint (the taxonomy already has ρ) beside the naive price; (c) refuse two HR legs from one lineup on the slip the way the engine refuses them. Ethan bets these — this is his decision.
- **A-4 PA tables.** Reconcile `homeruns.PA_BY_SPOT` to one table, and add a home/away term? It is a parameter change; the measurement route is `hr_backtest.py --seasons 2026` run twice on the droplet (once per table) and reported before-and-after on the holdout. Say yes and that measurement runs first.
- **A-5 Drawdown rule.** None exists. Add one (e.g. halve stakes after a 15u drawdown from peak until recovered)? A money rule with a number in it — not guessed here.
- **A-6 Game totals distribution.** Normal today. Measure on the droplet's totals record before any change.

## Phase 8 — Go / no-go

**Is this model profitable on its 2026 record?** **Unverified** — this
sandbox holds no scorable 2026 record (0 closes, 0 stored probabilities,
32 stale rows). The tool that answers it ships in this branch; the
answer is one droplet command away (Phase 4). Fill in from
`python3 -m engine.mlbrecord`: n = ___, ROI at price ___, ROI at close
___ on ___ closes, mean CLV ___ pts, beat share ___.

**Month-by-month trend:** unverified here — the same command prints it;
if July–August are negative after a positive April–June, that line is
the top of this report.

**GO / NO-GO for tonight's slate: NO-GO on the money verdict, GO on
the mechanics.** The single biggest reason: a record nobody has scored
is not an edge, and this audit could not score it. The mechanics that
gate a card — lineup hold, probable-starter certainty, per-park weather,
tonight's umpire, market-sum HR devig, 3-leg cap, exposure caps, the
refusal wording (fixed) — are correct by code and by 47 hand pins.

**P0:** none found. **P1:** F-2.12 (no postseason rule — Ask Ethan A-1).
**P2 fixed:** F-2.2 (refusal cause). **P2 open:** F-1.1 scratched-starter
journal rows, F-1.2/F-2.13 September, F-1.3 bullpen availability, F-2.1
learned-model dominance is silent, F-2.3 PA tables, F-2.6 unmeasured
HR pair priors, F-2.7 slip prices HR parlays as independent (disclosed),
F-2.8 no drawdown rule, F-2.11 matchup share of the clamp, F-3.1 normal
totals, F-5.1 no bullpen HR input. **P3:** F-2.4 (doc fixed), F-2.5 raw
CLV points, F-2.9, F-2.10.

**HR prop model:** method correct (per-PA → Poisson), inputs current
where reachable, one listed input missing (bullpen HR rates), sanity
bounds present, September call-ups regressed not flagged. Calibration:
unverified here; the 5–10 / 10–15 buckets print from the record tool.

**Parlays:** engine tickets never contain HR legs; same-lineup HR pairs
carry a measured +0.186 (on TB outcomes); HR + total and HR + K-under
are unmeasured +0.10 priors; the slip discloses rather than prices
correlation. Correlation is priced *where the engine bets* and
*disclosed where a person bets*. Parlay ROI vs the same legs as singles:
unverified here; `mlbrecord` prints both.

**Postseason:** not ready — no rule exists; recommendation A-1.

**Could not test, and what it takes:** tonight's card and render (needs
statsapi + Open-Meteo + Savant + an Odds API key, i.e. the droplet);
the 2026 record and calibration (the droplet's ledger); the ten largest
HR edges tonight (`hr_diagnose.py` on the droplet); the HR walk-forward
(`hr_backtest.py` on the droplet).

**Confident because I ran it:** the 47 arithmetic and record pins in
`tests/test_mlb_readiness_math.py` and `tests/test_mlbrecord.py`; the
refusal fix; the build's failure behaviour off-network; the relate /
check_ticket verdicts for every HR pairing in Phase 2. **Assuming:**
that the droplet's journal carries closes on most MLB bets (the harvest
has run nightly since August); that the site's MLB cards render the
`quality` field the tests pin.
