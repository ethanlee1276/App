"""The prop tape reads only the watched men's rows, and the line-movement
tapes sort the day's snapshots by prop once (engine/proptape.last_seen,
engine/linemoves.attach_series).

The NFL build's new part lines at 10:45 on 8 November named two jobs that
read far more than they kept:

  * the prop tape (16.1 of the prices stage's 17.3 seconds) read every row
    the league had stored in ten days to find the last price of the men it
    watches, and the game lines share that table: every game's spread,
    total and moneylines at every book, on every build, all week;
  * the line-movement stamps (15.0 of the pipeline's 15.5) asked every
    snapshot since midnight, every league's, once for each of about six
    hundred picks.

What these hold:

  * the prop tape's last prices are the old read's, key for key, through
    ties on the time (the event id decides, a missing one first, then the
    order written), the ten-day edge, other leagues, men nobody watches,
    and more men than one lookup names;
  * each lookup goes through the (sport, player, taken_at) index and never
    names a game line; a file without that index is read the old way, and
    one without the table still answers nothing, as before;
  * the rows the tape writes are the ones it wrote;
  * every pick's tape is the old walk's, a tie on price included (the walk
    kept the first row it met), and picks with no side, no market, a
    broken name or a row that is not a snapshot are treated as before;
  * the day's rows are walked once, whatever the number of picks.

Run directly: `python3 tests/test_the_prop_tape_and_the_line_tapes_read_only_their_own_rows.py`
"""
import copy
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, linemoves as L, proptape as P                 # noqa: E402

NOW = dt.datetime(2026, 11, 8, 15, 45, tzinfo=dt.timezone.utc)
BOOKS = ["draftkings", "fanduel", "betmgm", "caesars", "pinnacle", "espnbet"]
MARKETS = ["rec_yds", "receptions", "rush_yds", "anytime_td"]
TEAMS = ["BUF", "MIA", "KC", "DEN", "PHI", "DAL"]


def _name(k: int) -> str:
    """A man as the tape stores him: the books' spelling (`proptape._norm`)."""
    return P._norm(f"Player {k:03d}")


def _at(days_ago: float) -> str:
    return (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:00Z")


def _tape_db(players=40, seed=3):
    rnd = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    rows = []
    for step in range(0, 13 * 24 * 6, 7):                 # every 70 minutes for 13 days
        ago = step / (24 * 6)
        for k in range(0, len(TEAMS), 2):                 # the game lines, every book, every build
            home, away = TEAMS[k], TEAMS[k + 1]
            ev = f"2026-11-08-{away}@{home}"
            for b in BOOKS:
                rows.append(("nfl", _at(ago), ev, home, away, home, "spread", b,
                             -3.5, -110, -110, None))
                rows.append(("nfl", _at(ago), ev, home, away, "__total__", "total", b,
                             44.5, -110, -110, None))
    for p in range(players):
        name = _name(p)
        for step in range(rnd.randint(1, 12)):
            ago = rnd.uniform(0, 12)                      # some past the ten days
            m, b = rnd.choice(MARKETS), rnd.choice(BOOKS)
            ev = rnd.choice(["2026-11-08-MIA@BUF", "a1b2c3d4e5", "2026-11-08-DEN@KC"])
            rows.append(("nfl", _at(ago), ev, "BUF", "MIA", name, m, b,
                         float(rnd.choice([24.5, 30.5, 0.5])), rnd.choice([-120, -110, 105]),
                         rnd.choice([-110, 100, None]), None))
    # A tie on the time: two events at one instant (the harvest's hex id and
    # our own label), and two rows with no event id at all.
    t = _at(1.0)
    rows.append(("nfl", t, "2026-11-08-MIA@BUF", "BUF", "MIA", _name(1), "rec_yds", "fanduel",
                 61.5, -115, -105, None))
    rows.append(("nfl", t, "9f9f9f", "BUF", "MIA", _name(1), "rec_yds", "fanduel", 63.5, -110, -110, None))
    rows.append(("nfl", t, None, "BUF", "MIA", _name(2), "receptions", "betmgm", 4.5, -130, 110, None))
    rows.append(("nfl", t, None, "BUF", "MIA", _name(2), "receptions", "betmgm", 5.5, -105, -115, None))
    for ago in (0.5, 2.0, 11.0):                          # another league, the same names
        rows.append(("nba", _at(ago), "x", "BOS", "NYK", _name(3), "rec_yds", "fanduel",
                     1.5, -110, -110, None))
    conn.executemany("INSERT OR REPLACE INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return conn


def _since():
    return (NOW - dt.timedelta(days=P.WATCH_DAYS)).strftime("%Y-%m-%dT%H:%M:00Z")


def test_the_last_prices_are_the_old_reads_key_for_key():
    conn = _tape_db()
    sets = [{_name(1)}, {_name(2), _name(3), "nobody"},
            {_name(p) for p in range(40)},
            {_name(p) for p in range(1300)},              # more than one lookup names
            {"BUF", _name(4)}]                            # a team's name is watched only if asked for
    for players in sets:
        got = P.last_seen(conn, "nfl", players, NOW)
        want = P._last_seen_scan(conn, "nfl", players, _since())
        assert got == want, sorted(set(got.items()) ^ set(want.items()))[:5]
    every = P.last_seen(conn, "nfl", {_name(p) for p in range(40)}, NOW)
    assert every[(_name(1), "rec_yds", "fanduel")] == (63.5, -110, -110), "the later event id at a tie"
    assert every[(_name(2), "receptions", "betmgm")] == (5.5, -105, -115), "the later of two with none"
    assert P.last_seen(conn, "nfl", set(), NOW) == {}


def test_each_lookup_goes_through_the_player_index():
    conn = _tape_db()
    seen = []
    conn.set_trace_callback(seen.append)
    players = {_name(p) for p in range(1300)}
    P.last_seen(conn, "nfl", players, NOW)
    conn.set_trace_callback(None)
    reads = [s for s in seen if "FROM odds_history" in s]
    chunks = -(-len(players) // P.LOOKUP_CHUNK)
    assert len(reads) == chunks and all("INDEXED BY idx_odds_hist_player" in s and "player IN" in s
                                        for s in reads), reads
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT line FROM odds_history INDEXED BY idx_odds_hist_player "
        "WHERE sport=? AND player IN (?, ?) AND taken_at >= ?", ("nfl", _name(1), _name(2), _since())))
    assert "idx_odds_hist_player" in plan and "player=?" in plan, plan


def test_a_file_without_the_index_reads_the_old_way_and_one_without_the_table_answers_nothing():
    conn = _tape_db()
    players = {_name(p) for p in range(40)}
    want = P._last_seen_scan(conn, "nfl", players, _since())
    conn.execute("DROP INDEX idx_odds_hist_player")
    assert P.last_seen(conn, "nfl", players, NOW) == want
    assert P.last_seen(sqlite3.connect(":memory:"), "nfl", players, NOW) == {}


def test_the_rows_the_tape_writes_are_the_ones_it_wrote():
    import types
    conn = _tape_db()
    games = [types.SimpleNamespace(home="BUF", away="MIA", date="2026-11-08", kickoff="13:00")]
    stored = P._last_seen_scan(conn, "nfl", {_name(p) for p in range(40)}, _since())
    # Tonight's slate off what is stored: every other price unchanged, the
    # rest moved a point, and a few men the tape has never seen.
    by_prop: dict = {}
    for i, ((who, market, book), (line, over, under)) in enumerate(sorted(stored.items())):
        moved = i % 2 == 1
        by_prop.setdefault((who, market), []).append(types.SimpleNamespace(
            book=book, line=line + (1.0 if moved else 0.0), over_odds=over, under_odds=under))
    props = [types.SimpleNamespace(player=who, market=m, team="BUF", lines=lines)
             for (who, m), lines in sorted(by_prop.items())]
    props += [types.SimpleNamespace(player=_name(900 + k), market="rec_yds", team="MIA",
                                    lines=[types.SimpleNamespace(book="fanduel", line=50.5,
                                                                 over_odds=-110, under_odds=-110)])
              for k in range(3)]
    slate = types.SimpleNamespace(games=games, props=props)
    watch = {_name(p) for p in range(0, 40, 2)} | {_name(900), _name(901)}
    new = P.rows_for("nfl", slate, watch, P.last_seen(conn, "nfl", watch, NOW), NOW)
    old = P.rows_for("nfl", slate, watch, P._last_seen_scan(conn, "nfl", watch, _since()), NOW)
    assert new == old, "the same moved prices, in the same order"
    offered = sum(len(x.lines) for x in props if P._norm(x.player) in watch)
    assert 0 < len(new) < offered, (len(new), offered)
    assert {r["player"] for r in new} >= {_name(900), _name(901)}, "a man never seen is written"


def _snapshots(seed=5):
    rnd = random.Random(seed)
    rows = []
    for k in range(10):
        ts = 1794100000.0 + k * 1800
        for p in range(30):
            for m in ("rec_yds", "receptions"):
                for b in BOOKS:
                    rows.append({"ts": ts, "player": f"Player {p:03d}", "market": m, "book": b,
                                 "line": rnd.choice([24.5, 30.5]),
                                 "over_odds": rnd.choice([-110, -110, 100, None]),
                                 "under_odds": rnd.choice([-110, 100, -110])})
    rows += [{"ts": 1794100000.0, "player": "Player 001", "market": "rec_yds", "book": "x"},  # no line
             {"ts": "soon", "player": "Player 001", "market": "rec_yds", "book": "x", "line": 1},
             {"ts": 1794100001.0, "player": ["not", "a", "name"], "market": "rec_yds", "line": 2.5},
             {"ts": 1794100002.0, "player": None, "market": "rec_yds", "line": 2.5}]
    return rows


def _picks():
    picks = [{"player": f"Player {p:03d}", "market": m, "side": s}
             for p in range(0, 34) for m, s in (("rec_yds", "OVER"), ("receptions", "UNDER"))]
    picks += [{"player": "Player 001", "market": "rec_yds", "side": "YES"},
              {"player": "Player 002", "market": "rec_yds", "side": "OVER", "has_market": False},
              {"market": "rec_yds", "side": "OVER"},
              {"player": "Player 003", "side": "UNDER"},
              {"player": ["not", "a", "name"], "market": "rec_yds", "side": "OVER"},
              {"player": "Player 004", "market": "rec_yds", "side": "OVER"}]       # twice
    return picks


def _old_attach(recs, rows):
    n = 0
    for rec in recs:
        if rec.get("has_market") is False or rec.get("side") not in ("OVER", "UNDER"):
            continue
        series = L.prop_series(rows, rec.get("player", ""), rec.get("market", ""), rec["side"])
        if len(series) >= 2:
            rec["line_series"] = series
            n += 1
    return n


def test_every_picks_tape_is_the_old_walks():
    rows = _snapshots()
    new, old = copy.deepcopy(_picks()), copy.deepcopy(_picks())
    assert L.attach_series(new, rows) == _old_attach(old, rows) > 50
    assert json.dumps(new, sort_keys=True) == json.dumps(old, sort_keys=True)
    # A tie on price at one instant: the walk kept the first book it met.
    tie = [{"ts": 1.0, "player": "A", "market": "m", "book": "first", "line": 5.5, "over_odds": 100},
           {"ts": 1.0, "player": "A", "market": "m", "book": "second", "line": 5.5, "over_odds": 100},
           {"ts": 2.0, "player": "A", "market": "m", "book": "second", "line": 5.5, "over_odds": 100}]
    rec = [{"player": "A", "market": "m", "side": "OVER"}]
    L.attach_series(rec, tie)
    assert rec[0]["line_series"][0]["book"] == "first"


class _Counted(list):
    walks = 0

    def __iter__(self):
        type(self).walks += 1
        return super().__iter__()


def test_the_days_rows_are_walked_once():
    rows = _Counted(_snapshots())
    _Counted.walks = 0
    assert L.attach_series(copy.deepcopy(_picks()), rows) > 50
    assert _Counted.walks == 1, _Counted.walks
    _Counted.walks = 0
    assert L.attach_series([{"player": "A", "market": "m", "side": "YES"}], rows) == 0
    assert _Counted.walks == 0, "no pick that could carry a tape, no walk"


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
