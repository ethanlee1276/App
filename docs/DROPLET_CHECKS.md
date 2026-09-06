# Droplet checks waiting on Ethan

Commands to run on the live box (`/srv/qellys`), each answering a
question this repo cannot answer from anywhere else. Every one of them
is READ-ONLY, writes nothing outside `/tmp` unless it says so, and
leaves no untracked file behind — `cfbcheck.py` sat in the working tree
long enough to make `deploy.sh` look broken, and that is not repeated
here.

Paste the output back and the work each one blocks can finish.

---

## 0. Deploying after the 2026-09-04 gate run

The full suite ran INSIDE `deploy.sh` on the one-core box while the live
loops were polling: three hours, load 19.8 on 1 CPU, twelve files down.
Twelve was not twelve defects — it was two of mine, one environment-
dependent test, and nine processes starved or killed. `deploy.sh`'s own
header says when `--no-tests` is right: "only when the suite is already
green". It is green in the sandbox before every push, so:

```bash
cd /srv/qellys && ./deploy/deploy.sh --no-tests
```

Then confirm what is serving — the serving commit versus what is on disk,
and whether auto-update already restarted into it:

```bash
cd /srv/qellys && python3 -c "import launch; launch.show_boards()" | head -12
cat data/autoupdate.json
```

And whether the seven files that stopped mid-run were killed for memory
(the shape: some `ok` lines, then nothing, no traceback, no TIMED OUT):

```bash
journalctl -k --since "6 hours ago" | grep -iE "out of memory|killed process" | tail -8
```

---

## 1. Cam Edwards −300 on the book, −155 on our card

**ANSWERED 2026-09-05.** The box's cache said: Hard Rock −155, FanDuel
−260, DraftKings −270, Caesars −280, all read in the same pull. Book
selection — one soft book more than a hundred cents off the field, and
the shop crowned it because a shop is a `max`. Neither blind fix was
it. Shipped the same day: a price more than ten points of implied
probability under the median of the other books at the same line is
not shopped, in both touchdown shops and on the card's strip, and the
college row names the book left out (engine/odds.OUTLIER_GAP,
tests/test_shop_outlier.py). Still worth knowing from the box, because
the cache was 45 hours old: the board's own `odds_status` said "player
quotes: 0 of 0 eligible game(s) pulled" — the college player pull is
not running on the 5-credit day. That is §1b.

**Blocks (was):** task #135. Two candidate causes were fixed blind
(commit `e7930cc`, the sharp-book shop; `a1e121a`, the undated price)
and NEITHER is proven to be this one. A 145-cent gap is wider than
either explains.

The cached college event payload lists every book's price for the player
AND its file mtime, which is what separates the two explanations.

```bash
cd /srv/qellys && python3 - "cam edwards" <<'PY'
import json, time, glob, os, sys
sys.path.insert(0, "/srv/qellys"); os.chdir("/srv/qellys")
from engine.sources.oddsapi import parse_event_scorers, normalize_name
want = " ".join(sys.argv[1:]).strip().lower()
board = json.load(open("data/built/cfb.json"))
print("board built", board.get("generated_at"),
      "| odds_status", json.dumps(board.get("odds_status") or {}))
now, quotes = time.time(), {}
files = glob.glob("data/cache/odds_event_cfb_*.json")
for f in files:
    age = (now - os.path.getmtime(f)) / 3600.0
    try: payload = json.load(open(f))
    except Exception: continue
    for (norm, mkt), qs in parse_event_scorers(payload).items():
        if mkt == "anytime_td":
            for q in qs:
                quotes.setdefault(norm, []).append(
                    (q["book"], q["yes_odds"], q.get("no_odds"), age))
print(f"{len(files)} cached college payloads, {len(quotes)} players quoted\n")
def show(norm, label, odds=None, book=None):
    print(f"--- {label}  [{norm}]")
    if odds is not None: print(f"    board shows {odds:+d} at {book}")
    got = quotes.get(norm) or []
    if not got: print("    NOT IN ANY CACHED PAYLOAD"); return
    for b, y, n, age in sorted(got, key=lambda x: -x[1]):
        print(f"    {b:<14} yes {y:+6d}  no {str(n):>6}   read {age:5.1f}h ago")
hit = False
for key in ("most_likely", "longshot_watch", "long_shots"):
    for r in board.get(key) or []:
        name = str(r.get("player") or "")
        if not name or (want and want not in name.lower()): continue
        if key == "most_likely" and r.get("market") != "anytime_td": continue
        hit = True
        show(normalize_name(name), f"{name} ({r.get('team')}) on {key}",
             int(r["odds"]), r.get("book"))
if want and not hit:
    print(f"no board row matching {want!r} — searching the cache directly")
    for norm in quotes:
        if want.replace(" ", "") in norm.replace(" ", ""): show(norm, norm)
PY
```

Swap the name in the first line to check anyone else.

### How to read it

| What comes back | What it means |
|---|---|
| Every book old and clustered near −155 | **Stale cache.** The price was right when read and the market moved. `a1e121a` makes the board admit the age; the follow-up question is whether the college player pull can afford to run at all on a 26-credit day. |
| One book at −155, the rest at −300, all read minutes ago | **Book selection.** `e7930cc` covers it if that book was Pinnacle. If it was a soft book genuinely 145 cents off the field, that is a third defect — we shop the outlier and print it, and I would want a cap on how far one book may sit from consensus before it wins the shop. |
| `NOT IN ANY CACHED PAYLOAD` | The price came from somewhere I have not found. The most interesting of the three. |

### 1b. Is the college player pull running at all?

**ANSWERED 2026-09-05, in the evening, from the spend ledger.** No. On
the opening Saturday college made 63 board-line pulls (3 credits each,
one every fifteen minutes from 00:06) and ZERO player-quote pulls. The
NFL bought 336 credits of player quotes overnight for games five days
away. The full college pull was authorised once, at the 6pm
touchpoint, when every game had kicked off — so it found no candidates,
bought nothing, and STILL stamped college's clock and claimed the
touchpoint, because "landed" was the quota stamp moving and the
3-credit board request in the same build moves it. Why the morning
cycles never authorised it could not be read back: the refresh loop
runs quiet, its verdicts were printed nowhere, and the journal holds
only web requests.

Shipped the same night: every verdict is written to
`data/cache/odds_decisions.jsonl` whether or not it was printed, the
odds doctor prints the latest per lane, and a full pull that bought
less than a board request plus one player call no longer stamps the
clock (tests/test_odds_decisions.py). Also four schools the books spell
long ("Appalachian State", "Southern Mississippi", "Citadel", "UT Rio
Grande Valley") now resolve to ESPN's short names — 4 of 76 events.

**§1c, the check that matters next: Sunday morning for the NFL, next
Saturday morning for college.** After the deploy, from the box, during
the pre-game window (from 2.5 hours before the first kickoff):

```bash
cd /srv/qellys && python3 launch.py --odds-doctor 2>/dev/null | sed -n '/decisions/,$p'
cd /srv/qellys && python3 -c "
import json, collections
rows = [json.loads(l) for l in open('data/cache/odds_decisions.jsonl')]
for lane in ('cfb', 'cfb_lines', 'nfl', 'nfl_lines'):
    rs = [r for r in rows if r['lane'] == lane][-12:]
    print(lane)
    for r in rs: print('  ', r['iso'][11:16], 'PULL' if r['ok'] else 'hold', r['reason'][:100])"
grep '"sport": "cfb"' data/cache/odds_spend.jsonl | grep -v live_board | tail -5
```

* The `cfb` lane must show `PULL … refreshing odds` at least once before
  the first kickoff, and the spend log must then carry `live_event`
  rows for cfb. If every morning row is `hold` with the same reason,
  paste the reason: that is the sentence the whole day was missing.
* A `bought` row in the ledger names a pull that spent under the
  minimum; the clock was not stamped and the next cycle asked again.

The original command, kept for the board's own numbers:

```bash
cd /srv/qellys && python3 -c "
import json; d = json.load(open('data/built/cfb.json'))
print(d.get('generated_at'), json.dumps(d.get('odds_status')))
print('budget:', json.dumps((d.get('prop_census') or {}), default=str)[:400])"
cd /srv/qellys && python3 launch.py --odds-doctor 2>/dev/null | head -30
```

A `note` saying 0 of 0 eligible games on a game day means the
eligibility filter (kickoff window, credit ceiling) excluded every game;
the doctor prints the ceiling and what is left. Paste both.

---

## 2. What is actually inside an ESPN game summary

**Blocks:** task #138 — live play-by-play for NFL, CFB, NBA and WNBA
(items 3 and 4 of the live plan). `site.api.espn.com` is refused by the
agent sandbox's egress proxy on every path, and the repo has no fixture
of that payload's plays, so the shape of `drives` / `plays` is something
I would be recalling rather than reading.

```bash
cd /srv/qellys && python3 espnprobe.py --league cfb
```

Run it while a game is on — `drives.current` and a live situation only
exist while the clock is running, and the probe picks an in-progress
event on purpose. Worth doing all four:

```bash
cd /srv/qellys && for lg in nfl cfb nba wnba; do
  echo "===== $lg"; python3 espnprobe.py --league $lg; done
```

It 403'd on all four leagues the first time it was run (2026-09-04): the
probe sent a custom User-Agent, and ESPN refuses unfamiliar ones — the
exact rule `engine/sources/fetch.py` measured on 2026-08-08. Fixed to send
none, like every working ESPN call in the repo. Same command.

**Run on 2026-09-05.** College, live: the play-by-play is
`drives.current` + `drives.previous[]`, each drive carrying `plays[]` —
that shape is now what `engine/sources/espnplays.py` reads, and the NFL
and CFB cards draw drives from it. Still needed, one live game each:

* **CFB, SEEN LIVE 2026-09-05** (event 401856658, state `in`):
  `drives.current` + `drives.previous[19]`, each with `plays[]` carrying
  `text`, `clock.displayValue`, `period.number`, `start/end{down,
  distance, yardLine, yardsToEndzone, team{id}}`, `statYardage`,
  `scoringPlay`, `type{text, abbreviation}`, `awayScore/homeScore`,
  `wallclock`; `boxscore.players[2]{team{abbreviation,...},
  statistics[10]{name, keys, labels, athletes[{athlete{displayName, id},
  stats[]}]}}`. Every name `engine/sources/espnplays.py` and
  `cfbdata.parse_summary` read is present. Nothing to change.
* **NFL** — its probe ran pre-game and showed no drives (correct). It is
  the same `sports/football` API, so the parser serves it already, but
  the first live Sunday is the confirmation: `python3 espnprobe.py
  --league nfl` during a game should show `drives dict(2)`.
* **WNBA** — three probes in a row ran pre-game (every attempt landed
  between games). A FINISHED game keeps its play-by-play, so ask for
  yesterday's final instead of waiting for a tip-off:

  ```bash
  cd /srv/qellys && python3 espnprobe.py --league wnba --prefer post --date $(date -d yesterday +%Y%m%d)
  ```

  If that day had no game, step the date back until the first line says
  `state post`. Paste the whole output; the hoops feed gets built from it.
* **WNBA, SEEN** — the Aug 30 final (event 401857186) answered: a
  top-level `plays list(392)`, no `drives`. The hoops feed is built from
  that shape (`engine/sources/espnplays.hoops_plays`), and NBA is served
  off the same inference NFL is — same API one segment over. A play names
  its team and its players by id only, so the sides come from the
  scoreboard's competitor ids and the names from the box score. Three
  things a finished game could not show, to confirm on the first LIVE
  probe (any evening a game is on):

  ```bash
  cd /srv/qellys && python3 espnprobe.py --league wnba
  cd /srv/qellys && python3 espnprobe.py --league wnba --block boxscore.players --depth 5
  cd /srv/qellys && python3 espnprobe.py --league wnba --block plays.40 --depth 3
  cd /srv/qellys && python3 livescore_build.py --league wnba
  ```

  The first should say `plays list(N)` on a game in state `in` — a live
  payload carrying the block a final does. The second should show
  `team: dict(...)` with `id` beside `abbreviation`, and
  `athletes[].athlete{displayName, id}`. The third is a mid-game play
  rather than the opening jump ball: how many `participants` a shot
  lists (the parser names the first) and whether `pointsAttempted` is
  the shot's value. The build should print `plays: N of N live game(s)`.

It prints key names, container types, list lengths and the values of
numbers and booleans. It never prints a play's text — that comes back as
`str(29)`. If the structure alone turns out not to be enough,
`--dump /tmp/cfb_summary.json` writes the raw payload (ESPN's content: a
working note, not something to publish).

### 2b. The MLB play-by-play shapes the render needs

The play-by-play page (2026-09-05) reads three things off statsapi's
playByPlay that this repo had never read before: the batted-ball data
the park animation draws (`playEvents[].hitData`), the per-event and
per-play times (`startTime`/`endTime`), and the count on a pitch event
(`playEvents[].count`). All three are read tolerantly — absent means no
arc, no time, no count — and the droplet already caches real games
under `data/cache/mlb_pbp_*.json`. Print the shape of one:

```bash
cd /srv/qellys && F=$(ls -t data/cache/mlb_pbp_*.json | head -1) && echo $F && \
  python3 espnprobe.py --file $F --block allPlays.20 --depth 3 && \
  python3 -c "
import json, sys
d = json.load(open('$F'))
for p in d.get('allPlays') or []:
    for e in p.get('playEvents') or []:
        if e.get('hitData'):
            hd = e['hitData']; print('hitData keys:', sorted(hd)); print('coordinates:', sorted((hd.get('coordinates') or {}).keys()))
            print('about keys:', sorted(p.get('about') or {})); print('event keys:', sorted(e)); print('count:', e.get('count'))
            sys.exit(0)
print('no hitData in this file')"
```

**SEEN 2026-09-05** on `mlb_pbp_live_823823.json`: `hitData{coordinates
{coordX, coordY}, hardness, launchAngle, launchSpeed, location,
totalDistance, trajectory}`, `about{startTime, endTime, halfInning,
inning, isTopInning, ...}`, the event with `startTime`, `endTime` and
`count{balls, strikes, outs}`. Exactly the names the park reads.

Expected: `hitData` with `launchSpeed`, `launchAngle`, `totalDistance`,
`trajectory`, `coordinates{coordX, coordY}`; `about` with `startTime`
and `endTime`; the event with `startTime`/`endTime` and `count{balls,
strikes, outs}`. Anything different is a name to fix in
`engine/mlb/sources/pbp.py` (`_hit`, `_when`, `game_events`) — the
readers are tolerant, so a wrong name shows as an arc that never draws
rather than a crash.

---

## 3. MLB says 20 recommended bets and draws 2

**ANSWERED 2026-09-05.** The box said `analyzed 870 | recommended 0 |
drawn 0 | held 0` — the home-run rule was not the cause, and neither
number on the Dashboard is wrong. The "Recommended bets" tile is
`staked + riding` (web/js/app.js renderStats, Ethan's 2026-09-03 call:
"what am I on tonight"): NEW picks that clear the sliders PLUS the
open bets the tracker is still riding at the price they were taken.
The grid draws only the new ones. The day he saw 20 and 2 was 2 new
and 18 riding, and the tile's own sub-line says so ("2 new · 18 riding
at the price we took"). On the 5th it was 0 new and 11 riding. Product
call, not a defect: keep the headline as the total with the split
underneath (today), or make the headline the split itself ("2 new +
18 riding"). Say which.

**Blocks (was):** task #139. Two filter chains sit one above the other on the
Dashboard and nothing reconciles them:

| surface | filter | what it feeds |
|---|---|---|
| `tonightSignals().props` | `passesFilters` | the "Recommended bets" tile, the Best Bets picks box |
| `renderRecommended` | `passesFilters` **and** `hr_featured !== false` | the card grid |
| `renderTonight` | same as the grid | the Tonight tab |

`engine/mlb/pipeline.py` stamps `hr_featured` false on every home-run
prop outside the top three (`LONGSHOT_BOARD = 3`). That is a display
rule, not a verdict — those props passed every gate and are journaled.

The page now NAMES the gap rather than leaving you to find it, and
neither number was changed. Which one should win is a product call, and
this settles what the split actually is:

```bash
cd /srv/qellys && python3 - <<'PY2'
import json, collections
d = json.load(open("data/built/mlb_recommendations.json"))
recs = d.get("recommendations") or []
# The front end's own bar: recommended, not graded Pass. The sliders sit
# on top of this and only ever narrow it further.
rec = [r for r in recs if r.get("recommended") and r.get("grade") != "Pass"]
held = [r for r in rec if r.get("hr_featured") is False]
print(f"analyzed {len(recs)} | recommended {len(rec)} | "
      f"drawn on the grid {len(rec) - len(held)} | held for Long Shots {len(held)}")
print("recommended by market:",
      dict(collections.Counter(r.get("market") for r in rec)))
if held:
    print("\nheld back (these are the missing ones):")
    for r in held[:25]:
        print(f"  {r.get('player','?'):<24} {r.get('market')} "
              f"{r.get('side','')} {r.get('line','')} @ {r.get('odds')} "
              f"grade {r.get('grade')} stake {r.get('stake_units')}")
else:
    print("\nNOTHING is held by the home-run rule — the 20-vs-2 gap is "
          "something else, and the numbers above say where to look next.")
PY2
```

### How to read it

* **`recommended 20 · drawn 2 · held 18`** — confirmed. Then the product
  call: leave it as it is now (both numbers shown, the gap named and one
  click away), or draw all twenty on the Dashboard and accept that the
  board leads with home-run darts. Say which and it is a small change.
* **`held 0`** — the home-run rule is not the cause and I was chasing the
  wrong divergence. The market breakdown says where to look instead.

---

## 4. Confirm the two fixes that need a rebuild to show

Neither is urgent; both are "did the thing I changed actually reach the
board".

**The recency shade is retired** (NFL projections). Every `trend` step
should now be ×1.00:

```bash
cd /srv/qellys && python3 -c "
import json
b = json.load(open('data/built/recommendations.json'))
steps = [s for r in (b.get('recommendations') or [])
         for s in (r.get('chain') or []) if s.get('name') == 'trend']
print(len(steps), 'trend steps;',
      sum(1 for s in steps if abs(float(s.get('mult', 1)) - 1.0) > 1e-9),
      'still shading')"
```

**College headshots landed.** The next CFB build prints a
`Headshots: N of M` line; anything other than `0 of M` means the chain
is working.

---

## 5. Why college shows Most Likely rows and no edge bets

Ethan, 2026-09-05: "CFB is not showing any edge bets, just the most
likely bets."

Two different gates, and the second one is a calendar. Every college
prop goes through `betting.evaluate_prop`, which refuses a Pass when
`is_reliable("cfb", market)` is false or when the raw read disagrees
with the market by more than `MAX_CREDIBLE_EDGE` (0.10). Both depend on
`data/models/calibration.json` having a fitted entry for college — and
until 2026-09-04 no fitter could even be pointed at college (see the
merge in `e69a0fd`). The weekly deep refit that writes that store runs
on **Wednesdays** (engine/maintenance.py, `today.weekday() == 2`). So
until it has run once for college, `correction_for("cfb", …)` returns the
neutral (1.0, 0.0), the model over-claims by the 6–7 points the sandbox
fit measured, every edge lands past 0.10, and every prop is refused as
not credible. The Most Likely board does not price against the market,
which is why it still fills.

What the store says now, and what the board refused and why:

```bash
cd /srv/qellys && python3 calibrate.py --sport cfb --show
cd /srv/qellys && python3 - <<'PY4'
import json, collections
d = json.load(open("data/built/cfb.json"))
for k in ("prop_census", "gate_census", "game_census", "td_census", "likely_census"):
    v = d.get(k)
    if v: print(f"{k}: {json.dumps(v, default=str)[:600]}")
recs = d.get("recommendations") or []
print("\nprops by market -> grade:")
for m in sorted({r.get("market") for r in recs}):
    g = collections.Counter(r.get("grade") for r in recs if r.get("market") == m)
    print(f"  {m:<12} {dict(g)}")
gb = d.get("game_bets") or []
print("game bets:", len(gb), dict(collections.Counter(b.get("grade") for b in gb)))
PY4
```

**Read on 2026-09-05:** the store HAS college — pass_yds 0.4, rec_yds
0.7, receptions 0.4, rush_yds 0.4. The search grid runs 0.40 to 6.0, so
three of the four sit ON the floor: the data wanted a sharper correction
than the search allows, and `is_reliable` treats a boundary fit as
"unreliable here, not merely miscalibrated" and shuts the market. Only
`rec_yds` is open. (The NFL's rec_yds and rush_yds sit on the 6.0
ceiling — the same verdict from the other end, and the reason the NFL
board's props die at calibration.) So of the 19 college props that had a
book price, only the receiving-yard ones could have graded at all. This
prints each priced prop with the reason it was refused:

```bash
cd /srv/qellys && python3 - <<'PY5'
import json
from engine.calibrate import is_reliable
d = json.load(open("data/built/cfb.json"))
rows = [r for r in (d.get("recommendations") or []) if r.get("has_market") is not False and r.get("odds")]
print(f"{len(rows)} priced college props")
for r in sorted(rows, key=lambda r: (r.get("market"), -(r.get("edge") or 0))):
    shut = "" if is_reliable("cfb", r["market"]) else "  [market SHUT: boundary fit]"
    why = next((x for x in (r.get("reasons") or []) + (r.get("warnings") or [])
                if any(k in str(x) for k in ("disagree", "bar", "calibrat", "credib", "under", "hold"))), "")
    print(f"  {r.get('market'):<11} {str(r.get('player'))[:22]:<22} {r.get('side','')} {r.get('line')} @ {r.get('odds')} "
          f"edge {100*(r.get('edge') or 0):+.1f}pt model {100*(r.get('hit_prob') or 0):.0f}% grade {r.get('grade')}{shut}")
    if why: print(f"      {str(why)[:110]}")
PY5
```

If `--show` prints nothing for college, the store has no college entry
and the refusals are the calendar. To fit it now instead of waiting for
Wednesday — this spawns the three fitters as subprocesses and replays
every college season, so run it at a quiet hour and expect minutes:

```bash
cd /srv/qellys && python3 -c "from engine.deepfit import refit_sport; [print(l) for l in refit_sport('cfb')]"
```

Then a rebuild (`python3 launch.py` refreshes on its own cycle) prices
the next board against the fitted store. Expect ONE of the four markets
to stay shut afterwards: the sandbox fit put `receptions` at the edge of
its search grid, which `is_reliable` treats as "unreliable here, not
merely miscalibrated". That is the fitter's honest verdict, not a bug.

Game bets are a separate path (`engine/gamebets`), and `game_census`
above says whether they were refused before the model ran (no lines, no
rating) or by it (`gate_census`).

---

## 6. MLB recency shade, still unmeasured

**Blocks:** task #127. The harness is unblocked but there are no MLB
logs in the sandbox. On the box:

```bash
cd /srv/qellys && python3 - <<'PY3'
from engine import db, formcheck
conn = db.connect()                 # data/history.db — the graded logs
for m in ("hits", "total_bases", "strikeouts"):
    out = formcheck.run(conn, m, sport="mlb")
    n = out.get("n") or 0
    if not n:
        print(f"{m}: no eligible player-weeks "
              f"({out.get('unreadable', 0)} unreadable rows)")
        continue
    print(f"{m}: n={n}")
    for name, v in sorted(out.items()):
        if name not in ("market", "n", "unreadable"):
            print(f"    {name}: {v}")
PY3
```

`run` takes the history connection as its FIRST POSITIONAL argument —
the version of this command I first wrote omitted it and would have
failed on the box before printing anything, which is the same shape as
telling you to run `nfl_build.py --odds` when it needs two positional
arguments. Checked against the signature this time.

NFL's shade was retired after measurement showed it hurt ordering in all
four markets. MLB was deliberately left alone until its own history says
something.

---

## 7. The open-bet tracker on the NFL, CFB, NBA and WNBA Live tabs

Landed 2026-09-05 (`81f6f03`, `5600e0a`). Until then only the MLB board
wrote `live_picks`, so the Live tab on every other sport said "No open
bets on today's card" whatever the journal held. Each build now attaches
the tracker before it writes, and fetches live stat lines for player
props off ESPN's box score (the play feed's 30-second cache, never the
ingests' month-long one).

`live_picks` is a paid key, so the PUBLIC file never carries it — read
the full copy the gate writes first:

```bash
cd /srv/qellys && python3 - <<'PY7'
import json
for f in ("recommendations", "cfb", "nba", "wnba", "mlb_recommendations"):
    try:
        d = json.load(open(f"data/built/{f}.json"))
    except FileNotFoundError:
        print(f"{f:<20} no built copy yet"); continue
    rows = d.get("live_picks")
    print(f"{f:<20} live_picks={'ABSENT' if rows is None else len(rows)} "
          f"open_elsewhere={d.get('open_elsewhere')} "
          f"error={d.get('live_picks_error')}")
    for r in (rows or [])[:8]:
        print("   ", r.get("category"), "|", r.get("player"), r.get("market"),
              r.get("side"), r.get("line"), "|", r.get("phase"),
              r.get("status"), "current=", r.get("current"))
PY7
```

What to expect, board by board, after the next refresh cycle:

* `live_picks=ABSENT` on a football or hoops board means that build has
  not run since the pull — wait a cycle. `ABSENT` on MLB is a real
  regression (its tracker predates this and was not touched).
* `error=` names anything the tracker hit; it lands in the JSON on
  purpose because the launcher swallows build output.
* A row's `category` is what the Live tab splits on: `main`/`longshot`
  in the edge panel, `likely` in the Most Likely panel.
* `current=None` on a player prop during a live game means no live stat
  line reached it. The build log says why — one line per board:

  ```bash
  journalctl -u qellys --since "2 hours ago" --no-pager | grep -i "open-bet tracker"
  ```

  **SEEN 2026-09-05: that grep prints nothing on the box** — the
  launcher swallows build output, so neither this line nor the light
  board's size line reaches the journal. The tracker's own state is in
  the JSON (`live_picks_error`, `open_elsewhere`), which the script
  above prints; the light copies' sizes come from the files:

  ```bash
  cd /srv/qellys && ls -la data/built/*_picks.json data/built/recommendations.json data/built/mlb_recommendations.json data/built/cfb.json
  ```

  Seen on the 5th, pre-game: NFL 116 open bets for the week, all
  upcoming; CFB 34 with game rows tracking live scores; MLB 11; NBA and
  WNBA 0 with `open_elsewhere` 76. Player-prop rows with a live stat
  line are the one thing still unseen — Sunday.

  `Open-bet tracker: 5 on this card (5 live, 1 likely); live stats: 1
  of 1 live game(s)` is the healthy shape. `not on the scoreboard` means
  the board's `away@home` did not match the fast scoreboard's (the same
  identity join the Live tab's scores use); `feed(s) unreachable` is
  ESPN; `past the 8-game cap` is the budget, by design.
* NFL's card is the week label (`2026-W01`), so its rows are the whole
  week's open bets; the other three use the slate date and its two
  neighbours.


---

## 8. Team offense/defense rankings on the NFL and CFB standings pages

Shipped 2026-09-02 (`14ecec0`): scoring offense and defense from the
standings table's own finished games, `standings.unit_rankings`. Absent
by design for a season with no finals — which is the NFL until Week 1 —
and as of 2026-09-05 the section renders anyway on a football page with
the reason and, on the NFL, the model's profile ranked on last season.

Whether CFB's live file carries the real rankings today (two weeks of
finals exist; the sandbox copy is stale and cannot say):

```bash
cd /srv/qellys && python3 -c "
import json
for sp in ('cfb', 'nfl'):
    d = json.load(open(f'web/data/standings_{sp}.json'))
    ur = d.get('unit_rankings')
    print(sp, 'season', d.get('season'), 'games_counted', d.get('games_counted'),
          'source', d.get('source'), 'feed_error', (d.get('feed_error') or '')[:80])
    print('   rankings:', 'ABSENT' if not ur else
          f\"{len(ur['offense'])} teams, offense #1 {ur['offense'][0]['team']} {ur['offense'][0]['value']}\")"
```

* CFB `rankings: ABSENT` with `games_counted` 0 means the standings
  build is not seeing finals — check `feed_error` (ESPN's standings
  feed) and whether `ingest.py cfb` has run; the table and the rankings
  are counted from the same rows.
* NFL `ABSENT` before the 10th is correct; the page shows the wait and
  the 2025 model profile instead. After Week 1's finals ingest it fills
  in on its own.

**SEEN 2026-09-05:** CFB `82 teams, offense #1 UCF 73.0`, 43 games,
`source computed` (the league feed answered with no teams and the
count from our own finals took over — correct). NFL was WRONG: `49
games, source league, offense #1 BUF 29.3` five days before Week 1 —
ESPN's standings feed answered with the PRESEASON table because no
season type was named. Fixed the same day (the feed asks for
`seasontype=2`; tests/test_standings_regular_season.py). After the next
deploy and refresh:

```bash
cd /srv/qellys && python3 -c "
import json; d = json.load(open('web/data/standings_nfl.json'))
print('nfl games_counted', d.get('games_counted'), 'source', d.get('source'), 'rankings', 'ABSENT' if not d.get('unit_rankings') else 'PRESENT')"
```

must say `games_counted 0` and `rankings ABSENT` until the 10th, then
climb by 16 a week. A 49 that survives the deploy means ESPN ignored
the parameter, and the fallback is to read the count off our own
ingest before the 10th — say so and it is a small change.


## 9. The explainer, once its package and keys are on the box

Ethan, 2026-09-05: "a plain English explainer per pick." Shipped the
same day; nothing here can exercise it (no key, no package on the
sandbox's system python). After docs/DEPLOY.md's install step:

```bash
sudo -u qellys python3 -c "import anthropic; print('sdk', anthropic.__version__)"
sudo ./deploy/setenv.sh --show | grep -E "QB_EXPLAIN_MODEL|ANTHROPIC_API_KEY"
# signed in as a subscriber, in the browser: open any prop page, tap
# Explain. Then on the box:
python3 -c "
import json; d = json.load(open('/srv/qellys/data/explain_cache.json'))
print(len(d), 'cached answers'); k = next(iter(d)); print(k.split(chr(9))[:2]); print(d[k]['text'][:300])"
```

* "not switched on" on the page with both values set means the service
  did not get them — `systemctl restart qellys` after setenv.
* A 503 "explainer unavailable" with a detail naming `AuthenticationError`
  is the key; `NotFoundError` is the model id; `APIConnectionError` is
  the box's outbound HTTPS.
* A second tap on the same pick must come back at once (`cached: true`
  in the network tab) and the cache file must not grow.

## 10. Under pressure: the numbers, the college remap, and the live line

Ethan, 2026-09-05: "Add under pressure data for teams, like clutch win
% and reliability % and comeback % and choke % and see if we can have
that as live data as well like when games are going." The rates ride
`standings_<sport>.json` under `pressure` (engine/pressure.py). Two
things only the box can confirm: that college rows are keyed by the
board's abbreviations there (the sandbox still holds `espn:<id>` keys,
which the module maps through the persisted id file when it has one),
and that the live card's line appears while a game is going.

```bash
cd /srv/qellys && sudo -u qellys python3 standings_build.py --sport nfl && sudo -u qellys python3 standings_build.py --sport cfb
python3 -c "
import json
for sp in ('nfl','cfb','mlb'):
    d = json.load(open(f'web/data/standings_{sp}.json')); p = d.get('pressure')
    if not p: print(sp, 'no pressure block'); continue
    print(sp, 'season', p['season'], 'used', p['season_used'], 'lined', p['lined'], 'teams', len(p['teams']), p['note'][:60])
    for k in ('clutch','reliability','comeback','choke'):
        print('  ', k, [(r['team'], r['value'], r['n']) for r in p['ranked'][k][:3]])"
```

* NFL and CFB must show `used 2025` until this season has four games
  a team, and no team key may start with `ESPN:` — if one does, the id
  map is missing on the box: `python3 -c "from engine import cfbteams;
  print(len(cfbteams.load_ids()))"` should be in the hundreds.
* MLB: `lined False` and the note about closing lines is the honest
  state (we store no baseball spreads); the clutch column still ranks.
* In the browser during any live NFL or CFB game: the card on the Live
  tab carries an "UNDER PRESSURE" line under the lines grid, and it
  changes wording when the favourite trails or a one-score game reaches
  the fourth quarter. The game page carries the two-team table under
  the lines card. Both label the season the rates come from.

## 11. College bets that never settled: the 2026 results were never ingested

Ethan, 2026-09-06: "CFB doesn't seem to have settled its bets." The
nightly ingests three college feeds — closing lines, player logs and
results — and only the results had no in-season refresh: their guard was
a count of finished games, so once the four-season backfill landed the
block never ran again and no 2026 result reached the `games` table.
`settle_from_history` grades a college game bet (moneyline, spread,
total, team total) only from a games row on the bet's own date, so every
one of them stayed open; the props settled on the Monday player refresh.

The fix runs from tonight's nightly. To clear the backlog now:

```bash
cd /srv/qellys
sudo -u qellys python3 ingest.py cfbhist --seasons 2026
python3 -c "
import sqlite3; c = sqlite3.connect('data/history.db')
print(c.execute(\"SELECT COUNT(*), MIN(period), MAX(period) FROM games \"
                \"WHERE sport='cfb' AND season=2026 AND home_score IS NOT NULL\").fetchone())"
sudo -u qellys python3 launch.py --settle all
sudo -u qellys python3 launch.py --why-open | head -40
```

* The count must be the number of FBS games played so far this season,
  not 1. If it is 1, the mirror has not published 2026 yet — the skipped
  line from the ingest says which URL it tried.
* `--settle all` walks each day with open picks, oldest first, and the
  journal export at the end refreshes the Record page.
* `--why-open` lists what is still open and why. A college game bet that
  is still open after the ingest is a team-key mismatch, not a missing
  result: check `python3 -c "from engine import cfbteams; print(len(cfbteams.load_ids()))"`
  is in the hundreds, and that no `games` row for 2026 is keyed `espn:`.

If the college scope shows **no bets at all** rather than open ones, the
picks were never journaled, which is a different fault with its own
answer. A pick is skipped when it is not recommended, has no real book
price, is a long shot (its own bucket), or is sized at 0.00 units — and
`engine/probation.unstake` zeroes every college size while the ratings
are unfitted, which is exactly the state the missing results caused.

```bash
cd /srv/qellys
python3 -c "
import sqlite3; c = sqlite3.connect('data/ledger.db')
print(c.execute(\"SELECT category, status, COUNT(*) FROM bets \"
                \"WHERE sport='cfb' GROUP BY 1,2\").fetchall())"
sudo -u qellys python3 launch.py --why-pick "<a player on tonight's college board>" cfb
```

* Rows in `main` that are open: the results were missing — §11 above.
* Rows only in `likely` or `longshot`: the edge board staked nothing, so
  nothing reached the main book. `--why-pick` names the reason for one
  pick — "stake is 0.00u" with a probation note is the sport being
  gated rather than the pick being refused.
* No rows at all: the board recommended nothing that day.

## 12. College totals never had a joinable game key

Found from Ethan's §11 run on 2026-09-06: the ingest landed 25 games and
`--settle all` still graded nothing, with `--why-open` filing college
TOTALS under "no stat line". That label was wrong and the cause was a
key: every other ingest writes a game row as `away@home` (`DAL@TB`), and
a total bet stores exactly that matchup string — the college feed wrote
the mirror's numeric id instead, so 0 of 3,133 rows were joinable.

The nightly now rekeys before it refreshes. To do it at once:

```bash
cd /srv/qellys
python3 -c "
import sys; sys.path.insert(0, '.')
from engine import db, ingest
print(ingest.remap_cfb_game_ids(db.connect()))"
sudo -u qellys python3 launch.py --settle all
sudo -u qellys python3 launch.py --why-open | head -30
```

* `renamed` should be in the thousands on the first run and 0 after —
  it is idempotent. `merged` counts games that already had a row under
  the right key; those duplicates would have had `standings.compute`
  counting one game twice.
* College totals should start grading. Spreads, moneylines and team
  totals join on the TEAM columns and were never affected by this.
* What this does NOT fix: a bet on an FBS-vs-FCS game. `parse_schedule`
  keeps only FBS-vs-FBS, so those games have no result row at all and
  their bets stay open — that is the next item, and it needs a marker in
  `extra` so `engine/cfb/ratings.py` can keep excluding them from the
  fit while the settle path can see them.

## 13. Buy games: an FBS side against an FCS opponent

The last block of stuck college bets from §11/§12. `parse_schedule`
stored FBS-vs-FBS only, which is the right rule for the model's fit and
the wrong one for the ledger: the board prices every game an FBS team
plays, so a bet on UAPB@MIZ or BCU@UCF had no result row and never
would. Those games are stored now, with the FCS side keyed `espn:<id>`
— the same form `teamrates` and `cfb.ratings` exclude from every fit, so
the scoring baseline and margin spread are untouched.

```bash
cd /srv/qellys
sudo -u qellys python3 ingest.py cfbhist --seasons 2026
python3 -c "
import sqlite3; c = sqlite3.connect('data/history.db')
q = \"SELECT COUNT(*) FROM games WHERE sport='cfb' AND season=2026 AND home_score IS NOT NULL\"
print('2026 games', c.execute(q).fetchone()[0])
print('with an FCS side', c.execute(q + \" AND (home LIKE 'espn:%' OR away LIKE 'espn:%')\").fetchone()[0])"
sudo -u qellys python3 launch.py --settle all
sudo -u qellys python3 launch.py --why-open | head -30
```

* The 2026 count should jump well past the 25 from §11 — a college
  Saturday is 60-plus FBS games and roughly a fifth of September's are
  buy games.
* NO_STATLINE should fall sharply. What remains there should be real
  player props, not `total` rows.
* The college ratings must not move: `python3 launch.py --check` still
  reports the same margin spread and home-field edge it did before.

## 14. Is the claimed edge noise everywhere, or only on average?

Ethan, 2026-09-06: the line every settle pass prints — `edge test:
n=562 claimed-edge AUC 0.463 [0.414, 0.512] -> edge_is_noise`. That is
one number over six sports and a dozen markets, and a pooled coin flip
has three explanations with three different answers: every slice is a
coin flip, one slice carries the signal and the rest dilute it away, or
two slices point opposite ways and cancel. `stakecheck --info` now cuts
it.

```bash
cd /srv/qellys
sudo -u qellys python3 stakecheck.py --info
```

* Read the BY SLICE table under the pooled reading. `q` is the
  Benjamini-Hochberg q-value across every slice tested — a slice is only
  a finding if it is starred, and a raw p under 0.05 with a q above it
  means exactly one thing: that slice looked good because several were
  looked at.
* A slice under 60 settled bets is listed as too thin and is NOT tested.
  That is deliberate: adding it to the family would make every other
  slice harder to call, and its own interval would be wider than any
  effect worth acting on.
* If nothing survives, the pooled verdict stands per slice as well, and
  the honest reading is that selecting on claimed edge is selecting on
  noise anywhere we have enough bets to check.
* If something survives, that is where edge selection is doing work.
  Send it to me before changing any gate — one survivor out of a dozen
  at FDR 0.05 is still a one-in-twenty story, and the next thing to do
  is preregister it (`engine/prereg.py`) rather than act on it.

## 15. If not the claimed edge, then what?

Ethan, 2026-09-06, reading the §14 run — 931 settled bets, the model at
AUC 0.589, the market at 0.589, the claimed edge at 0.471, the paired
difference −0.000 [−0.007, +0.007], and no slice surviving: **"Rebuild
what it selects on."** Keep the staking rule, stop selecting on claimed
edge, sort and gate on the model's probability rank instead.

Nothing in the gate has moved. `stakecheck --select` is the backtest
that has to run first, because the alternative has never been scored
against the rule it would replace, and shipping it on the argument alone
would put a second unmeasured claim exactly where the first one stood.

```bash
cd /srv/qellys
sudo -u qellys python3 stakecheck.py --select
sudo -u qellys python3 stakecheck.py --select --sport mlb
sudo -u qellys python3 stakecheck.py --select --as-placed
```

It orders the same settled pool three ways — by claimed edge, by the
model's probability, and by the market's implied price as a control —
bets the top 25% of each at the prices we actually took, and counts the
money. Same rows, same vig, same settling, so a difference in ROI is a
difference in *selection* and nothing else.

**Read the overlap block before the ROI table.** If the `prob` slice and
the `market` slice are 85% the same bets, then "sort by the model's
probability" and "sort by the shortest price" are the same instruction
in different words — and `engine/likely.py` already carries what that
costs, in Ethan's own words from 2026-09-01, after a board built that
way spent its first settled night on −800, −1200 and −1800 rows and lost
11.2%. A high overlap does not kill the rebuild; it says the rebuild
needs a price bar bolted to it before it selects anything.

**What it cannot say**, and the report prints this itself: whether
probability-ranking would have *admitted* bets the edge gate refused.
The journal holds the bets we placed, not the ones we passed on, and a
candidate with no outcome cannot be scored. So every figure is
conditional on today's gate having already run — which is the right
evidence for changing the board's sort order and its cap, and not enough
on its own for opening the gate wider.

Send me all three outputs. The `--sport mlb` cut matters because 858 of
the 931 are baseball and the NFL has *zero* settled bets: whatever this
says, it is a baseball verdict, and football goes into Week 1 unmeasured.

## 16. Sizing the price test before it is registered

The §15 run came back against the rebuild. Backed out of its own table,
the three orderings were not three ideas — they were three prices:

    ordering   avg winner pays   hit     ROI
    edge            +122        44.6%   -0.9%
    prob            -163        56.2%   -9.3%
    market          -166        54.1%  -13.4%
    the lot         -102        48.1%   -4.5%

The short-price arms lost most. That observation cannot convict anything,
because it is the same 931 rows that produced it — so the question is
asked forward, through `engine/prereg.py`, and the bar is BORROWED rather
than fitted: -250, which is `likely.HEAVIEST_PRICE`, chosen on the Most
Likely board's own evidence on 2026-09-01.

`HEAVY_PRICE_EDGE` is drafted in `engine/prereg.py` and **is not
registered** — `ensure_registered` does not call it. One line there
activates it, and that line is not written until the band is known to be
reachable. A preregistration against a band the book never bets sits at
"0 of 80" forever while looking perfectly healthy; prereg.py records that
near-miss on `TD_EDGE_NFL` and calls it "the bug this codebase finds in
itself more than any other".

```bash
cd /srv/qellys
sudo -u qellys python3 stakecheck.py --prices
sudo -u qellys python3 stakecheck.py --prices --sport mlb
```

* It prints COUNTS ONLY, per band and per sport. No ROI column, on
  purpose: choosing a threshold after seeing which band happened to lose
  is fitting the test to the sample that suggested it. Counts carry no
  outcome information, so sizing on them cannot bias what the test finds.
* What matters is the first row, `-250 or shorter`. If the settled book
  has a healthy number there, `min_n: 80` is reachable and the test can
  be registered. If it is a handful, the Edge board is not betting chalk
  and the whole question is moot — which is also a real answer, arrived
  at without spending a preregistration on it.
* Send me the two outputs. Registering is one line and I will not write
  it until the counts say the test can finish.
