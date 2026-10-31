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
| Open-Meteo | Game-day weather | Free |
| Polymarket, Kalshi public APIs | The prediction desk | Free |

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
that compares the two sources game by game, off until there is a key. It is
not built yet:

- **The API's documentation could not be read from the build session.**
  `docs.balldontlie.io` does not resolve there (it is outside the session's
  allowed network domains), and a client written against an API nobody has
  read would be a guess. Allowing that domain in the session's network
  settings, or a key on the box, is the first step.
- **Which sport first.** The paper's own logic says start where a paid
  product leans hardest on an unofficial feed: the live scores and box
  scores that grade bets and drive the Live tab (ESPN, every league but
  MLB), then MLB.
- **The latency test decides the switch.** With both feeds running, the
  logger records when each first shows a score change, and the swap
  happens only for a league where the licensed feed is as fast or faster.

Until then, nothing changes: the free feeds keep the site running, and
this page is the record of the risk.
