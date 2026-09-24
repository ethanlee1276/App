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

**D. Wednesday, Sep 30**, after the first playoff games: step 8b's
grading line again.

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

Pick something long and random (`openssl rand -hex 24` is fine). Without
it every import answers 503 — closed, not open.

**2. Import an export.** Two ways; the first needs no SSH at all.

From your laptop, with the file next to you:

```bash
export QB_OWNER_TOKEN='paste-the-token-here'
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
