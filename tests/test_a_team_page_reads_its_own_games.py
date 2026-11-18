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
    keys = teamdex._log_keys("cbb", "DUKE", teamdex._team_games(conn, "cbb", "DUKE", 2026))
    sql = teamdex._by_keys_sql(teamdex._SUMS, len(keys), " AND l.player<>'' GROUP BY l.player, l.position, l.market")
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN " + sql, tuple(x for k in keys for x in k) + ("cbb", 2026, "DUKE")))
    assert "SCAN l" not in plan and "SCAN player_game_logs" not in plan, plan
    # A LOOKUP ON THE WHOLE KEY, THE KEYS OUTSIDE (2026-11-18): "SEARCH l USING INDEX
    # idx_logs_player (sport=?)" passed the two checks above and walked the sport's every row,
    # 28 seconds on the box. The search must name all four key columns, after the key list.
    assert "(sport=? AND season=? AND period=? AND game_id=?)" in plan, plan
    assert plan.index("SCAN g") < plan.index("SEARCH l"), plan
    days = sorted({p for _s, p, _g in teamdex._team_games(conn, "cbb", "DUKE", 2026)})
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN " + teamdex._by_days_sql("SELECT 1", len(days)), tuple(days) + ("cbb", 2026, "DUKE")))
    assert "SCAN l" not in plan and "SCAN player_game_logs" not in plan, plan
    assert "(sport=? AND season=? AND period=?)" in plan and plan.index("SCAN g") < plan.index("SEARCH l"), plan


def _nfl_history():
    """The NFL as it is filed: the schedule's "AWAY@HOME", the rows' team
    week ("DET-010"), and a same-night box score's "-box" copy."""
    conn = db.connect(":memory:")
    games, logs = [], []
    for wk in range(1, 6):
        p = f"{wk:03d}"
        home, away = ("DET", "CHI") if wk % 2 else ("CHI", "DET")
        games.append({"sport": "nfl", "season": 2026, "period": p, "game_id": f"{away}@{home}",
                      "date": f"2026-09-{6 + 7 * wk:02d}", "home": home, "away": away,
                      "home_score": 20 + wk, "away_score": 17})
        for team, opp in ((home, away), (away, home)):
            gid = f"{team}-{p}" + ("-box" if wk == 5 else "")
            for j, (name, pos) in enumerate(((f"{team} QB", "QB"), (f"{team} WR", "WR"))):
                for market, v in (("pass_yds" if pos == "QB" else "rec_yds", 200 + wk + j), ("rush_yds", 10 + wk)):
                    logs.append({"sport": "nfl", "season": 2026, "period": p, "game_id": gid, "player": name,
                                 "team": team, "opponent": opp, "position": pos, "home": int(team == home),
                                 "market": market, "value": v})
    db.upsert_games(conn, games)
    db.upsert_player_logs(conn, logs)
    conn.commit()
    return conn


def test_the_nfl_is_read_by_its_team_weeks():
    conn = _nfl_history()
    assert teamdex._log_keys("nfl", "DET", [(2026, "003", "DET@CHI")]) == [("003", "DET-003"), ("003", "DET-003-box")]
    new = teamdex._season_rows(conn, "nfl", "DET", 2026)
    old = conn.execute(OLD, ("nfl", "DET", 2026)).fetchall()
    assert new and _key(new) == _key(old), (_key(new), _key(old))
    assert {r["games"] for r in new} == {5}, "the box score's week counts with the rest"
    assert teamdex._latest_season(conn, "nfl", "DET") == 2026
    # Read by the team week, not by the old scan: no row of the answer is
    # left out when the old read is taken away.
    src = teamdex._keyed(conn, "nfl", "DET", 2026, teamdex._team_games(conn, "nfl", "DET", 2026),
                         teamdex._SUMS, " AND l.player<>'' GROUP BY l.player, l.position, l.market")
    assert src and _key(src) == _key(old)


def test_hockey_is_read_by_its_game_days():
    # A row per player and day ("Name-2026-11-17"): only the day is shared.
    conn = db.connect(":memory:")
    games, logs = [], []
    for k in range(4):
        day = f"2026-11-{10 + k:02d}"
        games.append({"sport": "nhl", "season": 2026, "period": day, "game_id": f"BOS@TOR{k}", "date": day,
                      "home": "TOR", "away": "BOS", "home_score": 3, "away_score": 2})
        games.append({"sport": "nhl", "season": 2026, "period": day, "game_id": f"NYR@MTL{k}", "date": day,
                      "home": "MTL", "away": "NYR", "home_score": 1, "away_score": 4})
        for team in ("TOR", "BOS", "MTL", "NYR"):
            for name in (f"{team} C", f"{team} D"):
                for market, v in (("shots", 2 + k), ("toi", 18.5)):
                    logs.append({"sport": "nhl", "season": 2026, "period": day, "game_id": f"{name}-{day}",
                                 "player": name, "team": team, "opponent": "x", "position": name[-1],
                                 "home": 0, "market": market, "value": v})
    db.upsert_games(conn, games)
    db.upsert_player_logs(conn, logs)
    conn.commit()
    new = teamdex._season_rows(conn, "nhl", "TOR", 2026)
    old = conn.execute(OLD, ("nhl", "TOR", 2026)).fetchall()
    assert new and _key(new) == _key(old)
    assert teamdex._latest_season(conn, "nhl", "TOR") == 2026
    # College's nights are too wide to read by day: its rows carry the key.
    assert "cbb" in teamdex._WIDE_PERIODS and "nfl" in teamdex._WIDE_PERIODS and "nhl" not in teamdex._WIDE_PERIODS


def test_the_depth_chart_reads_the_rosters_own_rows():
    conn = db.connect(":memory:")
    logs = []
    names = ("Nolan Smith Jr.", "Nikola Jokić", "De’Aaron Fox", "Someone Else", "Nolan Smithson")
    for k in range(25):
        day = f"2026-{10 + k // 20:02d}-{1 + k % 20:02d}"
        for i, name in enumerate(names):
            logs.append({"sport": "nba", "season": 2026, "period": day, "game_id": f"{name}-{day}",
                         "player": name, "team": "DEN", "opponent": "x", "position": "G", "home": 0,
                         "market": "min", "value": 30 - i + (k % 3)})
    db.upsert_player_logs(conn, logs)
    conn.commit()
    roster = [{"player": "Nolan Smith", "position": "G"}, {"player": "Nikola Jokic", "position": "C"},
              {"player": "De'Aaron Fox", "position": "G"}, {"player": "Nobody Here", "position": "F"}]
    depth = teamdex.usage_depth(conn, "nba", roster)
    by = {pos["position"]: dict(zip(pos["players"], pos["usage"])) for pos in depth["positions"]}
    # The newest twenty games of each, whichever spelling the logs use;
    # a name with none sits at the bottom of the chart, as it always has.
    assert by["G"]["Nolan Smith"] > 0 and by["G"]["De'Aaron Fox"] > 0, by
    assert by["C"]["Nikola Jokic"] > 0 and by["F"]["Nobody Here"] == 0, by
    assert teamdex._name_prefixes("Nolan Smith Jr.") == {"Nolan S"}
    assert {"Dario Š", "Dario S"} <= teamdex._name_prefixes("Dario Šarić")
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT player, period, value FROM player_game_logs WHERE sport=? AND market=? "
        "AND player>=? AND player<? AND season>=?", ("nba", "min", "Nolan S", "Nolan S￿", 2025)))
    assert "SCAN" not in plan and "USING INDEX" in plan, plan



def test_each_read_says_how_it_was_answered():
    # The team endpoint's Server-Timing header carries these (2026-11-18): a cold college page
    # spent 25 of its 30 seconds in the squad, and only the box can say which read.
    conn = _history()
    teamdex.trace_start()
    teamdex.squad(conn, "cbb", "DUKE")
    steps = teamdex.trace_take()
    assert [s for s, _ms, _how in steps] == ["games", "keyed", "games", "keyed"], steps
    assert steps[1][2].startswith("2026 keys"), "the newest season, off the team's own game keys"
    assert all(ms >= 0 for _s, ms, _h in steps) and teamdex.trace_take() == [], "taken once"
    teamdex._note("keyed", 0.0, "x")
    assert teamdex.trace_take() == [], "nothing is kept while no one is recording"
    conn = _history(with_games=False)
    teamdex.trace_start()
    teamdex.squad(conn, "cbb", "DUKE")
    assert [s for s, _ms, _how in teamdex.trace_take()] == ["games", "season_scan", "games", "rows_scan"], \
        "with no games on file, the scans are named"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
