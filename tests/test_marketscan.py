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


def test_stale_quotes_flags_a_book_out_of_line_with_the_field():
    """The one Scanner section backed by a measured CLV result: a book
    pricing a side cheaper than every other book. Taking those beat the
    closing consensus 64.8% of the time (+1.49 pts, z=11.6)."""
    from engine.marketscan import stale_quotes, STALE_MIN_BOOKS

    recs = [{"player": "Judge", "market": "hits", "market_label": "Hits",
             "all_lines": [
                 {"book": "DraftKings", "line": 0.5, "over_odds": -110, "under_odds": -110},
                 {"book": "BetMGM", "line": 0.5, "over_odds": -112, "under_odds": -108},
                 {"book": "theScore Bet", "line": 0.5, "over_odds": 100, "under_odds": -120},
             ]}]
    out = stale_quotes(recs)
    over = next(s for s in out if s["side"] == "OVER")
    assert over["book"] == "theScore Bet" and over["odds"] == 100
    assert over["gap_pts"] > 2.0
    assert over["consensus"] > over["implied"]      # field says it's worth less
    assert over["books_compared"] == 3
    # Sorted by how far out of line the price is.
    assert out == sorted(out, key=lambda d: -d["gap_pts"])

    # A tight market with everyone agreeing produces nothing.
    tight = [{"player": "X", "market": "hits", "market_label": "Hits",
              "all_lines": [{"book": b, "line": 0.5, "over_odds": -110,
                             "under_odds": -110}
                            for b in ("A", "B", "C")]}]
    assert stale_quotes(tight) == []

    # Fewer books than STALE_MIN_BOOKS is not a consensus.
    thin = [{"player": "Y", "market": "hits", "market_label": "Hits",
             "all_lines": [{"book": "A", "line": 0.5, "over_odds": -110, "under_odds": -110},
                           {"book": "B", "line": 0.5, "over_odds": 140, "under_odds": -160}]}]
    assert STALE_MIN_BOOKS == 3 and stale_quotes(thin) == []

    # A prop with no real market is skipped entirely.
    assert stale_quotes([{**recs[0], "has_market": False}]) == []


def test_longshot_warnings_flag_plus_money_props_with_measured_cost():
    """An avoidance rule, not a play. Measured on 27,226 settled quotes:
    backing plus-money props cost -16.7% per unit against -6.5% for short
    prices, the books shading big payouts 2.6x harder."""
    from engine.marketscan import (longshot_warnings, band_for,
                                   LONGSHOT_MAX_PROB, PRICE_BANDS)

    # The measured cost must worsen monotonically as the price lengthens.
    rois = [roi for _, _, roi in PRICE_BANDS]
    assert rois == sorted(rois), rois
    assert band_for(900)[1] < band_for(-110)[1] < 0

    recs = [
        {"player": "Judge", "market": "home_runs", "market_label": "HR",
         "side": "OVER", "line": 0.5, "odds": 650, "book": "DK", "grade": "Lean"},
        {"player": "Short", "market": "hits", "market_label": "Hits",
         "side": "OVER", "line": 0.5, "odds": -140, "book": "DK"},
    ]
    out = longshot_warnings(recs)
    assert len(out) == 1 and out[0]["bet"].startswith("Judge")
    assert out[0]["band"] == "+400 to +900"
    assert out[0]["measured_roi"] < -0.2
    assert out[0]["implied"] < LONGSHOT_MAX_PROB

    # Sorted longest price first — the most expensive warning leads.
    many = longshot_warnings([
        {"player": "A", "market": "m", "side": "OVER", "line": 0.5, "odds": 300},
        {"player": "B", "market": "m", "side": "OVER", "line": 0.5, "odds": 1200},
    ])
    assert many[0]["bet"].startswith("B")

    # Props without a real market are skipped.
    assert longshot_warnings([{**recs[0], "has_market": False}]) == []


def test_stale_quotes_dedupes_and_caps_the_board():
    """On a real 1,016-prop board this emitted 911 rows — every quote below
    consensus across seven books. All technically above threshold, and
    useless to act on. The measured CLV came from taking THE best price,
    so one flag per prop-side is what belongs on the page."""
    from engine.marketscan import stale_quotes, STALE_LIMIT

    recs = [{"player": f"P{i}", "market": "hits", "market_label": "Hits",
             "all_lines": [
                 {"book": "A", "line": 0.5, "over_odds": -110, "under_odds": -110},
                 {"book": "B", "line": 0.5, "over_odds": -112, "under_odds": -108},
                 {"book": "C", "line": 0.5, "over_odds": 100 + i, "under_odds": -120},
             ]} for i in range(60)]
    out = stale_quotes(recs)
    assert len(out) == STALE_LIMIT                 # capped
    assert out[0]["total_found"] > STALE_LIMIT     # but reports the real count
    gaps = [d["gap_pts"] for d in out]
    assert gaps == sorted(gaps, reverse=True)      # biggest gap first

    # One row per prop-side, never one per book.
    keys = [(d["bet"], d["side"]) for d in out]
    assert len(keys) == len(set(keys))

    # limit=0 returns everything, for callers that want the full set.
    assert len(stale_quotes(recs, limit=0)) == out[0]["total_found"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
