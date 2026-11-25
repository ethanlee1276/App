"""A role chart reads its team's games, not the league's week (step AGG, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load". A player's role chart says his share of his team's
targets and carries (NFL) or carries and catches (college) game by game, off his team's totals (engine/role
._shares). Left to itself SQLite read those totals off the week's index (sport, market, period): every player's
targets and carries league-wide in each of his weeks, each row a seek of its own, his team's kept at the end.
Jahmyr Gibbs's role chart took 26.4 s on the live site, 1.4 s of it the server's own work. The team's index
(engine/db.TEAM_INDEX, built on the box once, step AES) reads his team's games alone; a file without it reads as
before, and either way the shares are the same.

Offline. Run directly: `python3 tests/test_a_role_chart_reads_its_teams_games.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, role  # noqa: E402


def _history(team_index=True):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = db.connect(path)
    if team_index:
        conn.execute(db.TEAM_INDEX_SQL)
    rows = []
    for week, opp in (("010", "GB"), ("011", "NYG")):
        for player, team, tgt, car in (("Jahmyr Gibbs", "DET", 4, 15), ("Amon-Ra St. Brown", "DET", 9, 0),
                                       ("Sam LaPorta", "DET", 5, 0), ("Saquon Barkley", "PHI", 3, 20),
                                       ("A.J. Brown", "PHI", 10, 0)):
            for market, value in (("targets", tgt), ("carries", car), ("snap_pct", 70)):
                rows.append(("nfl", 2026, week, f"g{week}{team}", player, team, opp, "RB", 1, market, value))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


class _Seen:
    """A connection that keeps every statement it ran."""
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def _games():
    return [{"period": "010", "team": "DET", "v": {"tgt": 4.0, "car": 15.0}},
            {"period": "011", "team": "DET", "v": {"tgt": 4.0, "car": 15.0}}]


def test_the_shares_read_the_teams_index():
    conn = _history()
    seen = _Seen(conn)
    games = _games()
    role._shares(seen, "nfl", 2026, games)
    sql = next(s for s in seen.sql if "SUM(value)" in s)
    args = ("nfl", 2026, "targets", "carries", "010", "011", "DET")
    plan = " ".join(str(r[3]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args))
    assert "idx_logs_team" in plan, plan
    assert games[0]["v"]["tgt_sh"] == round(4 / 18, 4) and games[0]["v"]["car_sh"] == 1.0, games[0]["v"]


def test_a_file_without_the_index_reads_as_before_and_says_the_same():
    with_index, without = _games(), _games()
    role._shares(_history(True), "nfl", 2026, with_index)
    role._shares(_history(False), "nfl", 2026, without)
    assert with_index == without and without[1]["v"]["tgt_sh"] == round(4 / 18, 4)


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
