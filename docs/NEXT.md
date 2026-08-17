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

## 2. Smaller, known, not urgent

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
