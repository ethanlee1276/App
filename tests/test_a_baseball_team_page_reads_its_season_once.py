"""A baseball team page reads its season once, every club at a time, and keeps it (step ACD, 22 November 2026).

Baseball's team pages never answered on the box: the Yankees' gave up at 90 seconds, the Dodgers' at 55 and
the Mariners' at 90, while hockey's answered in four and basketball's in one. A baseball row is filed under its
player and day, so a club's rows were read through its game days, and each of its ~160 days read every club's
rows of that day: about the league's whole season for one club, twice a page. What these hold:

  * baseball's squad and stat page come off one read of the season that groups every club at once, and say the
    same as the day-by-day read did;
  * the read is kept against the logs' own count of their changes (engine/logcache): served from the copy until
    a baseball row changes, then read again;
  * the night warms it, so no reader waits on the first read; other leagues are read as before.

    python3 tests/test_a_baseball_team_page_reads_its_season_once.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, logcache, teamdex as T                   # noqa: E402


def _history():
    """Two baseball clubs a day for 40 days, three men a side, two markets each, and a hockey club."""
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    rows = []
    for n in range(40):
        day = f"2026-{4 + n // 28:02d}-{n % 28 + 1:02d}"
        for home, away in (("SEA", "NYY"), ("LAD", "SD")):
            conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date)"
                         " VALUES ('mlb', 2026, ?, ?, ?, ?, 3, 2, ?)", (day, f"g{home}{n}", home, away, day))
            for side, opp in ((home, away), (away, home)):
                for i in range(3):
                    for m, v in (("hits", float(i % 2 + n % 3)), ("total_bases", float(i + n % 4))):
                        rows.append(("mlb", 2026, day, f"{side}{i}-{day}", f"{side} Player {i}", side, opp,
                                     "OF" if i else "C", int(side == home), m, v))
    rows.append(("nhl", 2026, "2026-11-01", "x", "A Skater", "SEA", "VAN", "C", 1, "points", 1.0))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position,"
                     " home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_one_read_of_the_season_says_what_the_day_by_day_read_did():
    conn = _history()
    T.trace_start()
    squad, stats = T.squad(conn, "mlb", "SEA"), T.stat_tables(conn, "mlb", "SEA")
    steps = [s for s, _ms, _how in T.trace_take()]
    assert "kept" in steps and steps.count("season_read") == 2, steps     # unkept on a test's own file: read twice
    kept = T._kept_season(conn, "mlb", 2026)
    assert set(kept) == {"SEA", "NYY", "LAD", "SD"} and len(kept["SEA"]) == 6, {k: len(v) for k, v in kept.items()}
    was = T.SEASON_KEPT
    T.SEASON_KEPT = frozenset()
    try:
        T.trace_start()
        old = T.squad(conn, "mlb", "SEA"), T.stat_tables(conn, "mlb", "SEA")
        assert "kept" not in [s for s, _ms, _how in T.trace_take()]
    finally:
        T.SEASON_KEPT = was
    assert json.dumps([squad, stats], sort_keys=True) == json.dumps(list(old), sort_keys=True)
    assert squad["players"] == 3 and squad["season"] == 2026


def test_it_is_kept_until_a_baseball_row_changes():
    conn = _history()
    store = tempfile.mkdtemp()
    was_dir, was_on = os.environ.get("QB_FEEDSTATE_DIR"), logcache.enabled_for
    os.environ["QB_FEEDSTATE_DIR"] = store
    logcache.enabled_for = lambda c: True
    try:
        def reads():
            T.trace_start()
            T.squad(conn, "mlb", "SEA")
            T.stat_tables(conn, "mlb", "LAD")
            return [s for s, _ms, _how in T.trace_take()].count("season_read")
        assert reads() == 1, "one read for both clubs and both tables"
        assert reads() == 0, "served from the copy"
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position,"
                     " home, market, value) VALUES ('mlb', 2026, '2026-05-30', 'n', 'New Man', 'SEA', 'NYY', 'OF', 1,"
                     " 'hits', 2)")
        conn.commit()
        assert reads() == 1, "a baseball row changed: read again"
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position,"
                     " home, market, value) VALUES ('nhl', 2026, '2026-11-02', 'y', 'B Skater', 'SEA', 'VAN', 'C', 1,"
                     " 'points', 1)")
        conn.commit()
        assert reads() == 0, "another league's row changes nothing here"
        assert "New Man" in json.dumps(T.squad(conn, "mlb", "SEA"))
    finally:
        logcache.enabled_for = was_on
        if was_dir is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = was_dir


def test_the_night_warms_it_and_other_leagues_read_as_before():
    conn = _history()
    assert T.warm(conn, "mlb") == 4 and T.warm(conn, "nhl") == 0 and T.SEASON_KEPT == frozenset({"mlb"})
    src = (ROOT / "engine" / "teamdex.py").read_text(encoding="utf-8")
    assert 'logcache.memo(conn, "team_season_rows", sport, (int(season),), compute, code=__file__)' in src
    mt = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert '_kept = _tdx.warm(_hconn, "mlb")' in mt
    assert mt.index("hoops_preseason_out(state, _hconn, log)\n") < mt.index('_kept = _tdx.warm(_hconn, "mlb")')
    T.trace_start()
    T.squad(conn, "nhl", "SEA")
    assert "kept" not in [s for s, _ms, _how in T.trace_take()], "hockey reads its own way"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
