"""Game bets had none of the guards player props have had all along.

Reported from a screenshot of the NFL Edge Board, all on one screen:

    Josh Allen UNDER 259.5 Passing Yards   63% vs 50%   +21.4% EV   Pass
    CHI Over 18  (team total)              63% vs 50%   +19.9% EV   Play
    Over 43      (game total)              61% vs 50%   +16.1% EV   Play
    CHI +6.5     (spread)                  61% vs 50%   +15.5% EV   Play

The same 11-13 point disagreement with the market, four times. The prop
graded Pass. The three game bets graded Play. Only the prop layer ran the
shrink and the credibility ceiling — engine/gamebets.py imported `_grade`
and `_kelly_stake` from engine/betting.py and left `temper_edge` behind.

Spreads and totals are the most efficiently priced markets in American
sport. A 4-point disagreement with an NFL closing total is a statement
about our ratings, not a +17% edge.

Two smaller things this file also pins down:

  * The board's headline count was arithmetic wearing the clothes of a
    finding. On a two-way market the de-vigged prices sum to 1, so the two
    sides' edges sum to exactly zero — one side always prices positive, no
    matter what the model believes. "18 positively-priced bets" is the
    number of markets, and reading it as a haul is how a person talks
    themselves into a bad night.

  * gamebets looked its per-sport variance up with `.get(sport, default)`.
    CFB registers its own (engine.cfb.ratings.install, at import and again
    after each fit), so live builds were right — but anything pricing "cfb"
    without that import got the NFL's 13.5-point margin and NO home field,
    silently. Same shape as the backtest that fell back to nfl_win_prob for
    any sport it did not recognise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamebets
from engine.betting import MARKET_SHRINK, MAX_CREDIBLE_EDGE
from engine.odds import devig_two_way
from engine.statmath import normal_cdf


# --- the asymmetry that started it ------------------------------------------
def test_a_game_bet_takes_the_same_haircut_a_prop_does():
    """4 points off an NFL total is 11.7% raw. Untempered that rendered as
    +11.7% edge and +17.7% EV, graded Play."""
    raw = normal_cdf(4.0 / gamebets.NFL_TOTAL_SD)
    assert raw - 0.5 > 0.10, "the fixture no longer reproduces the report"
    card = gamebets.price_total("nfl", "CHI", "GB", 47.0, 43.0)
    assert card["edge"] < (raw - 0.5), "the raw edge is still being shown"
    assert abs(card["edge"] - MARKET_SHRINK * (raw - 0.5)) < 1e-3


def test_a_disagreement_too_large_to_be_an_edge_is_refused():
    card = gamebets.price_total("nfl", "CHI", "GB", 47.0, 43.0)
    assert card["credible"] is False
    assert card["grade"] == "Pass"
    assert card["stake_units"] == 0.0
    assert any("rating error" in r for r in card["reasons"])


def test_the_refusal_applies_to_every_game_market_not_just_totals():
    """The bug was one missing import, so it was missing everywhere."""
    cards = [
        gamebets.price_total("nfl", "H", "A", 47.0, 43.0),
        gamebets.price_team_total("nfl", "H", "H", "A", 27.0, 22.0),
        gamebets.price_spread("nfl", "H", "A", 4.5, 0.0),
    ]
    for c in cards:
        assert c["credible"] is False and c["grade"] == "Pass", c["pick_label"]
    ml = gamebets.price_moneyline("H", "A", 0.72, -110, -110)
    assert ml.grade == "Pass"


def test_a_real_sized_disagreement_still_bets():
    """The guard has to leave something behind, or it is just an off
    switch. A 3-point read on an NFL total survives."""
    card = gamebets.price_total("nfl", "CHI", "GB", 46.0, 43.0)
    assert card["credible"] is True
    assert card["grade"] != "Pass"
    assert 0 < card["edge"] < 0.05


def test_the_best_a_game_bet_can_now_claim_is_single_digits():
    """The ceiling is the point. Sweeping every disagreement from 0 to 12
    points, no bet that GRADES can show a double-digit EV — which is what
    made the reported board read as broken."""
    worst = 0.0
    for tenths in range(0, 121):
        c = gamefloat = gamebets.price_total("nfl", "H", "A",
                                             43.0 + tenths / 10.0, 43.0)
        if c["grade"] != "Pass":
            worst = max(worst, c["ev_per_unit"])
    assert 0 < worst < 0.10, f"a graded game bet can still claim {worst:+.1%} EV"


# --- the count that was never a finding -------------------------------------
def test_one_side_of_every_two_way_market_always_prices_positive():
    """Not a claim about the model — arithmetic. If this ever fails, the
    de-vig stopped normalising and every edge on the board is wrong."""
    for a, b in ((-110, -110), (-175, 150), (-250, 200), (120, -140)):
        fair_a, fair_b = devig_two_way(a, b)
        assert abs((fair_a + fair_b) - 1.0) < 1e-9
        for p in (0.2, 0.5, 0.63, 0.9):
            assert abs((p - fair_a) + ((1 - p) - fair_b)) < 1e-9


def test_the_board_leads_with_the_count_that_means_something():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "js", "app.js"), encoding="utf-8").read()
    # Anchored on the count itself, not on the sentence beside it. The
    # provenance clause gained a second variant on 2026-08-19 (a
    # schedule-only build prices off the schedule's own lines, not a book),
    # which pushed the two apart and broke a fixed-width window around the
    # copy — a test failing on where a comment sits, not on what the code
    # does.
    i = js.index("const plays = rows.filter(")
    block = js[i:i + 1600]
    assert "sum to zero" in block, "nothing explains why a full board is normal"
    assert "priced against a real book number" in block, \
        "the board stopped saying where its prices came from"
    # It must count the SAME flag the ✅ renders from. My first version read
    # r.recommended, which edge rows do not carry, so the headline reported
    # zero plays on a board showing several — a new wrong number replacing
    # the old one.
    tick = js[js.index("function edgeRowHTML("):]
    tick = tick[:tick.index("\n}\n")]
    flag = "r.rec" if "r.rec ?" in tick else None
    assert flag and f"{flag})" in block, \
        "the headline count and the ✅ read different fields"


# --- never another league's physics -----------------------------------------
def test_an_unregistered_sport_is_refused_rather_than_given_the_nfls_numbers():
    for call in (
        lambda: gamebets.price_total("kabaddi", "H", "A", 50.0, 45.0),
        lambda: gamebets.price_spread("kabaddi", "H", "A", 3.0, 0.0),
        lambda: gamebets.price_team_total("kabaddi", "T", "H", "A", 25.0, 22.0),
        lambda: gamebets.game_margin("kabaddi", 1.0, 0.0),
        lambda: gamebets.project_total("kabaddi", 1.0, 0.0, 1.0, 0.0),
    ):
        try:
            call()
        except ValueError as exc:
            assert "kabaddi" in str(exc) and "register" in str(exc).lower()
        else:
            raise AssertionError("priced a sport with a borrowed variance")


def test_college_football_brings_its_own_numbers():
    """And they are genuinely different — CFB is a wider, higher-scoring
    game, so borrowing football's 13.5 would inflate every edge by ~22% on
    spreads and ~50% on totals."""
    import engine.cfb.ratings          # noqa: F401 — installs on import
    assert gamebets.MARGIN_SD["cfb"] > gamebets.MARGIN_SD["nfl"]
    assert gamebets.TOTAL_SD["cfb"] > gamebets.TOTAL_SD["nfl"]
    assert gamebets.HOME_FIELD["cfb"] > gamebets.HOME_FIELD["nfl"]
    assert gamebets.SCORING_BASELINE["cfb"] > gamebets.SCORING_BASELINE["nfl"]


def test_cfb_gets_the_same_discipline_as_the_nfl():
    import engine.cfb.ratings          # noqa: F401
    hot = gamebets.price_total("cfb", "BAMA", "AUB", 58.0, 52.0)
    assert hot["credible"] is False and hot["grade"] == "Pass"
    ok = gamebets.price_total("cfb", "BAMA", "AUB", 55.0, 52.0)
    assert ok["credible"] is True


# --- the honest label on all of it ------------------------------------------
def test_the_confidence_curve_was_rescaled_with_the_shrink_not_left_behind():
    """Halving every edge while leaving the curve alone would have doubled
    the bar by accident and emptied the board — a different wrong answer."""
    assert abs(gamebets.CONFIDENCE_SATURATES_AT - 0.035) < 1e-9
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "gamebets.py"),
        encoding="utf-8").read()
    assert "never fitted" in src, \
        "the curve reads as measured when it is drawn by hand"


def test_max_credible_edge_is_shared_not_copied():
    assert gamebets.MAX_CREDIBLE_EDGE is MAX_CREDIBLE_EDGE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
