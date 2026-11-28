"""How many game prices carry no book name — counted, never enforced.

#207 was held open on purpose and the hold is worth restating, because
it is the reason this file counts instead of refusing.

`likely.from_game_bet` already refuses an unattributable football game
price outright. That is what took MIN ML -220 off the page on 2026-09-08
and it was right. The EDGE board does not apply the same rule, and the
comment in `engine/pipeline` says why in as many words: doing it blind
would ALSO withdraw the recommendation from every NFL game bet on a
build where the book names happen to be missing, and whether that was
the droplet's state could not be checked from here. One unverified swing
the night before Week 1 is enough.

What was actually missing was the number. Nobody knew whether the rule
costs nothing or costs a shelf, because nothing counted.

Tonight's `--ml-doctor` gives half the answer for free: 16 of 16 NFL
games named a book on BOTH moneyline sides, across seven books. Spread
and total have never been counted at all — the doctor prints
`board_spreads 16` and `board_totals 16` and says nothing about who
posted them.

So the counters go in, `--ml-doctor` prints `odds_status` whole, and one
paste tomorrow closes the hold with a measurement instead of a guess.
Nothing about what the board recommends changes tonight.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import oddsapi                           # noqa: E402


def test_both_result_shapes_carry_the_three_counters():
    """The board path and the event path both price games, and a build
    that took only one of them must not be silently uncounted."""
    for cls in (oddsapi.BoardLinesResult, oddsapi.OddsAttachResult):
        r = cls()
        assert r.unattributed_ml == 0
        assert r.unattributed_spread == 0
        assert r.unattributed_total == 0


def test_a_market_is_unattributed_when_either_side_has_no_name():
    """Not just when both are missing. A card is published for ONE side,
    and the likelihood board flips it to the other — so a game with a
    name on the home side only is a game that can still publish a price
    nobody posted."""
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    for a, b in (("home_ml_book", "away_ml_book"),
                 ("total_over_book", "total_under_book"),
                 ("home_spread_book", "away_spread_book")):
        assert f"if not (game.{a} and game.{b}):" in src, (a, b)


def test_every_pricing_site_counts_and_there_are_two_of_each():
    """`apply_board_lines_to_slate` and `apply_odds_to_slate` each set
    the book names, and a counter added to one only would report a clean
    board on whichever path that build happened to take."""
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    assert src.count("result.unattributed_ml += 1") == 2, src.count(
        "result.unattributed_ml += 1")
    assert src.count("result.unattributed_spread += 1") == 2
    assert src.count("result.unattributed_total += 1") == 2


def test_the_counts_reach_odds_status_from_both_paths():
    """`--ml-doctor` prints `odds_status` whole — that is what makes one
    paste enough to settle this. A counter that never reaches the board
    is a measurement nobody can read."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    for key in ("board_unattributed_ml", "board_unattributed_spread",
                "board_unattributed_total", "event_unattributed_ml",
                "event_unattributed_spread", "event_unattributed_total"):
        assert key in src, key


def test_nothing_recommends_or_refuses_on_this_yet():
    """The whole point of the hold. Counting must not quietly become
    enforcing — if a future commit wires this into `recommended`, that is
    a deliberate decision with a number behind it, not a side effect of
    the measurement landing."""
    for rel in ("engine/pipeline.py", "engine/mlb/pipeline.py",
                "engine/likely.py", "engine/betting.py"):
        body = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "unattributed_ml" not in body, rel
        assert "unattributed_spread" not in body, rel


def test_the_hold_is_written_down_where_the_next_reader_will_look():
    """A number with no question attached gets deleted as noise in six
    weeks. The field carries what it is for and what closes it."""
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    i = src.index("unattributed_ml: int = 0")
    note = src[max(0, i - 1400):i]
    assert "#207" in note
    assert "counted, never enforced" in note.lower()
    assert "MIN ML -220" in note


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
