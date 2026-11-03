"""The settle pass lets go of the history file before it fetches anything,
and when it is done (engine/boxsettle.ingest_for_open).

3 November: the college board failed every build from 07:56 on "database is
locked" while storing its results, and on the old code it still failed at
11:39, long after the daily chores had finished. The holder was the settle
pass, which runs every five minutes. Its box-score step deletes a finished
game's provisional rows once the official file has them, and it committed
only when that DELETE removed a row. A DELETE takes SQLite's write lock even
when it matches nothing. So after the official NFL file replaced Monday
night's provisional rows, every pass while a prop on that game stayed open
took the lock and kept it: through the box-score fetches and the rest of
the pass, which never commits the history connection itself. What these
hold:

  * a pass whose games are all in the official file, with nothing left to
    purge, ends with no transaction open, and another writer gets the file
    at once;
  * no scoreboard or box-score fetch runs while the history file is
    write-locked by the pass;
  * a pass that does purge and fetch still writes everything it should.

Run directly: `python3 tests/test_the_settle_pass_lets_go_of_the_history_file.py`
"""
import datetime as dt
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B, db, ledger                    # noqa: E402

YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H, str(t / "h.db")


def _bet(L, player="Amon-Ra St. Brown"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, 'nfl', '2026-W02', ?, ?, 'rec_yds', 'OVER', 60.5, -110, 1, 10, 'open', 'main')",
        (f"{YESTERDAY}T12:00:00", YESTERDAY, player))
    L.commit()


def _game(H, game_id, home, away):
    H.execute(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, "
        "home_score, away_score) VALUES ('nfl', 2026, '002', ?, ?, ?, ?, 24, 20)",
        (game_id, YESTERDAY, home, away))
    H.commit()


def _official(H):
    """nflverse has landed for DET's game: keyed the official way, with no
    provisional row left to purge."""
    db.upsert_player_logs(H, [{"sport": "nfl", "season": 2026, "period": "002",
                               "game_id": "DET-002", "player": "Amon-Ra St. Brown",
                               "team": "DET", "opponent": "KC", "position": "WR",
                               "home": 1, "market": "rec_yds", "value": 83.0}])


def _summary(home, home_name, player):
    return {"boxscore": {"players": [
        {"team": {"abbreviation": home, "id": "2", "displayName": home_name}, "statistics": [
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": player, "position": {"abbreviation": "WR"}},
                           "stats": ["6", "71", "11.8", "0", "22", "8"]}]}]}]}}


def _quiet(*_a, **_k):
    pass


def test_a_pass_with_nothing_left_to_purge_lets_go_of_the_file():
    L, H, path = _world()
    _bet(L)
    _game(H, "KC@DET", "DET", "KC")
    _official(H)
    fetched = []
    res = B.ingest_for_open(L, H, "nfl", log=_quiet,
                            fetch_rows=lambda lg: fetched.append(lg) or [],
                            fetch_summary=lambda lg, eid: fetched.append(eid) or {})
    assert res == {"games": 0, "rows": 0, "purged": 0, "skipped": []}, res
    assert fetched == [], "a game the official file has is never fetched"
    assert not H.in_transaction, "the purge's transaction was left open, holding the write lock"
    other = sqlite3.connect(path)
    other.execute("PRAGMA busy_timeout=100")
    other.execute("INSERT INTO games (sport, season, period, game_id) VALUES ('cfb', 2026, '10', 'x')")
    other.commit()                      # "database is locked" before the fix
    other.close()


def test_no_fetch_runs_while_the_file_is_write_locked():
    L, H, path = _world()
    _bet(L)
    _game(H, "KC@DET", "DET", "KC")       # in the official file: purged, not fetched
    _game(H, "MIA@BUF", "BUF", "MIA")     # still owed: fetched
    _official(H)
    seen = []

    def fetch_rows(league):
        seen.append(("scoreboard", H.in_transaction))
        return [{"away": "MIA", "home": "BUF", "event_id": "401778"}]

    def fetch_summary(league, eid):
        seen.append(("box score", H.in_transaction))
        return _summary("BUF", "Buffalo Bills", "Khalil Shakir")
    res = B.ingest_for_open(L, H, "nfl", log=_quiet, fetch_rows=fetch_rows, fetch_summary=fetch_summary)
    assert [what for what, _ in seen] == ["scoreboard", "box score"], seen
    assert not any(locked for _, locked in seen), f"fetched while holding the write lock: {seen}"
    # And the pass still did its work: BUF's line filed provisionally.
    assert res["games"] == 1 and res["rows"] >= 1, res
    got = H.execute("SELECT game_id, value FROM player_game_logs WHERE player='Khalil Shakir' "
                    "AND market='rec_yds'").fetchall()
    assert [(r["game_id"], r["value"]) for r in got] == [("BUF-002-box", 71.0)], [dict(r) for r in got]
    assert not H.in_transaction


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
