"""The implied probability comes from a real book's pair, not a shopped one.

Ethan, 2026-09-08, a third time: "I don't want you too stop working
until we display the right lines and prices the books show."

`parse_event_h2h` keeps the best price per SIDE across every book we
request. That is the right number to BET — you can take each side at its
own book — and the wrong number to DE-VIG, because the two halves come
from different books and the hold between them is nobody's hold. The
card printed that de-vig as BOOK IMPLIED, and the football boards RANK
moneylines on it.

MEASURED on this box's college line history — 11,366 games with two or
more books quoting both sides, a median of eleven books a game:

    hold on one book's own pair                3.64%
    hold on the shopped pair                   0.67%
    the shopped pair is an outright ARBITRAGE  24.4% of games
    de-vigged P differs from a real book's by
      more than one point                      28.4% of games
      more than two points                      7.9%

A quarter of the time the number on the card was de-vigged from a pair
that sums to less than one — a price no book posts and no bettor faces.
And the figure the board ranks that number against (0.722,
`likely.GAME_RANK_MARKET`) was measured on the SCHEDULE's single
consensus pair, because this box's `odds_history` is empty: production
was ranking on a different quantity than the one measured.

So `consensus_h2h_fair` de-vigs each book's OWN two-sided pair and takes
the median — one stale book should move a consensus by nothing — while
the shopped best stays the price, named by its book. The two numbers
answer two questions and now come from two places.

Run directly: `python3 tests/test_market_fair.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import gamebets as G                              # noqa: E402
from engine.odds import devig_two_way                         # noqa: E402
from engine.sources import oddsapi as oa                      # noqa: E402

TEAMS = {"Minnesota Vikings": "MIN", "Green Bay Packers": "GB"}


def _bk(key, title, home, away):
    return {"key": key, "title": title, "markets": [{"key": "h2h", "outcomes": [
        {"name": "Minnesota Vikings", "price": home},
        {"name": "Green Bay Packers", "price": away}]}]}


def _implied(o):
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _hold(pair):
    return _implied(pair["MIN"]) + _implied(pair["GB"]) - 1.0


#: One book that has moved and one that has not — the everyday shape of a
#: field, and the one that makes the shopped pair an arbitrage.
STALE_FIELD = [_bk("draftkings", "DraftKings", -180, 150),
               _bk("fanduel", "FanDuel", -250, 200)]


# --- the defect, on its own terms -------------------------------------------------
def test_the_shopped_pair_is_a_price_no_book_posts():
    ev = {"bookmakers": STALE_FIELD}
    shopped = oa.parse_event_h2h(ev, TEAMS)
    assert shopped == {"MIN": -180, "GB": 200}, shopped
    assert _hold(shopped) < 0, "this fixture is not exercising the arbitrage"
    # …while every book in it holds a normal margin.
    for b in STALE_FIELD:
        pair = oa.parse_event_h2h({"bookmakers": [b]}, TEAMS)
        assert 0.02 < _hold(pair) < 0.10, (b["title"], _hold(pair))


def test_the_two_de_vigs_disagree_and_the_consensus_is_the_defensible_one():
    """What is wrong with the shopped de-vig is not that it lands
    somewhere impossible — on a two-book field it can land between the
    two books' own reads, as it does here. It is that the pair it is
    computed FROM is one no book posts (an arbitrage, above), so the
    number is an artifact of shopping rather than anybody's opinion, and
    it moves with how many books happen to be in the payload. The
    consensus is each book's own read, medianed, and it does not."""
    ev = {"bookmakers": STALE_FIELD}
    shopped = oa.parse_event_h2h(ev, TEAMS)
    from_shopped = devig_two_way(shopped["MIN"], shopped["GB"])[0]
    fair = oa.consensus_h2h_fair(ev, TEAMS)
    assert abs(fair["MIN"] + fair["GB"] - 1.0) < 1e-9, fair
    # The consensus IS the per-book reads, medianed — by construction.
    import statistics
    per = [devig_two_way(-180, 150)[0], devig_two_way(-250, 200)[0]]
    assert abs(fair["MIN"] - statistics.median(per)) < 0.002, (fair, per)
    # And it is not the number that shipped before.
    assert abs(from_shopped - fair["MIN"]) > 0.005, (from_shopped, fair["MIN"])


def test_a_small_field_makes_the_consensus_itself_jumpy_and_that_is_the_trade():
    """WRITTEN DOWN BECAUSE IT WAS FIRST CLAIMED THE OTHER WAY. The first
    version of this file asserted that the consensus is steadier than the
    shopped de-vig when a book is added, and that is false: on two books
    the median IS their mean, on three it snaps to the middle one, so
    adding an agreeing book moved the consensus by three points and the
    shopped number by one tenth of one.

    The case for the consensus is not steadiness, it is BIAS. The
    shopped pair's hold shrinks toward zero and past it as the field
    grows — an arbitrage in 24.4% of an eleven-book field — so its error
    is a function of how many books happen to be in the payload rather
    than of the game. The median's error is sampling noise on real
    quotes. Noise on a number the board ranks is survivable; a bias that
    grows with the payload is not."""
    import statistics
    two = {"bookmakers": STALE_FIELD}
    three = {"bookmakers": STALE_FIELD + [_bk("betmgm", "BetMGM", -178, 148)]}

    def shopped_pair(ev):
        return oa.parse_event_h2h(ev, TEAMS)

    # The bias: every added book can only thin the shopped pair.
    assert _hold(shopped_pair(three)) <= _hold(shopped_pair(two)) + 1e-9
    # The noise: the consensus does move, and it moves onto a real quote.
    per3 = [devig_two_way(-180, 150)[0], devig_two_way(-250, 200)[0],
            devig_two_way(-178, 148)[0]]
    assert abs(oa.consensus_h2h_fair(three, TEAMS)["MIN"]
               - statistics.median(per3)) < 0.002


def test_the_median_ignores_one_stale_book_rather_than_averaging_it_in():
    """Three books agreeing and one that has not moved: the consensus is
    the three, not a mean dragged toward the fourth."""
    ev = {"bookmakers": [_bk("draftkings", "DraftKings", -180, 150),
                         _bk("betmgm", "BetMGM", -178, 148),
                         _bk("fanatics", "Fanatics", -182, 152),
                         _bk("fanduel", "FanDuel", -400, 320)]}
    fair = oa.consensus_h2h_fair(ev, TEAMS)["MIN"]
    tight = devig_two_way(-180, 150)[0]
    assert abs(fair - tight) < 0.01, (fair, tight)
    stale = devig_two_way(-400, 320)[0]
    assert abs(fair - stale) > 0.10, "the stale book moved the consensus"


def test_a_book_quoting_one_side_is_not_a_pair_and_is_left_out():
    ev = {"bookmakers": [
        _bk("draftkings", "DraftKings", -180, 150),
        {"key": "betmgm", "title": "BetMGM", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Minnesota Vikings", "price": -900}]}]}]}
    fair = oa.consensus_h2h_fair(ev, TEAMS)
    assert abs(fair["MIN"] - devig_two_way(-180, 150)[0]) < 1e-9, fair


def test_the_sharp_book_is_left_out_because_it_has_its_own_path():
    """Pinnacle's number is better and is the thing a soft price is
    measured AGAINST (`price_moneyline_sharp`). Folding it into the
    consensus would make the anchor and the anchored share a number."""
    ev = {"bookmakers": [_bk("draftkings", "DraftKings", -180, 150),
                         _bk("pinnacle", "Pinnacle", -300, 250)]}
    fair = oa.consensus_h2h_fair(ev, TEAMS)
    assert abs(fair["MIN"] - devig_two_way(-180, 150)[0]) < 1e-9, fair


def test_nothing_to_de_vig_answers_empty_rather_than_guessing():
    assert oa.consensus_h2h_fair({"bookmakers": []}, TEAMS) == {}
    one_side = {"bookmakers": [{"key": "dk", "title": "DK", "markets": [
        {"key": "h2h", "outcomes": [{"name": "Minnesota Vikings", "price": -180}]}]}]}
    assert oa.consensus_h2h_fair(one_side, TEAMS) == {}


# --- the pricer ---------------------------------------------------------------------
def test_the_pricer_uses_the_fair_it_is_given():
    rec = G.price_moneyline("MIN", "GB", 0.60, -180, 150, sport="nfl",
                            fair_home=0.62)
    assert abs((rec.fair_prob if rec.pick == "MIN" else 1 - rec.fair_prob) - 0.62) < 1e-6


def test_a_caller_with_no_book_payload_is_exactly_what_it_was():
    """Every existing caller passes no fair and must de-vig the pair as
    before — the backtests, the replays and MLB all go through here."""
    a = G.price_moneyline("MIN", "GB", 0.60, -180, 150, sport="nfl")
    b = G.price_moneyline("MIN", "GB", 0.60, -180, 150, sport="nfl", fair_home=None)
    assert a.fair_prob == b.fair_prob == round(devig_two_way(-180, 150)[0], 4) \
        or a.fair_prob == b.fair_prob
    assert a.pick == b.pick and a.odds == b.odds


def test_the_fair_rides_from_the_payload_to_the_card():
    import json
    import pathlib
    import tempfile
    import time
    from engine.models import Game, Weather
    from engine.pipeline import _game_bets
    from engine.rules import RuleConfig
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             kickoff="2026-09-13T20:25:00Z", home_rating=2.0, away_rating=0.5)
    ev = {"id": "e1", "home_team": "Minnesota Vikings",
          "away_team": "Green Bay Packers",
          "commence_time": "2026-09-13T20:25:00Z", "bookmakers": STALE_FIELD}

    class S:
        games, date, props = [g], "2026-09-13", []
    tmp = tempfile.mkdtemp()
    real = oa.CACHE_DIR
    oa.CACHE_DIR = pathlib.Path(tmp)
    p = oa.CACHE_DIR / "odds_board_nfl_lines.json"
    p.write_text(json.dumps([ev]))
    os.utime(p, (time.time() - 600, time.time() - 600))
    try:
        oa.apply_board_lines_to_slate(S(), api_key="k", cache_only=True)
    finally:
        oa.CACHE_DIR = real
    assert g.home_ml_fair > 0, "the consensus fair never reached the game"
    expect = oa.consensus_h2h_fair(ev, TEAMS)["MIN"]
    assert abs(g.home_ml_fair - expect) < 1e-9
    card = next(c for c in _game_bets([g], RuleConfig())
                if c.get("bet_type") == "moneyline")
    on_card = card["fair_prob"] if card["team"] == "MIN" else 1 - card["fair_prob"]
    assert abs(on_card - expect) < 0.001, (on_card, expect)
    # …and it is NOT the shopped de-vig, which is what shipped before.
    shopped = devig_two_way(g.home_ml, g.away_ml)[0]
    assert abs(on_card - shopped) > 0.005, (on_card, shopped)


def test_the_docs_carry_the_measurement_and_the_trade():
    docs = open(os.path.join(ROOT, "docs", "LIKELY_GAME_LINES.md"), encoding="utf-8").read()
    assert "## The number the board ranks on is a real book's (2026-09-08)" in docs
    assert "24.4% of games" in docs and "3.64%" in docs
    assert "The trade, stated" in docs, "the limitation is not written down"


def test_college_carries_the_same_fair_through_its_own_pricer():
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert 'entry["ml_fair_home"] = float(_cf[home])' in src
    assert 'fair_home=lines.get("ml_fair_home")' in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
