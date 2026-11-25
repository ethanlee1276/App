"""A week that would not place a journal row waits half a day before it is asked again (step AHL, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". The settle pass's preparation took 575.3 s
of an 809.5 s pass on the live box, 573.3 s of it placing old journal rows on their game day (ledger.
backfill_game_days): the week-labelled NFL rows no route places were asked again on every pass, a pass every quarter
hour on the box's one core, each with a read of the player's whole NFL career, twice. The settle pass now asks such a
row again only twelve hours after its last try, twenty of them a pass, the never-tried and the longest-waiting first;
a row whose date is a day is placed at once, as before; the --backfill-days command tries every row, as before.

Offline. Run directly: `python3 tests/test_a_week_that_would_not_place_a_row_waits.py`
"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger  # noqa: E402


def _hist():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, home TEXT, away TEXT, "
                       "date TEXT); CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, "
                       "game_id TEXT, player TEXT, team TEXT, market TEXT);")
    for gid, home, away, day in (("NE@SEA", "SEA", "NE", "2026-09-10"), ("DAL@NYG", "NYG", "DAL", "2026-09-13")):
        conn.execute("INSERT INTO games VALUES ('nfl',2026,'001',?,?,?,?)", (gid, home, away, day))
    conn.commit()
    return conn


def _ledger(players, iso=()):
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))
    for p in players:
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, stake_units, status, category) "
                     "VALUES ('nfl','2026-W01',?,'rec_yds','OVER',40.5,-110,1.0,'open','main')", (p,))
    for p in iso:
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, stake_units, status, category) "
                     "VALUES ('nba','2026-11-20',?,'pts','OVER',20.5,-110,1.0,'open','main')", (p,))
    conn.commit()
    return conn


def _day(conn, player):
    return conn.execute("SELECT game_day FROM bets WHERE player=?", (player,)).fetchone()["game_day"]


def test_unplaced_weeks_wait_and_take_their_turns():
    nobody = [f"Rookie {i}" for i in range(5)]                    # no team on file: no route places them
    conn, hist = _ledger(nobody, iso=["Jalen Brunson"]), _hist()
    day = 12 * 3600
    first = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=2)
    assert _day(conn, "Jalen Brunson") == "2026-11-20", "a row whose date is a day is placed at once, as before"
    assert first["retried"] == 2 and first["waiting"] == 3 and first["unresolved"] == 2, first
    second = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=2)
    third = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=2)
    assert (second["retried"], third["retried"]) == (2, 1), "the never-tried in turn"
    asked = {int(r[0]) for r in conn.execute("SELECT bet_id FROM game_day_tries")}
    assert len(asked) == 5, "every unplaced row tried once"
    quiet = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=2)
    assert quiet["retried"] == 0 and quiet["waiting"] == 5, ("none again inside the half day", quiet)
    conn.execute("UPDATE game_day_tries SET tried_at = tried_at - ? WHERE bet_id = (SELECT MIN(bet_id) FROM "
                 "game_day_tries)", (day + 60,))
    conn.commit()
    later = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=2)
    assert later["retried"] == 1, ("the one past its half day, alone", later)


def test_a_row_whose_week_can_now_place_it_is_placed_on_its_turn_and_the_command_tries_every_row():
    conn, hist = _ledger(["Malik Nabers", "Rookie 9"]), _hist()
    day = 12 * 3600
    ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=5)
    assert _day(conn, "Malik Nabers") is None, "no team on file yet"
    hist.execute("INSERT INTO player_game_logs VALUES ('nfl',2025,'014','DAL@NYG','Malik Nabers','NYG','rec_yds')")
    hist.commit()
    waiting = ledger.backfill_game_days(conn, hist, retry_after=day, per_pass=5)
    assert waiting["retried"] == 0 and _day(conn, "Malik Nabers") is None, "inside its half day it waits"
    command = ledger.backfill_game_days(conn, hist)                # the --backfill-days command: every row
    assert _day(conn, "Malik Nabers") == "2026-09-13" and command["retried"] == 2, command


def test_the_settle_pass_asks_so_and_says_its_counts():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "bf = ledger.backfill_game_days(lconn, hconn, retry_after=ledger.GAME_DAY_RETRY_S)" in src
    assert 'phases["game_days"] = {k: bf.get(k, 0) for k in ("filled", "unresolved", "retried", "waiting")}' in src
    assert ledger.GAME_DAY_RETRY_S == 12 * 3600 and ledger.GAME_DAY_TRIES_PER_PASS == 20
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert "_led.backfill_game_days(conn, _db.connect(), dry_run=dry_run)" in launch, "the command, as before"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
