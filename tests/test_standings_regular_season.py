"""The league standings feed is asked for the REGULAR season.

Ethan's box, 2026-09-05, five days before Week 1: the NFL standings
page carried 49 games, and the offense/defense rankings put Buffalo
first at 29.3 a game — August exhibition games, because ESPN's
standings answer with whatever season type is current when none is
named. The URL names type 2 now, and the cache file carries the type so
a cached preseason table can never be served as the regular one.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import leaguestandings as LS                        # noqa: E402

SRC = (ROOT / "engine" / "sources" / "leaguestandings.py").read_text()


def test_the_url_names_the_regular_season_and_the_cache_carries_it():
    seen = {}

    def fake(url, cache_name, **kw):
        seen["url"], seen["name"] = url, cache_name
        return {"children": []}

    real = LS.fetch_json
    LS.fetch_json = fake
    try:
        for sport in ("nfl", "cfb", "nba", "wnba"):
            LS.fetch(sport, 2026)
            assert "seasontype=2" in seen["url"], (sport, seen["url"])
            assert "season=2026" in seen["url"]
            assert seen["name"] == f"standings_{sport}_2026_t2.json", seen["name"]
    finally:
        LS.fetch_json = real


def test_baseball_is_untouched():
    """statsapi has no season type — its URL must not grow one."""
    seen = {}

    def fake(url, cache_name, **kw):
        seen["url"], seen["name"] = url, cache_name
        return {"records": []}

    real = LS.fetch_json
    LS.fetch_json = fake
    try:
        LS.fetch("mlb", 2026)
        assert "seasontype" not in seen["url"] and seen["name"] == "standings_mlb_2026.json"
    finally:
        LS.fetch_json = real


def test_the_reason_is_beside_the_parameter():
    assert "?season={season}&seasontype=2" in SRC
    assert "PRESEASON table" in SRC and "49 exhibition games" in SRC


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
