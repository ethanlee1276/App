"""The box-score ingest finds a game's rows by its season, through the
history file's primary key (engine/boxsettle._season_terms,
has_official_rows, purge_provisional).

The settle pass's own sampler at 20:52 on Saturday 7 November: the college
box-score pull took 43.4 seconds, 39.3 of them `has_official_rows`. It asked
for each finished game by sport, day and id, and no index on the history
file starts (sport, period): the primary key puts the season second and
every other index the market. So every finished college game on an open
prop's day read the sport's whole stored history, every five minutes. What
these hold:

  * a game's official rows are found whether filed under its season or a
    year either side (a January bowl's label), and its provisional rows are
    not taken for official ones;
  * the NFL's ids (a team and its week) repeat every season, so only the
    game's own season counts, as before;
  * the provisional rows are purged for that game alone, official rows and
    other games untouched;
  * each lookup is a search of the primary key with its season, never a
    scan; a game row without a season asks as it did.

Run directly: `python3 tests/test_the_box_score_lookups_read_by_season.py`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B, db                              # noqa: E402

DAY = "2026-11-07"


def _row(sport, season, period, game_id, player, market="rush_yds", value=50.0):
    return {"sport": sport, "season": season, "period": period, "game_id": game_id, "player": player,
            "team": "MICH", "opponent": "MSU", "position": "RB", "home": 1, "market": market,
            "value": value}


def _history():
    h = db.connect(Path(tempfile.mkdtemp()) / "h.db")
    rows = []
    for season in range(2022, 2027):
        for g in range(40):
            day = f"{season}-10-{1 + g % 28:02d}"
            for p in range(6):
                rows.append(_row("cfb", season, day, f"40{season}{g:03d}", f"Player {p}"))
    db.upsert_player_logs(h, rows)
    h.commit()
    return h


class _Seen:
    """The connection, every statement it is handed written down."""

    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append((sql, tuple(args)))
        return self.conn.execute(sql, args)


def _plan(conn, sql, args) -> str:
    return " | ".join(str(r[-1]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args).fetchall())


def test_a_games_official_rows_are_found_under_its_season_or_a_year_either_side():
    h = _history()
    g = {"season": 2026, "period": DAY, "game_id": "401999"}
    assert not B.has_official_rows(h, "cfb", g)
    db.upsert_player_logs(h, [_row("cfb", 2026, DAY, "401999" + B.BOX_SUFFIX, "Donovan Edwards")])
    assert not B.has_official_rows(h, "cfb", g), "a provisional row is not an official one"
    for season in (2025, 2027, 2026):
        db.upsert_player_logs(h, [_row("cfb", season, DAY, "401999", f"Back {season}")])
        assert B.has_official_rows(h, "cfb", g), season
        h.execute("DELETE FROM player_game_logs WHERE game_id='401999' AND season=?", (season,))
    assert not B.has_official_rows(h, "cfb", g)
    assert not B.has_official_rows(h, "cfb", dict(g, period="2026-11-08")), "another day"


def test_the_nfl_counts_only_the_games_own_season():
    h = _history()
    g = {"season": 2026, "period": "010", "game_id": "x", "home": "BUF", "away": "MIA"}
    db.upsert_player_logs(h, [_row("nfl", 2025, "010", "BUF-010", "Josh Allen")])
    assert not B.has_official_rows(h, "nfl", g), "last season's week ten is not this one's"
    db.upsert_player_logs(h, [_row("nfl", 2026, "010", "MIA-010", "Tua Tagovailoa")])
    assert B.has_official_rows(h, "nfl", g)


def test_the_provisional_rows_are_purged_for_that_game_alone():
    h = _history()
    g = {"season": 2026, "period": DAY, "game_id": "401999"}
    db.upsert_player_logs(h, [
        _row("cfb", 2026, DAY, "401999" + B.BOX_SUFFIX, "Donovan Edwards"),
        _row("cfb", 2026, DAY, "401999" + B.BOX_SUFFIX, "Donovan Edwards", market="receptions", value=2),
        _row("cfb", 2026, DAY, "401999", "Donovan Edwards"),
        _row("cfb", 2026, DAY, "401888" + B.BOX_SUFFIX, "Someone Else")])
    assert B.purge_provisional(h, "cfb", g) == 2
    left = {(r[0], r[1]) for r in h.execute("SELECT game_id, market FROM player_game_logs "
                                            "WHERE period=?", (DAY,))}
    assert left == {("401999", "rush_yds"), ("401888" + B.BOX_SUFFIX, "rush_yds")}, left
    nfl = {"season": 2026, "period": "010", "game_id": "x", "home": "BUF", "away": "MIA"}
    db.upsert_player_logs(h, [_row("nfl", 2026, "010", "BUF-010" + B.BOX_SUFFIX, "Josh Allen"),
                              _row("nfl", 2025, "010", "BUF-010" + B.BOX_SUFFIX, "Josh Allen")])
    assert B.purge_provisional(h, "nfl", nfl) == 1, "this season's week ten only"


def test_each_lookup_searches_the_primary_key_by_season():
    h = _history()
    seen = _Seen(h)
    B.has_official_rows(seen, "cfb", {"season": 2026, "period": DAY, "game_id": "401999"})
    B.purge_provisional(seen, "cfb", {"season": 2026, "period": DAY, "game_id": "401999"})
    B.has_official_rows(seen, "nfl", {"season": 2026, "period": "010", "home": "BUF", "away": "MIA"})
    assert len(seen.sql) == 3
    for sql, args in seen.sql:
        plan = _plan(h, sql, args)
        # Before: "... sqlite_autoindex_player_game_logs_1 (sport=?)", the
        # sport's every stored season walked for one game.
        assert "SCAN" not in plan and "sqlite_autoindex_player_game_logs_1" in plan, (sql, plan)
        assert "(sport=? AND season=? AND period=? AND game_id=?)" in plan, (sql, plan)
    # A game row with no season asks as it did.
    seen = _Seen(h)
    assert not B.has_official_rows(seen, "cfb", {"season": None, "period": DAY, "game_id": "401999"})
    assert "season" not in seen.sql[0][0]


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
