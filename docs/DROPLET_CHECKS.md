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

### 7a. The number on the row moves on the fast clock (2026-09-14)

Ethan, 11:01pm, fourth quarter of Broncos-Chiefs, every bet on the Live
tab reading "in play" and nothing else: "why are we not showing the live
lines for the live props here and not tracking the live stats like how
sports books do it." `current=` above is the BUILD's number, up to
forty-five minutes old on football. The fast scoreboard now carries each
live game's box rows (`players`, the same rows the play-by-play page's
Player stats room draws), written every twelve seconds, and the page
reads a bet's number off them on every poll — so the row under a game
card counts on the game card's clock. The build's figure is the floor,
never the ceiling.

```bash
cd /srv/qellys && python3 - <<'PY7A'
import json
for lg in ("nfl", "cfb", "nba", "wnba", "mlb"):
    try:
        d = json.load(open(f"web/data/live_{lg}.json"))
    except FileNotFoundError:
        print(f"{lg:<5} no fast file"); continue
    live = [g for g in d.get("games", []) if (g.get("live") or {}).get("state") == "live"]
    print(f"{lg:<5} {d.get('generated_at')} live={len(live)} note={d.get('plays_note')}")
    for g in live:
        rows = g.get("players")
        print(f"   {g.get('away')}@{g.get('home')} players="
              f"{'ABSENT' if rows is None else len(rows)}",
              *[f"{r['player']}={r['stats']}" for r in (rows or [])[:2]])
PY7A
```

* `players=ABSENT` on a live game while `plays_note` counts it means the
  box parser refused the payload (the rows are guarded: the plays stay,
  the box goes). `past the 8-game cap` games have no box by design — the
  page keeps the build's number for those.
* `N box score(s)` in `plays_note` is the count of live games whose box
  parsed this pass. Zero with live games on is the thing to look at.
* On the page, a tracked prop reads "57 so far · needs 6 more" and a
  spread "up 7 · covering −3.5"; both should move within a poll of the
  scoreboard, not a build. Live PROP LINES are a different question: the
  odds feed bills eight credits per game per pull for in-play props, and
  the budget buys none after kickoff. Game lines (`livelines`) are still
  pulled for the whole slate at three credits.

### 7b. No bet is journaled on a game under way (2026-09-14)

Ethan, 11:15pm: "Whatever u did shows the bets as upcoming again." Two
things were true at once. The page had dropped the game the moment it
went final (fixed: `fetchAllLive` keeps finals for the tracker). And the
BUILD had never known the game was live at all — the launcher never
passed `--live` to `nfl_build.py` — so at 8:52pm, 10:32pm and 10:51pm
it recommended and journaled pre-game prices on a game in progress:
Trautman over 1.5 receptions (Q1), Bo Nix over 217.5 passing yards and
Engram over 3.5 receptions (Q3), a game-total under 48.5 with 41 points
scored (Q4). Now: the launcher passes `--live`; `rules.game_has_started`
also reads the game's own kickoff (`clock_says_started`, an eight-hour
window after kickoff); and `ledger.in_play_reason` refuses the row at
journal time on all three books (edge, long shots, Most Likely).

The rows placed in play on the 14th are still open and still on the
record. Listing them is safe; voiding them is Ethan's call:

```bash
cd /srv/qellys && sqlite3 -header data/ledger.db "SELECT id, category, player, market, side, line, odds, stake_units, ts, status FROM bets WHERE sport='nfl' AND status='open' AND ts >= '2026-09-15T00:15' AND ts < '2026-09-15T04:00' AND (player IN ('KC','DEN','DEN@KC') OR team IN ('KC','DEN')) ORDER BY ts;"
```

Kickoff was 00:15Z (8:15pm ET). Every row that query returns was
journaled after it. To void them with the reason on the row (only on a
yes):

```bash
cd /srv/qellys && sqlite3 data/ledger.db "UPDATE bets SET status='void', pnl_units=0, pnl_dollars=0, why_note='placed in play — the build did not know the game had kicked off (2026-09-14)' WHERE sport='nfl' AND status='open' AND ts >= '2026-09-15T00:15' AND ts < '2026-09-15T04:00' AND (player IN ('KC','DEN','DEN@KC') OR team IN ('KC','DEN'));"
```

After the next refresh, the build log's `Journal:` line should stop
growing during a game, and `--why-pick` on a live game's prop says
"kicked off N min ago by its own schedule".

### 7d. The in-play sweep, and what it found on 2026-09-15

Once `ledger.in_play_reason` shipped, the question became how much had
already landed before it. Every book records `lead_min`, the minutes to
kickoff when the row was journaled, so a negative value IS the answer:

```bash
cd /srv/qellys && sqlite3 -header -column data/ledger.db "SELECT sport, category, status, COUNT(*) AS n, ROUND(SUM(pnl_units),2) AS pnl FROM bets WHERE lead_min IS NOT NULL AND lead_min < 0 GROUP BY 1,2,3 ORDER BY 1,2,3;"
```

Run it after any week where a build may not have known a game was live.
Anything it returns in `category='main'` is real money on the public
record and should be voided; the other books are measurement and the
call is judgment.

**Most Likely rows before 2026-09-15 answer NULL here.** That book did
not write the column until the commit that added this section, so rows
journaled earlier cannot be swept this way. For those, read `ts` against
the day's kickoffs by hand, and use `game_day` to separate a row taken
for that day's early game from one taken hours ahead of the night game:

```bash
cd /srv/qellys && sqlite3 -header -column data/ledger.db "SELECT id, player, team, market, line, game_day, status, ROUND(pnl_units,2) AS pnl, ts FROM bets WHERE sport='nfl' AND category='likely' AND lead_min IS NULL AND ts >= '2026-09-09' ORDER BY game_day, ts;"
```

Sunday's windows in UTC: early games 17:00, late games 20:05 and 20:25,
Sunday night 00:20 the next day. Thursday and Monday nights kick at
00:15. A row whose `game_day` is the day in question and whose `ts` is
after that day's first kickoff is in play unless the player was in the
night game.

WHAT THE FIRST SWEEP FOUND, and what was done about it:

| Book | Rows | Net units | Action |
|---|---|---|---|
| college edge | 5 | +3.15 | voided |
| baseball edge | 3 | +0.85 | voided |
| NFL edge (KC-DEN) | 2 | 0 | voided |
| NFL Most Likely / stale (KC-DEN) | 7 | +0.02 | voided |
| NFL Most Likely, Sunday 9/13 | 12 | +0.12 | OPEN QUESTION |
| baseball long shots | 229 | −0.62 | OPEN QUESTION |

The five college rows were the expensive ones. All were moneylines on
big underdogs journaled well after kickoff at prices the cached odds
payload was still serving from before it, and one of them — CIT at
+1300, journaled 207 minutes in, about when a college game ends — was
carrying +4.55 units of the college edge book on its own. That is the
shape to watch for: a long price on a live dog is what a stale payload
looks like from the inside.

The two open questions are deliberately left open. The twelve NFL
likelihood rows need each player's own game to separate an early-game
row from a night-game one. The 229 baseball long shots are more than
half that book, so voiding them halves a calibration sample that is
already thin; the P&L barely moves either way, and the trade is sample
size against a home-run model partly measured on games it could see.

### 7c. A player on his old team (2026-09-15)

Ethan: "we are showing props for players not even on the team any more.
Isaiah pachaceo is on the lions now, not the chiefs." Two causes, both
fixed: `build_slate.team_of` read the FIRST stat row of the season
(Week 1's team) before it asked the roster, and the price index is keyed
by name across every game on the pull, so a man filed under his old
team took his new team's price. Now the roster (`nflverse.roster_teams`,
every status, twelve-hour cache) is asked first, the NEWEST stat row
second, and a price from a game the prop's team is not in is refused
and counted (`Refused N price(s) from a game the player is not in`).

To see what the three sources say about one man:

```bash
cd /srv/qellys && python3 - <<'PY7C'
import csv, json, sys
from pathlib import Path
who = "Isiah Pacheco"                 # the roster's spelling; try the folded name too
from engine.sources.oddsapi import normalize_name
from engine.sources.fetch import CACHE_DIR
key = normalize_name(who)
for f in sorted(Path(CACHE_DIR).glob("roster_2026.csv")):
    rows = [r for r in csv.DictReader(open(f)) if normalize_name(r.get("full_name") or "") == key]
    print("roster:", [(r.get("team"), r.get("status"), r.get("week")) for r in rows] or "not in the file")
for f in sorted(Path(CACHE_DIR).glob("player_stats_2026.csv")):
    rows = [r for r in csv.DictReader(open(f)) if normalize_name(r.get("player_display_name") or "") == key]
    print("stats :", sorted((int(float(r["week"])), r.get("recent_team")) for r in rows) or "no rows yet")
d = json.load(open("data/built/recommendations.json"))
for r in d.get("recommendations", []) + d.get("most_likely", []):
    if normalize_name(r.get("player") or "") == key:
        print("board :", r.get("team"), "vs", r.get("opponent"), r.get("market"), r.get("book"), r.get("line"))
PY7C
```

* `roster:` should name the team he is on today. If it still names the
  old one, nflverse has not published the move — nothing here can fix
  that, and the board will follow within twelve hours of it landing.
* `stats :` is where the OLD code read from: the first tuple is Week 1.
* `board :` after the next refresh should match `roster:`; a line
  `Refused N price(s)` in the build log means a price was kept off a
  card filed under the wrong team.
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
| Settlement — game bets | `livescores.ingest_finals` fills the blank score on a scheduled fixture from the live scoreboard, on the 5-minute intraday pass | a moneyline/spread/total settles minutes after the whistle |
| Settlement — player props | `maintenance` ingests nflverse weekly results daily, Aug–Feb | Wednesday's props settle on Thursday's pass; the weekly stats file is the only source of an actual |

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

GENERALISED 2026-09-14, after it bit again. The NFL request gained
`player_pass_tds` that morning, which changed the base name too; every
NFL event missed its cache on every cached rebuild, every prop fell to
a proxy, and the Monday board showed one moneyline (Ethan: "we are now
only showing a money line for the Chiefs game tonight"). A cached
rebuild now serves the NEWEST payload on disk for the event under any
name (`name_fallback` in the attach result, `oddsapi.newest_event_cache`),
dated by that file's own age, so a change to the request never blanks
a board; the markets the old payload lacks stay unpriced until the next
paid pull. Confirm on the next cached NFL rebuild after a request
change: the build log's attach line should show `name_fallback` events
and no `cache_misses` for events the last paid pull reached.

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

BASEBALL TOO, since 2026-09-15 (Ethan: "MLB most likely bets are only
showing hits and total bases. There is no money lines or pitchers props
or game totals"). The MLB event pull asks for `batter_hits_alternate`,
`batter_total_bases_alternate` and `pitcher_strikeouts_alternate` —
eleven credits an event now — and every rung is priced by the curve
that priced the main line (`engine/mlb/betting.rung_probs`, carried on
the row as `rung_probs`). The three keys are unproven against the API
from the dev box: if one is refused, `fetch_event_odds` drops it and
retries the event without it, once per process, and the spend ledger
shows one refused call. The same check as above reads
`web/data/mlb_picks.json`; the Most Likely page's "Where each market's
rows went" block says, per market, what was offered, priced and shown
and at which bar the rest were refused — including the game lines,
which read "this game market has never been measured" until
`engine.gamerank` has written a figure on this box (the next
maintenance pass does that by itself now; see docs/LIKELY_GAME_LINES.md).

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

### The answer, 2026-09-09 — and what the answer turned out to mean

    OVER    11
    UNDER   12

Twenty-three bets, and the first thing to say is that **the window in
that query filtered nothing**. `AND date >= '2025-09-01'` looks like it
scopes to last season. It does not: the NFL journals a season-week label
(`2026-W01`, from the slate key in `engine/sources/nflverse.py`), and a
week label string-sorts above every ISO day in its own year. Every
football row passed the window unconditionally.

So 23 is not a season's worth. It is **every NFL player-prop bet this
journal has ever held**, all under one season-week prefix, on the day the
season opens. The NFL prop book starts at Week 1 with no history behind
it — which flips the sizing entirely: 23 bets in the first week is about
eleven OVERs a week, and `min_n: 80` lands around week seven, comfortably
inside an 18-week season.

**`OVER_BIAS_NFL` is still not registered, for a different reason.**
Until `bets.date` carries a calendar day for the NFL, `verdict` drops
every football row it cannot place in time, so the test would sit at "0
of 80" forever — correctly, and out loud, but forever. It is blocked on
the journal, not on the rate. Register it when the NFL journal writes a
day.

The near-parity reading survives and gets sharper: Week 1's actual
selection went out 11 overs to 12 unders, against the replay's 61 to 22.
The production board is not selecting three-to-one overs, which was the
premise the whole lead rested on. A one-sided error in the PROJECTION and
a one-sided SELECTION are two different claims, and the segment table ran
them together.

One query is still worth running, to see whether pooling the college book
would make the question askable and to check that no NFL props are hiding
under a category or market spelling the first query did not name — the
failure `TD_EDGE_NFL` nearly died of.

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

* NFL rows will all read `2026-W0` in the month column. That is not a
  month — it is the first seven characters of the season-week label, and
  seeing it there is how this was found.
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

## The moneyline doctor (2026-09-09)

Ethan, four times now, with a sportsbook open beside the site:

    2026-09-03  "These lines along with more are completely wrong, none
                of these teams are favored to win on any sports book."
    2026-09-08  "I don't want you too stop working until we display the
                right lines and prices the books show."
    2026-09-09  "FanDuel and draft kings show the lines in the screenshot
                yet we show a different line. That's wrong."
    2026-09-09  "i wanna focus on those moneyline props, they are still
                showing the wrong lines on the site like before"

Every one of those needed the same three numbers side by side, and every
one of them got a one-off command that was thrown away afterwards. That
is why the report keeps coming back with no accumulated answer: nothing
on the box could show, in one place, what the books quoted, what we
published, and whether those are the same number.

```bash
cd /srv/qellys && sudo -u qellys python3 launch.py --ml-doctor        # NFL
cd /srv/qellys && sudo -u qellys python3 launch.py --ml-doctor cfb
```

It prints one block per game on the board, matched to that game's own
kickoff in the pull, and then decides:

1. **What the cached pull holds** — every book's price per side out of
   `data/cache/odds_board_<sport>*.json`, with the best-per-side we would
   publish marked, and the payload's age. The sharp reference is skipped
   exactly as `parse_event_h2h` skips it, because nobody here can bet it.
2. **What the board published** — each game's `home_ml`/`away_ml`, the
   freshness counters off `odds_status`, and every Most Likely moneyline
   row with its price, its book, its age and where it was priced from.
   Read through `gate.board_source`, so it is the board's own rows and
   not the redacted copy.
3. **The verdict**, computed rather than eyeballed.

**How to read the verdict.** We publish the best price per side across
the field, so our number can beat any one book and can never be worse
than all of them.

* `every published moneyline matches the best price in the pull` — the
  board is doing its job. A phone showing −125 against our −118 is not a
  bug; it is shopping, and the doctor says so in the same sentence.
* `⚠️ N published price(s) are SHORTER than anything in the pull` — this
  is the real fault, and it names the team, both numbers and the book.
  A published price shorter than the whole field cannot come from
  shopping, so it came from somewhere else or from an older payload; the
  `age=` on the row and the pull's own age say which.
* `no cached pull to compare against`, or `no game on the board matched
  an event in the pull` — nothing was checked. Deliberately not phrased
  as a clean bill: a tool that reports an unchecked system as healthy is
  worse than no tool, and silence reads as approval.

**`odds_status` is printed whole, and a missing key is the evidence.** No
`board_*` entries means the cheap whole-slate line refresh
(`--board-odds`) never ran for that build, so the game prices are
whatever the per-event pull left — which on 2026-09-09 was 17.7 hours old
while a 0.6-hour payload sat unused in the cache. `error` separates "never
ran" from "ran and threw", and `source` says whether the event pull was
fresh or served from cache.

### The keying bug this tool shipped with, and what it cost

The first cut keyed the pull's best price on the TEAM. The whole-slate
payload is the whole SEASON — two hundred-odd games — so every team
appears seventeen times and each entry was overwritten by that team's
LAST game in the file. The verdict compared Week 1's Seattle price
against Seattle's January one, and reported **thirteen mismatches on a
sixteen-game slate** the hour it shipped.

That is precisely the failure `odds_doctor` warns about in its own
comment: *"A tool that reports a healthy system as broken costs more than
no tool: it sends you looking for a fault that is not there, and it
teaches you to discount the next true alarm."* It is now keyed on the
matchup, keeps every kickoff, and takes the soonest one that has not
started — pinned by
`tests/test_ml_doctor.test_the_season_long_payload_does_not_collapse_onto_one_price_per_team`.

---

# Moved from WHEN_YOU_ARE_HOME.md on 2026-10-02

Every block below was answered, done or superseded when the runbook was
pruned to what is open (audit #13). Kept word for word, oldest last.

## Disk full — the one-time cleanup (run 2026-10-01)

One-time cleanup of the pile that was already there (safe: lookups only,
nothing the models read). It takes a minute or two:

```
cd /srv/qellys/data/cache && find . -maxdepth 1 -type f \( -name 'dex_pairs_*' -o -name 'rug_*' \) -mmin +60 -delete; df -h / | tail -1
```

## PHASE 5 — items done 2026-10-01 (moved from the open list)

**P30-a: done 2026-10-01** (anthropic 1.11.0, pip-audit clean). Why the
uninstall loop below comes first: `--ignore-installed` writes the new
files over the old but leaves the old version's dist-info behind, so
`pip list` and `--todo` kept reading 1.4.0 while Python ran 1.11.0. Use
the same three lines next time the pins move.

**P30-a. Put the Ask SDK on its pin, then audit it (changes packages, 2
minutes).** `anthropic` was installed unpinned. `requirements.txt` now pins
it and everything it pulls in, with hashes:

```
cd /srv/qellys && for i in 1 2 3; do sudo python3 -m pip uninstall -y --break-system-packages anthropic httpx2 httpcore2 jiter 2>&1 | grep -i uninstalled; done
sudo python3 -m pip install --break-system-packages --ignore-installed --require-hashes -r requirements.txt
sudo -u qellys python3 -c "import anthropic; print(anthropic.__version__)"
sudo python3 -m pip install --break-system-packages pip-audit && pip-audit --disable-pip -r requirements.txt
sudo systemctl restart qellys && python3 launch.py --todo | grep -i "sdk"
```

The version line should print `1.11.0` (done 2026-10-01). `--disable-pip`
because the droplet has no `python3-venv` and the file is hash-pinned, so
pip-audit has nothing to resolve; it should print "No known
vulnerabilities found" (if it names one, paste it back); `--todo` should
say "anthropic 1.11.0, as pinned".

**P52-a: done 2026-10-01.** Unit installed (exposure 2.3 OK, no SIGSYS),
Caddy reloaded (permissions-policy live), cfips timer enabled (first run
Mon 2026-10-05 03:15 UTC). Backups of the old files: /root/*.before-p52.
If not done yet, drop the old cron line:
`sudo crontab -l | grep -v 'cfips.sh' | sudo crontab -`

**P52-a. Security housekeeping from the audit (on the box, ten minutes).**
Four changes in this update need the box itself:

1. **The unit's new syscall filter.** `deploy/qellys.service` now drops
   every capability and allows only systemd's `@system-service` calls.
   Install it, restart, and watch the first minute of the journal:

   ```
   cd /srv/qellys && sudo cp deploy/qellys.service /etc/systemd/system/ \
     && sudo systemctl daemon-reload && sudo systemctl restart qellys
   sudo journalctl -u qellys -n 50 --no-pager
   systemd-analyze security qellys | tail -1
   ```

   If the service will not start and the journal says `SIGSYS` or "Bad
   system call", take the two `SystemCallFilter`/`SystemCallArchitectures`
   lines back out and tell me which call it was.
2. **Caddy's new hide list and Permissions-Policy header.** Reload, then check:
   `sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy`
   then `curl -sI https://qellysbook.com/ | grep -i permissions-policy`.
3. **The weekly Cloudflare list refresh.**
   `sudo cp deploy/qellys-cfips.service deploy/qellys-cfips.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now qellys-cfips.timer`
   then `systemctl list-timers qellys-cfips.timer`.
4. **A board the boot seal cannot redact now comes off the public path.**
   If `data/UNSEALED.json` ever exists, read it, then reseal and restart:

   ```
   cd /srv/qellys && sudo -u qellys python3 launch.py --seal
   sudo systemctl restart qellys
   ```

The unsubscribe links in new emails now look like `/unsubscribe/<id>.<code>`
and carry no secret stored in the database. Links already in inboxes keep
working for 60 days from the next send.

**P44-a and P33-a: done 2026-10-01.** The journal re-keyed itself
(22,818 bets, old key gone), and the clock voided 28 rows: every one on
the postponed 9/22 Orioles–Blue Jays game (9 staked, 19 on the paper
boards). Nothing else is waiting on an unplayed game.

## TD-RZ: done 2026-10-01/02 (#168 closed)

Red-zone defence, measured on the box against the touchdown model's own
number over 19,860 graded player-weeks (2021–2025), pooled, cluster-robust,
on a rule fixed before the run:

- `rz_allowed` (how often a defence lets offences in): FAILS — clustered
  t 0.5, held-out gain 0.00% every season.
- `rz_td_allowed` (touchdowns allowed per red-zone play): FAILS —
  clustered t 1.5, mean held-out gain -0.004%, two seasons negative.

Neither goes into the chance; both stay on the touchdown cards as context.
With goal-line work (measured 2026-09-27, already in the chance, shown on
every card) and game script (in the model), all three parts of the other
model's touchdown method are either in the number or shown to add nothing.
To re-run after another season: `sudo -u qellys nice -n 10 python3 -m engine.tdmatchfit`.

## 2026-09-29 go-over: done 2026-10-01

M9 (the stuck MLB bets) was the postponed 9/22 game, voided by the clock.
M10/M11 (the NFL closing-line repair) was applied; the old values are in
`data/closerepair_<time>.json`, and each change is in the Record page's
change log as `closerepair`. No grade moved.

---

## GO OVER TOGETHER — saved 2026-09-29 (Ethan: "save everything for when I'm home so we can go over it")

### Step 1. One paste, read-only, a minute. Paste the output back.

```
cd /srv/qellys && { echo "=== CODE ON THE BOX ==="; git log --oneline -1; echo "=== M8 LIVE TAB ==="; python3 homecheck.py live; echo "=== M7 THE CLOSE ==="; sudo -u qellys python3 closecheck.py; } 2>&1 | tee ~/gooverit.txt
```

- **CODE ON THE BOX** should read `b206506f` or later (the Live tab fix).
  Older means the box has not pulled yet: wait five minutes and re-run.
- **M8, the Live tab.** Per league, how many open bets the Live tab has
  to draw and how many are Most Likely. Since the fix the Most Likely
  count includes the one board's picks, so for a slate with games on it
  the number should be close to the Most Likely page's count, not four.
  It only moves after that league's next board build.
- **M7, the close** — see below. If the paste is too long, `cat
  ~/gooverit.txt` prints it again.

### Step 2. What we decide together (nothing to run)

1. **The picks that lost the close** (M7's answer). If they are
   scratches graded 0, the fix is in the settler and changes past grades
   on the public record — your yes first, and I show you every row that
   would change. If it is news the market had, the fix is pulling a pick
   when its line moves a point against it before kickoff. If it is a bad
   close, the fix is in how the close is captured, and the record stands.
2. **"Worth a look" claims 59% and hits 48%** on the one board (123-132).
   Strong and Top pick hit 62%, about what they claim. Options: lower the
   ring's number on that tier to its measured rate, stop showing the tier,
   or keep it and let the record label carry the truth (it already says
   "picks like it hit X%"). It is paper, no money on it.
3. **Pinnacle for game lines.** The one sharp book, and the best close to
   measure against. It is in The Odds API's `eu` region; pulling it for
   game lines roughly doubles the game-line credit spend. Yes or no.
4. **Edge picks on MLB overs lost 26 units** over the summer (MLB hits
   overs 89-110). The season is over for the regular slate, so nothing
   bleeds now; the question is whether MLB edge overs start next season
   benched until a refit proves them.
5. **Still on the list, not started:** touchdown picks the other AI's way
   (goal-line usage, red-zone defence, game script), and the college
   starting-QB read from the news feed.

### What shipped 2026-09-28 into 09-29, all tested and pushed

- **Most Likely page:** the fair price and "take at X or better" on every
  card, the tier in words under the ring, the "same story as N others"
  tag, a record label that reads as a count until 20 picks and a hit rate
  after, the intro trimmed on phones, and the filters scrolling with the
  page again (they covered the cards when pinned). By Game ranks highest
  to lowest.
- **Live tab:** the one board's picks now reach "Open Most Likely bets"
  in every league, each wager once. This is why only four Bears rows
  showed during PHI@CHI.
- **Record page:** checked on the box (M6) — every grade right, every
  section's totals right. The 2/2 spread row was the Most Likely board's
  own two; the CAR loss was Pick of the Day's. Each section now names
  which picks it counts.
- **MLB:** the board builds the next game day on an off day, and the
  postseason start comes from the league's own calendar.
- **Team page:** schedule cycles 2021–2026. **Profit calendar:** settled
  bets under each day, folded after six with a summary. **QB-out teams:**
  the backup's team volume shown on every row of that team.
- **Loss audit** (M4) and **close check** (M7) scripts; the audit now
  labels football weeks as "NFL week 3", not January.

---

## THE CLOSE — 2026-09-29 (read-only, seconds)

M1–M6 ran on 2026-09-29 and are answered: the money bars read the real
tapes (PHI@CHI showed a split; started games show none, rightly), the
Record page's numbers all check (M6: every grade matches its final, no
bet graded two ways, every section's totals match), the MLB board built
the 09-29 slate from the league calendar, and bet365 is in no region The
Odds API serves — it cannot be added. Pinnacle is (the `eu` region), and
is the one sharp book; pulling it for game lines would double the
game-line credit spend, so it is a decision, not a fix.

**M7. Why do the picks that lost the close hit 12–18%?** The loss audit
(M4) found the only number that is not luck: Most Likely picks whose line
moved AGAINST them before kickoff hit 18% staked (8-37) and 12% on the one
board (9-63), where we claimed 62%. A move against a pick should cost a
few points, not forty-five. Three things do that — a scratch the ledger
graded at 0 instead of void, news the market had (the pick should have
come off the board), or a "close" that is not one (a snapshot from the
wrong day or market) — and each leaves a different mark on the rows. This
sizes every close, lists every lost-the-close bet with its final number,
flags the scratch suspects, says whether the finals sat nearer the close
or our line, and counts the markets that never get a close at all (half
the Edge picks and six in ten Most Likely picks carried none). Read-only,
seconds; paste the whole thing back:

```
cd /srv/qellys && sudo -u qellys python3 closecheck.py
```

`--sport nfl` for one league; `--all` lifts the 60-row cap on the lists.

---

## PREDICTION MARKETS — 2026-09-26 (read-only, a minute)

**A. Are the Polymarket tags real?** Prints how many game moneylines
each league's tag returned. A league showing 0 or "error" means the tag
name is wrong or the venue is blocked; paste it back.

```
cd /srv/qellys && python3 -c "from engine.sources import polysports as p; rows, rep = p.fetch_sports(); print(rep, len(rows))"
```

**B. After the next NFL and MLB builds: are the prices on the games?**
Look for the "crowd prices" lines in the build output. The count to
watch is how many games Kalshi and Polymarket each priced:

```
cd /srv/qellys && python3 -c "
import json; from engine import gate
for f in ('recommendations.json','mlb_recommendations.json','cfb.json'):
    d = json.load(open(gate.board_source('web/data/'+f)))
    print(f, d.get('crowd_census'), d.get('polymarket_tags'))"
```

**Answered 2026-09-27 evening** (Ethan's run on 4117cab0): B1 `tdcheck.py`
ALL TOUCHDOWN CHECKS PASS, Gibbs priced out past −250, reserves said as
reserves; the touchdown calibration on the box is T 1.12 / +0.20, the one
the day's position fixes were fitted against (no refit needed — Wednesday's
deep refit runs anyway); `tdearlyfit.py` matched the sandbox (the raw chain
runs ~4 points low, which the calibration corrects). B2 `crowdprobe.py`
confirmed Kalshi's spread and total series for NFL, college and MLB — now
wired (engine/crowd.kalshi_lines: the board's own half-point line only).
B3 `hoopsdvpfit.py` measured the defence's lean reaching one player in
every stat (NBA the whole lean; WNBA 78–100%) — now read into basketball
projections (hoopsdvp.TRANSFER). B5's LAC@BUF plan showed a play in both
"fits" and "avoid" and proxy lines set against "the market" — both fixed.

The one to re-run after the next NFL build (reads only):

```
cd /srv/qellys && python3 tdcheck.py
```

**B4. How much of a team's rating should be this season (2026-09-27).**
The matchup scan's split is now MEASURED, not set by hand: this season's
share grows with its games (a third after 3 games, half after 6), faster
for an offence under a new starting QB; new coaches are named on the card
but change nothing, because on 2022-2025 they did not help. That was
measured here on the cached play-by-play. This re-runs it on the box's own
database (the first line fills in the older seasons once; it reads
play-by-play the box already caches). Read-only after the backfill; paste
the output back:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.gamescan backfill 2021 2022 2023 2024 && python3 scanblendfit.py
```

**B5. The game plan, game by game (2026-09-27).** Every football game
page now opens with a Game plan: the line and the script, who is out and
where the work goes, the matchup, the plays that fit (volume first), the
plays to avoid, what changes the read, and where our raw number disagrees
with the market — those last rows go on paper under `plan_gap`, so in a
few weeks `python3 ledger.py report` says whether big disagreements with
the books pay (the other AI's strongest calls are exactly those). This
prints one game's plan from the box's own board, read-only:

```
cd /srv/qellys && python3 -m engine.gameplan nfl LAC@BUF
```

**B6. The markets the other AI bets that we did not carry (2026-09-27).**
Pass attempts, completions, carries and a quarterback's rushing yards are
now priced (measured first — `python3 marketfit.py` prints the held-out
ranking figures; interceptions measured a coin and stay off). Three
more credits per game per pull. The journal settles the two new stat
names (`pass_cmp`, `rush_att`) from the game logs, so re-ingest this
season once so those rows exist before the first of them settles:

```
cd /srv/qellys && sudo -u qellys python3 ingest.py nfl --seasons 2025,2026 && python3 marketfit.py
```

**C. In two or three weeks: is the crowd right?** Once a couple of
hundred games have finished with stored prices:

```
cd /srv/qellys && python3 crowdfit.py
```

---

## TONIGHT — 2026-09-25, in this order

Everything left from today, with what each answer means. Blocks 1–3
only read. Block 4 writes one row and only if you decide to. Run them
from the droplet (or the resource-check session); paste the output back.

Already answered today: the Most Likely journal check (62 picks on the
board, 76 journaled for the week — every pick journals now); the box is
level with GitHub again; the week-1 Tonges bet is voided; the database-
copy ignore rules are in.

**1. Did the breakout reads get their Most Likely picks?** After NFL has
rebuilt on today's code — this shows the running commit and NFL's last
build:

```bash
cd /srv/qellys && python3 launch.py --boards
```

Then:

```bash
cd /srv/qellys && python3 - <<'EOF'
import json
from engine.gate import board_source
b = json.load(open(board_source("web/data/recommendations.json")))
n = {}
for g, r in (b.get("scan_reads") or {}).items():
    for x in r.get("players") or []:
        if x.get("read") not in ("breakout", "good", "tough", "avoid"):
            continue
        if x.get("pick"):
            st, p = "PICK", x["pick"]
        elif x.get("pick_other_side"):
            st, p = "OTHER WAY", x["pick_other_side"]
        elif "no_pick" in x:
            st, p = "NO PICK", (x["no_pick"] or {}).get("best")
            if not (x["no_pick"] or {}).get("priced", True):
                st = "NO PROPS"
        else:
            st, p = "NOT STAMPED", None
        n[st] = n.get(st, 0) + 1
        what = (f"{p['side']} {p['line']} {p['market']} {p['odds']} {round(p['model_prob']*100)}%"
                if p else "")
        print(f"{x['label'][:18]:18} {x['player'][:22]:22} {st:11} {what}")
print(n)
EOF
```

Want: the last line split into PICK / OTHER WAY / NO PICK / NO PROPS.
All `NOT STAMPED` means the board is still from older code — wait a cycle.
Send the rows for Kincaid, Wilson and Mitchell.

**2. Is Pinnacle's baseball price reaching the board?** (item G1) After
an MLB build on today's code:

```bash
sudo journalctl -u qellys --since "2 hours ago" | grep "Sharp witness" | tail -3
```

Want: "N of M moneylines carry Pinnacle's price". N near M and "0
cleared the 2% edge" is the rule working, nothing to fix. N at 0 is the
bug — send the line.

**3. Does every board pick have its journal row?**

```bash
cd /srv/qellys && python3 - <<'EOF'
import json, sqlite3
from engine.gate import board_source
from engine import ledger
b = json.load(open(board_source("web/data/recommendations.json")))
c = sqlite3.connect("data/ledger.db")
missing = []
for r in b.get("most_likely") or []:
    if r.get("reserve"):
        continue
    m, p = r.get("market", ""), r.get("player")
    if r.get("kind") == "game" or m in ledger.GAME_MARKETS:
        k = ledger.game_row_keys(r, m)
        if not k:
            continue
        p, m = k[0], k[1]
    if not c.execute("SELECT 1 FROM bets WHERE sport='nfl' AND date=? AND player=? AND market=? "
                     "AND category IN ('likely','likely_live')", (b.get("date"), p, m)).fetchone():
        missing.append(f"{r.get('player')} {r.get('side')} {r.get('line')} {m} {r.get('odds')}")
print(len(missing), "board picks not in the journal")
for x in missing: print("  ", x)
EOF
```

Want: `0 board picks not in the journal`.

**3b. Is every NFL week table current?** The matchup tape ranks on this
season alone from two games on (2026-09-25, after the Jets' defence read
27th on mostly-2025 numbers) — which only helps if this season's weeks
are stored. The doctor now checks results, player stats, snap counts and
unit ratings against the last week played (it used to skip the NFL):

```bash
cd /srv/qellys && python3 doctor.py --skip-tests 2>&1 | grep -A1 "football weeks\|league days"
```

(`league days` is the same check for college, MLB, NBA and WNBA, added
later on 2026-09-25 — want `✅ league days … every league's stats reach
its last day played`.)

Want: `✅ football weeks  Freshness: 2026 week 3 is the last played — …
All current.` A `❌` line names what is behind. Unit ratings catch up on
their own now (the nightly retries whenever they trail); anything else
behind, send me the line.

**4. Your call — the Tonges bet.** It was voided this morning. By your
2026-09-14 rule a player who took snaps and logged no stat is graded at
zero, and he played 12% of them, so the rule says a LOSS (a `stale`
row: zero dollars, never in the headline). To grade it like every other
row, reopen it and the next settle pass applies the rule; to leave it
void, do nothing:

```bash
cd /srv/qellys && sqlite3 data/ledger.db "UPDATE bets SET status='open', why_note=NULL WHERE sport='nfl' AND date='2026-W01' AND player='Jake Tonges' AND status='void'"
```

**5. The Kalshi block runs as `qellys`, never root** (item G3). The
exact block is in `/srv/qellys/backups/OUTSTANDING-2026-09-25.md`; run
it with `sudo -u qellys` in front, not as root.

**6. Did the stale-data and teammate-out work reach the live board?**
(commits 9dc0800e and 75e70e1c) After NFL has rebuilt on today's code:

```bash
cd /srv/qellys && git log --oneline -1 && python3 - <<'EOF'
import json, datetime as dt
from engine.gate import board_source
d = json.load(open(board_source("web/data/recommendations.json")))
now = dt.datetime.now(dt.timezone.utc)
print("data_freshness:", d.get("data_freshness"))
ml = d.get("most_likely") or []
ages = [(now - dt.datetime.fromisoformat(r["priced_at"].replace("Z", "+00:00"))).total_seconds() / 3600
        for r in ml if r.get("priced_at")]
print(f"Most Likely rows {len(ml)} · with a pull time {len(ages)} · oldest price {max(ages or [0]):.1f}h")
lk = [r for r in ml if r.get("locked")]
print(f"locked {len(lk)} · book lists it now {sum(1 for r in lk if r.get('now_listed'))} · "
      f"no book lists it {sum(1 for r in lk if r.get('now_listed') is False)}")
for g in (d.get("scan_reads") or {}).values():
    for p in g.get("players") or []:
        for t in (p.get("pro") or []) + (p.get("notes") or []):
            if " out" in t and ("targets" in t or "carries" in t):
                print(" ", p["player"], "|", t)
EOF
```

Want:
- the commit at 75e70e1c or later;
- `data_freshness` with `behind: []` (anything listed there is also on
  the site's banner — send it);
- nearly every Most Likely row with a pull time, and the oldest price
  under 6h;
- the locked picks split between "book lists it now" and "no book lists it";
- each teammate-out line with a number in it (a share, or "absorbed
  +N%"), and "our projection counts it" where the model moved his number.

`data_freshness: None` and no pull times means NFL has not rebuilt on the
new code yet — wait a cycle.

**7. The board's self-check.** Every build now checks the claims its
board makes against its own data (engine/boardtruth): picks under 55% or
heavier than −250, old prices not marked, locked picks with no current
price, a note and a tile that disagree, a card naming a pick the board
lacks, a longshot called "likeliest", a teammate-out line with no number,
stats behind. The Status page shows each league's count under "Model
builds"; the detail is in the log:

```bash
sudo journalctl -u qellys --since "1 hour ago" | grep -A8 "self-check" | tail -40
```

No output means every claim held. Anything printed, send it.

**8. Does a pitcher's CSW help his strikeout number?** (read-only, a
minute) The strikeout adjustment for called strikes plus whiffs has been in
the code since the Statcast layer and never ran. It now reads the
pitch-by-pitch games the box already caches, and stays off until this
says SHIP:

```bash
cd /srv/qellys && python3 -m engine.mlb.csw
```

Want one line, `CSW: SHIP — …` or `CSW: HOLD — …`, with the starts it
measured. Send it either way; SHIP is the one that turns it on.

**Never commit on the box** — see block G. Write notes to `backups/` or
send them to Claude.

---

## STILL OPEN — after Ethan's run, 2026-09-24 evening

Answered tonight (droplet on 99dc78a2 → 524a72af): the Most Likely hold
report reads as it should (40 of 52 NFL picks up 3h+, and the 12 pulled
picks listed with their reasons); the MLB live-lines lane is approving
three-credit pulls about every 20 minutes and ARI @ COL carried a live
line; served boards are smaller than private ones; Ask spent $0.55 and
$0.37 on its first two days against the $25 ceiling; NBA season labels
all clean (9b not needed); wiring clean in all three leagues; all 14
outdoor NFL games forecast and the wind table matches.

**A. Done.** The deploy ran on d0a25e56; the trimmed files are live
(app.js 2,210 KB → 1,433 KB) and the script policy reads
`script-src 'self'`. The deploy's promo check printed every code in full;
it now prints only each code's last two characters.

**B. Answered.** Of the 23 lines under LOOK AT THESE, most were flat by
construction (a factor with no coefficient for that market) or player
memory the record has not earned for that market; the check now lists
those as known. Two things are left for a person: pitcher strikeouts
never get the contact-quality step (the Savant loader reads batter files
only), and the NFL yardage and reception markets cannot clear the edge
bar at any price once the selection haircut is applied.

**C. Two bets stuck on "player has no log"**, both in side books (not
the headline record): cfb 2026-09-19 Ryan Williams anytime TD (`stale`)
and mlb 2026-09-22 Harry Ford UNDER 0.5 hits (`loose`). Voiding them
waits on Ethan's yes.

**E. The matchup scan's unit rankings — one-time backfill** (about a
minute; **writes the history database**). The scan ranks every offence
and defence from the play-by-play; the Tuesday refresh keeps this season
current, and last season needs folding in once:

```bash
cd /srv/qellys && sudo -u qellys python3 -m engine.gamescan backfill 2025 2026
cd /srv/qellys && python3 -m engine.gamescan show 2026 4 GB TB
```

Want: two counts (about 1,088 rows for 2025), then Green Bay and Tampa
Bay ranked unit by unit with their edges. The next NFL build puts the
Matchup scan on every game page (it builds last season's man/zone cache
on its first run, about a minute).

College needs nothing run: the next college build fetches CFBD's advanced
season table (two calls, then cached) and scans every FBS game. To check
it after a build:

```bash
sudo journalctl -u qellys --since "3 hours ago" | grep -i "matchup scan"
```

Want: `Matchup scan: N of M game(s).` with N close to M. A line saying
`matchup scan skipped` is the one to send me.

**Weather, re-measured at the right hour** (2026-09-25). NFL forecasts
were read four hours before kickoff until today (Eastern read as UTC),
and the table that turns a forecast's wind into a cut was measured the
same way. The sandbox can't reach Open-Meteo's archive; the droplet can:

```bash
cd /srv/qellys && python3 wxfit.py --scale 2>&1 | tail -12
```

Want: either `the board's forecast table matches` (nothing to change) or
`CHANGE —` followed by new numbers. Send me the tail either way.
**Done 2026-09-25:** it said CHANGE (largest gap 0.030, 483 games), and
the new table is in engine/weather.WIND_FORECAST. Re-run it after a few
more weeks of games; it should then say "matches".

**D. Wednesday, Sep 30**, after the first playoff games: step 8b's
grading line again.

**G. Found on the box, 2026-09-25 morning** (a session run on the
droplet; its full notes are in `/srv/qellys/backups/OUTSTANDING-2026-09-25.md`
and the matching `0001-docs-home-…patch` — untracked, so they survive a
reset). Open:

1. **The sharp-witness fix shipped and did not fire.** Pinnacle's
   baseball prices ARE arriving (644 rows in the odds tape on the day
   checked), and a card is only sharp-anchored when the sharp book shows
   a side worth 2% (`gamebets.SHARP_MIN_EV`), so "every row False" is
   either the rule working or a hop dropping the price. Every MLB build
   now prints the answer:

   ```bash
   sudo journalctl -u qellys --since "2 hours ago" | grep "Sharp witness" | tail -3
   ```

   Want: "N of M moneylines carry Pinnacle's price". N near M and
   "0 cleared the 2% edge" is the rule working; N at 0 is the bug —
   send me the line.
2. **Done 2026-09-25.** The week-1 bet (Jake Tonges, anytime TD +900,
   `stale` book) was voided at Ethan's call. Why it sat open: week-1 rows
   were journalled before `game_day` existed, and the no-show rule needed
   the day to read the snap file. The rule now dates such a row itself
   (tests/test_an_old_bet_is_graded_without_its_game_day.py).
3. **The Kalshi block must run as the `qellys` user.** Run as root it
   leaves root-owned cache files the build user cannot write, and the
   permission error is swallowed, so the exchange tier freezes silently.
4. **Done 2026-09-25.** A database copy is ignored whatever it is
   called (`*.db.*`, `*.sqlite*`); the box's untracked listing is empty.

Also in the notes: a week-2 alarm that resolved itself (do not re-chase
it), and a note on confident zeros.

**Never commit on the box.** Its GitHub key is read-only, so a commit
there can never be pushed; it splits the branch, and the auto-update
then STOPS ("auto-update stopped: … has diverged") rather than resetting
— new code quietly stops reaching the site. Notes go in `backups/` or to
Claude to commit. (2026-09-25: a notes commit did exactly this and
blocked that morning's deploy.)

**F. Every Most Likely pick journaled** (2026-09-25). Until today the
journal took the board's top ten rows only, so a pick posted further
down — the Packers back over 9.5 rushing yards on Thursday night — was
on the page and never on Live or the record. After the next NFL build
on the new code (read-only):

```bash
cd /srv/qellys && python3 - <<'EOF'
import json, sqlite3
from engine.gate import board_source
b = json.load(open(board_source("web/data/recommendations.json")))
rows = [r for r in b.get("most_likely") or [] if not r.get("reserve")]
c = sqlite3.connect("data/ledger.db")
n = c.execute("SELECT COUNT(*) FROM bets WHERE sport='nfl' AND date=? "
              "AND category IN ('likely','likely_live')", (b.get("date"),)).fetchone()[0]
print(b.get("date"), len(rows), "picks on the board ·", n, "Most Likely bets journaled this week")
EOF
sudo journalctl -u qellys --since "1 hour ago" | grep "Most likely:" | tail -3
```

Want: the journaled count at least the board count, and one build
printing a larger "Most likely: N row(s) journaled" as it catches up.
Thursday's Packers pick cannot be caught up: the board keeps no copy of
a game's picks after kickoff and it was never journaled.

## NEXT TIME HOME — from 2026-09-24, in this order

Ethan, 2026-09-24: *"save all the code u need me too run for when im
home."* **Nothing below writes anything** — every block only reads, so
any of them is safe mid-cycle. Paste each output back with its number.

**1. Which code is running** (want the newest commit on the branch —
steps 7-9 need today's):

```bash
cd /srv/qellys && cat data/autoupdate.json; echo
```

If it shows an older commit, wait five minutes and run it again — the
auto-update pulls AND restarts the site. (A hand `git pull` does not
restart it, so the web process keeps running the old code.)

**2. The wind table** (about a minute; fetches ~75 small files from
Open-Meteo). After three runs on 2026-09-23 a forecast takes the measured
cut of its own range (`engine/weather.WIND_FORECAST`); this confirms the
board gives what the games say:

```bash
cd /srv/qellys && python3 wxfit.py --scale | tail -8
```

Want: the last line ending "nothing to change". A CHANGE line prints the
new rows — paste them.

**3. The MLB Live tab holds the night** (seconds). The live scoreboard
now reads the same baseball day as the board, rolling at 5 AM Eastern:

```bash
cd /srv/qellys && python3 -c "import json; d=json.load(open('web/data/live_mlb.json')); print(d['date'], len(d['games']), 'games,', sum(g['live']['state']=='live' for g in d['games']), 'live')"
```

Want: between midnight and 5 AM Eastern, the PREVIOUS day's date, with a
late game still showing as live. After 5 AM, today's date. And on the
phone, a bet whose game has ended sits under "N finished — waiting on the
official result", not in the live list.

**4. Weather reached the football games** (seconds):

```bash
cd /srv/qellys && python3 homecheck.py weather
```

Want: every outdoor NFL game "forecast" (a London or Rio game included),
and "rows the weather moved" wherever a game is at 7+ mph or rain is 30%+
likely.

**5. Every number still traces to its model** (seconds):

```bash
cd /srv/qellys && python3 homecheck.py inputs | grep -E "wiring|LOOK"
```

Want: every league "every step and card reaches the number", and nothing
under LOOK AT THESE.

**6. On the phone, no command:** tap any Most Likely pick. The page
should open on that pick (its side, line, book and chance) with the green
"Why it’s likely" card straight under it. Tap an Edge bet — its page is
unchanged.

**7. The Most Likely board holds its picks** (seconds — best a few hours
after the update, so there is a day of refreshes to read). Ethan,
2026-09-24: *"they seem too change alot so it's hard too judge what picks
the models are comfortable with."* A pick now keeps its number and its
seat between refreshes (`engine/likely.HOLD_MARGIN`), and every build
counts what changed and why:

```bash
cd /srv/qellys && python3 homecheck.py hold
```

Want: by the afternoon most picks under "up 3h+", and under "left" mostly
"its game started". A lot of "a likelier pick took its seat" or "no
longer offered" means something else still moves the board — paste it.
On the phone: Most Likely rows read "Since 9:12 AM" or "New", and a
pick's page says when it went up and at what chance.

**8. The site audit's box checks** (seconds each; read-only). The audit
(`docs/AUDIT_2026-09-24.md`) ran on this machine's demo boards; three
numbers only the box has:

```bash
cd /srv/qellys && python3 homecheck.py weight
```

(8a, M-3) Each board's private size beside what a phone is now served
(the ladders and the repeated shelf rows are cut from the served copy —
`engine/served.py`). Want the "served" number well under the "private"
one on every board, and the MLB one most of all. Needs one build after
the update, so the boards are republished through the new code.

```bash
cd /srv/qellys && python3 homecheck.py grading | grep -iE "mlb|no log" | head -20
```

(8b, H-1, H-4) Any MLB Most Likely rows stuck open because the hitter
sat — "player has no log". Before today's fix the book could journal a
projected lineup; paste what it shows and I will say which to void. Run
it again the morning after the first playoff games (Wednesday, Sep 30):
playoff props now grade off the box score, and want no MLB rows there.

```bash
cd /srv/qellys && python3 -m engine.askbot usage
```

(8c, H-3) Ask's real daily spend so far, to set the new ceilings. The
defaults are 100 questions per account and $25 a day. To change one
(neither is a secret, so the value goes inline), for example:
`cd /srv/qellys && sudo ./deploy/setenv.sh QB_ASK_DAILY_USD 40` — then
restart the site for it to take (`sudo systemctl restart qellys`).

```bash
cd /srv/qellys && python3 homecheck.py nba
```

(8d, NBA readiness) Two counts only the box has. Rows the nightly NBA
ingest filed under the calendar year rather than the season (a March game
as "2027" beside a season filed as "2026" — the board reads by season, so
from January those games would have fallen out of every player's form),
and any basketball prop already graded won or lost off a 0:00 box-score
line (a player who sat — the book voids those; the settler now does too,
going forward only). Paste it: I will say whether 9b is needed, and past
grades change only on your yes.

**9. Turn on the trimmed code and the strict script policy** (about a
minute; **this one changes the box**). Both ride the Caddy config, which
only the deploy installs — it validates the new file first and keeps the
running one if it does not validate, so the site cannot go down on it.
The trimmed code cuts a first visit from about 1.1 MB to about 0.7 MB;
the strict policy means no script runs that the site did not send
(`docs/AUDIT_2026-09-24.md`, M-2 and M-4):

```bash
cd /srv/qellys && ./deploy/deploy.sh --no-tests
curl -sI https://qellysbook.com/ | grep -io "script-src [^;]*"
curl -s --compressed https://qellysbook.com/js/app.js | wc -c
```

Want: `script-src 'self'` (no `unsafe-inline`), and the size about
1,430,000 (it was about 2,200,000 with the comments). Then force-quit the
app on the phone, reopen, and tap around — My Bets, the Record chips, a
Most Likely pick. Anything dead, tell me which.

**9b. Only if 8d found wrong season labels — fix them** (seconds; **this
one changes the history database**). It moves each row to its season, or
deletes it where a correctly labelled copy already exists. Run it once
without `--apply` first; it prints what it would do:

```bash
cd /srv/qellys && python3 -m engine.seasons relabel nba
cd /srv/qellys && python3 -m engine.seasons relabel nba --apply
```

Want the second run to end with every count at 0 fixed on a re-run.

**10. SATURDAY ONLY — are college receptions priced?**

```bash
cd /srv/qellys && python3 homecheck.py inputs | grep -A6 "cfb:"
```

Want: `receptions … priced` above 0%.

**11. Whenever there is a quiet minute** (parked since 2026-09-21):

```bash
cd /srv/qellys && python3 homecheck.py bench; python3 homecheck.py sizing; python3 homecheck.py shelves
```

**Decisions only you can make** (from `docs/AUDIT_2026-09-23.md`, no
command): 3 — keep the "Zeno" name and say who he is where it first
appears? · 6 — where the Predict / Fantasy / Memes tiles sit · 13 — trial
length · 14 — switch on the privacy-safe usage counts (built, off) and
approve the policy wording · 15 — a one-time "What do you bet?" card, yes
or no · 18 — rename the grade words or keep them · 20 — the postal
address for the footer. And from the site audit (`docs/AUDIT_2026-09-24.md`):
H-3 — are 100 Ask questions per account and $25 a day the right
ceilings? (Everything else in that audit is fixed — your "fix all
issues": the brighter red and lighter grey, the stadiums back at the top of
Home with the picks under them and the tool tiles last, the shorter game strip and the one Share
button are live with the update. Say if any of them should go back.)

## AFTER THE WIND FIX — ANSWERED into NEXT TIME HOME (above)

Tonight's answers (Ethan's droplet, 2026-09-23 night): the trade-tape
indexes took the wallet history from 233 s to 8.5 s; college 2026 closes
0 → 44; wiring clean on all four leagues; all 14 outdoor NFL games
forecast (Rio found at the Maracanã); baseball's short starts and short
games measured KEEP (`engine/exitfit.py`); the WNBA confirmed the hoops
rule on our own data. The wind took three runs of `wxfit.py --scale`: the
median ratio (×0.714) was a calm-day artifact, one best scale (×1.18)
traded misses, and the per-range table of measured cuts is now the table
the board applies to a forecast (`engine/weather.WIND_FORECAST`).

## NEXT TIME HOME — 2026-09-23 night — ANSWERED (above)

Ethan, leaving again: *"start doing all that shit and save the codes for
me too run when I'm back home."* Everything below is copy-paste. Only
step 2 changes anything (it adds two database indexes, with the site
stopped for about a minute). Paste every output back.

**1. Which code is running** (want the newest commit on the branch):

```bash
cd /srv/qellys && cat data/autoupdate.json; echo
```

**2. The prediction-market indexes** — the build ran 248 s against a
180-second kill, 207 s of it adding up 3.9 million trades from 144,039
wallets with no index that carries the dollars
(`engine/predmarket.BUILD_INDEXES`). Site down about a minute:

```bash
cd /srv/qellys && sudo systemctl stop qellys && sudo -u qellys python3 -c "from engine import predmarket as pm; pm.build_indexes()"; sudo systemctl start qellys
sudo -u qellys timeout 300 python3 pm_build.py --out /tmp/pm.json | grep -E "wallet history|recent tape|Wrote"
```

Want: "wallet history" a few seconds after "recent tape", not ~200.

**3. This season's college closes, backfilled.** The published closes stop
at the 2025 season (cfbfastR's newest row is 2026-01-20), so 2026 read
zero. Every college build now copies each finished game's last pre-kickoff
line from our own tape (`engine/lineledger.closes_into_games`) for the
last fourteen days; this does the whole season once:

```bash
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, lineledger as L; from engine.sources import cfbdata as C; c=db.connect(); print(L.closes_into_games(c, 'cfb', C.load_range('2026-08-22', '2026-09-23')))"
python3 -c "from engine import db; c=db.connect(); print([tuple(r) for r in c.execute(\"SELECT season, COUNT(total) FROM games WHERE sport='cfb' GROUP BY season\")])"
```

Want: the first line counting games, spreads and totals written; the
second showing 2026 above zero. It can only fill games the build saw a
book line for, so early-August games may stay empty.

**4. Every number still traces to its model** (all leagues, full boards):

```bash
cd /srv/qellys && python3 homecheck.py inputs | grep -E "wiring|LOOK"
```

Want: every league "every step and card reaches the number" and nothing
under LOOK AT THESE.

**5. SATURDAY ONLY — are college receptions priced?** On the one-game
Wednesday slate none were, and the cache showed books posting receptions
about half as often as receiving yards. On a full Saturday this says
whether it is the books or a matching bug:

```bash
cd /srv/qellys && python3 homecheck.py inputs | grep -A6 "cfb:"
```

Want: `receptions … priced` above 0%.

**6. Weather reaches the games and the numbers** (read-only, seconds).
Until tonight the NFL forecast stopped at the build's console — every
outdoor game a projection or a card saw was the 60°F / 6 mph prior — and
the wind bands were hand-set. Both are fixed; this says the forecast is
landing on the live board:

```bash
cd /srv/qellys && python3 homecheck.py weather
```

Want: every outdoor NFL game "forecast" (none "on the prior") once the
next NFL build has run, and "rows the weather moved" wherever a game is
listed at 8+ mph or 30%+ precipitation. If every outdoor game is on the
prior, the box cannot reach Open-Meteo — paste `grep -i "Weather:"
/var/log/qellys/*.log | tail -3` or the build's journal line.

**7. Does the forecast read wind on the scale the bands were measured
on?** (fetches ~75 small files from Open-Meteo, about a minute; writes
nothing). The bands were measured on the wind the game book reports at
kickoff; the board reads Open-Meteo's forecast for the kickoff hour. This
compares the two over 2023-2025:

```bash
cd /srv/qellys && python3 wxfit.py --scale
```

Want: "same scale — the bands hold". If it says DIFFERENT SCALE, paste
it: the bands get read on the forecast's scale.

**8. Games a player left early — baseball, on our own history**
(read-only, a minute or two). The NFL keeps a game a player left hurt and
names it (measured); basketball now drops an OLDER early exit from the
minutes base when his last five are clean and keeps a recent one
(measured on four seasons of both leagues). Baseball has not been
measured yet — a starter pulled after an inning, a hitter's one-at-bat
game — and our own database holds every start's outs and every game's
plate appearances:

```bash
cd /srv/qellys && python3 exitfit.py mlb; python3 exitfit.py wnba
```

Paste both. For each market it shows how centred the next game's
projection is ("above" near 0.50) with the short games kept, dropped when
old, and dropped always. The rule that centres it goes in next.

## LIVE. Did today's model work reach the board? (read-only, seconds) — ANSWERED 2026-09-23

Answered from the phone that evening: the Status page's Model builds
section showed every league rebuilding on the new code, and the full run
confirmed the NFL board (609 props, 52 thin-sample players, Nabers and
Malachi Fields on it, the lineup step moving 13 rows). Kept for the
commands, which still answer the same question after any push.

Ethan, 2026-09-23: *"the same most likely pics that we had earlier are
the same ones that are there now."* From here the site cannot be
reached, so the answer is on the box. **From the phone first:** the
Status page now has a **Model builds** section — the code the site is
running and each league's last rebuild on it. If NFL says *build failed*,
the line after it is the reason, and the board you are reading is the
last one that built. For the whole picture:

```bash
cd /srv/qellys && python3 launch.py --boards
cat data/autoupdate.json
sudo journalctl -u qellys --since "6 hours ago" | grep -E "NFL|kept the last board|timed out|Traceback" | tail -40
```

Want: `autoupdate.json` naming the latest commit, and NFL rebuilt after
it. Paste all three outputs back.

## INPUTS. Is every input the models read actually moving a number? (read-only, seconds)

Ethan, 2026-09-23: *"do another scan and make sure all the models aren't
being affected by issues where data isn't being used or being pulled."*

The scan from here found three in the NFL (odds bought for markets no
position was built for, every receiver labelled "wr1", passing TDs with
no matchup) and fixed them. It could not see MLB, NBA, WNBA or college,
because their feeds do not reach this sandbox — this reads every
league's LIVE board on the box and asks the same questions of each:

```bash
cd /srv/qellys && python3 homecheck.py inputs
```

Per league and market: the share of rows each step of the model (matchup,
weather, park, umpire, player memory …) actually moved, whether any row
has a real book price, and whether a position's roles all say the same
thing. Anything under **LOOK AT THESE** is an input wired in and moving
nothing. Paste the whole output back.

Since the second NFL pass (same day, *"make sure everything we pull … is
actually being projected to the pick … Most Likely is number one"*) each
league also prints a **wiring** line: every row's base × every step equals
the projection it shows, the "who plays around him" step equals what its
QB and teammate cards say was applied, and every Most Likely row's
projection and probability come from its prop row. "every step and card
reaches the number" is the answer to want; anything else is listed.

## CFB. The college closing lines and the college matchup (read-only, a few minutes)

The college scan (2026-09-23) found every college closing spread, total
and moneyline being "attached" and written to nothing — the ingest looked
each game up by ESPN's number and then wrote to that number instead of
the stored row. The nightly maintenance re-fills them by itself once this
deploys (it re-runs the fill whenever the table holds too few, and it has
been holding none). Then re-measure the college matchup on the box's own
data and paste it back:

```bash
cd /srv/qellys && python3 -c "from engine import db; c=db.connect(); print(c.execute(\"SELECT season, COUNT(total) FROM games WHERE sport='cfb' GROUP BY season\").fetchall())"
cd /srv/qellys && python3 cfbdefensefit.py
```

The first line should show hundreds of totals per season (it was zero).
The second prints, per market, what `engine/defensevs.TRANSFER_CFB` ships
against what this box's data measures.

## PARKED 2026-09-21 — three read-only checks, whenever there is a quiet minute

Ethan, home that evening: *"save all of this to pick up later. the main
thing i wanna work on is … Zenos Record."* So nothing here is due; the
three below just tell me what the box measured, and each has its own
section further down.

```bash
cd /srv/qellys && python3 homecheck.py bench     # did benching WNBA help or hurt the record
cd /srv/qellys && python3 homecheck.py sizing    # what the likelihood board should be staking
cd /srv/qellys && python3 homecheck.py shelves   # which markets the record says to stop
```

Paste all three back together when convenient. None of them writes.

---

## ZENO'S RECORD. Setting it up (one-time, two minutes)

Ethan, 2026-09-21: *"implement my juice reel record on the site … a spot
on the record page called "Zenos Record" … a page for "Zenos Picks" …
just for me so my record can show on the site for everyone. no one else
should be able to log in and show this data."*

**What is built.** `Zeno's Record` on the Record page and a `Zeno's
Picks` tab, both read from record.json's `zeno` block, both public. The
store is `data/zeno.db` — separate from the model's journal on purpose,
because these are settled by the BOOK and never re-graded. The only
write path is an owner token; there is no per-account path at all.

**How it syncs.** Juice Reel has an API (juicereel.com/api-docs) and
every bets endpoint takes *"Owner only: Client ID + secret"* — for the
account that owns the app, the two keys are the whole credential. The
settle pass pulls `/oauth2/bets/changed` every cycle and imports what
moved, so a bet placed this afternoon is on the page by the next build.
The CSV import below stays as the fallback.

**Getting the two keys (once).** In Juice Reel, create an API
application — look for "Developer" / "API" / "Create an application" in
the web app while logged in, or under the app's settings. Request the
scopes `bets.open.read` and `bets.settled.read`. It gives you a client
ID and a client secret. Store them like every other key (each prompts;
paste at the prompt, never in chat):

```bash
cd /srv/qellys && sudo ./deploy/setenv.sh QB_JUICEREEL_CLIENT_ID
sudo ./deploy/setenv.sh QB_JUICEREEL_CLIENT_SECRET
sudo systemctl restart qellys
```

Prove they work, then pull the whole history once:

```bash
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep ^QB_JUICEREEL | xargs) python3 -m engine.juicereel check
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep ^QB_JUICEREEL | xargs) python3 -m engine.juicereel sync --full
```

`check` prints `ok — connected as 'Zenos_Props'`. `sync --full` prints
`N changed → N added …`. From then on the build does it by itself; the
log line `Juice Reel sync:` in the settle pass says so every cycle, and
`Juice Reel sync skipped:` names the reason when it cannot.

**1. Set the owner token** (prompts, never in history — same as every
other secret):

```bash
cd /srv/qellys && sudo ./deploy/setenv.sh QB_OWNER_TOKEN
sudo systemctl restart qellys
```

Pick something long and random — at least 32 bytes:
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (audit
E-16). Without it every import answers 503 — closed, not open.

**2. Import an export.** Two ways; the first needs no SSH at all.

From your laptop, with the file next to you:

```bash
read -rs QB_OWNER_TOKEN && export QB_OWNER_TOKEN   # paste, Enter; never in shell history (E-16)
curl -sS -X POST https://qellys.com/api/zeno/import \
  -H "X-Owner-Token: $QB_OWNER_TOKEN" -H "X-Zeno-Source: juicereel" \
  --data-binary @juicereel.csv
```

Or on the box — **as the service user, never as root.** The service runs
as `qellys` under a locked-down filesystem, and a store created by root
is one it can read the day it is made and never write again. The
command refuses to run as root and prints this line if you forget:

```bash
scp juicereel.csv you@qellys.com:/tmp/juicereel.csv      # from the laptop
cd /srv/qellys && sudo -u qellys python3 -m engine.zeno import /tmp/juicereel.csv
```

Either prints `N added · N updated · N unchanged · N skipped`. Re-running
the same file is a no-op; a ticket that was open and is now settled is
UPDATED, never duplicated. If it prints `headers not recognised`, paste
that line back to me — that is the sample I need.

**3. Look:** `curl -sS https://qellys.com/api/zeno | head -c 600`, or
just open the Record page. The block lands in record.json on the next
build.

**4. Post a bet from your phone (2026-09-26).** Your props and parlays are
for members; your record stays free. Open **Zeno's Picks**, scroll to the
bottom, tap **"Zeno? Sign in to post a bet"** and paste the same owner
token once (it stays on that phone). Then:

- **Post a bet** — straight/prop or parlay (one leg per line), book,
  sport, odds, stake. It reaches members the moment you tap **Post it**.
- **Grade it** — under each open bet in "Riding now": Won, Lost, Push,
  Void. Your record and the combined line update on the next build.
- When Juice Reel's API is on, its copy of a bet you posted takes over
  the posted one (same book, stake, price and day) — never a second bet.
- Or send Claude the slip: it goes into `data/zeno_manual.json`, and the
  droplet imports it on the next record build after it pulls.

**Members' copy:** `data/built/zeno.json`. The public `web/data/zeno.json`
is a locked stub that says how many bets, never which.

---

## TIMING. Why these take longer than they read (read first)

Ethan, 2026-09-16, after running seven of these back to back: *"these
took far longer than the doc's one-to-two-minute estimates, around 25
minutes each, because four processes were sharing the single core."*

The estimates in this file were wall-clock on an idle box. The droplet is
ONE core and the 5-minute deploy timer, the 45-minute build cycle and the
nightly fitters all want it. Run these one at a time, and if a build is
in flight expect a replay or a backtest to take tens of minutes rather
than the seconds it costs on its own.

To see what you are sharing the core with before you start:

```bash
uptime
systemctl list-units --type=service --state=running 'qellys*'
ps -o pid,pcpu,etime,cmd --sort=-pcpu -e | head -8
```

A load average near or above 1.00 means the next block will be slow, not
broken. Nothing in this file is time-sensitive — waiting for a quiet
minute costs less than reading a number you then have to re-run.

**And which commit the box is on, before anything else.** The deploy
timer pulls every five minutes, so a block run a moment too early reads
the BEFORE-picture and looks like the fix did not work:

```bash
cd /srv/qellys && python3 homecheck.py head
```

`homecheck.py` is where the checks in this file live that used to be
pasted heredocs — `python3 homecheck.py` on its own lists them, and
`python3 homecheck.py all` runs every read-only one in a single paste.

---

## SHARP. Did the MLB board get its sharp witnesses back? (read-only, seconds — but see the timing note)

**This is the one to run first.** On 2026-09-16 your MLB board had thirty
game rows and **not one** carried a sharp or a market witness, so
`potd.shortfall` refused all thirty with *"only our own model disputes
this price"* — the league with by far the most data could not produce a
Pick of the Day on any day.

The cause was one boolean. `engine/mlb/pipeline.py` calls the sharp
pricers exactly as the football pipeline does, but `sharp_anchored` was
being written by each pipeline *after* the card came back — NFL three
times by hand, college once, **MLB never**. Fixed at the source: the
function that prices the card sets it now.

Wait for one full build cycle after you pull (the timer is every 5
minutes, so give it ~10), then:

```bash
cd /srv/qellys && python3 potd_report.py mlb
```

**What good looks like:** the witness breakdown names `sharp` on some
rows. Before the fix it read `model` on all thirty.

```bash
# The blunt version — count the witness tiers straight off the board.
#
# It goes through `launch.BOARD_FILES` and `gate.board_source` rather
# than opening a path by hand, for two reasons this file has already
# been bitten by: MLB's board is NOT `mlb_picks.json` (it is
# `mlb_recommendations_picks.json`), and `web/data` is the PUBLIC copy
# with `most_likely` stripped out by the paywall. Guessing either one
# gives you a confident zero.
cd /srv/qellys && python3 -c "
import json
from collections import Counter
import launch
from engine import gate
p = gate.board_source(launch.BOARD_FILES['mlb'])
b = json.load(open(p))
rows = [r for r in (b.get('most_likely') or []) if r.get('kind') == 'game']
print('read:', p)
print('game rows:', len(rows))
print('sharp_anchored:', Counter(bool(r.get('sharp_anchored')) for r in rows))
print('prob_source:  ', Counter(r.get('prob_source') for r in rows))
"
```

| if you see | it means |
|---|---|
| `sharp_anchored: {True: n}` with n > 0 | **fixed** — the witness is reaching the board |
| all `False` and `prob_source` all `model` | Pinnacle quoted nothing on tonight's slate, OR the fix has not deployed yet — check `git log -1` in /srv/qellys |
| `prob_source` never says `market` | expected, and NOT a bug — see block MKT below |

---

## BAR. Where should the EV floor sit? (#164-adj) — ANSWERED: IT STAYS

**Ran 2026-09-16. The floor was never the thing holding the product
back, and the table says so in the column built to say it.**

```
  floor  days w/ pick   bets      W-L       ROI
  0.0%            37     37    25-12     +27.9%
  0.5%            37     37    25-12     +27.9%
  1.0%            37     37    25-12     +27.9%
  1.5%            37     37    25-12     +27.9%
  2.0%            37     37    25-12     +27.9%   <- shipped
  3.0%            30     30    18-12     +12.9%
  4.0%            22     22    14-8      +19.5%
```

**Flat across the entire range below the shipped floor**, then falling
when raised. Ethan: *"There is no cliff to find beneath 2.0% because
nothing down there is being excluded."* Not one extra day is bought by
lowering it, at any value tried.

**The binding column names the real constraint,** and it is the same at
every floor: on days with no pick the bar that turned the best row away
is *"the gap is too big to trust — the sharp side has probably moved"* —
`MAX_EV`, not the EV floor. The thing standing between the card and a
bet more often is the sharp-witness disagreement gate.

**~~AND THAT CEILING IS EARNED~~ — WITHDRAWN 2026-09-16.** This block said
the leans `MAX_EV` excludes at 7-15% edge ran **-23.1% over 12 bets**, so
the gate was refusing a population that loses money. Ethan re-ran the
same replay later that day, with more days settled:

```
  the leans, by the edge they were refused at:
    under 4%            1 bets     1 won    +1.18u  ROI +118.0%
    4-7%                3 bets     2 won    +1.77u  ROI +59.0%
    7-15% (suspect)    11 bets     6 won    +2.25u  ROI +20.5%
```

**+20.5%, not -23.1%.** Two readings of one replay, opposite in sign, on
about a dozen bets. That is not a finding reversing — it is a sample too
small to have supported either claim, and I stated the first one without
saying so. `MAX_EV` is **UNPROVEN**, not earned.

It stays at 7% for now, because nothing argues for moving it either: the
positive read is +20.5% on 11 bets and the whole lean book is +34.7% ±
29.9%, about 1.2 standard errors from zero. Revisit when that band passes
~40 bets. Nothing else in the product rests on it.

**Read the ROI last and lightly.** +27.9% is 37 bets, and the dip to
+12.9% at 3.0% and back to +19.5% at 4.0% is not a shape, it is the
noise this block warned about. Ethan: *"The finding here is the flatness
below 2.0%, which is structural rather than statistical, not the return
figure."* Agreed, and that is the right way round.

**THE NFL TABLE CANNOT ANSWER ANYTHING YET** — one day with a priced
game, zero picks at every floor. The season is two weeks old. Re-run
once the harvest has a month in it.

```bash
cd /srv/qellys && python3 potd_backtest.py mlb --sweep-ev
cd /srv/qellys && python3 potd_backtest.py nfl --sweep-ev   # from mid-October
```

## KX. Why the exchange tier is dead — BOTH SPORTS, ran 2026-09-16 (read-only, seconds — but see the timing note)


**RAN, AND THE PREMISE WAS TOO NARROW.** Ethan, 2026-09-16: NFL is zero
matched on 60 usable markets and **MLB is zero matched on 42** — this was
filed as an NFL problem and baseball has it identically. The cause is
reproduced in KX-2 below and it is not the spelling: `match_game` needs
BOTH clubs in the market's text and the exchange titles name only the
winner. Read KX-2; this block is kept for the census it prints.

Your 2026-09-16 run said: nine NFL rows, 58 usable Kalshi markets, zero
matched. The report called that *"OUR name matching"* — **and it could
not actually know that.** `NO_MATCH` was one bucket covering three
different failures with three different fixes: our spelling of a club
differs from the exchange's, the board is a day stale so no market names
tonight's games, or the game matched and we could not resolve which side
the YES pays on.

I could not tell them apart from here, and guessing at a matcher change
risked breaking MLB — **which I assumed was working, and it is not.** The
2026-09-16 run put baseball at zero matched too, so there was never a
working sport to protect. So the census now names the step, and
prints **both parties' spellings**:

```bash
cd /srv/qellys && python3 potd_report.py nfl
```

Look for these two lines under `Exchange`:

```
      exchange says:  Chiefs vs Bills
      the board says: BUF @ KC   [9 game(s) on the board, 0 matched one]
```

**That line is the whole answer.** Read it like this:

| if you see | the cause is | and the fix is |
|---|---|---|
| exchange naming teams the board also names, but spelled differently | our name matching | `exchangefair.names_for` / `kalshi._name_tokens` |
| exchange naming **different games** from the board | the board is stale, or it is tomorrow's slate | the build cycle, not the matcher |
| `0 game(s) on the board` | the NFL payload shipped no `games` list | `pipeline._game_to_dict` |
| `the exchange priced this game but not this side` | `kalshi.yes_team` could not name a side | that function, not the matching |

Paste those two lines back and I can fix the real one in a single pass.

**Also worth running for MLB**, since that league's exchange tier was
working and this change touched the shared code path:

```bash
cd /srv/qellys && python3 potd_report.py mlb | grep -A4 Exchange
```

---

## KX-2. The one thing the exchange fix needs (read-only, seconds)

Ethan ran KX on 2026-09-16 and it named the failure exactly:

```
NFL  exchange says:  Buffalo wins; Philadelphia wins
     the board says: DET @ BUF; CAR @ ATL   [16 games, 0 matched]
MLB  exchange says:  New York Y wins; Chicago WS wins
     the board says: CWS @ CLE; SF @ STL   [15 games, 0 matched]
```

**It is not the spelling.** Reproduced here: "Buffalo wins" tokenises to
`{BUFFALO}`, and BUF's names tokenise to `{BUFFALO, BILLS}`, so the home
side matches perfectly. What fails is that `kalshi.match_game` requires
BOTH teams to appear in the market's text, and the exchange's title names
only the winner. Detroit is nowhere in "Buffalo wins", so the game is
never matched. That rule is not a mistake — it is there because one name
alone matches every futures market and half the league — and baseball
shows exactly why it cannot simply be relaxed: "New York Y wins"
tokenises to `{NEW, YORK}`, which matches the Yankees AND the Mets.

So the fix needs a second identifier, and Kalshi puts one in the event
ticker.

**SHIPPED 2026-09-16 — this block is now a CHECK, not a blocker.** The
paragraph above used to end "I have not seen this box's tickers and will
not guess their shape", and it was wrong about what this repository
already knew: `tests/test_prediction_desk.py` has carried
`KXMLBGAME-26AUG111840CLEDET-CLE` as a fixture since the desk shipped,
and both clubs are in the middle segment. `match_game` was already
feeding `event_ticker` into its haystack and simply could not SEE them —
`_name_tokens` splits on non-alphanumerics, so `26AUG111840CLEDET` is one
token and `"CLE" in hay` is False.

`kalshi.match_game` now also searches the ticker text for both club codes
as substrings, which needs to know nothing about where in the ticker they
sit or what separates them, and takes the match only when EXACTLY ONE
game on the board fits — so the Yankees/Mets case and an MLB doubleheader
are both refused rather than guessed. The two-club rule is intact.
`tests/test_the_exchange_finds_the_game_in_its_ticker.py` runs Ethan's
own two pasted lines as fixtures.

**CONFIRMED ON THE LIVE FEED 2026-09-16 — #256 IS CLOSED.** Ethan ran it
against `b4ce344`:

```
KXNFLGAME-26SEP17DETBUF-BUF   "Buffalo wins"
KXMLBGAME-26SEP161340NYYMIN-NYY   "New York Y wins"
```

Both clubs concatenated in the middle segment, exactly the shape the
fixture had. `potd_report mlb` went from **0 matched to 31 of 45 usable
markets matched a game**. The tier is alive.

**THE BOTTLENECK MOVED, and it is worth knowing where to.** That same
report reads `0 of 1 moneyline row(s) priced`: 15 games on the board, 31
matched markets, and the MLB board carries exactly ONE moneyline row for
them to attach to. Kalshi lists game winners and nothing else
(`exchangefair.MARKETS`), so the exchange tier's ceiling is now how many
moneyline rows the edge board publishes, not the matcher. That is a
board-composition question, filed separately from this block.

**RUN IT AS THE BUILD USER.** Ethan, 2026-09-16, declining to run the
first version of this: *"KX-2 writes Kalshi cache files. As root they
come back root-owned, the build user then silently falls back to a stale
cache, and there are already 6,098 root-owned files in that directory."*

That is a live problem this file caused, not a hypothetical — every
block here that touches `fetch_text` writes into the shared cache, and a
root-owned entry is one the build can read and never replace. The
`sudo -u qellys` below is not optional, and there is a cleanup for the
6,098 underneath it.

```bash
cd /srv/qellys && sudo -u qellys python3 homecheck.py exchange
```

**`sudo -u qellys` is still not optional** — this is the one check
that fetches, and a cache entry written as root is one the build can
read and never replace. The script refuses quietly to pretend
otherwise: run it as root and the first line of its output says so.

**Paste the whole thing.** Six rows per sport is enough. What I am
looking for is whether `event_ticker` carries both clubs — something like
`...25SEP14DETBUF...` — because if it does the fix is to match the
abbreviation PAIR inside it, which disambiguates the Yankees from the
Mets without loosening the two-team rule at all.

**And the 6,098 already there**, which are silently costing every build
a fresh pull. Count first, then fix ownership — no deletion, because a
valid cache entry is worth keeping whoever wrote it:

```bash
sudo find /srv/qellys/data/cache -user root | wc -l
sudo chown -R qellys:qellys /srv/qellys/data/cache
sudo find /srv/qellys/data/cache -user root | wc -l   # expect 0
```

If the second count is not zero, something is still writing there as
root on a timer and that is worth finding before anything else in this
file.

---

## MKT. The measurement MLB never had (read-only, ~1 minute)

The second half of why MLB showed no witness: `likely.GAME_RANK_MARKET`
has entries for **nfl.moneyline (0.722)** and **cfb.moneyline (0.7905)**
and no `mlb` key at all — so `ranking_number` can never return "market"
for baseball. That is a missing measurement, not a bug: nothing has ever
replayed MLB's de-vigged consensus against closes.

`gamerank.measure_market_moneyline` has existed since 09-07 and **nothing
could run it** — `measure()` walks the model's markets only, and the CLI
walks `measure()`. The two football numbers were taken by calling the
function by hand. There is now a flag:

```bash
cd /srv/qellys && python3 -m engine.gamerank --sport mlb --market
```

It prints the market's AUC beside the model's, on the same quoted games,
and gives a verdict. **It will not print a table entry off a thin
sample** — under 400 quoted games it declines and says why.

```bash
# Sanity: the same command on NFL should reproduce the 0.722 already
# written down. If it does not, the harvest changed under us and BOTH
# football entries need re-reading before the MLB one is trusted.
cd /srv/qellys && python3 -m engine.gamerank --sport nfl --market
```

**Paste both.** If MLB's market figure beats its model figure on a real
sample, the verdict prints the exact line to add and I will add it. If it
does not, we leave the table alone and the honest answer is that our MLB
model ranks as well as the book does — which is worth knowing either way.

---

## BT. Re-read the Pick of the Day verdict under the new ceiling (~30 seconds)

`potd.MAX_EV` landed on 09-16: a gap wider than 7% is refused, because
`gamebets._sharpify` already grades those Pass at a stake of zero on the
edge board. Your own bucket split is what made the case — the 7-15% band
went −7.2% over 27 bets while the two tighter bands went +71.4% and
+47.1%.

The replay now splits the **leans** across the same bands, which is the
only place the question *"was refusing them right?"* can still be asked:

```bash
cd /srv/qellys && python3 potd_backtest.py mlb
```

**The new block to read** is under `IF THE LEANS HAD BEEN BET TOO`:

```
    the leans, by the edge they were refused at:
      7-15% (suspect)     n bets   n won   +/-n.nnu  ROI +/-n.n%
```

A **negative** ROI on that line is the ceiling earning its keep. A
**positive** one means it is costing money and I should reconsider.

Also worth one run across everything, now that MLB should have witnesses:

```bash
cd /srv/qellys && python3 potd_backtest.py --all
```

**One decision for you in here.** `MIN_FAIR` (50%) and `MAX_EV` (7%)
cross at **+114**: above that price no bet can be both at-or-above the
fair floor and at-or-below the trust ceiling, so the usable band is
−142…+114 while `MAX_ODDS` still reads 190. Both bars are defensible
alone and I left it standing. Reopening the plus side means dropping
`MIN_FAIR` below 50% for sharp-anchored rows — that is your product bar
("the pick should be more likely to win than lose"), so it is your call,
not a consequence of a measurement. Say the word either way.

---

## GATE. Which refusal is costing money (#164) — RAN, STILL UNPROVEN

**Ran 2026-09-16. The negative point estimate reproduces on the droplet
and it is still not evidence.**

Admitted ran −10.1% over 82 bets against refused at −6.7% over 1,655 — a
difference of **−3.4% with an interval of [−25.6%, +20.0%]**. That
straddles zero by a wide margin on both sides, which is the honest
reading: 82 bets cannot separate a board that is working from one that
is not, and the point estimate being negative is not a finding.

**The leads, which are leads and not results.** Every one is a small
slice, and the tool says to read them that way:

| refusal | ROI if admitted | rows |
|---|---|---|
| confidence just under the 6.0 bar | +23.2% | 21 |
| confidence, next band down | +13.4% | 35 |
| rest deficit | +13.8% | 48 |
| market disagreement | +0.6% | 296 |

The bottom row is the informative one and it is the one that looks
boring: 296 rows is the only sample here with any weight, and it says
that bar is costing nothing and saving nothing. The three positive
slices are 21, 35 and 48 rows — the size at which a coin flip produces
+20% regularly.

**Nothing changes on the board off this.** What would settle it is more
settled bets through the same bars, which arrives on its own. Re-run when
the admitted count is past a few hundred.

```bash
cd /srv/qellys && python3 backtest.py 2025 --weeks 6-17 --gate --real-lines --gate-basis book
```

Note the season positional — the line here omitted it until 2026-09-16
and argparse exited 2 without measuring anything. Weeks 6-17 of 2026 do
not exist yet, which is why the command names 2025.

## ALT. Should we buy alternate spreads and totals? (#253) — ANSWERED: NO

**Ran 2026-09-16. The answer is do not buy, and the tool said so itself.**

Ethan: *"The NFL's six price refusals are all moneyline, where no
alternate exists, and it prints that verdict outright. Baseball has one
addressable spread refusal at −177, but zero of that one clears every
other bar, which is your 'not worth it' row."*

That is the whole case. An alternate line can only rescue a row refused
ON PRICE in a market that HAS alternates — spreads and totals. Every NFL
price refusal was a moneyline, which has no ladder to climb, so the
entire football case is empty by construction rather than by a close
call. Baseball produced exactly one candidate and it failed the other
bars anyway, so buying the ladder would have cost quota to convert zero
rows on either board.

Nothing to re-run. If the shape of the refusals changes — several
spread-or-total price refusals showing up on one board — the question is
worth reopening, and `potd_report.py | grep -A8 "Alternate lines"` is
still the way to ask it.

## BARS. The Most Likely board's safety bars (#165) — nothing to run

Reported here rather than as a command, because the answer came out of
the code: **all of them fire.** `tests/test_likely_bars_are_alive.py`
produces a row for every refusal `likely.admissible` can return and each
one is reachable — the price cap, the likelihood floor, the proxy-price
refusal, the impossible-price refusal, all three credibility bars and the
injury hold.

That matters because a dead bar is invisible in a census: an unreachable
branch reports zero, and zero is exactly what a bar that is simply not
binding tonight reports. So when your `--likely` scoreboard shows a bar
at zero refusals, that now means **not binding**, not broken.

**Still owed on the droplet** (from #165, unchanged):

First read the scoreboard as it stands, so there is a BEFORE:

```bash
cd /srv/qellys && python3 launch.py --likely | tee /tmp/likely-before.txt
```

Then the repair. It lives in `engine/ledger` and takes a connection, and
it is **the only block on this page that writes** — it flips the side on
`home_runs` rows in the `likely` bucket carrying `side='OVER'` with a
probability above a coin flip, which is a bet nobody could have made
(`likely.MIN_PROB` refuses a home-run over outright). Idempotent: run it
twice and the second run flips nothing.

```bash
cd /srv/qellys && python3 -c "
from engine import ledger
conn = ledger.connect()
try:
    print(ledger.repair_inverted_likely_sides(conn))
finally:
    conn.close()
"
```

**CORRECTED 2026-09-16.** This line said `db.connect()` and Ethan got
`sqlite3.OperationalError: no such table: bets`. There are two databases:
`db.DEFAULT_DB` is `data/history.db` (games, player logs) and
`ledger.DEFAULT_DB` is `data/ledger.db` (the journal). The function now
raises a message naming that mistake rather than a raw sqlite error.

**And the premise may already be gone.** The `--likely` scoreboard from
that same run reads `home_runs  11  said 94.0%  hit 90.9%` — which is
what a CORRECT row looks like, not the inverted signature (#165 recorded
"said 94.0%, hit 10.0%"). So expect `{'flipped': 0}`, and if that is what
comes back the repair is done and the settle pass below is unnecessary.
Paste the number either way: zero closes it, non-zero means there were
still rows to fix.

It re-OPENS the rows rather than re-grading them, so the settle pass has
to run before the numbers move:

```bash
cd /srv/qellys && python3 launch.py --settle all
cd /srv/qellys && python3 launch.py --likely | tee /tmp/likely-after.txt
```

(The #165 note says `ingest.py --settle all`; that flag does not exist on
`ingest.py` — the settler is `launch.py --settle`, which `ingest.py`'s own
help text points at. Corrected here rather than in the note, because this
is the file you paste from.)

The home-run rows were journaled with the side inverted (said 94.0%, hit
10.0% over 10 rows — 42.8% of all losses from 2.4% of the bets). **Every
band and per-market number in #165 still contains those rows**, so the
before/after is what makes the rest of that task readable. Paste both.

---

## POTD-MLB. Why the MLB Pick of the Day is blank (read-only, seconds — but see the timing note)

**RUN THIS ONE FIRST.** Ethan, 2026-09-16: *"pick of the day for mlb
isn't showing still but nfl is showing And so is CFB."*

MLB-only rules out most of what was suspected: the paywall, the
renderer's error branch and the sign-in state would all hit three
leagues, not one. I found two real defects looking for it (the card never
rendered `potd._repoint`'s explanation, fixed) but **I have not proven
either is what you are seeing.** This names it in one run.

```bash
cd /srv/qellys && python3 - <<'PY'
import json, os, subprocess, time
import launch
from engine import gate, lightboard

print("HEAD:", subprocess.run(["git", "log", "-1", "--format=%h %ad %s",
                               "--date=short"], capture_output=True,
                              text=True).stdout.strip())
print()
hdr = f"{'sport':5} {'copy':6} {'age':>7}  potd      pick   most_likely  notes"
print(hdr)
print("-" * len(hdr))
for sp in ("mlb", "nfl", "cfb"):
    board = launch.BOARD_FILES.get(sp)
    if not board:
        print(f"{sp:5} {'-':6}  NOT IN launch.BOARD_FILES")
        continue
    for label, path in (("full", gate.board_source(board)),
                        ("light", gate.board_source(
                            lightboard.light_path(board)))):
        try:
            age = f"{(time.time() - os.path.getmtime(path)) / 60:.0f}m"
            b = json.load(open(path))
        except Exception as exc:
            print(f"{sp:5} {label:6} {'-':>7}  UNREADABLE  "
                  f"{type(exc).__name__}: {exc}")
            continue
        got = b.get("pick_of_the_day")
        notes = []
        if b.get("pick_of_the_day_error"):
            notes.append("ERROR=" + str(b["pick_of_the_day_error"])[:60])
        if b.get("locked_reason"):
            notes.append("PAYWALL STUB: " + str(b["locked_reason"])[:40])
        if isinstance(got, dict):
            if got.get("relocked"):
                notes.append("relocked=" + str(got["relocked"])[:60])
            if got.get("note") and not got.get("pick"):
                notes.append("note=" + str(got["note"])[:60])
            if isinstance(got.get("pick"), dict):
                p = got["pick"]
                notes.append(f"{p.get('player') or p.get('team')} "
                             f"{p.get('market')} {p.get('odds')}"
                             + (" LOCKED" if p.get("locked") else "")
                             + (" OFF_BOARD" if p.get("off_board") else ""))
        print(f"{sp:5} {label:6} {age:>7}  {type(got).__name__:9} "
              f"{str(isinstance(got, dict) and got.get('pick') is not None):5}  "
              f"{len(b.get('most_likely') or []):>11}  {' | '.join(notes)}")
print()
print("Today's locked Pick of the Day per sport, straight from the journal:")
try:
    from engine import ledger, db
    import datetime
    conn = db.read_only()
    try:
        day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        locked = ledger.locked_potd_picks(conn, day, strict=True)
        if not locked:
            print(f"  none locked for {day} (UTC)")
        for sport, entry in sorted(locked.items()):
            print(f"  {sport:5} {entry.get('player') or entry.get('team')} "
                  f"{entry.get('market')} {entry.get('side')} "
                  f"{entry.get('line')} @ {entry.get('odds')}")
    finally:
        conn.close()
except Exception as exc:
    print(f"  could not read the journal: {type(exc).__name__}: {exc}")
PY
```

A heredoc rather than `python3 -c "..."`, because the quoting in a `-c`
string one level down from a shell one level down from markdown is how a
paste-able command stops being paste-able. It degrades on every line: a
board it cannot read says so and the next one still runs.

**`age` is doing real work here.** A board 300 minutes old on a five
minute timer is a build that stopped, and that alone would explain a
stale or missing card without anything else being wrong.

Read the MLB rows against the NFL and CFB rows — the difference is the
answer:

| MLB shows | it means | fix |
|---|---|---|
| `potd=NoneType` while NFL/CFB are `dict` | the key never reached the file. The build's POTD hook did not run or raised before my 2026-09-16 fix — check `git log -1` in /srv/qellys |
| `potd=dict pick=False relocked=this sport locked…` | **the likeliest one.** MLB locked a pick today that has left the board and cannot be read back. The card now SAYS this; before today it said "No pick today." |
| `locked_reason` set and `ml=0` | the page is being served the paywall STUB, not the board. MLB's is the 8 MB one, so a slow or failed API read falls back further than the others do |
| `err=` anything | the selector raised; the string is the cause |
| identical to NFL/CFB | the file is fine and the problem is in the browser — hard-refresh, then check the console |

**Paste the whole table.** With NFL and CFB beside it as controls, one
run settles which of these it is.

---

## RECORD. Does the page's own file carry every league? (read-only, seconds)

Ethan, 2026-09-19. `grading` came back with college football holding
**285 Most Likely, 8 Edge and 1 Long Shot settled** — all three are
books the Record page renders — and the page was showing him nothing.

```bash
cd /srv/qellys && python3 homecheck.py record
```

**Every layer between the journal and the page is generic**, which is
why this reads the artifact instead of the code. `TRACKED_SPORTS` lists
cfb; `book_records` groups by sport with no league list; the scope chips
loop `tracked_sports` and deliberately show a league with nothing
journaled rather than hide it; `recBookSections` just indexes
`br[scope]`. Nothing in that chain can single a league out. So the
disagreement, if there is one, is between the journal and the published
file — and this prints both side by side.

```
  generated_at 2026-09-19T00:29:05  (11.2h old)   !! STALE
  record_epoch 2026-08-06  — rows before this date are NOT in the public record
  cfb   by_sport settled     0  open    0  |  books W-L: likely 246, main 8
        also tracked, never staked: stale 210
        scope chip reads 504 (446 settled, 58 open)
  mlb   by_sport settled   743  open    2  |  books W-L: edge …, likely … (+9 push)
```

**What to look for, in order.**

* **`STALE`** — the page is rendering an old export. `export_json` runs
  after every settle, so a file hours old means the settle loop is not
  reaching it. That alone explains a missing league with nothing else
  wrong.
* **`the export is the gap, not the journal`** — the journal has graded
  rows into a rendered book and the file carries none of them.
* **`journal N W-L, file M`** — a partial export. Both numbers count
  WON AND LOST ONLY. A push is settled but not graded: `book_records`
  keeps it in its own `push` field and leaves it out of the ROI
  denominator, so it is printed beside the book as `(+N push)` rather
  than counted here. The two sides once counted differently and the
  check reported nine phantom missing MLB rows on 2026-09-19.
* **`record_epoch`** — rows dated before it are excluded from the public
  record by design. Rule this out before chasing anything else.
* **`also tracked, never staked`** — the quarantined books (stale-line
  flags, form and looser-gates samplers, long-shot watch, prediction
  desk). Since 2026-09-19 a sport's own Record scope draws these under
  that heading, so every bet the league placed is reachable. They are
  never in the P&L.
* **`scope chip reads N`** — what the chip beside that league on the
  Record page shows: every book, open and settled, voids excluded. It
  counted only the staked edge book until 2026-09-19, which is why
  college read 0 with a full page under it. A `!! no journaled key` line
  means the published file predates that fix.
* **`by_sport settled 0` beside a full book** is NORMAL for a league on
  probation. `by_sport` is the staked Edge book (`performance` filters
  `stake_units > 0`); a probation league is journaled and graded at a
  zero stake, so its record lives entirely in the other books. College
  football read exactly that all season. The page draws those books —
  since 2026-09-19 it stopped calling such a league empty.

---

## DATA. Is what we store earning its keep? (read-only, seconds)

Ethan, 2026-09-19: *"figure out what data we need to source and what we
can use to make all of our edge bets and all of our most likely bets
better. I know it's out there."*

Some of it is already here.

```bash
cd /srv/qellys && python3 homecheck.py data
```

Two halves. The first asks the DATABASE which of its tables any model
reads — `engine.datause` also keeps a hand-written list of twelve
signals, and a hand-written list can only answer for what somebody
remembered to register. The first run of the table audit found
`injury_events` written every night by the news tape and selected from
by **nothing**.

The second measures that store. For every injury filing, did the
player's own prop line move after we first saw it?

```
  ok     injury_events            in pipeline

  ARE WE AHEAD OF THE MARKET ON INJURY NEWS?
  nfl    1553 filings ·    0 with quotes either side ·    0 moved the line
        708 never quoted by any book · 0 quoted, but never within 24h
        the books do not price these men, or we spell them differently
```

That is the REAL first run, 2026-09-19, and it is a zero — which is why
the block above is the measured output and not an illustration. An
invented sample showing a healthy lead would have sat here next to a
check that returns nothing, and the next reader would have trusted the
wrong one.

The zero had a cause: the two stores spell a man differently.
`injury_events` keeps the news feed's display name, `odds_history` keeps
the books' menu run through `oddsapi.normalize_name` at parse time, so
the join was `A.J. Terrell Jr.` against `a j terrell` and matched 0 of
708. The lookup now normalises; the counts below the headline exist
because the first version printed only "0 with quotes either side",
which is equally true of a naming gap, a coverage gap and a timing gap.

**What the answer means, both ways.**

* **A POSITIVE median lead is an edge you can bet.** Minutes between our
  filing and the market's move, at a price still on the board. Injury
  news is mechanical rather than predictive — we do not have to
  out-forecast anyone, only be early — so a positive lead with a real
  sample is the most actionable number on this page.
* **A NEGATIVE lead means the market moved first.** Our feed is a
  newspaper, not a wire. No model fixes that; only a faster source,
  which is a purchase rather than a patch.
* **A high "never quoted"** is a coverage or naming gap, not a verdict
  on our speed. The books may not price these men at all, or the two
  stores may not spell them the same way — the failure this check hit on
  its first real run.
* **A high "quoted, but never within 24h"** is the more interesting one:
  the names are fine and we simply hold no price at the moment the news
  breaks. That says the edge is unRECORDED rather than unmeasurable, and
  recording is free — the prop prices are already in memory on every
  build, which is the argument `engine/lineledger.py` makes for the game
  lines it started storing.
* **`read by NOTHING`** in the table audit — a feed we pay for, a nightly
  that runs, and a column no model reads. The cheapest data to start
  using is the data already on disk. `injury_events` was the first one
  found, and reads `ok ... in pipeline` now only because this check reads
  it; that is a measurement, not yet a bet.
* Nothing in this check bets or writes. It is the information test from
  `docs/THE_INFORMATION_TEST.md` pointed at a store we already keep.

---

## EDGE. Does the book we stake actually make money? (read-only, seconds)

Ethan, 2026-09-19, after the stale book's promotion verdict came back
`hold` for every sport with three of the four measured NEGATIVE: the
question that decides what to build next is not why college has no edge
bets, it is whether the edge bets we DO place are worth placing.

```bash
cd /srv/qellys && python3 homecheck.py edge
```

```
EDGE — does the staked book make money, per sport
  category main+paper, stake above zero, since the record epoch
  mlb    412-331-9    743 settled  ROI  +2.14%  net  +15.9u on 743.0u  CLV +0.31
  nfl     14-12-0      26 settled  ROI  -4.40%  net   -1.1u on 26.0u  CLV n/a   !! 26 settled — too thin to call

  by grade — which selector earned it
    Sharp anchor  318-241   559 rows  ROI  +3.90%
    Play          108-102   210 rows  ROI  -1.20%

  stale-line book — the promotion ladder
    mlb   hold     2433 flags  hit 36.8% vs 37.9% break-even  z -1.10  ROI -1.81%
          hit rate 36.8% is -1.1 standard errors from the 37.9% break-even, needs +2.0
```

**What to look for.**

* **`too thin to call`** — under 100 settled. An ROI on 17 bets is a
  coin, not a result. The warning is there because the number looks
  like evidence and is not.
* **`by grade`** — the edge book is not one selector. A sharp-anchored
  card, a model card and (since 2026-09-19) a promoted stale flag all
  land in `main`. Pooling them hides which one is carrying the book, or
  sinking it. **This is the line that says where to spend the next
  week.**
* **the promotion ladder** — the stale-line book's progress toward
  becoming real edge bets, per sport, with the guard that is holding it.
  A sport reading `PROMOTE` starts staking on the next build.
* Numbers here are UNGATED, unlike the Record page's verdict, which is
  deliberately held below the ledger's sample bar. That is right for a
  public page and useless for deciding what to work on.

---

## SHELVES. Which markets should we stop staking? (read-only, seconds)

Ethan, 2026-09-21: *"what makes people the most money without losing the
most money alongside increasing and boosting our ROI record."*

**A flat stake cannot move ROI.** The only thing that raises the
percentage is taking fewer, better bets — so this is the table that
matters for the record, and `sizing` is the one that matters for the
money. The Edge book is the board with the most real money and the
least evidence behind it (`boards.EDGE_AUC` is 0.468, below a coin
flip), and until today it was the only staked board with no breaker.

```bash
cd /srv/qellys && python3 homecheck.py shelves
```

```
   sport market            n     ROI       z    verdict
   nfl   receptions      214   -18.40%   -3.91  stop <<< STOP
   mlb   total_bases     216    -4.10%   -2.11  review (watch)
   nfl   rec_yds         341   +10.40%   +2.44  run
   cfb   moneyline        41    +2.10%     —    run
```

**What to look for.**

* **`STOP`** — refused on the next build, through the same veto every
  board already consults. The pick is still priced and still shown; it
  stops being staked until the record turns.
* **`(watch)`** — past two standard errors on its own, but NOT once
  every shelf tested is counted. Sixty shelves at z −2 throws up more
  than one of these by chance every run, so a shelf here is one to look
  at, never one the record has convicted. The distinction is
  Benjamini-Hochberg, the same control the blind-spot miner runs under.
* **an em dash in the z column** — under 80 settled rows, never judged.
  `pass_td 2 bets −22.20%` is a real line from a 2026-09-16 run, and
  acting on it is the error this repo has made more than any other.
* **nothing stopped** is the expected reading most nights and is not a
  broken check. The bar is deliberately hard to clear in both
  directions: a false stop costs the edge on a shelf whose edge is
  indistinguishable from zero, which is approximately nothing, and
  failing to stop a losing shelf costs money every night.
* The decision is re-made every settle pass beside the blind-spot
  miner, so a shelf that crosses the bar tonight is refused tomorrow.

---

## SIZING. What should the likelihood board be staking? (read-only, seconds)

Ethan, 2026-09-21: *"we need to figure out what unit sizes and money
sizes makes the most sense and make the most money and highest roi on
the most likley bets."*

**A flat stake cannot change ROI.** Net units over units staked scale
together, so staking 2u a row instead of 0.25u on a board returning
+9.5% returns +9.5% on eight times the money — eight times the profit,
eight times the drawdown, the same number on the page. "Most money" and
"highest ROI" are two different requests and only the first is a sizing
question. The replay below prints the same percentage on every row on
purpose.

```bash
cd /srv/qellys && python3 homecheck.py sizing
```

```
  NFL  —  160 settled across 12 slates (paper rows included: same picks,
          and ROI does not care what they cost)
        hit 70.6% · ROI +9.50% · average payout 0.55 per unit
        NOW 0.25u  →  RECOMMENDED 0.62u
        measured +9.5% on 160 settled; one standard error below is +4.0%;
        full Kelly on that at an average 0.55 payout is 7.3% of bankroll; a
        quarter of it is 1.81u, divided by 2.9 bets riding at once (measured
        2.1, inflated for 12 slates) = 0.62u

        if it kept doing what it has done:
          size     net       ROI      worst run   one bad night
          0.25u    +3.80u   +9.50%     -2.47u        -7.5u
          0.62u    +9.42u   +9.50%     -6.13u       -18.6u
           1.0u   +15.20u   +9.50%     -9.87u       -30.0u
           2.0u   +30.40u   +9.50%    -19.75u       -60.0u
```

**What to look for.**

* **the ROI column never moves.** That is the answer to half the
  question, printed rather than argued. What moves the percentage is
  which rows get taken — `live_verdict` stopping a band that is not
  paying — not how much is on them.
* **`one bad night`** is the biggest slate this board has ever had,
  losing in full. A slate is bet all at once, so if the model is wrong
  in a correlated way that is the loss, and it is the one the ROI column
  cannot show you. Read it before reading the net column.
* **`N settled, 100 needed before the stake moves`** — the same bar the
  board's own verdict waits for. A stake says more than a verdict does,
  so it does not move on less.
* **`one standard error below is …`** — the stake is sized on what the
  record can prove, not on what it printed. A board that got lucky
  shrinks back on its own as the bound catches up, with nobody having to
  notice.
* **`the board is wide for this bankroll`** — even the minimum stake
  puts more than 12u on one night. That is a finding about the board's
  width, not about its edge.
* Nothing here writes. The stake it recommends is what
  `ledger.likely_stake_for` already uses on the next build.

---

## BENCH. What did benching a league do to the record it left? (read-only, seconds)

Ethan, 2026-09-21, the day WNBA came off the Record page: *"Are roi and
record should be better now that wnba is removed"* — and the honest
answer was that nobody had measured it. WNBA was benched because he
asked for it, not because it was shown to be losing. **If it was
winning, the bench cost the record rather than saved it, and nothing on
the page would ever say so.** This is the check that can.

```bash
cd /srv/qellys && python3 homecheck.py bench
```

```
BENCH — what the bench did to the record it left
  benched: wnba   (units only; benched dollars are zeroed by design)

  THE EDGE BOOK — the headline, with and without them
  now (benched out)          412 settled  210-198    +6.40u  ROI  +1.55%  (412.0u staked)
  with them back in          498 settled  244-251    -2.10u  ROI  -0.42%  (498.0u staked)
       → the bench made the headline ROI better by 1.97 points, on 86 fewer settled bets

  EACH BENCHED LEAGUE, ON ITS OWN
  wnba (edge)                 86 settled   34-53     -8.50u  ROI  -9.88%  (86.0u staked)
  wnba most likely           241 settled  120-121    -4.20u  ROI  -1.74%  (24.1u staked)

  EVERY LEAGUE, so a benched one is compared rather than assumed
  mlb                        743 settled  412-331   +15.90u  ROI  +2.14%  (743.0u staked)
  wnba (benched)              86 settled   34-53     -8.50u  ROI  -9.88%  (86.0u staked)
```

**What to look for.**

* **`IT IS WINNING`** — printed when the bench made the headline ROI
  WORSE. That is the finding this check exists for, because it is the
  one nothing else on the page can tell you. Emptying
  `ledger.BENCHED_SPORTS` puts the league straight back.
* **`N fewer settled bets`** — printed as loudly as the ROI, and it is
  the cost. A book that improved by shedding a third of its sample has
  a prettier number and a weaker claim. Read the two together or not at
  all.
* **`nothing has settled in either book yet`** — the bench has not
  bought or cost anything that can be measured. Not the same as
  "unchanged", and deliberately not printed as a 0.00.
* **units, never dollars.** Benching a row zeroes its `stake_dollars` —
  that is what takes the league off the money — so a benched league's
  dollar ROI has no denominator left. Units, wins, losses and P&L are
  untouched, and units are the honest measure of a book anyway.
* **the per-league table at the bottom** is there so a benched league
  is compared rather than assumed. −9.9% is a verdict beside mlb's
  +2.1% and a shrug on its own.

---

## GRADING. Is every league's book actually settling? (read-only, seconds)

Ethan, 2026-09-18: *"CFB still hasn't graded any edge bets or most likely
bets."*

```bash
cd /srv/qellys && python3 homecheck.py grading
```

**A bet that can never settle does not announce itself.**
`settle_from_history` says so in its own docstring — "bets whose games
haven't been ingested yet simply stay open" — and an open bet waiting on
Saturday's kickoff looks exactly like an open bet waiting on a results
feed that stopped landing in August. One resolves itself. The other
never will. Both read as a quiet book.

```
  cfb       0 settled  |     34 open
             31 stuck past the settle window — no results ingested
       !! CFB HAS NEVER GRADED A BET (34 open, 0 settled) — this is not a
          quiet week, it is a book that has never closed one
       !! 31 cfb bet(s) are waiting on results that were never stored —
          the ingest is the fix, not the settler
```

The reasons are `ledger.why_open`'s, the same ones `doctor.py --stuck`
prints. That check already existed and already knew; it just lived in a
command nobody runs daily. This puts it in the paste.

**FOUND AND FIXED 2026-09-18 — the college player-log ingest never ran
for the season being played.**

Ethan: *"It's been like that since week zero."* It was. Two compounding
faults in the nightly, both in `engine/maintenance`:

1. The one-time historical backfill is `[today.year - n for n in
   (4, 3, 2, 1)]` — 2022-2025 in 2026. **The season being played has
   never been in that list.** A box that ran it came away with four
   years of history and nothing from the year its board prices.
2. The only other path was `elif today.weekday() == 0` — Mondays, and
   unreachable at that, because the `elif` hangs off a floor (`have <
   5,000`) that counts EVERY season's rows. Five years of history
   satisfied a threshold that says nothing about whether this season
   landed.

The results half of the same nightly already refreshes the current
season with `[season] if in_season else []` — which is exactly why
`games` was current to the day while the player half was a month
behind. The player half now follows the same rule
(`maintenance.cfb_player_seasons`), and the file for a season still
being played gets a 12-hour cache instead of the seven-day one a
finished season deserves.

**Nothing needs backfilling by hand.** `fetch_season` pulls the whole
season file, so the first nightly after this deploys ingests all of 2026
to date in one pass — a dry run on 2026-09-18 parsed **12,179 rows
covering 08-29 through 09-06**, the exact games that were not grading —
and `settle_from_history` then grades the open college book on the next
build. Run `homecheck.py grading` the morning after to confirm `cfb`
shows settled rows.

**WHAT THE DEV BOX SHOWED, AND WHY IT WAS A LEAD RATHER THAN A FINDING.**
On the container this was written in, `data/history.db` holds, for the
2026 college season:

* `games` — **100 rows**, through 2026-09-07. Scores ARE being ingested.
* `player_game_logs` — **0 real rows.** The only 2026 entries are ten on
  08-23 that are plainly fixtures: `game_id` "401", and a player called
  "Opp Back" on CLEM.

If the droplet looks like that, then every college PLAYER-market bet —
props, TD long shots, Most Likely player rows, stale flags on player
markets — has nothing to grade against and never will, while game
markets (moneyline, spread, total) settle fine off `games`. That would
explain the exact split Ethan is seeing.

**This box is not the droplet and its history file may simply be a stale
copy.** Run the command before believing any of it. What is NOT
box-dependent, and is already fixed: nothing in the daily checks could
tell that story apart from an ordinary quiet week.

**The settler itself is correct and was checked first.** With no logs on
file, `_absent_player_verdict`'s college branch returns `None` — it
voids only when the team's box IS filed — so the bets stay open rather
than being graded zero. An ungraded bet is visible and honest; an
invented grade would be neither. Nothing needs undoing.

---

## LIVE. Does the Live tab have any bets to draw? (read-only, seconds)

Ethan, 2026-09-18, during Lions-Bills: *"we have a live nfl game right
now, and it's not showing any live edge or most likely bets in the live
tab. Instead, it's showing mlb bets."*

Two separate faults wear that one sentence, and only one of them is
visible from a browser.

The **showing mlb bets** half was the page: the Live tab had two league
selectors and the chips above the games only moved the games. Fixed —
a chip now switches the league outright, and every bets panel prints
the league it is speaking for, so the mismatch cannot come back silent.

The **not showing any** half is this check. It is not answerable from
the page, because an empty tracker and a quiet night draw the same
thing.

```bash
cd /srv/qellys && python3 homecheck.py live
```

**RAN 2026-09-18 — ALL THREE LEAGUES RECONCILE EXACTLY.** The NFL board
had 39 tracked rows with 5 live and 2 Pick of the Day rows while Ethan
was reading a list of baseball bets, which settles it: the bets were
there, the page was showing another league's. The output:

```
  nfl  board date 2026-W02     |  39 tracked (5 live, 31 likely) | 2 pick of the day
       journal: 101 open nfl bet(s) — 41 in the books the Live tab draws
         2026-W02     likely            31   shown  <- the board's date
         2026-W02     longshot           3   shown  <- the board's date
         2026-W02     main               5   shown  <- the board's date
         2026-W02     potd               2   shown  <- the board's date
         2026-W02     stale             59   measurement book, never on the tab
         2026-W01     stale              1   measurement book, never on the tab
       reconciles: 41 drawn (39 tracked + 2 pick of the day) vs 41 reachable
       note: 1 measurement row(s) still open under a past slate
```

**101 open against 39 tracked is not a 62-row hole.** 59 of those are
`stale`, the line-staleness shadow book, which is journaled at a zero
stake to be measured and has never been drawn on the Live tab.
`TRACKER_CATEGORIES` is main/longshot/likely plus the Pick of the Day on
its own key — so the number to compare is the `reconciles:` line, and it
is the check that does the arithmetic rather than you.

**What to look for.**

* **`reconciles:` disagrees** — shouted as `THESE DISAGREE`. Rows the
  tracker could reach and did not draw.
* **`invisible on the Live tab`** — rows in a book the tab draws, filed
  under a date that is NOT the board's. `open_bets_for` matches `date`
  exactly and football files a **week label** (`2026-W02`), not a day,
  so these never appear and never will.
* **`the tracker itself is not working`** — the rows are on the board's
  own date, in a book the tab draws, and nothing was tracked.
* **`measurement row(s) still open under a past slate`** — a settling
  gap, not a tracking one. The one NFL `stale` flag under `2026-W01` is
  the current example: nothing downstream will ever close it.
* **`live_picks_error`** — the build's tracker threw. The message is the
  build's own, written into the board so the page could show it.

`live` runs inside `homecheck.py all`, so the daily paste carries it.

---

## FILLER. Did the baseball filler price actually die? (read-only, seconds — but see the timing note)

Ethan, 2026-09-16, reading the MLB census: *"Eleven of the twelve game
rows carry an empty book field … Those eleven all show odds of exactly
-110, which is a filler number rather than a posted quote."* You were
right, and commit `59becc8` fixes it. This is the after-picture.

Run it **after the timer has pulled** — check `HEAD` in the output is
`59becc8` or later, or you are reading the before-picture again.

```bash
cd /srv/qellys && python3 homecheck.py filler
```

**CONFIRMED ZERO ON ALL THREE LEAGUES 2026-09-16 — #258 IS CLOSED**
(`mlb 5 rows | 2 no book | 0 filler`, `nfl 80 | 32 | 0`,
`cfb 3 | 0 | 0`). Both `59becc8` (totals) and `70ee99f` (team totals)
took. Keep running it after a pricing change; the 32 unbooked NFL rows
are a separate question and the check now says whether any of them is
being recommended.

**It used to be a thirty-line heredoc and Ethan could not paste it**
(2026-09-16: *"i couldnt get that last command to work"*), while the
five one-line blocks he ran the same evening all worked. The check is
now `homecheck.py`, which prints `HEAD` itself — so there is no
separate step to confirm you are reading the after-picture.

**What to look for.** The number that has to move is baseball's
`bet_type` mix. Before the fix MLB's filler rows were `total` and
`team_total`; after it, **`total` must be gone from every league's
filler count** — a total is now priced only when a book posted one.

`team_total` SHOULD ALSO BE GONE NOW. When Ethan first ran this on
2026-09-16 it still showed 32 such rows on the NFL and 2 on the MLB, and
this block said to expect them — that was #258, unfixed at the time.
He made the call the same day and commit 70ee99f took the filler out of
`price_team_total` as well, so a run against that commit or later should
show **zero at a filler price on all three leagues**. If `team_total`
still appears, the deploy has not landed; check HEAD.

If `total` still appears in MLB's filler count with `HEAD` at `59becc8`
or later, the fix did not take and I want the whole line.

---

## SHRINK. Does the market shrink help or hurt the top of the board? (#77) (read-only — but see the timing note)

The Most Likely page prints a touchdown row's probability **already
shrunk halfway toward the book** (`betting.MARKET_SHRINK = 0.5`). The
replay says the top of that board UNDERCLAIMS even after the fitted
temperature — top-1 claims 60.0% and lands 67.4% — so the shrink is
either closing exactly that gap or dragging good numbers toward a lazy
consensus. **Those read identically on the page**, and the headline
number the whole board is sorted by depends on which.

The measurement has existed since it shipped and ran **only from the
weekly maintenance pass, into a log** — so this could be asked once every
seven days, by waiting. There is a flag now:

```bash
cd /srv/qellys && python3 -m engine.tdbacktest --board
cd /srv/qellys && python3 -m engine.tdbook --shrink
```

Run `--board` first (the task says so) to confirm the replay reproduces
on the droplet, then `--shrink`. **Note the two different modules** —
`tdbacktest` grades the replay, `tdbook` joins it to harvested closes,
and the shrink question needs the prices.

The flag has worked since it shipped and was in no usage text, which is
most of why #77 sat open reading as though the measurement still had to
be built. It is listed now.

**What it prints:** three claims per top-of-board row — the corrected
MODEL, the SHRUNK number the page actually shows, and the de-vigged
MARKET — against what landed, at each depth, plus which claim the landed
rate sits nearest.

| if you see | it means |
|---|---|
| `nearest: shrunk` at most depths | `MARKET_SHRINK` is the right knob and **0.5 should be fitted, not assumed** |
| `nearest: model` | the shrink is dragging good numbers down — the page should show the model's number |
| `nearest: market` | our model adds nothing at the top and the book should be the display number |
| `noise` | the slate bootstrap could not separate them. **That is an answer, not a failure** — do not act on the point estimate |
| `shrink check: N priced slate(s) — needs 30` | the harvest is too young. Nothing to do but wait; the question stays open |

The second panel asks the ordering half separately: does ranking by the
shrunk number land more of the top k than ranking by the model alone?
Same rows, same slates, paired by slate.

**Paste both panels.** If it says anything but noise, this is a
one-constant change with a measurement behind it.

---

## TOP. Is there one pick for the day? (read-only, seconds — but see the timing note)

You asked for *"one pick for the pick of the day"* — singular. Until
today each league chose its own, so the MLB page and the NFL page each
claimed a different Pick of the Day. There is now a cross-league layer:
`potd.day_top_pick` runs the SAME ranking over every board and names
one, written once a cycle by the refresh loop.

```bash
cd /srv/qellys && python3 potd_report.py --top
```

That prints the board's answer beside the locked one. **When those two
lines differ it is not a bug** — it means a league has moved off the pick
it journaled this morning, and the locked line is what the site
publishes. The raw file is still there if you want it:

```bash
cat /srv/qellys/web/data/day_top_pick.json | python3 -m json.tool | head -30
```

**What good looks like:** `"sport"` names a league, `"pick"` is a card,
`"runners_up"` lists the league picks it beat, `"census"` says why any
league contributed nothing.

| if you see | it means |
|---|---|
| `"pick": null` with a census full of "has not rebuilt today" | the boards are stale — that is the cycle, not this |
| `"pick": null`, census empty | no league published a board at all |
| "nothing locked for today yet" | that league's pick was below its bar, so it was never journaled and cannot be published |
| "the board has changed its pick" | the league is showing something else now; the journaled one still stands |
| a `below_bar` on the pick | nothing cleared the bar anywhere; it is shown as a lean and is NOT on the record |

**One thing worth knowing about this tool.** Until 2026-09-15 it looked
for `nfl_picks.json` and `mlb_picks.json`, and neither exists — the NFL
writes `recommendations_picks.json` and MLB
`mlb_recommendations_picks.json`. So every run before that quietly
skipped your two priority leagues and said nothing about it. It reads the
launcher's own board registry now, and names any league it could not find
a board for.

On the site it draws as one line inside the Pick of the Day card — it
does **not** get its own block, because the picks already start right at
the fold on a phone and another card pushes them under it.

**It is a paid file.** Signed out, `data/day_top_pick.json` should come
back stripped; signed in, through `/api/board/`, whole. Worth one look
in a private window, since this is the headline pick.

---

## BOOKS. Did the seven new books actually show up? (read-only, seconds — but see the timing note)

Ethan, 2026-09-15: *"all the us books your using and shit, is that able
too be used for all sports if it makes sense and can save us api key
credits?"*

Seven books were added that day — BetRivers, Bally Bet, betPARX, Fliff,
Wind Creek, Novig, ProphetX — on the argument that the book list is a
filter on a response already paid for, so books are free. **A book key
that does not resolve on the live API is free in exactly the same way
and worth nothing**, and from the board the two look identical: the
price shown is the best of whoever answered.

This reads the payloads already on disk. No API credit, nothing written.

```bash
cd /srv/qellys && python3 book_margins.py --hours 24
```

**What I am looking for**, in the "asked for and never seen" line at the
bottom of each league:

| that line says | what it means |
|---|---|
| nothing at all | every book we ask for is answering — nothing to do |
| Novig, ProphetX | the two exchange-ish books never resolved; drop them or fix the keys |
| ten or more names | likely a stale cache rather than a book problem — check the "newest Nh old" figure in the heading first |

The margins above it are the other half. They should run roughly Novig
≈ 1.00, Pinnacle ≈ 1.03, the ordinary books ≈ 1.045. **A book sitting at
1.00 that is not an exchange is the interesting case** — either it is
one and I did not know, or its pair is being parsed wrong.

If a sport prints *"no book quoted both sides of any game"*, that is not
a book problem: it means no odds payload for that league is on disk at
all, which is the same question block PIN-2 asks from the other side.

---

## PIN. Does the Pinnacle tape exist? (read-only, seconds — but see the timing note)

Ethan, 2026-09-15, approving the sharp-anchor work: *"I say start on the
pinnacle money line closes if you think that's gonna make us more money
in the long-term."*

**The harvest may already be running.** `engine/lineledger.rows_for_games`
writes `book="Pinnacle"` moneyline, spread and total rows on every build,
and all three builds call `lineledger.record` — NFL (nfl_build.py:708,
:825), CFB (cfb_build.py:1636) and MLB (mlb_build.py:163). What I checked
before saying otherwise was the DEV copy on the container, which is not
this box. So this is a measurement, not a build task, and it decides
six weeks of work either way.

```bash
cd /srv/qellys && sqlite3 -header -column data/history.db "
SELECT sport, book, market, COUNT(*) rows,
       COUNT(DISTINCT event_id) games,
       MIN(substr(taken_at,1,10)) first_day,
       MAX(substr(taken_at,1,10)) last_day
FROM odds_history
GROUP BY sport, book, market
ORDER BY sport, book, market;"
```

**What each answer means, so the next step is decided before you paste:**

| what comes back | what it means | what happens next |
|---|---|---|
| `Pinnacle` + `moneyline` rows over several days | the harvest has been running all along | `backtest_sharp_anchor` is answerable NOW, not in six weeks — I run it the same night |
| only `book = best` | the sharp pair never reaches the games | a bug with an address, not a new feature — fixed in the parse, not the schema |
| almost nothing, any book | `lineledger.record` is failing silently | the `except Exception: return 0` hole (see below); the fix is already written |

If it is the third one, this second block says WHICH sport stopped and
when, which the first block cannot:

```bash
cd /srv/qellys && sqlite3 -header -column data/history.db "
SELECT substr(taken_at,1,10) day, sport, book, COUNT(*) rows
FROM odds_history
WHERE taken_at >= date('now','-14 days')
GROUP BY day, sport, book ORDER BY day DESC, sport;"
```

A day with a board but no rows is the silent failure caught in the act.

---

## PIN-2. What the Pick of the Day actually saw (read-only, seconds — but see the timing note)

The same trip, the second question. `potd_report.py` runs the selector
over the boards already on disk and prints what it saw, chose and
refused. It opens the JSON, never writes, never fetches a price — safe
mid-cycle.

```bash
cd /srv/qellys && python3 potd_report.py --dir web/data --rows 10
```

**Two lines in that output decide the next build.**

**The census.** A day with no pick names the gate that was binding. If
it reads "61 of 68 outside the even-money band", the band is the
constraint and `potd.MIN_PAYOUT` is the argument to have. If it reads
"40 with only our own model behind them", the sharp prices are not
arriving and that is a pull problem, not a selector one.

**The ladder line**, which is the one piece of work left on this feature
(docs/PICK_OF_THE_DAY.md §3d):

```
  Ladder      1 of 2 price-refused row(s) HAVE a rung inside the band,
              unreached today:
    Heavy Fav rush_yds at -400 → 34.5 at -115 (DraftKings)
```

A -400 read is unbettable at that price and perfectly bettable at 34.5.
Wiring that through means a new pricing path — what is the fair at an
alternate line, and is the sharp book quoting that rung two ways — so it
waits on this count rather than on a hunch. **Several rows a day with a
reachable rung makes it worth building. Zero saves the work.** Either
answer is worth the ten seconds.

If the line is absent entirely, this board carries no alternate ladder
at all, which is its own answer and points at the pull rather than the
selector.

---

## PIN-3. Two budget calls I made for you, and the one query that checks them

Ethan, 2026-09-15: *"I would like you too choose what you think is best.
I just don't want too drain my 100k api credits immediately."*

**The two levers price completely differently, and that decided it.**
The API bills per MARKET per region — `oddsbudget`'s header records the
4-8x overspend that burned 19k of a 20k plan in a day when the pacer
counted requests while the meter counted credits. The `bookmakers`
parameter is a **filter on a response already paid for**.

| lever | costs | call |
|---|---|---|
| more books | **nothing** | **taken** — BetRivers added |
| more sharp references | nothing to fetch, but it is a pricing claim | **declined** — `booksharp` measures it |
| earlier / extra pulls | **billed, and NFL's 12-market event call is the priciest thing we buy** | **declined** |

**Why the extra pull window was declined.** It is the only one that
touches your meter, and it would land hardest on Thu/Sun/Mon where the
NFL already owns the budget. The hypothesis behind it is real — our own
`backtest_sharp_anchor` docstring says *"soft books have mostly
converged to sharp ones by then; a live version gets to act earlier,
when gaps are wider"* — but it is a hypothesis, and **it can be tested
for free from tape we already keep**:

```bash
cd /srv/qellys && sqlite3 -header -column data/history.db "
SELECT substr(taken_at,12,2) AS hour_utc,
       COUNT(*) rows, COUNT(DISTINCT event_id) games,
       ROUND(AVG(ABS(over_odds)),1) avg_price
FROM odds_history
WHERE market='moneyline' AND taken_at >= date('now','-30 days')
GROUP BY hour_utc ORDER BY hour_utc;"
```

If the tape shows real spread between books early and convergence late,
the extra window is worth paying for and we size it against the NFL
days. If it shows nothing, we just saved the credits. **Either answer is
free; the pull is not.**

**Why no book was promoted to sharp.** The obvious fix for an MLB board
with no sharp witness was to name Circa or BookMaker sharp. `engine
/booksharp` exists to stop exactly that — *"received wisdom about which
book is sharp is the single most repeated claim in this industry and the
least often checked."* It measures lead time and accuracy against the
close from our own tape. Promotion waits on it.

**Check the book keys are real** (an unknown key is ignored by the API,
so a typo costs a missing book and says nothing):

```bash
cd /srv/qellys && python3 - <<'PY'
import json, glob
# data/built, NOT web/data. Ethan, 2026-09-16: this globbed the web copy
# and came back with an empty list for all five boards -- a confident
# zero read off the paywalled file, which is the exact blind spot the
# SHARP block warns about three sections earlier. Against the full
# copies the boards carry 13 books for the NFL and 9 for baseball, both
# exchanges included. Third instance of it in one day.
#
# A HEREDOC RATHER THAN python3 -c "...", because the prose above wants
# quotes and quotes inside a double-quoted -c argument end the argument.
for f in sorted(glob.glob('data/built/*_picks.json')):
    d = json.load(open(f))
    seen = set()
    for r in (d.get('recommendations') or []) + (d.get('most_likely') or []):
        if r.get('book'):
            seen.add(r['book'])
    print(f.split('/')[-1], sorted(seen))
PY
```

Seventeen keys are asked for now, up from ten. The new ones are
BetRivers, Bally Bet, betPARX, Fliff, Wind Creek — and **Novig and
ProphetX**, which are the two worth looking for. They are US-legal
peer-to-peer exchanges: nobody takes the other side as a house, so their
price carries no margin to strip. That is the same property that put
Kalshi at the TOP of the Pick of the Day's ladder above Pinnacle
(`engine/exchangefair`, docs/PICK_OF_THE_DAY.md §3). **If either name
appears in that output, tell me** — they should be feeding the exchange
tier rather than just the shop, and that is a change worth making.

Any name that never appears is a key the API does not recognise. It
costs a missing book and nothing else, and the fix is one word.

### The one-word change that would double your bill

Ethan asked whether the US book list could be shared across sports to
save credits. It already is — one `DEFAULT_BOOKS` serves every league —
and it saves nothing because books were never billed. **Regions are the
half that is.**

```
credits = markets x regions      (oddsapi._classify, read off the real URL)
```

We ask for **`regions: "us"` — one**, which is the cheapest setting
available and is also already shared across every sport.

**So the trap is this.** Some of the new books may live in the API's
`us2` region rather than `us`. If so they never appear, which costs
nothing — and the obvious next move is to add `us2` to go and get them.
That single word **doubles every call, for every sport, forever**: a
100k month becomes 200k. In a diff it looks exactly like adding a book,
which is free. This repo has already paid for confusing the two — the
pacer counted requests while the meter counted credits and burned 19k of
a 20k plan in a day.

`test_every_paid_call_asks_for_exactly_one_region` now fails that change
with the arithmetic in the message. If a missing book is worth a second
region, budget it first — do not let it in as a typo.

**Not added, and waiting on you:** the offshore reduced-juice books
(LowVig, BetOnline, Bovada). They would want a third category —
reference-but-not-a-ticket — because `odds.is_sharp_book` currently
carries BOTH "this is the sharp reference" and "never quote this as the
price to take" across sixteen call sites. That is a real refactor on a
pricing path, it is speculative until PIN-2 says whether MLB's problem
is book coverage or no pull at all, and it needs your answer to a
question I cannot settle from here: **would you bet at those books?** If
not, their price can still inform the fair — but it must never be the
ticket on the card.

---

## 1. The one thing that needs your hands (2 minutes)

A `git pull` does not install a systemd unit. The auto-updater restarts
the service; it does not re-copy the file. So the allocator setting that
landed today is sitting in the repo doing nothing until you run this.

What it is: glibc hands every thread its own malloc arena and never
reuses a freed block across arenas. `hashlib.scrypt` — the password hash
— asks for 16MB a call, so a burst of sign-ins used to leave one retained
16MB block per thread that ever hashed, and memory followed the number of
CALLERS rather than the number running at once. Measured here: 64
concurrent sign-ins peaked at 963MB against your `MemoryMax=1600M`. With
this set it is 219MB, and slightly faster.

```bash
cd /srv/qellys && git pull --ff-only
sudo cp deploy/qellys.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart qellys
```

Then confirm it actually took — this reads the live process's own
environment, so it cannot be fooled by an edit that did not get applied:

```bash
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value qellys)/environ \
  | grep -E '^(MALLOC_ARENA_MAX|TZ)='
```

Expected: `MALLOC_ARENA_MAX=2` and `TZ=America/New_York`. If MALLOC is
missing, the copy or the daemon-reload did not happen.

**ANCHORED, AND THAT IS NOT STYLE.** Until 2026-09-16 this read
`grep -E 'MALLOC|TZ'` over the whole environ, and Ethan caught what that
does: the two letters TZ appear inside a promo code, so the command
would have printed **every live discount code on the site** into a
terminal. `QB_PROMOS` lives in that same environment. Any filter over a
process environment gets anchored to the variable names it wants, or it
is a secret dump with a filter-shaped comment above it.

---

## 2. What the box is actually doing (read-only)

This is the block I most want back. I have been reasoning about a 2GB
droplet with a 1600M cap from what the unit file says; these say what is
true.

```bash
free -m
uptime
systemctl status qellys --no-pager | head -20
```

Whether the memory cap has ever been approached or hit — the dangerous
case is the kernel reclaiming rather than killing, which leaves no OOM
line at all, so both counts matter:

```bash
journalctl -u qellys --since "7 days ago" | grep -ci oom
journalctl -k --since "7 days ago" | grep -icE "out of memory|killed process"
systemctl show qellys -p MemoryCurrent -p MemoryPeak -p MemoryMax
```

`MemoryPeak` is the one to read: if it is anywhere near 1600M, the cap is
doing more than sitting there.

---

## 3. Are the four sign-ups actually working? (read-only)

Accounts, sessions, and whether anyone has saved anything. No emails or
verifiers are printed — counts and dates only.

```bash
cd /srv/qellys && python3 - <<'PY'
import sqlite3, time
c = sqlite3.connect("data/accounts.db")
c.row_factory = sqlite3.Row
n = lambda q: c.execute(q).fetchone()[0]
print("users            ", n("SELECT COUNT(*) FROM users"))
print("sessions live    ", n("SELECT COUNT(*) FROM sessions WHERE expires_at > %f" % time.time()))
print("sessions expired ", n("SELECT COUNT(*) FROM sessions WHERE expires_at <= %f" % time.time()))
print("saved sections   ", n("SELECT COUNT(*) FROM user_data"))
print("\nsign-ups by day:")
for r in c.execute("SELECT date(created_at,'unixepoch','localtime') d, COUNT(*) k"
                   " FROM users GROUP BY d ORDER BY d DESC LIMIT 10"):
    print("  %s  %d" % (r["d"], r["k"]))
print("\nlast seen (most recent 10, no addresses):")
for r in c.execute("SELECT id, datetime(last_seen,'unixepoch','localtime') s"
                   " FROM users ORDER BY last_seen DESC NULLS LAST LIMIT 10"):
    print("  user %-4s %s" % (r["id"], r["s"] or "never"))
PY
```

---

## 4. What the traffic looks like (read-only)

Caddy's log is the only place the real request pattern exists. Requests
per hour, the busiest paths, and whether anybody is being turned away.

```bash
sudo awk -F'"' '{print $0}' /var/log/caddy/qellys.log 2>/dev/null | tail -1 >/dev/null \
  && echo "log readable" || echo "log NOT readable — try with sudo -i"

# requests per hour today
sudo python3 - <<'PY'
import json, collections, glob, gzip, io
c = collections.Counter(); status = collections.Counter(); paths = collections.Counter()
# THE ROTATED ARCHIVES ARE NAMED WITH A DASH, not a suffix on .log —
# qellys-2026-09-15.log.gz, not qellys.log.1.gz. So `qellys.log*` matched
# the live file alone, the gzip branch below was dead code, and the
# readability check could never print its failure line. Ethan read all
# six files with a corrected glob on 2026-09-16.
for p in sorted(glob.glob("/var/log/caddy/qellys*.log*")):
    op = gzip.open if p.endswith(".gz") else open
    try:
        for line in op(p, "rt", errors="ignore"):
            try: e = json.loads(line)
            except Exception: continue
            ts = e.get("ts")
            if not ts: continue
            import datetime
            h = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:00")
            c[h] += 1
            status[e.get("status")] += 1
            paths[(e.get("request") or {}).get("uri","")[:60]] += 1
    except OSError:
        pass
print("requests per hour (last 12):")
for h, k in sorted(c.items())[-12:]:
    print("  %s  %5d" % (h, k))
print("\nstatus codes:", dict(status.most_common(8)))
print("\ntop paths:")
for p, k in paths.most_common(12):
    print("  %6d  %s" % (k, p))
PY
```

Two numbers I care about in that output:

* **`429`** — anybody hitting the rate limit. A real subscriber
  refreshing hard should never see one. If they do, `RATE_READ_PER_MIN`
  (server.py, currently 300/min per IP) is too tight for how the app
  actually polls, and I will raise it.
* **`503`** — the load shedder firing. Should be zero at this traffic.
  Anything above zero means `MAX_INFLIGHT` is binding and I want to know.

---

## 4b. The code box is gone from the two paying screens — check the third

Removed 2026-09-09 at your ask: the "Have a code?" box is off the PLANS
page and off the CHECKOUT page, which are the two you circled.

It is still on the ACCOUNT page, deliberately. That box never took a
Stripe discount code and never could — those go in Stripe's own field on
Stripe's page. It takes a COMP code, which writes free access here with
no card at all. If I had deleted all three, any code you have already
handed out would have stopped working with nothing to say so.

I could not verify the account page from here because it needs a signed-in
session. Two minutes on your phone, signed in:

1. Open the account page. There should still be a **Have a code?** box.
2. Type any nonsense and press Apply — it should say the code is not
   valid, not throw or go blank.
3. Plans page and checkout page: **no** code box anywhere. The FAQ entry
   "I have a code." now says to use the account page, and says plainly
   that a discount code for a paid plan is a different thing that goes in
   on Stripe's page.

If you would rather comp codes went away entirely, say so and I will take
the account box out too — it is one line. I did not do it unasked because
it is a working capability you did not mention, and losing it is the kind
of thing you find out about from a friend who cannot get in.

---

## 4c. Backups — the one where the downside is unrecoverable

Now that there is money and real accounts, this is the highest-stakes
thing on the box. The script itself is good (it uses SQLite's backup API
rather than `cp`, so a snapshot taken mid-write is still consistent), and
I fixed a real hole in its verifier today — see the commit. What it
cannot tell me from here is whether the nightly job is actually RUNNING
and whether the offsite copy exists.

```bash
cd /srv/qellys && ./deploy/backup.sh --check
```

Read three things in that output:

* **`ok: accounts (Nh old, ...)`** followed by a row count. It now prints
  what is IN the backup — `5 users`, and so on. Until today it printed
  "3 table(s)" and would have said `ok` for a backup holding NOTHING,
  which I demonstrated: five accounts live, zero in the backup, verdict
  ok. If you ever see **`EMPTY IN THE BACKUP`**, stop and tell me — that
  message means the last good copy is a countdown away from rotating out.
* **The age.** Over 48h and it says STALE, which means the 4am cron is
  not running.
* **`OFFSITE:`**. If it says `none`, every backup is on the same disk as
  the database, which survives a mistake but not a dead droplet.

If offsite is not set up, this proves a destination end to end before
trusting it:

```bash
cd /srv/qellys && QB_BACKUP_REMOTE=b2:qellys-backups/db ./deploy/backup.sh --test-remote
```

And the cron line, if `--check` says the backups are stale:

```bash
crontab -l | grep -c backup.sh    # 0 means it was never installed
```

`docs/BACKUPS.md` has the full setup including the Backblaze/S3 route.

---

## 5. Board health, same as always (read-only)

```bash
cd /srv/qellys && python3 -c "import launch; launch.show_boards()"
cd /srv/qellys && python3 launch.py --why-empty nfl | head -40
```

---

## 5b. Which numbers we compute and nobody ever sees (read-only)

You asked for *"every single piece of data we have"*. I checked every
file in `web/data/` has a reader — that part came back clean. Checking
every FIELD INSIDE those files is this, and it only works where real
data lives, because half the fields are null on my machine and a null
tells you nothing.

```bash
cd /srv/qellys && python3 -m engine.feedaudit
```

It prints every key the build publishes that no page names. Two kinds
land in that list and they look identical from the outside:

* something computed correctly every cycle that nobody can see — a
  feature that is silently off; or
* an internal the build needs and the front end was never meant to read,
  which is fine.

Read the marks, not just the names:

* **no mark** — the field is carrying real values on the box and no page
  shows them. This is the short list and the interesting one.
* **`[always empty]`** — nobody reads it AND it is empty in the file. On
  the droplet that is a stronger signal than on my machine, but still
  check before deleting anything.
* **`internal — <reason>`** — already classified, only shown with
  `--all`. If a name in the report should be here instead, tell me the
  name and I will write the reason down beside it.

It never exits nonzero and it touches nothing. One feed at a time if the
list is long:

```bash
cd /srv/qellys && python3 -m engine.feedaudit record.json
```

Paste me the output and I will turn each line into either a fix or a
sentence in the allow-list. On my box the names carrying real values
were `starting_bankroll`, `clv_coverage`, `curve_from`, `predmarket`,
`staked_d` and `tax_by_book` — I expect that list to look different
where the real numbers are.

---

## 6. If the site ever feels slow while you are on it

Run this WHILE it feels slow, not after — it is a snapshot:

```bash
systemctl show qellys -p MemoryCurrent -p TasksCurrent
uptime
ps -o pid,rss,pcpu,etime,cmd -p $(systemctl show -p MainPID --value qellys)
sudo tail -50 /var/log/caddy/qellys.log | python3 -c "
import sys, json
for l in sys.stdin:
    try: e = json.loads(l)
    except Exception: continue
    print('%6.0fms  %3s  %s' % (1000*e.get('duration',0), e.get('status'),
          (e.get('request') or {}).get('uri','')[:70]))
"
```

The last one prints how long each recent request actually took. Anything
over ~200ms on an `/api/` path is worth me seeing.

## G1 + C1: done 2026-10-04

G1 (red-zone and third-down backfill, CIN–JAX tape) ran: JAX's offence against CIN's defence matched the research's model; the CIN run game against JAX's run defence did not; red-zone ranks read softer because this season is only a third of the blend.

C1 (corner rules, engine.cbfit): neither proven. H1 (WR1 keeps catches better than yards against an elite corner) +0.020 overall; halves +0.046 (n 405) and −0.026 (n 211). H2 (WR2 catches more) −0.026 overall; halves −0.032 (n 403) and +0.001 (n 203).

The blocks as they were:

#### Red zone + third downs, and our Bengals–Jaguars card (2026-10-04, later)

**G1. Fill the new red-zone and third-down numbers** for last season and
this one (otherwise they arrive with Tuesday's weekly refresh). A few
minutes; read-only for everything else:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.gamescan backfill 2025 2026
cd /srv/qellys && sudo -u qellys python3 -m engine.gamescan show 2026 4 CIN JAX
```

**C1. Test the breakdowns' two corner rules on five seasons** (paste it
back). H1: a WR1 against a shutdown corner keeps his catches better than
his yards. H2: the WR2 catches more when his team faces one. Each must
hold in both halves of the seasons on 100+ games a half, or it is left
alone. Nothing it finds moves a number:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.cbfit
```

## T1 + T2 + G2 + S0 + R1 (round 7) + NHL H1–H13/H15: done 2026-10-04

T1 (engine.tdinjfit, 2021–2024, on top of the touchdown model): none proven.
- SECONDARY (opponent starting DBs out → receivers): 2,522 of 11,026 flagged; scored ÷ model 1.327 flagged vs 1.345 rest; b 0.014, clustered t 0.3; better 0/4 seasons.
- FRONT (opponent starting linemen out → backs): 582 of 4,622; 1.243 vs 1.243; t 0.12; better 0/4.
- CATCHERS (a starting WR/TE out → teammates): 2,640 of 15,648; 1.374 vs 1.29; b 0.054, t 1.28; better 3/4; held-out gain +0.000026. A hint (+6%), same direction as engine/matefit; below the bar. Stays shown, not priced.

T2/G2 printed nothing: the 1 PM games had started and left the board. Read from the journal instead (week 4 TD board: Brown 53.8% at −145, Chase 47.3% at +100, Tuten 44.5% at +105, P. Washington 40.5% at +165, McCaffrey 60.8% at −170, Kittle 34.3% at +150, Dobbins 31.9% at +120, Sutton 28.6% at +233, Harvey 28.1% at +225).

Box: disk 45%, one nightly backup plus the Sunday check, settle took 936 s (ceiling raised 20 → 45 min).

The blocks as they were:

#### Touchdown picks: the injury test, and our scorers next to your four TD scans (2026-10-04, latest)

**T1. Test your TD scans' injury moves on four seasons** (paste it back).
Three claims, each on top of our touchdown model: opponent starting DBs out
→ his receivers score more (Cook and Dugger out → Washington); opponent
starting linemen out → his backs score more (Bosa out → McCaffrey); a
starting WR or TE out → his teammates score more (Evans out → Kittle).
Each must beat the model on held-out seasons, hold in all but one, and
clear a clustered t of 2 on 300+ flagged games, or it is left alone.
Nothing it finds moves a number. About 10–20 minutes:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.tdinjfit
```

**T2. Every scorer we price in Bengals–Jaguars and Broncos–49ers**, to line
up against the four TD scans (paste it back):

```
cd /srv/qellys && python3 -c "
import json
d = json.load(open('web/data/recommendations.json'))
games = ({'CIN','JAX'}, {'DEN','SF'})
rows = [r for r in d.get('td_field') or [] if any({r.get('team'), r.get('opponent')} <= g for g in games)]
for r in sorted(rows, key=lambda r: (r.get('team') or '', -(r.get('model_prob') or 0))):
    print(f\"{str(r.get('team')):4} {(r.get('player') or ''):22} {round(100*(r.get('model_prob') or 0)):3}%  {str(r.get('odds')):6} {r.get('book') or '':11} rz/wk {r.get('rz_chances')}  {r.get('goal_line_text') or ''}\")
"
```

**G2. Our picks for Bengals–Jaguars**, to line up against your two
research cards (paste it back):

```
cd /srv/qellys && python3 -c "
import json
d = json.load(open('web/data/recommendations.json'))
rows = [r for r in (d.get('most_likely') or []) + (d.get('recommendations') or []) if {r.get('team'), r.get('opponent')} & {'CIN','JAX'}]
seen = set()
for r in sorted(rows, key=lambda r: -(r.get('model_prob') or r.get('hit_prob') or 0)):
    k = (r.get('player'), r.get('market'), r.get('side'), r.get('line'))
    if k in seen: continue
    seen.add(k)
    print(f\"{(r.get('player') or r.get('pick_label') or ''):22} {str(r.get('market')):12} {str(r.get('side')):6} {str(r.get('line')):6} chance {round(100*(r.get('model_prob') or r.get('hit_prob') or 0))}%  proj {r.get('projection')}  {r.get('category') or r.get('board') or ''}\")
"
```


#### The overnight stall — what happened, and one check (2026-10-04)

At about 12:26 AM every board stopped rebuilding (your 4:26 AM status
screenshots). That was the first loop cycle of the new day, the one that
runs the daily chores, and the chores ran INSIDE the board loop, so one
chore that would not come back stopped every board and every settle. The
fix is already on the box once it updates (it restarts itself, rebuilds
every board first, then carries on):
- the chores now run in their OWN PROCESSES, in two lanes (the daily pass,
  and settling), at the same low priority as the builds. (The first fix put
  them on threads of the server's process; you reported the site still
  stale an hour later. A thread shares the server's CPU priority and memory
  and can never be stopped, so a busy chore still starved every build.) A
  lane past its limit (daily 60 min, settle 20) is killed, its stack goes
  to the log, and it rests two hours before it runs again;
- the status page has two new rows under "Code running": **Refresh loop**
  (when the board loop last finished a cycle) and **Daily chores** /
  **Settling** (which step each is on; if one is stuck, the exact line);
- a watchdog restarts the board loop if no board step finishes for 90
  minutes, writing every thread's stack to the log first;
- the overnight NHL catch-up stops after 20 minutes and resumes the next
  night (its first run, last night, walked up to 45 days of preseason);
- a code update now waits for the board build in progress before it
  restarts, instead of abandoning it.

**S0. When you're home, paste this** (read-only). It shows which chore
was stuck last night, from the box's own log:

```
journalctl -u qellys --since "2026-10-04 00:00" --no-pager | grep -iE "chore|stuck at|watchdog|nhl results|nhl xG|daily maintenance|auto-update|startup build" | tail -40
python3 -c "import json; print(json.dumps(json.load(open('/srv/qellys/web/data/heartbeat.json')).get('chores'), indent=1))"
```


#### NFL Most Likely + touchdowns — run these now (2026-10-04, round 7)

Two things in this round:
- **The touchdown model.** The record hints a scorer's chance does not
  follow his team's expected points hard enough (teams at 18-22 went
  1-for-12 on our TD picks at a claimed 43%; teams at 26+ went 13-for-21
  at 49%). This replays the real TD model over every stored season and
  fits, per position, how much harder or softer a scorer's chance should
  follow his team's implied total. It is adopted only if it beats today's
  model on held-out seasons.
- **2026 counts now.** The history fits needed a player to have 4-5
  earlier games in the SAME season, so with four 2026 weeks played almost
  no 2026 game counted. They now reach back into last season for his
  recent form, the way the live model does in the first weeks, so 2026
  counts from week 2. (The TD replay already counted 2026 from week 4.)
  The record-based corrections were always 100% 2026.

First make sure the box has the new code. This should print a line saying
"2026 counts in the history fits", or anything newer:

```
git -C /srv/qellys log --oneline -1
```

**R1. Re-run every fit with 2026 in it** (paste all of it; ten minutes or
so). `nice -n 19` runs them at the lowest priority, so the site stays
quick while they work. All of these also run by themselves every Wednesday, in this order:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.scouthist
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.posspread
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.tdscale
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.tdbacktest --fit
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.boardlearn
```

To undo any one: remove its file under /srv/qellys/data/models/ —
`td_implied.json` (touchdown team-total step), `position_spread.json`
(widths), `likely_calibration.json` (record), `scout_history.json`
(history). Each comes back by itself if it is still proven.


#### NHL — load three seasons, then it runs itself (2026-10-03)

The code is on the box once the auto-updater pulls it. The NHL board builds
in the launcher's cycle from today, but it has no players until history
lands. Every NHL Edge pick goes on **paper** until its record earns money.

**H1. Disk, then a probe** (paste). The probe fetches one day, one box
score and one player from the NHL's own free feed, which this sandbox
cannot reach:

```
df -h / | tail -1
cd /srv/qellys && sudo -u qellys python3 ingest.py nhl --probe
```

**H2. Load 2023-24, 2024-25 and 2025-26** (an hour or more, in the
background; it is safe to stop and rerun, finished days are skipped):

```
cd /srv/qellys && sudo -u qellys nohup python3 ingest.py nhl --seasons 2023-2025 > /tmp/nhl_ingest.log 2>&1 &
tail -3 /tmp/nhl_ingest.log
```

**H3. When H2 ends: open the Most Likely shelves** (paste). Each hockey
market goes on the Most Likely board only if it ranks on its own walk
(the same 2,000-pair, 0.60 bar as every sport). The nightly job does this
too; this just does it now:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, rankfit; rankfit.measure(db.connect(), 'nhl')"
```

**H4. Build tonight's board once by hand** (paste the last line):

```
cd /srv/qellys && sudo -u qellys python3 nhl_build.py --odds
```

**H5. Headshots, now** (paste the last line). Every club's current roster
fills the faces and moves traded players; the nightly job repeats it from
September to June:

```
cd /srv/qellys && sudo -u qellys python3 ingest.py nhl --faces
```

**H6. Re-rank after Scalpy NHL 1.0** (paste). Goals are now shots times a
regressed shooting rate and the opposing starter tilts goals and points,
so each market earns its shelf again on its own walk:

```
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, rankfit; rankfit.measure(db.connect(), 'nhl')"
```

**H7. One build from the saved odds** (paste the Odds line and the last
line). Shows the odds result, the scan's reads and how many rows each
Scalpy rule passed, without journaling anything:

```
cd /srv/qellys && sudo -u qellys python3 nhl_build.py --cached-odds --no-journal
```

That build now prints a second line, Scalpy NHL — Edge Hunter 1.0's census
(how many Elite / Strong / Small edges and passes, and the commonest pass
reasons). Paste it: it is how we will tune the Edge bar on real prices.

**H8. Live rosters and standings, now** (paste the four lines). The NHL's
own rosters and standings, and ESPN's NBA/WNBA rosters, for the team pages;
the launcher's cycle repeats both:

```
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport nhl
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport nba
cd /srv/qellys && sudo -u qellys python3 rosters_build.py --sport wnba
cd /srv/qellys && sudo -u qellys python3 standings_build.py --sport nhl
```

Each roster line should say `from league` (NHL) or `from roster`
(basketball). `from appearances` means the feed failed, and the line says
why.

**H9. Install the new Caddyfile** (paste the last line). The page itself
is now served without its comments (29 KB -> 11 KB gzipped on every first
visit); the updater builds the trimmed copy, but Caddy only serves it once
its config is reloaded. Validates first — a bad file is never installed:

```
cd /srv/qellys && sudo caddy validate --config deploy/Caddyfile --adapter caddyfile && sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy && ls -la web/min/index.html
```

**H10. Every NHL logo resolves** (paste the summary line). The site now
draws ESPN's NHL logos everywhere a team mark appears; this fetches all 32
and names any club whose spelling misses (that club shows its coloured
badge until the map is corrected):

```
cd /srv/qellys && sudo -u qellys python3 assets.py --audit --sport nhl
```

**H11. Shot quality, power-play time, starting goalies: what reads?**
(paste the play-by-play, power-play ice time and starting goalies lines).
The starting-goalies line asks ESPN's scoreboard for today's announced
starters. On a morning before any team has announced, it lists what a side
carries instead, which tells me the field's name. The probe now opens one
game's play-by-play and reports its attempts, goals, named shooters and the
first shot's type and distance. It also asks the league's stats host for
power-play ice time. If that line says ok, I can wire minutes on the power
play. Until then, PP1/PP2 is read from who scores and shoots on it:

```
cd /srv/qellys && sudo -u qellys python3 ingest.py nhl --probe
```

**H12. Load every NHL shot, then fit our expected-goals model** (paste the
last three lines). About 4,200 games from the league's free play-by-play.
It is safe to stop and rerun, because a stored game is skipped. It runs in
the background, so closing the terminal does not stop it. Nothing else
calls the NHL host while it runs, and no odds credits are used:

```
cd /srv/qellys && sudo -u qellys nohup python3 ingest.py nhl --shots > /tmp/nhl_shots.log 2>&1 &
tail -f /tmp/nhl_shots.log
```

Ctrl-C stops the `tail`, not the load. When it finishes, the log names the
attempts and the league rate. From then on the nightly job stores each
final's shots and refits.

**H13. The board reads shot quality** (paste the "Shot quality" line and
the last line). This is one build from the saved odds, so no credits are
used and nothing is journaled. It should say `Shot quality: on`:

```
cd /srv/qellys && sudo -u qellys python3 nhl_build.py --cached-odds --no-journal
```

**H15. NHL futures, lines and live, once** (paste each last line). The
probe in H11 now also prints a `shift charts` line: if it says ok, the
board reads every team's lines from it. The first command projects the
season for free. The second adds the Stanley Cup price, at one credit a
week (the cache holds it seven days). Live scores, win probability and the
live line run by themselves. Hockey's live line is never pulled while an
NFL or college game is live:

```
cd /srv/qellys && sudo -u qellys python3 futures_build.py nhl
cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep ^ODDS_API_KEY | xargs) python3 futures_build.py nhl --odds
cd /srv/qellys && sudo -u qellys python3 livescore_build.py --league nhl
```

The `--odds` line reads the one key it needs from `/etc/qellys/env`, the
same way the JuiceReel check does. A plain hand run has no key (the box
printed "prices: OddsAPIError: No Odds API key", 2026-10-03).

**H14. Later — once NHL picks have graded for a couple of weeks.** This
makes the NHL Most Likely chances honest from their own record. It is the
same fit as M1 and saves only if it scores better on games it never
learned from. It needs 40 settled picks in a group before it touches that
group:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.likelycal fit --sport nhl
```

