"""Hockey's opening week is this season's (2026-11-19, step YF, FINALS2).

The check-in after 18 November's games found fifteen NHL clubs one game short
of the league's table, the same fifteen as the night before, with the nightly
re-read of owed days (FINALS1) changing nothing. The eight games were on file,
finals and all, under 2025: the 2026-27 season (84 games a club, 1,344 in all)
opened on 29 September (Chicago at Vegas, Florida at Carolina, Montreal at
Toronto, the Rangers at Boston, Vancouver at Edmonton) and 30 September (the
Kings at Colorado, the Islanders at Toronto, Pittsburgh's 7-0 at Philadelphia),
and a season began in October by its date. So the race simulated from 338
games of 346, the clubs' pages and their players' season lines were a game
short, and last season held eight games it never played. (The race's 998 games
left was right all along: 346 + 998 is 1,344.) What these hold:

  * September is the new season's (engine/seasons), and a stored game takes
    the season its own league id names (nhldata.season_of_game), its players'
    lines and shots with it;
  * the night moves every game filed under another season, with its lines and
    shots, before it looks for owed days (nhldata.reseason), and does it once:
    a second night moves nothing;
  * hockey's night opens with the season's window (September), never walking
    back past its first day.

    python3 tests/test_the_opening_week_is_this_seasons.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, maintenance as M                                     # noqa: E402
from engine.seasons import season_of, window                                # noqa: E402
from engine.sources import nhldata as N                                     # noqa: E402

OPENER = {"games": [
    {"id": 2026020001, "gameType": 2, "gameState": "OFF", "startTimeUTC": "2026-09-30T02:00:00Z",
     "homeTeam": {"abbrev": "VGK", "score": 5, "sog": 31}, "awayTeam": {"abbrev": "CHI", "score": 2, "sog": 24},
     "periodDescriptor": {"periodType": "REG"}},
    {"id": 2026010077, "gameType": 1, "gameState": "OFF", "startTimeUTC": "2026-09-29T23:00:00Z",
     "homeTeam": {"abbrev": "OTT", "score": 3}, "awayTeam": {"abbrev": "MTL", "score": 1}}]}


def test_september_is_the_new_season():
    assert season_of("nhl", "2026-09-29") == 2026, "opening night of 2026-27"
    assert season_of("nhl", "2026-06-20") == 2025 and season_of("nhl", "2026-08-31") == 2025
    assert season_of("nhl", "2027-02-14") == 2026
    assert window("nhl", 2026) == ("2026-09-20", "2027-06-30")
    assert season_of("nba", "2026-09-29") == 2025, "the other leagues keep their own boundaries"


def test_a_game_takes_the_season_its_id_names():
    assert N.season_of_game(2026020001, "2026-09-29") == 2026
    assert N.season_of_game("2026030411", "2027-06-12") == 2026, "a Final in June is the season before"
    assert N.season_of_game("2019030411", "2020-09-28") == 2019, "the id wins over the date"
    assert N.season_of_game(None, "2026-09-30") == 2026 and N.season_of_game("CHI@VGK", "2026-03-01") == 2025
    assert N.season_of_game("12345", "2026-10-02") == 2026, "no league id: the date's"


def test_the_opener_is_filed_under_its_season():
    c = db.connect(":memory:")
    N.ingest_day(c, "2026-09-29", scores_only=True, fetch_day=lambda d: OPENER)
    rows = c.execute("SELECT season, game_id, home_score, away_score FROM games WHERE sport='nhl'").fetchall()
    assert [tuple(r) for r in rows] == [(2026, "CHI@VGK", 5.0, 2.0)], [tuple(r) for r in rows]
    skater = {"pid": 1, "team": "VGK", "opponent": "CHI", "position": "C", "home": True, "goalie": False,
              **{m: 1.0 for m in N.SKATER_MARKETS}}
    lines = N.log_rows([skater], {1: ("Jack Eichel", "")}, "2026-09-29", 2026)
    assert lines and {r["season"] for r in lines} == {2026}
    assert {r["season"] for r in N.log_rows([skater], {1: ("Jack Eichel", "")}, "2026-09-29")} == {2026}
    src = (ROOT / "engine" / "sources" / "nhldata.py").read_text(encoding="utf-8")
    body = src[src.index("def ingest_day("):src.index("def backfill_lines(")]
    assert 'season = season_of_game(g["game_id"], date)' in body
    assert "prows += log_rows(players, names, date, season)" in body
    assert 'conn, g["game_id"], date, season,' in body, "the shots take the game's season too"


def _misfiled():
    c = db.connect(":memory:")
    games = [  # (season, period, game_id, home, away, home_score, away_score, nhl_id)
        (2025, "2026-09-29", "CHI@VGK", "VGK", "CHI", 5, 2, 2026020001),
        (2025, "2026-09-30", "PIT@PHI", "PHI", "PIT", 0, 7, 2026020008),
        (2026, "2026-09-30", "PIT@PHI", "PHI", "PIT", 0, 7, 2026020008),  # already re-read under 2026
        (2025, "2026-04-10", "BOS@TOR", "TOR", "BOS", 4, 3, 2025021200),  # last season's: stays
        (2026, "2026-10-08", "NYR@BOS", "BOS", "NYR", 2, 1, 2026020040),
    ]
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, extra) "
                  "VALUES ('nhl',?,?,?,?,?,?,?,?)",
                  [(s, p, g, h, a, hs, as_, json.dumps({"nhl_id": i})) for s, p, g, h, a, hs, as_, i in games])
    logs = [  # (season, period, player, team, market, value)
        (2025, "2026-09-29", "Jack Eichel", "VGK", "points", 2.0),
        (2025, "2026-09-29", "Jack Eichel", "VGK", "sog", 4.0),
        (2025, "2026-09-29", "Connor Bedard", "CHI", "points", 1.0),
        (2025, "2026-09-30", "Sidney Crosby", "PIT", "points", 3.0),
        (2026, "2026-09-30", "Sidney Crosby", "PIT", "points", 3.0),           # its copy under 2026
        (2025, "2026-04-10", "Auston Matthews", "TOR", "points", 1.0),
    ]
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
                  "VALUES ('nhl',?,?,?,?,?,?,?)",
                  [(s, p, f"{n}-{p}", n, t, m, v) for s, p, n, t, m, v in logs])
    c.executemany("INSERT INTO nhl_shots (game_id, event_id, date, season) VALUES (?,?,?,?)",
                  [(2026020001, 1, "2026-09-29", 2025), (2026020001, 2, "2026-09-29", 2025),
                   (2025021200, 1, "2026-04-10", 2025), (2026020040, 1, "2026-10-08", 2026)])
    c.commit()
    return c


def test_the_misfiled_opener_moves_with_its_lines_and_shots():
    c = _misfiled()
    moved = N.reseason(c)
    assert moved == {"games": 1, "lines": 3, "shots": 2}, moved
    by_season = {tuple(r) for r in c.execute("SELECT season, period, game_id FROM games WHERE sport='nhl'")}
    assert by_season == {(2026, "2026-09-29", "CHI@VGK"), (2026, "2026-09-30", "PIT@PHI"),
                         (2025, "2026-04-10", "BOS@TOR"), (2026, "2026-10-08", "NYR@BOS")}, by_season
    lines = {tuple(r) for r in c.execute("SELECT season, period, player, market FROM player_game_logs")}
    assert lines == {(2026, "2026-09-29", "Jack Eichel", "points"), (2026, "2026-09-29", "Jack Eichel", "sog"),
                     (2026, "2026-09-29", "Connor Bedard", "points"), (2026, "2026-09-30", "Sidney Crosby", "points"),
                     (2025, "2026-04-10", "Auston Matthews", "points")}, lines
    shots = sorted(tuple(r) for r in c.execute("SELECT game_id, event_id, season FROM nhl_shots"))
    assert shots == [(2025021200, 1, 2025), (2026020001, 1, 2026), (2026020001, 2, 2026),
                     (2026020040, 1, 2026)], shots
    assert N.reseason(c) == {"games": 0, "lines": 0, "shots": 0}, "a second night moves nothing"
    gp = c.execute("SELECT COUNT(*) FROM games WHERE sport='nhl' AND season=2026 AND home_score IS NOT NULL")
    assert gp.fetchone()[0] == 3, "this season counts its opening week"


def test_the_night_opens_with_the_season_and_repairs_first():
    assert M._season_start("nhl", dt.date(2026, 9, 10)) == dt.date(2026, 9, 20), "before opening: nothing to read"
    assert M._season_start("nhl", dt.date(2026, 11, 18)) == dt.date(2026, 9, 20)
    assert M._season_start("nhl", dt.date(2027, 6, 10)) == dt.date(2026, 9, 20), "June is the season before's"
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    block = src[src.index("    # NHL results (2026-10-03)"):src.index("    # THE FACES AND THE ROSTERS")]
    assert "if today.month >= 9 or today.month <= 6:" in block, "September is hockey's"
    assert 'hstart = max(_catch_up_start(_hconn, "nhl", yesterday), _season_start("nhl", yesterday))' in block
    assert block.index("_nhl.reseason(hconn2)") < block.index("_nhl.days_owed("), "repair before the owed days"
    # Step YE's goalie-start repair (RUN_NEXT 00p) runs each night too, on the
    # moved games as well: after the season repair, before the owed days.
    i = block.index('_unnamed = _starts.found(hconn2, _nhl_season("nhl", today.isoformat()))')
    assert block.index("_nhl.reseason(hconn2)") < i < block.index("_nhl.days_owed(")
    assert "_starts.apply(hconn2, _unnamed)" in block


def test_a_season_not_begun_says_when_hockey_opens():
    import standings_build
    note = standings_build._empty_note("nhl", 2027, "2027-09-01")
    assert note.startswith("The 2027 NHL season has not started yet. It opens in late September or early October"), note


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
