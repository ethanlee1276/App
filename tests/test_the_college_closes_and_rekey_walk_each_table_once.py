"""The college build's closes read the tape once for the whole results
window, and the team re-key walks each table once, at most hourly
(engine/lineledger.closes_into_games, pregame_tape; engine/ingest.
remap_cfb_team_keys, remap_cfb_team_keys_paced).

The college build's part lines at 10:48 on 8 November put "teams + re-key"
at 19.1 seconds and "closes from the tape" at 17.8, two-fifths of its
"history + team ratings" stage:

  * each finished game in the two-week results window asked the tape for
    its own closing lines, and with no index leading on the event every ask
    walked every row the league had stored before that game's kickoff;
  * the re-key walked the games and the player logs twice each, every
    build, to find the same visiting FCS schools the teams feed can never
    map.

What these hold:

  * the closes written are the old per-game reads', column for column and
    count for count: a game with a published close, one missing a side, one
    priced only after kickoff, one never priced, a game twice in the list,
    rows of other books, markets, leagues and events, kickoffs that cannot
    be read;
  * the tape is read once for the window (more events than one read names
    take one read each);
  * the re-key finds and rewrites exactly the keys the four walks found,
    a capital ESPN: included, through one walk a table;
  * the paced re-key rests while its map and its hour hold, runs at once
    when the map grows, again after the hour, and when its note is lost.

Run directly: `python3 tests/test_the_college_closes_and_rekey_walk_each_table_once.py`
"""
import datetime as dt
import json
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import db, ingest as I, lineledger as LL                   # noqa: E402

TEAMS = ["MICH", "MSU", "OSU", "PSU", "UGA", "BAMA", "TEX", "OU", "espn:2", "espn:99"]


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:00Z")


def _world(seed=4):
    """A college season's tape and games table, and the build's game dicts."""
    rnd = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    games, tape = [], []
    day0 = dt.datetime(2026, 10, 24, 16, 0, tzinfo=dt.timezone.utc)
    import itertools
    pairs = list(itertools.permutations(TEAMS, 2))
    rnd.shuffle(pairs)
    for k in range(40):
        home, away = pairs[k]
        kick = day0 + dt.timedelta(days=7 * (k // 20), hours=rnd.choice([0, 3, 4, 7]))
        date = kick.strftime("%Y-%m-%d")
        gid = f"{away}@{home}"
        ev = f"{date}-{away}@{home}"
        kind = k % 8
        games.append({"completed": kind != 7, "kickoff": _iso(kick) if kind != 6 else "half past",
                      "date": date, "home": home, "away": away, "game_id": gid, "season": 2026})
        extra = json.dumps({"ml": [-150, 130]}) if kind == 1 else (json.dumps({"venue": "x"}) if kind == 2 else None)
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, spread, total, extra) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     ("cfb", 2026, date, gid, home, away,
                      -3.5 if kind in (1, 3) else None, 51.5 if kind == 1 else None, extra))
        if kind == 5:
            continue                                      # never priced
        for h in range(-72, 6, 6):                        # before and after kickoff
            t = _iso(kick + dt.timedelta(hours=h))
            if kind == 4 and h < 0:
                continue                                  # priced only once it started
            for book in (LL.BEST_BOOK, "draftkings"):
                for market, player, line, price in (("spread", home, -3.0 - h / 24, -110),
                                                    ("total", LL.TOTAL_KEY, 50.0 + h / 12, -110),
                                                    ("moneyline", home, 0.0, -150 + h),
                                                    ("moneyline", away, 0.0, 130 - h)):
                    if kind == 3 and market == "total":
                        continue                          # a side missing from the tape
                    tape.append(("cfb", t, ev, home, away, player, market, book, line, price, -110, None))
            tape.append(("cfb", t, ev, home, away, "Some Back", "rush_yds", LL.BEST_BOOK, 80.5, -110, -110, None))
            tape.append(("nfl", t, ev, home, away, home, "spread", LL.BEST_BOOK, -7.0, -110, -110, None))
    conn.executemany("INSERT OR REPLACE INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tape)
    games.append(dict(games[0]))                          # a game twice in the list
    return conn, games


def _old_closes(conn, sport, games):
    """The per-game read `closes_into_games` made until 8 November."""
    out = {"games": 0, "spread": 0, "total": 0, "ml": 0}
    for g in games or []:
        if not g.get("completed") or not g.get("kickoff"):
            continue
        try:
            kick = dt.datetime.fromisoformat(str(g["kickoff"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if kick.tzinfo is None:
            continue
        cut = kick.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
        home, away = g.get("home") or "", g.get("away") or ""
        event_id = f"{str(g.get('date') or '')[:10]}-{away}@{home}"
        last = {}
        for r in conn.execute(
                "SELECT market, player, line, over_odds FROM odds_history WHERE sport=? AND "
                "event_id=? AND book=? AND market IN ('spread','total','moneyline') AND taken_at<? "
                "ORDER BY taken_at", (sport, event_id, LL.BEST_BOOK, cut)):
            last[(r[0], r[1])] = (r[2], r[3])
        if not last:
            continue
        key = (sport, g.get("season") or 0, g.get("date") or "", g["game_id"])
        wrote = False
        for market, player, column in (("spread", home, "spread"), ("total", LL.TOTAL_KEY, "total")):
            got = last.get((market, player))
            if got is None or got[0] is None:
                continue
            cur = conn.execute(
                f"UPDATE games SET {column}=? WHERE sport=? AND season=? AND period=? AND game_id=? "
                f"AND {column} IS NULL", (float(got[0]), *key))
            out[column] += cur.rowcount
            wrote = wrote or cur.rowcount > 0
        hm, am = last.get(("moneyline", home)), last.get(("moneyline", away))
        if hm and am and hm[1] and am[1]:
            row = conn.execute("SELECT extra FROM games WHERE sport=? AND season=? AND period=? "
                               "AND game_id=?", key).fetchone()
            if row is not None:
                try:
                    extra = json.loads(row[0] or "{}") or {}
                except ValueError:
                    extra = {}
                if "ml" not in extra:
                    extra["ml"] = [int(hm[1]), int(am[1])]
                    extra["ml_source"] = "tape"
                    conn.execute("UPDATE games SET extra=? WHERE sport=? AND season=? AND period=? "
                                 "AND game_id=?", (json.dumps(extra, separators=(",", ":")), *key))
                    out["ml"] += 1
                    wrote = True
        out["games"] += int(wrote)
    conn.commit()
    return out


def _table(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT season, period, game_id, spread, total, extra FROM games ORDER BY game_id, period")]


def test_the_closes_written_are_the_old_reads_column_for_column():
    new_conn, games = _world()
    old_conn, _ = _world()
    got = LL.closes_into_games(new_conn, "cfb", games)
    want = _old_closes(old_conn, "cfb", games)
    assert got == want, (got, want)
    assert _table(new_conn) == _table(old_conn)
    assert got["games"] > 5 and got["spread"] and got["total"] and got["ml"], got
    assert LL.closes_into_games(new_conn, "cfb", games) == {"games": 0, "spread": 0, "total": 0, "ml": 0}, \
        "a second pass finds every close already in"
    assert LL.closes_into_games(new_conn, "cfb", []) == {"games": 0, "spread": 0, "total": 0, "ml": 0}


def test_the_tape_is_read_once_for_the_window():
    conn, games = _world()
    seen = []
    conn.set_trace_callback(seen.append)
    LL.closes_into_games(conn, "cfb", games)
    conn.set_trace_callback(None)
    reads = [s for s in seen if "FROM odds_history" in s]
    assert len(reads) == 1, reads
    keep = LL.TAPE_CHUNK
    LL.TAPE_CHUNK = 7
    try:
        conn2, games2 = _world()
        seen.clear()
        conn2.set_trace_callback(seen.append)
        LL.closes_into_games(conn2, "cfb", games2)
        conn2.set_trace_callback(None)
    finally:
        LL.TAPE_CHUNK = keep
    events = {f"{g['date']}-{g['away']}@{g['home']}" for g in games2
              if g["completed"] and g["kickoff"] != "half past"}
    assert len([s for s in seen if "FROM odds_history" in s]) == -(-len(events) // 7)


def _logs_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    rnd = random.Random(8)
    for k in range(60):
        home, away = rnd.choice(TEAMS + ["ESPN:61"]), rnd.choice(TEAMS)
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away) VALUES (?,?,?,?,?,?)",
                     ("cfb", 2025, f"2025-10-{k % 28 + 1:02d}", f"g{k}", home, away))
        for p in range(5):
            conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                         "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         ("cfb", 2025, f"2025-10-{k % 28 + 1:02d}", f"g{k}", f"P{k}-{p}",
                          home if p % 2 else away, away if p % 2 else home, "WR", 1, "rec_yds", 40.0))
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away) VALUES (?,?,?,?,?,?)",
                 ("nfl", 2025, "2025-10-01", "x", "espn:2", "BUF"))
    return conn


def _old_present(conn):
    present = set()
    for table, columns in (("games", ("home", "away")), ("player_game_logs", ("team", "opponent"))):
        for column in columns:
            for (value,) in conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE sport='cfb' "
                                         f"AND {column} LIKE ?", (I.ESPN_KEY_PREFIX + "%",)):
                present.add(str(value))
    return present


def _dump(conn):
    return ([tuple(r) for r in conn.execute("SELECT * FROM games ORDER BY sport, game_id")],
            [tuple(r) for r in conn.execute("SELECT * FROM player_game_logs ORDER BY game_id, player")])


def test_the_rekey_rewrites_exactly_what_the_four_walks_found_in_one_walk_a_table():
    mapping = {"2": "FCSU", "61": "UGA"}
    conn, ref = _logs_db(), _logs_db()
    present = _old_present(ref)
    assert {"espn:2", "espn:99", "ESPN:61"} <= present
    seen = []
    conn.set_trace_callback(seen.append)
    got = I.remap_cfb_team_keys(conn, mapping)
    conn.set_trace_callback(None)
    walks = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    assert len(walks) == 2, walks
    # The reference: the old walks' keys, rewritten the same way.
    for key in sorted(present):
        abbr = mapping.get(key[len(I.ESPN_KEY_PREFIX):])
        for table, columns in (("games", ("home", "away")), ("player_game_logs", ("team", "opponent"))):
            for column in columns:
                if abbr:
                    ref.execute(f"UPDATE {table} SET {column}=? WHERE sport='cfb' AND {column}=?", (abbr, key))
    assert _dump(conn) == _dump(ref)
    assert got["teams"] == 2 and got["unmapped"] == ["espn:99"], got
    assert conn.execute("SELECT home FROM games WHERE sport='nfl'").fetchone()[0] == "espn:2", "other leagues untouched"


def test_the_paced_rekey_rests_and_runs_when_it_should():
    path = str(Path(tempfile.mkdtemp()) / "rekey.json")
    conn = _logs_db()
    runs = []
    keep = I.remap_cfb_team_keys
    I.remap_cfb_team_keys = lambda c, m=None: runs.append(dict(m)) or {"teams": 0, "unmapped": ["espn:99"]}
    try:
        t0 = 1_794_150_000.0
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU"}, now=t0, path=path) is not None
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU"}, now=t0 + 600, path=path) is None, "rests"
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU", "61": "UGA"}, now=t0 + 900, path=path) is not None, \
            "a grown map runs at once"
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU", "61": "UGA"}, now=t0 + 1000, path=path) is None
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU", "61": "UGA"},
                                           now=t0 + 900 + I.REKEY_EVERY_S, path=path) is not None, "the hour is up"
        os.remove(path)
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU", "61": "UGA"},
                                           now=t0 + 900 + I.REKEY_EVERY_S + 5, path=path) is not None, "note lost"
        assert I.remap_cfb_team_keys_paced(conn, {"2": "FCSU", "61": "UGA"}, now=t0, path=path) is not None, \
            "a clock that went back runs"
    finally:
        I.remap_cfb_team_keys = keep
    assert len(runs) == 5 and runs[1] == {"2": "FCSU", "61": "UGA"}


def test_the_college_build_uses_the_paced_rekey():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert "_cfbingest.remap_cfb_team_keys_paced(_cfbdb.connect(), ids)" in src
    assert "remap_cfb_team_keys(_cfbdb.connect()" not in src


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
