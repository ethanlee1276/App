"""Which games a man's minutes base is read from at a season's start —
chosen by measurement, every day.

Ethan, 2026-10-29, after the minutes fix: "Ok keep going" (the ask before
it: "calibrate that more ... think like a pro sports better").

THE QUESTION. The minutes base (`engine/nba/minutes.base_minutes`) is a
weighted average of his last twenty games. A week into a season most of
them are LAST season's final weeks: a lottery club's April, starters on
short minutes; a contender's playoffs, starters on long ones. A pro reads a
man's role off this season's games once he has a few, because rotations
change over a summer. The same pro does not guess which reads better: it
is measured here, every day, on the games this season has already played.

THE MEASUREMENT (`measure`). Every game this season by a man with
MIN_PRIOR earlier games this season: his minutes against the base read
before it, two ways, through the board's own arithmetic (`role_minutes`
then `base_minutes`): the twenty-game window the board reads, and this
season's games alone. For each, the mean absolute error in minutes and
the median of minutes over base (over 1.00, the base runs light).

THE RULE, written before any run (`choose`): this season's games alone are
used only once at least MIN_GAMES games are scored and their error is
lower by at least MARGIN minutes. Otherwise the twenty-game window stays,
as the board always read it. A season twenty games old has the same games
in both windows, so nothing can differ after that.

THE CACHE. One measurement a day per league (`window_for`, kept under
data/models), so a build every few minutes reads it instead of re-reading
two seasons of box scores.

Standard library only.
"""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict

STORE = "nba_minutes_window.json"
#: Earlier games this season a man needs before his game is scored, and
#: before this season's games alone can be his base (the base's own floor).
MIN_PRIOR = 3
#: Scored games before the rule may choose this season's games alone.
MIN_GAMES = 150
#: How much lower, in minutes of mean absolute error, this season's games
#: alone have to read before they are used.
MARGIN = 0.25
#: How many days of measurements the store keeps per league.
KEEP_DAYS = 7


def measure(conn, sport: str, season: int, min_prior: int = MIN_PRIOR) -> dict:
    """``{"n", "mae_twenty", "mae_season", "ratio_twenty", "ratio_season"}``
    over every game of ``season`` with ``min_prior`` earlier ones in it;
    ``{"n": k}`` alone when there is nothing to score."""
    from .minutes import base_minutes, role_minutes
    games: dict = defaultdict(list)                     # player -> [(season, minutes)], oldest first
    for r in conn.execute("SELECT player, season, value FROM player_game_logs WHERE sport=? AND market='min' "
                          "AND season IN (?, ?) ORDER BY period", (sport, season, season - 1)):
        games[r[0]].append((int(r[1]), float(r[2] or 0.0)))
    err_all, err_own, rat_all, rat_own = [], [], [], []
    for rows in games.values():
        for i, (sea, actual) in enumerate(rows):
            if sea != season or actual <= 0:
                continue
            before = [m for _s, m in reversed(rows[:i])]
            own = [m for s_, m in reversed(rows[:i]) if s_ == season][:20]
            if len(own) < min_prior:
                continue
            b_all = base_minutes(role_minutes(before[:20])[0])
            b_own = base_minutes(role_minutes(own)[0])
            if not (b_all and b_own):
                continue
            err_all.append(abs(actual - b_all))
            err_own.append(abs(actual - b_own))
            rat_all.append(actual / b_all)
            rat_own.append(actual / b_own)
    out: dict = {"n": len(err_all)}
    if err_all:
        out.update(mae_twenty=round(statistics.fmean(err_all), 3), mae_season=round(statistics.fmean(err_own), 3),
                   ratio_twenty=round(statistics.median(rat_all), 4),
                   ratio_season=round(statistics.median(rat_own), 4))
    return out


def choose(m: dict) -> str:
    """"season" when this season's games alone have earned it, else "twenty"."""
    try:
        if int(m.get("n") or 0) >= MIN_GAMES and float(m["mae_season"]) <= float(m["mae_twenty"]) - MARGIN:
            return "season"
    except (KeyError, TypeError, ValueError):
        pass
    return "twenty"


def _path() -> str:
    from .. import modelstate
    return modelstate.path(STORE)


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def window_for(conn, sport: str, date: str) -> dict:
    """Today's measurement for ``sport`` with its ``window`` ("season" or
    "twenty"), measured once a day and kept. A store that cannot be written
    still answers; a history that cannot be read answers "twenty"."""
    from ..seasons import season_of
    key = f"{str(sport).lower()}:{date}"
    data = _load()
    if isinstance(data.get(key), dict) and data[key].get("window"):
        return data[key]
    season = season_of(sport, date)
    try:
        m = measure(conn, sport, season)
    except Exception as exc:                              # noqa: BLE001 — no history, the board's window
        return {"n": 0, "window": "twenty", "season": season, "date": date, "why": type(exc).__name__}
    m.update(window=choose(m), season=season, date=date)
    keep = sorted((k for k in data if k.startswith(f"{str(sport).lower()}:")), reverse=True)[:KEEP_DAYS - 1]
    data = {k: v for k, v in data.items() if not k.startswith(f"{str(sport).lower()}:") or k in keep}
    data[key] = m
    try:
        path = _path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass
    return m


def this_season(dates, sport: str, season: int) -> int:
    """How many of his games, newest first, lead the list inside ``season``."""
    from ..seasons import season_of
    n = 0
    for d in dates or []:
        try:
            if season_of(sport, str(d)[:10]) != season:
                break
        except (ValueError, TypeError):
            break
        n += 1
    return n
