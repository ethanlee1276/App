"""Two things the off day before the Wild Card round showed (Ethan,
2026-09-28: "mlb isn't showing any post season games or anything like
that. The rankings didn't even update").

1. The MLB build built today alone, so an off day was an empty board. It
   now advances to the next day the league lists a playable game (up to
   MLB_LOOKAHEAD_DAYS), the way the college build has since August, and
   stamps `upcoming` for the page's banner.
2. The postseason start was one year's constant (Sept 30, 2025's). 2026's
   Wild Card round starts Sept 29: under the constant its first day would
   have counted in the regular-season table and been missing from the
   bracket. standings_build now asks the league's own calendar
   (engine/mlb/sources/mlbstats.season_dates) and sets engine/playoffs.
   POST_START; the constant is the fallback.

Offline: the stats API is stubbed; nothing here touches the network.

Run directly: `python3 tests/test_the_mlb_board_looks_ahead_and_the_postseason_starts_when_the_league_says.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import playoffs as P                                  # noqa: E402
from engine.mlb.sources import mlbstats as M                      # noqa: E402


def _day(date, *states):
    return {"date": date, "games": [{"status": {"codedGameState": s}} for s in states]}


def test_the_next_game_day_skips_blank_days_and_postponed_games():
    seen = {}

    def fake(url, cache, ttl=900, timeout=30):
        seen["url"], seen["cache"] = url, cache
        return {"dates": [_day("2026-09-29"), _day("2026-09-30", "D"), _day("2026-10-01", "P", "S")]}
    real = M._get_json
    M._get_json = fake
    try:
        assert M.next_game_day("2026-09-28", 5) == "2026-10-01", "a postponed-only day is not a slate"
        assert "startDate=2026-09-29&endDate=2026-10-03" in seen["url"]
        assert seen["cache"] == "mlb_schedule_2026-09-29_2026-10-03.json", "a prunable cache name"
        M._get_json = lambda *a, **k: {"dates": []}
        assert M.next_game_day("2026-09-28") is None
    finally:
        M._get_json = real


def test_the_build_moves_to_the_next_slate_and_says_so():
    src = (ROOT / "mlb_build.py").read_text(encoding="utf-8")
    assert "MLB_LOOKAHEAD_DAYS = 5" in src
    block = src[src.index("upcoming = None\n    if not slate.games:"):src.index("result = run_mlb_slate")]
    assert "nd = next_game_day(args.date, MLB_LOOKAHEAD_DAYS)" in block
    assert "nslate = build_live_slate(nd)" in block
    assert 'upcoming = {"date": nd, "days_ahead": ahead, "built_for": args.date}' in block
    assert "slate, args.date = nslate, nd" in block, "the odds, tracker and journal follow the slate built"
    assert 'if upcoming:\n            result["upcoming"] = upcoming' in src
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fn = js[js.index("function renderGames()"):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "const up = state.data.upcoming;" in fn and "No games today — this is the next slate" in fn, \
        "the page's banner reads the same field for every sport"


def test_the_season_dates_parse_and_the_postseason_start_can_be_set():
    got = M.parse_season_dates({"seasons": [{"regularSeasonStartDate": "2026-03-26",
                                             "regularSeasonEndDate": "2026-09-27",
                                             "postSeasonStartDate": "2026-09-29",
                                             "postSeasonEndDate": "2026-11-01"}]})
    assert got == {"regular_start": "2026-03-26", "regular_end": "2026-09-27",
                   "post_start": "2026-09-29", "post_end": "2026-11-01"}
    assert M.parse_season_dates({}) == {"regular_start": None, "regular_end": None,
                                        "post_start": None, "post_end": None}
    P.POST_START.pop(("mlb", 2026), None)
    try:
        assert P.is_postseason("mlb", 2026, "2026-09-29") is False, "the constant alone: Sept 30"
        P.set_post_start("mlb", 2026, got["post_start"])
        assert P.post_start("mlb", 2026).isoformat() == "2026-09-29"
        assert P.is_postseason("mlb", 2026, "2026-09-29") is True
        assert P.is_postseason("mlb", 2026, "2026-09-28") is False
        assert P.is_postseason("mlb", 2025, "2025-09-29") is False, "another season keeps its own start"
        assert P.is_postseason("nba", 2025, "2026-05-01") is True, "next-year leagues unchanged"
    finally:
        P.POST_START.pop(("mlb", 2026), None)


def test_the_standings_build_asks_the_league_first_and_keeps_the_constant_when_it_cannot():
    src = (ROOT / "standings_build.py").read_text(encoding="utf-8")
    assert 'first = (season_dates(season) or {}).get("post_start")' in src
    assert 'playoffs.set_post_start("mlb", season, first)' in src
    assert "calendar unreachable" in src
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    assert "mlb_season_" in PRUNABLE_CACHE_PREFIXES


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
