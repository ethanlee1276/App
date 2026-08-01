"""More history must not silently rewrite what "this season" means.

Backfilling 2021-2026 was supposed to help — deeper variance fits, real
calibration, walk-forward backtests. But two live code paths read the
history table with no season bound, which was *correct by accident* while
only the current season was ingested. The moment the backfill landed they
started answering a different question:

  * MLB form blends a "season" window at 20%; unbounded, that window
    became a six-year career average.
  * CFB team ratings would rate a roster that turns over ~25% a year on
    players who have graduated.

These tests pin the season bound so a future refactor cannot quietly
widen it again.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_player_logs
from engine.mlb.bookmenu import logs_by_player, add_book_listed_props


def _log(season, day, player, value, team="NYY", opponent="BOS"):
    return {"sport": "mlb", "season": season, "period": f"{season}-0{day}",
            "game_id": f"{season}{day}", "player": player, "team": team,
            "opponent": opponent, "position": "OF", "home": 1,
            "market": "total_bases", "value": value}


def _seed():
    """A player who was excellent years ago and ordinary now."""
    conn = connect(":memory:")
    rows = [_log(2021, d, "Old Timer", 4.0) for d in range(1, 6)]
    rows += [_log(2026, d, "Old Timer", 1.0) for d in range(1, 6)]
    upsert_player_logs(conn, rows)
    return conn


def test_logs_by_player_bounds_to_the_requested_season():
    conn = _seed()
    rec = logs_by_player(conn, "total_bases", seasons=[2026])["old timer"]
    assert len(rec["logs"]) == 5
    # Every log is from 2026 — none of the 4.0s from five years ago.
    assert all(g.value == 1.0 for g in rec["logs"])
    assert all(g.date.startswith("2026") for g in rec["logs"])


def test_unbounded_call_still_returns_everything():
    """The backtest wants all of it; only the live path narrows."""
    conn = _seed()
    rec = logs_by_player(conn, "total_bases")["old timer"]
    assert len(rec["logs"]) == 10


def test_book_menu_prop_carries_only_current_season_form():
    """The whole point: a prop built from the book's menu must project the
    player who exists now, not his 2021 self."""
    conn = _seed()

    class _Slate:
        props: list = []

    slate = _Slate()
    slate.props = []
    book_only = [{"player": "Old Timer", "market": "total_bases",
                  "home": "NYY", "away": "BOS",
                  "lines": [{"book": "dk", "line": 1.5,
                             "over_odds": -110, "under_odds": -110}]}]
    added = add_book_listed_props(slate, book_only, conn, seasons=[2026])
    assert added == 1
    prop = slate.props[0]
    assert len(prop.logs) == 5
    # career_avg here is the average of the logs handed in. Season-scoped
    # that is 1.0; unbounded it would be 2.5 and the prop would look like a
    # screaming over on a 1.5 line.
    assert abs(prop.career_avg - 1.0) < 1e-6


def test_cfb_ratings_are_fit_on_one_season():
    """`cfb_build` must scope team ratings to the season being built.

    Read at the source level on purpose: the alternative is standing up a
    full CFB build, and what needs pinning is one argument.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "cfb_build.py")).read()
    i = src.index("compute_team_ratings(conn, \"cfb\"")
    call = src[i:src.index(")", src.index("shrink", i))]
    assert "seasons=" in call, (
        "cfb_build must bound team ratings to one season — college rosters "
        "turn over every year, so an unbounded fit rates graduated players")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
