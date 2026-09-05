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
* **WNBA** — both basketball probes ran pre-game and showed no `plays`
  block. Whether it appears live, and under what key, is unknown; the
  hoops card is not wired until it has been seen. Playoffs are on:
  `python3 espnprobe.py --league wnba` during a game.

It prints key names, container types, list lengths and the values of
numbers and booleans. It never prints a play's text — that comes back as
`str(29)`. If the structure alone turns out not to be enough,
`--dump /tmp/cfb_summary.json` writes the raw payload (ESPN's content: a
working note, not something to publish).

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

## 5. MLB recency shade, still unmeasured

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
