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

> **Measured 2026-08-09: 656,647 bytes for one game** — about 640 KB,
> smaller than the 1–3 MB this section first estimated. A full season is
> therefore ~1.5 GB raw and the nightly window ~32 MB before caching.
>
> Savant and statsapi are both blocked from the sandbox this was scoped
> in (403 at the proxy), so the remaining figures are still estimates.
> Re-measure with:
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

1. ~~**A playByPlay adapter**~~ — **built 2026-08-09**.
   `engine/mlb/sources/pbp.py`: cached fetch plus pure parsers for
   pitches, per-pitcher counts, velocity by pitch type, and times through
   the order. 9 tests.

   **Its fixture is a READ of the payload, not a capture of one** — the
   sandbox cannot reach statsapi — so the parsers are proven
   self-consistent and unproven against reality. `python3 launch.py --pbp
   <gamePk>` closes that gap on a machine with network, and says so
   loudly if zero pitches parse.
2. ~~**Velocity trend**~~ — **built 2026-08-09**. `engine/mlb/velocity.py`,
   10 tests. Last five STARTS (relievers excluded by `gamesStarted`),
   compared within a pitch type, against his own baseline, with a
   10-pitch floor per start and a signed 1.0 mph threshold.
   `python3 launch.py --velo <personId>` prints the starts and EVERY
   pitch type, not just the verdict.

   Both of those came from running it on a real pitcher. Cole's four-seam
   and slider each appeared in all five starts, so the primary-pitch
   tiebreak fell through to sorting — "SL" beats "FF" — and it judged a
   fastball pitcher on his slider. Ranked by volume now. And a single
   verdict reported "SL within 0.8 mph" while his changeup went 87.64,
   86.48, 86.26, 85.09 and then vanished from the latest start: a 2.5 mph
   slide and a shelved pitch, both invisible. `trend_all` reports every
   type and names a pitch that disappeared.
3. ~~**TTO**~~ — **built 2026-08-09**. Journaled as `tto_proj`, banded
   around §5's third-time-through penalty, in `DIMS` so the lab can
   propose on it and in `bleed` so the report that tests can slice it.

   **It is a PROJECTION, and that is the whole design.** Times through
   the order is a within-game quantity and the bet is placed before any
   of it exists, so what lands on the row is how deep he has BEEN going.
   Journaling tonight's actual depth would be journaling the future — the
   miner would convict on information the pick never had, and any gate
   built on it would be reading tomorrow's newspaper.
4. **Pitch-count projection** — **parked, deliberately.** The raw counts
   are parsed and reach the probe. Going further means feeding the outs
   projection, which is a PRICING change, and §6 below is why that waits.
   As a mining dimension it would restate `tto` almost exactly — how deep
   he goes and how many pitches he throws are close to one fact, and the
   miner would spend its multiple-testing budget convicting the same
   pocket twice.

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


---

## 7. §6's arsenal matchup — the two halves cost very differently

Added 2026-08-10, because "needs pitch-mix + per-pitch-type hitter data"
hid two costs that are nothing like each other.

**The pitcher half is free.** `velocity.py` already loads a starter's last
five playByPlay payloads to read his velocity, and every pitch in them
carries `details.type.code` and `details.call.code`. So mix share by type,
whiff rate by type, and mix SHIFT against his own baseline are a second
parse of games the board already fetched. `engine/mlb/arsenal.py`,
`launch.py --arsenal <personId>`. No new feed, no new request, no credit.

Two decisions inside it worth keeping:

- **Whiff is per SWING, not per pitch.** A pitch nobody offers at is a
  ball. Dividing by every pitch measures how often he is in the zone
  rather than how hard the pitch is to hit.
- **A foul tip is contact.** Counting `T` as a miss would inflate every
  splitter in the league.

**The hitter half is the expensive one**, and the two routes are:

| route | cost | status |
|---|---|---|
| Savant pitch-arsenal BATTER leaderboard | one CSV per season | **unverified** — the sandbox cannot reach Savant (403 at the proxy). `engine/mlb/sources/savant.py` already fetches sibling leaderboards through the same host, so the adapter would be a small addition. Probe it on the laptop first. |
| playByPlay, whole season | ~1.5 GB, ~2,430 games | works, and is a real ingest project |

The reason it cannot ride tonight's fetches: a batter's whiff rate against
sliders needs HIS season, not his opponent's five starts. That asymmetry is
the whole difference between the two halves.

**RESOLVED 2026-08-10 — the cheap path exists.** Ethan ran the curl and it
returned:

    "last_name, first_name","player_id","team_name_alt","pitch_type",
    "pitch_name","run_value_per_100","run_value","pitches","pitch_usage",
    "pa","ba","slg","woba","whiff_percent","k_percent","put_away",
    "est_ba","est_slg","est_woba","hard_hit_percent"

One row per hitter per pitch type, with whiff%, wOBA, xwOBA and hard-hit%.
`savant.load_arsenal(year, "batter")` reads it; `arsenal.matchup` combines
it with the pitcher's mix; `launch.py --matchup <personId> "<Batter>"`.
**§6 is complete as a probe** — both halves free, neither priced.

The one design note worth keeping: this is the only Savant board here with
SEVERAL rows per person, so the parser keys by (player, pitch_type).
Parsing it like its neighbours would silently keep whichever pitch type
came last.

The original recommendation follows, kept because the method was the
point — one `curl` settled a row that had been parked for months:

    curl -s "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=batter&pitchType=ALL&year=2025&csv=true" | head -1

If that returns a header row with a pitch-type column, the hitter half is a
day's work. If it 404s, it is the 1.5 GB route or nothing, and the platoon
engine stays the proxy — which is a fine answer, and better than a matchup
built on three sliders.
