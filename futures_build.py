#!/usr/bin/env python3
"""Build the futures board for one sport, or all of them.

    python3 futures_build.py mlb
    python3 futures_build.py all
    python3 futures_build.py all --odds        # one credit per sport, weekly

Its own build, on its own cadence, for one measured reason: a full MLB
season at twenty thousand trials takes 3.6 seconds, and four sports on the
60-second refresh loop would spend fourteen seconds of every minute
re-answering a question whose answer moves over weeks. Futures are the
slowest thing on this site. Once a day is generous.

``--odds`` is the only part that can spend, at one credit per sport, and the
cache TTL is a week so running it daily still only reaches the wire on the
seventh day. Without the flag the board is built entirely from keyless
feeds and whatever prices are already cached.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import db as hist_db                        # noqa: E402
from engine import futuresdata as FD                    # noqa: E402

SPORTS = ("nfl", "mlb", "cfb", "nba")

#: Season-total markets worth publishing per sport — the ones a book posts
#: futures on and our logs already carry. CFB is absent on purpose: there
#: are no college player logs in this database, and inventing a projection
#: from nothing is the one thing a futures page must not do.
SEASON_MARKETS = {
    "mlb": [("home_runs", "Home runs"), ("hits", "Hits"),
            ("total_bases", "Total bases"), ("strikeouts", "Strikeouts (P)")],
    "nfl": [("rush_yds", "Rushing yards"), ("rec_yds", "Receiving yards"),
            ("pass_yds", "Passing yards"), ("receptions", "Receptions")],
    "nba": [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists")],
    "cfb": [],
}

#: How many names per market. A futures page is a shortlist, not a
#: leaderboard — the whole board's season totals is a database dump.
PER_MARKET = 12

#: The two sentences every futures surface inherits. A constant rather than
#: an inline literal so there is exactly one wording to keep honest, and so
#: it can be asserted on as a value instead of grepped for in source that
#: happens to wrap it across three string literals.
DOCTRINE = (
    "Every number here comes from simulating the rest of the season twenty "
    "thousand times, not from reading a price. Futures are the market a book "
    "posts earliest and revisits least, which is where the edge argument "
    "comes from — and the market least likely to hold a sure thing, because "
    "the horizon is months and the stake is tied up for all of it.")

OUT = ROOT / "web" / "data"


def build(sport: str, conn, trials: int = 20000, live_odds: bool = False) -> dict:
    out = FD.project(conn, sport, trials=trials, live_odds=live_odds)
    left = out.pop("games_left", {}) or {}
    markets = []
    for market, label in SEASON_MARKETS.get(sport, []):
        try:
            rows = FD.player_season_totals(conn, sport, market,
                                           season=out.get("season"),
                                           team_games_left=left,
                                           limit=PER_MARKET)
        except Exception:                              # noqa: BLE001
            rows = []
        if rows:
            markets.append({"market": market, "label": label, "players": rows})
    out["season_totals"] = markets
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    # Said once, in DOCTRINE, so every surface that renders this inherits
    # it rather than each one inventing its own wording.
    out["doctrine"] = DOCTRINE
    return out


def main(argv: list[str]) -> None:
    args = [a for a in argv[1:] if not a.startswith("--")]
    live = "--odds" in argv
    trials = 20000
    for a in argv[1:]:
        if a.startswith("--trials="):
            trials = int(a.split("=", 1)[1])
    want = SPORTS if (not args or args[0] == "all") else [args[0]]
    conn = hist_db.connect()
    OUT.mkdir(parents=True, exist_ok=True)
    for sport in want:
        if sport not in SPORTS:
            print(f"  ✗ {sport}: not a futures sport")
            continue
        try:
            data = build(sport, conn, trials=trials, live_odds=live)
        except Exception as exc:                       # noqa: BLE001
            print(f"  ✗ {sport.upper()}: {exc}")
            continue
        path = OUT / f"futures_{sport}.json"
        path.write_text(json.dumps(data, indent=2))
        n = len(data.get("teams") or [])
        priced = data.get("priced", 0)
        note = data.get("note") or ""
        print(f"  {sport.upper():>4}: {n} team(s), {data.get('fixtures_remaining', 0)} "
              f"game(s) left, {priced} priced"
              + (f"  — {note}" if note else ""))
    conn.close()


if __name__ == "__main__":
    main(sys.argv)
