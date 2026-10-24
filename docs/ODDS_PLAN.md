# The odds plan: 100k credits a month, NFL first

Ethan, 2026-10-21: *"we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority"*.

The code is `engine/oddsplan.py`. The launcher reads it for every paid odds
pull (`launch._budget_share`). On the box, this prints today's plan next to
what each league has actually spent:

    cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan

## The rule

1. **Held back first.** The reserve (500), the closing-line harvest's daily
   cap (400 a day for every day left) and a 5% buffer. The plan never
   spends these.
2. **Every league in season is owed what its normal cadence costs** for the
   rest of the month. The NFL's share is funded first, in full. College is
   second. Every other league in season (NBA, NHL, MLB, UFC, WNBA) then
   splits what's left **in proportion to what it needs**, so they all get
   the same percentage. A short month trims each of them a little instead
   of shutting the last one off.
3. **Headroom only once every league is fully funded.** The NFL gets up to
   50% extra first. Then college and the rest get up to 25% each, for extra
   pulls on a big news day.
4. **Today's ceiling** for each league is today's need times the share of
   its month the plan could fund. The pacer can't spend more than that on a
   league's ordinary pulls, but closing-line, readiness and inactives pulls
   still go through when needed.

It's recomputed from the real balance every cycle, so it corrects itself.
If a league overspends, the pool shrinks and the next plan trims the last
tier, never the NFL. Credits nobody spent (a quiet night, the harvest using
less than 400) become extra room for the days after.

## What November looks like at 100,000

| | need (rest of month) | planned | fill |
|---|---:|---:|---:|
| NFL | 42,020 | 42,020 | 100% |
| College | 13,940 | 13,940 | 100% |
| NBA | 19,398 | 16,667 | 86% |
| NHL | 10,476 | 9,001 | 86% |
| MLB (World Series to Nov 4) | 496 | 426 | 86% |
| UFC | 518 | 445 | 86% |
| WNBA | off-season | 0 | |
| Held back: closing lines 12,000 · buffer 5,000 · reserve 500 | | | |

All target cadences together come to about 104k for November, a bit more
than one plan buys. So football is funded in full and everyone else runs at
86% of their target. As the month goes on and the buffer and unspent
credits come back, that fill rises. A month where every league spends its
full ceiling every day still ends above the reserve; that's tested in
`tests/test_the_odds_plan.py`.

## What a league's day buys (the targets)

Credits by day, Monday to Sunday, on a typical November week. These are the
box's days, which run on UTC, so each day starts at 8pm Eastern.

| | Mon | Tue | Wed | Thu | Fri | Sat | Sun | week |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NFL | 600 | 500 | 500 | 2,000 | 600 | 1,780 | 3,500 | 9,480 |
| College | 228 | 328 | 328 | 356 | 512 | 1,586 | 72 | 3,410 |
| NBA | 639 | 582 | 810 | 468 | 753 | 639 | 639 | 4,530 |
| NHL | 234 | 450 | 270 | 486 | 270 | 558 | 234 | 2,502 |
| UFC | 14 | 14 | 14 | 14 | 14 | 56 | 0 | 126 |

* **NFL.** Sunday: the four windows (7am, noon, 3pm, 6pm ET), plus a
  readiness pull and an inactives pull before each wave, and game lines
  every 15 minutes through the games. Thursday and Monday: the priority
  floor (six pulls on a day with a kickoff inside 24 hours), narrowing to
  that night's game once it's six hours out. Other days: one pull of the
  week's board, with hourly game lines.
* **College.** Eight prop pulls on Saturday, two on Thursday and Friday,
  four on weekday nights, at 13 credits a game for up to 12 games a pull.
  Game lines run every day of the season, hourly when no game is close and
  every 15 minutes in the pre-game window and through the games.
* **NBA and NHL.** Three prop pulls on a game day: noon, the pre-game run
  and 6pm ET. The NBA adds its three-credit game-lines lane until the last
  tip. Both add the live line while games are on. An 11-game NBA night is
  about 870 credits; a 9-game NHL night is about 410.
* **MLB.** Four pulls on a World Series game day, about 124 credits.
* **UFC.** One credit a fight. One pull a day, four on fight day.

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
| `TIERS` | who's funded first: `("nfl",), ("cfb",), (everyone else)` |
| `NFL_HEADROOM`, `HEADROOM` | 50% and 25% extra, only after every target is funded |
| `BUFFER_SHARE` | 5% of the pool, never planned |
| `NFL_REGULAR`, `NFL_PLAYOFFS` | the NFL's day, Monday to Sunday |
| `PULLS`, `PULLS_ON` | prop pulls per game day, per league |
| `LINES_BY_WEEKDAY`, `LIVE_HOURS` | the three-credit lanes |
| `SEASONS` | when each league plays. Today's real slate always overrides it |

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
* **A league the plan can't fund at all** (only in a very tight month)
  still gets the pacer's old safety net: one sparse pull every 12 hours,
  if the month can afford it.
* **Leftover credits in quiet months** (March, with no football) show up
  as "unplanned" in the report. They're Ethan's to spend: more NBA pulls,
  a wider college cap, or nothing.
