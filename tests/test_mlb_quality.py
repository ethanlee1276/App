"""Scalpy 2.0 — MLB tiers, volatility, certainties and the unified grade
(docs/MLB_MODEL.md §9–§10), plus baseball's correlation rules.

The spec's promises, verified:
- tiers follow beatability (Ks most modelable, HRs quarantined);
- the grade uses baseball's weights — pitcher-grade certainty and
  lineup certainty are 15% each, because the starter is the center of the
  MLB universe and the lineup card is a projection input;
- a starter's K Over next to an opposing hitter's Over is rejected;
- an offense stack is flagged as one bet wearing several jerseys;
- the sample slate produces exactly one qualifying Tier-1 play.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.mlb.quality import (mlb_tier, mlb_tier_shrink, mlb_tier_min_edge,
                                mlb_volatility, mlb_quality_score)
from engine.correlation import flag_mlb_correlations


def _score(**over):
    kw = dict(edge=0.05, market="strikeouts", side="OVER",
              pitcher_certainty=1.0, lineup_certainty=1.0,
              env_mult=1.0, matchup_mult=1.0)
    kw.update(over)
    return mlb_quality_score(**kw)


def test_mlb_tiers_track_beatability():
    assert mlb_tier("strikeouts") == 1
    assert mlb_tier("total_bases") == mlb_tier("hits") == 2
    assert mlb_tier("home_runs") == 3
    assert mlb_tier_shrink("strikeouts") > mlb_tier_shrink("home_runs")
    assert (mlb_tier_min_edge("strikeouts") < mlb_tier_min_edge("hits")
            < mlb_tier_min_edge("home_runs"))


def test_mlb_volatility_matches_the_spec():
    # "6+ Ks = MEDIUM; 2+ TB = HIGH; home run = EXTREME."
    assert mlb_volatility("strikeouts") == "MEDIUM"
    assert mlb_volatility("total_bases") == "HIGH"
    assert mlb_volatility("home_runs") == "EXTREME"


def test_unconfirmed_probable_costs_a_hitter_prop():
    known, _ = _score(market="hits", pitcher_certainty=0.9)
    unknown, notes = _score(market="hits", pitcher_certainty=0.55)
    assert known - unknown >= 4
    assert any("starter not confirmed" in n for n in notes)


def test_unposted_lineup_makes_a_hitter_conditional():
    posted, _ = _score(market="total_bases")
    benched, notes = _score(market="total_bases", lineup_certainty=0.35)
    assert posted - benched >= 8
    assert any("Conditional until the lineup posts" in n for n in notes)


def test_environment_against_the_side_is_said_out_loud():
    _, notes = _score(side="UNDER", env_mult=1.08)   # big-K ump vs an Under
    assert any("environment points the other way" in n for n in notes)


def _rec(player, team, opp, market, side, quality=80, stake=0.5):
    return {"player": player, "team": team, "opponent": opp, "market": market,
            "market_label": market, "side": side, "quality": quality,
            "stake_units": stake, "recommended": True, "game_date": "2026-07-29"}


def test_k_over_vs_opposing_hitter_over_is_rejected():
    k = _rec("Ace One", "PHI", "CHC", "strikeouts", "OVER", quality=85)
    hitter = _rec("Bat One", "CHC", "PHI", "total_bases", "OVER", quality=72)
    out = flag_mlb_correlations([k, hitter])
    assert out["pairs_rejected"] == 1
    assert hitter["recommended"] is False and hitter["stake_units"] == 0.0
    assert any("same pitches" in w for w in hitter["warnings"])
    assert k["recommended"] is True          # the deeper-graded actor survives


def test_k_over_vs_same_team_hitter_is_fine():
    k = _rec("Ace One", "PHI", "CHC", "strikeouts", "OVER")
    mate = _rec("Bat Two", "PHI", "CHC", "hits", "OVER")
    out = flag_mlb_correlations([k, mate])
    assert out["pairs_rejected"] == 0
    assert k["recommended"] and mate["recommended"]


def test_offense_stack_is_flagged_as_combined_exposure():
    a = _rec("Bat One", "COL", "LAD", "hits", "OVER")
    b = _rec("Bat Two", "COL", "LAD", "total_bases", "OVER")
    out = flag_mlb_correlations([a, b])
    assert out["pairs_flagged"] == 1
    assert any("several jerseys" in c for c in a["correlations"])
    assert any("Bat One" in c for c in b["correlations"])
    assert a["recommended"] and b["recommended"]     # flagged, not rejected


def test_sample_slate_recommends_one_tier1_play():
    """The demo slate embodies the spec: pass on nearly everything, bet the
    one Tier-1 strikeout prop that clears every gate — no leans anywhere.

    Run with calibration OFF. `is_reliable` reads a fitted file from
    data/models, so on a machine that has fitted its own temperatures the
    pipeline closes different markets and the sample slate produces a
    different count — this asserted a hard `== 1` and failed on Ethan's
    laptop while passing on a dev checkout with no fit. The slate is a
    fixture; the fit is machine-local state; a test that mixes them is
    measuring the machine.
    """
    from engine.mlb.pipeline import run_mlb_slate
    from engine import calibrate
    with calibrate.disabled():
        out = run_mlb_slate("data/mlb_sample_slate.json")
    recs = out["recommendations"]
    on = [r for r in recs if r["recommended"]]
    assert len(on) == 1 and on[0]["tier"] == 1
    assert on[0]["grade"] in ("A+", "A", "B+")
    assert on[0]["stake_units"] > 0
    for r in recs:
        assert r["grade"] in ("A+", "A", "B+", "Pass")   # no Lean survives
        assert r["quality"] == round(r["confidence"] * 10)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
