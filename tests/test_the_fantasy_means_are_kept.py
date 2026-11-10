"""The fantasy week's season means are kept between builds until the logs
change (engine/fantasy_lineup.season_means through engine/logcache.memo;
nfl_build.py's fantasy week).

The NFL build at 01:19 on 10 November, the box to itself: the fantasy week
took 4 seconds, 2.5 of them its season means, two aggregates over the box's
whole log table (`per_game` for last season and this) for numbers that
change only when a game is ingested. What these hold:

  * the kept means are exactly last season's `per_game` overlaid by this
    season's, as the build read them before;
  * a second build reads nothing; a new log row reads both again;
  * a read that fails is never kept, and the build gets the answer it
    always got (`per_game` answering ``{}``);
  * `per_game` without ``strict`` still answers ``{}`` on a failed read.

Run directly: `python3 tests/test_the_fantasy_means_are_kept.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, logcache                                    # noqa: E402
from engine import fantasy_lineup as FL                             # noqa: E402


def _row(season, wk, player, market, value, team="AAA", pos="WR"):
    return {"sport": "nfl", "season": season, "period": str(wk), "game_id": f"{team}-{season}-{wk}",
            "player": player, "team": team, "opponent": "BBB", "position": pos, "home": 1,
            "market": market, "value": value}


class _Kept:
    """A real history database in a scratch folder, the kept reads on."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.tmp.name, "feedstate")
        self.enabled, self.reads = logcache.enabled_for, []
        self.per_game = FL.per_game
        logcache.enabled_for = lambda c: True
        FL.per_game = lambda *a, **k: (self.reads.append(a[1]), self.per_game(*a, **k))[1]
        self.conn = db.connect(os.path.join(self.tmp.name, "history.db"))
        rows = [_row(2025, wk, "Old Hand", "fp_ppr", 10.0 + wk) for wk in range(1, 9)]
        rows += [_row(2025, wk, "Both Years", "fp_ppr", 5.0 + wk, team="CCC") for wk in range(1, 9)]
        rows += [_row(2026, wk, "Both Years", "fp_ppr", 20.0 + wk, team="DDD") for wk in range(1, 5)]
        rows += [_row(2026, wk, "Both Years", "rec_yds", 60.0 + wk, team="DDD") for wk in range(1, 5)]
        db.upsert_player_logs(self.conn, rows)
        self.conn.commit()
        return self

    def __exit__(self, *exc):
        FL.per_game, logcache.enabled_for = self.per_game, self.enabled
        self.conn.close()
        if self.old is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.old
        self.tmp.cleanup()


def test_the_kept_means_are_last_seasons_overlaid_by_this_ones():
    with _Kept() as k:
        means = FL.season_means(k.conn, 2026)
        plain = {**k.per_game(k.conn, 2025), **k.per_game(k.conn, 2026)}
    assert means == plain and set(means) == {"Old Hand", "Both Years"}
    assert means["Both Years"]["team"] == "DDD" and means["Old Hand"]["team"] == "AAA"
    assert means["Both Years"]["_games"] == 4, "this season's own games, not last season's"


def test_a_second_build_reads_nothing_and_a_new_row_reads_again():
    with _Kept() as k:
        first = FL.season_means(k.conn, 2026)
        assert k.reads == [2025, 2026], k.reads
        again = FL.season_means(k.conn, 2026)
        note = logcache.status()["fantasy_means.nfl"]
        assert k.reads == [2025, 2026] and note["kept"] is True and again == first, (k.reads, note)
        db.upsert_player_logs(k.conn, [_row(2026, 5, "Both Years", "fp_ppr", 31.0, team="DDD")])
        k.conn.commit()
        moved = FL.season_means(k.conn, 2026)
        note = logcache.status()["fantasy_means.nfl"]
        assert k.reads == [2025, 2026, 2025, 2026] and note["kept"] is False and note["why"] == "rows changed"
        assert moved["Both Years"]["_games"] == 5 and moved == {**k.per_game(k.conn, 2025),
                                                                **k.per_game(k.conn, 2026)}


def test_a_failed_read_is_never_kept():
    with _Kept() as k:
        real = k.per_game
        broke = {"on": True}

        def flaky(conn, season, markets=None, *, strict=False):
            if broke["on"] and season == 2026:
                if strict:
                    raise sqlite3.OperationalError("database is locked")
                return {}
            return real(conn, season, markets, strict=strict)
        FL.per_game = flaky
        got = FL.season_means(k.conn, 2026)
        assert got == real(k.conn, 2025), "the answer the build always got: last season alone"
        assert logcache.status().get("fantasy_means.nfl", {}).get("kept") is not True
        broke["on"] = False
        whole = FL.season_means(k.conn, 2026)
        assert whole == {**real(k.conn, 2025), **real(k.conn, 2026)}, "nothing was kept from the failure"


def test_per_game_without_strict_still_answers_nothing_on_a_failed_read():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert FL.per_game(conn, 2026) == {}, "no table: an empty answer, as before"
    try:
        FL.per_game(conn, 2026, strict=True)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("strict lets the failure through")


def test_the_build_reads_its_means_through_the_kept_read():
    src = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert "_fw_means = _fw_season_means(_fw_conn, args.season)" in src
    assert "_fw_per_game(" not in src


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
