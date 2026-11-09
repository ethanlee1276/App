"""A finished game's pregame tape is walked once, then again only at the
recheck (engine/lineledger.closes_into_games, CLOSES_RECHECK_S).

The college build's "closes from the tape" was 6 to 11 seconds of every
build on 9 November, walking the league's whole pregame tape (no index
leads with the event) to find closes earlier builds had already written. A
finished game's pregame tape cannot grow: every row a build records after
kickoff is stamped after it, and only rows before kickoff count. What
these hold:

  * a build whose finished games were all walked within the recheck, with
    the same kickoffs, reads no tape and changes nothing, and what the
    games table holds is what walking every build would have left;
  * a newly finished game walks the window at once and gets its close;
  * a moved kickoff walks again;
  * past the recheck the window is walked again, so a line harvested later
    for a past game (harvest_odds.py) is still written;
  * a table that cannot be read leaves the walk as it always was.

Run directly: `python3 tests/test_a_finished_games_closes_are_walked_once.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import lineledger as LL                                   # noqa: E402


class _World:
    """The closes test's world (tests/test_the_college_closes_and_rekey_walk_
    each_table_once), imported when first asked for, as sibling tests are."""

    def __getattr__(self, name):
        import test_the_college_closes_and_rekey_walk_each_table_once as mod
        return getattr(mod, name)


W = _World()

T0 = 1_794_240_000.0
ZERO = {"games": 0, "spread": 0, "total": 0, "ml": 0}


def _reads(conn, games, now):
    seen = []
    conn.set_trace_callback(seen.append)
    try:
        got = LL.closes_into_games(conn, "cfb", games, now=now)
    finally:
        conn.set_trace_callback(None)
    return got, len([s for s in seen if "FROM odds_history" in s])


def test_a_build_inside_the_recheck_reads_no_tape_and_leaves_the_same_table():
    conn, games = W._world()
    every, _ = W._world()
    first, n1 = _reads(conn, games, T0)
    assert n1 == 1 and first["games"] > 5, (first, n1)
    LL.closes_into_games(every, "cfb", games, now=T0)
    for k in range(1, 6):
        got, n = _reads(conn, games, T0 + k * 600)
        assert (got, n) == (ZERO, 0), (k, got, n)
        LL.closes_into_games(every, "cfb", games, now=None)      # walking every build, as before
    assert W._table(conn) == W._table(every)


def test_a_newly_finished_game_walks_at_once_and_gets_its_close():
    conn, games = W._world()
    whole, _ = W._world()
    ev = lambda g: (g["date"], g["away"], g["home"])                       # noqa: E731
    untouched = {(r[1], r[2]): r for r in W._table(W._world()[0])}
    LL.closes_into_games(whole, "cfb", games, now=T0)
    written = {(r[1], r[2]) for r in W._table(whole) if untouched[(r[1], r[2])] != r}
    late = [i for i, g in enumerate(games)
            if (g["date"], g["game_id"]) in written and sum(ev(h) == ev(g) for h in games) == 1][-1]
    early = [dict(g) for g in games]
    early[late]["completed"] = False
    _reads(conn, early, T0)
    got, n = _reads(conn, games, T0 + 600)
    assert n == 1 and got["games"] == 1, (got, n)
    assert W._table(conn) == W._table(whole), "the same as one walk with the game finished"


def test_a_moved_kickoff_walks_again():
    conn, games = W._world()
    _reads(conn, games, T0)
    moved = [dict(g) for g in games]
    i = [k for k, g in enumerate(moved) if g["completed"] and g["kickoff"] != "half past"][0]
    moved[i]["kickoff"] = moved[i]["kickoff"].replace(":00:00Z", ":30:00Z")
    _got, n = _reads(conn, moved, T0 + 600)
    assert n == 1


def test_past_the_recheck_a_harvested_line_is_still_written():
    conn, games = W._world()
    _reads(conn, games, T0)
    g = next(g for g in games if g["completed"] and g["kickoff"] != "half past"
             and conn.execute("SELECT total FROM games WHERE game_id=? AND period=?",
                              (g["game_id"], g["date"])).fetchone()[0] is None)
    ev = f"{g['date']}-{g['away']}@{g['home']}"
    import datetime as dt
    taken = (dt.datetime.fromisoformat(g["kickoff"].replace("Z", "+00:00"))
             - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")
    conn.execute("INSERT OR REPLACE INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("cfb", taken, ev, g["home"], g["away"], LL.TOTAL_KEY, "total", LL.BEST_BOOK,
                  44.5, -110, -110, None))
    conn.commit()
    got, n = _reads(conn, games, T0 + 3600)
    assert (got, n) == (ZERO, 0), "inside the recheck: not yet"
    got, n = _reads(conn, games, T0 + LL.CLOSES_RECHECK_S + 60)
    assert n == 1 and got["total"] >= 1, (got, n)
    assert conn.execute("SELECT total FROM games WHERE game_id=? AND period=?",
                        (g["game_id"], g["date"])).fetchone()[0] == 44.5


def test_a_table_that_cannot_be_read_walks_as_before():
    conn, games = W._world()
    keep = LL.CLOSES_SEEN
    LL.CLOSES_SEEN = "CREATE TABLE closes_seen (nonsense"                 # unreadable
    try:
        a, n1 = _reads(conn, games, T0)
        b, n2 = _reads(conn, games, T0 + 600)
    finally:
        LL.CLOSES_SEEN = keep
    assert n1 == 1 and n2 == 1 and a["games"] > 5 and b == ZERO


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
