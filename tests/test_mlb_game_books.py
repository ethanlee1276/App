"""Baseball game cards name the book posting the side they took.

Football has done this since 2026-09-07 (#199 for the NFL, #200 for
college). Baseball published the same three markets — moneyline, run
line, total — with a price and no shop beside it, which is a number a
reader cannot check against a phone at all. Ethan's standing complaint
is exactly one step further down the same road: "I don't want you too
stop working until we display the right lines and prices the books
show."

Nothing was missing but the copy. `apply_odds_to_slate` and
`apply_board_lines_to_slate` are sport-agnostic and set `home_ml_book`,
`total_over_book` and the rest on every slate they touch, so the names
were already on the Game object when MLB's pipeline built its cards.
The football pipeline had a block that copied them onto the row; MLB's
own `_finish_bet` had no equivalent and never had.

So the fix is a shared `gamebets.attach_books` called from both, rather
than the same fifteen lines written twice — which is the mistake that
produced the gap in the first place.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.gamebets import attach_books                     # noqa: E402


class _Game:
    """Only what the attribution reads. A slate Game carries far more."""

    def __init__(self, **kw):
        self.home, self.away = "LAD", "SDP"
        self.home_ml_book = "FanDuel"
        self.away_ml_book = "DraftKings"
        self.home_spread_book = "Caesars"
        self.away_spread_book = "BetMGM"
        self.total_over_book = "Hard Rock"
        self.total_under_book = "Fanatics"
        for k, v in kw.items():
            setattr(self, k, v)


def test_a_moneyline_names_the_book_for_the_side_taken():
    d = attach_books({"bet_type": "moneyline", "team": "SDP"}, _Game())
    assert d["book"] == "DraftKings", d
    assert d["home_book"] == "FanDuel" and d["away_book"] == "DraftKings"


def test_the_home_side_gets_the_home_book():
    d = attach_books({"bet_type": "moneyline", "team": "LAD"}, _Game())
    assert d["book"] == "FanDuel", d


def test_the_run_line_is_attributed_by_the_team_laid():
    """MLB's spread. #200 fixed the college version of exactly this: the
    card named the HOME book whichever side it took."""
    d = attach_books({"bet_type": "spread", "team": "SDP"}, _Game())
    assert d["book"] == "BetMGM", d


def test_a_total_is_attributed_by_the_side_not_the_home_team():
    over = attach_books({"bet_type": "total", "side": "OVER"}, _Game())
    under = attach_books({"bet_type": "total", "side": "under"}, _Game())
    assert over["book"] == "Hard Rock", over
    assert under["book"] == "Fanatics", under


def test_both_sides_ride_along_so_a_flipped_card_can_flip_its_book():
    """`likely.from_game_bet` shows the side more likely to LAND, which
    is the other side whenever a card backed a sub-50% price. A row
    carrying only the taken side's book would then name the shop that
    quoted a side it is no longer showing."""
    d = attach_books({"bet_type": "total", "side": "OVER"}, _Game())
    assert d["over_book"] and d["under_book"]
    assert d["over_book"] != d["under_book"]


def test_a_team_total_gets_no_book_and_that_is_the_answer():
    """Nothing quotes one — the number is derived from the game total
    and the spread. An invented name would be worse than none."""
    d = attach_books({"bet_type": "team_total", "team": "LAD"}, _Game())
    assert "book" not in d or not d["book"], d


def test_an_unquoted_market_leaves_an_empty_name_not_a_missing_key():
    """A build where the books were absent must still produce the field,
    so a reader can tell "nobody posted this" from "we forgot to look"."""
    g = _Game(home_ml_book="", away_ml_book="")
    d = attach_books({"bet_type": "moneyline", "team": "LAD"}, g)
    assert d["book"] == "" and d["home_book"] == "" and d["away_book"] == ""


def test_a_game_missing_the_attributes_entirely_does_not_raise():
    """Backtest and replay games are plain objects built from history and
    carry no book columns. A pricer that raised on them would take the
    whole board down to add a label."""
    class _Bare:
        home, away = "LAD", "SDP"
    d = attach_books({"bet_type": "moneyline", "team": "LAD"}, _Bare())
    assert d["book"] == ""


def test_the_mlb_pipeline_actually_stamps_the_card():
    """Through MLB's own `_finish_bet`, not by grepping for the helper's
    name — the first cut of this test did that and passed against a
    pipeline that had stopped calling it, because the word survived in a
    comment. A name in a comment is not a call."""
    from engine.mlb.pipeline import _finish_bet
    from engine.rules import RuleConfig

    g = _Game()
    g.live = None
    g.date, g.kickoff = "2026-07-04", "19:10"
    g.status, g.state = "scheduled", "pre"
    card = _finish_bet(
        {"bet_type": "moneyline", "team": "SDP", "grade": "B",
         "confidence": 7.0, "edge": 0.04, "odds": -110},
        g, RuleConfig())
    assert card["book"] == "DraftKings", card
    assert card["home_book"] == "FanDuel", card


def test_the_football_pipeline_no_longer_carries_its_own_copy():
    """Two copies of one rule is what produced the gap: football grew the
    block, baseball never did. Pinned so the next market added to either
    cannot fork it again."""
    nfl = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    assert 'd["home_book"] = getattr(g, "home_ml_book"' not in nfl
    assert "attach_books" in nfl


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
