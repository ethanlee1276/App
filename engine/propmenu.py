"""What the books posted for each game a league's prop pulls bought.

Written 2026-11-14 for college basketball. Its board priced no player props
for two days, and telling "we did not buy" from "we bought and the books had
posted nothing" took a command on the box (runbook PL): the pacer's
decisions are private, and the board's own odds line says only how many
props matched. Ethan's run showed the second: Saturday's 7am pull bought
five games and the books had posted player markets on one of them, ladders
only, where Friday's 6pm pull found them on all five.

This reads the paid pulls' own cached payloads (the files
`oddsapi.fetch_event_odds` writes) and says, per game, how many books
answered, how many standard player markets and how many ladders they
carried, and when the pull was made: a fact about the books' menus, never a
price, so the public board can carry it. A week of these says whether a
league's morning pull buys anything.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import time

#: A pull older than this is about another day's games.
MAX_AGE_H = 20
#: A game whose tip is this far past is over; its menu says nothing now.
PAST_TIP_H = 6
#: At most this many games on the board.
MAX_ROWS = 12


def _cache_dir() -> str:
    from .sources.fetch import CACHE_DIR
    return str(CACHE_DIR)


def _tip(raw) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def census(sport: str, now: float | None = None, cache_dir: str | None = None) -> list[dict]:
    """One row per game bought in the last MAX_AGE_H hours whose tip is not
    long past, newest pull per game, soonest tip first."""
    now = time.time() if now is None else float(now)
    folder = cache_dir or _cache_dir()
    newest: dict = {}
    for path in glob.glob(os.path.join(folder, f"odds_event_{sport}_*.json")):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if now - mtime > MAX_AGE_H * 3600:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        tip = _tip(data.get("commence_time"))
        if tip is not None and tip.timestamp() < now - PAST_TIP_H * 3600:
            continue
        key = (data.get("away_team") or "", data.get("home_team") or "")
        if key in newest and newest[key][0] >= mtime:
            continue
        newest[key] = (mtime, data, tip)
    rows = []
    for (away, home), (mtime, data, tip) in newest.items():
        books = data.get("bookmakers") or []
        keys = {str(m.get("key") or "") for b in books for m in (b.get("markets") or [])}
        player = {k for k in keys if k.startswith(("player_", "batter_", "pitcher_"))}
        ladders = {k for k in player if k.endswith("_alternate")}
        mains = player - ladders
        said = ("player props and ladders" if mains and ladders else
                "player props" if mains else
                "ladders only" if ladders else "no player markets")
        rows.append({"game": f"{away} @ {home}",
                     "tip": tip.strftime("%Y-%m-%dT%H:%MZ") if tip else None,
                     "pulled": _dt.datetime.fromtimestamp(mtime, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                     "books": len(books), "player_markets": len(mains), "ladders": len(ladders),
                     "posted": said})
    rows.sort(key=lambda r: (r["tip"] or "9999", r["game"]))
    return rows[:MAX_ROWS]


def summary(rows: list[dict]) -> str:
    """One line: how many bought games carried what."""
    if not rows:
        return "no paid prop pull in the last day"
    with_props = sum(1 for r in rows if r["player_markets"])
    ladders = sum(1 for r in rows if r["ladders"] and not r["player_markets"])
    return (f"{len(rows)} game(s) bought: {with_props} with player props, {ladders} with ladders only, "
            f"{len(rows) - with_props - ladders} with none")
