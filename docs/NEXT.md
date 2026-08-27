# What to do next

Written 2026-08-16, at the end of the session that took the site live.
Updated 2026-08-17, when the props build was fixed and the measurement it
rested on turned out to be wrong.
Ethan should not have to carry any of this in his head — a new session
reads this file and picks up the top item.

---

## 1. Before charging anyone (not code — Ethan's calls)

* A Paddle account, and a real test webhook sent through it. The signature
  verifier in `engine/paddle.py` was written from memory with the API
  unreachable from the dev container, and it is flagged UNVERIFIED in the
  file. It is the one place where being wrong is silent AND dangerous.
* The LLC and a business bank account.
* Phase 0 in `docs/LAUNCH.md`: commercial-use terms for ~25 data feeds,
  and the Michigan/MGCB question. These gate charging money, not shipping
  code.

The paywall itself is BUILT AND SWITCHED OFF. `QB_PAYWALL` unset means
boards publish whole and the site behaves exactly as it does today. Put
Ethan's address in `QB_COMP_EMAILS` in `/etc/qellys/env` BEFORE ever
setting `QB_PAYWALL=1`, or the first thing the paywall does is lock him
out of his own board.

---

## NFL Week 1 dress rehearsal — run 2026-08-26, board healthy

Ahead of the Sep 10 opener, `nfl_build.py 2026 1 --carry` was run
end-to-end on this box against the ingested 2025 season. What came out:

* 16 games, 64 game bets, 285 props analysed, 283 players with stat
  histories attached, drive sim replayed, 32 team shapes ranked;
* every board section present (`game_bets`, `player_stats`,
  `team_recent`, `incentives`, `playoff_picture`, `parlays`,
  `correlation`, `market_scan`, `injury_status`, `odds_status`);
* the gate census — new the same day — correctly attributed all 285
  deaths to "no real book price yet", broken out per market, because
  the rehearsal ran WITHOUT `--odds` and therefore spent no credits;
* long shots empty, which is correct with no odds: a scorer market has
  no proxy price by design.

So the player layer, the carry, the TD histories and the whole payload
shape are ready. The only thing the rehearsal could not exercise is
real book prices, which the launcher supplies.

ONE DEFECT FOUND, by looking at the render rather than the JSON: the
census's unpriced note read "we project every hitter in the lineup" on
the NFL board — the wrong sport's noun in the one panel whose whole job
is explaining an empty board honestly. Fixed and pinned.

---

## The NFL weather feed — CLOSED 2026-08-27

Found 2026-08-26: the NFL's weather came from the nflverse schedule's
`temp` and `wind`, which nflverse fills from the game's OWN box score —
so every outdoor game on a forward board was blank and took the engine's
mild-day prior of 60°F and 6 mph, printed as a forecast. The honest half
shipped that day (`Weather.measured`, and every surface checking it).

**The feed is in now** (`engine/nflwx.py`). It is deliberately the same
machine college has run since 2026-08-24: `engine/cfb/wx`'s
`fetch_forecast`, `pick_hour` and `compass` take a latitude, a
longitude, a date and a kickoff instant, none of which is
college-shaped. What the NFL was missing was the two things college gets
from its own feeds — where the stadium is, and when the ball is kicked.
`engine/fatigue.kickoff_instant` supplied the second (written for
capture lag; this is its second reader).

**The coordinates are checked rather than trusted**, which was the whole
reason this waited a day. `engine/stadiums.STADIUM_COORDS` is pinned
against two tables this repo already runs on: twenty-four of the thirty-
two stadiums share a city with a major-league ballpark whose coordinates
have been fetching weather all season, and each must sit within 65km of
it (the shared complexes come out under two kilometres); the other eight
are pinned against `engine/fatigue.TEAM_UTC_OFFSET_FROM_ET`, since a
longitude and a time zone that disagree are the same typo seen from the
other side. Arizona is the one documented exception and the test says
why.

**This container cannot see it work and that is expected**: its egress
policy blocks both Open-Meteo hosts, so a build here stamps the five
domes and leaves eleven outdoor games saying "not pulled" — which is the
correct behaviour for a machine that cannot reach the service. The
droplet reaches it every day for college.

---

## 2. Smaller, known, not urgent

* Player photos are missing for MLB / NFL / NBA — faces are captured
  during ingest, so a re-read picks them up. Cosmetic; cards show
  initials. `python3 launch.py --todo` reports which leagues still have
  none and prints the ingest command for each.
* `launch.py --check` reports unregistered knowledge-tier openings. The
  barrel-rate half is registered now (`elite barrel rate`, `low barrel
  rate` — the percentage rides in the opening, so the prefix stops before
  it). The umpire strings are NOT, and cannot be honestly added from
  here: the exact openings only exist on a board with a live slate, and
  guessing at them would register prefixes that match nothing while the
  real strings stay unlabelled. Re-run `--check` on the laptop with a
  live board and paste the list.
* ~~`deploy.sh` runs the full suite on the production droplet.~~ DONE —
  the normal deploy is `--no-tests`, gated on the GitHub Actions tick,
  and deploy.sh says so in its own header. Worth knowing: the suite is
  now ~an hour on that box, and `tests/test_isotonic.py` alone is 5m17s
  (two 30,000-sample fits). That is a real cost if the gate ever moves
  back onto the droplet.
* Two service stop/start pairs on 2026-08-16 at 16:15 and 16:33 were never
  explained. If they recur, find out what is restarting the live site.

### Three found while fixing the props build — ALL FIXED 2026-08-20

They sat here for three days. Written down is not fixed, and a document
is a worse place to keep a defect than a failing test, so each one now
has one. `tests/test_cacheclass.py`.

* **A rate-limited board published EMPTY and reported success.** FIXED.
  `_get_json` turned a 429 into `DataUnavailable`, `_add_prop` caught it
  and returned, and `build_live_slate` handed back its games with zero
  props — reproduced with every game log answering 429: 15 games, 0
  props, no exception, and `launch.py` logging a healthy build. A refusal
  is not an absence. The status is kept now (`REFUSAL_STATUSES` — 429 and
  the 5xx family), and a board that is EMPTY *and* was refused raises
  instead of publishing. A 404 still reads as an ordinary absent player,
  which is the half that stops this becoming "raise on any error", and a
  board that lost three props out of two hundred still publishes.

* **`lineupwatch.py` wrote another module's cache file.** FIXED. It
  fetched the schedule without `&hydrate=probablePitcher,venue` and
  stored it as `mlb_schedule_{date}.json` — the exact name the builder
  reads, from a different URL, and `_get_json` keys on the filename and
  never compares URLs. Any build inside that 600s TTL got an unhydrated
  payload: no probable pitchers, so no pitcher props at all, and
  `park="generic"` everywhere. It now writes `mlb_watchsched_{date}.json`.

* **`mlb_pbp_` was missing from `PRUNABLE_CACHE_PREFIXES`.** FIXED, and
  the audit found far more than the one name. `wnba_box_` was missing
  while `nba_box_` was present; every Polymarket prefix, Rocket Radar's
  per-mint holder files, `espn_cfb_` and the MMA caches were all absent.
  ~640 KB per play-by-play payload and ~150 starters a night is ~96 MB a
  night that nothing would ever have deleted.

  **The generalisation is the actual fix.** A list somebody must remember
  to extend is the same failure as a cache version somebody must remember
  to bump. Every cache filename in the source must now be classified as
  prunable or explicitly kept WITH A REASON, and
  `test_every_cache_name_is_classified` fails the suite otherwise — it
  caught two more (`espn_cfb_`, `injuries_`) on its first run, after a
  by-hand audit had already been over the same ground. The keep list
  earns its exemptions: `odds_*` costs paid API credits to refetch, and
  the nflverse `pbp_*` / `player_stats_*` / `depth_charts_*` files are
  per-SEASON bulk (~100 MB each) that is bounded rather than per-game.

---

## Done

**MLB props were 8–15 minutes stale** — fixed 2026-08-17, in two halves.
Reproducing the whole build against a fake wire at the droplet's own
measured latency, which is how each half was checked:

```
                     BEFORE     pooled     + sim
build_live_slate     277.0s      35.7s      35.7s
run_mlb_slate        180.9s     123.6s      53.5s
                     ------     ------     ------
TOTAL                457.9s     159.3s     100.1s
```

The BEFORE column is 457.9s against the 459.5s actually measured on the
droplet, so the model is trustworthy. Both halves keep the board
byte-identical — same 870 props in the same order, same 601 requests.

**Correct the record on one thing: `user 0m0.007s` in the original
write-up was a bad measurement.** It sent that investigation looking only
at the network and led it to predict that pooling the game logs alone
would take the build under a minute. In fact 113 of the 458 seconds were
CPU, which no pool touches — the waiting half and the computing half both
had to be dealt with.

*The waiting half.* A cold build made 751 HTTP requests one at a time;
they are independent, so `build_live_slate` and the pitcher play-by-play
pass now warm their caches through a capped thread pool, and every
sequential pass behind them reads from disk unchanged.

*The computing half.* All of it was `gamesim.simulate_lineup` — 210 runs
per board, six of them per lineup just to fit the rates. The trial loop was
recomputing constants: `_key(line)` is an f-string over a number that never
changes, called 107M times, and `_pair_key` 46M more. Those and the
canonical pair keys are computed once now, the loop counts into flat lists
indexed by leg, and the per-trial rate-table rebuild is unrolled. 2.2x, and
the sim is seeded so it had to be — and is — bit-identical.

**The real ceiling is `launch.py:51`**, which runs every build with
`timeout=180` and swallows the `TimeoutExpired`. At 458s the build was
being KILLED every cycle and the board only republished when a later run
happened to get through; that explains "8–15 minutes stale" far better
than slowness alone. At 100s there is now real margin on a 2-core droplet
that is also serving the site.

**CLOSED ON THE LIVE BOX, 2026-08-17 21:03 UTC**, after two more finds
the fake-wire model could not see:

* the service still carried `MemoryMax=900M` from the 1GB droplet on the
  resized 2GB box — a cgroup riding its ceiling is not killed, it is
  reclaimed into swap, and the measured 826M/900M throttle is part of why
  even 100s-shaped builds were blowing through 180s in production;
* the guillotine itself: refresh_mlb now passes `timeout=600`, the
  default 180 stays for the fast loops, and `_run_build` prints EVERY
  kill and failure into the journal — the three silent hours were more
  expensive than the wrong number.

Verified by the check that had failed all day: consecutive board writes
at 20:55:40 and 21:03:24 — an ~8-minute publish cycle under live-site
load, down from frozen. If anyone wants that smaller, the lever is the
sim or more cores, not the fetch layer.

Three things a future edit here needs to know:

* **The warm passes are removable by construction, and must stay that way.**
  They fetch and discard; the real calls still happen where they always
  did. A draft that consumed the pooled `projected_lineup` answer instead
  would have deleted a whole team's hitters on any morning before lineups
  post, because `fetch_many` turns a fault into `None`.
  `test_the_same_holds_on_a_morning_with_no_lineups_posted` fails on that
  draft and passes on this one.
* **The per-cache-file dedup is load-bearing.** 870 game-log calls collapse
  to 300 requests only because `_get_json` checks the file's mtime. A pool
  that let three markets miss the same file at once would TRIPLE the
  request count, so `fetch_many` collapses repeated arguments itself.
* **A warm pass must not ask for more than the build needs.** Warming the
  probable starters off the schedule looks free and is not: a doubleheader
  is two legs in that payload and only one gets priced, so it bought two
  game-log requests for a game nobody looks at. The starters are warmed
  after the doubleheader bookkeeping instead, and a test counts it.
* **The sim's numbers are pinned by a golden digest**
  (`tests/test_gamesim_exact.py`). It was taken from the sim BEFORE the
  loop was reworked and the rework reproduced it exactly, which is the only
  reason that change was safe to make. Speed work on a seeded sampler is
  not allowed to move a number, and the digest is how you show it did not.
  Note that a Python release changing `random.gauss` would fail it too —
  that is intended, because it would move every published price.
* **`QB_MLB_WORKERS=1`** restores the old strictly-sequential behaviour —
  the first thing to try if MLB ever starts refusing us. It is clamped to
  1..16.

Verify with the command that found it:

```
$ time python3 mlb_build.py <date> --cached-odds --out /tmp/x.json
```
