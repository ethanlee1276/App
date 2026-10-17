"""A postponed MLB game's picks void on the settle clock, not by hand.

Audit 2026-09-30, O4 / E15 (roadmap #44). `--void-unplayed --apply` was
the only way a pick on a postponed, cancelled or suspended MLB game left
the open list, so a rainout kept picks open until somebody ran it — nine
from 2026-09-22 were still open a week later (task #183). The settle pass
now voids them itself, through the same finder (`unplayed_bets`), and
every void lands in the append-only audit table under its own reason.

Two guards keep it from voiding what could still grade:
  * MLB only — the C/D/T state rules behind `never_resolving_game` are
    the baseball ingest's; other leagues keep the manual command.
  * three days old — a suspended game resumed inside that window grades
    normally; past it the pick is not waiting on anything.

Run directly: `python3 tests/test_a_postponed_mlb_game_voids_itself.py`
"""

import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger, maintenance                        # noqa: E402

TODAY = dt.date(2026, 9, 30)


def _day(n):
    return (TODAY - dt.timedelta(days=n)).isoformat()


def _world(sport="mlb", age=8):
    """One unplayed CLE@CIN among scored games, and a CIN hitter logged the
    day before (his last real game)."""
    day = _day(age)
    hconn = db.connect(":memory:")
    lconn = ledger.connect(":memory:")
    db.upsert_games(hconn, [
        {"sport": sport, "season": 2026, "period": day, "game_id": "CLE@CIN",
         "home": "CIN", "away": "CLE", "home_score": None, "away_score": None},
        {"sport": sport, "season": 2026, "period": day, "game_id": "NYY@CWS",
         "home": "CWS", "away": "NYY", "home_score": 5, "away_score": 9},
    ])
    db.upsert_player_logs(hconn, [{
        "sport": sport, "season": 2026, "period": _day(age + 1),
        "game_id": "CIN@X", "player": "Elly De La Cruz", "team": "CIN",
        "opponent": "X", "position": "SS", "home": 1,
        "market": "hits", "value": 1.0}])
    lconn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " stake_units, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (day, sport, day, "Elly De La Cruz", "hits", "OVER", 0.5, -150, 1.0,
         "open", "main"))
    lconn.commit()
    return hconn, lconn


def _status(lconn):
    return lconn.execute("SELECT status, pnl_units FROM bets").fetchone()


def test_an_old_postponed_mlb_pick_voids_and_is_audited():
    hconn, lconn = _world()
    got = ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat())
    assert [r["player"] for r in got] == ["Elly De La Cruz"], got
    assert tuple(_status(lconn)) == ("void", 0), tuple(_status(lconn))
    audit = lconn.execute(
        "SELECT action, reason FROM bets_audit ORDER BY seq DESC").fetchone()
    assert tuple(audit) == ("update", "auto_void_unplayed"), tuple(audit)


def test_it_is_idempotent():
    hconn, lconn = _world()
    ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat())
    assert ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat()) == []


def test_a_recent_game_waits_for_a_resumption():
    hconn, lconn = _world(age=2)
    assert ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat()) == []
    assert _status(lconn)[0] == "open"
    # The manual finder still lists it: the command is unchanged.
    assert len(ledger.unplayed_bets(lconn, hconn, today=TODAY.isoformat())) == 1


def test_other_leagues_keep_the_manual_command():
    hconn, lconn = _world(sport="nba")
    assert ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat()) == []
    assert _status(lconn)[0] == "open"


def test_a_graded_pick_is_never_touched():
    hconn, lconn = _world()
    lconn.execute("UPDATE bets SET status='won', pnl_units=0.67")
    lconn.commit()
    assert ledger.auto_void_unplayed(lconn, hconn, today=TODAY.isoformat()) == []
    assert tuple(_status(lconn)) == ("won", 0.67)


def test_the_settle_pass_runs_it_after_grading():
    src = inspect.getsource(maintenance.settle_open)
    i = src.index("ledger.settle_from_history(lconn, hconn)")
    j = src.index("ledger.auto_void_unplayed(lconn, hconn")
    assert i < j, "voids follow the grading pass, so a late final grades first"
    assert ledger.AUTO_VOID_SPORTS == ("mlb",) and ledger.AUTO_VOID_AFTER_DAYS == 3


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fails += 1; print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
