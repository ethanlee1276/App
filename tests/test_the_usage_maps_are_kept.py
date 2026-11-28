"""The NFL build's usage maps and its join audit are kept between builds
until what they read changes (engine/nflusage.build_usage_maps, join_audit).

The NFL build read the maps afresh every build, 1.9 seconds at 03:56 on 10
November (7 to 9 on a cold disk), and the join audit 0.8 more, from rows
that change when a week's results are ingested. What these hold:

  * a kept map is exactly the map the table gives, and a second build reads
    neither the maps nor the audit again;
  * a new log row, a changed game line (the red-zone map's implied totals)
    or a refitted role detector (the snap and volume maps ask it) reads the
    maps again, and the copy then kept is the new table's;
  * the replay's calls (a season and a week) are read as they always were
    and never touch the kept copy;
  * only the production history file keeps.

Run directly: `python3 tests/test_the_usage_maps_are_kept.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, logcache, nflusage as U                       # noqa: E402
# Only ever a scratch file of this test's own, named in full: the suite
# never runs the audit against the box's history (test_td_xfp's guard).
from engine.db import connect as scratch_history                      # noqa: E402


def _log(player, team, wk, market, value, season=2026):
    return {"sport": "nfl", "season": season, "period": f"{wk:03d}",
            "game_id": f"{team}-{season}-{wk:03d}", "player": player, "team": team,
            "opponent": "OPP", "position": "", "home": 1, "market": market, "value": value}


def _seed(conn, weeks=6):
    """Two KC backs and a receiver, every map's markets, and each week's game
    with its spread and total."""
    rows = []
    for wk in range(1, weeks + 1):
        rows += [_log("J.Bell", "KC", wk, "i5_car", 3), _log("J.Bell", "KC", wk, "rz_car", 5),
                 _log("J.Bell", "KC", wk, "rz_tgt", 1), _log("S.Pace", "KC", wk, "rz_car", 1),
                 _log("S.Pace", "KC", wk, "rz_tgt", 2),
                 _log("Jalen Bell", "KC", wk, "carries", 16), _log("Jalen Bell", "KC", wk, "rush_yds", 71),
                 _log("Jalen Bell", "KC", wk, "snap_pct", 0.62),
                 _log("Rich Rice", "KC", wk, "targets", 8), _log("Rich Rice", "KC", wk, "receptions", 6),
                 _log("Rich Rice", "KC", wk, "rec_yds", 77), _log("Rich Rice", "KC", wk, "snap_pct", 0.88),
                 _log("R.Rice", "KC", wk, "xfp", 14.5), _log("R.Rice", "KC", wk, "tgt_short", 4),
                 _log("R.Rice", "KC", wk, "tgt_mid", 3), _log("R.Rice", "KC", wk, "tgt_deep", 1)]
    db.upsert_player_logs(conn, rows)
    db.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": f"{wk:03d}",
                            "game_id": f"g{wk}", "home": "KC", "away": "OPP",
                            "spread": -3.5, "total": 47.5} for wk in range(1, weeks + 1)])
    conn.commit()


class _Kept:
    """A scratch history file the cache treats as production, a scratch
    cache and models folder, and every read from the table counted."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("QB_FEEDSTATE_DIR", "QB_MODELS_DIR")}
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.tmp.name, "feedstate")
        os.environ["QB_MODELS_DIR"] = os.path.join(self.tmp.name, "models")
        os.makedirs(os.environ["QB_MODELS_DIR"])
        self.saved = logcache.enabled_for, U._usage_maps, U._join_audit
        self.conn = scratch_history(os.path.join(self.tmp.name, "history.db"))
        _seed(self.conn)
        self.reads = {"maps": [], "audit": []}
        plain_maps, plain_audit = U._usage_maps, U._join_audit
        U._usage_maps = lambda c, s, w: (self.reads["maps"].append((s, w)), plain_maps(c, s, w))[1]
        U._join_audit = lambda *a, **k: (self.reads["audit"].append(1), plain_audit(*a, **k))[1]
        logcache.enabled_for = lambda c: True
        self.plain_maps = plain_maps
        return self

    def __exit__(self, *exc):
        logcache.enabled_for, U._usage_maps, U._join_audit = self.saved
        self.conn.close()
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()


def test_a_kept_map_is_the_tables_and_a_second_build_reads_neither():
    with _Kept() as k:
        first = U.build_usage_maps(k.conn)
        assert first == k.plain_maps(k.conn, None, None)
        assert first["red_zone"] and first["xfp"] and first["depth"] and first["team_of"], first
        assert first["red_zone"][("j", "bell", "KC")].team_implied == 25.5
        audit = U.join_audit(k.conn)
        again, audit_again = U.build_usage_maps(k.conn), U.join_audit(k.conn)
        assert again == first and audit_again == audit
        assert k.reads == {"maps": [(None, None)], "audit": [1]}, k.reads
        status = logcache.status()
        assert status["nfl_usage_maps.nfl"]["kept"] is True, status
        assert status["nfl_join_audit.nfl"]["kept"] is True, status


def test_a_new_row_a_moved_line_or_a_refit_role_reads_again():
    with _Kept() as k:
        U.build_usage_maps(k.conn)
        db.upsert_player_logs(k.conn, [_log("J.Bell", "KC", 7, "rz_car", 6)])
        k.conn.commit()
        moved = U.build_usage_maps(k.conn)
        assert len(k.reads["maps"]) == 2 and logcache.status()["nfl_usage_maps.nfl"]["why"] == "rows changed"
        assert moved == k.plain_maps(k.conn, None, None)
        k.conn.execute("UPDATE games SET total=51.5 WHERE sport='nfl' AND game_id='g3'")
        k.conn.commit()
        relined = U.build_usage_maps(k.conn)
        assert len(k.reads["maps"]) == 3 and logcache.status()["nfl_usage_maps.nfl"]["why"] == "inputs changed"
        assert relined["red_zone"][("j", "bell", "KC")].team_implied != moved["red_zone"][("j", "bell", "KC")].team_implied
        from engine import modelstate
        from engine.rolechange import STORE
        with open(modelstate.path(STORE), "w") as fh:
            fh.write("{}")
        U.build_usage_maps(k.conn)
        assert len(k.reads["maps"]) == 4, "a refitted role detector reads again"
        U.build_usage_maps(k.conn)
        assert len(k.reads["maps"]) == 4, "and is kept again after"


def test_the_replays_calls_are_read_as_before_and_leave_the_kept_copy():
    with _Kept() as k:
        live = U.build_usage_maps(k.conn)
        for wk in (3, 5):
            assert U.build_usage_maps(k.conn, 2026, upto_week=wk) == k.plain_maps(k.conn, 2026, wk)
        assert k.reads["maps"] == [(None, None), (2026, 3), (2026, 5)], k.reads
        assert U.build_usage_maps(k.conn) == live and len(k.reads["maps"]) == 3


def test_only_the_production_history_keeps():
    with _Kept() as k:
        logcache.enabled_for = k.saved[0]
        assert U._kept_inputs(k.conn) is None
        U.build_usage_maps(k.conn)
        U.build_usage_maps(k.conn)
        U.join_audit(k.conn)
        U.join_audit(k.conn)
        assert len(k.reads["maps"]) == 2 and len(k.reads["audit"]) == 2
        assert not os.path.exists(os.path.join(os.environ["QB_FEEDSTATE_DIR"], logcache.DIRNAME))


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
