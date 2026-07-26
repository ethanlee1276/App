"""Tests for the cross-book market scanner (pure price math)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.marketscan import scan_recommendations


def _rec(player, lines, market="total_bases", label="Total Bases"):
    return {"player": player, "market": market, "market_label": label,
            "has_market": True,
            "all_lines": [{"book": b, "line": l, "over_odds": o, "under_odds": u}
                          for b, l, o, u in lines]}


def test_arbitrage_locks_profit_across_books():
    # Over +105 at DK, Under +105 at FD on the same line: 48.8% + 48.8% < 100%.
    scan = scan_recommendations([_rec("Arb Guy", [
        ("DraftKings", 1.5, 105, -125),
        ("FanDuel", 1.5, -125, 105),
    ])])
    assert len(scan["arbs"]) == 1
    a = scan["arbs"][0]
    assert a["profit_pct"] > 0.02
    assert a["over"]["book"] == "DraftKings" and a["under"]["book"] == "FanDuel"
    # Equal-return split: half the stake each side at equal prices.
    assert abs(a["stake_over_pct"] - 0.5) < 0.01


def test_middle_window_between_different_lines():
    # Over 69.5 at one book, Under 72.5 at another: 70/71/72 wins BOTH.
    scan = scan_recommendations([_rec("Middle Guy", [
        ("DraftKings", 69.5, -110, -110),
        ("FanDuel", 72.5, -110, -110),
    ], market="rush_yds", label="Rushing Yards")])
    assert len(scan["middles"]) == 1
    m = scan["middles"][0]
    assert m["gap"] == 3.0
    assert m["over"]["line"] == 69.5 and m["under"]["line"] == 72.5
    # Both win pays both prices; worst case costs only the vig.
    assert m["both_win_return"] > 0.8
    assert -0.15 <= m["worst_case"] < 0


def test_low_hold_and_no_false_arbs():
    # -105 / -105: 2.4% hold — cheap, but NOT an arb.
    scan = scan_recommendations([_rec("Cheap Guy", [
        ("DraftKings", 5.5, -105, -110),
        ("FanDuel", 5.5, -110, -105),
    ], market="strikeouts", label="Strikeouts")])
    assert scan["arbs"] == []
    assert len(scan["low_holds"]) == 1
    assert scan["low_holds"][0]["hold_pct"] <= 0.025


def test_one_sided_and_proxy_markets_never_pair():
    scan = scan_recommendations([
        # HR overs quoted one side only (under_odds 0 = not offered).
        _rec("HR Guy", [("DraftKings", 0.5, 320, 0), ("FanDuel", 0.5, 340, 0)],
             market="home_runs", label="Home Runs"),
        # Proxy-priced prop (no real market) is skipped entirely.
        {**_rec("Proxy Guy", [("proxy", 1.5, -110, -110)]), "has_market": False},
        # A single book can never scan against itself for a middle.
        _rec("Lonely Guy", [("DraftKings", 1.5, -110, -110)]),
    ])
    assert scan["arbs"] == [] and scan["middles"] == [] and scan["low_holds"] == []


def test_expensive_middles_are_rejected():
    # A 1-point gap at -150 both sides risks too much for the window.
    scan = scan_recommendations([_rec("Juiced", [
        ("DraftKings", 5.5, -150, -150),
        ("FanDuel", 6.5, -150, -150),
    ], market="strikeouts", label="Strikeouts")])
    assert scan["middles"] == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
