"""The MLB game shelf measures itself on the next pass, not next Wednesday.

Ethan, 2026-09-15: "MLB most likely bets are only showing hits and
total bases. There is no money lines or pitchers props or game totals
or anything like that."

An MLB moneyline reaches the Most Likely board only once `engine.gamerank`
has written a figure into the rank store, and the only thing that wrote
one was the Wednesday block of the weekly pass — inside one try shared
with four prop measurements and a park report, any of which could raise
first and skip it. The prop shelves have had a bootstrap since 08-31
("measuring now, not Wednesday"); the game shelf now has the same, once
a day, with the marker written before the walk.

Run directly: `python3 tests/test_game_rank_bootstrap.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.maintenance import game_rank_boot_due            # noqa: E402

TODAY = dt.date(2026, 9, 15)


def _src():
    with open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8") as f:
        return f.read()


def test_an_empty_store_is_due():
    assert game_rank_boot_due({}, {}, TODAY)
    assert game_rank_boot_due(None, None, TODAY)


def test_a_prop_entry_alone_does_not_count_as_a_game_measurement():
    store = {"mlb:hits": {"auc": 0.71, "n": 9000}}
    assert game_rank_boot_due(store, {}, TODAY), \
        "a measured hits shelf says nothing about the moneyline"


def test_any_game_entry_for_the_sport_settles_it():
    store = {"mlb:total": {"auc": 0.49, "n": 1200, "kind": "game"}}
    assert not game_rank_boot_due(store, {}, TODAY), \
        "a sub-floor game figure IS a measurement — the weekly refits it"
    # Another sport's game entry is not this sport's.
    assert game_rank_boot_due({"nfl:moneyline": {"auc": 0.67, "kind": "game"}}, {}, TODAY)


def test_once_a_day_not_once_a_pass():
    state = {"game_rank_boot": {"mlb": TODAY.isoformat()}}
    assert not game_rank_boot_due({}, state, TODAY)
    assert game_rank_boot_due({}, state, TODAY + dt.timedelta(days=1))
    # A marker for another sport does not hold this one back.
    assert game_rank_boot_due({}, {"game_rank_boot": {"nba": TODAY.isoformat()}}, TODAY)


def test_the_pass_measures_with_the_marker_written_first():
    src = _src()
    at = src.index("if game_rank_boot_due(_grank_load(), state, today):")
    body = src[at:at + 1200]
    mark = body.index('state.setdefault("game_rank_boot", {})["mlb"] = today.isoformat()')
    save = body.index("_save_state(state_path, state)")
    work = body.index('_game_boot(_gbc, "mlb", log=log)')
    assert mark < save < work, "the marker must be on disk before the walk starts"
    assert "WHERE sport='mlb'" in body and "home_score IS NOT NULL" in body


def test_one_sports_failed_walk_no_longer_skips_the_game_markets():
    src = _src()
    at = src.index('for _sp in ("mlb", "wnba", "nba", "cfb"):')
    block = src[at:src.index("_rkc.close()", at)]
    assert "try:\n                        _rank_measure(_rkc, _sp, log=log)" in block
    assert 'log(f"  ⚠️  rank fit {_sp} skipped: {_rexc}")' in block
    assert "try:\n                    _rank_ctx(_rkc, \"mlb\", log=log)" in block
    assert block.index("_rank_ctx(") < block.index("_game_rank(_rkc, _sp, log=log)")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
