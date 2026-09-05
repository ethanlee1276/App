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

**Blocks:** task #135. Two candidate causes were fixed blind
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

Expected: `hitData` with `launchSpeed`, `launchAngle`, `totalDistance`,
`trajectory`, `coordinates{coordX, coordY}`; `about` with `startTime`
and `endTime`; the event with `startTime`/`endTime` and `count{balls,
strikes, outs}`. Anything different is a name to fix in
`engine/mlb/sources/pbp.py` (`_hit`, `_when`, `game_events`) — the
readers are tolerant, so a wrong name shows as an arc that never draws
rather than a crash.

---

## 3. MLB says 20 recommended bets and draws 2

**Blocks:** task #139. Two filter chains sit one above the other on the
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
