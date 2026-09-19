"""Tests for measured bullpen fatigue (pure parsers + matchup wiring)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.bullpen import (
    ip_to_float, parse_relief_innings, fatigue_factor, TIRED_MIN, FACTOR_MAX,
)


BOX = {
    "teams": {
        "home": {
            "pitchers": [10, 11, 12, 13],       # starter + three relievers
            "players": {
                "ID10": {"stats": {"pitching": {"inningsPitched": "6.0"}}},
                "ID11": {"stats": {"pitching": {"inningsPitched": "1.2"}}},
                "ID12": {"stats": {"pitching": {"inningsPitched": "0.1"}}},
                "ID13": {"stats": {"pitching": {"inningsPitched": "1.0"}}},
            },
        },
        "away": {"pitchers": [20], "players": {
            "ID20": {"stats": {"pitching": {"inningsPitched": "9.0"}}}}},
    }
}


def test_ip_notation_thirds():
    # Baseball's ".1/.2" means outs, not tenths.
    assert abs(ip_to_float("5.2") - (5 + 2 / 3)) < 1e-9
    assert ip_to_float("1.0") == 1.0
    assert ip_to_float(None) == 0.0 and ip_to_float("junk") == 0.0


def test_relief_innings_exclude_the_starter():
    # 1.2 + 0.1 + 1.0 = 3 relief innings; the starter's 6 never count.
    assert parse_relief_innings(BOX, "home") == 3.0
    # A complete game means the pen never pitched.
    assert parse_relief_innings(BOX, "away") == 0.0
    assert parse_relief_innings({}, "home") == 0.0


def test_fatigue_factor_is_a_bounded_nudge():
    assert fatigue_factor(0.0) == 1.0
    assert fatigue_factor(TIRED_MIN - 0.1) == 1.0        # normal workload
    assert 1.0 < fatigue_factor(8.0) < FACTOR_MAX + 1e-9
    assert fatigue_factor(25.0) == FACTOR_MAX            # capped, never a lever


def test_matchup_boosts_hitters_against_a_gassed_pen():
    from engine.mlb.matchup import evaluate_matchup
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, TOTAL_BASES
    from engine.models import SportsbookLine

    def prop_for(game):
        return MLBProp("Hitter", "NYY", "BOS", "RF", TOTAL_BASES,
                       [MLBGameLog(i, "BOS", 1) for i in range(1, 6)], 1.0,
                       None, [SportsbookLine("proxy", 1.5)], bats="R",
                       lineup_spot=5)

    fresh = MLBGame(home="NYY", away="BOS", park="yankee",
                    bullpen_fatigue={"BOS": 2.0})
    gassed = MLBGame(home="NYY", away="BOS", park="yankee",
                     bullpen_fatigue={"BOS": 9.5})
    e_fresh = evaluate_matchup(prop_for(fresh), fresh)
    e_gassed = evaluate_matchup(prop_for(gassed), gassed)
    assert e_gassed.multiplier > e_fresh.multiplier
    assert any("tired arms late" in r for r in e_gassed.reasons)
    assert not any("tired arms" in r for r in e_fresh.reasons)


def test_the_leash_can_only_ever_lengthen_a_start():
    """Pinned as a PROPERTY, not endorsed as correct.

    leash_factor floors at 1.0, so a tired pen lengthens a start and a
    fresh one cannot shorten it — "pen fresh" and "pen normal" produce the
    identical 1.000. Every adjustment available to this function pushes a
    pitcher projection UP, and the journal has measured a matching
    asymmetry (pitcher OVERS -24.9%, pitcher UNDERS +9.1% on 29 bets).

    29 bets convicts nothing, so the behaviour is unchanged and the claim
    lives in the hypothesis lab. This test exists so that if someone later
    makes the factor two-sided, it is a deliberate act with this comment
    in front of them rather than an accident.
    """
    from engine.mlb.bullpen import TIRED_MIN, leash_factor

    for score in (0.0, 1.0, 2.9, 3.0, 5.0, TIRED_MIN - 0.1):
        for outs in (True, False):
            assert leash_factor(score, market_is_outs=outs) == 1.0, score
    # Above the bar it lifts, and never below 1.0 at any input.
    assert leash_factor(TIRED_MIN + 4) > 1.0
    assert all(leash_factor(s) >= 1.0 for s in range(0, 30))
    # A fresh pen and an ordinary one are indistinguishable to it.
    assert leash_factor(0.0) == leash_factor(5.0)


def test_the_asymmetry_is_recorded_where_someone_would_look():
    """A structural property with a betting consequence that nothing in the
    code mentions is one that gets rediscovered the expensive way."""
    import inspect

    from engine.mlb import bullpen
    doc = inspect.getdoc(bullpen.leash_factor)
    assert "one-directional" in doc
    assert "hypothesis lab" in doc, "no pointer to where the claim is tracked"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
