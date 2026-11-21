"""The defense fit waits for the turnovers (the box, 2026-10-28).

Ethan ran `dstfit.py` on the box and it printed the league at
`"takeaways": 0.0`. The turnover columns of team_weeks have been counted
since 2026-10-20, but only the current season is refreshed, so 2023-2025
held NULL there: summed as none, they measured a league that never takes
the ball away, and `--save` would have kept a zero the projection divides
by. What these hold:

  - a saved league rate of zero is never the league (dstproj.league_rates);
  - a week whose turnovers were never counted is not a game without a
    takeaway: last season's NULL weeks no longer pull this season's
    defenses down;
  - dstfit.py names the seasons, measures and saves nothing, and prints the
    one command that fills them;
  - that command (`python3 -m engine.sources.nflpbp --team-weeks`) writes
    the counts off the play-by-play, a season at a time, and a season it
    cannot fetch is skipped and said, never half-written.

    python3 tests/test_the_defense_fit_waits_for_the_turnovers.py
"""
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as DB                  # noqa: E402
from engine import dstproj as D              # noqa: E402
from engine.sources import nflpbp as NP      # noqa: E402
from engine.sources.fetch import DataUnavailable  # noqa: E402

GAME = {"home": "PHI", "away": "DAL", "spread": -3.0, "total": 44.0}


@contextlib.contextmanager
def _fit(doc):
    with tempfile.TemporaryDirectory() as d:
        old = D.FIT_PATH
        D.FIT_PATH = Path(d) / "dst_fit.json"
        try:
            if doc is not None:
                D.FIT_PATH.write_text(json.dumps(doc))
            yield D.FIT_PATH
        finally:
            D.FIT_PATH = old


def test_a_saved_zero_is_never_the_league():
    with _fit({"league": {"sack_rate": 0.0663, "dropbacks": 35.41, "takeaways": 0.0, "pa_sd": 8.98}}):
        lg = D.league_rates()
    assert lg["takeaways"] == D.LEAGUE["takeaways"] > 0, "the box's zero is empty data, not a league"
    assert lg["sack_rate"] == 0.0663 and lg["dropbacks"] == 35.41 and lg["pa_sd"] == 8.98, "the real ones still win"
    row = D.project(GAME, "PHI", {}, lg)
    assert row and row["dst"]["int"] > 0, row


def _weeks_db(last_counted: bool):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE team_weeks (sport TEXT, season INTEGER, period TEXT, team TEXT, "
              "takeaways INTEGER, giveaways INTEGER)")
    for wk in range(1, 18):                    # last season: stored before the turnovers were counted
        c.execute("INSERT INTO team_weeks VALUES ('nfl', 2025, ?, 'PHI', ?, ?)",
                  (f"{wk:03d}", 2 if last_counted else None, 1 if last_counted else None))
    for wk in range(1, 8):                     # this season: counted, two a game
        c.execute("INSERT INTO team_weeks VALUES ('nfl', 2026, ?, 'PHI', 2, 1)", (f"{wk:03d}",))
    return c


def test_an_uncounted_week_is_not_a_game_without_a_takeaway():
    c = _weeks_db(last_counted=False)
    assert "PHI" not in D.team_rates(c, 2025), "no week of it counted, so no turnover games"
    now = D.season_rates(c, 2026, 8)["PHI"]
    assert now["games"] == 7 and now["takeaways"] == 14, now
    counted = D.season_rates(_weeks_db(last_counted=True), 2026, 8)["PHI"]
    assert counted["games"] == 7 + D.LAST_SEASON_WEIGHT * 17, counted
    rate = lambda r: (r["takeaways"] + D.LEAGUE["takeaways"] * D.PRIOR_GAMES) / (r["games"] + D.PRIOR_GAMES)  # noqa: E731
    assert rate(now) > 1.6, "two a game, shrunk toward the league, and no NULL week read as none"


# --- dstfit.py -------------------------------------------------------------------------------
def _history(path, counted: bool):
    sys.path.insert(0, str(ROOT / "tests"))
    from test_team_defenses_are_projected import _history as base
    base(path)
    if not counted:
        c = sqlite3.connect(path)
        c.execute("UPDATE team_weeks SET takeaways=NULL, giveaways=NULL")
        c.commit()
        c.close()


def _run_main(path, argv):
    import dstfit
    old = dstfit.connect
    dstfit.connect = lambda: sqlite3.connect(path)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = dstfit.main(argv)
    finally:
        dstfit.connect = old
    return code, out.getvalue()


def test_the_fit_names_the_seasons_and_measures_nothing():
    import dstfit
    with tempfile.TemporaryDirectory() as d, _fit(None) as fit:
        path = os.path.join(d, "h.db")
        _history(path, counted=False)
        conn = sqlite3.connect(path)
        try:
            assert dstfit.turnovers_missing(conn, [2025]) == [2025]
            assert dstfit.turnovers_missing(conn, [2024]) == [], "a season with no rows is not missing counts"
        finally:
            conn.close()
        code, out = _run_main(path, ["--seasons", "2025", "--weeks", "3-8", "--save"])
        assert code == 1, out
        assert "missing for 2025" in out and "Nothing measured, nothing saved." in out, out
        assert "python3 -m engine.sources.nflpbp --team-weeks 2025" in out, out
        assert not fit.exists(), "--save kept nothing"
        assert "League:" not in out, "no rate printed off empty data"


def test_with_the_counts_it_measures_and_saves():
    with tempfile.TemporaryDirectory() as d, _fit(None) as fit:
        path = os.path.join(d, "h.db")
        _history(path, counted=True)
        code, out = _run_main(path, ["--seasons", "2025", "--weeks", "3-8", "--save"])
        assert code == 0, out
        doc = json.loads(fit.read_text())
        assert doc["league"]["takeaways"] == 1.0, doc["league"]      # two a game for half the league


def test_a_run_of_seasons_is_named_the_way_the_command_reads_it():
    import dstfit
    assert dstfit._span([2023, 2024, 2025]) == "2023-2025"
    assert dstfit._span([2025, 2023]) == "2023,2025"
    assert dstfit._span([2024]) == "2024"
    for spec, want in (("2023-2025", [2023, 2024, 2025]), ("2023,2025", [2023, 2025]), ("2024", [2024])):
        assert NP._seasons(spec) == want, spec
        assert NP._seasons(dstfit._span(want)) == want, want


def test_a_partly_counted_season_is_missing_too():
    import dstfit
    c = _weeks_db(last_counted=True)
    c.execute("UPDATE team_weeks SET takeaways=NULL WHERE season=2026 AND period='003'")
    assert dstfit.turnovers_missing(c, [2025, 2026]) == [2026]
    c.execute("UPDATE team_weeks SET takeaways=0 WHERE season=2025")
    assert dstfit.turnovers_missing(c, [2025]) == [2025], "a league with no takeaway all season is empty data"


# --- the backfill ------------------------------------------------------------------------------
def _plays(season):
    if season == 2023:
        raise DataUnavailable("pbp 2023 unavailable")
    for wk in (1, 2):
        # Two weeks of the Eagles at the Cowboys: an interception the Eagles
        # throw, a fumble the Cowboys lose, a muffed punt the Eagles lose.
        yield {"week": str(wk), "posteam": "PHI", "defteam": "DAL", "play_type": "pass", "yardline_100": "60",
               "interception": "1", "epa": "-3.1", "game_id": f"g{wk}", "qtr": "1", "wp": "0.5"}
        yield {"week": str(wk), "posteam": "DAL", "defteam": "PHI", "play_type": "run", "yardline_100": "40",
               "fumble_lost": "1", "fumbled_1_team": "DAL", "epa": "-2.0", "game_id": f"g{wk}", "qtr": "1"}
        yield {"week": str(wk), "posteam": "DAL", "defteam": "PHI", "play_type": "punt", "yardline_100": "50",
               "fumble_lost": "1", "fumbled_1_team": "PHI", "game_id": f"g{wk}", "qtr": "2"}


def test_the_backfill_fills_the_counts_a_season_at_a_time():
    import dstfit
    with tempfile.TemporaryDirectory() as d:
        conn = DB.connect(os.path.join(d, "q.db"))
        try:
            # 2024 as the box holds it: rows from before the turnovers were counted.
            DB.upsert_team_weeks(conn, [{"sport": "nfl", "season": 2024, "period": f"{wk:03d}", "team": t,
                                         "plays": 60, "proe": 0.01} for wk in (1, 2) for t in ("PHI", "DAL")])
            assert dstfit.turnovers_missing(conn, [2024]) == [2024]
            got = NP.fill_team_weeks(conn, [2023, 2024], load=_plays)
            assert got[2023] == "pbp 2023 unavailable", "a season it cannot fetch is said"
            assert got[2024] == {"rows": 4, "takeaways": 6}, got
            rows = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(
                "SELECT team, period, takeaways, giveaways FROM team_weeks WHERE season=2024")}
            # The Eagles: the fumble they took; the pick and the muffed punt they gave.
            assert rows[("PHI", "001")] == (1, 2) and rows[("DAL", "002")] == (2, 1), rows
            assert dstfit.turnovers_missing(conn, [2024]) == []
            assert not conn.execute("SELECT COUNT(*) FROM team_weeks WHERE season=2023").fetchone()[0]
        finally:
            conn.close()


def test_the_command_runs_as_a_module():
    r = subprocess.run([sys.executable, "-m", "engine.sources.nflpbp", "--help"], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--team-weeks" in r.stdout, (r.returncode, r.stdout, r.stderr)
    src = (ROOT / "engine" / "sources" / "nflpbp.py").read_text(encoding="utf-8")
    fill = src[src.index("def fill_team_weeks("):src.index("def _seasons(")]
    assert "except DataUnavailable" in fill and "db.upsert_team_weeks(conn, rows)" in fill


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
