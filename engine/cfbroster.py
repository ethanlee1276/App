"""A college player's team, off the roster file already on the box.

Ethan, 2026-09-14, five college rows still open after the absent-player
rule shipped: DJ Miller, Derek Meadows, Gabe Burkle, Kaleb Edwards, Zack
Marshall — first appearances, a freshman or a walk-on with no earlier
stat row to read a team off, journaled before the bet carried its team.
Without a team the settler cannot find the game, and a bet that cannot
find its game sits open forever.

The team is on the box. The college ingest pulls cfbfastR's roster file
every season (`engine.sources.cfbstats.fetch_rosters`, a month-deep
cache) for positions and faces, and that file names every player's
school. This reads the cached copy — NEVER the network; the settler is
not the place to start a download — and resolves the school to the code
the games table keys on through the same schedule join the stat ingest
uses (`ingest.cfb_games_for` + `cfbstats._side_of`).

`CACHE_DIR` is module-level so a test points it at a temp dir; the suite
must never read the box it runs on.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .sources.fetch import CACHE_DIR as _FETCH_CACHE
from .sources.oddsapi import normalize_name

CACHE_DIR: Path = Path(_FETCH_CACHE)


def roster_schools(season: int, cache_dir=None) -> dict:
    """``{normalized player name: school name}`` from the cached roster
    file for ``season``; empty when there is no cached file."""
    path = Path(cache_dir or CACHE_DIR) / f"cfb_rosters_{int(season)}.csv"
    if not path.is_file():
        return {}
    out: dict = {}
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                first = (r.get("first_name") or "").strip()
                last = (r.get("last_name") or "").strip()
                school = (r.get("team") or r.get("school") or "").strip()
                name = normalize_name(f"{first} {last}".strip())
                if not name or not school or school.upper() in ("NA", "NULL"):
                    continue
                # A name two schools share is nobody's: leave it out
                # rather than guess.
                if name in out and out[name] != school:
                    out[name] = ""
                else:
                    out.setdefault(name, school)
    except OSError:
        return {}
    return {k: v for k, v in out.items() if v}


def school_key(hist_conn, season: int, school: str) -> str | None:
    """The games-table code for a school name, through the season's
    schedule rows — the same join the stat ingest resolves through."""
    if not school:
        return None
    from .ingest import cfb_games_for
    from .sources.cfbstats import _side_of
    for g in cfb_games_for(hist_conn, int(season)).values():
        side = _side_of(g, school)
        if side and side[0]:
            return side[0]
    return None


def team_of(hist_conn, player: str, season: int, cache_dir=None) -> str | None:
    """The player's team code for ``season``, or None when the roster
    file is absent, does not carry him, or names a school the schedule
    has not seen."""
    school = roster_schools(season, cache_dir).get(normalize_name(player or ""))
    return school_key(hist_conn, season, school) if school else None
