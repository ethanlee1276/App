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
    # Best -102 / -102 across books: ~1% hold — cheap, but NOT an arb.
    scan = scan_recommendations([_rec("Cheap Guy", [
        ("DraftKings", 5.5, -102, -110),
        ("FanDuel", 5.5, -110, -102),
    ], market="strikeouts", label="Strikeouts")])
    assert scan["arbs"] == []
    assert len(scan["low_holds"]) == 1
    assert scan["low_holds"][0]["hold_pct"] <= 0.02


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


def test_middles_ranked_by_ev_from_real_distributions():
    """A narrow window on a DENSE number must outrank a wide window in dead
    space — the spec's core middles requirement."""
    # League outcome distribution via logs: strikeouts cluster at 5-6.
    logs_dense = [{"value": v} for v in ([5] * 120, [6] * 120, [2] * 30, [10] * 30)
                  for v in v]
    recs = [
        {**_rec("Dense Window", [("DraftKings", 4.5, -105, -110),
                                 ("FanDuel", 6.5, -110, -105)],
                market="strikeouts", label="Strikeouts"), "logs": logs_dense},
        {**_rec("Dead Space", [("DraftKings", 8.5, -105, -110),
                               ("FanDuel", 11.5, -110, -105)],
                market="strikeouts", label="Strikeouts"), "logs": logs_dense},
    ]
    scan = scan_recommendations(recs)
    assert len(scan["middles"]) == 2
    first, second = scan["middles"]
    # 4.5/6.5 straddles the 5-6 cluster (80% mass); 8.5/11.5 catches ~10%.
    assert first["bet"].startswith("Dense Window")
    assert first["middle_prob"] > 0.7 > second["middle_prob"]
    assert first["ev_per_unit"] > second["ev_per_unit"]
    assert first["ev_per_unit"] > 0                # dense middle is +EV


def test_arb_suspect_flag_and_low_hold_cost():
    scan = scan_recommendations([
        # A "9% arb" is a stale line, not free money — flagged, still shown.
        _rec("Too Good", [("DraftKings", 1.5, 145, -125),
                          ("FanDuel", 1.5, -125, 145)]),
        _rec("Cheap", [("DraftKings", 5.5, -102, -110),
                       ("FanDuel", 5.5, -110, -102)],
             market="strikeouts", label="Strikeouts"),
    ])
    assert scan["arbs"][0]["suspect"] is True
    lh = scan["low_holds"][0]
    # 2.4% hold ≈ $24 per $1,000 bet through — the number that matters.
    assert abs(lh["cost_per_1k"] - lh["hold_pct"] * 1000) < 0.01


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
