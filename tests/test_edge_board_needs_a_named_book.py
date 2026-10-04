"""The board that stakes asks the question the other two already ask.

#207, answered 2026-09-16: YES, the edge board refuses an unattributed
game price.

THREE BOARDS, THREE ANSWERS, AND THE WRONG ONE STAKED.

  * Most Likely refuses it — `likely.admissible`, since 2026-09-09, from
    Ethan's screenshot of MIN ML -220 beside a market at -125.
  * The Pick of the Day refuses it — `potd.disqualify`, "no real market
    price".
  * The EDGE board recommended it at a full unit. Its gate checked the
    grade, the confidence, the edge, the juice, the price age and whether
    the game had started, and never the book.

That is the board money follows, so it was the one place the check
mattered most and the one place it was missing.

AND THE RULE LIVED IN THREE COPIES, which is how they drifted: the NFL's
gate in `pipeline._finish_bet`, baseball's in `mlb.pipeline._finish_bet`
and college's in `cfb_build._finish_sharp_card`. All three now call
`gamebets.price_is_attributable`, so there is one definition of what a
price is.

SHOWN, NOT RECOMMENDED — the same shape as the stale-price rule it sits
beside. The card keeps its number and says why it is not a play, because
a row that silently vanishes is a row nobody can question.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamebets as G                              # noqa: E402
from engine.models import Game, Weather                       # noqa: E402
from engine.rules import RuleConfig                           # noqa: E402


def _card(**kw):
    """A card that clears every OTHER bar on the edge board."""
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             home="KC", away="DEN", team="DEN", side="", line=0.0,
             pick_label="DEN ML", headline="DEN ML", matchup="DEN @ KC",
             win_prob=0.46, fair_prob=0.40, edge=0.06, odds=155,
             ev_per_unit=0.09, confidence=7.0, quality=70, grade="B+",
             credible=True, has_market=True, stake_units=1.0,
             reasons=[], warnings=[], book="DraftKings")
    d.update(kw)
    return d


def _nfl(card, book="DraftKings"):
    """THE BOOK LIVES ON THE GAME, not on the card handed in.

    `_finish_bet` calls `attach_books`, which copies the names off the
    Game object — so a fixture that sets `card["book"]` is overwritten
    and tests nothing. That is the right behaviour and it caught a first
    draft of this file."""
    from engine.pipeline import _finish_bet
    g = Game(home="KC", away="DEN", weather=Weather(dome=True),
             home_ml=-180, away_ml=155,
             home_ml_book=book, away_ml_book=book)
    return _finish_bet(dict(card), g, RuleConfig())


def _mlb(card):
    from engine.mlb.pipeline import _finish_bet
    from engine.mlb.models import MLBGame
    g = MLBGame(home="NYY", away="BOS", park="generic")
    return _finish_bet(card, g, RuleConfig())


# --- the rule itself ----------------------------------------------------------
def test_a_real_price_with_no_book_is_not_attributable():
    assert G.price_is_attributable({"odds": 155, "book": "DraftKings"})
    assert not G.price_is_attributable({"odds": 155, "book": ""})
    assert not G.price_is_attributable({"odds": 155, "book": "   "})
    assert not G.price_is_attributable({"odds": 155})


def test_the_engines_own_invented_price_is_refused_by_name():
    """"proxy" is what this codebase calls a number it made up, and the
    prop side has refused it since the Blackburn card."""
    assert not G.price_is_attributable({"odds": -140, "book": "proxy"})
    assert not G.price_is_attributable({"odds": -140, "book": "Proxy"})


def test_a_card_with_no_price_at_all_is_not_this_rules_business():
    """Zero odds means nothing was posted, which `has_market` and the
    grade already refuse. Failing it here too would print the wrong
    cause on a card that is not claiming anything — team totals, since
    #258, are exactly this shape."""
    assert G.price_is_attributable({"odds": 0, "book": ""})
    assert G.price_is_attributable({"bet_type": "team_total", "odds": 0})


# --- and it reaches the board that stakes -------------------------------------
def test_the_nfl_edge_board_will_not_stake_an_unattributed_price():
    assert _nfl(_card())["recommended"] is True, "the fixture cleared nothing"
    for bad in ("", "proxy"):
        d = _nfl(_card(), book=bad)
        assert d["recommended"] is False, f"staked a price from {bad!r}"


def test_the_baseball_edge_board_keeps_the_same_rule():
    """Baseball's gate is a separate function and had separately never
    asked."""
    assert _mlb(_card())["recommended"] is True
    assert _mlb(_card(book=""))["recommended"] is False


def test_the_college_edge_board_keeps_it_too():
    """College's gate is a THIRD copy in a different file, and a source
    grep cannot tell a gate that calls the rule from one that imports it
    and ignores the answer. `_book_for_side` returns "" when nobody is
    posting the taken side at the published line, which its own docstring
    says the parsers paper over with -110 — so this is not a hypothetical
    shape on that board, it is the documented one."""
    import cfb_build
    g = {"home": "Alabama", "away": "Auburn", "game_id": "x",
         "date": "2026-09-19", "kickoff": ""}

    def run(lines):
        card = dict(bet_type="moneyline", market="moneyline",
                    market_label="Moneyline", team="Alabama", side="",
                    line=0.0, odds=155, grade="B+", stake_units=1.0,
                    reasons=[], warnings=[])
        return cfb_build._finish_sharp(card, g, lines)

    named = run({"ml_books": {"Alabama": "DraftKings", "Auburn": "FanDuel"}})
    assert named["book"] == "DraftKings", named["book"]
    assert named["recommended"] is True, "the fixture cleared nothing"

    blank = run({"ml_books": {}})
    assert blank["book"] == ""
    assert blank["recommended"] is False, "college staked an unnamed price"
    assert G.UNATTRIBUTED_PRICE_WARNING in blank["warnings"]


def test_the_refused_card_still_renders_and_says_why():
    """Shown, not recommended — the stale-price shape. A row that simply
    disappears is a row nobody can question."""
    d = _nfl(_card(), book="")
    assert d["odds"] == 155, "the card lost its number"
    assert G.UNATTRIBUTED_PRICE_WARNING in d["warnings"], d["warnings"]
    assert "not a play" in G.UNATTRIBUTED_PRICE_WARNING


def test_a_named_book_carries_no_such_warning():
    assert G.UNATTRIBUTED_PRICE_WARNING not in _nfl(_card())["warnings"]


# --- the three boards cannot drift apart again --------------------------------
def test_every_game_recommendation_gate_asks_through_the_one_function():
    """The rule was in three copies and they had three different ideas of
    what a price is. If a fourth board grows a gate, this is what points
    at the function rather than at a fourth spelling."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("engine/pipeline.py", "engine/mlb/pipeline.py", "cfb_build.py"):
        src = open(os.path.join(root, rel), encoding="utf-8").read()
        assert "price_is_attributable" in src, \
            f"{rel} has a recommendation gate that does not ask about the book"


def test_the_sharp_book_case_is_left_out_on_purpose():
    """`potd` ALSO refuses a price quoted only at a sharp book, because
    Pinnacle does not take US action. The edge board deliberately does
    not, and the reason is written down rather than left as a silent
    difference between two boards."""
    assert G.price_is_attributable({"odds": 155, "book": "Pinnacle"}), \
        "the sharp-book rule arrived without the evidence it needs"
    assert "is_sharp_book" in (G.price_is_attributable.__doc__ or ""), \
        "the difference from potd stopped being explained"


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
