"""An NFL player's game was at home or on the road, and the page says which
(engine/ingest.nfl_set_home, correct_nfl_home), NFLHOME1.

Read on the live site on 17 November 2026: Josh Allen's By market card said
"vs NYJ" for Week 10, a game played at the Jets, while Recent games on the
same page said "@ NYJ". All 418 players on the NFL board had every game as a
home game. The weekly stats file names a team and an opponent and never the
venue, so every NFL row had gone in with `home` 1 since the first ingest.
What these hold:

  * a row written by any NFL pull takes its side from the stored schedule:
    the host's players 1, the visitors' 0, in the playoffs as in the season;
  * a row the schedule cannot place (a week not stored, a team spelled
    another way) is left as given, and counted;
  * the seasons stored before this are corrected from the schedule, the
    newest first and one a night, once: a season with a visiting row is done,
    a season whose schedule is not stored waits, and nothing but the flag
    of a visiting row is touched;
  * the board's per-market history, which the card draws, says "@" for the
    road games once the rows are right.

    python3 tests/test_an_nfl_game_is_home_or_away.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, ingest as IG, statlogs                  # noqa: E402
from engine.sources import nflverse                                  # noqa: E402


def _week(name, team, opp, wk, pos="QB", kind="REG", **stats):
    return {"season_type": kind, "week": str(wk), "player_display_name": name, "recent_team": team,
            "opponent_team": opp, "position": pos, "position_group": pos,
            **{k: str(v) for k, v in stats.items()}}


def _qb(name, team, opp, wk, yds, kind="REG"):
    return _week(name, team, opp, wk, kind=kind, completions=20, attempts=30, passing_yards=yds,
                 passing_tds=1, interceptions=0, carries=5, rushing_yards=20)


#: Buffalo's 2026: at the Jets in Week 10, at home to Baltimore in Week 8, and a playoff game at Denver.
WEEKLY = [_qb("Josh Allen", "BUF", "NYJ", 10, 196), _qb("Josh Allen", "BUF", "BAL", 8, 289),
          _qb("Josh Allen", "BUF", "DEN", 20, 283, kind="POST"), _qb("Justin Fields", "NYJ", "BUF", 10, 150),
          _qb("Bo Nix", "DEN", "BUF", 20, 240, kind="POST"), _qb("Nobody Placed", "XXX", "BUF", 3, 100)]
GAMES = [(2026, "010", "BUF@NYJ", "NYJ", "BUF"), (2026, "008", "BAL@BUF", "BUF", "BAL"),
         (2026, "020", "BUF@DEN", "DEN", "BUF")]


def _conn(games=GAMES, scores=True):
    conn = _db.connect(":memory:")
    for season, period, gid, home, away in games:
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, extra) "
                     "VALUES ('nfl', ?, ?, ?, ?, ?, ?, ?, '{}')",
                     (season, period, gid, home, away, 24 if scores else None, 17 if scores else None))
    conn.commit()
    return conn


def _homes(conn, player, market="pass_yds", season=2026):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT period, home FROM player_game_logs WHERE sport='nfl' AND season=? AND player=? AND market=?",
        (season, player, market))}


def test_a_row_takes_its_side_from_the_stored_schedule():
    conn = _conn()
    rows = IG.nfl_player_log_rows(WEEKLY, 2026) + IG.nfl_usage_rows(WEEKLY, 2026) + IG.nfl_td_rows(WEEKLY, 2026)
    assert rows and all(r["home"] == 1 for r in rows), "the file never says where: every row arrives as home"
    left = IG.nfl_set_home(conn, rows)
    side = {(r["player"], r["period"]): r["home"] for r in rows}
    assert side[("Josh Allen", "010")] == 0 and side[("Josh Allen", "008")] == 1, side
    assert side[("Justin Fields", "010")] == 1, "the Jets hosted"
    assert side[("Josh Allen", "020")] == 0 and side[("Bo Nix", "020")] == 1, "the playoffs as the season"
    assert side[("Nobody Placed", "003")] == 1, "a row the schedule cannot place is left as given"
    assert left == sum(1 for r in rows if r["player"] == "Nobody Placed") > 0
    assert IG.nfl_set_home(conn, []) == 0


def test_every_nfl_pull_writes_the_side():
    conn = _conn()
    real = (nflverse.load_weekly_stats, nflverse.load_snap_counts)
    nflverse.load_weekly_stats = lambda season, **kw: WEEKLY
    nflverse.load_snap_counts = lambda season, **kw: [
        {"week": "10", "player": "Josh Allen", "team": "BUF", "opponent": "NYJ", "position": "QB", "offense_pct": "0.97"},
        {"week": "8", "player": "Josh Allen", "team": "BUF", "opponent": "BAL", "position": "QB", "offense_pct": "1.0"}]
    try:
        res = IG.ingest_nfl_results(conn, 2026)
    finally:
        nflverse.load_weekly_stats, nflverse.load_snap_counts = real
    assert res["player_logs"] and not res["skipped"], res
    assert _homes(conn, "Josh Allen") == {"010": 0, "008": 1, "020": 0}, _homes(conn, "Josh Allen")
    assert _homes(conn, "Josh Allen", "snap_pct") == {"010": 0, "008": 1}
    assert _homes(conn, "Justin Fields") == {"010": 1}
    # The card's own history: the road games read "@".
    got = statlogs._query(conn, "nfl", statlogs.SPORT_MARKETS["nfl"], ["Josh Allen"])["Josh Allen"]["Passing Yards"]
    assert [(g["week"], g["opponent"], g["home"]) for g in got] == [(20, "DEN", False), (10, "NYJ", False),
                                                                    (8, "BAL", True)], got
    src = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    writes = src[src.index("def backfill_nfl_box("):src.index("# --- MLB ---")]
    assert writes.count("nfl_set_home(conn, ") == 5, "the box backfill, the results pull and its snaps, the full ingest and its play file"


def _stored(conn, season, rows):
    """Rows as every season before this was stored: each one a home game."""
    _db.upsert_player_logs(conn, [{"sport": "nfl", "season": season, "period": per, "game_id": f"{team}-{per}",
                                   "player": who, "team": team, "opponent": opp, "position": "QB", "home": 1,
                                   "market": "pass_yds", "value": 200.0} for who, team, opp, per in rows])
    conn.commit()


def test_the_seasons_stored_before_are_corrected_newest_first_one_a_night_and_once():
    games = [(2025, "001", "BUF@NYJ", "NYJ", "BUF"), (2025, "002", "MIA@BUF", "BUF", "MIA"),
             (2024, "001", "BUF@MIA", "MIA", "BUF"), (2023, "001", "BUF@NYJ", "NYJ", "BUF")]
    conn = _conn(games)
    _stored(conn, 2025, [("Josh Allen", "BUF", "NYJ", "001"), ("Josh Allen", "BUF", "MIA", "002"),
                         ("Aaron Rodgers", "NYJ", "BUF", "001")])
    _stored(conn, 2024, [("Josh Allen", "BUF", "MIA", "001"), ("Tua Tagovailoa", "MIA", "BUF", "001")])
    _stored(conn, 2023, [("Josh Allen", "BUF", "NYJ", "001")])
    _stored(conn, 2022, [("Josh Allen", "BUF", "LA", "001")])          # no schedule stored: it waits
    first = IG.correct_nfl_home(conn)
    assert first == {"seasons": [2025], "rows": 1, "left": 2}, first
    assert _homes(conn, "Josh Allen", season=2025) == {"001": 0, "002": 1}
    assert _homes(conn, "Aaron Rodgers", season=2025) == {"001": 1}, "the host's rows are not touched"
    assert _homes(conn, "Josh Allen", season=2024) == {"001": 1}, "one season a night"
    assert IG.correct_nfl_home(conn) == {"seasons": [2024], "rows": 1, "left": 1}
    assert IG.correct_nfl_home(conn) == {"seasons": [2023], "rows": 1, "left": 0}
    assert IG.correct_nfl_home(conn) == {"seasons": [], "rows": 0, "left": 0}, "done once"
    assert _homes(conn, "Josh Allen", season=2022) == {"001": 1}
    # The value, the opponent and every other column are as they were.
    row = conn.execute("SELECT team, opponent, position, market, value FROM player_game_logs "
                       "WHERE sport='nfl' AND season=2025 AND player='Josh Allen' AND period='001'").fetchone()
    assert tuple(row) == ("BUF", "NYJ", "QB", "pass_yds", 200.0)


def test_a_season_not_played_yet_and_another_league_are_left_alone():
    conn = _conn([(2027, "001", "BUF@NYJ", "NYJ", "BUF")], scores=False)
    _stored(conn, 2027, [("Josh Allen", "BUF", "NYJ", "001")])
    _db.upsert_player_logs(conn, [{"sport": "cfb", "season": 2026, "period": "2026-10-24", "game_id": "g1",
                                   "player": "A Passer", "team": "BUF", "opponent": "NYJ", "position": "QB",
                                   "home": 1, "market": "pass_yds", "value": 250.0}])
    conn.commit()
    assert IG.correct_nfl_home(conn) == {"seasons": [], "rows": 0, "left": 0}, "no final in its schedule: not a season to correct"
    assert conn.execute("SELECT home FROM player_game_logs WHERE sport='cfb'").fetchone()[0] == 1
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("res = ingest_nfl_results(_rdb.connect(), season)")
    assert "fixed = correct_nfl_home(_hdb.connect())" in src[i:i + 1800], "after the night's pull, in the season's months"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
