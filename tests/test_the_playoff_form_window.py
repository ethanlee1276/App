"""A hitter's recent form in October includes his October games.

The site audit, 2026-09-24 (docs/AUDIT_2026-09-24.md, H-4's known limit).
`stats=gameLog` answers with regular-season games unless asked for another
game type, so a hitter's "last five" in the playoffs were his last five of
September. `statslogs.with_postseason` adds the postseason's games to the
regular log when the slate is a postseason one — additive only, so an
empty or failed answer changes nothing.
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.mlb.sources import statslogs as SL                   # noqa: E402


def _log(*games):
    return {"stats": [{"splits": [
        {"date": d, "game": {"gamePk": pk}, "stat": {"totalBases": tb},
         "opponent": {"abbreviation": "NYY"}, "isHome": True}
        for d, pk, tb in games]}]}


def test_playoff_games_join_the_log_in_date_order_once():
    reg = _log(("2026-09-26", 1, 1), ("2026-09-27", 2, 0))
    post = _log(("2026-09-30", 9, 4), ("2026-10-01", 10, 2), ("2026-09-27", 2, 0))
    merged = SL.with_postseason(reg, post)
    dates = [sp["date"] for sp in merged["stats"][0]["splits"]]
    assert dates == ["2026-09-26", "2026-09-27", "2026-09-30", "2026-10-01"], dates
    logs = SL.parse_game_log(merged, SL.TOTAL_BASES, limit=2)
    assert [g.value for g in logs] == [2.0, 4.0], "the newest games are the playoff ones"
    assert len(reg["stats"][0]["splits"]) == 2, "the regular answer is not mutated"


def test_an_empty_or_missing_postseason_changes_nothing():
    reg = _log(("2026-09-26", 1, 1))
    assert SL.with_postseason(reg, {}) is reg
    assert SL.with_postseason(reg, {"stats": []}) is reg
    assert SL.with_postseason(reg, _log()) is reg


def test_only_a_postseason_slate_asks_and_a_failure_is_not_fatal():
    src = inspect.getsource(SL.build_live_slate)
    assert 'in POSTSEASON_TYPES' in src and 'if postseason:' in src
    assert SL.POSTSEASON_TYPES == {"F", "D", "L", "W"}, "the regular season is R and asks nothing more"
    add = inspect.getsource(SL._add_prop)
    assert 'fetch_game_log(person_id, group, season, "P")' in add
    i = add.index('fetch_game_log(person_id, group, season, "P")')
    assert "except DataUnavailable:" in add[i:i + 200]


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
