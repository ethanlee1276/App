"""The pitcher outs market — §5.2's best construction, made buildable.

The parlay instruction set calls the pitcher stack — strikeouts over PLUS
outs over PLUS the opposing team total under — "the single best 3-leg
construction in your entire system." One arm, one mechanism, three markets
that move together, and books frequently price the K/outs pair as if it were
independent.

Every piece of the screen for it was already implemented and tested: the §3
Type 5 same-player exception, the §5.1 correlation, the opposing-total leg.
The construction was unbuildable for one reason — `outs` was not a market
this engine knew about. These tests pin the wiring that fixed that, layer by
layer, because a market half-registered is worse than one that is absent:
it produces a projection with no dispersion model behind it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import models as M
from engine.mlb.quality import mlb_tier, MLB_VOLATILITY
from engine.mlb.projection import CV_FLOOR
from engine.sources.oddsapi import MLB_ODDS_TO_MARKET
from engine.mlb.sources.statslogs import MARKET_GROUP, MARKET_STAT
from engine import parlays as P


def test_outs_is_a_pitcher_market_with_a_label():
    assert M.OUTS == "outs"
    assert M.MARKET_LABELS[M.OUTS] == "Outs Recorded"
    assert M.OUTS in M.PITCHER_MARKETS
    assert M.OUTS not in M.HITTER_MARKETS, (
        "outs filed as a hitter market would put it behind the lineup rule")


def test_the_odds_feed_key_is_mapped():
    """Without this the market can never arrive, however well modelled."""
    assert MLB_ODDS_TO_MARKET["pitcher_outs"] == M.OUTS


def test_the_game_log_ingest_knows_where_outs_lives():
    """The MLB Stats API reports outs directly on the pitching log. Taking
    it from there beats reconstructing it from innings pitched, where 6.1 IP
    is nineteen outs and the thirds are the easiest thing in baseball to get
    wrong."""
    assert MARKET_GROUP[M.OUTS] == "pitching"
    assert MARKET_STAT[M.OUTS] == "outs"


def test_outs_is_tier_1_and_the_least_volatile_pitcher_market():
    """§9's own examples: outs LOW, 6+ Ks MEDIUM. A starter is pulled by
    pitch count and score far more than by anything that varies night to
    night, so his outs distribution is tighter than his strikeouts."""
    assert mlb_tier(M.OUTS) == 1
    assert MLB_VOLATILITY[M.OUTS] == "LOW"
    assert CV_FLOOR[M.OUTS] < CV_FLOOR[M.STRIKEOUTS], (
        "outs was registered with a wider dispersion than strikeouts")


def test_every_layer_that_keys_off_a_market_covers_outs():
    """A market registered in some tables and missing from others is the
    dangerous state: it projects, prices, and quietly falls back to a
    default nobody chose. Park and weather return 1.0 for outs ON PURPOSE —
    how long a manager leaves his starter in is a bullpen and scoreboard
    decision, not a contact one — but they have to say so rather than
    KeyError or default by accident."""
    from engine.mlb.parks import evaluate_park, PARKS
    from engine.mlb.weather import evaluate_weather
    park = list(PARKS.values())[0]
    assert M.OUTS in evaluate_park(park).multipliers
    assert M.OUTS in evaluate_weather(
        M.MLBWeather(temp_f=70, wind_mph=5, wind_dir_rel="out")).multipliers


def test_a_prop_is_actually_built_for_outs():
    """Registering a market in every lookup table is not the same as the
    market existing.

    The first pass at this wired OUTS through the models, the odds map, the
    game-log ingest, the tier table and the dispersion floor — and never
    added it to the slate builder, which creates exactly one prop per
    probable starter. The market was present everywhere except the one place
    that makes it real, so nothing would ever have been projected, priced or
    ingested for it."""
    import inspect
    from engine.mlb.sources import statslogs
    src = inspect.getsource(statslogs.build_live_slate)
    assert "for mkt in (STRIKEOUTS, OUTS)" in src, (
        "the slate builder still creates only the strikeout prop, so no outs "
        "prop is ever built for a starter")


def test_the_pitcher_stack_the_doc_calls_the_best_in_the_system_now_builds():
    """End to end: strikeouts over + outs over on one confirmed starter.
    §3 Type 5 bans same-player multi-prop and then carries an exception for
    a confirmed-active player; §5.2 names this construction the best in the
    system. An announced starter is the cleanest instance of that exception
    there is."""
    def leg(market, p, odds):
        ev = p * (P.american_to_decimal(odds) - 1) - (1 - p)
        return dict(player="Wheeler", team="PHI", opponent="CHC",
                    market=market, market_label=M.MARKET_LABELS[market],
                    side="OVER", line=5.5, odds=odds, hit_prob=p,
                    ev_per_unit=ev, recommended=True, grade="A",
                    game_date="2026-08-02", warnings=[],
                    headline=f"Wheeler OVER {market}")
    slate = {"date": "2026-08-02",
             "games": [dict(home="PHI", away="CHC", date="2026-08-02",
                            spread=1.5, favorite="PHI", total=8.5,
                            roof="closed", lineups_confirmed=True,
                            weather={"wind_mph": 5})],
             "recommendations": [leg(M.STRIKEOUTS, 0.58, -120),
                                 leg(M.OUTS, 0.57, -115)]}
    out = P.screen(slate, "mlb")
    assert out["tickets"], out["killed"]
    t = out["tickets"][0]
    assert {l["market"] for l in t["legs"]} == {M.STRIKEOUTS, M.OUTS}
    assert "pitcher stack" in t["pairs"][0]["mechanism"]
    assert all(l["tier"] == 1 for l in t["legs"])


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
