"""A preseason game is no season's (2026-11-18, walk 11, step YB).

The Cavaliers' 2025–26 row on their team page read 61-43 over 104 games: 82,
eighteen in the playoffs and four in the preseason, which every NBA season
stored before 24 September 2026 holds (the history backfill read ESPN's
scoreboard day by day from 1 October; the nightly has skipped the preseason
since). engine/hoopspreseason finds them by the scoreboard's own season type,
day by day in each season's first weeks, and moves each one's games row and
stat lines to the preseason tables the NFL already uses; its shots and opening
tip go. Nothing is written without --apply, a day the scoreboard does not
answer is left alone, and the NFL's own preseason count stays the NFL's.

    python3 tests/test_a_preseason_game_is_no_seasons.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D, hoopspreseason as HP                                # noqa: E402


def _db():
    path = Path(tempfile.mkdtemp()) / "t.db"
    conn = D.connect(path)
    games = [  # (sport, season, day, id, home, away, hs, as)
        ("nba", 2025, "2025-10-07", "401812684", "CLE", "CHI", 117, 118),     # preseason
        ("nba", 2025, "2025-10-14", "401812716", "CLE", "DET", 118, 100),     # preseason
        ("nba", 2025, "2025-10-22", "401809234", "NYK", "CLE", 119, 111),     # opening week
        ("nba", 2025, "2026-04-18", "401869187", "CLE", "TOR", 126, 113),     # the playoffs, past the scan
        ("nba", 2026, "2026-10-22", "401900001", "PHI", "CLE", 114, 106),     # this season: none stored
        ("wnba", 2026, "2026-05-03", "401700001", "IND", "WAS", 90, 80),      # preseason
        ("wnba", 2026, "2026-05-16", "401700002", "IND", "CHI", 93, 58),
        ("nfl", 2025, "2025-09-07", "nfl1", "KC", "LAC", 27, 21),
    ]
    for sport, season, day, gid, home, away, hs, as_ in games:
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES (?,?,?,?,?,?,?,?)", (sport, season, day, gid, home, away, hs, as_))
        for player, team, opp in (("A One", home, away), ("B Two", away, home)):
            for market, value in (("pts", 20), ("reb", 5)):
                conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                             "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (sport, season, day, gid, player, team, opp, "G", int(team == home), market, value))
        if sport == "nba":
            conn.execute("INSERT INTO nba_shots (game_id, action, season, date, player) VALUES (?,?,?,?,?)",
                         (gid, 1, season, day, "A One"))
            conn.execute("INSERT INTO nba_tips (game_id, season, date, home, away) VALUES (?,?,?,?,?)",
                         (gid, season, day, home, away))
    conn.execute("INSERT INTO preseason_games (sport, season, week, game_id, date, home, away, home_score, "
                 "away_score, completed, venue) VALUES ('nfl', 2026, 1, 'p1', '2026-08-08', 'KC', 'ARI', 20, 17, 1, '')")
    conn.commit()
    return conn


SCOREBOARD = {
    "2025-10-07": [{"game_id": "401812684", "preseason": True}],
    "2025-10-14": [{"game_id": "401812716", "preseason": True}, {"game_id": "elsewhere", "preseason": True}],
    "2025-10-22": [{"game_id": "401809234", "preseason": False}],
    "2026-05-03": [{"game_id": "401700001", "preseason": True}],
    "2026-05-16": [{"game_id": "401700002", "preseason": False}],
}


def _load(asked):
    def load(day):
        asked.append(day)
        if day == "2026-10-22":
            raise RuntimeError("scoreboard timed out")
        return SCOREBOARD.get(day, [])
    return load


def test_it_asks_the_scoreboard_only_about_a_seasons_first_weeks():
    conn = _db()
    assert HP.season_days(conn, "nba", 2025) == ["2025-10-07", "2025-10-14", "2025-10-22"], "not April's playoffs"
    assert HP.season_days(conn, "wnba", 2026) == ["2026-05-03", "2026-05-16"]
    assert HP.season_days(conn, "nba", 1999) == []


def test_it_finds_the_preseason_by_the_scoreboards_word_and_writes_nothing():
    conn = _db()
    asked = []
    rep = HP.found(conn, "nba", load=_load(asked))
    assert [g["game_id"] for g in rep["games"]] == ["401812684", "401812716"], rep
    assert rep["rows"] == 8, "four lines a game"
    assert rep["unread"] == ["2026-10-22: scoreboard timed out"], "a day it could not read is named, not guessed"
    assert "2026-04-18" not in asked
    assert conn.execute("SELECT COUNT(*) FROM games WHERE sport='nba'").fetchone()[0] == 5, "nothing written"
    wn = HP.found(conn, "wnba", load=_load([]))
    assert [g["game_id"] for g in wn["games"]] == ["401700001"]


def test_apply_moves_them_to_the_preseason_tables_and_keeps_the_season():
    conn = _db()
    rep = HP.found(conn, "nba", load=_load([]))
    moved = HP.apply(conn, "nba", rep)
    assert moved == {"games": 2, "lines": 8, "shots": 2, "tips": 2}, moved
    left = [r[0] for r in conn.execute("SELECT game_id FROM games WHERE sport='nba' ORDER BY period")]
    assert left == ["401809234", "401869187", "401900001"], left
    assert conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='nba' AND game_id IN "
                        "('401812684', '401812716')").fetchone()[0] == 0
    kept = conn.execute("SELECT sport, season, week, date, home, away, home_score, away_score, completed "
                        "FROM preseason_games WHERE sport='nba' ORDER BY date").fetchall()
    assert [tuple(r) for r in kept] == [("nba", 2025, 0, "2025-10-07", "CLE", "CHI", 117.0, 118.0, 1),
                                        ("nba", 2025, 0, "2025-10-14", "CLE", "DET", 118.0, 100.0, 1)], kept
    assert conn.execute("SELECT COUNT(*) FROM preseason_player_logs WHERE sport='nba'").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM nba_shots").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM games WHERE sport='nfl'").fetchone()[0] == 1, "another league untouched"
    # Run again: nothing left to move.
    assert HP.found(conn, "nba", load=_load([]))["games"] == []


def test_the_nfls_preseason_count_stays_the_nfls():
    conn = _db()
    HP.apply(conn, "nba", HP.found(conn, "nba", load=_load([])))
    from engine import todo
    src = Path(todo.__file__).read_text(encoding="utf-8")
    assert "SELECT COUNT(*) FROM preseason_games WHERE sport='nfl'" in src
    assert conn.execute("SELECT COUNT(*) FROM preseason_games WHERE sport='nfl'").fetchone()[0] == 1
    # The NFL's own readers already ask for the NFL's rows alone.
    for f in ("engine/nfl/prestarters.py", "engine/nfl/prefit.py"):
        body = (ROOT / f).read_text(encoding="utf-8")
        assert "sport='nfl'" in body, f


def test_the_runbook_names_the_command():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "python3 -m engine.hoopspreseason" in doc


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
