# Run these when you're home

Ethan, 2026-09-09, from work: *"please save all the code you need me too
run for when I'm home."*

Short list, in order. Everything is copy-paste. **Block 1 is the only one
that changes anything** — the rest are read-only and just tell me what
the box is actually doing, which is the half I cannot see from here.

Paste the output back with the block number and I can carry on.

The long history of one-off checks lives in `DROPLET_CHECKS.md`; this
file is only what is outstanding right now, and lines get deleted from it
as they are done.

---

## SHARP. Did the MLB board get its sharp witnesses back? (read-only, 10 seconds)

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

## KX. Why the NFL exchange tier is dead (read-only, 10 seconds)

Your 2026-09-16 run said: nine NFL rows, 58 usable Kalshi markets, zero
matched. The report called that *"OUR name matching"* — **and it could
not actually know that.** `NO_MATCH` was one bucket covering three
different failures with three different fixes: our spelling of a club
differs from the exchange's, the board is a day stale so no market names
tonight's games, or the game matched and we could not resolve which side
the YES pays on.

I could not tell them apart from here, and guessing at a matcher change
risks breaking MLB, which works. So the census now names the step, and
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

## GATE. Which refusal is costing money (#164) (read-only, ~2 minutes)

The open question was *"whether any ordering would have ADMITTED bets the
edge gate refused"*, and the first run said the admitted slice ran 11.5%
WORSE than what it refused — on proxy-priced rows, interval
[-31.5%, +8.0%], straddling zero. Not a finding. It needs a book-priced
arm, which needs this box's harvest:

```bash
cd /srv/qellys && python3 backtest.py --weeks 6-17 --gate --real-lines --gate-basis book
```

**New in this run:** a gate that costs money is not one fact, because it
is not one rule. Under the arms table there is now a split by WHICH bar
refused each row:

```
  What each refusal turned down, flat 1u, best first:
      240 rows  ROI   +11.4%   +27.30u  Model disagrees with the market by more…
       90 rows  ROI    -8.2%    -7.40u  This market's calibration fit hit the edge…
```

A **positive** line is a bar the gate was wrong to apply — that is the
one to change. Read the caveat it prints: these are many small slices of
one sample and the smallest always looks the most extreme.

**If it says `no refusal reasons recorded`,** the walk-forward ran before
`SettledProp.refusal` shipped — pull and re-run, the field is filled at
settle time.

**Paste the arms table and the split.** If the book-priced arm reproduces
the negative point estimate, the split names the line to change and I can
prereg a test for it.

---

## ALT. Should we buy alternate spreads and totals? (#253) (read-only, 10 seconds)

Already in the report you are running for block KX — no extra command.
Look for the `Alternate lines` block:

```bash
cd /srv/qellys && python3 potd_report.py --all | grep -A8 "Alternate lines"
```

**The purchase decision is in the market split.** Spreads and totals have
a ladder of alternate numbers; **a moneyline does not** — there is one
number and it is the price.

| if the block says | it means |
|---|---|
| `VERDICT: every price refusal is in a market with no alternate line to buy` | **DO NOT BUY.** The credits would buy nothing. |
| `VERDICT: nothing was refused on price today` | nothing to address today — run it over a week before concluding |
| `N of the M clear every OTHER bar` | that N is the number to watch over a fortnight. If it is 0-1 a day, the purchase is not worth it |

It deliberately does NOT tell you an alternate line would have cleared —
an alternate is a different bet, not the same bet at a better number, and
guessing that is the thing the purchase exists to find out.

---

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
from engine import db, ledger
conn = db.connect()
try:
    print(ledger.repair_inverted_likely_sides(conn))
finally:
    conn.close()
"
```

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

## TOP. Is there one pick for the day? (read-only, 5 seconds)

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

## BOOKS. Did the seven new books actually show up? (read-only, 5 seconds)

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

## PIN. Does the Pinnacle tape exist? (read-only, 10 seconds)

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

## PIN-2. What the Pick of the Day actually saw (read-only, 10 seconds)

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
cd /srv/qellys && python3 -c "
import json,glob
for f in sorted(glob.glob('web/data/*_picks.json')):
    d=json.load(open(f)); seen=set()
    for r in (d.get('recommendations') or [])+(d.get('most_likely') or []):
        if r.get('book'): seen.add(r['book'])
    print(f.split('/')[-1], sorted(seen))"
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

## 0. THE SITE IS DOWN — run this first, before anything else

Ethan, 2026-09-09, with a photo: *"the site crashed. It won't load
anything and won't show logos."*

**What that screenshot actually says.** The page frame, the buttons and
the nav all drew — that is the service worker serving the shell it
cached. `/data/` and `/api/` are the only things it NEVER caches, on
purpose, because a stale board is worse than an honest error. So "10
boards failed to load" plus a working-looking page means one thing: **the
app is not answering, and the browser is showing you a photograph of it.**
The missing logos are the same fact — images are not cached either.

**Bring it back first, ask why second.** The journal keeps the history, so
restarting costs you no evidence:

```bash
sudo systemctl restart qellys && sleep 3 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/data/recommendations.json
```

`200` means it is back. Anything else, keep going.

**Then paste me all of this at once** — it answers every likely cause in
one go, and I cannot see any of it from here:

```bash
echo "=== service ==="; systemctl status qellys --no-pager -l | head -15
echo "=== restarts ==="; systemctl show qellys -p NRestarts -p MemoryPeak -p MemoryCurrent
echo "=== last 40 log lines ==="; journalctl -u qellys -n 40 --no-pager
echo "=== was it OOM-killed? ==="; sudo dmesg -T 2>/dev/null | grep -iE "killed process|out of memory" | tail -5
echo "=== disk ==="; df -h /srv /var | sed 1d
echo "=== memory ==="; free -m
echo "=== are the board files even there ==="; ls -la /srv/qellys/web/data/*.json 2>/dev/null | head -5
echo "=== how old are they ==="; date; find /srv/qellys/web/data -name '*.json' -newermt '-2 hours' | wc -l
echo "=== which commit is deployed ==="; cd /srv/qellys && git log --oneline -3
```

**The three things it can be, and what each looks like:**

* **Out of memory.** `NRestarts` climbing, `dmesg` naming a killed
  process. This box is 2GB with `MemoryMax=1600M` and it has done this
  before (2026-09-02, the in-process Wednesday refit). Restarting works
  and it comes back.
* **Out of disk.** `df` at 100%. The builds write and the app cannot.
  Clear the cache directory, not the data: the boards are the product.
* **A bad deploy.** The auto-updater pulls every five minutes, so a
  commit that will not import takes the service down within five minutes
  of being pushed. `journalctl` shows a traceback on startup rather than
  a request. If that is what it is:

```bash
cd /srv/qellys && git log --oneline -5          # find the last one that worked
sudo systemctl stop qellys-update.timer         # stop the updater re-pulling it
cd /srv/qellys && git checkout <that-commit> && sudo systemctl restart qellys
```

Tell me the commit and I will fix forward; do not leave the updater off
longer than that, or the boards stop rebuilding.

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
  | grep -E 'MALLOC|TZ'
```

Expected: `MALLOC_ARENA_MAX=2` and `TZ=America/New_York`. If MALLOC is
missing, the copy or the daemon-reload did not happen.

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
for p in sorted(glob.glob("/var/log/caddy/qellys.log*")):
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
