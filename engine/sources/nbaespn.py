"""The NBA from ESPN — a thin league binding over :mod:`espnhoops`, as
:mod:`wnbaespn` is the WNBA's.

WHY (2026-10-14, the evening Ethan got home): the league's own CDN
(`nbadata`, cdn.nba.com) answers the box with 403 Forbidden, for every
file and every User-Agent, while ESPN answers 200:

    403  staticData/scheduleLeagueV2.json        (three agents, same answer)
    403  liveData/playbyplay/playbyplay_….json
    200  site.api.espn.com …/basketball/nba/scoreboard

So the NBA board had read "unreachable" with no games, and the nightly
results ingest that settles NBA picks had nothing to read, six days before
opening night. The history backfill (`ingest.py nba`) has ridden ESPN all
along; the board's schedule and the nightly results now do too.

THE CLUBS ARE THE LEAGUE'S OWN CODES. ESPN spells six of them its own way
(GS, NY, NO, SA, UTAH, WSH); the odds feed, the club rosters and the board
key on the league's (GSW, NYK, NOP, SAS, UTA, WAS). `divisions.canonical`
holds that table, and the schedule rows here carry the league's codes so
tonight's games meet their prices and their rosters.
"""

from __future__ import annotations

from .. import divisions
from . import espnhoops as _h

LEAGUE = "nba"


def _club(team: str) -> str:
    return divisions.canonical(LEAGUE, team)


def fetch_schedule(ttl: int = 21600) -> dict:
    return _h.fetch_schedule(ttl=ttl)


def parse_schedule_day(_schedule: dict, date: str) -> list[dict]:
    """One day's games in the shape `nba_build` reads (`espnhoops`), the
    clubs in the league's codes, the preseason marked so the build drops
    it before anything is priced."""
    rows = _h.parse_schedule_day(_schedule, date, league=LEAGUE)
    for g in rows:
        g["home"], g["away"] = _club(g["home"]), _club(g["away"])
    return rows


def ingest_day(conn, date: str, scores_only: bool = False) -> dict:
    """One date's finals and player logs (the nightly results, the settle
    pass), as the history backfill stores them."""
    return _h.ingest_day(conn, date, league=LEAGUE, scores_only=scores_only)
