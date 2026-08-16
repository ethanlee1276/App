# What to do next

Written 2026-08-16, at the end of the session that took the site live.
Updated 2026-08-17, when the props build was fixed and the measurement it
rested on turned out to be wrong.
Ethan should not have to carry any of this in his head — a new session
reads this file and picks up the top item.

---

## 1. The MLB board is now CPU-bound, and the margin is thin

The 7m39s props build is fixed (see Done, below) — but only the waiting
half of it was ever network. Reproducing the whole build against a fake
wire at the droplet's own measured latency:

```
                        BEFORE            AFTER
build_live_slate        277.0s            35.7s     601 requests, both
run_mlb_slate           180.9s           123.6s     150 requests, both
                        ------            -----
TOTAL                   457.9s           159.3s
```

The BEFORE number is 457.9s against the 459.5s actually measured on the
droplet, so the model is trustworthy. What it shows is that **115 of those
159 remaining seconds are CPU** — and no amount of concurrency touches
them.

**So correct the record: "user 0m0.007s" in the original write-up was a bad
measurement.** It is what sent that investigation looking only at the
network, and it is why the note said pooling the game logs alone would take
the build under a minute. It would not have. Under a minute is not
available at all while the sim costs two minutes.

**Why it still matters that this is tight.** `launch.py:51` runs every
build with `timeout=180` and `launch.py:52` swallows the `TimeoutExpired`.
At 458s the build was being KILLED every cycle — which is the real reason
the board sat 8–15 minutes behind, rather than slowness alone. At 159s it
completes, but with ~20s of margin, on a 2-core droplet that is also
serving the live site. A slate bigger than 15 games eats that margin.

**Where the time goes.** Profiled: it is all
`engine/mlb/gamesim.simulate_lineup` (210 calls) under
`simjoint.build`, and `gamesim.calibrate` is about half of it. The two
hottest lines are `gamesim._key` (107M calls) and `gamesim._pair_key`
(46M calls) — pure-Python helpers called from inside the Monte Carlo
loop, which is exactly the shape that precomputing or memoising fixes.
Start there before touching the sim's statistics.

---

## 2. Before charging anyone (not code — Ethan's calls)

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

## 3. Smaller, known, not urgent

* Player photos are missing for MLB / NFL / NBA — faces are captured
  during ingest, so a re-read picks them up. Cosmetic; cards show initials.
* `launch.py --check` reports ~19 unregistered knowledge-tier openings
  (umpire and barrel-rate strings). Add them to `engine/knowledge.py`
  PREFIXES.
* `deploy.sh` runs the full 4,550-test suite on the production droplet,
  which takes ~15 minutes and competes with the live app for CPU. The gate
  is right; the venue is wrong. CI or the Mac is the better place, with a
  fast smoke check on the box.
* Two service stop/start pairs on 2026-08-16 at 16:15 and 16:33 were never
  explained. If they recur, find out what is restarting the live site.

### Three found while fixing the props build, none of them its cause

* **A rate-limited board publishes EMPTY and reports success.** `_get_json`
  turns a 429 into `DataUnavailable`, `_add_prop` catches that and returns,
  and `build_live_slate` hands back its games with zero props. Reproduced:
  every game log answering 429 gives 15 games, 0 props, no exception —
  and `launch.py` logs a successful build. The pool now stands down on the
  first 429 rather than piling on, but nothing yet makes the *build* say
  it was refused. This is the one on this list that can be silently wrong.
* **`lineupwatch.py:99` writes another module's cache file.** It fetches
  `{STATS_BASE}/schedule?sportId=1&startDate=…&endDate=…` and caches it as
  `mlb_schedule_{date}.json` — the same filename `build_live_slate` reads,
  from a URL with no `&hydrate=probablePitcher,venue`. `_get_json` keys on
  the filename and never compares URLs, so a build inside that 600s TTL
  gets an unhydrated payload: no probable pitchers, so no pitcher props at
  all, and `park="generic"` everywhere. It is not wired into `launch.py`,
  so this needs someone to run `lineupwatch.py` by hand to fire — but the
  fix is a distinct `cache_name` and costs nothing.
* **`mlb_pbp_` is missing from `PRUNABLE_CACHE_PREFIXES`**
  (`engine/maintenance.py:208`). Play-by-play payloads are ~640 KB each and
  a night's starters are ~150 of them, so the cache grows ~96 MB a night
  and `prune_cache` never touches it. Every other MLB prefix is in the
  list; this one was just missed.

---

## Done

**MLB props were 8–15 minutes stale** — the waiting half fixed 2026-08-17.
A cold build made 751 HTTP requests one at a time; they are independent, so
`build_live_slate` and the pitcher play-by-play pass now warm their caches
through a capped thread pool and every sequential pass behind them reads
from disk unchanged. 277.0s → 35.7s on the slate build, 457.9s → 159.3s
overall, with a byte-identical board (same 870 props, same order, same
digest) and the same 601 requests — no amplification.

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
* **`QB_MLB_WORKERS=1`** restores the old strictly-sequential behaviour —
  the first thing to try if MLB ever starts refusing us. It is clamped to
  1..16.

Verify with the command that found it:

```
$ time python3 mlb_build.py <date> --cached-odds --out /tmp/x.json
```
