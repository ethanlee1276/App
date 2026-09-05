"""A game bet needs a price a book actually posted.

Found chasing #73 — why the live board carries open game bets when the
replay grades none over 1,184 games. That question is still open, but the
hunt turned up a live hole underneath it.

THREE DEFAULTS THAT LIED TOGETHER. `Game.total_over_odds` defaulted to
-110, which is indistinguishable from a book quoting -110. `Game.total`
defaults to 44.0. And `_game_bet` never set `has_market` at all — the
flag `ledger.journal_skip_reason` uses to refuse a proxy-priced row,
which it tests with `is False`, and None is not False.

So a game nobody had posted a total for was priced against a fabricated
44.0 at a fabricated -110, graded, and journaled, with nothing anywhere
on the row saying either number was invented. The moneyline was the one
game market that never had this bug, because it has always used 0 for
"not offered" and gated on it.

Run directly: `python3 tests/test_gamepriced.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gamebets import (price_total, price_spread,        # noqa: E402
                             price_team_total, _real_price)
from engine.ledger import journal_skip_reason                  # noqa: E402
from engine.models import Game, Weather                        # noqa: E402

SLATE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "sample_slate.json")


# --- a missing price is representable now --------------------------------
def test_not_offered_is_zero_the_way_the_moneyline_always_had_it():
    """-110 as a default cannot be told apart from a book quoting -110.
    0 can, and `home_ml` has used that convention since it shipped —
    which is exactly why the moneyline never grew this bug."""
    g = Game(home="KC", away="DEN", weather=Weather(dome=True))
    assert g.total_over_odds == 0 and g.total_under_odds == 0
    assert g.spread_home_odds == 0 and g.spread_away_odds == 0
    assert g.home_ml == 0 and g.away_ml == 0


def test_the_loader_does_not_invent_juice_for_a_market_nobody_posted():
    import inspect
    from engine import data_loader
    src = inspect.getsource(data_loader)
    assert 'g.get("total_over_odds", 0)' in src
    assert 'g.get("spread_home_odds", 0)' in src
    assert '"total_over_odds", -110' not in src


# --- the flag that could never fire --------------------------------------
def test_a_game_bet_now_carries_has_market():
    """It returned None, and `journal_skip_reason` tests `is False`. None
    is not False, so every game bet walked past a guard the prop layer
    has applied since it shipped."""
    real = price_total("nfl", "KC", "DEN", 47.0, 44.5, -110, -110)
    fake = price_total("nfl", "KC", "DEN", 47.0, 44.5, 0, 0)
    assert real["has_market"] is True
    assert fake["has_market"] is False


def test_the_journal_refuses_a_fabricated_price():
    row = dict(price_total("nfl", "KC", "DEN", 47.0, 44.5, 0, 0),
               recommended=True, stake_units=1.0, market="total")
    why = journal_skip_reason(row)
    assert why and "proxy" in why, why
    # And takes the same bet when a book really posted it.
    ok = dict(price_total("nfl", "KC", "DEN", 47.0, 44.5, -110, -110),
              recommended=True, stake_units=1.0, market="total")
    assert journal_skip_reason(ok) is None


def test_every_game_market_declares_it_not_just_the_total():
    for card in (price_spread("nfl", "KC", "DEN", -3.0, -3.5, 0, 0),
                 price_team_total("nfl", "KC", "KC", "DEN", 27.5, 23.5, 0, 0)):
        assert card["has_market"] is False, card["market"]
    for card in (price_spread("nfl", "KC", "DEN", -3.0, -3.5, -110, -110),
                 price_team_total("nfl", "KC", "KC", "DEN", 27.5, 23.5,
                                  -110, -110)):
        assert card["has_market"] is True, card["market"]


def test_real_price_wants_every_side_not_just_one():
    assert _real_price(-110, -110)
    assert not _real_price(-110, 0)
    assert not _real_price(0, -110)
    assert not _real_price(0, 0)


# --- the board stops pricing what nobody offered -------------------------
def test_the_board_skips_a_total_no_book_posted():
    """`Game.total` defaults to 44.0, so without this gate a game with
    ratings and no posted total was compared against an invented number.
    The team totals go with it: their line is SPLIT from the total and
    the spread, so without a posted total there is nothing to split."""
    import inspect
    from engine import pipeline
    src = inspect.getsource(pipeline._game_bets)
    assert "priced_total = bool(g.total_over_odds and g.total_under_odds)" in src
    assert "if has_rating and priced_total:" in src
    # RE-ANCHORED 2026-09-03, same guarantee, better spelling. This read
    # `g.spread and g.spread_home_odds and g.spread_away_odds`, and the
    # leading `g.spread` dropped every PICK'EM along with every missing
    # spread — 0.0 is an ordinary NFL line, not an absence. It also could
    # not gate the team totals, whose line is split by the spread: the
    # docstring above says "the total and the spread" and the code tested
    # the total alone. Both now ask `Game.spread_is_posted`.
    assert "g.spread_is_posted and g.spread_home_odds and g.spread_away_odds" in src
    assert "if g.spread_is_posted:" in src, \
        "team totals are no longer gated on the spread they are split by"


def test_a_slate_with_no_posted_lines_produces_no_game_bets():
    from engine.pipeline import _game_bets
    from engine.rules import RuleConfig
    g = Game(home="KC", away="DEN", weather=Weather(dome=True),
             home_off=3.0, home_def=-1.0, away_off=-2.0, away_def=1.0)
    assert not _game_bets([g], RuleConfig()), \
        "a game nobody priced is not a board"


def test_a_slate_with_posted_lines_still_produces_them():
    """The gate must not silence a real board — that would be the same
    failure in the other direction."""
    from engine.pipeline import _game_bets
    from engine.rules import RuleConfig
    g = Game(home="KC", away="DEN", weather=Weather(dome=True),
             home_off=3.0, home_def=-1.0, away_off=-2.0, away_def=1.0,
             total=44.5, spread=-3.5, home_ml=-180, away_ml=155,
             total_over_odds=-110, total_under_odds=-110,
             spread_home_odds=-110, spread_away_odds=-110)
    got = _game_bets([g], RuleConfig())
    markets = {r["market"] for r in got}
    assert {"moneyline", "total", "team_total", "spread"} <= markets, markets
    assert all(r["has_market"] for r in got)


def test_the_suite_is_green_on_a_board_only_an_uncalibrated_box_produces():
    """A TRAP FOUND BY TRIPPING IT, and worth leaving lit.

    `test_gamebets.test_pipeline_emits_game_bets` asserts that some game
    bet on the sample slate is RECOMMENDED. On this box, with a fitted
    `gamecal` store, nothing is — the measured shrink is 0.03 on totals
    and 0.006 on spreads and the board correctly goes silent. It passes
    only because `run_tests` points QB_MODELS_DIR at an empty sandbox,
    where the shrink falls back to the 0.5 guess.

    So the suite is green on a board that exists only where the
    calibration has never run. That is the same condition
    `nflready.game_shrink` reports as BETTING ON A GUESS, and the same
    one that puts 232 total bets at -7.5% ROI in replay.

    Not a bug in the fixture and not fixed here — the sandbox is what
    keeps the suite honest about the machine. Recorded so the next person
    to see a recommended game bet in a test does not read it as evidence
    the model qualifies one."""
    from engine.pipeline import run_slate
    from engine import gamecal as GC
    real = GC.shrink_for
    try:
        GC.shrink_for = lambda s, m: 0.03          # a fitted box
        tight = [b for b in run_slate(SLATE)["game_bets"] if b["recommended"]]
        GC.shrink_for = lambda s, m: 0.5           # an unfitted one
        loose = [b for b in run_slate(SLATE)["game_bets"] if b["recommended"]]
    finally:
        GC.shrink_for = real
    assert not tight, \
        "a measured shrink must not recommend a game bet on this slate"
    assert loose, "the 0.5 fallback is what produces a game board at all"


# --- #73, answered ------------------------------------------------------
def test_every_game_card_records_the_haircut_that_priced_it():
    """WHY #73 TOOK THREE INVESTIGATIONS. Twelve NFL game bets sat open
    from 2026-08-08 to 08-12 with 7.64 units staked, while the replay
    graded none at all over 1,184 games. Nothing on those rows said which
    market haircut had priced them, so the live board and the replay
    could not be compared directly and the gap had to be cornered by
    elimination.

    `engine.ledger` has kept `cal_temp` on props all along for exactly
    this — "the correction that was live when the row was logged", with
    the contract that a row recording its correction can be un-corrected
    and one that does not, cannot. Game bets recorded nothing."""
    from engine import gamecal as GC
    real = GC.shrink_for
    try:
        GC.shrink_for = lambda s, m: 0.03
        cards = [price_total("nfl", "KC", "DEN", 47.0, 44.5, -110, -110),
                 price_spread("nfl", "KC", "DEN", -3.0, -3.5, -110, -110),
                 price_team_total("nfl", "KC", "KC", "DEN", 27.5, 23.5,
                                  -110, -110)]
        assert all(c["cal_temp"] == 0.03 for c in cards), \
            [c["cal_temp"] for c in cards]
        GC.shrink_for = lambda s, m: None
        blind = price_total("nfl", "KC", "DEN", 47.0, 44.5, -110, -110)
        assert blind["cal_temp"] is None, \
            "an unmeasured market must be distinguishable from a measured one"
    finally:
        GC.shrink_for = real


def test_the_moneyline_records_it_through_its_own_builder():
    """It does not go through `_game_bet`, so it needed its own wiring
    and would otherwise have been the one market with no memory."""
    from engine.gamebets import price_moneyline, moneyline_to_dict
    from engine import gamecal as GC
    real = GC.shrink_for
    try:
        GC.shrink_for = lambda s, m: 0.07
        got = moneyline_to_dict(price_moneyline("KC", "DEN", 0.62, -180, 155,
                                                [], sport="nfl"))
    finally:
        GC.shrink_for = real
    assert got["cal_temp"] == 0.07


def test_the_arithmetic_that_closed_it():
    """The largest edge that can survive is MAX_CREDIBLE_EDGE x shrink:
    anything more disagreeable is refused as our error before the haircut
    ever sees it. So a fitted shrink caps a game edge at 0.003 to 0.009,
    and only the 0.5 fallback reaches 0.05.

    The twelve open rows ran 0.0340 to 0.0495 — every one of them under
    the fallback ceiling and none reachable at any fitted value. They were
    priced before `gamecal` had measured anything, three weeks before the
    replay they appeared to contradict. The board and the replay never
    disagreed; they were run at different haircuts."""
    from engine.gamebets import MAX_CREDIBLE_EDGE
    observed = (0.0340, 0.0495)
    for shrink in (0.0296, 0.0558, 0.0904):
        assert MAX_CREDIBLE_EDGE * shrink < observed[0], shrink
    assert MAX_CREDIBLE_EDGE * 0.5 >= observed[1]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
