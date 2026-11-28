"""The game logs' index on the team is built once, in the quiet hours (step AES, 25 November 2026).

A basketball board reads its games' players by team (nba_build.player_history: `team IN (...)` over two seasons),
and no index of player_game_logs holds the team, so the read looked up every row of both seasons: college
basketball's took 17 to 62 seconds of a game-night build on 24 November. engine/db.TEAM_INDEX holds (sport, team,
season, period). What this holds:

  * the index is never in the schema a connection runs (building it takes minutes on the box's file and holds the
    write lock, too long for a build under its ten-minute limit);
  * engine/maintenance.build_team_index builds it only in the hours nothing is played (4 and 5 AM Eastern), with
    the disk room it needs, once; a try that did not build waits before the next, and each outcome is kept for
    the heartbeat;
  * with the index, the player-history read walks the teams' own rows;
  * the cycle never asks inside the suite's sandbox.

Offline. Run directly: `python3 tests/test_the_team_index_is_built_once_in_the_quiet_hours.py`
"""
import datetime as dt
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, maintenance as M                             # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                                    # noqa: BLE001
    ET = dt.timezone(dt.timedelta(hours=-5))


def _at(hour):
    return dt.datetime(2026, 11, 25, hour, 10, tzinfo=ET).timestamp()


class _Box:
    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = self.dir / "history.db"
        conn = db.connect(self.db)
        db.upsert_player_logs(conn, [{"sport": "cbb", "season": 2026, "period": "2026-11-20", "game_id": "g",
                                      "player": "A B", "team": "DUKE", "opponent": "UNC", "position": "G",
                                      "home": 1, "market": "pts", "value": 9.0}])
        conn.commit()
        conn.close()
        self.state = self.dir / "team_index.json"
        self.logs = []
        return self

    def build(self, hour, **kw):
        return M.build_team_index(self.logs.append, now=_at(hour), path=self.db, state_path=self.state, **kw)

    def has_index(self):
        conn = sqlite3.connect(str(self.db))
        try:
            return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                                     (db.TEAM_INDEX,)).fetchone())
        finally:
            conn.close()

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


def test_a_connection_never_builds_it():
    assert db.TEAM_INDEX not in db.SCHEMA and "player_game_logs (sport, team, season, period)" in db.TEAM_INDEX_SQL
    with _Box() as box:
        assert not box.has_index(), "db.connect ran the schema, and the schema does not hold it"


def test_it_is_built_in_the_quiet_hours_once_and_said_so():
    with _Box() as box:
        assert box.build(21) == "not now" and not box.has_index(), "a game night: never"
        assert box.build(4, free_gb=10.4) == "built" and box.has_index()
        doc = json.loads(box.state.read_text())
        assert doc["result"] == "built" and doc["seconds"] >= 0 and doc["free_gb"] == 10.4
        assert any("index on the team built" in line for line in box.logs), box.logs
        assert box.build(4) == "there" and box.build(21) == "there", "once"


def test_short_of_disk_it_waits_and_a_try_is_not_made_again_for_hours():
    with _Box() as box:
        assert box.build(5, free_gb=1.2) == "no room" and not box.has_index()
        assert json.loads(box.state.read_text())["result"] == "no room"
        assert box.build(5, free_gb=10.0) == "not now", "inside the retry's wait"
        later = M.build_team_index(box.logs.append, now=_at(4) + 86400, path=box.db, state_path=box.state,
                                   free_gb=10.0)
        assert later == "built" and box.has_index(), "the next night's quiet hours"


def test_a_failure_is_kept_and_never_raises():
    with _Box() as box:
        box.db.write_bytes(b"not a database")
        assert box.build(4, free_gb=10.0) == "failed"
        assert json.loads(box.state.read_text())["result"] == "failed"
        assert M.build_team_index(box.logs.append, now=_at(4), path=box.dir / "none.db",
                                  state_path=box.state) == "no history"


def test_with_it_the_player_history_read_walks_the_teams_rows():
    with _Box() as box:
        box.build(4, free_gb=10.0)
        conn = db.connect(box.db)
        q = ("SELECT player, team, position, period, market, value, opponent, home FROM player_game_logs "
             "WHERE sport=? AND team IN (?,?) AND season IN (?,?) ORDER BY period DESC")
        plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + q, ("cbb", "DUKE", "UNC", 2026, 2025)))
        conn.close()
        assert f"USING INDEX {db.TEAM_INDEX} (sport=? AND team=? AND season=?)" in plan, plan


def test_the_cycle_asks_outside_the_sandbox_only_and_the_heartbeat_shows_it():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index("def _run_team_index("):src.index("def run_if_due(")]
    assert "if os.environ.get(modelstate.ENV_VAR):" in body
    assert "    _run_team_index(log)\n    state = _load_state(state_path)" in src
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"team_index": _team_index_public(),' in launch


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
