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

  LOOK FOR `yardsToEndzone` INSIDE A PLAY'S `start` WHILE YOU ARE THERE.
  Since 2026-09-07 the field-position strip on the play-by-play page
  falls back to it whenever the scoreboard's `situation` block is
  absent, which is the normal case in college and the reason Ethan saw
  no ball marker on a live Louisville card. College has been seen
  carrying it; the NFL is served by the same inference as its drives
  are, and this is the run that settles it. If it is missing, the strip
  simply does not draw on games with no `situation` block — the
  scoreboard path is untouched — so this is a check, not an outage.
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
* NFL `ABSENT` before the opener (Wednesday the 9th) is correct; the page shows the wait and
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

must say `games_counted 0` and `rankings ABSENT` until the opener on the 9th, then
climb by 16 a week. A 49 that survives the deploy means ESPN ignored
the parameter, and the fallback is to read the count off our own
ingest before the opener — say so and it is a small change.

**2026-09-08, asked a third time.** The section was drawn LAST on the
page — under eight division tables on the NFL, under 130-odd conference
rows on the CFB — and the page's empty-table branch returned before
reaching it, so an NFL feed that answers with no teams before kickoff
hid the 09-05 wait section entirely. The rankings lead the football
page now (the nav button says "Rankings"), an empty table no longer
hides them, and the page title reads "NFL rankings & standings". What
to see, no command needed: open Rankings on the NFL and the first
heading is **Team rankings**, thirty-two teams ranked on 2025 until the
first 2026 finals; on the CFB the same heading, ranked on this season's
finished games (82 teams on 09-05). If the NFL heading is there but
the two columns are not, the NFL board is missing `team_shapes` —
`python3 -c "import json; d=json.load(open('web/data/recommendations.json')); print(len(d.get('team_shapes') or {}), d.get('team_shapes_season'))"`
should print `32 2025`.


## 8b. The college talent card left the home page (2026-09-08)

Ethan, with the card circled in week three: "do we really still need to
show this on CFB still and was all that data actually being used." It is
a build-status readout. It now lives on **Status** (with CFB selected as
the league) under "The college talent prior", and says what the prior
carries this week — `weight_now` and `games_median` on `cfb.json`'s
`talent` block — instead of "~25% of a Week-1 projection". The home
page shows nothing while a prior is in force, and the no-prior warning
only while the prior would still carry 10% or more.

```bash
cd /srv/qellys && python3 -c "
import json; t = json.load(open('web/data/cfb.json')).get('talent') or {}
print('available', t.get('available'), 'teams', t.get('teams_with_prior'),
      'weight_now', t.get('weight_now'), 'games_median', t.get('games_median'),
      'layers', t.get('layers'))"
```

In week three expect `weight_now` near 0.19–0.21 and `games_median` 2
or 3. All four inputs are used, unequally: the recruiting composite is
the prior; blue-chip ratio only halves it where the two disagree on a
roster's sign; returning production speeds or slows the decay by up to
30%; the portal moves the prior by at most 2.5 points. What has never
been measured is whether the layer helps against the close —
`engine/gamerank.py`'s college walk leaves it out by its own admission.
That measurement needs the CFBD talent cache by season, which only this
box holds.

## 8c. The Wednesday opener — what was verified here, and what only the box can say (2026-09-08)

Ethan: "since nfl is going to be live and starting on wednsday, do one
more scan and sweep of the site and make sure EVERYTHING is ready for
nfl" and "the opener is on the 9th so we need to make sure we have that
set in to."

**Nothing in the code names a weekday.** The 9/9 opener was a P3 note in
`NFL_READINESS.md` Phase 6 ("Week 1 opens Wednesday 9/9 20:20 NE@SEA in
the nflverse schedule; the brief says Thursday 9/10") and the answer
then is the answer now: the build reads the feed. Verified by running
each assumption rather than reading it:

| what | how it is decided | verified |
|---|---|---|
| Which week builds | `_current_nfl_week` — nearest game in nflverse's schedule, any weekday | nearest-game rule, no weekday term |
| Season window | `seasons.window("nfl", 2026)` = 2026-09-01 → 2027-02-20 | the 9th is inside; `season_wait` already False since the 1st |
| Kickoff epochs for the pacer | `launch._eastern_epoch(date, "HH:MM")` | `("2026-09-09","20:20")` matches the real 20:20 ET epoch exactly |
| Readiness pull | `oddsbudget.ready_window`, 3h before the next kickoff | shut Tue 20:00 and Wed 16:00; **open from Wed 17:20**, and at 19:00 |
| Live scores | `_live_scores_refresher` loops `("nfl","cfb","nba","wnba")` every 12s while anything is live | nfl is in the loop and in `ESPN_SCOREBOARD` |
| Deep play-by-play | `livescore_build` writes `web/data/pbp/nfl_<event>.json` | `PBP_DIR` written for every league it builds |
| Settlement | `maintenance` ingests nflverse weekly results daily, Aug–Feb | Wednesday's final settles on Thursday's pass |

The only two places that named "the 10th" were prose in §8 of this
file, corrected in the same commit.

**On the box, Wednesday.** The readiness pull fires at 17:20 ET; before
then its absence from the log is correct, not a fault:

```bash
cd /srv/qellys && grep -h '"readiness pull' data/cache/odds_decisions.jsonl | tail -3
cd /srv/qellys && python3 -c "
import json; b=json.load(open('web/data/recommendations.json'))
g=b.get('games') or []; print(len(g),'games'); print(sorted({x.get('date') for x in g})[:3])
print('kickoffs:', [x.get('kickoff') for x in g][:3])
m=b.get('most_likely') or []
print(len(m),'most likely,',sum(1 for r in m if r.get('rung')=='alt'),'on a rung')
print(b.get('likely_census'))
for k,v in (b.get('likely_census_by_kind') or {}).items(): print(' ',k,v)"
```

Expect the 9th among the dates, a `20:20` kickoff, and — after the
ladder fix (2026-09-08) — rungs on the Most Likely board where the main
line is a coin flip.

**Where each kind of row died** (`likely_census_by_kind`, 2026-09-08):
one line each for `td`, `prop` and `game`, with `offered` (rows handed
to the board — for `td` that is every quoted scorer, since the same
day), `kept` (cleared the one bar), `duplicate`, `shown` (survived the
per-kind caps) and `refused` by reason. Read it before guessing:

* `td` offered 0 — no scorer menu was bought; check the touchdown
  markets in the event pull.
* `td` offered 40, refused 38 under the floor — the shown number for
  real scorers sits under 55% after the market shrink; that is the
  model, not the feed. Whether the market's number should order those
  rows instead, the way it orders the moneylines, is one command on
  the box that holds the touchdown closes:

  ```bash
  cd /srv/qellys && python3 -m engine.tdbook --rank
  ```

  It prints the model's and the market's ranking of who scores over
  the same joined player-weeks with a bootstrap of the gap. "The market
  ranks scorers better" with an interval clear of zero is the case for
  ranking the scorer rows on the book's number; bring the printout and
  the figure gets written down beside `likely.GAME_RANK_MARKET`.
* `game` offered 16, refused under the floor and the cap — the slate's
  favourites are priced outside -140 to -250, which the board cannot
  help; anything refused as a disagreement is a fault (that bar no
  longer applies to a market-ranked row, §8d). A census still showing hundreds under the floor
with `0 on a rung` means the ladders are not being bought: check
`alt_lines` is non-empty on the recommendations, which needs a paid
event pull (12 credits an NFL game, four of them the `_alternate`
markets).

During the game, the live page and the play-by-play page:

```bash
cd /srv/qellys && ls -la web/data/live_nfl.json web/data/pbp/ | head
```


## 8d. Moneylines on the Most Likely board (2026-09-08)

Ethan: "just barely any money lines." A football moneyline row ranks
on the market's number, and the credibility bar was still refusing it
for the MODEL's disagreement with that number — three eligible
favourites in ten on this repo's NFL closes, four in ten on the college
ones, with no measurable difference
in how the market's number landed on them (docs/LIKELY_GAME_LINES.md,
"The raw claim on a market-ranked row"). The bar no longer applies to a
market-ranked row. Re-measure it where the harvest lives:

```bash
cd /srv/qellys && python3 -m engine.gamerank --sport nfl --raw-bar
cd /srv/qellys && python3 -m engine.gamerank --sport cfb --raw-bar
```

Expect the refused rows' landed rate to sit as near the market's
claim as the kept rows' does. If a band of disagreement lands well
under its claim on the droplet's larger sample, that is the evidence
for a wider bar on that band — bring the printout.

## 8g. Why the wrong moneylines kept coming back (2026-09-08)

Third report in a week, and the first one with a root cause rather than
another stamp. Ethan: "this could be our issue with not showing picks
and shit bc we are pulling the wrong lines. Also that can make us give
fake and false picks that can hurt us."

**The cause.** `oddsapi._request` with `cache_only` serves the cached
payload at ANY age — deliberately, because on a cycle the pacer declines
the last paid pull's real prices beat proxies — and nothing bounded
"any" or recorded which payload a price came off. The board-level
`priced_at` dates the last PULL, not the payload each game was filled
from, and on a cached cycle those are hours apart by design. So no fact
existed that could tell an old price from a wrong one.

That the screenshots were stale rather than mis-mapped is provable
without the box: DraftKings is in `DEFAULT_BOOKS` and `parse_event_h2h`
keeps the BEST price per side across the books we request, so a payload
holding DK at −125 cannot publish −220 for the same team.

**What it costs, measured** on this box's 5,241 college games with both
an opening and a closing moneyline from one book (an opening price being
the extreme stale case):

| | |
|---|---|
| median move | 0.020 |
| 90th percentile | 0.066 |
| 99th percentile | 0.136 |
| open and close named a different favourite | 3.19% |
| moved more than ten points | 3.5% |

One game in thirty priced off a stale pull shows the wrong side as most
likely.

**The fix, as first shipped.** A payload older than
`oddsapi.MAX_GAME_PRICE_AGE` (6h) priced no game market: the game kept
no price, the board said "no real book price", and both builds printed
what they refused and how old it was. Every price that IS attached
carries its own age (`Game.price_age_s`, `priced_from`) onto the card,
the game row and the prop row.

**And then the ceiling had to split in two, the same day.** One hard
ceiling at six hours refused every price the droplet had not re-pulled
inside six hours — which, on a box whose paid pulls are budgeted across
four touchpoints, is most of the day. The boards emptied. Ethan, the
night before the Week 1 opener: "We have barely any moneylines show and
barley and touchdowns shown." So there are now two bars, and only the
wider one refuses:

| knob | default | what it decides |
|---|---|---|
| `QB_MAX_GAME_PRICE_AGE` / `QB_MAX_PROP_PRICE_AGE` | 6h | the FRESHNESS bar. Past it the price is shown with its age on the card, the row carries `price_stale`, and `recommended` is false whatever the edge says. |
| `QB_MAX_GAME_PRICE_SHOW_AGE` / `QB_MAX_PROP_PRICE_SHOW_AGE` | 48h | the SHOW ceiling. Past it the price is refused outright, exactly as the measurement above says it must be. |

The measurement did not change and neither did what it implies about a
stale price — one game in thirty names the wrong favourite. What changed
is the answer to "and therefore what". Between six and forty-eight hours
the honest move is to publish the last paid pull's real number with its
age attached; past forty-eight, no price beats a wrong price.

The two counts are reported separately on purpose. `*_stale_prices`
means REFUSED (the build prints "kept NO price"); `*_shown_stale_prices`
means shown, dated and unrecommended. Adding them together would print
"kept NO price" about a game whose price is on the board.

**Props answer to the same pair of ceilings** (`MAX_PROP_PRICE_AGE` 6h,
`MAX_PROP_PRICE_SHOW_AGE` 48h, each with its own knob). The first cut left them dated
but served; Ethan repeated the ask word for word — "this could be our
issue with not showing picks ... fake and false picks that can hurt us"
— and a pick IS a prop. A per-event payload past the SHOW ceiling
indexes no line, no rung, no menu entry and no scorer quote, so every
prop on that game is proxy-priced and cannot be a pick; the college
quote loop refuses the same way and says so in
`odds_status.player_quotes`. Between the two bars the quotes are kept
and the note says "shown and marked, not recommended". The game and prop
knobs are separate because the two pulls cost differently: game lines
refresh for three credits a slate, props for twelve a game.

Read it on the box:

```bash
cd /srv/qellys && python3 -c "
import json
b = json.load(open('web/data/recommendations.json'))
os_ = b.get('odds_status') or {}
for k in ('source','event_stale_prices','event_stale_age_s',
          'event_stale_prop_events','event_stale_prop_age_s',
          'event_shown_stale_prices','event_shown_stale_age_s',
          'board_stale_prices','board_stale_age_s',
          'board_shown_stale_prices','board_shown_stale_age_s',
          'board_moneylines'):
    if os_.get(k) is not None: print(f'  {k}: {os_[k]}')
ages = [(g.get('matchup'), g.get('price_age_s'), g.get('priced_from'))
        for g in (b.get('game_bets') or []) if g.get('market') == 'moneyline']
for m, a, src in ages[:8]:
    print(f'  {m:<14} {\"never priced\" if a is None else f\"{a/3600:.1f}h\"} from {src or \"?\"}')"
```

* Rows reading `from board` with an age in minutes are the cheap
  whole-slate pull working as intended.
* `event_stale_prices` above zero means the per-event payload is past
  the SHOW ceiling (48h) and those games kept no price at all — buy a
  pull, or widen it with `QB_MAX_GAME_PRICE_SHOW_AGE` (seconds) if the
  budget truly cannot. This should be rare: 48 hours is a box that has
  not successfully pulled in two days.
* `event_shown_stale_prices` / `board_shown_stale_prices` above zero is
  the ORDINARY declined-cycle state, not a fault: those games are priced
  from a pull older than six hours, the cards say so, and none of them
  can be recommended. A high count with a low `board_moneylines` is
  worth a pull; a high count on its own is the pacer doing its job.
* `event_stale_prop_events` above zero is the same fact for the props:
  those games' players are proxy-priced this cycle and none of them can
  be a pick. A board that is thin with this number high is not a quiet
  slate — it is a payload the pacer has not refreshed. Widen with
  `QB_MAX_PROP_PRICE_AGE` only if the plan truly cannot afford the pull;
  the touchpoints (7am, 12pm, 3pm, 6pm ET), the readiness pull three
  hours before kickoff and the closing pull all sit inside six hours
  during betting hours, so the ceiling should only bite overnight.
* Every moneyline missing with `board_moneylines` at zero and no stale
  count means the cheap pull is not running at all — check the pacer.

## 8f. The moneyline that disagreed with its own spread (2026-09-08)

Ethan sent two cards. One is now refused by measurement; the other can
only be diagnosed on the box.

**Refused:** a moneyline further than `likely.SPREAD_COHERENCE` (0.15)
from its own game's posted spread, read through the sport's win curve.
Measured on 1,424 stored NFL closes: a real book's two markets never
name a different favourite and disagree by at most 0.118
(docs/LIKELY_GAME_LINES.md). The census line is "the moneyline
disagrees with this game's own spread by more than any book has".

**Not refused, and this is the one to look at:** MIN -1.5 on his book
with MIN -125, our board showing MIN ML -220. Our spread and our
moneyline agree with each other, so nothing is internally wrong — the
price is simply not the price the book is showing. That is either a
stale pull or a mis-mapped event, and this prints which:

```bash
cd /srv/qellys && python3 -c "
import json, time
b = json.load(open('web/data/recommendations.json'))
os_ = b.get('odds_status') or {}
for k in ('priced_at','lines_priced_at','lines_at','board_moneylines','board_games'):
    v = os_.get(k)
    if isinstance(v,(int,float)) and v > 1e9:
        print(f'  {k}: {(time.time()-v)/3600:.1f}h ago')
    elif v is not None:
        print(f'  {k}: {v}')
print()
for g in (b.get('game_bets') or []):
    if g.get('market') != 'moneyline': continue
    print(f\"  {g.get('matchup',''):<14} {g.get('pick_label',''):<9} \"
          f\"{g.get('odds')}  home_odds={g.get('home_odds')} away_odds={g.get('away_odds')}  \"
          f\"spread={g.get('game_spread')}  book={g.get('book','')}\")"
```

Read it this way:

* `lines_priced_at` hours old with `board_moneylines` at zero means the
  cheap game-lines refresh (`--board-odds`, three credits for the whole
  slate) is not running or is not reaching these games — the moneyline
  on the page is then as old as the last paid prop pull.
* `game_spread` None on every row means no spread was posted for the
  check to read, so the guard above is inert and only the clocks can
  tell you anything.
* prices that match no book on screen while the clocks are minutes old
  is a mapping fault, not a staleness one: send the row and I will walk
  the event map.

## 8e. The college Most Likely board (2026-09-08)

Ethan, after the NFL work: "do all those checks on college football to
make sure none of the [rows] for the most likely [are] thin either."
All three, applied:

| check | college |
|---|---|
| The scorer menu | Was cut to `CFB_WATCH_LIMIT` (20) BEFORE the bar; the board's floor, −250 cap and injury holds then came out of those twenty. The menu leaves `build_cfb_td_longshots` whole now and twenty is the board's `limit` — rows that survive. |
| The market-ranked moneyline | Fixed for both leagues (§8d). College was hit harder: 401 of 1,066 eligible favourites refused (38%) against the NFL's 207 of 681 (30%). |
| The by-kind census | `cfb_build` publishes `likely_census_by_kind` beside the flat census. |

On a Saturday, read the college board the same way as the NFL's:

```bash
cd /srv/qellys && python3 -c "
import json; b=json.load(open('web/data/cfb.json'))
m=b.get('most_likely') or []
print(len(m),'most likely ·',sum(1 for r in m if r.get('kind')=='td'),'scorers,',
      sum(1 for r in m if r.get('kind')=='game'),'game rows')
print(len(b.get('longshot_watch') or []),'on the page shelf (cap 20)')
print(b.get('likely_census'))
for k,v in (b.get('likely_census_by_kind') or {}).items(): print(' ',k,v)"
```

Expect `td` to show `offered` in the hundreds on a full Saturday and
`shown` at twenty. `offered` at twenty exactly means the old truncation
is still in the running build — check the deploy landed. `shown` well
under twenty with a large `refused` count under the −250 cap is the
board working: college prices its bell cows as chalk and the cap is
Ethan's rule.

The college window is narrow, which is worth knowing before reading a
small `shown` as a fault. On this repo's own college fixture the shown
number clears the 55% floor only between roughly −250 and −130 (0.546
at −320, 0.547 at +110): the model reads college scorers flatter than
the market does, and the shrink lands them just under the floor on
either side of that band. Whether the market's number should order
scorer rows instead — the way it orders the moneylines — is
`python3 -m engine.tdbook --rank`, which needs the touchdown closes and
therefore this box. That command walks the NFL replay; the college
equivalent needs `engine.cfbtdfit`'s samples joined to the college
closes and does not exist yet, so read the NFL answer as the leading
indicator and do not assume it transfers.

The college prop half stays empty until a college prop market is
measured (`no market measured to rank yet` in the census); when one is,
the board's player cap goes back to `likely.LIMIT` on its own —
`cfb_build` reads `likely.rankable`, it is not a number anybody has to
remember to change.

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

## 17. The home-run rows on the Most Likely board were graded backwards

`launch.py --likely` on 2026-09-06, per market:

    home_runs   10 rows   said 94.0%   hit 10.0%   ROI -89.71%

Both halves of that are correct and they describe **different bets**.
94% is P(NO home run) — which is the only reason a home-run row is on a
board called Most Likely at all. 10% is roughly how often a hitter
actually homers, which is the bet the journal rewrote it into.

`ledger.log_most_likely` normalised every `LONGSHOT_MARKETS` row to
`side, line = "OVER", 0.5`. The LINE half is why the branch exists: a
"yes/no" scorer row carries no line and `_grade_side_aware` needs one.
The SIDE half was written when this board showed nothing but overs, and
it survived the day the board began admitting unders (2026-09-02).

A home-run OVER cannot reach this board — P(homer) is 0.05-0.15 and
`likely.MIN_PROB` is 0.30 — so **every** home-run row in this bucket is
an under, and every one was inverted. `anytime_td` escaped only because
`from_watch` is its single maker and it always says yes.

WHAT IT WAS WORTH. At the book's flat 0.1u those ten rows are -0.897u of
a -2.094u book: **42.8% of every loss, from 2.4% of the bets.** Without
them the board reads -2.98% rather than -5.08%. They were also the whole
of its worst-looking result — strip them from the 75%+ band and its miss
falls from 18.5 points to 8.3, inside its own +/-10.6% noise band. The
board is not overconfident at the top. Ten rows were graded backwards.

The writer is fixed. These are the rows it already wrote:

```bash
cd /srv/qellys
sudo -u qellys python3 -c "
from engine import ledger
c = ledger.connect()
print(ledger.repair_inverted_likely_sides(c))
"
sudo -u qellys python3 -c "
from engine import ledger
from engine.db import connect as hist
c = ledger.connect()
print('settled', ledger.settle_from_history(c, hist()))
"
sudo -u qellys python3 launch.py --likely
```

(`ingest.py --settle all` does NOT exist — that was wrong in the first
version of this section, and the repair leaves the rows OPEN, so without
a settle they vanish from the scoreboard instead of being counted
correctly. `python3 ledger.py settle --from-db --sport mlb` is the
equivalent through the supported CLI.)

* The repair is deliberately narrow: `home_runs`, in the `likely`
  bucket, `side='OVER'`, `hit_prob > 0.5`. Nothing else. A repair that
  guesses turns one data error into two, and `anytime_td` is excluded
  because an OVER above a coin flip is a real bet there.
* It re-OPENS the rows rather than rewriting their results, so the next
  settle pass grades them through the same path as everything else. Run
  the settle immediately after, or they sit open.
* Expect the flipped count to be about ten, and the second `--likely`
  to show home_runs near its claimed rate instead of 89 points under it.
  Send me the before and after.

## 18. The one number the parlay ledger has never had

Every parlay ticket in the journal has been graded against `assumed_dec`
— the naive product of the legs, less the MID-POINT of a 15-to-30 point
correlation-tax band the doc guesses at. That is not a price. No odds
feed we ingest carries same-game-parlay quotes, and an SGP price cannot
be derived from the leg prices: the whole point of the tax is that only
the book knows it.

Which END of that band a book actually sits on is the entire difference
between a ticket worth taking and a dead one. A ticket that is +EV at a
book taxing 18% is dead at one taxing 26%, and nothing in the model
tells us which book we are at.

So the price has to be typed in by a person. Two commands:

```bash
cd /srv/qellys
sudo -u qellys python3 -m engine.parlayledger open
```

That prints the tickets with no recorded price, newest first — every
ticket, including the ones the screen refused, because the tax is a fact
about a BOOK and a refused ticket is priced by the same book on the same
kind of legs. Then, for any ticket you can see a real SGP price for:

```bash
sudo -u qellys python3 -m engine.parlayledger quote 412 +290 --book dk
```

* **The sign is required.** `340` is +340 to a bettor and 340.0 to a
  parser, and the two differ by a factor of a hundred. A price entered
  wrong is worse than no price, because nothing downstream can tell it
  is wrong. A bare number is refused rather than guessed at.
* **The tax is derived, not asked for.** `1 − quoted/naive`. You type
  what the book shows; the arithmetic is ours.
* **A quote above the naive product is recorded and flagged `boosted`.**
  That is a promo or a typo, never an ordinary SGP price. Recording it
  keeps a real promo in the book; flagging it stops it averaging into
  the by-book table and making that book look cheaper than it is on the
  tickets you would actually take.
* **An already-graded ticket is REOPENED, not rescored in place.** The
  settle pass owns that arithmetic. Run the parlay settle afterwards.

What this unlocks: grading runs on money instead of our assumption, and
the §11 by-book tax table — written months ago and measuring nothing
since, because it divides by a column that was always NULL — starts
filling in. That table is the durable edge here; a handful of real
quotes is worth more to it than any amount of further modelling.

It is a record of tickets somebody went and looked up, not a survey of
the market, so it is worth exactly as much as that sample is
representative. Price the tickets you would have taken AND the ones the
screen refused, or the table measures the tax only where we liked the
bet.

## The NFL calibration store carries figures from a walk that was not one (2026-09-07)

Every NFL walk-forward — `engine.gamecal`'s three, `engine.gamerank`'s
four, `engine.gamebacktest`'s four — sorted the games `ORDER BY period`,
and an NFL period is a WEEK NUMBER that repeats every season. The walk
took week 1 of 2021, 2022, 2023, 2024 and 2025 before week 2 of anything,
and rated each season's early games on results from seasons that had not
happened. And the schedule closes were keyed `(period, home, away)`, so
a same-week rematch a season apart shared a key: 1,359 keys for 1,424
games, 65 graded against another year's line. Fixed to `ORDER BY season,
period` and a season-qualified close key read through
`gamebacktest.close_for`; college was never affected (its period is a
date).

The stored NFL shrinks in `data/feedstate/gamecal.json` were fitted on
the faulty walk and are flattered — moneyline 0.005, spread 0.056, total
0.090. Refit on the corrected walk the slopes are −0.174 ± 0.108,
−0.085 ± 0.076 and −0.136 ± 0.111, which all adopt as 0.0: the NFL game
markets keep NONE of the model's disagreement with the close, which is
the honest output. The nightly refits on its own; to not wait for it:

```bash
cd /srv/qellys && sudo -u qellys python3 -m engine.gamecal --sport nfl --save
cd /srv/qellys && sudo -u qellys python3 -m engine.gamerank --sport nfl --save
```

Expect the first to print the three slopes above and adopt every shrink
at zero, and the second to print `nfl:moneyline: AUC 0.6773 on 1,356`
with the other three under the floor — the second now walks the ratings
the build ships (`gamerank.measure_nfl`), so the store, and the board's
"ranks at", describe the model on the site. NFL spread and total edge bets will go
quiet after the first — that is the measurement doing its job, not a
fault.

THE WALKS NOW READ THE `date` COLUMN WHEN IT IS THERE. Commit 444cbba
gave every game a kickoff date so an NFL bet could have a closing line;
`upsert_games` fills it on the next ingest. `close_for` tries the
game's own date against the harvest first and, where the date is NULL
(this container's copy of the DB predates the column by four minutes),
reads exactly what it read before — the period, then the schedule — so
a box that has not re-ingested is not silently back to the fault above,
it is simply where it was. The walks still ORDER by season and period;
the date is a join key, not the clock. After the nightly has run once
on this box:

```
sudo -u qellys python3 -c "
import sqlite3; c = sqlite3.connect('/srv/qellys/data/history.db')
print(c.execute(\"SELECT COUNT(*), SUM(date IS NOT NULL) FROM games WHERE sport='nfl'\").fetchone())"
sudo -u qellys python3 moneyline_backtest.py nfl
```

The first prints how many NFL rows carry a date; the second, once
they do, reads the harvested NFL closes instead of the schedule's
consensus alone, and its source line says so
("real harvested closes, topped up from …").

## NFL game markets now price a sharp book's disagreement first (2026-09-07)

`engine/pipeline._game_bets` (NFL) got the policy `engine/mlb/pipeline`
has had since baseball's model-alone moneylines measured −12.4%: when
Pinnacle quoted the market, the card prices the soft book's number
against Pinnacle's de-vigged fair; when it did not, the model card is
built as before and shown as information — never recommended, never
staked. The NFL model's own disagreement with the close was measured
worthless every way the database allows (docs/NFL_MONEYLINE_ARITHMETIC.md).

WHETHER THE SHARP PATH IS LIVE depends on one thing: Pinnacle answering
NFL `h2h`, `spreads` and `totals` in the odds pull. `DEFAULT_BOOKS`
requests it. After a build, count it:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json
b = json.load(open("web/data/nfl_board.json"))
g = [r for r in b.get("recommendations", []) if r.get("market") in ("moneyline", "spread", "total")]
rec = [r for r in g if r.get("recommended")]
print(len(g), "NFL game cards,", len(rec), "recommended (sharp-anchored),",
      sum(1 for r in g if any("sharp-anchor" in w for w in r.get("warnings", []))), "info-only")
EOF
```

Zero recommended with many info-only means Pinnacle is not in the NFL
payload, and the fix is on the odds side (the book, the region, the
budget), not in the pipeline. Also worth one look:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import db; c = db.connect()
print(c.execute(\"select book, market, count(*) from odds_history where sport='nfl' and market in ('moneyline','spread','TOTAL') group by book, market\").fetchall())"
```

THE EDGE BAR ON A SHARP CARD IS THE NEXT LEVER, and the droplet holds
the measurement. A game card's context is fixed at 35 points, so its
grade is its edge alone: B+ needs about 3.3 percentage points on a
moneyline, and at even money that is 7% of EV — exactly where the
pricer calls a gap suspect. Near a coin flip the sharp path shows and
never stakes; on a favourite it stakes in a narrow window
(tests/test_nfl_sharp_first.py has the arithmetic). That bar was set
for MODEL edges, which are noisy; a price-versus-price edge is not. The
MLB replay already buckets sharp-anchored bets by EV — `<4%`, `4-8%`,
`8-15%` — on a season of harvested Pinnacle closes:

```bash
cd /srv/qellys && sudo -u qellys python3 moneyline_backtest.py mlb
```

If the `<4%` bucket pays over a few hundred bets, the bar on
sharp-anchored game cards should come down to meet it — a grade band
is money, so that is a change to make WITH the number, not before it.
If it does not pay, the narrow window is the right window and nothing
moves.

THE RETROSPECTIVE GRADE READS `games.date`. `backtest_sharp_anchor`
keys the harvest by the date it was taken; the walk keyed by `period`,
which for the NFL is a week, so the two never joined and it priced zero
NFL games in silence — the same reason the NFL harvest never joined
`gamecal`. `close_for` now tries the game's own kickoff date first
(tests/test_harvest_joins_by_date.py), so once the nightly re-ingest
has filled the column here, this strategy can be graded over the
season it has run:

```
sudo -u qellys python3 -c "
from engine import db; from engine.gamebacktest import backtest_sharp_anchor
print(backtest_sharp_anchor(db.connect('/srv/qellys/data/history.db'), 'nfl').summary())"
```

`python3 moneyline_backtest.py nfl` prints the same summary after the
model walk. "0 with both a Pinnacle pair and a soft price" followed by
"No games priced — harvest Pinnacle closes first" means the column is
still NULL on this box (see the count above), not that Pinnacle was
never harvested — check the count before harvesting anything. Until it
prints games, the CLV ledger is the grade: every recommended NFL game
card is journaled with its price and settled against the close.

## CFB game markets price a sharp book's disagreement first (2026-09-07)

Ethan: "make sure you do the same exact work to make CFB just as good."
`cfb_build` got the NFL's policy on college's own measurement
(`engine.cfb.pipeline.CFB_MODEL_GAME_RECOMMENDATIONS` has the table:
moneyline −0.079 ± 0.067, spread −0.037 ± 0.040, total +0.115 ± 0.060
with 52.4% of sides beating the close, on 2,016–2,055 games). The
build reads Pinnacle's own pair out of the same events the soft prices
come from (`_sharp_for`), prices each market it quoted through the
shared sharp pricers (`sharp_game_bets`), and demotes every
ratings-priced card — play, conditional, refusal — to information
after its verdict. The college build's `_books_for` had been skipping
`SHARP_BOOKS` for months without anything reading the sharp pair, so
this is the first time a Pinnacle number reaches a college card.

WHETHER THE SHARP PATH IS LIVE is the same question as the NFL's:
Pinnacle answering college `h2h`, `spreads` and `totals` in the odds
pull. After a build with odds:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json
b = json.load(open("web/data/cfb.json"))
g = b.get("game_bets", [])
sharp = [r for r in g if r.get("sharp_anchored")]
print(len(g), "CFB game cards,", len(sharp), "sharp-anchored,",
      sum(1 for r in sharp if r.get("recommended")), "recommended,",
      sum(1 for r in g if any("sharp-anchor" in w for w in r.get("warnings", []))),
      "model cards shown as information")
EOF
```

The build log prints the same split: "N sharp-anchored card(s), M of
them picks; K model market(s) → J model play(s) shown as information".
Zero sharp-anchored cards across a full Saturday means Pinnacle is not
in the college payload — the fix is on the odds side, not in the
pipeline. A sharp card refused with "Neither side is in a conference
this board bets" is the Group of Five rule (Ethan, 2026-09-02) holding
for sharp cards too; lifting it for them is one constant
(`engine.cfb.model.BET_GROUP_OF_FIVE`) and a decision to make with the
college sharp-anchor replay's numbers in hand.

## Player props price a sharp book's pair first, where one exists (2026-09-07)

Ethan: "I want all of that tuned in exactly how you just did" — props,
touchdown props, spreads and totals. The game markets got sharp-first
on 2026-09-07 (both football boards and baseball); the player props
had no sharp path at all: `oddsapi.parse_event_lines` dropped the
sharp book on purpose (nobody here can bet it) and nothing read the
pair it dropped. `parse_event_sharp_lines` reads it now, the pair rides
on `Prop.sharp_lines`, and `betting.evaluate_prop` prices the shopped
soft quote against the sharp pair AT THE SAME LINE when there is one
(`sharp_anchor_for`): the card's probability is the sharp book's fair,
its edge the soft price's distance from it, the model's read kept as
context, inside the same EV bands as every sharp game card. Where the
sharp book quoted nothing — the common case outside the main markets —
the model card prices exactly as before.

WHETHER THE SHARP BOOK QUOTES NFL PROPS AT ALL is the droplet's
question, and the board answers it on every row:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json
b = json.load(open("web/data/nfl_board.json"))
rows = [r for r in b.get("recommendations", []) if r.get("has_market")]
print(len(rows), "priced props;", sum(1 for r in rows if r.get("sharp_quoted")),
      "quoted by the sharp book;", sum(1 for r in rows if r.get("sharp_anchored")),
      "priced against it;", sum(1 for r in rows if r.get("sharp_anchored") and r.get("recommended")),
      "recommended")
EOF
```

Zero `sharp_quoted` on a full Sunday board means the sharp book is not
answering player markets in this region or plan, and the fix is on the
odds side. A prop quoted but not anchored means the sharp pair sat at
a different line from the shopped one — a fair at 75.5 says nothing
about a bet at 76.5, so the model card priced it.

COLLEGE TOO. The evaluator is shared, so the same path prices college
props the moment the pair reaches the prop: `cfb_build.
attach_player_quotes` fills a `sharp` out-parameter from the same
per-event payloads and `engine.cfb.props.attach_lines` puts it on each
matched prop. The same count, on `web/data/cfb.json`, answers whether
the sharp book quotes college player markets at all — expect fewer
than the NFL's; a sharp book prices college props thinly. The
touchdown boards need nothing: their fair has always been the median
de-vigged price across every book that quoted the player, the sharp
one included (`engine.devig.board_fair`), so a touchdown pick has been
price against price since the day the board shipped.

THE MODEL PROP CARDS ARE NOT DEMOTED, and the reason is a measurement
that only this box can make. The game cards went informational because
`gamecal` and the information tests measured the model's disagreement
with the close as noise, on this container's schedule closes. The prop
model's disagreement with a real close has been measured for two
markets only — `engine/formbook.py`, rush_yds 0.468 and rec_yds 0.477
against harvested closes, both already shut by their calibration — and
never for receptions, pass_yds or anytime_td, because the prop closes
live in this box's `odds_history` and nowhere else. The command that
decides, per market, once a season of prop closes is in:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import db, formbook
conn = db.connect()
for m in formbook.MARKETS:
    out = formbook.scan(conn, m)
    if out.get('skipped'):
        print(m, out['n'], 'pairs —', out['skipped']); continue
    r = out['best_brier_r']; d = out['dial'][r]
    print(m, out['n'], 'pairs; best dial', r, 'AUC', round(d['auc'] or 0.5, 3), 'z', round(d['z'] or 0, 1))"
```

A market whose best dial still leaves AUC at a coin flip on four
hundred or more pairs gets what the game cards got: its model card
shown and never recommended, with only the sharp path and the stale
shadow book able to make it a pick. That is a one-constant change per
market, made WITH the number.

## The college information test, and the one number it left to re-read (2026-09-07)

`python3 -m engine.cfbinfo` asks college the NFL's question: with the
closing number as a fixed offset, does any input on disk — the
rating's gap, the starting quarterback, rest and byes, a neutral site,
form drift — still predict the outcome? Fitted on 2022-23, judged on
2024-25: nothing holds, and the table is in the module note. The one
near miss is a change of starting quarterback (−0.392 ± 0.114 on the
fit seasons, −0.172 ± 0.114 held out, the same sign). It is
pre-registered on `engine.cfbinfo.QB_CHANGE_WATCH`. When the 2026
season has been ingested — the box's `player_game_logs` carry
college `pass_yds` for the season's dates — run it on the droplet
with the test seasons extended:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import sqlite3
from engine import db, cfbinfo
conn = db.connect(); conn.row_factory = sqlite3.Row
rows = cfbinfo.build_rows(conn)
for line in cfbinfo.report(rows, train=(2022, 2023), test=(2024, 2025, 2026)):
    if "qb_change_diff" in line or "information test" in line:
        print(line)
EOF
```

The `qb_change_diff` moneyline line's TEST cell decides, alone and
unpooled: beyond two standard errors (the `**`), a fitted qb-change
term enters the college moneyline pricing; short of it, the watch
stays a record of a near miss. Nothing is re-fitted on the way to that
reading, and nothing in the pipeline reads the watch today.

## The college sharp-anchor replay, and the command that runs it (2026-09-07)

`backtest_sharp_anchor` — the season replayed betting only the shopped
soft close against Pinnacle's de-vigged pair — is the retrospective
grade for the strategy the college edge board now runs on. It never
needed a college branch: a college `period` is a date, the key every
harvest is filed under. What was missing was the command:

```bash
cd /srv/qellys && sudo -u qellys python3 moneyline_backtest.py cfb
```

College prints the sharp-anchor replay alone — its model is measured
by `python3 -m engine.gamecal --sport cfb` and `gamerank.measure_cfb`,
which walk the opponent-adjusted ratings the board ships, not by the
plain walk the pro leagues get here. "0 with both a Pinnacle pair and a
soft price" means no college moneyline close has been harvested on
this box yet, not that the join failed. The nightly harvest is driven
by the journal (`maintenance._harvest_targets`): the first Saturday a
college sharp card journals a moneyline, the next morning's harvest
pulls that day's college `h2h` closes across `DEFAULT_BOOKS`, Pinnacle
included, and the replay starts filling. To backfill a stretch by
hand, the summary prints the command with the sport already in it.

## The Most Likely board showed only tight ends for receiving (2026-09-07)

Ethan: "for some reason its only displaying tight ends for reciving
props and thats it." The cause in the code: the board kept the forty
highest probabilities across every player market in ONE list, and the
highest probabilities belong to the lowest lines — a tight end or a
back over 2.5 receptions at 68% — so the forty filled with those and a
receiver's honest 58% on 64.5 yards never reached the receiving shelf.
`likely.build` now cuts in two passes (`likely.PER_MARKET`, eight per
market, then the best of the rest to forty). The floor Ethan chose on
2026-09-06 (55%), the −250 price cap and the credibility bar are
untouched, so a market whose every row sits under 55% still shows
nothing — and receiver yardage lines are set at the median, so many of
those rows DO sit under it. Read the census before concluding the
board is wrong:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json, collections
b = json.load(open("web/data/nfl_board.json"))
rows = b.get("most_likely") or []
print("rows by market and position:")
for (m, pos), n in sorted(collections.Counter((r.get("market"), r.get("position") or "?") for r in rows).items()):
    print(f"  {m:12s} {pos:4s} {n}")
print("refused:", b.get("likely_census"))
EOF
```

`under the likelihood floor` counting most of the refusals is the
floor doing what it was asked to; a receiving shelf with no receivers
after this change means their rows were under it, not that they were
cut for a tight end's.

**Later the same day this was not the whole story** — see "The Most
Likely board judged sharp-quoted props on the sharp book's coin flip"
below. The two-pass cut was real and stays; the reason the census then
still read almost entirely `under the likelihood floor` was the second
defect.

## Touchdown flags are sampled by the stale shadow book now (2026-09-07)

Ethan: "you worked on the NFL and CFB TD Model and made it better."
The best-measured signal here — a book a point under the field's
consensus beat the close 64.8% of the time — was sampled at a flat
0.1u on yardage props and never on the one prop market the football
edge boards actually stake, the anytime touchdown. Two gaps, both
closed: `price_props` skips the touchdown market (the long-shot board
prices it), so no touchdown row ever reached `stale_quotes`, and the
journal's settleable set had no `anytime_td`. Now every touchdown
quote on both boards reaches the scan (`pipeline.td_scan_rows`,
`cfb_build.td_scan_rows` — one row per player, every book's Yes/No as
a line at 0.5), a flag journals as OVER 0.5, category 'stale', and it
settles from the same `anytime_td` game-log rows the long-shot book
grades on. After a Sunday and a Saturday with player odds:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import ledger; c = ledger.connect()
for sport in ('nfl', 'cfb'):
    print(sport, c.execute(\"select market, status, count(*) from bets where sport=? and category='stale' group by market, status\", (sport,)).fetchall())
print(ledger.stale_verdict(c))"
```

`anytime_td` rows appearing under each sport is the wiring working;
their settling is the game logs arriving (the NFL's weekly stats, the
college box scores). The per-sport verdict pools every market's flags
— when the touchdown rows are a large share of a sport's book, read
the market split above before trusting the pooled hit rate, because
+300 flags and −110 flags do not share a break-even (the verdict
averages the break-even of the prices actually taken, so it is
honest, but a market cut is the next thing to want).

## College runs the stale-line scan now (2026-09-07)

`cfb_build` shipped `market_scan` as an empty literal from the day it
was written — no college stale flag was ever shown, journaled or
judged, while the NFL and MLB builds have sampled theirs at a flat 0.1u
since the signal measured 64.8% against the close. The college board
now runs the shared scan (`engine.pipeline.market_scan`, the NFL's
under its public name) over its priced props and long shots, and
journals the flags to the shadow book, category 'stale', settled from
the same college game logs as the props. After a Saturday with player
odds:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json
b = json.load(open("web/data/cfb.json"))
st = (b.get("market_scan") or {}).get("stale") or []
print(len(st), "college stale flag(s) on the board;",
      sum(1 for r in st if r.get("market") in ("pass_yds", "rush_yds", "rec_yds", "receptions")),
      "settleable")
EOF
sudo -u qellys python3 -c "
from engine import ledger; c = ledger.connect()
print(c.execute(\"select status, count(*) from bets where sport='cfb' and category='stale' group by status\").fetchall())
print(ledger.stale_verdict(c).get('cfb'))"
```

The build log's journal line now carries the count ("+ N stale
flag(s)"). Zero flags on a Saturday the board bought player odds means
fewer than three books quoted the same line on every prop — the scan
needs a crowd — not that the scan did not run; `market_scan_error` on
the result is the only way it fails. The verdict's `cfb` key appears
with the first settled flag and reads "hold" until two hundred of them
have settled; that is the sample the college promotion decision waits
on, exactly as the NFL's does.

## The three numbers that decide the next NFL moves (2026-09-07)

Everything a model could compute has been measured against the NFL
close and carries nothing (docs/NFL_MONEYLINE_ARITHMETIC.md). What is
left is prices, and three price-based measurements live only on this
box. Each one decides a specific change; none of the changes is made
until its number is in.

**1. Is the sharp path live for NFL game markets?** (decides nothing in
code — it says whether Pinnacle is in the payload.) The count under
"NFL game markets now price a sharp book's disagreement first" above.

**2. Do small sharp-anchored edges pay?** (decides whether the grade
bar on a sharp card comes down.) `python3 moneyline_backtest.py
mlb` — the `<4%` EV bucket over a few hundred bets.

**3. Do stale-line flags cash?** (decides whether the best-measured
signal in the repository becomes a pick.) Every flag has been a 0.1u
shadow bet since the scanner shipped, the NFL's since its build began
journaling them; `ledger.stale_verdict` reads that book PER SPORT and
says, by arithmetic, whether the flags have earned it — 200 settled
flags, a hit rate two standard errors over the break-even of the prices
actually taken, positive flat-stake ROI:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
import json; from engine import ledger
print(json.dumps(ledger.stale_verdict(ledger.connect()), indent=1))"
```

It is also in the nightly report as `stale_verdicts`. A sport reading
`promote` is the go-ahead for the follow-on change: stale flags in that
sport journaled to the main book at a real stake and shown on the edge
board as picks — a change to make WITH the verdict, which is why the
function promotes nothing itself. A sport reading `hold` says which
guard held it. The NFL's book is a few weeks old and will read "needs
200" for a while; that is the honest answer and not a fault.

For the NFL-specific closing-line check behind the 64.8% figure (which
was measured on baseball's harvest): `python3 stale_lines.py --sport
nfl`, once the NFL harvest holds a few weeks of closes.

## The price tape now stores the sharp book too (2026-09-07)

Ethan, 2026-09-07, setting the data plan: "A price database. Timestamped
quotes from every book, Pinnacle included, from open to close, for game
lines and props in both leagues. Every edge we can measure is a
comparison of prices."

Both measured edges here ARE comparisons of two prices — the sharp
anchor (+13.5% on the MLB replay) and the stale-line flag (64.8% CLV on
30,448 quotes) — and until now only one side of the comparison was
being written down. Every build parses the sharp book's own two-sided
pair (`apply_odds_to_slate` and `apply_board_lines_to_slate` hang it on
the game as `sharp_home_ml` / `sharp_total` / `sharp_spread` and their
prices; `cfb_build._sharp_for` puts the same pair on its entry), prices
against it, and dropped it. `engine/lineledger` now writes those rows
under `book = 'Pinnacle'` beside the shopped `book = 'best'`, on all
three sports. It costs nothing: the numbers were already in memory.

The spelling matters. It is the API's DISPLAY title because that is
what the historical harvest stores, so a build row and a harvested row
for the same book join instead of forming two tapes.

After a slate with paid odds, both books should be present:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import db
c = db.connect()
for sport in ('nfl','cfb','mlb'):
    rows = c.execute('SELECT book, market, COUNT(*) FROM odds_history '
                     \"WHERE sport=? AND player!='' GROUP BY book, market \"
                     'ORDER BY book, market', (sport,)).fetchall()
    print(sport, [tuple(r) for r in rows] or 'no rows yet')"
```

A sport showing `best` rows and no `Pinnacle` rows means the sharp book
was not in the payload for those pulls — check `DEFAULT_BOOKS` still
carries pinnacle and that the pull was not book-filtered. It does NOT
mean the join is broken.

## The reserve no longer skips the close (2026-09-07)

Ethan, 2026-09-07: "Add an intraday snapshot loop through the betting
window, and stop letting the 500-credit reserve skip the close."

The intraday loop already exists — `prime_window` opens 2.5 hours before
the first kickoff and `PRIME_BURST` triples the sport's share inside it,
so the day's credits already concentrate on the betting window. The
close did not. Below `RESERVE` the pacer authorised nothing but a
six-hourly recovery probe, and the daily ceiling refused on its own
account, so on a thin month the last pull before kickoff was exactly the
pull that never happened — and every bet that week settled with no
closing line, which means no closing-line value and no process grade.

`oddsbudget.closing_window` now names the last half hour before the next
kickoff, and a pull inside it is authorised past both refusals. The
exemption is deliberately narrow and each bound is load-bearing:

  * only a CHEAP pull (`CLOSE_MAX_CREDITS`, 8). The board endpoint bills
    three credits for a whole slate; the event endpoint bills eight PER
    GAME, and letting that through would drain the reserve it is carved
    out of;
  * once per window per sport, enforced by the sport's own refresh clock
    rather than by new state;
  * never below `CLOSE_FLOOR` (50 credits);
  * `MIN_REFRESH_GAP` still applies, as it does to the touchpoint
    override.

A staggered Sunday gets one close per wave, which is right — each wave
has its own closing number. Cost is three credits a wave.

To see the closes being bought, read the decision log for the phrase:

```bash
cd /srv/qellys && sudo -u qellys grep -h "closing window" \
  data/cache/odds_decisions*.jsonl | tail -20
```

No lines on a day with kickoffs means either the pull was declined for
another reason earlier in the chain (the log names it) or the cheap tier
was not the one asking. It does NOT mean the exemption is broken.

## Injury designations get a first-seen stamp (2026-09-07)

Ethan, 2026-09-07, on the data a winning model needs: "News timing.
Injuries, inactives, quarterback changes, weather, each timestamped. The
value is not knowing, it is knowing before the soft books move."

The injuries page has read ESPN's keyless league feed since 2026-08-10
and keeps only the CURRENT board — `espninjuries.current_rows` holds the
newest filing per player, so a designation four minutes old and one
standing since Tuesday were the same row and "did the soft books move
after this filing" could not be asked. `engine/newstape.py` now writes
one `injury_events` row the first time it sees each (sport, player,
status, posted_at), stamps `first_seen` with OUR clock, and never
rewrites it (INSERT OR IGNORE). A player moving Questionable to Out is a
second row, because that move is the news. Only designations a book
would reprice on are kept; "Active" is not news.

The stamp is minute-resolution UTC in the same format `engine/lineledger`
uses for `odds_history`, because the two tables exist to be read against
each other: the gap between `first_seen` and a price moving is the
interval an edge could live in. Nothing measures that yet — a
measurement needs a sample, and a sample needs the timestamps written
down first.

After a few injury-build cycles on a football week:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import db
c = db.connect()
for r in c.execute('SELECT sport, status, COUNT(*), MIN(first_seen), MAX(first_seen) '
                   'FROM injury_events GROUP BY sport, status ORDER BY sport, 3 DESC'):
    print(tuple(r))"
```

An empty table after a day means `injuries_build` could not open the
history DB — its printed notes will say `news timing not recorded`.

## The nightly harvest walks back for missing closes, inside one day's budget (2026-09-07)

Ethan, 2026-09-07: "set the harvest floor to 1000 and day budget 400 and
lets keep going."

`HARVEST_MIN_REMAINING` is 1000 (was 3000) and `HARVEST_DAY_BUDGET`
stays 400. The nightly now harvests yesterday first, then walks back up
to thirty days for any day that journaled bets and holds no close in
`odds_history`, newest first. Spend is metered from the API's own
remaining count: each run is told only what is left of the day's 400,
and the walk stops when the day is spent or the balance would drop under
the floor. It never hands a run a fresh 400.

To see what it did last night:

```bash
cd /srv/qellys && sudo -u qellys grep -h "closes" data/logs/maintenance*.log | tail -20
```

`closes (nfl 2026-09-06): Harvested …` lines are the walk. A line
ending `waits for tomorrow's walk` means the day's budget ran out with
days still owed — the next night continues from the newest owed day. A
line reading `auto-harvest skipped (quota N, reserve 1000)` means the
month is under the floor and nothing was spent.

## The ballpark cards read the fast clock too (2026-09-07)

Ethan, 2026-09-07, two screenshots taken at the same moment: the
dashboard card showed one runner on, the game centre showed two. "So
something is delayed."

It was, and by design of two clocks. The board file behind the dashboard
cards (`data/mlb.json` and its siblings) is rebuilt on the minutes-long
cycle — the header's "Updated 5m ago" — while the game centre and the
Live tab read the fast scoreboard (`data/live_mlb.json`, seconds). The
bases, outs and score on a ballpark card were therefore minutes behind
the same numbers one tap away. The fast rows were already being fetched
for the league so the play-by-play door could open instantly; they were
never merged into the cards. `mergeFastLive` now does that with the same
merge the Live tab uses (fast fields win, board-only fields survive), and
`armDashLive` re-reads the scoreboard every sixteen seconds while a game
is on, redrawing only when a live fact moved.

The phone was never a separate problem. The service worker has never
cached `/data/`; the phone had loaded the board a few minutes earlier
than the laptop and was reading an older copy of the same slow file,
which is exactly the gap this closes.

To confirm the two clocks now agree, open the dashboard beside the game
centre during an inning with a runner on and watch the card's diamond
change within about sixteen seconds of the game centre's.

## The market's ranking figure is re-measured here, not in the suite (2026-09-07)

Ethan, 2026-09-07, with a screen of failed GitHub runs: "The nightly is
failing a lot too so idk if it's even doing anything like we think."

Two different "nightlies", and the emails are about the wrong one. The
GitHub workflow called `nightly` is a repository health check that runs
the test suite on GitHub's machines; it has no databases and no built
boards and cannot touch the droplet. The droplet's nightly — the settle,
the harvest, the backfill — runs inside `launch.py` on this box and
writes its own log (`grep -h closes data/logs/maintenance*.log`). One
failing does not mean the other is.

WHAT WAS FAILING, and it was mine. `tests/test_likely_ranks_on_market.py`
re-measured the 0.722 / 0.7905 market figures by opening the real history
database. Green on any box with closes; on GitHub's clone, which has
none, the AUC helper returned None and the file crashed — every `tests`
and `nightly` run from 47ec2b7 through fbf4aaf failed on exactly that
line. The suite's own rule (`run_tests.py`, and test_td_xfp.py spells it
out) is that it must not read the box it runs on. The measurement now
lives in `gamerank.measure_market_moneyline`, beside the model's, and the
test proves it on a synthetic book and pins the constants.

Re-measure the real figures here whenever the closes have grown:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import db, gamerank, likely
c = db.connect()
for sport in ('nfl', 'cfb'):
    r = gamerank.measure_market_moneyline(c, sport)
    print(sport, 'market', r.auc, 'on', len(r.pairs), 'games —',
          'carried', likely.GAME_RANK_MARKET[sport]['moneyline'], '·', r.note)"
```

If a re-measured figure drifts more than half a point from the carried
constant, update `likely.GAME_RANK_MARKET` and the test's pinned values
together, in one commit that quotes this command's output.

## The Most Likely board judged sharp-quoted props on the sharp book's coin flip (2026-09-07)

Ethan, 2026-09-07, evening: "you said you did model work but i dont
see any changes for nfl in the edge bets or the most likley bets. it
just shows 2 tight end reception props. there is no rushing props for
running backs or any recieving props for wr, that makes it feel like
something is off or irs broken."

It was broken, and the sharp-anchor change for props broke it. When
the sharp book quotes a prop two ways at the shopped line, the card is
priced from that pair and its `hit_prob` becomes the sharp book's fair.
A sharp line is hung where the sharp book thinks the coin is fair, so
that number is 50–53% for every prop it quotes. `likely.from_prop` read
`hit_prob` against the 55% floor — so every prop the sharp book quoted
was refused before the model was consulted, and the board showed only
what the sharp book did NOT quote. On Week 1's menu that was two
tight-end receptions rows.

Two fixes. The card's `raw_prob` on an anchored row is now the MODEL's
read of the side rather than a second copy of the sharp fair (which was
also feeding the calibration fitter the sharp book's calibration as if
it were ours). And the board judges an anchored row's floor on that
number, shows the mixture exactly as before, and carries the sharp fair
on the row as `sharp_fair` beside it. The Edge board is untouched: a
pick there still needs the sharp pair and its EV bands.

Confirm on the next NFL build after this deploys — the census's floor
count should fall and the shelves should hold backs and receivers:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json, collections
b = json.load(open("web/data/nfl_board.json"))
rows = b.get("most_likely") or []
print("refused:", b.get("likely_census"))
anch = [r for r in rows if r.get("sharp_anchored")]
print(len(rows), "rows on the board,", len(anch), "of them sharp-quoted")
for (m, pos), n in sorted(collections.Counter((r.get("market"), r.get("position") or "?") for r in rows).items()):
    print(f"  {m:12s} {pos:4s} {n}")
for r in anch[:6]:
    print(f"  {r['player']:<22} {r['market']:<10} {r['side']:<5} {r['line']}  model {r['model_prob']:.0%}  sharp fair {r['sharp_fair']:.0%}")
EOF
```

The census now names the two refusals the mixture makes — `under the
likelihood floor after calibration` (the raw claim cleared 55%, the
calibrated number did not) and `disagrees with the market by more than
we credit` (the calibrated number sits more than ten points from the
book's fair). Until 2026-09-07 both were silent, so an empty board
under-reported its own refusals by the whole of that count.

`sharp-quoted` at zero on a Sunday menu with Pinnacle posting means the
odds pull did not carry the sharp book (`sharp_quoted` on the prop rows
of recommendations.json says whether it was quoted at all), which is a
different problem from this one.

## The model reads the live injury board now, not just the weekly report (2026-09-07)

Ethan, 2026-09-07: "Confirm all of our models and game scripts and all
of that are updating to live injuries. An example is RB2 Isiah Pacheco
is now out till October 11th so RB 1 Jahmyr Gibbs should be seeing a
lot more usage ... make sure we are adjusting if needed and reading
this data and adjusting everything live and everything is up to date."

WHAT WAS TRUE BEFORE THIS. The NFL slate's injuries came from one
source, nflverse's weekly report: the club's filed designation
(Questionable / Doubtful / Out), re-downloaded at most twice a day
(`fetch.DEFAULT_TTL`), applied on every NFL build. It holds the
injured man's own props and applies the knock-on multipliers
(opposing CB1 / slot CB / DT out, own LT / OT out). It does NOT list
a man placed on injured reserve — he is off the active roster and
files nothing — and it cannot list a Saturday move. ESPN's
current-status board, which the injuries page and the news tape have
read since August, had the reserve move and the return date; nothing
carried it to the model. The game script (`engine/gamescript.py`)
reads no injury feed at all; it moves with the spread and total, which
the market has already moved for a star's absence.

WHAT CHANGED. `injuries.live_injuries` turns ESPN's NFL board into the
same `Injury` objects the weekly report produces, `merge_injuries`
lays it over the weekly report (a man on both keeps the more severe
designation; Questionable / Doubtful age out after seven days; OUT and
IR stand), and `nfl_build --injuries` — which the launcher always
passes — fetches it under its own guard and hands the merged list to
the slate. The board is cache-served inside `espninjuries.INJURY_TTL`
(ten minutes), so the model is at most ten minutes plus one build
behind ESPN. When nflverse's file is a 404 (every week before it
publishes a season's first) the live board now carries the slate
alone instead of the slate going out with no injuries at all.

WHAT IS STILL NOT DONE, AND WHY. A back on reserve does not lift the
next back's projection. `engine/redistribute.py` measures that
redistribution from the weekly stats (share of the team's carries in
the games the starter played against the games he missed), and the
information test (`docs/THE_INFORMATION_TEST.md`) is why it is not
priced: over 307 settled bets the model's disagreement with the price
ranked winners at AUC 0.479 — the model contributes nothing beyond the
price — so a new input into the grade, a share multiplier included, is
the exact move that finding rules out until a measured input beats the
close. Feeding a measured share into the projection is that pricing
change, and it waits. The hold is what protects the board
today: the man who is out is held, and the man behind him is priced
on his own logs and the book's line, which already knows.

Confirm on the box after this deploys:

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json
b = json.load(open("web/data/recommendations.json"))
s = b.get("injury_status") or {}
print("source:", s.get("source"), "| weekly:", s.get("weekly"), "live:", s.get("live"),
      "only on the live board:", s.get("live_added"), "| holds:", s.get("holds"))
print("by status:", s.get("by_status"))
print("errors:", s.get("error"), "/ live:", s.get("live_error"))
EOF
```

`live` at None means the build never asked ESPN (the launcher stopped
passing `--injuries`); `live` at zero in-season with `live_error` empty
means the cached board parsed to nothing — run `python3 launch.py
--injuries` to see the raw board and its age.

**What the first run printed (Ethan, 2026-09-07, a Monday):** `weekly:
0 live: 262 only on the live board: 262 | holds: 66`, with 56 of the
holds on Questionable. Two things to read in that. `weekly: 0` with no
error means nflverse's file answered but had no rows for the week the
build asked for — the model had been pricing with NO injuries until the
live board arrived. And 56 Questionable on a Monday were Friday's
designations for games already played; the first cut aged them on a
flat seven days. They now age by the slate's own week (`week_starts`:
five days before each team's game date), so the count of Questionable
holds on a Monday or Tuesday should be near zero and rise from
Wednesday. If `weekly` stays at 0 into a week nflverse has published,
check `data/cache/injuries_<season>.csv` has rows for that week.

To ask about one man across both feeds and see whether the slate holds
him:

```bash
cd /srv/qellys && sudo -u qellys python3 launch.py --injuries "Isiah Pacheco"
cd /srv/qellys && sudo -u qellys python3 -c "
import json
for r in json.load(open('web/data/recommendations.json'))['recommendations']:
    if 'Pacheco' in r['player']: print(r['player'], r['market'], r['recommended'], r['injury_status'])"
```

A man on reserve should print `IR` in the last column on every row he
still has, and `recommended` False. If the books have pulled his props
he prints nothing, which is the same fact from the other side.

## The football pulls buy the alternate ladders, and the Most Likely board stands on them (2026-09-07)

Ethan, after the census: "i prefer to do whatever gives us props and
picks every single day ready for every game at least 3 hours before. i
want to prioritize NFL and CFB over anything so if we gotta limit MLB
pulls im ok with that."

WHAT CHANGED. The NFL and college event pulls ask for the four
`_alternate` player markets. A rung lands on `Prop.alt_lines`, apart
from the shopped main line, and `likely.from_prop` picks the likeliest
rung that clears the same bars the main line answers to — see
docs/LIKELY_GAME_LINES.md, "The alternate ladder". An NFL event call
costs twelve credits now, a college one nine; the pacer meters each
league at its own price (`oddsbudget.credits_per_event`).

THE DEPLOY-DAY MISS. The cache file is named by the market list, so the
first cached rebuild after this deploys finds no payload under the new
name. Both attach steps fall back to the last paid pull's base-market
payload (`alt_fallback` in the attach result) until the next paid pull
buys the ladders; the board keeps its main lines and game prices
through the gap.

Confirm after the first PAID NFL pull on the new code (the decisions
ledger says when one landed):

```bash
cd /srv/qellys && sudo -u qellys python3 - <<'EOF'
import json, collections
b = json.load(open("web/data/recommendations.json"))
props = b.get("recommendations") or []
with_ladder = [r for r in props if r.get("alt_lines")]
print(len(props), "prop rows,", len(with_ladder), "with a ladder,",
      sum(len(r["alt_lines"]) for r in with_ladder), "rungs in all")
rows = b.get("most_likely") or []
print("refused:", b.get("likely_census"))
print(len(rows), "rows on the board;", sum(1 for r in rows if r.get("rung") == "alt"), "on a rung")
for (m, pos), n in sorted(collections.Counter((r.get("market"), r.get("position") or "?") for r in rows).items()):
    print(f"  {m:12s} {pos:4s} {n}")
for r in rows[:8]:
    tag = f"rung of {r.get('main_line')} ({r.get('main_odds')})" if r.get("rung") == "alt" else "main line"
    print(f"  {r['player']:<22} {r['side']:<5} {r['line']:>6} {r['market']:<10} {r['odds']:>5}  {r['model_prob']:.0%}  {tag}")
EOF
```

`with a ladder` at zero after a paid pull means the books are not
posting alternates for this slate yet (they post them later in the
week than main lines) or the request did not carry them — check the
spend ledger's `detail` for `_alternate` in the market list. `on a
rung` at zero with ladders present means every rung fell under the
floor or past the credibility bar, which the census now counts by
name.

## Football is priced three hours before kickoff, and the pacer can see NFL kickoffs now (2026-09-07)

THE FINDING UNDER THE REQUEST. The launcher's kickoff reader took only
ISO times and skipped any time without a date; an NFL game's kickoff is
"HH:MM" Eastern beside a "YYYY-MM-DD" date. So for the NFL the kickoff
list had been empty all season, and everything the pacer keys on it —
the pre-game window and its burst, the closing window, the window-aware
starvation rule — never fired for the NFL. It reads the date and the
Eastern clock now (`launch._eastern_epoch`).

THE READINESS PULL. Once the next kickoff is within three hours
(`oddsbudget.READY_BEFORE_S`), a football league that has not pulled
since the window opened gets one pull through the day's ceiling and the
ordinary gap. Never the reserve, once per window per sport, football
only (`READY_SPORTS`). The pre-game window opens at three and a half
hours so the burst is already running when it fires. Baseball weighs
0.6 to football's 1.0 in the day's split (`launch.SPORT_WEIGHT`).

What to look for on a Sunday, in the decisions ledger:

```bash
cd /srv/qellys && grep -h '"readiness pull' data/cache/odds_decisions*.jsonl | tail -5
cd /srv/qellys && sudo -u qellys python3 -c "
import launch
print('NFL kickoffs the pacer can see:', len(launch._slate_kickoffs(launch.NFL_OUT)))
print('CFB kickoffs:', len(launch._slate_kickoffs(launch.CFB_OUT)))"
```

The first line should show one `readiness pull` verdict per kickoff
wave (1pm, 4pm, 8pm Eastern) on the `nfl` lane, each at the full
event price. The kickoff count for the NFL should equal the number of
games on the slate; zero means the games carry no `date` and the pacer
is time-blind again.

## Sizing the over/under test before it is registered (2026-09-09)

The refusal audit from the day before Week 1 —
`backtest.py --gate --real-lines`, 3,339 NFL props with a real harvested
close — printed a segment table nobody had asked for in advance. Split by
the side taken, the 83 props the gate ADMITTED read:

    side     bets     ROI at a flat unit
    OVER       61          -24.7%
    UNDER      22          +20.8%

A 45.5-point gap at roughly 1.9 standard errors, found by reading a
table. That is a lead, not a finding: the same run also printed a grade
split and a basis split, and this is simply the cell that read worst.
`gradecheck` refused to convict the B+ bucket at 2.1 for the same reason.

What makes it worth a preregistration rather than a shrug is that it has
a mechanism. A projection model biased HIGH produces overs, not a
symmetric spread of overs and unders — so a one-sided error is the shape
you would expect if a recency shade or a usage estimate fitted on healthy
weeks were running hot. A grade bucket has no such story behind it.

`OVER_BIAS_NFL` is drafted in `engine/prereg.py` and **is not
registered** — `ensure_registered` does not call it. One line there
activates it, and that line is not written until `min_n: 80` is known to
be reachable. `HEAVY_PRICE_EDGE` two blocks above it has sat unregistered
since 2026-09-06 for exactly this reason: a test against a population the
book never bets sits at "0 of 80" forever while looking perfectly
healthy.

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
import sqlite3; c = sqlite3.connect('data/ledger.db')
for side, n in c.execute(\"\"\"
    SELECT side, COUNT(*) FROM bets WHERE sport='nfl'
      AND market IN ('receptions','pass_yds','rush_yds','rec_yds')
      AND category IN ('main','paper') AND stake_units > 0
      AND date >= '2025-09-01' GROUP BY side\"\"\"):
    print(' ', side, n)"
```

* COUNTS ONLY, per side, no ROI column — the same rule §16 states. A
  threshold chosen after seeing which side happened to lose is fitted to
  the sample that suggested it; counts carry no outcome information, so
  sizing on them cannot bias what the test finds.
* Last season is the runway estimate: 18 weeks. If the OVER count over
  that stretch puts 80 inside a season, `min_n: 80` is reachable as
  written. If it is a handful, the honest move is a lower `min_n` with
  the cost stated, or leaving it drafted — not registering a clock that
  never rings.
* The UNDER count matters too, and it is the one that decides how sharp
  the test can be. At the ratio the audit saw (22 to 61) an 80-over
  sample can only convict a gap of about 41 points. Near parity it
  reaches about 30. Either way it can catch a badly one-sided board; it
  cannot certify that a ten-point tilt is absent.
* Send me both numbers. Registering is one line and I will not write it
  until they say the test can finish.

### The answer, 2026-09-09: no

    OVER    11
    UNDER   12

Twenty-three bets — every NFL player prop the edge board has journaled
since 2025-09-01. `min_n: 80` needs roughly three more NFL seasons at
that rate, so **`OVER_BIAS_NFL` is not registered**, and the terms are
left exactly as drafted rather than trimmed to fit the count that failed
them. Trimming would be fitting the test to the sample that just told us
it does not fit.

The count also says something the lead did not. The live book is 11 overs
to 12 unders; the replay's admitted arm was 61 to 22. Those are different
populations, but the production board is plainly not selecting
three-to-one overs, which is the premise the whole lead rested on. A
one-sided error in the PROJECTION and a one-sided SELECTION are two
different claims, and the segment table ran them together.

Two things are still unknown, and one query answers both. Is 23 a RATE or
the startup artefact of a journal that only recently began carrying NFL
props — and would pooling the college book make the question askable at
all? The second half re-counts by category and market as well, because a
population hiding under a market name nobody filtered on is the failure
`TD_EDGE_NFL` nearly died of.

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
import sqlite3; c = sqlite3.connect('data/ledger.db')
print('football prop bets by sport, month and side')
for row in c.execute("""
    SELECT sport, substr(date,1,7) AS mon, side, COUNT(*) FROM bets
      WHERE sport IN ('nfl','cfb')
      AND market IN ('receptions','pass_yds','rush_yds','rec_yds')
      AND category IN ('main','paper') AND stake_units > 0
      AND date >= '2025-09-01'
      GROUP BY sport, mon, side ORDER BY sport, mon, side"""):
    print(' ', *row)
print()
print('every NFL bet by category and market')
for row in c.execute("""
    SELECT category, market, COUNT(*) FROM bets
      WHERE sport='nfl' AND date >= '2025-09-01'
      GROUP BY category, market ORDER BY COUNT(*) DESC"""):
    print(' ', *row)"
```

* If the NFL months are spread evenly across last season, 23 is a rate
  and the edge board bets NFL props about once a week — which is task
  #164's real question, not this one's.
* If they cluster in the last few weeks, 23 is a startup artefact and
  says nothing about the forward rate; the sizing has to be re-asked
  after a few live weeks rather than answered now.
* The college rows decide whether pooling the two football leagues is
  worth building. `verdict` filters on one `sport`; a `sports` field
  would go in the same optional, only-hashed-when-carried way `sides`
  did — but only if the pooled count can actually finish a test.
* The second table is the paranoia check. If NFL props are sitting in a
  category or under a market spelling the first query does not name, the
  23 is a measurement artefact and everything above it is wrong.

### Which gate is eating the NFL props (task #164)

Whichever way the count above lands, the question underneath it is why
the edge board recommends so few NFL props at all — and that one does not
need any new instrumentation. `engine/census.py` already publishes an
ordered funnel into the board under `gate_census`, counting the FIRST
failing gate per prop, and `bar_status` names any market whose minimum
edge is unreachable after the selection haircut. Nothing on the terminal
printed it for a long time, which is why "285 → 0" used to read as a dead
board with no reason attached.

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
import json
from pathlib import Path
from engine import gate
d = json.loads(gate.board_source(Path('web/data/recommendations.json')).read_text())
c = d.get('counts') or {}
print('props analyzed', c.get('props_analyzed'), '-> recommended', c.get('recommended'))
for k, v in sorted((d.get('gate_census') or {}).items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int) else 0)):
    if v and k != 'calibration_markets':
        print('  ', v, ' ', k)
for note in (d.get('bar_status') or []):
    print('   bar:', note)"
```

* Read it as a funnel: each prop is counted once, at the first gate it
  failed, so the numbers sum to the props analyzed rather than past them.
* `no_real_price` at the top means the board never got a say — that is an
  odds-coverage problem, not a model one.
* A `bar:` line is the important one. It means the market's minimum edge
  CANNOT be cleared after the selection haircut, so no read however good
  would have produced a bet — which looks identical to a quiet night in
  every other view and is not the same fact at all.

## Reading the board's own rows, not the redacted copy (2026-09-09)

A correction to a diagnosis I sent on 2026-09-08. I reported that the NFL
board was "publishing zero rows" after a script of mine read
`web/data/recommendations.json` and found `most_likely`, `recommendations`
and `game_bets` all empty. **That was my error, not the board's.**
`web/data/` holds the PUBLIC copy, and `engine/gate.py` strips every paid
key out of it — `most_likely`, `board_shelves`, `recommendations`,
`game_bets`, `long_shots` and the rest. An empty list there is the
paywall working, not a build failing.

`gate.board_source()` exists precisely to stop this mistake, and its own
docstring lists three tools that had already made it —
`parlays.arbitrate_slate`, `parlaycheck.py`, and `launch.py
--odds-doctor`, which "counted priced games off the public copy and
reported 0 of 15". Mine was the fourth. Any audit of what the board holds
goes through it:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "
import json
from collections import Counter
from pathlib import Path
from engine import gate
src = gate.board_source(Path('web/data/recommendations.json'))
d = json.loads(src.read_text())
print('read:', src)
for k in ('most_likely','board_shelves','recommendations','game_bets','long_shots'):
    v = d.get(k)
    print(f'  {k:16s}', len(v) if isinstance(v, list) else type(v).__name__)
ml = d.get('most_likely') or []
print('  by kind :', dict(Counter((r.get('kind') or 'prop') for r in ml)))
print('  reserve :', sum(1 for r in ml if r.get('reserve')))
print('  game rows with no book:', sum(1 for r in ml
      if r.get('kind') == 'game' and not (r.get('book') or '').strip()))"
```

* `read:` should print a path under `data/built/`. If it prints the
  `web/data/` path back, there is no private copy on this box — either
  the board predates `data/built/` or `publish()` has never run — and
  every count below it is the redacted one.
* The per-kind funnel the build itself prints is the other half of the
  answer, and on 2026-09-09 it said td 12, prop 27, game 12 shown. A
  board holding 51 rows is a healthy board.
* The last line is the measurement task #207 is waiting on: how many NFL
  game rows carry no book name. The Most Likely board already refuses
  those; whether the edge board should refuse them too is not a question
  to answer by guessing at the count.
