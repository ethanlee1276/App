# The odds plan: 100k credits a month, every sport its own budget, NFL first

Ethan, 2026-10-21: *"we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority"*.

Ethan, 2026-10-28, after October's credits ran out for every league after
football: *"NHL, NBA, WNBA, NFL, college football, MLB, all of that needs
its own budget and needs to be able to budget every single sport every
month with that 100K credit ... NFL comes first, then college football,
then NBA, then baseball since it's about to be over. So once baseball is
over, we can take baseball out of the credit pool, and whatever other sport
is not being played needs to be taken out of the credit pool ... and make
sure we're not running through credits like crazy."*

Ethan, 2026-10-30, with October's credits nearly gone and the NBA's board
empty: *"tonight's games come first. We need to make up a system of just
recognizing what sport has what games live that night and pulling credits
just for those sports. So obviously if NFL and NBA and MLB and all of them
have a game on that night, then we need to pull all of them. But if just
NFL has a game that night, we just need to pull NFL and so forth."*

The code is `engine/oddsplan.py`. The launcher reads it for every paid odds
pull (`launch._budget_share`). On the box, this prints today's plan: each
sport's month, today's ceilings, and the pace:

    cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan

## Tonight's games only

Every cycle the box counts each league's games **on tonight's slate**: the
boards' own day, which turns at 5 AM Eastern, so a game past midnight is
still tonight's (`oddsbudget.tonight_games`). Then:

* **A league with no game tonight buys nothing**: no props, no game lines,
  no live line (`launch._odds_affordable`). The decline goes in the
  decisions log as "no NFL game tonight — credits go to the leagues playing
  tonight". A board whose times can't be read isn't treated as a night off;
  the pacer decides as before.
* **A league playing tonight is metered at tonight's games.**
* **A board that holds the week buys tonight's games only.** The NFL's and
  college's paid pulls buy the games before tonight's slate ends and read
  the rest from the cache (`--price-until`). A Thursday NFL pull used to buy
  all ~15 games of the week at 25 credits each, about 400 a pull, and a
  Sunday price bought on Thursday is past the 6-hour age limit long before
  kickoff. Now it buys the one game, about 50.
* **UFC's games are its card's bouts**, so the card is bought on fight day.

What readers see: on a day a league doesn't play, its board shows its next
games without prices once the last ones are 6 hours old. Saturday's NFL
board shows Sunday's games unpriced until the 7am Sunday pull. Scores,
schedules and live games keep updating.

## The rule

1. **Held back first.** The reserve (500), the closing-line harvest's daily
   cap (400 a day for every day left) and a 5% buffer. The plan never
   spends these.
2. **Tonight's games first.** Every league playing tonight is owed what
   tonight's slate costs at its cadence, and that's funded before any day
   to come, in the order below: the NFL's tonight, then every other
   league's half of its tonight together, then the rest of tonight tier by
   tier. A league with no game tonight is owed nothing today.
3. **Only sports being played are in the pool.** Every sport in season is
   owed what its normal cadence costs for the rest of the month. A sport out
   of season is owed nothing (the WNBA now). So is **a sport whose season
   just ended**: baseball leaves the pool the morning after the World
   Series' last game, when its board is empty and finds no game in the next
   five days. A basketball or college board that says "offseason" in its
   postseason does the same. What the table held for them goes to the
   sports still playing.
4. **Then the NFL's month, in full.**
5. **Then every other sport playing gets half its share** (`FLOOR_SHARE`),
   all together. That half is its own budget: no sport but the NFL comes
   before it. A short month thins a sport; it never switches it off, which
   is what October did to the NBA and the NHL.
6. **Then the rest, in Ethan's order:** college, then the NBA, then
   baseball, then hockey, UFC and the WNBA together (they split what's
   left by need, so they all get the same percentage).
7. **Headroom only once every sport is fully funded.** The NFL gets up to
   50% extra first. Then the others get up to 25% each, in the same order,
   for extra pulls on a big news day.
8. **Today's ceiling** for each sport is today's need times the share of
   its month the plan could fund, and never less than what step 2 funded
   for tonight. The pacer can't spend more than that on a sport's ordinary
   pulls, but closing-line, readiness and inactives pulls still go through
   when needed.

Until November 1 the NBA comes right after the NFL, ahead of college. That
was Ethan's call on October 28 to get NBA picks back for the month's last
days (runbook GU). From the renewal his order above stands.

It's recomputed from the real balance every cycle, so it corrects itself.
If a sport overspends, the pool shrinks and the next plan trims the last
tier's share above its half, never the NFL's and never anyone's half
unless the NFL's own need takes it. Credits nobody spent (a quiet night,
the harvest using less than 400, a season that ended early) become extra
room for the days after.

## What November looks like at 100,000

| | need (the month) | planned | fill |
|---|---:|---:|---:|
| NFL | 22,100 | 33,150 | 150% |
| College | 10,256 | 12,820 | 125% |
| NBA | 19,398 | 24,247 | 125% |
| MLB (World Series, to Nov 4 at most) | 496 | 620 | 125% |
| NHL | 10,476 | 11,418 | 109% |
| UFC | 224 | 244 | 109% |
| WNBA | off-season | 0 | |
| Held back: closing lines 12,000 · buffer 5,000 · reserve 500 | | | |

With every league buying on its game nights only, all target cadences
together come to about 63k for November, well inside the 82,500 a 100k
plan leaves after what's held back (before the tonight rule they came to
about 87k, and hockey and UFC ran at 60%). So every sport is funded in full
with headroom on top: the NFL half again, college, the NBA and baseball a
quarter, and hockey and UFC share the rest. Once baseball is out, they go
to 115%. December and January fund everyone with full headroom and leave
some credits unplanned.

A month where every sport spends its full ceiling every day still ends
above the reserve; that's tested in `tests/test_the_odds_plan.py`.

## Each sport's budget, in the report

Each sport gets one line: its budget for the month, which is what it has
spent since the renewal plus what the plan holds for it from today, the
share of its need that covers, and today's need, ceiling and spend:

    order: NFL > CFB > NBA > MLB > NHL · UFC · WNBA
    tonight: CFB 3 · NBA 9 · NHL 5 — funded first; no game: NFL, UFC (they buy nothing today)
    tonight's games are funded first, in that order; then the month: the NFL, then every sport playing held 50% of its need before any gets more

    each sport's month: budget = spent + left (fill) | today: need -> ceiling, spent
    NFL    36,450 = 15,800 + 20,650 (150%) |     0 ->     0, 0 · no game tonight
    NBA    15,445 =  6,100 +  9,345 ( 70%) |   753 ->   753, 230
    MLB   season over — out of the pool (spent 140 this month)
    WNBA  out of season

    pace: 3,282 a day — at that pace the pool runs dry Nov 29, 2 day(s) before the renewal; the plan slows every sport to fit ⚠️

## Not running through credits

* **Every ceiling is a day's share of the month**, worked out from what's
  really left, so no sport can spend next week's credits today.
* **The pace line** counts every credit spent over the last seven days of
  this month: every sport, the harvest and the slips. It says the day the
  pool would run dry at that pace. ✓ means it lasts past the renewal. ⚠️
  means spending is ahead of the tables; the plan slows every sport to fit,
  the last tier first. The "last 7 days, a day" line shows which sport.
* **A season that's over spends nothing**, and its share goes to the
  sports still playing.
* **Every call is booked at what the API billed** (its own
  `x-requests-last`), with our estimate beside it. The plan's printout
  says how far apart they are: `the API's own bill, last 24h: … (R×)`. In
  October the API counted ~99,400 credits used against ~55,000 booked; the
  17 books (billed as two regions if every ten count as one) are the likely
  reason.

## What a league's day buys (the targets)

Credits by day, Monday to Sunday, on a typical November week, on the
box's days (the service runs on Eastern time). Today's real slate replaces
the table for today.

| | Mon | Tue | Wed | Thu | Fri | Sat | Sun | week |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NFL | 600 | 0 | 0 | 400 | 0 | 0 | 3,500 | 4,500 |
| College | 0 | 224 | 224 | 252 | 278 | 1,586 | 0 | 2,564 |
| NBA | 639 | 582 | 810 | 468 | 753 | 639 | 639 | 4,530 |
| NHL | 234 | 450 | 270 | 486 | 270 | 558 | 234 | 2,502 |
| UFC | 0 | 0 | 0 | 0 | 0 | 56 | 0 | 56 |

* **NFL.** Sunday: the four windows (7am, noon, 3pm, 6pm ET), plus a
  readiness pull and an inactives pull before each wave, and game lines
  every 15 minutes through the games. Thursday and Monday: the priority
  floor (six pulls on a day with a kickoff inside 24 hours) of that night's
  game. Other days: nothing, since there's no game. A game night the table
  doesn't hold (Thanksgiving's three games, Black Friday, December's
  Saturdays, Christmas) is priced by the game: about 390 for one, 690 for
  three.
* **College.** Eight prop pulls on Saturday, two on Thursday and Friday,
  four on weekday nights, at 13 credits a game for up to 12 of that night's
  games a pull. Game lines run on game nights only, every 15 minutes in the
  pre-game window and through the games.
* **NBA and NHL.** Three prop pulls on a game day: noon, the pre-game run
  and 6pm ET. The NBA adds its three-credit game-lines lane until the last
  tip. Both add the live line while games are on. An 11-game NBA night is
  about 870 credits; a 9-game NHL night is about 410.
* **MLB.** Four pulls on a World Series game day, about 124 credits.
* **UFC.** One credit a fight, four pulls on fight day, nothing on the
  days before.

## The renewal day: check this one

The plan spends to the day your Odds API month renews. **If your plan
doesn't renew on the 1st**, the plan has to know, or late in the calendar
month it would spend credits meant to last until the real renewal.

It works the day out on its own: it walks back through the spend ledger
until it reaches what the API says this month has used. The report's
second line says which way it knows:

* `renewal day measured: …`: worked out from the ledger.
* `renewal day set by QB_ODDS_RESET_DAY`: you set it.
* `renewal day ASSUMED — the 1st`: it couldn't tell (two keys with
  credits on the ring, a fresh month with under 100 credits used, or no
  recent quota reading). While it's only assumed, the plan pays every
  league's normal cadence but **no headroom**, so a wrong guess can't spend
  next month's days early.

If the report's "renews" date isn't the date on your Odds API account,
set the right day of the month:

    cd /srv/qellys && sudo ./deploy/setenv.sh QB_ODDS_RESET_DAY 14

## What changed in the pacer with it

* **NBA, NHL and WNBA pull at noon and 6pm ET** instead of the four
  football windows. Their pre-game window doesn't triple their pace (the
  burst), which would spend a three-pull day before the 6pm injury reports.
* **A day with no game near is off-peak.** When a board's next game is more
  than 36 hours away (NFL Tuesdays and Fridays, college Sundays), the
  pacer used to treat the slate as having no times at all. That kept the
  3-credit game-lines lane on its 15-minute floor all day: about 96 pulls
  and 290 credits on days nobody can bet a game. Now it's hourly.
* **The live line polls every 10 minutes**, down from 5. Every live pull
  comes out of its league's day, and at 5 minutes it was the costliest
  thing a basketball night bought after the props, about 9,000 credits a
  month. At 10 minutes it's half that.
* **UFC is metered at one credit a fight**, its real price. It used to be
  metered at the generic eight.

## Knobs (engine/oddsplan.py)

| | what it does |
|---|---|
| `TIERS` | the order: `("nfl",), ("cfb",), ("nba",), ("mlb",), ("nhl", "ufc", "wnba")` |
| `FLOOR_SHARE` | after the NFL, every sport playing gets this share of its need first (50%) |
| `NBA_FIRST_UNTIL` | the NBA before college until Nov 1, 2026 (Ethan's October call) |
| `NFL_HEADROOM`, `HEADROOM` | 50% and 25% extra, only after every target is funded |
| `BUFFER_SHARE` | 5% of the pool, never planned |
| `NFL_REGULAR`, `NFL_PLAYOFFS` | the NFL's day, Monday to Sunday (0 on a day with no game) |
| `NFL_FLOOR_PULLS`, `NFL_LINES_PULLS` | an NFL game night the table doesn't hold, priced by the game |
| `oddsbudget.tonight_games` | the count the tonight rule reads: each league's games on tonight's slate |
| `PULLS`, `PULLS_ON` | prop pulls per game day, per league |
| `LINES_BY_WEEKDAY`, `LIVE_HOURS` | the three-credit lanes |
| `SEASONS` | when each league plays. Today's real slate always overrides it, and a board that says its season is over (`launch._seasons_over`) ends it early |

## Known limits

* **The tables are a model**, built from the pacer's own arithmetic, not
  from a month of the box's ledger. The report prints each league's daily
  average over the last seven days, so after a week the tables can be
  checked against reality and adjusted.
* **The NFL can go over its plan on a game day.** The priority floor
  (six full pulls with a kickoff inside 24 hours) and the readiness,
  inactives and closing pulls still apply. That's on purpose, since the
  NFL comes first. The real balance absorbs it, and the next plan trims
  the last tier.
* **A sport the plan can't fund at all** (only when tonight's games and
  the NFL's own need take the whole pool, as at the very end of October)
  still gets the
  pacer's old safety net: one sparse pull every 12 hours, if the month can
  afford it.
* **A season ending is read off its board**: baseball's the morning after
  its last game; the NBA, WNBA and college once their board says
  "offseason", which waits for a look back with no games (up to 10 days);
  hockey and the NFL by the season table.
* **A league buys nothing on a night it doesn't play.** That's Ethan's
  rule (2026-10-30), and its cost is a board with no prices between game
  nights: Saturday's NFL board shows Sunday's games unpriced until Sunday
  morning, and a UFC card isn't priced until fight day.
* **Leftover credits in quiet months** (March, with no football) show up
  as "unplanned" in the report. They're Ethan's to spend: more NBA pulls,
  a wider college cap, or nothing.
