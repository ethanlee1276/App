"""The board's player stats seek each player's last ten games in each market
instead of walking the whole table (engine/statlogs._query).

The single read (`_query_scan`) asked for every season of every priced
player sorted newest first, and SQLite answered by walking the table's key
backwards — every row the sport has — to keep ten a pair: 1.68 seconds on a
two-million-row copy of the table's shape, inside an 11-second part of the
NFL pricing stage at 09:16 on 8 November. What these hold:

  * the stats are the single read's, game for game and in the same order —
    a pair's games newest first with the game id breaking a doubleheader's
    tie, the players by their newest game with the name breaking a tie —
    on NFL weeks and on MLB dates, for a regular, a man back from a long
    injury whose ten span seasons, one too thin to chart, one never seen;
  * each pair is one seek of the (sport, market, player) index;
  * a file without that index is read the old way, and a broken one still
    raises rather than coming back empty.

Run directly: `python3 tests/test_the_player_stats_seek_each_player_and_market.py`
"""
import json
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, statlogs as S                                # noqa: E402


def _conn(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return c


def _nfl():
    rnd = random.Random(4)
    rows = []
    markets = [m for m, _ in S.SPORT_MARKETS["nfl"]]
    for season in (2023, 2024, 2025, 2026):
        for wk in range(1, 18 if season < 2026 else 10):
            for k in range(12):
                game = f"{season}_{wk:02d}_G{k % 4}"              # three men in each game: ties
                name = f"Player {k:02d}"
                if k == 7 and season > 2023:
                    continue                                      # hurt since 2023: his ten span seasons
                if k == 8 and not (season == 2026 and wk <= 2):
                    continue                                      # two games: too thin to chart
                for m in markets:
                    if k == 9 and m.startswith("pass"):
                        continue                                  # no passing rows at all
                    rows.append(("nfl", season, f"{wk:03d}", game, name, "BUF", "MIA", "WR",
                                 wk % 2, m, float(rnd.randint(0, 120))))
    return rows


def _mlb():
    rnd = random.Random(6)
    rows = []
    for d in range(1, 25):
        day = f"2026-07-{d:02d}"
        for k in range(6):
            games = [f"G{d}-{k % 3}"] + ([f"G{d}-{k % 3}b"] if d % 5 == 0 else [])   # doubleheaders
            for g in games:
                for m in ("hits", "total_bases", "strikeouts"):
                    rows.append(("mlb", 2026, day, g, f"Bat {k}", "NYY", "BOS", "OF", 1, m,
                                 float(rnd.randint(0, 4))))
    return rows


def _same(a, b):
    return json.dumps(a) == json.dumps(b)


def test_the_stats_are_the_single_reads_game_for_game_and_in_order():
    players = [f"Player {k:02d}" for k in range(12)] + ["Never Seen"]
    c = _conn(_nfl())
    got = S._query(c, "nfl", S.SPORT_MARKETS["nfl"], players)
    want = S._query_scan(c, "nfl", S.SPORT_MARKETS["nfl"], players)
    assert _same(got, want), "the same players, markets and games, in the same order"
    assert "Player 07" in got and "Player 08" not in got and "Never Seen" not in got
    old_man = got["Player 07"][S.SPORT_MARKETS["nfl"][0][1]]
    assert len(old_man) == S.N_GAMES and old_man[0]["week"] == 17, "his last ten, from 2023"
    assert all(not k.startswith("Pass") for k in got["Player 09"]), "no passing chip without passing rows"
    mlb = _conn(_mlb())
    bats = [f"Bat {k}" for k in range(6)]
    mlb_markets = (("hits", "Hits"), ("total_bases", "Total Bases"), ("strikeouts", "Strikeouts"))
    assert _same(S._query(mlb, "mlb", mlb_markets, bats), S._query_scan(mlb, "mlb", mlb_markets, bats)), \
        "a doubleheader's two games in the old order"


def test_each_pair_is_one_seek_of_the_player_index():
    c = _conn(_nfl())
    seen = []
    c.set_trace_callback(seen.append)
    S._query(c, "nfl", S.SPORT_MARKETS["nfl"], ["Player 01", "Player 02"])
    c.set_trace_callback(None)
    reads = [s for s in seen if "FROM player_game_logs" in s]
    assert len(reads) == 2 * len(S.SPORT_MARKETS["nfl"]) and all("LIMIT" in s for s in reads)
    plan = " ".join(str(tuple(r)) for r in c.execute(
        "EXPLAIN QUERY PLAN SELECT season FROM player_game_logs INDEXED BY idx_logs_lookup "
        "WHERE sport=? AND market=? AND player=? ORDER BY season DESC, period DESC, game_id DESC LIMIT 10",
        ("nfl", "rec_yds", "Player 01")))
    assert "idx_logs_lookup" in plan and "sport=? AND market=? AND player=?" in plan, plan


def test_a_file_without_the_index_is_read_the_old_way_and_a_broken_one_raises():
    players = [f"Player {k:02d}" for k in range(12)]
    c = _conn(_nfl())
    want = S._query_scan(c, "nfl", S.SPORT_MARKETS["nfl"], players)
    c.execute("DROP INDEX idx_logs_lookup")
    assert _same(S._query(c, "nfl", S.SPORT_MARKETS["nfl"], players), want)
    broken = sqlite3.connect(":memory:")
    try:
        S._query(broken, "nfl", S.SPORT_MARKETS["nfl"], players)
        raised = False
    except sqlite3.OperationalError:
        raised = True
    assert raised, "half a database is a broken machine: it says so"


def test_the_board_reads_the_same_through_a_file():
    path = Path(tempfile.mkdtemp()) / "history.db"
    c = db.connect(str(path))
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", _nfl())
    c.commit()
    c.close()
    recs = [{"player": f"Player {k:02d}"} for k in range(12)] + [{"player": None}, "not a row"]
    got = S.for_board(recs, "nfl", db_path=str(path))
    c = db.connect(str(path))
    want = S._query_scan(c, "nfl", S.SPORT_MARKETS["nfl"], sorted({f"Player {k:02d}" for k in range(12)}))
    c.close()
    assert _same(got, want) and len(got) == 11, "every player but the one too thin to chart"


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
