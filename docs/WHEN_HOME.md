# When you get home — the laptop checklist

Written 2026-08-07, revised 2026-08-13. Everything here needs the Mac,
because the container has no ledger, no route to the sports APIs, and no
browser you can look at.

**Push state: nothing outstanding.** Everything discussed is on
`claude/sports-betting-app-vhgmho`.

---

## TODAY'S ROUND — 2026-08-18 (added while you were at work)

Thirty-six commits today, GitHub tick green, 4,706 tests across 275
files (sanity check after T1’s pull: `git log --oneline -1` should name
the commit that refreshed this very note). In the order to run them:

### T1. Deploy — DROPLET, not laptop (engine files changed, ~1 min)

```
cd /srv/qellys && ./deploy/deploy.sh --no-tests
```

Then close and reopen the app once on the phone. What lands: the
knowledge-tier fix (your preflight's 16 unregistered "Low barrel rate"
openings), the NBA Players empty-state fix (the 20-character page), CFB
on the Live tab with the win-probability chart (it was invisible there —
wrong payload shape, found while wiring the chart; Week 0 is Saturday),
and the sim-joint evidence journal, which starts recording on the next
MLB build.

### T2. Settle the stuck days — laptop, ~1 min

```
python3 launch.py --settle all
```

Your own preflight flagged it: 7 finished days still holding open
predmarket picks (projected lineups that sat). The pass VOIDS them, same
as the book would.

### T3. Player faces — laptop, one season re-read per league

```
python3 ingest.py mlb
python3 ingest.py nfl
python3 ingest.py nba --seasons 2025-2026
```

Photos are captured DURING ingest, so the cards show initials until
these run. WNBA already has its 171 faces — these three bring MLB, NFL
and NBA level with it.

### T4. The game-sim verdict — laptop, ~10 min, read-only

```
python3 simrecon.py
```

Full write-up in §6 below ("the game-sim verdict"). Paste me the verdict
block — the adjacency split is the line I most want to see.

### T5. Still carrying from before, unchanged

- **Which key is `5dc51e48` (#76)** — ten seconds, §7 below. Open
  `secrets.local`, see which line it is on; only the live key needs
  regenerating, at your leisure.
- **Venue art (#120)** — `docs/VENUE_PROMPTS.md` when you feel like
  making pictures; fifteen colour renders wanted.

### T6. Appended later the same day — two features, same T1 deploy

Both land with the T1 command (deploy.sh restarts the service, which
the search needs — server.py grew two endpoints):

* **League-wide player search.** The Players page now looks up ANY
  player in the sport — everyone in the ingested game logs, not just
  tonight's board — and draws the same multi-market profile card a
  priced star gets. Try someone obscure after deploying; the roster
  stub-card fallback only appears if the API is unreachable.
* **Mock draft simulator.** Fantasy → Mock draft: snake order, pick
  your league size and slot, CPUs draft best-value-with-noise off the
  kit's own board, and the finish is your starters' projected PPG
  against the room — arithmetic, not a letter grade.

### T7. Headshots everywhere — code done, T3 is the other half

Every surface that names a player now passes the stored face through:
the draft kit and mock draft, the rankings table, camp risers/fallers,
the league-wide search results, and the searched-up profiles. But your
own preflight says the photos are only STORED for WNBA — MLB, NFL and
NBA show initials until the T3 ingests run. After T3 + the T1 deploy,
if any spot still shows initials where a photo should be, tell me the
page — that would be a real gap, not the data.

### T8. The About page now sells the whole product

Rides the same T1 deploy (web-only, but T1 covers it). It opens with
the pitch and then tours everything by name — six leagues and their
models, the betting toolkit, the fantasy suite with the mock draft and
league sync, Polymarket intel, Rocket Radar, My Bets — then "Why here,
and not five other subscriptions." The honesty, legal and
responsible-play sections are untouched underneath. Read it on the
phone and tell me if the pitch lands.

### T9. Tap any fantasy player for his dossier

Same T1 deploy. Every player name on the fantasy page — usage rows,
trade cards, the whole draft kit, the rankings table, camp, the waiver
pulse, and the mock draft — now opens a bottom-sheet dossier: draft
value (proj/xFP/VORP/tier), usage shares with the trend, buy/sell
gaps, where the ranking sources argue, camp movement, new-team flags,
and his real weekly volume charted from the game logs. Sections only
appear where a board actually knows something.

### T10. The fantasy dossier became the full player page

You sent the render; it is followed. Tap any player on the fantasy
page and, when the server answers, the compact card upgrades to the
full page: season stat tiles with position ranks ("2nd of 71"), the
board projection with tier dots, fantasy points by week (real fp_ppr),
matchup strength for the next four games (defenses ranked by fantasy
points they allowed to his position in our own logs), the snap-share
ring and per-game volume, an eight-week game log with each game's real
final, the upcoming game with spread/total/implied, and key takeaways
derived only from real flags. Rides the T1 deploy (server.py grew the
/api/players/fantasy endpoint). Tiles thin out only where the DB lacks
the 08-15 component markets — your laptop has them; the droplet gets
them on its next NFL ingest.

### T11. One-time /tmp sweep — droplet AND laptop, ~30 seconds each

Found while closing out the day: every test-suite run used to leave
~1,600 temp directories behind in /tmp (each fixture makes one and
nobody deleted them). This cloud machine had 236,908 of them — 28GB —
which is what kept driving the suite into “no space left on device.”
The runner now sandboxes and sweeps them itself, so this is a one-time
cleanup of the old debris, not a chore that comes back.

Droplet (deploys used to run the suite):

```
find /tmp -maxdepth 1 -name "tmp????????" -mmin +60 | wc -l
find /tmp -maxdepth 1 -name "tmp????????" -mmin +60 -exec rm -rf {} +
```

Laptop (same two commands — macOS keeps its per-user temp elsewhere,
so also count the Python one):

```
find "$TMPDIR" -maxdepth 1 -name "tmp*" -mmin +60 | wc -l
find "$TMPDIR" -maxdepth 1 -name "tmp*" -mmin +60 -exec rm -rf {} +
```

The first line just counts, so you can see the size of it before
deleting. If the count is small, skip the delete — it only matters
where the suite ran often.

### T12. Headshots in the new fantasy pieces — rides the T1 deploy

You asked from work: “Make sure you have the headshots in the new
fantasy shit.” The sweep found the draft kit was the real gap — its
overall board, position tiers, and sleeper rows had carried each
player’s headshot URL since the stamping pass and were rendering plain
text anyway. All three now draw the face. The dossier also stopped
trusting the first board that matched a name (often the one WITHOUT
the face) and now takes the headshot from whichever board has it, and
your Sleeper roster list falls back the same way for bench players
with no usage row.

Verified here against a fresh build: 146 of 150 board rows, 10 of 10
sleepers, and 60 of 60 usage rows carry real photo URLs (the misses
are name variants the roster file spells differently). Where a photo
is missing or slow, the drawn team-color avatar stays underneath — no
blank circles. Nothing for you to run beyond T1 + T3: T3’s face
ingests are still what fills MLB/NBA photos, and the NFL faces come
from the roster file the build already reads.

### T13. The Cade Mays report — why injuries went stale, both fixes shipped

Cade Mays broke a wrist bone in Lions camp on August 9 (out 8–10
weeks) and nine days later the site still showed him “Active.” Two
separate holes, both real, both closed:

1. **The refresh loop could die silently.** The background refresher —
   the thread that keeps EVERY board current on the droplet — had no
   guard around its cycle. One exception anywhere in a cycle killed it
   for good, and the server keeps serving stale files afterwards, so
   nothing looks broken. (The UFC/MLB/memes live threads always had
   the guard; the main loop never got it.) One bad cycle now logs one
   line and the next cycle runs.

2. **ESPN never retires “Active” rows.** A cleared-to-play notice from
   months ago sits in their feed forever, and August has no filing
   duty that would produce a newer row to beat it — so the page wore
   an old “he’s fine” over a broken wrist. Return notices now age out
   after 14 days (undated ones are dropped outright); real
   designations — Out, IR, Questionable — never age out, because they
   ARE current status.

Before you deploy, 10 seconds on the droplet to confirm which hole bit:

```
ls -l /srv/qellys/web/data/injuries.json
```

If that file’s timestamp is minutes old, the loop was alive and ESPN
was the laggard. If it’s days old, the loop was dead — worth knowing,
but nothing more to do either way: the T1 deploy restarts the service
into the guarded loop and the next injuries pull applies the cut.
Injuries refresh from ESPN’s feed at most every 30 minutes, for every
league that publishes one (NFL, MLB, NBA, WNBA, CFB; UFC has no feed
anywhere, which the page says rather than hiding the tab).

### T14. Injury tags on every roster surface + a pulse for the refresh loop

You asked what else could get done — two follow-ons from the Cade Mays
report, both riding the same T1 deploy:

**Injury tags everywhere a player’s name is a decision.** The injuries
page was already right; the gap was everywhere else — the draft kit
ranked a man with a broken wrist and said nothing. Now the kit’s
board, tiers, and sleepers, every mock-draft row, the dossier card,
the full player page, and the search profiles (every sport, not just
NFL) show a compact colored designation — “Q”, “OUT”, “IR”, “DTD” —
with the injury and return date on hover, and the dossier spells the
whole sentence: “Questionable — Calf.” Cleared-to-play notices never
tag; that would re-create the exact confusion T13 just fixed.

Second round on the same theme: your **Sleeper “My roster” rows** tag
too, with a one-line “Carrying a designation: …” callout above the
list naming exactly who — the first thing a manager checks. The
**roster-directory search fallback** tags as well, so even a player
with no logged games (linemen, rookies) shows his status. And the
**mock draft’s CPU now reads the injury report**: an OUT/IR-tier
player’s draft weight collapses to a quarter (a multiplier, not a ban
— late-round stashes are a real strategy, and you can still draft
anyone the tag warns about).

Third round: the **live draft sync’s own panels** — the “Best
available” chips and the pick-by-pick advice’s take — tag as well,
which matters most on draft night. The whole draft-day path got a dry
run against a stubbed Sleeper draft: connect, three picks crossed off
the kit, best-available with tags, advice panel with survival odds —
zero page errors.

**The refresh loop now proves it’s alive.** T13 guarded the loop
against dying; this makes any future death visible in seconds instead
of days. The loop writes `web/data/heartbeat.json` every cycle —
whether the cycle succeeded or not — and `python3 launch.py --check`
reads it first, before the per-file ages: a fresh beat with one old
board means a failing build; a dead beat means the loop is down and
says so in those words. File timestamps alone can’t tell those apart.

### T15. My Bets grew its insights — “What your book says about you”

Same T1 deploy. The bet log was a list with totals; now it reads your
habits back to you, Juice Reel-style, all from the bets you already
logged: a bankroll curve (cumulative P&L with a break-even line),
P&L tables by sport and by odds band (heavy favorites / favorites /
small dogs / longshots), and at most three one-line verdicts — “Longshots
are the leak: −$120 on $120 staked,” “NFL is carrying you,” “At your
average odds you need 42% winners to break even — you’re hitting 36%,”
“You bet bigger on your losers.” Every read is gated on ten decided
bets in the group, so nothing accuses a habit off a thin sample; under
three settled bets the whole section stays hidden. Realized results
only — pending money never colors a verdict.

### T16. The start calendar — fantasy’s new Calendar sub-tab

You asked from work: a calendar showing the best play for each day,
tap a day for the top five with in-depth why. Built and riding the T1
deploy. The grid starts at the first game week (right now that is the
Sep 9 opener) and each game day wears its best play — face, name,
projected points. Tap a day and the five best plays appear as cards,
each showing its whole arithmetic instead of an oracle number:
baseline projection from the draft kit (tier, VORP), times that day’s
game environment (the team’s implied points from the game script over
the league average, with the spread and total printed), plus the
script’s own read (“Everyone eats — high total, close spread”), the
usage trend behind the baseline, and his injury tag. Players ruled
out that day are excluded by name, never silently. Every card taps
through to the full player profile. The build now ships the league
schedule (dates per game) alongside the game scripts — that lands on
the droplet with the same deploy, no extra step.

Second pass, following your Zenos calendar render with only real
numbers: month navigation (‹ › and a First-slate jump), a
play-quality legend where “Elite slate” is the season’s own top
quarter of game days by projected points (computed, never
hand-picked), green-ringed elite days, a selected-day summary strip
(“13 games · top five average 21.4 · ELITE SLATE”), the why rebuilt
as the render’s checklist of facts, FPPG beside each name, and the
render’s floor/median/ceiling range on the full profile — sourced
from the one place a range honestly exists, his own 2025 weeks
(worst / median / best). The render’s salaries, ownership and boom
rates have no honest source here, so they stay off — same rule as
the player-page render.

### T17. The game sim reaches the clock sports — NFL first, nothing priced

You asked whether we re-run games thousands of times, and said to
start it for the other sports. Done tonight, MLB-pattern all the way:
`engine/drivesim.py` replays a game 20,000 times, drive by drive
(NFL/CFB) or possession by possession (NBA/WNBA), anchored to the
market’s implied points so it reproduces the line and adds the SHAPE —
margin distribution, cover-and-over correlation, blowout odds, push
mass. The first sanity check came out beautiful: nobody told the model
the NFL margin’s standard deviation, and drives that score 0/3/7 at
league rates land it at 13.7 — the empirical number is 13-14.

Same discipline as the MLB sim: `ENABLED = False`, nothing prices off
it. The NFL build now journals the sim’s pre-kickoff claims per game
(`data/drivesim_log.jsonl`) so Weeks 1-4 can grade it against finals —
if the joints beat the correlation priors by the paired log-loss bar,
it earns the parlay seat; if not, it stays a diagnostics tool. Play
with it yourself:

```
python3 -m engine.drivesim --sport nfl --spread -3.5 --total 47
```

And your T4 is now doubly worth running — it is the same verdict for
the MLB sim that Weeks 1-4 will be for this one.

**Then the reconciliation ran the same night it was built.**
`drivesimrecon.py` graded the sim against five finished seasons —
1,378 gradable finals with closing lines. The good: win-probability
calibration is genuinely strong (the 60–80% bucket wins 70%, the
80–100% bucket wins 93%), and the margin shape is close (real sd
14.2, sim 13.2; 23% of finals land exactly on 3 or 7). The honest:
**NO EDGE on the joint** — the sim’s cover-and-over correlation does
not beat plain independence at the closing line (+0.0007 ± 0.0012
paired log-loss), so independence keeps that seat, exactly as the
two-standard-error bar demands. That is the system working: game-level
spread and total at the close are nearly independent, and the sim’s
real payoff is the PLAYER layer — QB yards riding the over, stacks,
game-script conditioning — where correlations are large. That is the
September build, and the forward journal (`--forward`) is already
collecting what it will need. Re-run the verdict yourself:

```
python3 drivesimrecon.py --seasons 2021 2022 2023 2024 2025
```

**And the replays are on the site.** Every NFL game page with a posted
line now carries “The replay” — this matchup run 4,000 times: win
share, one-score share, blowout share, a six-bucket margin histogram,
and the cover/over/both line with its lift vs independent legs. The
panel disclaims itself in its own words: anchored to the posted line,
not a pick, prices nothing until the reconciliation says so. Rides the
same T1 deploy; the droplet’s next NFL build stamps it on the Week 1
slate automatically.

### T18. Two from your paste-backs: the simrecon fix + the faces backfill

**The 8,619 mystery is solved, and it was mine.** Your paste proved
`pa` fully populated (309,621 rows, 2021–2026), which killed my first
theory — so the code was the suspect, and it confessed. Every MLB log
row carries a **per-player** game_id (`"Aaron Judge-2026-08-15"`, the
ingest has always written them that way), but simrecon assembled
lineups by grouping on game_id — so every “lineup” it built held
exactly one hitter, and the six-hitter gate failed all 8,619 of them.
The tests never caught it because the fixture seeded shared per-game
ids, a shape the real ingest never writes; the fixture is now
ingest-shaped and there’s a regression test named after the failure.
Lineups now group by (date, team, doubleheader leg). On the laptop:

```
cd ~/App && git pull
python3 simrecon.py
```

Expect the history arm to actually score lineups this time (~900
team-games over the default 30-day window, not 8,619 player-rows).
Paste the whole printout — that’s the #60 verdict evidence.

**The faces backfill is built — one command, as promised.** Ingest
skips already-stored days, which is why re-running it could never fill
the missing photos (your WNBA 171/183 didn’t move). This fills from
ids already in hand instead: NFL takes the 2,816 roster headshot URLs
nflverse ships (and lands them in `player_assets`, which the fantasy
player profile reads and nothing had ever written NFL rows to), MLB
constructs from active-roster person_ids with the same pattern the
prop board uses, NBA/WNBA fill only their faceless rows from the
stored espn_id. Taken URLs are never overwritten; re-running is safe.

```
python3 facesfill.py
```

Then `python3 launch.py --check` — the Player faces lines should jump.

### T19. “Why do I keep having to do ingests” — you don’t, any more

You asked why ingests and settles keep landing on you. The honest
answer: the automation already existed — the droplet runs the full
loop 24/7 (its service runs `launch.py`, which ingests, settles and
rebuilds on its own), and the laptop self-heals every time `launch.py`
starts — but two constants kept betraying you, and both are fixed:

* **The catch-up window was a fixed 7 days.** Your lid was closed
  8/11–8/18 — eight days — so the first missing day silently fell off
  the edge, and that is the entire reason you typed a `--from/--to`
  backfill this week. The window is now **derived from the database’s
  own last stored final, per sport**: however long the machine was
  closed, the next pass resumes exactly where the data ends (capped at
  45 days so a machine off for a whole off-season doesn’t grind).
* **The settle clock was 15 minutes; it is now 5** — your words
  (“every 5 mins scan if props have been won or lost”). It scans open
  props, pulls the free results feeds for any day with an open bet,
  grades what finished, and is a no-op when nothing recent is open.
* **WNBA got the daily-results block it never had.** Until now a WNBA
  day was only ingested when an open bet pointed at it, which is where
  the quiet gaps in its history came from.

What this means in practice: **you never run `ingest.py` or
`--settle` by hand again.** The droplet does everything on its own,
forever. On the laptop, either leave `python3 launch.py` running (it
does everything on its clocks) or just open it whenever you sit down —
startup runs the chores immediately and the gap-aware catch-up heals
whatever it missed. The 184 open predmarket rows are the same story:
they settle when the Polymarket build runs, which happens every cycle
while the launcher is up — they sat open because nothing was running,
not because settling is manual.

### T20. The verdict acted on, and the bug sweep you asked for

**The sim is benched, per its own rule.** Your simrecon printout read
WORSE THAN THE PRIOR by nineteen standard errors on 40,181 pairs, and
the module’s pre-declared rollback ran: `simjoint.ENABLED = False`.
Every parlay pair keeps the 27,613-game measured prior (which beat
independence on your own printout — the seat is real, the sim just
didn’t earn it). The live journal keeps accruing; a future IMPROVEMENT
printout is what turns it back on.

**The sweep found five real bugs; all fixed:**

1. **Your 104 “about to void” predmarket bets were a settler bug, not
   scratched players.** Desk tickets carry an exchange ticker in the
   player column and ride the slate’s date, so the no-show sweep read
   every one as a lineup scratch once the day went final. The sweep now
   skips predmarket and UFC rows (each has its own grader), and any
   ticket it already voided is reopened automatically on the next
   settle pass — no command needed.
2. **Polled JSON files were written in place.** Every board write now
   lands atomically (write-then-rename): gate.publish (all boards),
   record.json, live scores (the 15-second loop!), fantasy, futures,
   rosters, the Kalshi fallback. A phone poll landing mid-write used to
   get half a file and render an error until the next cycle.
3. **The droplet lives on UTC, so its evening “today” is tomorrow.**
   That drift is why the settler needed a neighbour-day fallback. The
   service unit now pins `TZ=America/New_York` — one-time on the
   droplet after your next deploy:
   `sudo cp deploy/qellys.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart qellys`
4. **One HTML injection sink** — the My Bets insight lines rendered
   your sport labels unescaped (a pasted import could carry markup).
   Escaped now; everything else on that page already was.
5. **NBA faces were structurally impossible** — the NBA ingest never
   captured identity (WNBA’s feed hands over a photo URL; NBA’s CDN
   hands over a personId and nothing kept it). The ingest now stores
   the id and the league headshot beside every log row, and the
   `--check` hint gained the `--refresh` flag without which a re-read
   skips every stored day. If you want the 306k-row history’s faces
   now rather than when the season starts:
   `python3 ingest.py nba --seasons 2025-2026 --refresh` (re-fetches
   box scores — takes a while, entirely optional).

Also verified clean: every Python file compiles, every JS file parses,
static file serving can’t escape the web root, profile names are
strictly validated, the escape helper is correct, no mutable default
arguments. The `--check` line that still said “every 15 min” now says
5, and its stuck-bets section no longer threatens to void desk tickets
it has no business grading.

### T21. The page is “Prediction Market” now, and the board grew meters

Your rename, everywhere it shows: the chip reads **PREDICT**, the
masthead and page title read **Prediction Market**, the Record bucket
button, the mode tagline and the `--check` labels all follow. (The
words “Kalshi” and “Polymarket” survive where they name the actual
venue — that part is factual, not branding.)

And the first strike against “the site feels and looks very flat”:
every row on the prediction board now carries a **price meter** — a
track from 0–100¢, the venue’s YES price drawn as a filled length, and
a colored tick where OUR model prices the same claim. Tick right of
the fill in green = the market underprices YES; left in red = it
overprices. The gap you used to compute by reading three numbers is
now visible at a glance, on every row, phone and desktop. Rows we
don’t price show no tick — the meter never fakes the symmetry the dash
columns refuse to. Also fixed while in there: a desk row with no
recorded side used to print a literal “undefined” chip.

Worth saying about “more visuals” generally: the flat look is the
design language from your own render (no shadows, square corners, one
amber accent), so the way this site gets richer is MORE DATA GRAPHICS
— meters like these, the score rings on Flow, the sparklines, the
stadium overheads — not decoration. If you want a different overall
look, do what you did for Fantasy: send me a render to copy and I’ll
match it. And the single biggest visual upgrade on the table is still
**T-item #120, the venue art kit** — that one is waiting on images
from you, and the site already knows how to wear them.

*(More gets appended here as the day goes on — you said to keep the
list running, so this section is the list.)*

---

## WHAT IS ACTUALLY LEFT

### 0. Pull — 14 commits from 2026-08-13

```
cd ~/App && git pull origin claude/sports-betting-app-vhgmho
```

Then run the six commands below IN THIS ORDER. The order is not cosmetic:
each one changes an input the next one reads.

### 1. Re-run the NFL refit — it shipped in the wrong order

```
python3 launch.py --relearn nfl
```

`--relearn` used to run calibration FIRST. Your own NFL run printed the
refutation in formfit's output: "Adopted weights change the model — refit
its temperature next, on the new model." The dial and the memory change
what the model SAYS; the temperature corrects what it says. Fit the
correction first, then move the model underneath it, and the correction
describes a model that no longer exists. NFL shipped exactly one run that
way, so it is currently carrying three adopted dials sitting under
temperatures fitted before them. This re-lands it on dial → memory →
temperature.

### 2. Refit MLB — it has never run through the new calibrator

```
python3 launch.py --relearn mlb
```

MLB has only ever had temperature scaling, which is a one-knob correction
and is structurally incapable of fitting a curve that CROSSES: at a
claimed 83% it moves the number to 95% when the truth is 81%. The
isotonic calibrator can bend, and `calibrate.py` now runs a three-way
bake-off (isotonic vs temperature vs nothing) judged on a chronological
held-out slice. This is the first run that lets it pick.

### 3. Hoops — check the logs are there, then fit

```
python3 ingest.py status
```

NBA and WNBA were not merely unfitted before today, they were an ILLEGAL
`--sport` argument — all three deep fitters validated against a dict that
held mlb and nfl only. That is fixed, but a fit needs game logs. If
`status` shows NBA/WNBA player-game rows:

```
python3 launch.py --relearn nba
python3 launch.py --relearn wnba
```

If it shows nothing, ingest first (`python3 ingest.py nba --seasons
2021-2026`), which is a long backfill and resumable.

### 4. Remeasure the selection haircut

```
python3 launch.py --haircut --refit
```

This has to be re-run because of a defect I shipped and you found:
`selectionfit` read `category='main'` only, so it stopped seeing new
evidence on 2026-08-09, the day paper mode started. It reads main AND
paper now, so the fit is sitting on ~5 days of bets it never counted.

**Done — it came back LIVE at -0.301 pooled (451 bets, claimed 53.8%,
landed 45.9%).** MLB's own fit was refused by its held-out test on very
nearly the same rows, and MLB borrows the pooled cut anyway. That
disagreement is what step 4b looks at.

### 4b. Check the shape, and whether the cut is stable

```
python3 launch.py --shape
```

Read-only, changes nothing. Three answers, in this order: whether the
over-claim is the same size at every confidence (a bias) or grows with
it (a slope); how much leverage the journal actually has to tell those
apart; and whether the one-parameter cut that just went live helps from
several walk-forward origins or only from the single 70/30 boundary that
happened to pass.

### 4c. Collect the preseason (new, and it prices nothing)

```
python3 ingest.py nflpre --seasons 2021-2026
```

Why it exists: nflverse publishes no preseason player stats, so this repo
has never held a single preseason snap — 2021-2025 are periods 001-022,
regular and post only. "Should we model August" is unanswerable while
that is true, and this is the step that makes it answerable next year.
ESPN's box scores are the source; one cached request per played game.

It lands in `preseason_player_logs` and `preseason_games`, **separate
tables**, quarantined from everything the season models read. The run
takes a few minutes for five seasons and is resumable — re-running skips
nothing but costs only cached reads.

**Re-run it even if you already have**, because the finals table is new
(2026-08-14). The box scores say a starting quarterback threw nine times;
only `preseason_games` says the game ended 20-17, and without an outcome
column there is nothing for step 4d to fit against. The second run is
cheap — the schedule is cached and the box scores are already stored.

### 4d. Then ask whether August is priceable at all

```
python3 launch.py --prescan     # who is likely to play their starters
python3 launch.py --prefit      # does that actually move the scoreboard
```

`--prescan` is descriptive: how often the club's starter has played in
this slot in past Augusts, how many attempts he took when he did, and who
is expected to start this year. "plays / mixed / rests" are cut from the
league's own spread of rest rates rather than a number somebody picked.

Read the counts as the CLUB's record, not the named man's — each past
August is measured against its own starter, so Cleveland's "2 of 5" spans
five staffs and is not a claim about Shedeur Sanders.

`--prefit` is the measurement underneath it, and it is the one with a
verdict. The bar is written into `engine/nfl/prefit.py` ABOVE the answer —
60 joined games, p ≤ 0.01, at least one point of out-of-sample adjustment
— so it cannot be talked into place afterwards. Two questions, in order:
whether the attempts move the final at all (using information no bettor
has, purely to falsify), and whether a team's habit from EARLIER Augusts
predicts it out of sample. It writes `web/data/nfl_prefit.json`, and the
preseason board prints the verdict rather than staying quiet — "we
measured and there is nothing" and "we never measured" are different
sentences.

Nothing prices off it either way. `prefit.prices_allowed()` is hard False:
a measured effect is not evidence the book missed it, and that second
question needs preseason closing lines, which only started being recorded
this August.

### 5. Rebuild, so tonight's board prices through all of it

```
python3 launch.py
```

Three things changed underneath the board today and NONE of them are
visible until a rebuild: the price ladder (the stake comes off the odds,
not the grade), the refreshed haircut, and whatever step 1-3 adopted.

### 6. Read back what landed

```
python3 launch.py --learning     # which loops have ever changed a number
python3 launch.py --stakes       # what tonight's board costs
```

`--learning` is the one that answers your original question. `--stakes`
is the check on the ladder: nothing on the board should be a 50-cent
ticket any more — the smallest possible is 0.35u and a standard -110 prop
is 1.00u. Those are $3.50 and $10 ONLY IF 1u = $10, i.e. bankroll x
unit_pct = 10. Yours is stored in the ledger config
(`starting_bankroll`, `unit_pct`); if the bankroll is not $1,000 at 1%,
every dollar figure scales and the floor is not $3.50.

### 7. Look at four things in the browser — ten minutes

`python3 launch.py` serves it. Hard-refresh ONCE (Cmd-Shift-R) on both
the laptop and the phone before judging anything.

- **The stadiums.** The fix was cache-busting, not new art — the variant
  files were rebuilt three times under the same filenames, so your browser
  was holding a mix of generations. One hard refresh clears it. If any
  card is still stale after that, tell me, because then it is not the
  cache.
- **The prop cards.** Bar graphs instead of lines, and the card built to
  your render: face, name, PROP/LINE/ODDS box, labelled axes, stat row.
  NOTE: the NFL board may have nothing to show — every carried prop in
  the Week-1 slate grades Pass, so the cards do not render there. Look at
  the MLB board.
- **The Record page, Receipts tab.** It now leads with BOTH books, main
  and paper, each with a standard error. That is the +17.8% you asked
  about, printed next to what it actually means.
- **The stake chips.** Every one says which rung of the ladder set it.

### 8. Standing rule, easy to forget

`VENUE_ART_V` in `web/js/app.js` must be BUMPED whenever the venue
renders are rebuilt. A cache-busting token nobody changes is worse than
none — it reads as solved while the next rebuild quietly reintroduces the
exact bug you reported today.

### 9. Still open from before, unchanged

- **Which key is `5dc51e48` (#76)** — ten seconds, see below. Not urgent.
- **NFL Week 1 is on a clock (#41).** Unless the NFL logs are ingested and
  refitted before it opens, that board goes live with a model no outcome
  has ever corrected, sitting beside an MLB model carrying corrections
  fitted on 280,000+ player-games. Step 1 is half of this.

---

## PREVIOUS ROUND (2026-08-09) — both closed or unchanged

### A. Which key is `5dc51e48` (#76) — ten seconds

Open `secrets.local` and see which line it is on. Measured 2026-08-08 by
`keycheck.py`: `ODDS_API_KEY` has 10,965 credits, `ODDS_API_KEY_2` has 0
and is spent.

- on **`ODDS_API_KEY_2`** → do nothing. A key with zero credits can spend
  nothing.
- on **`ODDS_API_KEY`** → that is the live 10,965. Regenerate at your
  leisure, keep the old line and add the new one; the ring skips dead keys.

Not urgent either way. It is a quota credential, not a payment method, and
`git grep` plus `git log --all -S` both return zero, so it never reached the
repo.

### B. Look at the site (§4b below) — five minutes

Seven visual changes are shipped and test-pinned and you have not seen any
of them on a real screen. `python3 launch.py`, then a board page and the
Record page at phone and desktop width. The list and what to check on each
is in §4b. Every one has the number that justified it in its commit message,
so you can argue with the measurement rather than with taste.

### Verified done 2026-08-09, no action

- **§1 ingests** — your `--check` shows NFL 269,181 player-game rows, NBA
  306,355, and NFL team ratings on 1,696 games. All three ran.
- **§2 the loss miner** — it no longer prices anything without evidence
  from the book being gated. Tonight it demoted all five closures for want
  of `main` rows, which is the demotion working, not a failure.
- **§5a the nightly job** — installed and running; the launchd/TCC problem
  that kept it from ever firing was the repo living under `~/Desktop`, and
  moving to `~/App` fixed it.
- **§5b the Routines fix** (#79) — done.
- **§4a the `--text-mute` split** (#82) — decided and shipped.
- **§3f the CFB conference feed** (#93, #94) — closed; the live feed cannot
  supply conferences at all, and the built-in table has been corrected.
- **§6 diagnostics** — `movecheck` and `nflguard` still decline to answer,
  which is the correct output at this point in the season.

---

# CLOSED — kept for the record

Everything below is finished. It is here because the measurements and the
reasoning behind each decision are worth keeping, not because anything in
it needs doing.


## 1. Pull, then two ingests — 15 minutes, do it first

Two days of work — real team logos on every sport, player faces on NFL, NBA,
WNBA and MLB, the preseason board, and a crash on the NFL offseason section
— is inert on your machine until you pull. The faces need more than a pull:
the photo URL is captured **during ingest**, so the table is empty until the
hoops seasons are re-read.

```
git pull
python3 ingest.py wnba --seasons 2025-2026
python3 ingest.py nba  --seasons 2025-2026
python3 ingest.py nfl
python3 launch.py
```

`ingest.py nfl` is the one that matters most and has never been run. Without
it there are no NFL team ratings, so `game_bets` is empty and the
moneyline/total/spread board cannot price at all — which is most of what the
NFL board is for during the three weeks its props are dark (§3a).

**It now also carries the fantasy scoring components** — `rec_yds`,
`rush_yds`, `pass_td`, `pass_int` (added with the lineup optimiser) and
`rush_td`, `rec_td` (added with the Yahoo adapter). Until it runs, the
league desk scores every league off nflverse's PPR total with **no**
custom-scoring adjustment, and says so on the page: a quarterback row
reads "could not be adjusted for: pass_int, pass_td". That warning is the
symptom of this command not having run, and it disappears when it does.

What you should see afterwards: photos instead of initials on NBA, WNBA and
MLB prop cards, real logos beside team names everywhere, and the offseason
coach-change rows rendering at all — they were throwing a TypeError and
taking that whole section down.

Anything that can't load a photo falls back to the team-coloured chip it drew
before, so a missing face is cosmetic, never a hole.

## 2. Read the loss miner before it prices anything

```
python3 -m engine.losspatterns
```

Writes nothing. It prints which slices it has convicted and what the veto
would block. The `home_runs` slice now closes, and its reading says 100% of
those are `longshot` bets with the block landing on recommendations. Decide
whether you want that veto live before anything runs `--apply`.

---

## 3. NFL — the part that changed today

I measured three things in the container this afternoon. Two of them move the
NFL plan.

### 3a. The prop board is empty for Weeks 1–3 (#83) — the real finding

Measured against the cached 2025 season, not predicted:

```
2025 week 1:    0 props,   0 players
2025 week 2:    0 props,   0 players
2025 week 3:    0 props,   0 players
2025 week 4:  235 props, 235 players
2025 week 5:  231 props, 231 players
```

Two lines cause it. `player_game_logs()` at `engine/sources/nflverse.py:184`
keeps only `0 < wk < upto_week` — one season, no cross-season carry anywhere
in the file. And `build_slate()` at `nflverse.py:379` skips any player with
`len(logs) < 3`. Week 1 has zero prior weeks, week 2 has one, week 3 has two.
Week 4 is the first with three.

For 2026, from the cached schedule:

| week | dates | props |
|---|---|---|
| 1 | Sep 9 – Sep 14 | none |
| 2 | Sep 17 – Sep 21 | none |
| 3 | Sep 24 – Sep 28 | none |
| 4 | Oct 1 – Oct 5 | appear |

**The NFL prop board would be dark for the first 23 days of the season.**

What still works in those weeks: `build_games()` needs only the schedule, and
the cached `games.csv` already carries real spread and total for all 16 Week 1
games. So the game-level board — moneyline, total, spread off team ratings —
and futures are unaffected. It is specifically the player props that vanish.

**DONE — you chose "build it with the reset gate", and it is built.** On the
2026 week-1 slate it now builds **293 props across all 32 teams**, up from
zero. `launch.py` passes `--carry` on every NFL refresh and it stands itself
down as soon as the season has three real games, so there is nothing to turn
off in October.

Two things the measurement changed, both written up in `docs/NFL_MODEL.md`:

* **The shrink is mild, not heavy.** Fitted on 2024 → 2025 weeks 1-3, the
  best `k` is 2 across every market — an 11% pull toward the positional mean
  on a 17-game log. My plan assumed a stale season needed heavy regression;
  measured, that is wrong in the expensive direction, costing 39% on
  receiving yards if taken all the way.
* **The offseason reset warns instead of discarding.** Discarding a mover
  leaves nothing to project from, so he drops off the board — the exact
  problem being fixed. Level-matched, movers are not consistently worse, and
  fitting them separately returns the same `k = 2`. So 105 flagged movers
  keep their baseline and say so on the card. `DISCARD_ON_RESET` is there to
  revisit it when there is enough data.

Nothing here needs you. Run it if you want to see it:

```
python3 nfl_build.py 2026 1 --carry --injuries --depth
```

Without `--odds` every edge reads +0.0% — the proxy line is derived from our
own baseline, so the model is pricing against itself. That is pre-existing
and expected; real edges need real book lines.

### 3b. The dress rehearsal can happen tonight, not Aug 24 (#41 corrected)

Task #41 says to rehearse against "a real preseason slate." That is not
reachable. The cached nflverse `games.csv` holds 7,548 games and its
`game_type` values are `REG/WC/DIV/CON/SB` only — **zero preseason rows**.
Preseason is not in this data source at all.

But 2026 Week 1 is already in there with real market lines on all 16 games,
so the rehearsal can run now:

```
python3 nfl_build.py 2026 1 --games-only
```

That one is verified — I ran it here this afternoon and it printed all 16
games with spreads, totals and roofs. The full build is the one to try on
your machine:

```
python3 nfl_build.py 2026 1 --injuries --depth --out /tmp/nfl2026wk1.json
```

Expect it to stop at the props with a `player_stats_2026.csv` 404 — that file
cannot exist until games are played, and that is §3a again rather than a
separate fault. What you are checking is that the games, injuries and depth
layers all come through, and that the game-level bets price.

Note the message it prints blames "GitHub release access is blocked by this
environment's egress policy" when the actual error is a plain 404. Cosmetic,
but it will send you chasing a network problem that isn't there.

### 3c. `launch.py` will not touch NFL until Sep 2

`_current_nfl_week()` at `launch.py:224` only calls a week current if the
nearest game is within 7 days. Week 1 opens Wed Sep 9, so the NFL board stays
on its existing data until **Sep 2**, then starts refreshing nightly. That is
correct behaviour, not a bug — but it means between now and Sep 2 the only way
to exercise NFL is `nfl_build.py` by hand, as in §3b.

### 3d. Two things to confirm during the rehearsal

- The NFL journal writes `move_delta` and `move_steam`. The movement capture
  from `c8657de` went in on the shared ledger path so it should, but it has
  never run on an NFL slate.
- `python3 nflguard.py` should read **TOO EARLY** until Week 1 settles. That
  is the correct output, not a failure.

### 3e. The stopping rule is already armed

No action — recording it so the NFL section is complete. `MARKET_TIER` in
`engine/quality.py` is entirely NFL markets and `TIER_MIN_EDGE`/`TIER_SHRINK`
are shared, so NFL prices through the identical gate that MLB's +12-point
over-claim inverted. `nflguard.py` watches cumulative calibration z at
boundary 2.5, looks after each date once 25 bets settle, first crossing wins.
Against a real 12-point gap at 15 bets/week it catches 96% of seasons, median
105 bets, week 7. Against an 8-point gap, 64%. Against 5 points, 30% — and 5
points already inverts the window. **Silence means not catastrophically
dishonest. It does not mean honest.**

`watch.py` runs it nightly for NFL and CFB, so a crossing reaches you as a
notification rather than something you have to remember to check.

---

## 3f. College — the conference feed went quiet (#93)

Found by `--audit cfb` on the 8th, and it is not an audit problem. ESPN's
groups endpoint stopped returning conferences while the teams endpoint on the
same host answered fine. Conference feeds `attention_tier`, which is how the
CFB model decides whether the market is looking hard at a game — so with the
live feed gone, the whole sport resolves through a **twelve-row built-in
table**, and `cfbdata`'s own header says that table exists to be overridden
because "conferences in this sport move around constantly." Post-realignment,
its `Pac-12` entry is close to fiction.

**Resolved, and the answer is that this feed cannot give us conferences at
all.** Your three runs settled it. The host was never down; every shape
returned valid JSON. The shape dump showed why nothing came out:

```
{status, groups: [ {name, abbreviation, children: [
    {name, abbreviation, teams: [ {id, name, abbreviation, logos, ...} ]}
]} ]}
```

Two facts, neither guessable:

- **The group nodes carry no id.** Only teams do. So `{group_id: name}` —
  what this module has asked this endpoint for since it was written — was
  never buildable from it.
- **The four children are NCAA divisions**, not conferences: FBS, FCS,
  Division II, Division III. There is no conference node anywhere in the
  tree. And the team lists paginate at 25, so the 100 rows it returns are a
  page, not a roster.

**I shipped a bug on the way here and your output caught it.** For one
commit I read those division labels as conferences and wired them into
`parse_scoreboard`. That would have told `attention_tier` that Alabama's
conference is "FBS" — dropping every power-five school out of the power set
and pricing the SEC as though nobody was watching it. Reverted; conference
resolution is back on `conferenceId` and the built-in table, exactly as
before any of this. A test now fails if that map is wired into naming again.

So the honest state: **CFB conference resolution is unchanged and still runs
on the twelve-row checked-in table.** What was gained is knowing the live
feed cannot replace it, instead of assuming it was temporarily broken. The
audit still needs a D-I filter and still does not have one — a paginated
list is worse than none, so it audits all 756 and says so.

I also removed a `conf` field I had added to the team payload on the guess
that ESPN ships `conferenceId` there. It doesn't, nothing read it, and it was
riding along on 756 rows to the browser.

`limit=900` was the last idea and it did not lift the pagination — still 25
per division. So the endpoint is a dead end and the build has stopped asking
it: `fetch_conferences` made four requests per cache miss to be told again
what three runs already established. `assets.py --conferences` still probes
on demand, so re-checking after any ESPN change is one command, not a code
edit.

**Nothing here needs you any more.** It is closed, with one real thing left
over that this feed can no longer answer:

### The conference table — checked, corrected, closed

Derived twice, from 2025-11-01 and 2025-11-29. Both slates: 50 teams, 50
joined to CFBD, no misses. Between them, **nine of the twelve ids confirmed**
— ACC 1, Big 12 4, Big Ten 5, SEC 8, Conference USA 12, MAC 15, Mountain West
17, FBS Independents 18, Sun Belt 37.

**One real error found and fixed: id 151 was labelled `FCS` and is the
American Athletic Conference.** Both Saturdays resolved it unanimously, four
schools on the second, while every other id on those slates came back
matching — so the method was not simply disagreeing with everything.

It moved no price. Nothing in the engine keys on the string `FCS`, and
`POWER_CONFERENCES` is exactly `{SEC, Big Ten, Big 12, ACC}` — all four
verified. It was a label on the board naming the wrong conference.

The `MAC → Mid-American` mismatch from the first run was my alias table and
is fixed; CFBD drops the trailing "Conference".

Still uncovered: **9 (Pac-12), 20 (American)**. Neither had a game on either
slate, which for a two-team Pac-12 is not surprising. Nothing needs doing —
if you ever want them checked, `python3 assets.py --conf-table 2025-09-06` or
any earlier-season Saturday will reach different conferences. Low value: both
are non-power, so neither can move a tier.

Which id real FCS teams carry is now unknown, and deliberately not guessed.
Unresolved conferences come out empty, and `attention_tier` reads empty as
STANDARD — never as "nobody is watching this".

---

## 4. Website visuals

The design queue is empty — all four items shipped, each with a before/after
number in its commit. What's left is one decision and one look.

### 4a. The one decision: split `--text-mute` (#82)

`--text-mute` measures APCA **Lc 15** on every dark ground — the point of
invisibility — and it is used **108 times**, on things people need to read:
`.section-title`, `.tile .k` (the label on every metric tile), `.matchup
.away`, `.pick .book`, `.game-sub.starters`.

Be exact about the standard: this is *not* the "WCAG flatters dark pairs"
case from the manual. It measures 2.57:1 in WCAG terms, which fails AA for
large text (3.0) as well as normal (4.5). Both algorithms agree it is too
faint.

It cannot simply be made lighter. The tiers by OKLCH lightness:

```
--text       L 0.919    Lc 90
--text-dim   L 0.708    Lc 51   (already under its own 60 target)
--text-mute  L 0.441    Lc 15
```

Reaching Lc 60 needs `--text-mute` at L 0.761, which is **brighter than
`--text-dim`**. The hierarchy inverts. What each target costs:

```
Lc 30 (decorative)   L 0.566   #7B766D
Lc 45 (large/bold)   L 0.670   #9A958C
Lc 60 (secondary)    L 0.761   #B6B1A8   <- passes --text-dim
```

The real fault is one token doing two jobs — decorative furniture, and
readable secondary content. The repair is to split it and decide which of the
108 sites go in which tier. **A suggested shape, not a decision:**
`--text-mute` stays quiet at ~L 0.57 (Lc 30), a new `--text-quiet` at ~L 0.67
(Lc 45) takes the readable labels, and `--text-dim` probably wants to come up
too.

Also under target: `--bad` at Lc 36, below the 45 large/bold bar. Negative-EV
and error text is set in it.

```
python3 contrast.py --wcag     # the whole table, writes nothing
```

`tests/test_contrast.py` is a ratchet, not a standard: it pins today's numbers
and fails if any pair gets fainter. So the decision stays open instead of
quietly getting worse while nobody looks.

### 4b. The one look: seven changes you have not seen on a real screen

All shipped, all test-pinned, none eyeballed by you. Run `python3 launch.py`
and look at a board page and the Record page at both phone and desktop width:

- `afa618b` — real minus signs (U+2212) on every number, chosen by measured
  font metrics. Check dates still read `2026-08-07` with hyphens; that
  regression happened once and the guard is a preceding-character rule.
- `8795028` — the dark neutrals moved onto hue 84, the same hue as the rest of
  the palette. Backgrounds should read very slightly warm rather than blue.
- `4c20069` — nav indicator and confidence bars now animate on `transform`
  instead of `width`/`left`. Should feel identical but smoother; watch the
  nav underline as you switch tabs.
- `9205827` — five box-shadow transitions removed (the shadows themselves were
  already gone, so these were animating nothing).
- `5dc3c82` — apostrophes curled in copy, and only in copy.
- `55640ae` — one span on the Edge Board was painting a green the palette does
  not own.
- `d1f0cc5` — the contrast measurement itself; nothing visual changed.

If any of it looks wrong, the number that justified it is in the commit
message, so we can argue with the measurement rather than with taste.

---

## 5. Infrastructure — two things that only need a terminal

### 5a. Install the nightly job

```
bash tools/install-nightly.sh --now      # run once, read the log
tail -40 logs/nightly-$(date +%F).log
bash tools/install-nightly.sh            # then schedule for 06:00
```

Runs `launch.py` then `watch.py`. **`watch.py` prints nothing on a quiet
night — that silence is the design**, not a broken install. The log is how you
tell the difference.

### 5b. Approve `update_trigger` (#79)

The two Routines have a silent-push-failure hole: a run can do its work and
fail to push without saying so. The prompt fix is written up in
`docs/ROUTINES.md` under "Amendment after run #1".

It needs approving from the **Claude Code desktop app or CLI on the Mac** —
web and mobile have nowhere to show the permission prompt. Or paste both
prompts into the claude.ai Routines UI by hand, which needs no approval.

---

## 6. Diagnostics sweep — five minutes, all read-only

```
python3 barcheck.py     # why a higher edge bar cannot fix the over-claim
python3 movecheck.py    # expect NOTHING TO MEASURE YET — correct
python3 nflguard.py     # expect TOO EARLY — correct
python3 watch.py --all
python3 gapcheck.py     # expect "cannot be answered yet"
python3 assets.py --conferences        # §3f — the one I need output from
python3 assets.py --probe --sport nba  # confirms the face resize
```

None of these write anything. Three of them are supposed to decline to answer
right now, and knowing which three is the point of running them.

**New 2026-08-18 — the game-sim verdict (task #60), ~10 minutes:**

```
python3 simrecon.py
```

Read-only. The Parlay Zone has been pricing two-bats-one-lineup pairs off
the game sim's own dealt innings instead of the flat +0.186 prior — that
shipped on structural gates, but no OUTCOME had ever graded it. This
replays the last 30 slates from your DB (plus whatever the live journal
has recorded) and prints one of three verdicts, with the bar written in
the file's header before any answer: IMPROVEMENT, KEEPS ITS SEAT, or
WORSE THAN THE PRIOR — and the last one names the exact one-line
rollback (`engine/mlb/simjoint.ENABLED = False`). Paste me the verdict
block either way; the adjacency split (back-to-back bats vs distant
ones) is the line I most want to see.

**Two more, new since this list was written — first live contact for the
two pages built while you were out:**

```
python3 launch.py --memes      # Rocket Radar live-shape probe
python3 launch.py --injuries   # Injury Report probe — all five leagues
python3 launch.py --venues     # Stadium-art probe — is it one set of pictures?
```

`--injuries` should print counts for nfl/mlb/nba/wnba/cfb and the
freshest filings league-wide. It is the same ESPN host the live scores
already use from your machine, so anything other than instant success is
surprising. CFB at (or near) zero is normal — schools have no duty to
report. Once it runs, check the new Injuries tab in any sport and the
"Injury watch — tonight's teams" block on Recommended → Watchlists.

`--venues` needs no network — it measures the files already in the repo.
It exists because of the one bug nothing else in that chain could see:
`variants/` held two GENERATIONS of art, and since the card picks a slot
from the home team's kit, a neutral-kitted club got the sharp render and
a colour-kitted club got a soft sheet tile, deterministically. You spotted
it by eye on 2026-08-13; this measures it.

It should print `SERVED BY THE SITE: steel` and list fifteen colour files
as off-generation — that is the CURRENT, KNOWN state, not a new problem.
Fixing it means generating fifteen replacement renders; the prompts, the
exact filenames and the check-in steps are in `docs/VENUE_PROMPTS.md`. The
short version: one full render per colour (never a five-up sheet),
1536x1024 3:2, tint the FLOODLIGHTS not the grass. Then
`python3 tools/venues_ingest.py`, re-run `--venues`, paste the
`VENUE_MATCHED` line it prints, and bump `VENUE_ART_V`.

The whole Rocket Radar stack (new "Meme Coins" tab, GeckoTerminal +
DexScreener feeds, momentum/risk scoring) was built against fixtures
because the sandbox can't reach either provider — the same story as
statsapi and Savant. This run is where the parsers meet reality. Expect
coins on the first run; expect the rocket list to be THIN until the
launcher has polled a few minutes, because acceleration needs three
sightings of a coin on our own tape. Zero coins with fetch-failure notes
= network; zero coins with clean fetches = a payload shape moved and
`engine/sources/dexes.py` needs a look. The run also hits Solana's
public RPC for holder concentration (top-10 % on the page) — a
"solana rpc holders: N lookups declined" note means that host is
unreachable or rate-limiting, and the column shows "—" instead of a
number, which is the honest state. The Live chart buttons need nothing
from you: they embed the venue's own chart in the browser. It writes the board JSON and the
snapshot tape — the one non-read-only line in this section, both files
the launcher rebuilds anyway.

The two `assets.py` runs are new. `--probe --sport nba` should show the
combiner at ~15KB against ~274KB raw — that measurement is already in hand
and the run is just a regression check. `--conferences` is the one carrying
real information.

---

## 7. The Odds API keys (#76) — now answerable in ten seconds

**Measured 2026-08-08 by `keycheck.py`:**

```
ODDS_API_KEY     10,965 credits left,  9,035 used
ODDS_API_KEY_2            0 left,     20,000 used   — SPENT
```

Both keys are live and correctly named; the second one's plan is simply
exhausted, and the ring skips a spent key automatically, so nothing is
broken. Between them you are running on ~11k credits until the second
plan resets.

That also settles the leak question below without any guesswork. Open
`secrets.local` and see which line the key starting `5dc51e48` is on:

- it is **`ODDS_API_KEY_2`** → do nothing at all. That key has zero credits;
  someone holding it can spend nothing.
- it is **`ODDS_API_KEY`** → that is the one with 10,965 credits on it.
  Regenerate at your leisure, keep the old line in the file, and add the new
  one — the ring skips dead keys.

Original write-up follows, still accurate on everything else.



Not a blocker, and I previously wrote it up as though it were. It is a quota
credential, not a payment method: the worst case is someone spending credits,
and if the leaked one is your exhausted key the worst case is nothing.

Verified: `git grep` and `git log --all -S` both return zero — the key never
reached the repo or its history. `secrets.local` and its variants are
gitignored at `.gitignore:29-31`.

Open `secrets.local` and check whether `5dc51e48…` is the dead key or the live
one. Dead → do nothing, just don't top that one up. Live → regenerate at your
leisure. Your two-key setup is already the design: `oddsapi.py:284-305` reads
a ring (`ODDS_API_KEY`, `ODDS_API_KEY_2..n`, or `ODDS_API_KEYS` comma-
separated), `get_api_key()` returns the first with credits left, and line 427
swaps to the next key and retries the same call when one comes back exhausted.
Keep both in there, dead one included — the ring skips it.

## 8. Accounts — your info follows you now (2026-08-10)

> **SUPERSEDED 2026-08-15.** The name-and-PIN profile below still works and
> is still what `data/profiles/` holds, but it is no longer the front
> door. There is now a real **email and password** account
> (`data/accounts.db`, scrypt verifiers, hashed sessions) that stores four
> things instead of three — My Bets, fantasy leagues, bankroll **and
> search history** — and it is what a public site will use. See
> `GUIDE.md` → "Accounts and subscriptions" and `docs/ACCOUNTS.md`.
> Nothing you already synced is lost; both stores are read, and both are
> now in the weekly backup.
>
> **One thing to look at when you're next at the laptop:** run
> `python3 launch.py --check` and read the new *Accounts backup* line. If
> it warns, your newest backup zip predates the fix that put
> `accounts.db` in it — the line prints the one command that forces a
> fresh one, or you can just let the next weekly backup handle it.


My Bets, the Sleeper league link and your bankroll used to live only in
each browser's localStorage — which is why the phone and the laptop each
made you type them in again. There's now a **Make an account** card on
the My Bets page (and on Fantasy → Around the league): pick a name, add
an optional 4–12-digit PIN, and those three things sync to every device
that signs in.

Where it actually lives: `data/profiles/<name>.json` on the laptop
running the site. No cloud, no email, no third party — and still no
sportsbook logins anywhere. The PIN is stored salted-and-hashed and
keeps other people on your Wi-Fi out of your book; it is not
encryption (the site is plain HTTP on your LAN), just a lock on the
door. Sync needs the live server (`launch.py`), merges so a bet logged
on two devices at once can never be lost, and deletions carry across.
Sign out any time — everything stays on the device, it just stops
syncing.
