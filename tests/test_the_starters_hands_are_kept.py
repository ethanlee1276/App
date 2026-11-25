"""A season's starters' hands are read once for every hitter's page (step AHK, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". Each baseball hitter's page read the
season's every starting pitcher (about 4,900 rows) for its splits by the starter's hand: Juan Soto's "splits" part
was 369 ms on the live site. They are read in one step now and kept ten minutes per database file while no starter
is added, the same for every hitter.

Offline. Run directly: `python3 tests/test_the_starters_hands_are_kept.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, playerpage as PP  # noqa: E402


class _Seen:
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def test_the_hands_are_the_same_and_kept_until_a_starter_is_added():
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    conn.executemany("INSERT INTO game_starters (sport, season, period, game_id, team, pitcher, throws) "
                     "VALUES ('mlb', 2026, ?, ?, ?, ?, ?)",
                     [("2026-09-01", "g1", "NYY", "Gerrit Cole", "R"), ("2026-09-01", "g1", "BOS", "Garrett Crochet", "L"),
                      ("2026-09-02", "g2", "NYY", "Carlos Rodon", "L"), ("2026-09-02", "g3", "NYY", "Max Fried", "L"),
                      ("2026-09-03", "g4", "TOR", "Kevin Gausman", "r")])
    conn.commit()
    PP._HANDS.clear()
    first = _Seen(conn)
    hands = PP.starter_hands(first, 2026)
    assert hands == {("2026-09-01", "NYY"): "R", ("2026-09-01", "BOS"): "L", ("2026-09-03", "TOR"): "R"}, \
        "a doubleheader's two starters are neither, as before"
    again = _Seen(conn)
    assert PP.starter_hands(again, 2026) is hands
    assert not any("FROM game_starters WHERE" in s for s in again.sql), ("kept", again.sql)
    conn.execute("INSERT INTO game_starters (sport, season, period, game_id, team, pitcher, throws) "
                 "VALUES ('mlb', 2026, '2026-09-04', 'g5', 'BOS', 'Brayan Bello', 'R')")
    conn.commit()
    assert PP.starter_hands(conn, 2026)[("2026-09-04", "BOS")] == "R", "a starter added: read again"
    key = next(iter(PP._HANDS))
    at, top, kept = PP._HANDS[key]
    PP._HANDS[key] = (at - PP.HANDS_TTL - 1, top, kept)
    assert PP.starter_hands(conn, 2026) is not kept, "past its ten minutes: read again"
    PP._HANDS.clear()
    mem = D.connect(":memory:")
    assert PP.starter_hands(mem, 2026) == {} and not PP._HANDS, "a database in memory is never kept"


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
