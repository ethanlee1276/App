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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
