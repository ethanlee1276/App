"""WNBA from ESPN — a thin league binding over :mod:`espnhoops`.

The NBA and WNBA publish identical JSON at identical paths under different
league slugs, so the parsers, the fetchers and the day ingest all live in
one module. This file exists to keep ``from engine.sources.wnbaespn import
…`` working and to say, in one place, that the WNBA's binding is the
default one.

Two copies of a box-score parser drift. The first symptom would be one
league quietly missing a stat the other has, on a board that still looks
fine — so there is one copy, and this is a binding rather than a fork.
"""

from __future__ import annotations

from .espnhoops import (          # noqa: F401
    LEAGUES, ROOT, SCOREBOARD, SUMMARY, STAT_MAP,
    parse_scoreboard, parse_summary,
)
from . import espnhoops as _h

LEAGUE = "wnba"


def fetch_scoreboard(date: str, ttl: int = 21600) -> dict:
    return _h.fetch_scoreboard(date, ttl=ttl, league=LEAGUE)


def fetch_summary(game_id: str, ttl: int = 30 * 24 * 3600) -> dict:
    return _h.fetch_summary(game_id, ttl=ttl, league=LEAGUE)


def load_day(date: str, ttl: int = 21600) -> list[dict]:
    return _h.load_day(date, ttl=ttl, league=LEAGUE)


def ingest_day(conn, date: str, scores_only: bool = False) -> dict:
    return _h.ingest_day(conn, date, league=LEAGUE, scores_only=scores_only)


def fetch_schedule(ttl: int = 21600) -> dict:
    return _h.fetch_schedule(ttl=ttl)


def parse_schedule_day(_schedule: dict, date: str) -> list[dict]:
    return _h.parse_schedule_day(_schedule, date, league=LEAGUE)
