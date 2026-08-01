"""Two warnings that read as "we failed to fetch this".

Both were reported from the live board, in the same breath: "are we not
pulling the data we need? also its not verifying they are playing even though
that game starts very soon?"

Neither was a data gap.

  * "Only one side quoted" — books do not offer "no home run" as a bet, so
    there is no second price in existence to pull. The adapter already looks
    for the under and deliberately refuses to invent one at -110, because
    that manufactured enormous fake edges on bets nobody can place.

  * "Not confirmed yet" — lineup confirmation reads MLB's own boxscore feed
    every minute, and the club had not filed the card. Nobody had it, the
    book taking the bet included.

A caveat that states a limit without stating its cause gets read as
incompetence, and the reasonable response to that is to distrust the whole
board. So each one now says why, and — for the lineup — when it clears.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import longshots
from engine.mlb import homeruns


class _Game:
    def __init__(self, kickoff=""):
        self.kickoff = kickoff


# --- the one-sided price ----------------------------------------------------
def test_the_assumed_hold_is_named_rather_than_a_number_in_an_expression():
    assert longshots.ONE_SIDED_HOLD == 1.06


def test_a_two_way_market_is_measured_and_says_so():
    _implied, exact = longshots._price(0.22, 400, -550)
    assert exact is True


def test_a_one_way_market_is_estimated_and_says_so():
    implied, exact = longshots._price(0.22, 400, None)
    assert exact is False
    # 20% raw, stripped of the assumed hold.
    assert abs(implied - 0.20 / longshots.ONE_SIDED_HOLD) < 1e-9


def test_an_impossible_pair_is_treated_as_one_sided():
    """A stale -110 under recorded against a +400 over sums to under 100% —
    a book paying out more than it takes. De-vigging that pair produces an
    implied probability LOWER than the raw price, i.e. free money, on a
    number that was never real."""
    _implied, exact = longshots._price(0.22, 400, -110)
    assert exact is False


def test_the_caveat_explains_that_the_price_does_not_exist_to_be_pulled():
    pick = longshots.build_pick(
        player="A Hitter", team="ATL", opponent="WSH", market="home_runs",
        label="Anytime HR", book="FanDuel", odds=400, model_prob=0.21,
        under_odds=None, opportunities=4.0, opp_target=4.0,
        primary_reason="power", reasons=["r"], caveats=[], sport="mlb")
    assert pick is not None
    text = " ".join(pick.caveats)
    assert "don't offer the NO side" in text, \
        "the caveat still reads as a feed we failed to pull"
    assert "6%" in text, "the assumption is unquoted, so it cannot be judged"
    # And it must not oversell itself: the assumed hold is narrower than the
    # real one on a longshot, so this edge is a ceiling, not a floor.
    assert "optimistic" in text


def test_a_measured_price_carries_no_such_caveat():
    pick = longshots.build_pick(
        player="A Hitter", team="ATL", opponent="WSH", market="home_runs",
        label="Anytime HR", book="FanDuel", odds=400, model_prob=0.21,
        under_odds=-550, opportunities=4.0, opp_target=4.0,
        primary_reason="power", reasons=["r"], caveats=[], sport="mlb")
    assert pick is not None
    assert not any("NO side" in c for c in pick.caveats)


# --- the unconfirmed lineup -------------------------------------------------
def test_the_lineup_caveat_names_the_hour_it_clears():
    """"not confirmed yet" invites "why not?" and has no answer on the card.
    The answer is that the club has not filed the lineup, which happens on a
    schedule anyone can plan around."""
    first = datetime.datetime.now().astimezone() + datetime.timedelta(hours=7)
    msg = homeruns._lineup_eta(_Game(first.isoformat()))
    eta = first - datetime.timedelta(hours=homeruns.LINEUP_POSTS_BEFORE_H)
    assert "lineups post around" in msg
    assert str(int(eta.strftime("%I"))) in msg and eta.strftime("%M") in msg
    assert "clears itself" in msg, \
        "nothing tells the reader this resolves without their doing anything"


def test_an_unknown_first_pitch_does_not_invent_a_time():
    """A made-up hour is worse than no hour: it would be checked against, and
    found wrong."""
    for bad in ("", "tonight", "not-a-date"):
        assert homeruns._lineup_eta(_Game(bad)) == "not confirmed yet"


def test_the_caveat_is_attached_only_while_the_lineup_is_unconfirmed():
    """It reads MLB's own boxscore battingOrder, refreshed every minute — so
    a confirmed card must drop the warning rather than leaving a stale
    "verify he's starting" on a lineup that is now public."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "mlb", "homeruns.py"),
        encoding="utf-8").read()
    i = src.index('if not getattr(game, "lineups_confirmed", True):')
    assert "_lineup_eta(game)" in src[i:i + 260]
    assert "elif prop.lineup_spot in (0, None):" in src[i:i + 500], \
        "the confirmed-but-no-spot branch was lost"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
