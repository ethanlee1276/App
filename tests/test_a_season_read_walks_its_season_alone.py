"""A read of one season's game logs walks that season's rows alone (step AEO, 24 November 2026).

The box's history file is never ANALYZEd, so SQLite chooses an index by the shape of a query alone, and three reads
that ask for one season chose an index that holds no season:

  * the stat spreads' values (engine/hoops_fit._read_values) and the team profiles' box columns
    (engine/nba/teams.load_rows) went through (sport, market, game_id, player): every stored season's rows of each
    market, each looked up in the table to be told its season. On the box that evening college basketball's 2026
    values took 35.1 seconds to read (about 410,000 rows), and its team profiles 40 seconds of a game-night build;
  * the fantasy file's season means (engine/fantasy_daily._season_rows) walked (sport, market, player, ...) for its
    grouping order, every season of the sport: the NHL's 2025 means took 39.3 seconds.

Each now leaves the market (or the grouping) to the row filter, and walks the table's own key (sport, season, ...).
What each answers is the same, a day's two games in the order the old index gave them. On a test history of five
college seasons (1,050,000 rows, all in memory) the reads ran 11, 9 and 2.7 times faster.

Offline. Run directly: `python3 tests/test_a_season_read_walks_its_season_alone.py`
"""
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, fantasy_daily as FD, hoops_fit as HF         # noqa: E402
from engine.nba import teams as T                                    # noqa: E402

BOX = ("min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb")
SEASON_KEY = "USING INDEX sqlite_autoindex_player_game_logs_1 (sport=? AND season=?)"


class _History:
    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        return self

    def __exit__(self, *exc):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def _fill(conn, seed=3):
    """Three college seasons, and one man with two games on one day (a doubleheader's two game ids)."""
    rnd = random.Random(seed)
    rows = []
    for season in (2024, 2025, 2026):
        for night in range(12):
            day = f"{season}-11-{night + 1:02d}"
            for a, b in (("DUKE", "UNC"), ("KU", "UK")):
                for team, opp in ((a, b), (b, a)):
                    for k in range(5):
                        for m in BOX:
                            rows.append({"sport": "cbb", "season": season, "period": day, "game_id": f"{season}-{night}-{a}",
                                         "player": f"{team} P{k}", "team": team, "opponent": opp, "position": "G",
                                         "home": int(team == a), "market": m, "value": float(rnd.randint(0, 25))})
    for gid, v in (("2026-dh-b", 9.0), ("2026-dh-a", 4.0)):
        rows += [{"sport": "cbb", "season": 2026, "period": "2026-11-20", "game_id": gid, "player": "DUKE P0",
                  "team": "DUKE", "opponent": "UNC", "position": "G", "home": 1, "market": m, "value": v} for m in BOX]
    db.upsert_player_logs(conn, rows)
    conn.commit()


def _plans(conn, fn):
    """The query plan of every read of the logs ``fn`` makes."""
    seen = []
    conn.set_trace_callback(seen.append)
    try:
        fn()
    finally:
        conn.set_trace_callback(None)
    return [" | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + s).fetchall())
            for s in seen if "FROM player_game_logs" in s and s.lstrip().upper().startswith("SELECT")]


def test_each_read_walks_the_season_on_a_file_with_no_statistics():
    with _History() as h:
        _fill(h.conn)
        for name, fn in (("stat spreads", lambda: HF._read_values(h.conn, "cbb", [2026])),
                         ("team profiles", lambda: T.load_rows(h.conn, "cbb", 2026)),
                         ("fantasy means", lambda: FD._season_rows(h.conn, "cbb", 2026))):
            plans = _plans(h.conn, fn)
            assert plans and all(SEASON_KEY in p for p in plans), (name, plans)


def _old_values(conn, seasons):
    """The read as it was before step AEO, ordered as its index gave the rows."""
    q = ("SELECT player, market, season, period, value FROM player_game_logs WHERE sport=? AND market IN (%s) "
         "AND season IN (%s)" % (",".join("?" * len(HF._READ)), ",".join("?" * len(seasons))))
    rows: dict = {}
    for r in conn.execute(q, ["cbb", *HF._READ, *seasons]):
        rows.setdefault((r["player"], r["market"]), []).append((int(r["season"]), str(r["period"]), float(r["value"])))
    return {k: [v for _s, _p, v in sorted(vals, key=lambda x: (x[0], x[1]))] for k, vals in rows.items()}


def test_the_answers_are_the_old_reads_and_a_days_two_games_keep_their_order():
    with _History() as h:
        _fill(h.conn)
        for seasons in ([2026], [2025, 2026], [2024]):
            assert HF._read_values(h.conn, "cbb", seasons) == _old_values(h.conn, seasons), seasons
        got = HF._read_values(h.conn, "cbb", [2026])[("DUKE P0", "pts")]
        assert got[-2:] == [4.0, 9.0], ("the season's last day, two games, in game-id order as the old index gave "
                                        "them", got)
        qs = ",".join("?" * len(T.BOX))
        old = sorted(tuple(r) for r in h.conn.execute(
            "SELECT period, team, opponent, market, value FROM player_game_logs "
            f"WHERE sport=? AND season=? AND market IN ({qs})", ("cbb", 2026, *T.BOX)))
        assert sorted(T.load_rows(h.conn, "cbb", 2026)) == old
        old_means = {(p, m): (n, a, pos) for p, m, n, a, pos in h.conn.execute(
            "SELECT player, market, COUNT(*), AVG(value), MAX(position) FROM player_game_logs "
            "WHERE sport=? AND season=? GROUP BY player, market", ("cbb", 2026))}
        new_means = FD._season_rows(h.conn, "cbb", 2026)
        assert set(new_means) == set(old_means)
        assert all(new_means[k][0] == old_means[k][0] and abs(new_means[k][1] - old_means[k][1]) < 1e-9
                   and new_means[k][2] == old_means[k][2] for k in old_means)


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
