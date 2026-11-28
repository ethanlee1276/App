"""A player's tables lead with what he does (step AFW, 25 November 2026).

The game log's layout lists passing, rushing, receiving, and every table followed it: Amon-Ra St. Brown's two
carries all season put a Rushing group of zeros at the head of his game log, his Recent games and his career
table, with his catches off the right of a phone's screen; Travis Kelce's the same. ESPN's log for a receiver leads
with Receiving. Each table now puts the player's own group first (his role, engine/playerpage.role: his position,
else his volume), the rest in the layout's order: a receiver's receiving, a back's rushing, a passer's passing.

Offline. Run directly: `python3 tests/test_a_receivers_log_leads_with_receiving.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, gamelog as GL, playerpage as PP                 # noqa: E402


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    games = [("nfl", 2026, "009", "DET-009", "DET", "GB", 24, 20, "2026-11-02"),
             ("nfl", 2026, "010", "DET-010", "NE", "DET", 10, 35, "2026-11-09"),
             ("nfl", 2026, "011", "DET-011", "DET", "TB", 31, 21, "2026-11-16")]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", games)
    rows = []

    def log(period, gid, player, opp, pos, stats):
        for m, v in stats.items():
            rows.append(("nfl", 2026, period, gid, player, "DET", opp, pos, 1, m, v))
    wr = lambda r, t, y, c=0, ry=0: {"receptions": r, "targets": t, "rec_yds": y, "rec_td": 0,  # noqa: E731
                                     "carries": c, "rush_yds": ry, "rush_td": 0}
    log("009", "DET-009", "Amon-Ra St. Brown", "GB", "WR", wr(8, 11, 92))
    log("010", "DET-010", "Amon-Ra St. Brown", "NE", "WR", wr(6, 8, 71, c=1, ry=4))
    log("011", "DET-011", "Amon-Ra St. Brown", "TB", "WR", wr(5, 6, 37))
    for period, gid, opp in (("009", "DET-009", "GB"), ("010", "DET-010", "NE"), ("011", "DET-011", "TB")):
        log(period, gid, "Jahmyr Gibbs", opp, "RB", wr(4, 5, 30, c=15, ry=88))
        log(period, gid, "Jared Goff", opp, "QB", {"pass_cmp": 22, "pass_att": 30, "pass_yds": 260, "pass_td": 2,
                                                   "pass_int": 0, "carries": 2, "rush_yds": 3, "rush_td": 0})
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def test_the_game_log_leads_with_his_own_group():
    path = _history()
    keys = lambda name: [g["key"] for g in GL.season_log("nfl", name, db_path=path)["groups"]]  # noqa: E731
    assert keys("Amon-Ra St. Brown") == ["receiving", "rushing"], "one carry all season: receiving first, as ESPN's"
    assert keys("Jahmyr Gibbs") == ["rushing", "receiving"]
    assert keys("Jared Goff") == ["passing", "rushing"]
    log = GL.season_log("nfl", "Amon-Ra St. Brown", db_path=path)
    week10 = next(g for g in log["games"] if g.get("week") == 10)
    assert (week10["values"]["receiving.rec"], week10["values"]["rushing.car"]) == (6, 1), "each cell where it was"


def test_the_pages_tables_lead_with_it_too():
    PP._RANKS.clear()
    path = _history()
    d = PP.page("nfl", "Amon-Ra St. Brown", db_path=path, data_dir=tempfile.mkdtemp())
    assert d["role"] == "receiving"
    assert [g["key"] for g in d["career"]["groups"]] == ["receiving", "rushing"]
    assert [g["key"] for g in d["splits"]["groups"]] == ["receiving", "rushing"]
    back = PP.page("nfl", "Jahmyr Gibbs", db_path=path, data_dir=tempfile.mkdtemp())
    assert [g["key"] for g in back["career"]["groups"]] == ["rushing", "receiving"]


def test_with_no_role_the_layouts_order_stands():
    groups = [("rushing", "Rushing", ()), ("receiving", "Receiving", ())]
    assert GL.role_first(groups, "") == groups and GL.role_first(groups, "kicking") == groups
    assert [g[0] for g in GL.role_first(groups, "receiving")] == ["receiving", "rushing"]


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
