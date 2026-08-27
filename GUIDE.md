# Qellys Book — Owner's Guide

Written for the owner, assuming no coding background. Everything you need
to run, check, and troubleshoot the system is on this page.

---

## The 30-second version

```
cd ~/App          (or wherever the project lives)
git pull          ← get the newest code whenever I tell you I pushed
python3 launch.py ← start everything → http://localhost:8000
```

Leave `launch.py` running in its terminal window. It refreshes every page
about once a minute, runs the nightly chores by itself, and prints one
line per product each cycle. **You almost never need any other command.**

To check health at any time (safe to run while the site is up):

```
python3 launch.py --check
```

That prints a full checklist: which data feeds are reachable, how fresh
each page's data is, whether every page's JSON is valid, how many rows
are in each database, journal status, and backups.

It can also **render all 13 pages in a headless browser** and report any
JavaScript error — the class of bug no data check can see (it is how a
phantom arbitrage on the Scanner and a broken parlay calculator were both
caught). That part is optional and skips with instructions unless you run
once:

```
npm install playwright && npx playwright install chromium
``` When something seems broken, run this first and paste me the
output.

---

## The six pages — what each one is

| Button | What it does | Live when |
|---|---|---|
| **⚾ MLB** | The betting model: player props, sharp-anchor game bets, Edge Board, Long Shots (home-run board), Record | Now (daily in season) |
| **🏈 NFL** | Same engine for football | September |
| **🏈 CFB** | College football: full-game markets tiered by how hard the market is watching, and conditionals that wait on a starting QB | Late August |
| **🛰️ Polymarket** | Informed-flow detection on prediction markets: whale flags with scores, top traders by profit, our flag report card | Now |
| **🏆 Fantasy** | Usage trends, buy-low/sell-high (xFP), game scripts, Sleeper league sync, **draft kit** (VORP board, tiers, live draft sync) | Now (2025 data until September) |
| **🏀 NBA** | Scalpy: minutes engine, probability distributions, humility clamp, max 4 picks a slate | October |
| **🥊 UFC** | Scalpy MMA: fighter dossiers, joint method-of-victory model, pass list | Fight weeks (needs dossiers — see below) |
| **🧭 Why Us** | The positioning page: what makes this different from picks services, live receipts from the journal, and an open math toolbox (de-vig, Kelly sizing, parlay-vs-singles calculators) | Always (no data feed needed) |
| **📊 Standings** | A tab inside each sport (not UFC): full standings for the current season, grouped by real conference and division, plus the postseason bracket once it starts. Counted from our own results, so it can never disagree with the records shown elsewhere |
| **📋 Rosters** | Now a **tab inside each sport**, not its own page. NFL shows the real published depth chart; MLB, NBA and WNBA show who has actually appeared for each club this season, most games first — built from our own game logs |
| **ℹ️ About** | Plain-English explainer for anyone who lands here cold: what the site is and isn't, the legal terms, why nothing here is betting advice, and responsible-gambling help | Always (no data feed needed) |

Shared ideas everywhere: **real prices only** (nothing is recommended
against a placeholder line), **every pick is journaled and graded**
(Record tab), and **an empty board explains itself** — if a page shows
nothing, read the message; it says exactly why and it's usually "working
as designed," not broken.

**Click any stadium.** The ballpark/stadium strip at the top of the MLB
and NFL boards is now clickable — each card says how many picks that game
has, and tapping it opens a page for just that matchup: the park and
weather, the game bets, every player prop in it, and any long shots. The
back button returns you to the board, and the page has its own link you
can bookmark or share.

That page also carries a **venue panel**. For all 30 ballparks it shows
the dimensions (left / center / right, plus any wall worth knowing about
— Fenway's 37-foot Monster, the 21-foot Clemente Wall at PNC), the three
park factors the model actually prices with, drawn as bars centered on
the league-average park, and a line on what the park is known for. The
dimensions are there to explain the factors, not to double-count them:
they're display only and never reach the model.

NFL stadiums get a shorter version — roof, altitude, surface — and say
so. A ballpark changes what identical contact produces, which is why MLB
park factors are large and worth modelling; a football field is 100 yards
everywhere, so the venue effect is almost entirely indoors-vs-outdoors
and then Denver's altitude. Live weather is the number that moves an NFL
total, and the game card already shows it.

## How to read the numbers (the honest version)

- **Edge / EV** — how much better the model thinks a price is than fair.
  A +5% EV bet still loses often; the edge only shows up over hundreds of
  bets.
- **CLV (closing line value)** — did the line move our way after we bet?
  This is the earliest real signal the process works. Win/loss over a
  week is noise; CLV over hundreds of bets is the scoreboard.
- **"No qualifying plays" / small pick counts** — the models are built to
  pass on most things. That is the discipline, not a bug.
- **Per-sport records.** The Record tab now opens on whichever sport you
  came from, with a row of chips across the top — All bets, Polymarket, and
  one per league. The combined number answers "is the system making money";
  a per-sport one answers "is this model any good", and the average of six
  models actively hides that. A journal reading −7% overall can be MLB at
  +2% and NFL at −19%, and only one of those needs fixing.
  The samplers, account health and model eras stay on **All bets** — a
  per-book limit risk is not a per-sport question — and Polymarket has its
  own scope because its flags are graded by a report card, not staked as
  bets. Folding a flag rate into a betting P&L would make both meaningless.
- **Calibration readouts** (Record tab, Polymarket report card) — "model
  said X%, reality delivered Y%." When those track each other, trust
  grows; when they don't, we fix the model, not the story.

---

## What runs automatically

While `launch.py` is running, with no input from you:

- every ~60s: all six pages rebuild (scores free, odds only when the
  budget allows — cached prices in between, never placeholder lines)
- **every ~15 min: tonight's finished games are graded automatically.**
  Picks settle within about a quarter hour of the final out, and the
  Record page updates itself. You should never need `--settle` again.
- **at launch:** the same settle runs immediately, ignoring the timer —
  so opening the site the morning after a slate catches everything up.
- first cycle each day: ingest yesterday's MLB results, re-settle,
  update the Record page, harvest closing odds when affordable
- Polymarket: records the trade tape every cycle (it can't be rebuilt if
  missed — this is why the launcher should run daily)
- weekly: an automatic **backup** of the three databases (history, the
  bet journal, and accounts), the line-history file, your saved profiles
  and your UFC dossiers → `data/backups/` (newest 6 kept). `--check`
  opens the newest archive and says whether accounts are actually inside
  it — because "we meant to back that up" and "it is in the zip" are
  different claims, and only the second one restores.

**"Why are my picks still open?"** Tonight's picks stay open until the
games actually end — that's correct, not a bug. `python3 launch.py
--check` now tells you which kind you have: it flags anything older than
yesterday as a real problem and says so, and confirms when the open ones
are just tonight's board waiting on results. It also prints when the
auto-settle last ran, so you can see the loop is alive.

## The few manual commands (rare)

| When | Command |
|---|---|
| I say "pull and relaunch" | `git pull`, then Ctrl+C the launcher and `python3 launch.py` |
| **Build multi-season history (do this once per sport)** | see "Filling in the history" below |
| NFL data refresh (few times a season) | `python3 ingest.py nfl` |
| MLB history | `python3 ingest.py mlb --seasons 2021-2026` |
| NBA history | `python3 ingest.py nba --seasons 2021-2026 --scores-only` |
| WNBA history (May–October, the live one right now) | `python3 ingest.py wnba --seasons 2021-2026` |
| College football history | `python3 ingest.py cfb --seasons 2021-2026` |
| College football history **from a server** (results + player usage, one request a season) | `python3 ingest.py cfbhist --seasons 2022-2025` |
| WNBA board (May–September) | builds automatically once the history above is ingested; it is **on probation** — see below |

| Confirm a college QB (turns a conditional into a bet) | `python3 launch.py --confirm-qb "TOL" --starter "Name"` |
| See which CFB games are waiting on a QB | `python3 launch.py --confirm-qb` |
| New Odds API key | put it in `secrets.local`, then `python3 launch.py --reset-budget` |
| College recruiting data (free, big September upgrade) | get a key at collegefootballdata.com/key, put `CFBD_API_KEY=…` in `secrets.local` |
| Health check | `python3 launch.py --check` |
| **What data is each model missing?** | `python3 launch.py --coverage` (or `--coverage wnba cfb`) |
| Leave it running while you're out, picking up pushed fixes | `caffeinate -is python3 launch.py --auto-update` |
| Force a settle right now (rarely needed — it's automatic) | `python3 launch.py --settle` |
| Bets still open after the games ended | `python3 launch.py --settle all` |
| Fold old 0.00-unit picks back into the record (once) | `python3 launch.py --resize-unstaked` |
| Separate long shots from the main record (once) | `python3 launch.py --repair-journal` |
| Does the site still look like the renders? | `python3 launch.py --renders` (add `--shots out/` for a contact sheet) |
| Why is the board empty? | `python3 launch.py --why-empty` |
| Why did the UFC card produce no picks? | `python3 launch.py --why-ufc` |
| What does each WNBA feed endpoint actually return? | `python3 ingest.py wnba --probe` |
| Why do N props have no book price? | `python3 launch.py --odds-doctor` |
| A trade isn't showing on the Fantasy page | `python3 launch.py --refresh-rosters "Player Name"` |
| See a team's active roster | Menu → **More** → **Rosters** (search a team or a player) |
| Settle UFC picks + see what dossiers are needed | `python3 ingest.py ufc` |
| Record a UFC weigh-in (fight day) | `python3 launch.py --weigh-in "Fighter Name" 155.5` |
| See which weigh-ins are still missing | `python3 launch.py --weigh-in` |
| Set where a UFC card is being held (cage size + altitude) | `python3 launch.py --card-venue "UFC Apex" "Las Vegas"` |

**About the WNBA board:** it runs the same Scalpy pipeline as the NBA —
minutes first, distributions, humility clamp, approval gate — with the
40-minute game accounted for wherever a number is denominated in minutes.
What it does *not* have is tuning fitted to WNBA results: the margin SD,
the blowout curves, the stat spreads and the gate thresholds were all
fitted against NBA games. So the board is **on probation**. It prices and
journals every pick exactly as a live board would, and grades them, but it
stakes nothing until that record clears the promotion bar. The page says
so at the top. Inventing "WNBA-ish" constants would have looked tailored
while being made up, and nothing downstream could have told the
difference.

**About the college football board:** it is the same decision spine as
everything else, with one idea layered on top — **attention is the axis**.
About 134 teams play 60-plus games most Saturdays, and no book prices a
Wednesday MAC game the way it prices Ohio State – Michigan, so how much of
our own edge we believe depends on how hard the market was looking. A
marquee game keeps half its edge and has to clear 4%; a low-attention game
keeps three quarters and clears 2.5%. That is why the same model number
can be a pass in one game and a bet in another, and it is the whole reason
the page exists.

Two things on that board will look unusual and are meant to.

**Conditionals.** College football has no league-wide injury report, and
the gap between a starter and his backup is routinely worth four to seven
points — more than any edge the model will ever find. So a game whose
quarterbacks nobody has confirmed publishes as a *conditional*: the real
number, the real price, the real edge, an amber badge, and **no stake**.
Check the starter, run `python3 launch.py --confirm-qb "TEAM"`, rebuild,
and it becomes a bet at the grade the conditional advertised. December
games additionally wait on participation being verified, because bowl
opt-outs and the portal can gut a roster between the last game and the
bowl.

**Probation until the variance is measured.** How far college games land
from a projection is a number this engine *measures* from ingested
results, not one it asserts. Until roughly 400 games are in the database
it uses a documented prior instead, marks the board on probation, and
journals without staking. Run the backfill above once and the numbers
become measurements.

### Filling in the history

The NFL had five seasons in the database and everything else had one or
none, and almost every limitation traced back to that. Team ratings firm
up with games. A prop backtest can only replay games it actually has.
Calibration needs hundreds of graded results before it means anything. The
college football variance fit refuses to run at all under 400 games.

`--seasons` expands into each sport's real calendar for you, so you don't
have to remember that the WNBA runs May to October, the NBA crosses New
Year, and college football ends in January:

```
python3 ingest.py cfb  --seasons 2021-2026
python3 ingest.py wnba --seasons 2021-2026
python3 ingest.py mlb  --seasons 2021-2026
python3 ingest.py nba  --seasons 2021-2026 --scores-only
```

`ingest.py cfb` goes to ESPN, one request per day and one per box score,
which many cloud hosts are refused outright. `ingest.py cfbhist` reads
whole finished seasons off the sportsdataverse mirror instead — finished
results AND play-level player production, one request each. That second
half is what the college touchdown board prices off: it will not quote a
player it has no ingested usage for, so without it the board is empty.
The nightly runs it by itself on a box that needs it.

**Start with CFB and WNBA** — they're fast and they unblock the two boards
that need it most. MLB is a few hours. **NBA is the slow one:** a season is
~1,200 games and each needs its own box score, so six seasons is an
afternoon. `--scores-only` skips the box scores entirely and runs many
times faster — that gets you team ratings, the variance fits and
settlement, everything except player-prop backtests. Run it that way
first, and add the full version later if you want prop history.

All of it is **resumable**. Days already stored are skipped, so if it dies
halfway, or you close the laptop, just run the same command again. Ctrl-C
is safe too.

A season is labelled by the year it *starts*, so the 2021 NBA season means
October 2021 through June 2022 — same convention the NFL data already
uses.

**More history is not automatically better, and the code had to learn
that.** Once MLB went from one season to six, three things quietly changed
meaning. The prop model's "season average" became a six-year career
average. A team's "season run differential" — the baseline the hot/cold
board measures against — became a multi-year one, and its win streak ran
straight through the offseason. And two database joins that were instant
on one season stopped being instant on six, which is what made the MLB
board time out. All three are fixed: the live model now reads *this*
season and the measurements still read all of them. The first run after
this change builds a few new database indexes — expect one slow startup,
then faster than before.

**About `--coverage`:** every sport has a written spec in `docs/` with an
implementation map, and those maps are prose — prose rots. A feed stops
resolving, a season never gets ingested, a key expires, and the table still
says ✅ because nobody edited it. `--coverage` answers the same question by
*looking*: it reads the database, the cache and your config, and prints
what each model actually has behind it, why that layer matters, and the
command that closes the gap. A 📋 means no free source exists — those stay
listed every time on purpose, because a permanent gap you've stopped
seeing is how a blind spot becomes an identity.

**About the college recruiting key:** this is the high-school layer —
recruiting composites, blue-chip ratio, returning production, the portal.
It matters most in September, when a team's own results are two games
against opponents nobody has measured either. Without it a results-only
rating quietly says an unproven Alabama and an unproven Kent State are both
average; the market disagrees, and it will take money for that. The prior
carries about a quarter of the projection early and decays to almost
nothing by November, which is the point — it fills the gap until real
results exist. It is free and read-only; without it the college board just
runs without a prior and says so.

**About `--card-venue`:** cage size is the input almost nobody prices.
The promotion's own facility uses a 25-foot cage and arenas use 30 — less
room to retreat means pressure fighters and wrestlers gain and finishes go
up. Altitude is the other half: Mexico City and Denver impose a real
cardio tax that pushes finishes later. Neither rides in the odds feed and
both are one fact per card, so you type them once and every method and
distance price on that card is reshaped. Leave it unset and the model
scores it neutral rather than guessing.

**What changed for UFC:** the model always computed a full outcome
distribution — who wins, by what method, and whether it reaches the
scorecards — and then bet the moneyline anyway. That was backwards. Books
derive method props lazily off the moneyline, so the moneyline is the one
number they have thought about and the props are the ones they haven't.
Now every fight's distribution prices *every* market it implies, and the
model takes the biggest edge relative to that market's own bar. A pick
card can now read "Alpha by KO/TKO +190" instead of a moneyline with no
edge in it. Markets your books quote but our odds feed doesn't carry show
our fair number instead, under "every market this fight implies" — those
are yours to shop, and they are never staked or journaled.

**About weigh-ins:** every UFC pick prints `KILL IF: missed weight …
→ automatic void`. That was a rule with nothing enforcing it. Now a
recorded miss becomes a red flag, and red flags already gate a bet off the
card — so the rule holds itself.

**Live fights.** While a UFC bout is actually happening, the UFC page
grows a **Live now** panel at the top: a body figure per fighter shaded by
where he is being hit, plus head/body/leg counts, the round and the clock.
It polls every 12 seconds while a fight is on and backs off to every 3
minutes when none is.

What it shows is *significant strikes absorbed by target area* — the same
thing the UFC's broadcast graphic shows. It is not a damage score and it
is not a betting signal; the model refuses in-play prices by design and
nothing on this panel reaches it.

Two things it will not do: if the feed stops moving, the badge changes
from LIVE to **STALLED** and the panel says how old the numbers are rather
than redrawing a stale count as though it were current. And if a fight is
live but the feed publishes no target breakdown, it says that instead of
drawing an empty body — zeros look like a fight where nothing has landed.
If that happens, `python3 launch.py --probe-live` prints exactly what the
feed is sending, mid-fight.

**Camp data pulls itself too.** There is still no feed anywhere for camp
footage or training reports — that part is genuinely missing and the page
says so. But three real camp facts *are* measurable from what the dossier
already fetches, and they now feed the grade: how long since he fought
(ring rust is one of the few camp effects with evidence behind it), how
often he fights, and where he trains. Gym changes are found by diffing our
own drafts, the same way NFL trades are found here without a news feed —
which means the first one shows up after the second time a fighter is
drafted, not immediately.

**Weigh-ins pull themselves now.** The launcher checks the card's feed on
every refresh and records whatever weights it carries, validated against
the division limit and the one-pound non-title allowance. `--weigh-in
"Fighter Name" 155.5` still exists for the one case a feed can't cover:
you watched the scale on the broadcast before anyone published it. If
nothing is landing, `python3 launch.py --probe-weighins` prints exactly
what the feed returned, bout by bout — a blank board should never be a
mystery.

An unrecorded weigh-in still shows as **"not recorded"** rather than
passing for "made weight" — those are opposite facts. What changed is
that it no longer costs the fight anything: the fight-week component drops
out of the grade and the rest is renormalised, so a card is judged on what
we know instead of being marked down for a Friday that hasn't happened.

**About `--auto-update`:** the laptop is at home and you are not. With
this flag the launcher checks the branch every 5 minutes, fast-forwards
anything that's been pushed, and restarts itself into the new code — so a
fix lands without you typing `git pull`. Pair it with `caffeinate -is` so
the Mac stays awake for the whole day:

    caffeinate -is python3 launch.py --auto-update

It is off unless you type the flag, because it pulls code and then runs
it. And it is deliberately timid: `--ff-only` (never merges, never
rebases), it refuses outright if the working tree has uncommitted changes,
it never switches branches, and a diverged branch stops it with a message
rather than being resolved behind your back.

**About `--settle`:** this used to be a nightly chore, because the journal
only graded itself on the first cycle of the *next* day. It doesn't work
that way any more — the launcher settles finished games every ~5 minutes
and again the moment you start it, so picks close out on their own within
minutes of the last out.

`--settle` is still there for when the launcher *wasn't* running — a
laptop that slept, a night it was closed, a west-coast game that ended
after you quit. It ingests that day's results, grades every open pick
against them, and prints the open → settled counts for both buckets so
nothing has to be taken on faith.

Three ways to call it:

| | |
|---|---|
| `python3 launch.py --settle` | tonight's board |
| `python3 launch.py --settle 2026-07-25` | one older date |
| `python3 launch.py --settle all` | **every** day that still has picks open |

Use `all` when more than one night is stuck — `--check` says so explicitly
when it spots that, and it saves reading the list and running the command
once per date.

**A note on the clock.** The baseball day rolls at **5 AM**, not midnight,
because west-coast games run past twelve and flipping the board on the
calendar tick would yank still-live bets off the Live tab in the 7th
inning. So a bare `--settle` at 3 AM grades *last night's* board, which is
the one you're looking at — you do not need to work out yesterday's date
and type it in.

## Draft day (Fantasy page, before your Sleeper draft)

The Fantasy page carries a **draft kit** built from last season's usage:

- **Overall board** ranked by VORP — value over the best freely-available
  player at the same position. This is why the 4th-best QB sits below the
  15th-best WR: the QB you can get ten rounds later scores nearly as much.
- **Position tiers** — draft by tier, not rank. Inside a tier the
  differences are noise; the gaps between tiers are the real information.
- **Usage says buy** — players whose opportunity outran their scoring
  last year; the draft-day version of buy-low.
- **Live draft sync** — when your Sleeper draft room opens, paste the
  draft link into the "Draft day" box and hit Connect. Taken players
  cross off everywhere on the page as picks come in, and a best-available
  strip (overall + per position) stays current. Read-only, no password.

Honest limits, because they matter at the table: the board is last
season's volume run forward. Rookies carry no projection (none exists),
and a moved player's numbers came from his old offense — but the page
now TELLS you all of that instead of leaving you to remember it.

## The offseason panel (Fantasy page)

Above the draft kit, the page shows **what the league changed under last
season's numbers** — refreshed automatically on every build, derived
from data rather than from a news list that goes stale:

- **Coaching changes** come from the nflverse schedule file itself:
  every game row is stamped with both head coaches, so "new coach" is a
  diff between a team's last game of last season and next season's rows.
- **Current teams & rookies** come from Sleeper's public players feed
  (the same one league sync uses, cached daily). Board players who
  changed teams get a NEW TEAM flag — their projection is deliberately
  NOT adjusted, because nobody knows what the new offense does to their
  volume, and flagging honestly beats inventing a number.
- **New starting QBs**: current depth-chart QB1 vs the QB who actually
  started late last season.
- **Rookies** are listed with their current depth-chart slot and no
  projection — no NFL volume exists, and the site doesn't fake numbers.

The launcher's daily maintenance also re-pulls the NFL schedule, so as
books post next season's lines over the summer, the **game scripts**
section fills in on its own.

## UFC dossiers (a two-minute review before each card)

The UFC model follows "no dossier, no bet" — and **the launcher now
drafts them without being asked.** A few fighters per refresh, saved as it
goes, so a 34-bout card fills itself in over a few minutes instead of
stalling one refresh for half an hour. You do not have to run anything.

To draft a whole card at once anyway, or a specific fighter:

```
python3 ufc_dossiers.py
python3 ufc_dossiers.py "Fighter Name"
```

It reads the upcoming card from the odds feed (free), pulls every
fighter's real fight-by-fight stats from ESPN's public MMA data, and
writes drafted dossiers into `data/ufc_dossiers.json`. First run takes a
few minutes for a full card (~30s per fighter, then cached). Your job is
the two-minute review it prints at the end:

1. Open `data/ufc_dossiers.json` and check each entry's `review` notes —
   the archetype is guessed from stats, so fix any style you know better.
2. **Red flags block bets on purpose** (chin damage, long layoffs, age).
   Delete a red flag only once you've checked it; leave it and the fight
   stays on the pass list.
3. Or skip the JSON entirely: `python3 ufc_dossiers.py --review` lists
   every flag with context, and
   `python3 ufc_dossiers.py --clear "Fighter Name"` clears one once
   you've checked it.
4. Anything you edit by hand is never overwritten by the tool. Fighters
   it can't find (debutants) stay on the pass list — which is correct.

---

## Accounts and subscriptions (new — for going public)

None of this changes how *you* use the site. It's the machinery other
people need before the site can live on a real server, and it's built but
not switched on.

**Where it is.** The account card sits on two pages: **My Bets**, and
**Fantasy → Around the league**. It's the same card in both places, so
signing in on one signs you in on the other. The billing card appears
underneath it once you're signed in.

**What an account is.** Email and password. It stores four things per
person: their My Bets log, their fantasy leagues, their bankroll
settings, and their search history. That's the whole list — no name, no
address, no card number (see below).

**Passwords are stored as scrypt verifiers, not passwords.** A verifier
is a one-way scramble: it can confirm the password you typed is right,
but nobody — including you, including me, including anyone who steals the
database file — can read the original back out of it. It's the standard
way anyone competent stores a password, and it is why the docs that used
to say "we will never store passwords" were wrong twice over: we do store
*something*, and what we store isn't the password.

**Anything that carries a password is refused over an unencrypted
connection.** That's sign-up, sign-in, password change and delete alike.
A password typed into a plain `http://` page on open wi-fi has already
crossed the network in the clear before it reaches us, and no amount of
scrambling on our end helps with that. Three cases:

- **`http://localhost` on your own Mac** — allowed. Nothing crosses a
  network at all.
- **Tailscale** (`http://100.x.x.x`) — allowed. Tailscale is WireGuard;
  the packets are already encrypted device to device, so the missing
  padlock describes the last inch, not the wire. That carve-out exists
  because the site refused *your* tailnet address and was wrong to.
- **Any other machine with no certificate** — refused, and the message
  names the fix.

So today, on your Mac and your phone over Tailscale, everything works.
Once there's a real certificate in front of the site (Phase 2 —
`deploy/Caddyfile` does this automatically), all of it works from
anywhere, and this stops being a limitation at all.

**Subscriptions run through Stripe.** Card numbers never touch our
server — Stripe hosts the payment page, we only get told "this person
paid." Nothing on the site is locked behind payment yet. That is
deliberate: the code is ready so it can be turned on the day the answers
in `docs/LAUNCH.md` come back, not before.

**Three things must be answered before any of it goes live** (they're
yours, not mine — full detail in `docs/LAUNCH.md`):

1. Stripe, in writing, on whether a paid sports-betting *tool* is a
   restricted business for them.
2. Commercial-use terms for the data feeds. About 25 of them; a few
   (ESPN, the NBA CDN) are undocumented endpoints with no licence at all.
3. A Michigan lawyer on the regulatory side. You're in a legal state and
   the site takes no wagers, which is the easy version of this question —
   but *affiliate links to sportsbooks* is the change most likely to drag
   licensing into it, which is why there are none.

Deeper reading, if you want it: `docs/ACCOUNTS.md` (how sign-in works),
`docs/BILLING.md` (how Stripe is wired), `docs/LAUNCH.md` (the phased
plan), `deploy/README.md` (the server itself).

**`web/terms.html` and `web/privacy.html` are drafts and say so.** They
carry a banner at the top and orange markers everywhere a lawyer has to
fill something in. Don't take the banner off yourself.

---

## Money & API facts

- **One API key total**: `ODDS_API_KEY` in `secrets.local` (The Odds
  API — sportsbook prices for MLB/NFL/NBA/UFC). Everything else —
  Polymarket, NBA CDN, MLB Stats, nflverse, Sleeper, Savant, weather —
  is free and keyless.
- The odds budget is paced automatically (credits reset monthly). If the
  board says prices are cached, that's the pacer saving credits, not an
  error. Don't buy extra credits.
- **Money coming in** is subscriptions only, via Stripe, and is switched
  off until Phase 0 clears. No affiliate deals, no sportsbook referral
  cuts.
- Nothing here places bets. It recommends, journals, and grades. Charging
  people to use a tool is not the same as taking their wagers, and the
  site is built so it stays that way — no bet slip, no deposits, no
  balance, enforced by a test that fails if one appears.

## When something looks wrong

1. Screenshot the page **and** copy the last ~20 lines from the launcher
   terminal.
2. Run `python3 launch.py --check` and copy its output.
3. Send me all of it. The terminal usually names the exact failing feed —
   that's how we've fixed every issue so far (Statcast, nflverse, the
   Polymarket leaderboard…).

Golden rules: an empty section with an explanation is usually the filters
working. Odd numbers at ~11pm are usually in-play prices. And if the data
looks frozen, check that the launcher terminal is still running — it's
the heartbeat of the whole system.
