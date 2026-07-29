"""The Correlation Engine (docs/NFL_MODEL.md §9) and the §10 exposure caps.

Correlated bets are one bet wearing two jerseys: the engine must SAY so on
both cards, must reject incoherent pairs outright (QB Under next to his
receiver's Over), and must count correlated stakes together against the
5u-per-game / 15u-per-slate circuit breakers.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.correlation import (flag_correlations, apply_exposure_caps,
                                GAME_CAP_U, SLATE_CAP_U)


def _rec(player, team, opp, market, side, quality=80, stake=0.5, rec=True):
    return {"player": player, "team": team, "opponent": opp, "market": market,
            "market_label": market, "side": side, "quality": quality,
            "stake_units": stake, "recommended": rec, "game_date": "2026-09-13"}


def test_qb_and_his_receiver_same_side_is_flagged_positive():
    qb = _rec("QB One", "KC", "LV", "pass_yds", "OVER")
    wr = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    out = flag_correlations([qb, wr])
    assert out["pairs_flagged"] == 1 and out["pairs_rejected"] == 0
    assert any("combined exposure" in c for c in qb["correlations"])
    assert any("WR One" in c for c in qb["correlations"])
    assert any("QB One" in c for c in wr["correlations"])
    assert qb["recommended"] and wr["recommended"]


def test_incoherent_pairing_rejects_the_lower_grade():
    # QB Under + his WR Over describe contradictory passing games.
    qb = _rec("QB One", "KC", "LV", "pass_yds", "UNDER", quality=84)
    wr = _rec("WR One", "KC", "LV", "receptions", "OVER", quality=73)
    out = flag_correlations([qb, wr])
    assert out["pairs_rejected"] == 1
    assert wr["recommended"] is False and wr["grade"] == "Pass"
    assert wr["stake_units"] == 0.0
    assert any("Incoherent" in w for w in wr["warnings"])
    assert qb["recommended"] is True          # the higher grade survives


def test_two_receivers_one_ball_is_mildly_negative():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Two", "KC", "LV", "receptions", "OVER")
    flag_correlations([a, b])
    assert any("one ball" in c for c in a["correlations"])
    assert a["recommended"] and b["recommended"]      # flagged, not rejected


def test_cross_team_overs_are_pace_linked():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Away", "LV", "KC", "rec_yds", "OVER")
    flag_correlations([a, b])
    assert any("Pace-linked" in c for c in a["correlations"])


def test_different_games_never_flag():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Two", "BUF", "MIA", "rec_yds", "OVER")
    out = flag_correlations([a, b])
    assert out["pairs_flagged"] == 0
    assert "correlations" not in a and "correlations" not in b


def test_game_cap_scales_correlated_stakes_together():
    rows = [_rec(f"P{i}", "KC", "LV", "receptions", "OVER", stake=2.0)
            for i in range(4)]                    # 8u in one game
    notes = apply_exposure_caps(rows, [])
    total = sum(r["stake_units"] for r in rows)
    assert abs(total - GAME_CAP_U) < 0.05
    assert any("Game cap" in n for n in notes)


def test_slate_cap_counts_game_bets_too():
    recs = [_rec(f"P{i}", t, o, "receptions", "OVER", stake=4.0)
            for i, (t, o) in enumerate([("KC", "LV"), ("BUF", "MIA"),
                                        ("DAL", "NYG"), ("SF", "SEA")])]
    bets = [{"home": "GB", "away": "CHI", "date": "2026-09-13",
             "recommended": True, "stake_units": 4.0}]
    notes = apply_exposure_caps(recs, bets)
    total = (sum(r["stake_units"] for r in recs)
             + sum(b["stake_units"] for b in bets))
    assert abs(total - SLATE_CAP_U) < 0.1
    assert any("Slate cap" in n for n in notes)


def test_non_recommended_rows_are_ignored_by_caps():
    rows = [_rec("P1", "KC", "LV", "receptions", "OVER", stake=2.0),
            _rec("P2", "KC", "LV", "receptions", "OVER", stake=9.0, rec=False)]
    notes = apply_exposure_caps(rows, [])
    assert notes == []                     # 2u recommended — no cap tripped
    assert rows[1]["stake_units"] == 9.0   # untouched: it isn't a bet


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
