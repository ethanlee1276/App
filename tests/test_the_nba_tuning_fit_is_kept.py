"""The NBA (and WNBA) tuning fit's stat spreads are kept until the league's
logs change (engine/hoops_fit.fit_stat_cvs, engine/logcache), and the fit
names its two halves on the heartbeat (boards.nba.parts, "tuning fit").

The heartbeat at 09:05 on 9 November had the NBA build's "tuning fit" stage
at 9 seconds of a 52-second build: every build re-read every season's stat
rows to measure per-player spreads that only move when a night's box
scores land. What these hold:

  * the spreads come back the same through the cache as off the table,
    are served while the league's rows hold, and are read again when any
    of them moves; another league's rows never touch them;
  * the seasons asked for and the games a player needs are each their own
    read, never served one another's numbers;
  * the fit prints its two halves (margin spread, stat spreads) in a build
    and stays silent outside one.

Run directly: `python3 tests/test_the_nba_tuning_fit_is_kept.py`
"""
import contextlib
import io
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, hoops_fit as HF, logcache, stageclock      # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own, with the
    cache switched on for that file (it is not the production one)."""

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


_MEANS = {"pts": 14.0, "reb": 5.5, "ast": 3.2, "fg3m": 1.6, "stl": 0.9, "blk": 0.6,
          "tov": 1.7, "min": 27.0}


def _league(conn, sport="nba", players=24, games=20, seed=7):
    """Enough of one league's box scores for every stat to fit: two seasons,
    each player's lines spread around his own means."""
    rnd = random.Random(seed)
    rows = []
    for p in range(players):
        scale = 0.6 + rnd.random()
        for g in range(games):
            season = 2025 if g < games // 2 else 2026
            day = f"{season}-{11 if season == 2025 else 1:02d}-{(g % 28) + 1:02d}"
            for market, mean in _MEANS.items():
                value = max(0.0, round(rnd.gauss(mean * scale, mean * scale * 0.4)))
                rows.append({"sport": sport, "season": season, "period": day,
                             "game_id": f"{sport}-{p % 6}-{g}", "player": f"{sport.upper()} P{p}",
                             "team": f"T{p % 6}", "opponent": f"T{(p + 1) % 6}", "position": "G",
                             "home": g % 2, "market": market, "value": value})
    db.upsert_player_logs(conn, rows)
    conn.commit()


def _note(name, sport):
    return logcache.status().get(f"{name}.{sport}") or {}


def _bump(conn, sport="nba"):
    db.upsert_player_logs(conn, [{"sport": sport, "season": 2026, "period": "2026-02-02",
                                  "game_id": "late", "player": f"{sport.upper()} P0", "team": "T0",
                                  "opponent": "T1", "position": "G", "home": 1,
                                  "market": "pts", "value": 41.0}])
    conn.commit()


def test_the_spreads_are_kept_and_read_the_same():
    with _Sandbox() as sb:
        _league(sb.conn)
        want = HF._fit_stat_cvs(sb.conn, "nba")
        assert want[0], "every stat has enough rows to fit"
        assert HF.fit_stat_cvs(sb.conn, "nba") == want, "the same through the cache"
        assert _note("hoops_cvs12", "nba")["kept"] is False
        assert HF.fit_stat_cvs(sb.conn, "nba") == want
        assert _note("hoops_cvs12", "nba")["kept"] is True, "served the second time"
        _bump(sb.conn)
        again = HF.fit_stat_cvs(sb.conn, "nba")
        assert again == HF._fit_stat_cvs(sb.conn, "nba") and again != want
        assert _note("hoops_cvs12", "nba")["why"] == "rows changed"


def test_another_leagues_rows_never_touch_them():
    with _Sandbox() as sb:
        _league(sb.conn)
        _league(sb.conn, sport="wnba", seed=8)
        nba = HF.fit_stat_cvs(sb.conn, "nba")
        wnba = HF.fit_stat_cvs(sb.conn, "wnba")
        assert wnba == HF._fit_stat_cvs(sb.conn, "wnba") and wnba != nba, "each league its own"
        _bump(sb.conn, sport="wnba")
        assert HF.fit_stat_cvs(sb.conn, "nba") == nba
        assert _note("hoops_cvs12", "nba")["kept"] is True, "a WNBA night leaves the NBA's alone"
        assert HF.fit_stat_cvs(sb.conn, "wnba") == HF._fit_stat_cvs(sb.conn, "wnba")
        assert _note("hoops_cvs12", "wnba")["why"] == "rows changed"


def test_the_seasons_and_the_games_needed_are_their_own_reads():
    with _Sandbox() as sb:
        _league(sb.conn, players=40)
        every = HF.fit_stat_cvs(sb.conn, "nba")
        one = HF.fit_stat_cvs(sb.conn, "nba", [2026], min_games=5)
        assert one == HF._fit_stat_cvs(sb.conn, "nba", [2026], 5) and one != every
        assert HF.fit_stat_cvs(sb.conn, "nba", [2026]) == HF._fit_stat_cvs(sb.conn, "nba", [2026])
        assert HF.fit_stat_cvs(sb.conn, "nba") == every
        assert _note("hoops_cvs12", "nba")["kept"] is True


def test_the_fitted_tuning_reads_the_same_through_the_cache():
    with _Sandbox() as sb:
        _league(sb.conn)
        keep = logcache.enabled_for
        logcache.enabled_for = lambda conn: False
        try:
            plain = HF.fitted_tuning(sb.conn, "nba")
        finally:
            logcache.enabled_for = keep
        assert HF.fitted_tuning(sb.conn, "nba") == plain
        assert HF.fitted_tuning(sb.conn, "nba") == plain
        assert _note("hoops_cvs12", "nba")["kept"] is True
        assert plain[1]["stat_rows"]["pts"] > 0


def test_the_fit_names_its_two_halves_in_a_build_only():
    keep = dict(stageclock._STATE)
    try:
        with _Sandbox() as sb:
            _league(sb.conn)
            stageclock._STATE.update(t0=None, last=None)
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet):
                HF.fitted_tuning(sb.conn, "nba")
            assert "⏱" not in quiet.getvalue(), "silent outside a build"
            stageclock.start()
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                HF.fitted_tuning(sb.conn, "nba")
            parts = stageclock.parse_parts(said.getvalue().splitlines())
            assert list(parts.get("tuning fit", {})) == ["margin spread", "stat spreads"], parts
            assert stageclock.parse(said.getvalue().splitlines()) == {}, "parts, never a stage"
    finally:
        stageclock._STATE.clear()
        stageclock._STATE.update(keep)


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
