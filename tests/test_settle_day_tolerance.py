"""A college stat line filed on the UTC next day still grades the bet on it.

Ethan, 2026-09-14: eight college props and three college game rows open
for two to nine days, beside their own stat lines. A college games row's
period is its UTC date and the bet's date is the Eastern game day, so a
Saturday-night kickoff files its box score one day AFTER the prop. The
settler's neighbour-day rule was built for baseball, where the drift
runs the other way, and only ever looked one day BACK.

College now looks forward first, then back, and refuses when both days
answer; every other league keeps the single day-before read it had. The
game markets get the same day-either-side lookup, which is the
Hawaii-UNLV three.

Run directly: `python3 tests/test_settle_day_tolerance.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger                                  # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()      # noqa: E731
BET_DAY = D(-2)          # a Saturday two days back: never inside the strict window


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _bet(L, sport, date, player, market="rec_yds", line=60.5, side="OVER",
         game_day="", category="main"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, -110, 1, 10, 'open', ?)",
        (f"{date}T12:00:00", sport, date, game_day or date, player, market, side, line, category))
    L.commit()
    return L.execute("SELECT id FROM bets ORDER BY id DESC LIMIT 1").fetchone()[0]


def _game(H, sport, season, period, game_id, home, away, date=None, final=True, extra=None):
    H.execute(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, "
        "home_score, away_score, extra) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sport, season, period, game_id, date, home, away,
         24.0 if final else None, 20.0 if final else None,
         json.dumps(extra) if extra else None))
    H.commit()


def _log(H, sport, season, period, game_id, player, team, market, value, opp="OPP"):
    db.upsert_player_logs(H, [{"sport": sport, "season": season, "period": period,
                               "game_id": game_id, "player": player, "team": team,
                               "opponent": opp, "position": "WR", "home": 1,
                               "market": market, "value": float(value)}])
    H.commit()


def _status(L, bid):
    r = L.execute("SELECT status, actual, why_note FROM bets WHERE id=?", (bid,)).fetchone()
    return r["status"], r["actual"], r["why_note"]


def test_a_college_prop_grades_off_the_next_days_box_row():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "Night Receiver", line=19.5)
    _game(H, "cfb", 2026, D(-1), "401555", "HOME", "AWAY")            # filed the UTC next day
    _log(H, "cfb", 2026, D(-1), "401555-box", "Night Receiver", "HOME", "rec_yds", 44)
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[:2] == ("won", 44.0)


def test_both_college_neighbours_answering_is_a_coin_flip_and_stays_open():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "Twice Logged", line=19.5)
    _game(H, "cfb", 2026, D(-1), "401555", "HOME", "AWAY")
    _game(H, "cfb", 2026, D(-3), "401554", "HOME", "AWAY")
    _log(H, "cfb", 2026, D(-1), "401555-box", "Twice Logged", "HOME", "rec_yds", 44)
    _log(H, "cfb", 2026, D(-3), "401554-box", "Twice Logged", "HOME", "rec_yds", 10)
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


def test_baseball_keeps_its_day_before_read_and_never_reaches_forward():
    L, H = _world()
    bid = _bet(L, "mlb", BET_DAY, "Late Slugger", market="hits", line=0.5)
    _game(H, "mlb", 2026, D(-3), "g1", "NYY", "BOS")
    _log(H, "mlb", 2026, D(-3), "g1", "Late Slugger", "NYY", "hits", 2)
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[0] == "won"
    # And a row only on the day AFTER is baseball's other game, not this one.
    L2, H2 = _world()
    bid2 = _bet(L2, "mlb", BET_DAY, "Late Slugger", market="hits", line=0.5)
    _game(H2, "mlb", 2026, D(-1), "g2", "NYY", "BOS")
    _log(H2, "mlb", 2026, D(-1), "g2", "Late Slugger", "NYY", "hits", 2)
    ledger.settle_from_history(L2, H2)
    assert _status(L2, bid2)[0] == "open"


def test_a_college_game_row_filed_on_the_next_day_settles_the_total():
    """The Hawaii-UNLV three: spread and total rows dated 09-05 ET, the
    games row filed 09-06."""
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "AWAY@HOME", market="total", line=40.5)
    _game(H, "cfb", 2026, D(-1), "AWAY@HOME", "HOME", "AWAY")        # 24-20 = 44, over
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[0] == "won"


def test_a_college_game_row_two_days_off_is_not_this_game():
    L, H = _world()
    bid = _bet(L, "cfb", BET_DAY, "AWAY@HOME", market="total", line=40.5)
    _game(H, "cfb", 2026, D(-4), "AWAY@HOME", "HOME", "AWAY")
    ledger.settle_from_history(L, H)
    assert _status(L, bid)[0] == "open"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
