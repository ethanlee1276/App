"""A team page reads its own games, not the sport's every row (18 November 2026).

A college basketball team page answered in 16 to 40 seconds. Its squad and
stat page read `player_game_logs` by team, and nothing on that table leads
with the team (its key is sport, season, period, game_id, player, market):
the latest season scanned the sport's every season, and the squad and the
stat page a whole season each, millions of college rows to find a few
hundred. A team's rows sit under its own games, which the games table lists.
What these hold:

  * the squad and the stat page read the same rows as before, through the
    team's games — the same players, games and totals as the old reads;
  * the season they pick is the newest one with the team's rows;
  * with no games on file for the team (a team filed under another code
    there) the old reads answer, so nothing that read before reads less;
  * the read goes through the table's key, a lookup per game, not a scan.

    python3 tests/test_a_team_page_reads_its_own_games.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, teamdex                                # noqa: E402

OLD = ("SELECT player, position, market, COUNT(*) n, SUM(value) total, "
       "COUNT(DISTINCT game_id) games FROM player_game_logs "
       "WHERE sport=? AND team=? AND season=? AND player<>'' "
       "GROUP BY player, position, market")


def _history(with_games=True):
    conn = db.connect(":memory:")
    games, logs = [], []
    for season in (2025, 2026):
        for k in range(6):
            day = f"{season}-11-{10 + k:02d}"
            for home, away in (("DUKE", "UNC"), ("KU", "BAY")):
                gid = f"{season}{k}{home}"
                games.append({"sport": "cbb", "season": season, "period": day, "game_id": gid,
                              "date": day, "home": home, "away": away,
                              "home_score": 70 + k, "away_score": 60 + k})
                for team, opp in ((home, away), (away, home)):
                    for j in range(3):
                        for market, v in (("points", 10 + j + k), ("rebounds", 4 + j)):
                            logs.append({"sport": "cbb", "season": season, "period": day, "game_id": gid,
                                         "player": f"{team} Player {j}", "team": team, "opponent": opp,
                                         "position": "G" if j else "F", "home": int(team == home),
                                         "market": market, "value": v})
    if with_games:
        db.upsert_games(conn, games)
    db.upsert_player_logs(conn, logs)
    conn.commit()
    return conn


def _key(rows):
    return sorted((r["player"], r["position"], r["market"], r["n"], r["total"], r["games"]) for r in rows)


def test_the_teams_games_give_the_same_rows_as_the_old_read():
    conn = _history()
    for team in ("DUKE", "UNC", "KU"):
        for season in (2025, 2026):
            new = teamdex._season_rows(conn, "cbb", team, season)
            old = conn.execute(OLD, ("cbb", team, season)).fetchall()
            assert new and _key(new) == _key(old), (team, season)
    sq = teamdex.squad(conn, "cbb", "DUKE")
    names = sorted(w["player"] for g in sq["positions"] for w in g["players"])
    assert names == ["DUKE Player 0", "DUKE Player 1", "DUKE Player 2"], names


def test_the_newest_season_with_the_teams_rows():
    conn = _history()
    assert teamdex._latest_season(conn, "cbb", "DUKE") == 2026
    # A season on the schedule with no rows yet steps back to the last one with rows.
    db.upsert_games(conn, [{"sport": "cbb", "season": 2027, "period": "2027-11-05", "game_id": "x1",
                            "date": "2027-11-05", "home": "DUKE", "away": "UNC",
                            "home_score": None, "away_score": None}])
    conn.commit()
    assert teamdex._latest_season(conn, "cbb", "DUKE") == 2026
    assert teamdex._latest_season(conn, "cbb", "NOBODY") is None


def test_with_no_games_on_file_the_old_reads_answer():
    conn = _history(with_games=False)
    assert teamdex._team_games(conn, "cbb", "DUKE") == []
    assert teamdex._latest_season(conn, "cbb", "DUKE") == 2026
    new = teamdex._season_rows(conn, "cbb", "DUKE", 2026)
    assert _key(new) == _key(conn.execute(OLD, ("cbb", "DUKE", 2026)).fetchall()) and new


def test_the_team_list_reads_two_names_off_each_final():
    conn = _history()
    db.upsert_games(conn, [
        {"sport": "cbb", "season": 2026, "period": "2026-12-01", "game_id": "f1", "date": "2026-12-01",
         "home": "FUTURE", "away": "LATER", "home_score": None, "away_score": None},
        {"sport": "cbb", "season": 2026, "period": "2026-12-02", "game_id": "f2", "date": "2026-12-02",
         "home": "BADROW", "away": "KU", "home_score": "n/a", "away_score": 60}])
    conn.commit()
    assert teamdex.teams(conn, "cbb") == ["BAY", "DUKE", "KU", "UNC"]
    assert teamdex.teams(conn, "nfl") == []
    src = open(os.path.join(ROOT, "engine", "teamdex.py"), encoding="utf-8").read()
    i = src.index("def teams(conn, sport: str)")
    assert "_finals(" not in src[i:src.index("\ndef ", i + 10)]


def test_the_read_is_a_lookup_per_game():
    conn = _history()
    pairs = [(p, g) for _s, p, g in teamdex._team_games(conn, "cbb", "DUKE", 2026)]
    sql = teamdex._BY_GAMES.format(pairs=",".join("(?,?)" for _ in pairs))
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN " + sql, tuple(x for p in pairs for x in p) + ("cbb", 2026, "DUKE")))
    assert "SCAN l" not in plan and "SCAN player_game_logs" not in plan, plan
    assert "USING INDEX" in plan or "USING PRIMARY KEY" in plan, plan


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
