"""The league's list of teams is read in one step and kept, and so is each season's table (step AHI,
25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". Every team page built read the sport's
every game, row by row, to list its teams: 191 to 557 ms of the live site's NHL, NBA and MLB team pages ("teams" in
their Server-Timing). The rows come in one step now (db.rows_at_once), and the list is kept ten minutes per database
file while no game is added. A team's profile built each season's league table from every final of that season, for
every club's page; each table is kept ten minutes while the season's games say the same.

Offline. Run directly: `python3 tests/test_the_leagues_team_list_is_kept.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, teamdex  # noqa: E402


class _Seen:
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def _games(path=None):
    conn = D.connect(path or os.path.join(tempfile.mkdtemp(), "history.db"))
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('nhl', 2026, ?, ?, ?, ?, ?, ?)",
                     [("2026-11-20", "g1", "EDM", "CGY", 4, 2), ("2026-11-21", "g2", "TOR", "MTL", None, None),
                      ("2026-11-22", "g3", "VAN", "EDM", "3", 1)])
    conn.commit()
    return conn


def test_the_list_is_the_one_it_was_and_kept_until_a_game_is_added():
    conn = _games()
    teamdex._TEAMS.clear()
    first = _Seen(conn)
    assert teamdex.teams(first, "nhl") == ["CGY", "EDM", "VAN"], "a game with no score names no team, as before"
    assert any("FROM games WHERE sport=?" in s for s in first.sql)
    again = _Seen(conn)
    assert teamdex.teams(again, "nhl") == ["CGY", "EDM", "VAN"]
    assert not any("FROM games WHERE sport=?" in s for s in again.sql), ("kept", again.sql)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                 "VALUES ('nhl', 2026, '2026-11-23', 'g4', 'SEA', 'VAN', 2, 5)")
    conn.commit()
    assert teamdex.teams(conn, "nhl") == ["CGY", "EDM", "SEA", "VAN"], "a game added: read again"
    key = next(iter(teamdex._TEAMS))
    at, top, out = teamdex._TEAMS[key]
    teamdex._TEAMS[key] = (at - teamdex.TEAMS_TTL - 1, top, out)
    later = _Seen(conn)
    teamdex.teams(later, "nhl")
    assert any("FROM games WHERE sport=?" in s for s in later.sql), "past its ten minutes: read again"
    got = teamdex.teams(conn, "nhl")
    got.append("XXX")
    assert "XXX" not in teamdex.teams(conn, "nhl"), "a reader's copy, not the kept list"
    teamdex._TEAMS.clear()


def test_a_seasons_table_is_kept_for_every_club_until_a_final_lands():
    conn = _games()
    teamdex._SEASON_TABLES.clear()
    first = _Seen(conn)
    table = teamdex.season_table(first, "nhl", 2026)
    assert set(table) == {"CGY", "EDM", "VAN"} and table["EDM"]["games"] == 2
    assert any("FROM games WHERE sport=? AND season=? ORDER BY" in s for s in first.sql)
    again = _Seen(conn)
    assert teamdex.season_table(again, "nhl", 2026) is table, "the same table for the next club's page"
    assert not any("ORDER BY season DESC" in s for s in again.sql), ("kept", again.sql)
    conn.execute("UPDATE games SET home_score=3, away_score=2 WHERE game_id='g2'")    # a final lands on its row
    conn.commit()
    landed = teamdex.season_table(conn, "nhl", 2026)
    assert set(landed) == {"CGY", "EDM", "VAN", "TOR", "MTL"}, "a final written onto its row: built again"
    key = next(k for k in teamdex._SEASON_TABLES if k[1:] == ("nhl", 2026))
    at, stamp, kept = teamdex._SEASON_TABLES[key]
    teamdex._SEASON_TABLES[key] = (at - teamdex.SEASON_TABLE_TTL - 1, stamp, kept)
    assert teamdex.season_table(conn, "nhl", 2026) is not kept, "past its ten minutes: built again"
    page = teamdex.profile(conn, "nhl", "EDM")
    assert page["seasons"] and page["seasons"][0]["season"] == 2026 and page["career"]["games"] == 2
    teamdex._SEASON_TABLES.clear()


def test_the_newest_season_is_one_lookup_where_the_file_has_the_team_index():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('mlb', ?, ?, ?, 'BOS', 'NYY', 5, 3)",
                     [(2025, "2025-09-01", "g25"), (2026, "2026-09-01", "g26")])
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES ('mlb', ?, ?, ?, ?, ?, 'NYY', 'RF', 1, 'hits', 1.0)",
                     [(2025, "2025-09-01", "Rafael Devers-2025-09-01", "Rafael Devers", "BOS"),
                      (2026, "2026-09-01", "Aaron Judge-2026-09-01", "Aaron Judge", "NYY")])
    conn.commit()
    teamdex._TEAM_INDEXED.clear()
    plain = _Seen(conn)
    assert teamdex._latest_season(plain, "mlb", "BOS") == 2025, "2026 holds no Red Sox row"
    assert not any("INDEXED BY idx_logs_team" in s for s in plain.sql), "no team index: the keyed reads, as before"
    conn.execute(D.TEAM_INDEX_SQL)
    conn.commit()
    teamdex._TEAM_INDEXED.clear()
    fast = _Seen(conn)
    assert teamdex._latest_season(fast, "mlb", "BOS") == 2025, "the same answer"
    assert teamdex._latest_season(fast, "mlb", "NYY") == 2026
    asked = [s for s in fast.sql if "FROM player_game_logs" in s]
    assert asked and all("INDEXED BY idx_logs_team" in s for s in asked), asked
    assert not any("CROSS JOIN" in s for s in fast.sql), "one lookup a season, no club's day read whole"
    teamdex._TEAM_INDEXED.clear()


def test_a_database_in_memory_is_never_kept():
    conn = D.connect(":memory:")
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                 "VALUES ('nba', 2026, '2026-11-20', 'g1', 'NYK', 'BOS', 110, 104)")
    teamdex._TEAMS.clear()
    assert teamdex.teams(conn, "nba") == ["BOS", "NYK"] and not teamdex._TEAMS
    assert teamdex.teams(conn, "nfl") == []
    teamdex._SEASON_TABLES.clear()
    assert set(teamdex.season_table(conn, "nba", 2026)) == {"BOS", "NYK"} and not teamdex._SEASON_TABLES


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
