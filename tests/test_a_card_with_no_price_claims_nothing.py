"""A game card nobody posted a price for claims no edge, and no haircut.

#258, decided by Ethan 2026-09-16 after he read the MLB census: mark
these unpriced rather than buy team-total quotes we would never stake.

`gamebets.price_team_total` defaulted both its odds to -110, and no sport
passes any — the feed is asked for h2h, spreads and totals, and team
totals are not among them. So every team-total card on the NFL, CFB and
MLB boards published at a price nobody had quoted. The default is now 0,
which means NOT OFFERED everywhere else in that module.

Changing the default alone was not enough, and this is the part worth
reading. `_game_bet` SET `has_market` and then went on to publish four
numbers computed from a price of zero:

  * `edge` measured against `devig_two_way(0, 0)`, which returns the
    0.5/0.5 fallback — so the "edge" was the model's distance from a coin
    flip, routinely double digits on a team total;
  * `ev_per_unit` from `expected_value(win, 0)`, which reads a price of
    zero as even money and returns win - 1, so a 62% projection
    advertised "EV/unit -38%";
  * a `grade` and a `stake_units` off that quality score;
  * and `win_prob` ITSELF, because `temper` shrinks the projection toward
    the market's fair — 0.5 again. The model said 65.8%, the card said
    57.9%, and nothing claimed the number in between.

The prop layer has refused all of this since Ethan's Blackburn card on
2026-09-05 (`betting.py`, `if not has_market`). Game bets set the same
flag and acted on none of it. This is that rule reaching them.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gamebets import (                                  # noqa: E402
    NO_PRICE_REASON, price_team_total, price_total, price_spread,
)


def _unpriced(**kw):
    return price_team_total("mlb", "BBB", "BBB", "AAA", 5.8, 4.5,
                            units="runs", **kw)


# --- the default is the absence of a price ------------------------------------
def test_the_team_total_default_is_not_a_price():
    """-110 is a real American price. Nothing on a card carrying it says
    a book never posted it — which is the whole reason Ethan could only
    find this by noticing the BOOK column was empty."""
    import inspect
    sig = inspect.signature(price_team_total)
    assert sig.parameters["over_odds"].default == 0
    assert sig.parameters["under_odds"].default == 0


def test_an_unpriced_card_says_so_in_the_field_everything_reads():
    card = _unpriced()
    assert card["has_market"] is False
    assert card["odds"] == 0


def test_a_real_pair_still_produces_a_full_card():
    """The guard must not empty the market — a caller that HAS prices
    still gets the graded card."""
    card = _unpriced(over_odds=-105, under_odds=-115)
    assert card["has_market"] is True
    assert card["odds"] in (-105, -115)
    # The edge and the EV are measured against a real de-vig, not zeroed.
    # NOT the grade: baseball team totals grade Pass on their own
    # calibration, which is a separate judgement and not what this
    # asserts.
    assert card["edge"] != 0.0 and card["ev_per_unit"] != 0.0
    assert card["fair_prob"] != 0.5, "a real pair was de-vigged to the fallback"
    assert NO_PRICE_REASON not in card["reasons"]


# --- and claims nothing -------------------------------------------------------
def test_no_number_on_it_reads_as_an_edge():
    card = _unpriced()
    assert card["edge"] == 0.0, "an edge against a 0.5 fallback is not an edge"
    assert card["ev_per_unit"] == 0.0, \
        "expected_value(win, 0) reads a missing price as even money"


def test_it_takes_no_stake_and_carries_no_grade():
    card = _unpriced()
    assert card["grade"] == "Pass"
    assert card["stake_units"] == 0.0
    assert card["quality"] == 0 and card["confidence"] == 0.0


def test_the_confidence_score_is_zero_and_not_the_floor():
    """`game_bet_score` has a FLOOR of 35 — a zeroed edge still scores —
    so a card that only zeroed the edge printed "confidence 3.5" beside
    a price of zero. Asked on a market whose model IS credible, because
    the credibility branch zeroes the quality on its own and would hide
    this."""
    card = price_spread("nfl", "BBB", "AAA", 2.0, -3.5, 0, 0, context=[])
    assert card["credible"] is True, "fixture no longer tests what it means to"
    assert card["has_market"] is False
    assert card["quality"] == 0, "the floor score survived on an unpriced card"
    assert card["confidence"] == 0.0


def test_it_names_the_reason_rather_than_going_quiet():
    """A row that simply shows nothing looks like a bug. This one says
    which of the two numbers is missing and which still stands."""
    assert NO_PRICE_REASON in _unpriced()["reasons"]


def test_the_probability_shown_is_the_models_own_not_a_haircut_toward_a_guess():
    """THE SUBTLE HALF. `temper` shrinks toward the market's fair to
    respect a price. With no price there is nothing to respect, and the
    shrink was pulling the lean toward `devig_two_way(0, 0)`'s 0.5."""
    card = _unpriced()
    assert card["win_prob"] == card["engine_raw_prob"], \
        "the lean was haircut toward a coin flip nobody quoted"
    assert card["win_prob"] > 0.6, card["win_prob"]
    # …and `fair_prob` still reads 0.5, which is how the row records that
    # nothing priced it rather than pretending the model's number was
    # also the market's.
    assert card["fair_prob"] == 0.5


def test_a_priced_card_keeps_its_haircut():
    """The mirror image, so the fix cannot quietly disable the shrink on
    the rows that have a market to be shrunk toward."""
    card = _unpriced(over_odds=-105, under_odds=-115)
    assert card["win_prob"] != card["engine_raw_prob"]


# --- the rule is the module's, not one market's -------------------------------
def test_totals_and_spreads_are_held_to_it_too():
    """`price_total` and `price_spread` already computed `has_market`
    from `_real_price`; nothing acted on it. A sport that reaches them
    without a pair gets the same refusal, not a graded card."""
    tot = price_total("mlb", "BBB", "AAA", 9.1, 8.5, 0, 0, "runs", [])
    sp = price_spread("mlb", "BBB", "AAA", 1.2, -1.5, 0, 0, context=[])
    for card in (tot, sp):
        assert card["has_market"] is False, card["bet_type"]
        assert card["edge"] == 0.0 and card["ev_per_unit"] == 0.0, card["bet_type"]
        assert card["grade"] == "Pass" and card["stake_units"] == 0.0, \
            card["bet_type"]
        assert NO_PRICE_REASON in card["reasons"], card["bet_type"]


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
