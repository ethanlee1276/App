"""A moneyline that contradicts its own game's spread is not a price.

Ethan, 2026-09-08, two screenshots side by side — his sportsbook and our
Most Likely page:

    his book   DAL -3   ·  DAL -162 / NYG +136
    our board  NYG ML -218, 66% likely, "the likely side"

    his book   MIN -1.5 ·  MIN -125 / GB +105
    our board  MIN ML -220, 67% likely

"Also the money lines we are showing on the most likley page is
completely wrong."

The Giants card is wrong on its own terms, and that is what makes it
catchable: the spread on that game makes Dallas the favourite and the
moneyline on the same card makes the Giants a 66% favourite. Two
numbers, one card, opposite conclusions, and nothing ever read them
together. It is the third report of this class — 2026-09-03 twice, "the
lines ... are completely wrong so we are giving bad bets" and "a lot of
the money lines and shit are wrong" — and the first two were answered
with freshness stamps, which say a price is OLD and cannot say a price
is WRONG.

MEASURED BEFORE IT WAS BARRED, on this box's 1,424 stored NFL closes
holding both a closing moneyline and a spread. For each, the book's
de-vigged P(home) against its own spread through the sport's win curve:

    median gap 0.036 · 99th 0.102 · 99.9th 0.113 · largest 0.118
    games where the two named a different favourite: 0 of 1,424

A book keeps its two markets within about a tenth of each other and
never crosses over, so `likely.SPREAD_COHERENCE` is 0.15 — above every
disagreement five seasons of closes contain. The Giants card scores
0.199 and is refused. The Vikings card scores 0.083 and is not: that
one is a price that is merely old, and this bar does not pretend to see
age. Both facts are pinned below so neither is claimed as more than it
is.

Run directly: `python3 tests/test_spread_ml_coherence.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import boardlint as L, gamebets as G, likely as K       # noqa: E402
from engine.odds import devig_two_way                               # noqa: E402

WHY = "the moneyline disagrees with this game’s own spread by more than any book has"


def _card(home_spread, home_ml, away_ml, **kw):
    """A moneyline card in the shape both builds ship, with the game's
    own spread on it (`pipeline._finish_bet`, `cfb_build.to_game_bet`)."""
    fair_home, fair_away = devig_two_way(home_ml, away_ml)
    home_first = kw.pop("home_first", True)
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="NYG", away="DAL",
             team="NYG" if home_first else "DAL", pick_is_home=home_first,
             pick_label=("NYG ML" if home_first else "DAL ML"), side="", line=0.0,
             matchup="DAL @ NYG",
             win_prob=fair_home if home_first else fair_away,
             fair_prob=fair_home if home_first else fair_away,
             edge=0.0, odds=home_ml if home_first else away_ml,
             home_odds=home_ml, away_odds=away_ml, ev_per_unit=0.0,
             confidence=6.0, stake_units=0.0, grade="Pass", credible=True,
             headline="ML", reasons=[], recommended=False, live=False,
             date="2026-09-13", game_spread=home_spread)
    d.update(kw)
    return d


# --- the curve the check reads ------------------------------------------------
def test_a_posted_spread_reads_as_a_win_probability_on_its_own_sports_curve():
    """The HOME number, negative when home is favoured, through the same
    curve that prices that sport's moneyline."""
    pick_em = G.spread_win_prob("nfl", 0.0)
    assert abs(pick_em - G.nfl_win_prob(0.0, 0.0)) < 1e-9
    assert 0.50 < pick_em < 0.60, "the NFL curve carries its own home field"
    assert G.spread_win_prob("nfl", -7.0) > G.spread_win_prob("nfl", -3.0) > pick_em
    assert G.spread_win_prob("nfl", 7.0) < pick_em
    assert G.spread_win_prob("nhl", -1.5) is None, "no curve, no answer"
    assert G.spread_win_prob("nfl", None) is None


def test_college_answers_none_until_its_own_numbers_are_registered():
    """College installs its measured home field and margin spread at
    build time; outside a build there is nothing to read, and a missing
    curve must not become a guess. Inside the build the check runs."""
    got = G.spread_win_prob("cfb", -13.5)
    assert got is None or 0.0 < got < 1.0


# --- the bar ------------------------------------------------------------------
def test_the_giants_card_from_the_screenshot_is_refused():
    census: dict = {}
    row = K.from_game_bet(_card(3.0, -218, 180), "nfl", census=census)
    assert row is None and census == {WHY: 1}, (row, census)


def test_the_same_game_priced_as_the_book_actually_had_it_ships():
    """DAL -3 with DAL -162 / NYG +136: the two markets agree, the row is
    fine, and the board shows Dallas."""
    census: dict = {}
    row = K.from_game_bet(_card(3.0, 136, -162, home_first=False), "nfl",
                          census=census)
    assert row is not None and census == {}, census
    assert row["team"] == "DAL" and row["odds"] == -162


def test_the_vikings_card_is_not_caught_and_the_test_says_so():
    """MIN -1.5 with MIN -220: 0.083 apart, inside what real books do.
    A price that is merely OLD is invisible to this bar. Pinned so
    nobody reads the guard as covering staleness."""
    row = K.from_game_bet(_card(-1.5, -220, 200, home="MIN", away="GB",
                                team="MIN", matchup="GB @ MIN"), "nfl")
    assert row is not None and K.admissible(row) == ""


def test_the_check_reads_the_home_side_whichever_side_the_card_took():
    """The card backs whichever side has the edge; the comparison is
    always home against home, so a dog card is judged the same."""
    for home_first in (True, False):
        assert K.from_game_bet(_card(3.0, -218, 180, home_first=home_first),
                               "nfl") is None, home_first


def test_the_bar_sits_above_every_disagreement_five_seasons_hold():
    assert K.SPREAD_COHERENCE == 0.15
    # 0.118 was the largest in 1,424 closes; the bar clears it and is not
    # so wide that the screenshot's 0.199 slips through.
    assert 0.118 < K.SPREAD_COHERENCE < 0.199


def test_a_row_that_cannot_be_checked_is_not_a_row_that_is_refused():
    for kw in ({"game_spread": None}, {"fair_prob": None}):
        row = K.from_game_bet(_card(3.0, -218, 180, **kw), "nfl")
        assert row is not None, kw
    # …and a sport with no registered curve cannot be asked at all.
    assert K.from_game_bet(_card(3.0, -218, 180), "nhl") is None, \
        "an unmeasured sport should refuse on the market, not on the spread"


def test_only_the_moneyline_is_asked():
    """A spread row IS the spread; asking it to agree with itself would
    refuse the shelf Ethan asked for on 2026-09-02."""
    tot = dict(bet_type="total", market="total", market_label="Total",
               has_market=True, home="NYG", away="DAL", team="", side="Over",
               line=48.5, pick_label="Over 48.5", matchup="DAL @ NYG",
               win_prob=0.60, fair_prob=0.52, edge=0.08, odds=-110,
               other_odds=-110, ev_per_unit=0.0, confidence=5.0,
               stake_units=0.0, grade="Pass", credible=True, headline="Over",
               reasons=[], recommended=False, live=False, date="2026-09-13",
               game_spread=3.0)
    assert K.from_game_bet(tot, "nfl") is not None


# --- the builds put the spread on the card ------------------------------------
def test_both_football_builds_carry_the_games_spread_onto_every_card():
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    cfb = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert 'd["game_spread"] = g.spread if g.spread_is_posted else None' in pipe
    assert '"game_spread": game.get("spread"),' in cfb
    # An unposted spread is None, not a zero — a pick'em is a real line.
    fin = pipe[pipe.index("def _finish_bet("):pipe.index("\n#: (season, opponent)")]
    assert "spread_is_posted" in fin


def test_the_lint_reads_the_two_numbers_together_on_an_older_board():
    row = {"kind": "game", "player": "NYG ML", "team": "NYG", "home": "NYG",
           "away": "DAL", "market": "moneyline", "bet_type": "moneyline",
           "side": "", "odds": -218, "model_prob": 0.657, "implied_prob": 0.657,
           "fair_prob": 0.657, "pick_is_home": True, "game_spread": 3.0,
           "prob_source": "market", "ranked": True, "game_date": "2099-01-01"}
    flags = L.lint_likely([row], {})[0]["flags"]
    assert any(f.startswith("SPREAD vs ML") for f in flags), flags
    ok = dict(row, game_spread=-7.0)
    assert not any(f.startswith("SPREAD vs ML") for f in L.lint_likely([ok], {})[0]["flags"])


def test_the_docs_carry_the_measurement_and_the_droplet_check():
    docs = open(os.path.join(ROOT, "docs", "LIKELY_GAME_LINES.md"), encoding="utf-8").read()
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert "## The moneyline and the spread, read together (2026-09-08)" in docs
    assert "0 of 1,424" in docs and "0.118" in docs
    assert "## 8f. The moneyline that disagreed with its own spread" in checks
    assert "game_spread" in checks


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
