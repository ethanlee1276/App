"""A college player's team, off the roster file already on the box.

Ethan, 2026-09-14: five college rows open after the absent-player rule —
first appearances with no earlier stat row, journaled before the bet
carried its team. The cached cfbfastR roster names their schools; the
settler reads it, never the network.

Run directly: `python3 tests/test_cfbroster.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger, cfbroster                       # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()      # noqa: E731
BET_DAY = D(-2)
SEASON = TODAY.year if TODAY.month >= 8 else TODAY.year - 1


def _roster_dir(rows):
    d = Path(tempfile.mkdtemp())
    with open(d / f"cfb_rosters_{SEASON}.csv", "w", encoding="utf-8") as fh:
        fh.write("athlete_id,first_name,last_name,team,position\n")
        for r in rows:
            fh.write(",".join(r) + "\n")
    return d


def _game(H, period, game_id, home, away, home_name, away_name, final=True):
    H.execute(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, "
        "home_score, away_score, extra) VALUES ('cfb', ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
        (SEASON, period, game_id, home, away, 24.0 if final else None,
         20.0 if final else None,
         json.dumps({"home_name": home_name, "away_name": away_name})))
    H.commit()


def test_the_roster_file_names_the_school_and_the_schedule_names_the_code():
    d = _roster_dir([("1", "DJ", "Miller", "Central Michigan", "WR"),
                     ("2", "Derek", "Meadows", "Notre Dame", "WR"),
                     ("3", "Same", "Name", "Iowa", "RB"),
                     ("4", "Same", "Name", "Iowa State", "RB")])
    schools = cfbroster.roster_schools(SEASON, cache_dir=d)
    assert schools["dj miller"] == "Central Michigan"
    assert "same name" not in schools, "a name two schools share is nobody's"
    H = db.connect(":memory:")
    _game(H, D(-1), "COLG@CMU", "CMU", "COLG", "Central Michigan", "Colgate")
    assert cfbroster.school_key(H, SEASON, "Central Michigan") == "CMU"
    assert cfbroster.school_key(H, SEASON, "Colgate") == "COLG"
    assert cfbroster.school_key(H, SEASON, "Notre Dame") is None    # not on this schedule
    assert cfbroster.team_of(H, "DJ Miller", SEASON, cache_dir=d) == "CMU"
    assert cfbroster.team_of(H, "Derek Meadows", SEASON, cache_dir=d) is None
    assert cfbroster.team_of(H, "Nobody Here", SEASON, cache_dir=d) is None


def test_no_cached_file_means_no_team_and_no_network():
    d = Path(tempfile.mkdtemp())
    assert cfbroster.roster_schools(SEASON, cache_dir=d) == {}
    assert cfbroster.team_of(db.connect(":memory:"), "DJ Miller", SEASON, cache_dir=d) is None


def test_a_first_appearance_settles_through_the_roster():
    """The five 09-12 rows: no history, no stamp, and the roster file on
    the box knows the school. The absent-player rule reads it third and
    voids the row off the team's final box, like any other absence."""
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, 'cfb', ?, ?, 'DJ Miller', 'receptions', 'OVER', 1.5, -110, 1, 10, 'open', 'likely')",
        (f"{BET_DAY}T12:00:00", BET_DAY, BET_DAY))
    L.commit()
    _game(H, D(-1), "COLG@CMU", "CMU", "COLG", "Central Michigan", "Colgate")
    db.upsert_player_logs(H, [{"sport": "cfb", "season": SEASON, "period": D(-1),
                               "game_id": "COLG@CMU-box", "player": "Some Chippewa",
                               "team": "CMU", "opponent": "COLG", "position": "WR",
                               "home": 1, "market": "rec_yds", "value": 40.0}])
    H.commit()
    keep = cfbroster.CACHE_DIR
    try:
        # No roster on the box: nothing to read a team off, stays open.
        cfbroster.CACHE_DIR = Path(tempfile.mkdtemp())
        ledger.settle_from_history(L, H)
        assert L.execute("SELECT status FROM bets").fetchone()[0] == "open"
        # The roster names his school: the verdict finds the game.
        cfbroster.CACHE_DIR = _roster_dir([("1", "DJ", "Miller", "Central Michigan", "WR")])
        assert ledger.settle_from_history(L, H) == 1
        row = L.execute("SELECT status, why_note FROM bets").fetchone()
        assert row[0] == "void" and "Did not play" in (row[1] or ""), tuple(row)
    finally:
        cfbroster.CACHE_DIR = keep


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
