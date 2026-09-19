"""A sharp-anchored card says so itself, in every league.

THE BUG, 2026-09-16. Ethan's droplet report: the MLB Most Likely board
carried thirty game rows and NOT ONE of them had a sharp or a market
witness. `potd.shortfall` refuses a model-only row outright — "only our
own model disputes this price" — so the league with by far the most data
could not produce a Pick of the Day at all, on any day.

The prices were there. `engine/mlb/pipeline._game_bets` calls
`price_moneyline_sharp`, `price_total_sharp` and `price_spread_sharp`
exactly as the football pipeline does, and Pinnacle has been in
`oddsapi.DEFAULT_BOOKS` since 2026-09-15. What was missing was one
boolean: `sharp_anchored` was written by each pipeline AFTER the card
came back — `engine/pipeline.py` did it three times, `cfb_build.py` once,
and the MLB pipeline never did it at all. So every baseball card reached
`likely.from_game_bet` claiming our model was the only witness, and the
selector believed it.

THE SAME SHAPE AS THE SPREADS-AND-TOTALS BUG one day earlier, which was
`from_game_bet` dropping the flag on the floor. Both times a sharp book's
number was thrown away and a sentence about OUR model was printed over
it. The evidence was discarded, not outweighed.

SO THE FIX PUTS THE FLAG WHERE IT CANNOT BE FORGOTTEN: the function that
prices the card sets it, because that function is the only thing that
knows. `_sharpify` stamps totals and spreads, `price_moneyline_sharp`
stamps its rec and `moneyline_to_dict` carries it. A fifth pipeline
added tomorrow gets it for free.

These tests build no board and read no store — they run real cards
through the real pricers and the real MLB pipeline.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamebets                                   # noqa: E402

#: -160/+140 de-vigs to about 59.6/40.4; -131 on the favoured side is
#: +5.2% EV, inside [SHARP_MIN_EV, SHARP_MAX_EV] so a card is built, and
#: inside `potd.MAX_EV` so the selector will take it.
SHARP = (-160, 140)
SOFT = (-131, 150)


# --- the pricers stamp their own work ----------------------------------------
def test_the_sharp_moneyline_rec_says_whose_number_it_carries():
    rec = gamebets.price_moneyline_sharp("BBB", "AAA", *SHARP, *SOFT,
                                         win_prob_home=0.55, context=[])
    assert rec is not None, "the fixture no longer clears the gate"
    assert rec.sharp_anchored is True
    # …and `win_prob` IS the sharp fair, which is the claim the flag makes.
    assert abs(rec.win_prob - 0.5963) < 1e-3, rec.win_prob


def test_the_model_moneyline_rec_makes_no_such_claim():
    """The guard on the guard. If this ever reads True, every model card
    on every board starts claiming a sharp witness it does not have."""
    rec = gamebets.price_moneyline("BBB", "AAA", 0.55, -131, 150,
                                   context=[], sport="nfl")
    assert rec.sharp_anchored is False


def test_the_serializer_carries_it_onto_the_card():
    """`moneyline_to_dict` is what the boards actually see, and it is
    where the flag was being dropped for every league at once."""
    rec = gamebets.price_moneyline_sharp("BBB", "AAA", *SHARP, *SOFT,
                                         win_prob_home=0.55, context=[])
    assert gamebets.moneyline_to_dict(rec)["sharp_anchored"] is True
    model = gamebets.price_moneyline("BBB", "AAA", 0.55, -131, 150,
                                     context=[], sport="nfl")
    assert gamebets.moneyline_to_dict(model)["sharp_anchored"] is False


def test_sharp_totals_and_spreads_stamp_themselves_too():
    tot = gamebets.price_total_sharp("BBB", "AAA", 8.5, SOFT[0], SOFT[1],
                                     SHARP[0], SHARP[1], units="runs",
                                     context=[])
    assert tot is not None and tot["sharp_anchored"] is True

    sp = gamebets.price_spread_sharp("BBB", "AAA", -1.5, SOFT[0], SOFT[1],
                                     SHARP[0], SHARP[1], context=[])
    assert sp is not None and sp["sharp_anchored"] is True


def test_a_suspect_gap_is_still_stamped_though_it_is_graded_pass():
    """A gap too wide to trust is still a SHARP card — the witness is
    the sharp book either way. Stamping it is what lets `potd.shortfall`
    refuse it for the true reason (the gap) rather than the false one
    (our model being the only voice)."""
    hot = gamebets.price_spread_sharp("BBB", "AAA", -1.5, -115, 150,
                                      SHARP[0], SHARP[1], context=[])
    assert hot is not None
    assert hot["suspect_gap"] is True and hot["grade"] == "Pass"
    assert hot["stake_units"] == 0.0
    assert hot["sharp_anchored"] is True


# --- the league that was losing every row ------------------------------------
def _mlb_game():
    """One MLB game with a sharp pair on all three markets, built through
    the real model so the pipeline has everything it asks for."""
    from engine.mlb.models import MLBGame
    return MLBGame(
        home="BBB", away="AAA", park="generic",
        home_ml=SOFT[0], away_ml=SOFT[1],
        sharp_home_ml=SHARP[0], sharp_away_ml=SHARP[1],
        home_rating=0.2, away_rating=-0.1,
        home_off=0.3, home_def=-0.2, away_off=0.1, away_def=0.2,
        total=8.5, total_over_odds=SOFT[0], total_under_odds=SOFT[1],
        sharp_total=8.5, sharp_total_over_odds=SHARP[0],
        sharp_total_under_odds=SHARP[1],
        spread=-1.5, spread_home_odds=SOFT[0], spread_away_odds=SOFT[1],
        sharp_spread=-1.5, sharp_spread_home_odds=SHARP[0],
        sharp_spread_away_odds=SHARP[1],
    )


def test_the_mlb_pipeline_ships_its_sharp_cards_stamped():
    """THE ONE THAT WOULD HAVE CAUGHT IT. Not the pricer in isolation —
    the real MLB pipeline, the one whose thirty rows were all refused."""
    from engine.mlb.pipeline import _game_bets
    from engine.rules import RuleConfig

    cards = _game_bets([_mlb_game()], RuleConfig())
    assert cards, "the MLB pipeline priced nothing from a fully quoted game"
    by_market = {}
    for c in cards:
        by_market.setdefault(c.get("bet_type"), []).append(c)

    anchored = [c for c in cards if c.get("sharp_anchored")]
    assert anchored, (
        "no MLB card claims a sharp witness — this is the 2026-09-16 bug, "
        f"markets priced: {sorted(by_market)}")
    # The moneyline is the one Ethan's thirty rows were made of.
    mls = by_market.get("moneyline") or []
    assert mls and mls[0].get("sharp_anchored") is True, mls[:1]


def test_an_mlb_game_with_no_sharp_pair_claims_nothing():
    """The other half: a game Pinnacle is silent on must still ship a
    model card that says so, or the fix has simply moved the lie."""
    from engine.mlb.pipeline import _game_bets
    from engine.rules import RuleConfig
    import dataclasses

    g = dataclasses.replace(_mlb_game(), sharp_home_ml=0, sharp_away_ml=0,
                            sharp_total=0.0, sharp_spread=0.0)
    for c in _game_bets([g], RuleConfig()):
        assert not c.get("sharp_anchored"), c.get("bet_type")


def test_no_pipeline_has_to_remember_to_stamp_it():
    """The structural point, and the reason this is not four one-line
    fixes. The flag is set by the pricer, so a league added tomorrow
    cannot repeat the MLB bug by forgetting a line."""
    import inspect
    src = inspect.getsource(gamebets)
    assert 'card["sharp_anchored"] = True' in src, \
        "`_sharpify` no longer stamps the card it just rewrote"
    assert "sharp_anchored=True" in src, \
        "`price_moneyline_sharp` no longer stamps its rec"
    assert '"sharp_anchored": rec.sharp_anchored' in src, \
        "`moneyline_to_dict` no longer carries the flag onto the card"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
