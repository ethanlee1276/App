"""A night's box scores read this season's rows alone (step AEI, 24 November 2026).

College basketball's board was killed at its ten-minute limit at 12:45 ET on 24 November, as it had been on game
nights since 21 November (three builds running on the evening of the 23rd). The heartbeat's parts said where the
time went: the team profiles took 268 seconds and the stat spreads 81, read again because 266 of this season's rows
had landed. Both were kept (engine/logcache) on every season they read at once, so one night's rows read the whole
of last season again with them; college basketball's last season is about four times this one so far.

Each season is now kept on its own (engine/nba/teams.season_games, engine/hoops_fit._values_by_player): a night's
rows read this season's alone, last season's are kept while its rows hold, and what comes out is the same as one
read of every season. What this holds:

  * the team profiles through the kept seasons are the plain build's, and a night's rows read this season again
    and last season never;
  * the stat spreads' values are one read's, in season and day order, rows filed with no season first, and a
    night's rows read this season's again and no other;
  * the league's stored seasons are found by seeks, rows with no season said.

Offline. Run directly: `python3 tests/test_a_night_of_rows_reads_this_season_alone.py`
"""
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, hoops_fit as HF, logcache                     # noqa: E402
from engine.nba import teams as T                                    # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own, with the cache switched on for that file."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.keep = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.dir, "feedstate")
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        self.enabled = logcache.enabled_for
        logcache.enabled_for = lambda conn: True
        return self

    def __exit__(self, *exc):
        logcache.enabled_for = self.enabled
        self.conn.close()
        if self.keep is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)


CLUBS = ("BOS", "NYK", "MIA", "PHI")
BOX = ("min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb")


def _two_seasons(conn, sport="nba", nights=14, seed=5):
    """Two seasons of nights between four clubs, five men a side, every box column."""
    rnd = random.Random(seed)
    rows = []
    for season, month in ((2025, 11), (2026, 11)):
        for i in range(nights):
            day = f"{season}-{month:02d}-{i + 1:02d}"
            pairs = ((CLUBS[i % 4], CLUBS[(i + 1) % 4]), (CLUBS[(i + 2) % 4], CLUBS[(i + 3) % 4]))
            for a, b in pairs:
                gid = f"{sport}-{season}-{i}-{a}"
                for team, opp in ((a, b), (b, a)):
                    for k in range(5):
                        for m in BOX:
                            v = {"min": 34 - 3 * k, "fga": 14 - k, "fgm": 6 - k // 2, "fg3a": 5, "fg3m": 2,
                                 "fta": 4, "ftm": 3}.get(m, rnd.randint(0, 12))
                            rows.append({"sport": sport, "season": season, "period": day, "game_id": gid,
                                         "player": f"{team} P{k}", "team": team, "opponent": opp,
                                         "position": "G", "home": int(team == a), "market": m,
                                         "value": float(max(0, v + rnd.randint(-2, 2)))})
    db.upsert_player_logs(conn, rows)
    conn.commit()


def _night(conn, sport="nba", day="2026-11-20"):
    db.upsert_player_logs(conn, [{"sport": sport, "season": 2026, "period": day, "game_id": "late",
                                  "player": "BOS P0", "team": "BOS", "opponent": "NYK", "position": "G",
                                  "home": 1, "market": m, "value": 30.0 if m == "pts" else 4.0} for m in BOX])
    conn.commit()


def _counting(module, name):
    """Wraps ``module.name`` to note the seasons each call reads."""
    calls = []
    was = getattr(module, name)

    def wrapped(conn, sport, *a, **kw):
        calls.append((a, tuple(sorted(kw.items()))))
        return was(conn, sport, *a, **kw)
    setattr(module, name, wrapped)
    return calls, lambda: setattr(module, name, was)


def test_the_team_profiles_read_this_season_alone_on_a_night():
    with _Sandbox() as sb:
        _two_seasons(sb.conn)

        def plain(day):
            return T.build(T.load_rows(sb.conn, "nba", 2026), T.load_rows(sb.conn, "nba", 2025), "nba", before=day)
        want = plain("2026-11-15")
        assert T.board_profiles(sb.conn, "nba", "2026-11-15") == want
        calls, undo = _counting(T, "load_rows")
        try:
            kept = T.board_profiles(sb.conn, "nba", "2026-11-15")
            assert calls == [], f"kept: nothing read while the rows and the day hold: {calls}"
            _night(sb.conn)
            got = T.board_profiles(sb.conn, "nba", "2026-11-21")
            read = [c[0] for c in calls]
        finally:
            undo()
        assert kept == want
        assert read == [(2026,)], f"a night's rows read this season's alone, never last season's: {read}"
        assert got == plain("2026-11-21"), "and the profiles are the plain build's"
        assert got["teams"]["BOS"]["games_season"] > 0 and got["n"] == 4


def test_the_stat_spreads_read_this_season_alone_on_a_night():
    with _Sandbox() as sb:
        _two_seasons(sb.conn)
        one = HF._read_values(sb.conn, "nba")
        assert HF._values_by_player(sb.conn, "nba") == one, "the same values as one read of every season"
        want = HF.fit_stat_cvs(sb.conn, "nba")
        calls, undo = _counting(HF, "_read_values")
        try:
            _night(sb.conn)
            got = HF.fit_stat_cvs(sb.conn, "nba")
            read = [c for c in calls]
        finally:
            undo()
        assert read == [(([2026],), ())], f"this season's rows alone: {read}"
        keep = logcache.enabled_for
        logcache.enabled_for = lambda conn: False
        try:
            plain = HF._fit_stat_cvs(sb.conn, "nba")
        finally:
            logcache.enabled_for = keep
        assert got == plain and got != want, "the spreads are one read's, and the night moved them"


def test_values_keep_season_and_day_order_and_a_seasonless_row_comes_first():
    with _Sandbox() as sb:
        rows = [{"sport": "nba", "season": s, "period": d, "game_id": f"g{s}{d}", "player": "BOS P0",
                 "team": "BOS", "opponent": "NYK", "position": "G", "home": 1, "market": "pts", "value": v}
                for s, d, v in ((2026, "2026-11-02", 3.0), (2025, "2025-11-09", 2.0), (2025, "2025-11-01", 1.0),
                                (2026, "2026-11-01", 4.0))]
        rows.append({"sport": "nba", "season": None, "period": "2024-01-01", "game_id": "old", "player": "BOS P0",
                     "team": "BOS", "opponent": "NYK", "position": "G", "home": 1, "market": "pts", "value": 9.0})
        db.upsert_player_logs(sb.conn, rows)
        sb.conn.commit()
        assert HF._stored_seasons(sb.conn, "nba") == ([2025, 2026], True)
        assert HF._stored_seasons(sb.conn, "wnba") == ([], False)
        assert HF._read_values(sb.conn, "nba")[("BOS P0", "pts")] == [9.0, 1.0, 2.0, 4.0, 3.0]
        assert HF._values_by_player(sb.conn, "nba")[("BOS P0", "pts")] == [9.0, 1.0, 2.0, 4.0, 3.0]
        assert HF._values_by_player(sb.conn, "nba", [2026])[("BOS P0", "pts")] == [4.0, 3.0]


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
