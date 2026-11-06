# Where the data comes from, and what owning it would cost

Ethan's first research paper (2026-10-29, "Making Qellys Book a Daily
Habit") said it plainly: "ESPN's and MLB's free endpoints are unofficial or
non-commercial and shouldn't carry a paid product." This page lists what
leans on them today, what the paper priced as the alternatives, and what
waits on a decision.

## What reads which source today

Counted from the hosts the engine fetches (`engine/` and `engine/sources/`),
2026-10-29:

| Source | What it feeds | Paid? |
| --- | --- | --- |
| ESPN's site API (`site.api.espn.com`, `site.web.api.espn.com`, `sports.core.api.espn.com`) | Scoreboards and live scores, play-by-play, box scores, injuries and rosters for the NFL, college football, NBA, WNBA and NHL; the UFC card | No: unofficial |
| MLB's Stats API (`statsapi.mlb.com`) and Baseball Savant | Baseball schedules, live games, box scores, pitch and batted-ball data | No: MLB's own terms |
| The NHL's API (`api-web.nhle.com`, `api.nhle.com`) | Hockey play-by-play, shifts, starters | No: unofficial |
| `cdn.nba.com`, `cdn.wnba.com` | Basketball schedules and box scores | No: unofficial |
| nflverse (GitHub releases) | NFL play-by-play, participation, schedules | Free and open |
| collegefootballdata.com | College football play-by-play and stats | Free tier, keyed |
| The Odds API | Every price on the boards | Yes, keyed (`ODDS_API_KEY`) |
| Open-Meteo | Game-day weather | Free, for non-commercial use by its own terms (docs/LAUNCH.md 0.2; RUN_NEXT item 9) |
| Polymarket, Kalshi public APIs | The prediction desk | Free |

### Research only: not read by the site

| Source | What it was used for | Paid? |
| --- | --- | --- |
| `stats.nba.com` player tracking (`leaguedashptstats`: passing, possessions, drives, rebounding, one game day a request) | Whether potential assists, touches and rebound chances make the NBA board's number better, measured held out (`nbatrackcheck.py`, docs/NBA_LAB.md, 2026-11-05). Fetched on the box into `data/research/nba_tracking.db` by `engine/nba/tracking` (runbook KR); nothing the site serves or builds reads it. **Parked, 2026-11-06:** the league refused the box's first request (403, at once), so nothing was fetched; nothing tries again another way NBA.com's terms allow personal, non-commercial use, so a board that read it would be the owner's call, made only if a market measures | Free, the league's own; terms limit commercial use |
| `shufinskiy/nba_data` on GitHub (the `cdnnba_2024` and `cdnnba_2025` files) | The NBA lab (docs/NBA_LAB.md, 2026-11-04): two full seasons of the league's own play-by-play, in the format the build already reads from `cdn.nba.com`, to measure ideas on games the model never saw. Downloaded once into a scratch folder; nothing on the box reads it and nothing in the repo carries it | Free, public |

## The alternatives the paper priced

- **BALLDONTLIE**: NBA, WNBA, NFL, MLB, college football and MMA, with
  play-by-play, live box scores, odds and props. $39.99 a sport a month for
  the full tier, or $299.99 a month for every sport with webhooks.
- **The Odds API**: $30 to $249 a month (what the site already pays for).
- **Sportradar**: no public price list; third-party estimates run from
  about $1,250 to over $10,000 a month.

(The paper's figures; not re-checked here.)

## What waits, and on what

The paper's data item was a BALLDONTLIE client and a feed-latency logger
that compares the two sources game by game, off until there is a key.
**Built 2026-11-05, off until a key** (step KP in docs/WHEN_YOU_ARE_HOME.md):

- **The client** (`engine/sources/balldontlie.py`) follows BALLDONTLIE's
  own Python SDK (PyPI `balldontlie` 0.1.6, MIT), read line by line,
  because `docs.balldontlie.io` is outside the build session's network.
  The key goes bare in `Authorization`, lists repeat as `name[]`, pages
  run by cursor, and the games endpoint gives each game's status, period,
  clock and score for the NBA, the NFL and MLB. The WNBA, college football
  and MMA the paper listed are not in the SDK, so they are not in the
  client. `python3 -m engine.sources.balldontlie --probe` says what a
  key's plan answers, without printing the key.
- **The logger** (`engine/feedlatency.py`) runs on its own thread, started
  only when `BALLDONTLIE_API_KEY` is set. While an NBA or NFL game is on
  in ESPN's scoreboard, each tick reads that scoreboard (the copy the
  score loop already fetched, so ESPN is asked no more often) and
  BALLDONTLIE's games for the same dates, one request a league, and writes
  down the first time each feed shows each new score
  (`data/cache/feedlatency/`, 60 days kept). The report compares the
  middle of each feed's reading gap, so a feed read more often is not
  credited with being faster. It paces itself to the plan's own limit,
  read off every answer: the key on the box since 5 November is the free
  plan, 5 requests a minute, so it reads every 15 seconds with one league
  on (the games endpoint is in the free plan; the live box scores are
  not). MLB's live scores come from MLB's own feed,
  not ESPN's, and its season is over, so it waits.
- **The latency test decides the switch.** `python3 -m engine.feedlatency`
  gives each league's verdict after 200 score changes both feeds showed:
  `BALLDONTLIE as fast or faster ... a switch candidate`, or `ESPN faster
  by N s ... keep ESPN`. Nothing on the site reads the licensed feed yet;
  moving a league onto it is a separate change, made only on that verdict.
- **Which sport first** stays the paper's: the live scores and box scores
  that grade bets and drive the Live tab (ESPN, every league but MLB),
  then MLB.

Until there is a key, nothing changes: the free feeds keep the site
running, and this page is the record of the risk.
