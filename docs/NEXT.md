# What to do next

Written 2026-08-16, at the end of the session that took the site live.
Ethan should not have to carry any of this in his head — a new session
reads this file and picks up the top item.

---

## 1. MLB props are 8–15 minutes stale (the live scores are already fixed)

**Symptom.** Prop lines on the MLB board lag by 8–15 minutes. Live SCORES
were fixed on 2026-08-16 (`live_build.py`, commit 92af099) and now update
in seconds; this is the remaining half.

**Measured, on the production droplet:**

```
$ time python3 mlb_build.py 2026-08-16 --cached-odds --out /tmp/x.json
real    7m39.450s
user    0m0.007s
sys     0m0.013s
```

**Read those three numbers together.** Seven and a half minutes of wall
clock against effectively ZERO CPU. The build is not computing, it is
waiting — and that is what rules out every hardware answer. The droplet
was resized from 1 to 2 cores during this session and it changed nothing,
because cores are not the constraint.

**Cause.** `engine/mlb/sources/statslogs.py:183` fetches one HTTP request
per player for game logs:

```python
return _get_json(url, f"mlb_log_{group}_{person_id}_{season}.json", ttl=1800)
```

Called once per player, sequentially, from `build_live_slate`. Roughly 15
games x ~20 players is ~300 requests at a couple of seconds each, which is
the 7m39s almost exactly.

**Fix.** Thread-pool those fetches. They are independent of one another,
so this is concurrency rather than optimisation — nothing about the model
or the maths changes. A pool of 8–16 should take the build under a minute.

**Two hazards, both worse than slow props, so do not skip them:**

* `_get_json` WRITES CACHE FILES. Concurrent writes to the same path
  corrupt them, and a corrupt cache is a wrong number rather than a slow
  one. Write to a temp file and rename, or lock per path.
* The MLB Stats API rate-limits. Three hundred simultaneous requests is a
  good way to get the server's IP blocked mid-season. Cap the pool and
  keep the 30-minute TTL doing its job.

**Verify with the same command that found it** — the `real` time is the
whole test, and it should be under a minute.

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
