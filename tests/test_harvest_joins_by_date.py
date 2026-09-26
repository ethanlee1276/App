"""An NFL harvest is filed by date; the walks can now reach it.

Every closing-line harvest (`odds_history`) is keyed by the calendar
date it was taken. Every walk keyed its lookups by `period` — a date
for baseball and college, a WEEK for the NFL — so an NFL harvest never
joined anything: the calibration fitted on the schedule's consensus,
and `backtest_sharp_anchor`, which has no schedule to fall back on,
priced zero NFL games. Commit 444cbba gave the games table a kickoff
date; `close_for` now tries it first when it is there, and nothing
changes where it is not.

Run directly: `python3 tests/test_harvest_joins_by_date.py`
"""

import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine.gamebacktest import close_for, backtest_sharp_anchor  # noqa: E402


def test_the_games_own_date_is_tried_first_and_only_when_known():
    harvest = {("2026-09-13", "KC", "BUF"): "by date", ("001", "KC", "BUF"): "by week"}
    sched = {(2026, "001", "KC", "BUF"): "schedule"}
    assert close_for(harvest, sched, 2026, "001", "KC", "BUF", date="2026-09-13") == "by date"
    # A datetime is cut to its date; a NULL date changes nothing.
    assert close_for(harvest, sched, 2026, "001", "KC", "BUF", date="2026-09-13T20:20:00") == "by date"
    assert close_for(harvest, sched, 2026, "001", "KC", "BUF", date=None) == "by week"
    assert close_for(harvest, sched, 2026, "001", "KC", "BUF") == "by week"
    # A date the harvest never saw falls through to the week, then the schedule.
    assert close_for(harvest, sched, 2026, "001", "KC", "BUF", date="2026-09-14") == "by week"
    assert close_for({}, sched, 2026, "001", "KC", "BUF", date="2026-09-13") == "schedule"


def _kickoff(wk: int) -> str:
    """Seven days apart from the first of September, as the calendar has it."""
    return str(datetime.date(2026, 9, 1) + datetime.timedelta(days=7 * (wk - 1)))


def _nfl(with_date: bool):
    """Twenty KC-BUF weeks with schedule moneylines at a pick'em, plus a
    harvest for the last week at a very different price — Pinnacle and
    the shopped best — filed under that game's kickoff date."""
    conn = db.connect(":memory:")
    rows = []
    for wk in range(1, 21):
        rows.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}",
                     "game_id": f"g{wk}", "home": "KC", "away": "BUF",
                     "home_score": 27, "away_score": 24, "spread": -3.0, "total": 47.5,
                     "roof": "outdoors", "surface": "grass", "temp": None, "wind": None,
                     "date": _kickoff(wk) if with_date else None,
                     "extra": json.dumps({"ml": [-110, -110]})})
    db.upsert_games(conn, rows)
    last = _kickoff(20)
    for book, h, a in (("Pinnacle", -200, 170), ("best", -150, 140)):
        for team, odds in (("KC", h), ("BUF", a)):
            conn.execute(
                "INSERT INTO odds_history (sport, taken_at, event_id, home, away, player, "
                "market, book, line, over_odds, under_odds) VALUES "
                "('nfl', ?, 'x', 'KC', 'BUF', ?, 'moneyline', ?, NULL, ?, NULL)",
                (f"{last}T23:00:00Z", team, book, odds))
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_the_calibration_walk_reads_the_harvested_close_when_the_date_is_known():
    from engine.gamecal import _moneyline_observations
    conn = _nfl(with_date=True)
    assert conn.execute("SELECT date FROM games WHERE period='020'").fetchone()[0] == _kickoff(20) == "2027-01-12"
    obs = _moneyline_observations(conn, "nfl", min_team_games=1)
    # Nineteen weeks read the schedule's pick'em (market log-odds 0); the
    # last week reads the harvest's −150/+140, which is not a pick'em.
    offsets = [o[1] for o in obs]
    assert len(offsets) == 19, len(offsets)
    assert all(abs(x) < 1e-9 for x in offsets[:-1])
    assert offsets[-1] > 0.1, offsets[-1]


def test_without_a_date_the_walk_is_exactly_what_it_was():
    from engine.gamecal import _moneyline_observations
    conn = _nfl(with_date=False)
    obs = _moneyline_observations(conn, "nfl", min_team_games=1)
    assert len(obs) == 19 and all(abs(o[1]) < 1e-9 for o in obs)


def test_the_sharp_anchor_replay_can_finally_price_an_nfl_game():
    """No schedule fallback exists for it: before the date it priced
    zero NFL games in silence. Pinnacle −200/+170 makes KC 63% fair; the
    shopped best pays −150 on KC, which is +5% EV, so it bets — and KC
    won 27-24, so it cashes."""
    r = backtest_sharp_anchor(_nfl(with_date=True), "nfl")
    assert r.games_priced == 1 and r.n_bets == 1 and r.wins == 1, r.summary()
    r0 = backtest_sharp_anchor(_nfl(with_date=False), "nfl")
    assert r0.games_priced == 0, "a NULL date is the old silence, not an invented join"


def test_every_walk_hands_the_date_over():
    """Every `close_for` call in the three walk modules passes the game's
    date — the definition aside — and each module has at least as many
    calls as it had walks the day this was written (2, 10, 6). A new
    walk written without the date fails here, not on the droplet."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    floors = {"engine/gamecal.py": 2, "engine/gamerank.py": 10, "engine/gamebacktest.py": 6}
    for rel, floor in floors.items():
        src = open(os.path.join(root, rel)).read()
        calls = src.count("close_for(") - src.count("def close_for(")
        passes = src.count('date=row["date"]') + src.count('date=g["date"]')
        assert calls >= floor, (rel, calls, floor)
        assert calls == passes, (rel, calls, passes)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
