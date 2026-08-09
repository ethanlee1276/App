# §5's pitch-level feed — scoped, 2026-08-09

**Status: scope only. Nothing built. The headline is that three of the four
parked items do not need the feed the doc says they need.**

MLB_MODEL §5's implementation row reads:

> Stuff+/Location+, velocity trend, TTO, pitch-count projection 📋
> (need pitch-level feed — **the best next build**)

That note bundles four things with very different costs, and points at
Baseball Savant when most of them are already reachable through an
endpoint this repo has the adapter for and has simply never called.

---

## 1. What is already wired

`engine/mlb/sources/savant.py` pulls Savant **leaderboard CSVs** — one row
per player per season: expected stats (xSLG/xwOBA vs actual), barrels,
hard-hit, and pitcher CSW%. `engine/mlb/statcast.py` turns those into a
bounded multiplier.

Those are *season aggregates*. Nothing in the repo reads a single pitch.

## 2. What each parked item actually needs

| item | needs | where it comes from | cost |
|---|---|---|---|
| velocity trend, start over start | per-start average velo | **statsapi playByPlay** | small |
| TTO (times through order) | batter sequence within a game | **statsapi playByPlay** | small |
| pitch-count projection | pitches thrown per start | **statsapi boxscore** | already fetched |
| Stuff+ / Location+ | a pitch-quality MODEL | nowhere — see §4 | large |

**The endpoint that changes the picture** is
`https://statsapi.mlb.com/api/v1/game/{gamePk}/playByPlay`. It is free, key-less,
the same host `mlbstats.py` and `statslogs.py` already use, and its
`allPlays[].playEvents[].pitchData` carries per pitch:

    startSpeed, endSpeed, extension, plateTime
    coordinates (pX, pZ), zone, strikeZoneTop/Bottom
    breaks (spinRate, spinDirection, breakAngle, breakLength)
    details.type  — the pitch type

That is tracking data, per pitch, for free. The repo hits `/boxscore`,
`/linescore`, `/people`, `/schedule` and `/transactions` on that host and
has never called `/playByPlay`.

## 3. The size question, and why it is smaller than it looks

The instinct is a season bulk load: ~2,430 games, roughly 700k pitches,
and playByPlay JSON is verbose — call it single-digit GB raw. That is a
real ingest project.

**§5 does not ask for it.** Its own words:

> read the trend over the last 3–5 starts, not the season number

So the live requirement is the last 3–5 starts of tonight's probable
starters — about 10–12 pitchers a night, five games each, most of them
already cached from previous nights. Fifty-odd cached fetches per night,
falling to a handful once the cache warms.

A backfill for calibration is optional and separable: it only needs the
starts belonging to pitchers we have actually bet, which the journal
names.

> **Not measured.** Savant and statsapi are both blocked from the sandbox
> this was scoped in (403 at the proxy), so every size here is an
> estimate. Measure before building:
>
>     curl -s "https://statsapi.mlb.com/api/v1/game/775296/playByPlay" | wc -c
>     curl -s "https://statsapi.mlb.com/api/v1/game/775296/playByPlay" \
>       | python3 -c "import json,sys; d=json.load(sys.stdin); \
>         print(sum(len(p.get('playEvents') or []) for p in d.get('allPlays') or []), 'events')"

## 4. Stuff+ is not a feed, it is a model

This is the part the doc's note hides. **Stuff+ and Location+ are
proprietary FanGraphs metrics** (Eno Sarris's models). Savant does not
publish them and neither does statsapi. Getting them means either
scraping FanGraphs — no free API, and terms that do not invite it — or
building our own pitch-quality model: predict run value from velocity,
movement, spin, release point and location, fit over hundreds of
thousands of pitches.

That is a research project measured in weeks, and it is the one item here
that genuinely needs the bulk history. It is also the item most likely to
reproduce what the market already knows, which matters — see §6.

**Recommendation: park Stuff+ explicitly, and correct the doc row.** The
current wording implies one feed unlocks all four, which is why it reads
as "the best next build".

## 5. What is worth building, in order

1. **A playByPlay adapter** (`engine/mlb/sources/pbp.py`), cached exactly
   like `fetch_boxscore`, with a parser that is pure and unit-tested. One
   endpoint, one cache key, no new host.
2. **Velocity trend** — average `startSpeed` per start, by pitch type,
   for the last five starts. §5 calls a 1+ mph drop a red flag; that is
   directly checkable and needs nothing else.
3. **TTO** — batter-sequence position within the game, which the same
   payload gives for free.
4. **Pitch-count projection** — from boxscore `pitchesThrown`, which is
   already being fetched today and thrown away.

Steps 2–4 are days, not weeks, and none of them touches a new data
provider or costs a credit.

## 6. The condition on all of it

`docs/THE_INFORMATION_TEST.md`, measured 2026-08-09: the model's ranking
of its own bets and the market's ranking of the same bets differ by
**+0.004 AUC**, and the claimed edge cannot be told apart from a coin
flip. Every feature added to the pricing path feeds `edge`, and `edge`
currently carries no information.

So each of these lands as **evidence first, priced never by default**.
The question each must answer before it touches a grade is the one
`stakecheck --info` asks: does adding it move the claimed edge's AUC off
0.5? A velocity-trend flag that does not is another input reproducing
what the price already knows, which is the diagnosis this model already
has.

Velocity trend is the most promising of the three precisely because it is
closest to *information* rather than *processing*: a pitcher who lost
1.5 mph in his last start is a fact about the world that a book may or
may not have priced, rather than a rearrangement of public season stats.
