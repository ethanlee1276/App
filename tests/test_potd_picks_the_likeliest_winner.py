"""The Pick of the Day selects on whether it hits, not on its edge.

Ethan, 2026-09-16: *"I don't care about the edge a bet has when it comes
to the pick of the day. I care about if the pick is going to hit or not.
The point of the pick of the day is to give out confident winning picks.
Who cares about ev and shit."*

That is a product decision and it is his. What was built was a +EV board
wearing a Pick of the Day label: it ranked on the SIZE OF THE
DISAGREEMENT with the market and demanded 2% of edge to publish at all.
Those are the right rules for a different feature.

THE BAND WAS THE REAL CEILING, and it is the finding worth keeping.
`MIN_PAYOUT` of 0.70 IS a price floor of -142, and -142 implies 58.7%.
So the old bars did not merely prefer close games — they made a confident
pick ARITHMETICALLY IMPOSSIBLE. Every card read 55% because nothing
better was allowed through the door. Ranking on probability changes
nothing until the band stops banning favourites, which is why both moved
together.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402
from engine.odds import american_to_prob                      # noqa: E402


def _row(fair, odds, tier="sharp"):
    """A game row whose probability and price we choose."""
    d = {"odds": odds, "book": "DraftKings", "market": "moneyline",
         "bet_type": "moneyline", "home": "A", "away": "B", "team": "A",
         "rank_auc": 0.70, "has_market": True, "model_prob": fair,
         "win_prob": fair}
    if tier == "sharp":
        d.update(sharp_anchored=True, sharp_fair=fair)
    elif tier == "market":
        d.update(prob_source="market", implied_prob=fair)
    return d


# --- the principle ------------------------------------------------------------
def test_the_likeliest_winner_is_the_pick_not_the_biggest_edge():
    """THE WHOLE CHANGE, asked directly, AMONG ROWS OF ONE WITNESS. The
    55% row disagrees with its price by far more; the 70% row is far
    likelier to land. The day is named after the second."""
    big_edge = _row(0.55, +130)      # price implies 43.5% — a huge edge
    likelier = _row(0.70, -230)      # price implies 69.7% — almost none
    assert potd.edge(big_edge) > potd.edge(likelier), "fixture premise"
    best = min([big_edge, likelier], key=potd.rank_key)
    assert best is likelier, "the day went to the loudest disagreement again"


def test_a_weaker_witness_never_wins_on_a_bigger_number():
    """THE LIMIT ON "MOST LIKELY", and a first draft of this change got
    it wrong until an existing test caught it.

    A model-only 70% is not a 70%: the MLB model ranks winners at 0.5596,
    a coin flip with opinions, so its number is not one to bet on being
    right. A sharp book's de-vigged 60% is measured at 0.6727 and is. So
    "most likely to hit" has to mean "most likely among the numbers
    measured to be right" — otherwise the day goes to whichever witness
    is loudest and least reliable, which is the failure the old
    edge-ranking had, reached by a different road."""
    weak_but_bigger = _row(0.70, -230, tier="market")
    strong_but_smaller = _row(0.60, -140, tier="sharp")
    best = min([weak_but_bigger, strong_but_smaller], key=potd.rank_key)
    assert best is strong_but_smaller, \
        "a weaker witness won the day by printing a bigger number"


def test_a_tie_on_probability_and_witness_goes_to_the_better_price():
    """Equal chance, better payout — free money where it costs nothing."""
    cheap = _row(0.65, -190)
    dear = _row(0.65, -150)
    assert min([cheap, dear], key=potd.rank_key) is dear


def test_probability_sorts_on_whole_points_not_false_precision():
    """71.4% and 71.2% are the same claim made twice. Treating them as
    ranked hands the day to whichever rounded up while a materially
    better price sits one line below."""
    a = _row(0.714, -200)
    b = _row(0.712, -150)
    assert min([a, b], key=potd.rank_key) is b, "false precision beat a real price"


# --- the band that made confidence impossible ---------------------------------
def test_the_band_can_now_reach_the_confidence_floor():
    """THE ARITHMETIC THAT WAS THE BUG. A floor the band cannot reach
    selects nothing, and a band that stops below the floor makes the
    whole feature unreachable — which is what -142 did."""
    reachable = american_to_prob(potd.MIN_ODDS)
    assert reachable > potd.MIN_FAIR, (
        f"the band reaches {reachable:.1%} but the floor asks for "
        f"{potd.MIN_FAIR:.0%} — nothing can ever clear it")


def test_a_favourite_is_allowed_through_the_door_at_all():
    """-180 and -250 are ordinary prices on a confident pick and were
    both refused outright before 2026-09-16."""
    for odds in (-150, -180, -200, -250):
        assert potd.in_band(odds), odds
    # …and there is still a floor. -300 needs 75% to break even.
    assert not potd.in_band(-300)


def test_the_confidence_floor_names_itself_and_is_left_to_measurement():
    """THE ONE BAR NOT SET IN THIS CHANGE, deliberately.

    A pass at this raised it to 60% and the arithmetic said no: `MAX_EV`
    refuses a gap over 7%, so -110 can carry a fair of at most 56.0% and
    a floor above that makes every -110 row ineligible. Most of the board
    is -110. Raising it by judgement would have made the feature BLANKER,
    which is the opposite of what was asked for.

    So it stays where it is until `--sweep-conf` says otherwise, and what
    is pinned here is the seam and the sentence rather than a number
    somebody guessed."""
    assert potd.MIN_FAIR == 0.50, (
        "the confidence floor moved — if that came from --sweep-conf, "
        "update this test and say which table; if it came from an "
        "opinion, it is the mistake this test exists to catch")
    why = potd.shortfall(_row(0.52, -110), min_fair=0.60)
    assert "not confident enough" in why, why
    assert "60%" in why, "the refusal does not name the bar it applied"


# --- and the edge requirement is gone -----------------------------------------
def test_the_edge_floor_survives_because_it_is_what_makes_the_money():
    """THE HALF OF ETHAN'S INSTRUCTION THAT DID NOT SURVIVE, and why.

    He said "who cares about ev and shit" and then, asked to break a tie
    between two of his own specs: "whatever makes more sense and returns
    the most roi and wins and money in the long run."

    Those pull apart. Hit rate and money are different axes: a 71% pick
    at -250 breaks even at exactly 71.4%, so betting confident favourites
    at fair prices returns zero minus the hold however good the record
    looks. The only thing that makes money over a long run is taking a
    price better than the true chance. The money instruction is the one
    that decides, so this bar stays.

    THE TWO GOALS ARE SPLIT ACROSS TWO JOBS instead of one winning
    outright: this bar decides WHETHER there is a pick (money), and
    `rank_key` decides WHICH of the qualifying rows gets the day, on
    likelihood (confidence). Both are honoured where they do not
    conflict."""
    assert potd.MIN_EV > 0, (
        "the edge floor was dropped — that buys a better-looking hit "
        "rate and a worse bankroll, which is the opposite of the "
        "criterion given")
    fair_priced = _row(0.70, -230)          # implies 69.7%, edge ~0.3%
    assert abs(potd.edge(fair_priced)) < potd.MIN_EV, "fixture premise"
    assert "not far enough off the fair" in potd.shortfall(fair_priced), \
        "a pick priced at its own fair makes no money and is not the day's"


def test_a_price_worse_than_the_number_is_refused_hardest_of_all():
    rich = _row(0.62, -200)                 # implies 66.7% — worse than fair
    assert potd.edge(rich) < 0
    assert "not far enough off the fair" in potd.shortfall(rich)


def test_the_suspect_ceiling_survives_because_it_is_not_an_edge_bar():
    """`MAX_EV` refuses a gap so large the sharp side has probably moved.
    That is a data-quality guard, not a preference for edge, so it stays
    even though the edge FLOOR is gone."""
    assert potd.MAX_EV > 0
    silly = _row(0.70, +200)                # implies 33% against a 70% fair
    assert "too big to trust" in potd.shortfall(silly)


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
