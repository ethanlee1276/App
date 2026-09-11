"""A quarterback's touchdowns: not on his page, not on either board.

Ethan, 2026-09-10: "when we search a QB, we are not showing passing
touchdown stats at all, and we also don't display that as a pick in the
edge bets or most likely bets so we need too fix that now."

FOUR SEPARATE CAUSES, each of which alone was enough, which is why it
looked like one missing feature rather than four missing lines:

  the page      `statlogs.SPORT_MARKETS["nfl"]` — the list the search
                page draws its chips from — named passing YARDS and not
                passing touchdowns. The rows have been on disk since
                August (`ingest.NFL_USAGE_MARKETS`); nothing asked for
                them.
  the quote     `sources.oddsapi.ODDS_TO_MARKET` never requested
                `player_pass_tds`, so no book price for it has ever
                entered this system.
  the prop      `sources.nflverse.POSITION_MARKETS` gave a quarterback
                exactly one market, so there was no `Prop` for a quote
                to attach to even had one arrived.
  the model     nothing projected it, so there was nothing to price a
                quote against.

THE MEASUREMENT IS THE PART THAT DECIDES WHAT MAY BE CLAIMED, and it is
written into `engine/passtd`'s module note with the numbers: fitted on
2021-2024 and scored on held-out 2025, the blend sorts a quarterback who
throws at least one from one who does not at 0.687 over 647 games. That
clears `likely.MIN_RANK_AUC` and is what `RANK_AUC["pass_td"]` carries —
the held-out figure, not the 0.715 the same fit scored in sample.

Ranking is not edge. `quality.MARKET_TIER` already filed `pass_td` as
Tier 3 with the 6% post-haircut minimum that quarantines the touchdown
markets, and nothing here relaxes it: a card earns the edge board the
way an anytime-TD card does or it does not appear on it.

Run directly: `python3 tests/test_pass_td_market.py`
"""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import passtd                                    # noqa: E402
from engine.likely import MIN_RANK_AUC, RANK_AUC, rankable   # noqa: E402
from engine.markets import words                             # noqa: E402
from engine.models import (MARKET_LABELS, PASS_TD, Prop,     # noqa: E402
                           GameLog, SportsbookLine, Game, Team,
                           DefenseProfile, Weather)
from engine.quality import MARKET_TIER                       # noqa: E402
from engine.statlogs import SPORT_MARKETS                    # noqa: E402


# --- the page ---------------------------------------------------------------
def test_the_search_page_lists_passing_touchdowns():
    """The report's first half, in one assertion."""
    assert "pass_td" in dict(SPORT_MARKETS["nfl"])
    assert "pass_td" in dict(SPORT_MARKETS["cfb"]), \
        "a college quarterback's page has the same hole"


def test_the_stat_chip_and_the_priced_market_wear_one_label():
    """`statlogs` dedupes chips BY LABEL, so a second spelling would draw
    one stat on two chips now that the market is also priced — the trap
    the `anytime_td` entry beside it already documents."""
    assert dict(SPORT_MARKETS["nfl"])["pass_td"] == MARKET_LABELS[PASS_TD]
    assert words()["pass_td"] == MARKET_LABELS[PASS_TD]


# --- the quote and the prop -------------------------------------------------
def test_the_market_is_modelled_and_shelved_but_not_bought():
    """THE INCIDENT, 2026-09-10. `player_pass_tds` went onto the NFL odds
    request at 16:36 UTC and deployed at ~16:41. Ethan at 17:58: "all the
    edge bets and most likely bets for nfl disappeared" — inside the last
    thirty minutes, which is the first board rebuild after that deploy.

    `fetch_event_odds` joins this map's keys into ONE `markets=`
    parameter per event, so a key the API will not serve does not cost
    that one market, it costs the whole event — every market, every NFL
    game. Both boards are built from those props, which is why both went
    at once and why CFB, which was deliberately never given the key, was
    untouched.

    So the request is back to the four it was buying at 16:35. Everything
    else stays: the market is still modelled, still ranked, still
    shelved. What is rolled back is asking the book for it."""
    from engine.sources.oddsapi import (NFL_ODDS_TO_MARKET, ODDS_TO_MARKET,
                                        PASS_TD_ODDS_KEY, SPORT_CONFIG)
    assert PASS_TD_ODDS_KEY == "player_pass_tds"
    assert PASS_TD_ODDS_KEY not in SPORT_CONFIG["nfl"]["markets"], \
        "the key is back on the request without the guard that makes it safe"
    assert PASS_TD_ODDS_KEY not in SPORT_CONFIG["cfb"]["markets"]
    assert NFL_ODDS_TO_MARKET == ODDS_TO_MARKET
    # AND THE BUDGET COUNTS WHAT IS ACTUALLY ASKED FOR. It went to 13
    # with the key and back to 12 without it; a budget that counts a
    # market nobody requests plans with a number wrong in the direction
    # that under-spends.
    from engine.oddsbudget import credits_per_event
    assert credits_per_event("nfl") == 12


def test_one_unusable_market_must_not_be_able_to_empty_the_board():
    """The defect worth fixing, named where somebody will find it before
    re-adding the key. Every market for an event goes in a single
    request, so the blast radius of one bad key is the entire NFL board —
    and nothing in the code says so until it happens."""
    import os
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    i = src.index("def fetch_event_odds(")
    assert '",".join(markets)' in src[i:i + 900], \
        "the request no longer joins its markets — re-read this note"
    assert "TO PUT IT BACK" in src, "the re-enable conditions are gone"


def test_a_quarterback_gets_a_prop_for_it():
    from engine.sources.nflverse import POSITION_MARKETS, MARKET_COLUMNS
    assert PASS_TD in [m for m, _role in POSITION_MARKETS["QB"]]
    assert MARKET_COLUMNS[PASS_TD] == ("passing_tds",), \
        "the log column must be the passing one, not a touchdown sum"


# --- the model --------------------------------------------------------------
def test_an_empty_log_is_the_league_and_not_a_zero():
    """A quarterback with nothing behind him is an average one until he
    is not — a weaker claim than any number his own zero games support."""
    assert passtd.projection([]) == passtd.LEAGUE_PASS_TD


def test_the_projection_moves_with_the_man():
    elite = passtd.projection([3, 2, 4, 3, 2, 3, 3, 2])
    backup = passtd.projection([0, 0, 1, 0, 0, 0])
    assert elite > passtd.LEAGUE_PASS_TD > backup
    assert backup > 0, "shrunk toward the league, never to zero"


def test_a_thin_log_is_pulled_toward_the_league_harder_than_a_long_one():
    thin = passtd.projection([4, 4])
    long_ = passtd.projection([4] * 40)
    assert long_ > thin, "the prior must matter more when there is less"


def test_the_tails_are_poisson_and_not_a_normal_approximation():
    """A count of nought to about five through a normal fitted to it is
    visibly wrong at exactly the half-points the market hangs."""
    lam = 1.6
    assert abs(passtd.at_least(lam, 0.5) - (1 - math.exp(-lam))) < 1e-12
    assert abs(passtd.at_least(lam, 1.5)
               - (1 - math.exp(-lam) * (1 + lam))) < 1e-12
    # …and it is monotone in the line, which a mis-indexed sum is not.
    got = [passtd.at_least(lam, x) for x in (0.5, 1.5, 2.5, 3.5)]
    assert got == sorted(got, reverse=True), got


def test_a_dead_arm_and_a_hot_one_bracket_the_probability():
    assert passtd.at_least(0.0, 0.5) == 0.0
    assert passtd.at_least(9.0, 0.5) > 0.999


def test_the_form_windows_are_spelled_the_way_the_page_reads_them():
    assert set(passtd.form([1, 2, 3])) == {
        "last1", "last3", "last5", "last10", "season", "career",
        "vs_opponent"}
    assert passtd.form([])["last5"] is None, "no games is not an average"


# --- what the boards are allowed to claim -----------------------------------
def test_the_rank_figure_is_the_held_out_one():
    """0.687 is 2025 with the window chosen on 2021-24. 0.715 is the
    same fit scoring itself. Publishing the second would be reporting a
    number that never survived a season it had not seen."""
    assert RANK_AUC["pass_td"] == 0.687
    assert RANK_AUC["pass_td"] >= MIN_RANK_AUC
    assert RANK_AUC["pass_td"] < RANK_AUC["anytime_td"], \
        "it should not out-rank the scorer board it is measured beside"


def test_the_most_likely_board_will_take_it():
    assert rankable("pass_td", "nfl")


def test_it_stays_quarantined_on_the_edge_board():
    """Ranking is not edge. Tier 3 is the touchdown quarantine and this
    change does not relax it."""
    from engine.quality import tier_min_edge
    assert MARKET_TIER["pass_td"] == 3 == MARKET_TIER["anytime_td"]
    # BY MARKET NAME. `tier_min_edge` takes the market, not the tier —
    # the first cut of this test passed it the integer 3, which fell
    # through `market_tier` to the default and asserted 0.03 against a
    # bar that is really 0.06. It would have "passed" a false claim the
    # day those two numbers happened to agree.
    assert tier_min_edge("pass_td") == tier_min_edge("anytime_td") >= 0.06, \
        "the quarantine the scorer board answers to must apply here too"


# --- both boards, and the one that is refused -------------------------------
def test_the_nfl_row_reaches_the_most_likely_board_and_not_only_the_table():
    """Ethan, 2026-09-10: "Make sure we show passing touchdown props on
    the most likely bets too for CFB and nfl."

    A `RANK_AUC` entry is PERMISSION, not arrival — this repo has shipped
    four features this week that were built and unreachable. So the check
    drives a real row through `likely.from_prop` and asserts a row comes
    out the other side carrying the published figure."""
    from engine.calibrate import is_reliable
    from engine.likely import from_prop
    row = {"player": "Josh Allen", "team": "BUF", "opponent": "NYJ",
           "position": "QB", "market": PASS_TD, "market_label": "Passing TDs",
           "side": "OVER", "line": 1.5, "odds": -125, "book": "DraftKings",
           "hit_prob": 0.62, "raw_prob": 0.62, "fair_prob": 0.55,
           "projection": 1.9, "edge": 0.02, "grade": "B", "tier": 3,
           "has_market": True,
           "all_lines": [{"book": "DraftKings", "line": 1.5,
                          "over_odds": -125, "under_odds": 105}],
           "logs": [{"week": w, "opponent": "X", "value": v, "home": True}
                    for w, v in zip(range(8, 0, -1), [2, 1, 3, 2, 1, 2, 2, 3])],
           "sport": "nfl"}
    census = {}
    got = from_prop(row, lambda m: is_reliable("nfl", m), sport="nfl",
                    census=census)
    assert got is not None, census
    assert got["market"] == PASS_TD
    assert got["rank_auc"] == RANK_AUC["pass_td"]

    # THE SAME ROW ON THE COLLEGE BOARD IS REFUSED, and by the gate that
    # is about the measurement rather than by an accident of the fixture.
    census = {}
    assert from_prop(dict(row, sport="cfb"),
                     lambda m: is_reliable("cfb", m), sport="cfb",
                     census=census) is None
    assert "no measured ranking for this market yet" in census


def test_the_college_refusal_is_a_measurement_and_says_so():
    """Ethan asked for CFB too. The answer is no, and a no has to carry
    its number or it is just a preference. Re-measured with a COLLEGE
    anchor on 2026-09-10: 0.5556 at 2+, 0.5422 at 3+, both under the
    floor, with the naive career rate matching them."""
    from engine.likely import rank_auc
    assert rank_auc("cfb", "pass_td") is None, \
        "college was given a figure without one being measured"
    src = open(os.path.join(ROOT, "engine", "passtd.py"),
               encoding="utf-8").read()
    for fact in ("0.5556", "0.5422", "1.862", "4,474"):
        assert fact in src, fact
    # AND THE FIRST EXPLANATION, WHICH WAS WRONG, IS GONE. It blamed the
    # college base rate; the cause is that the feed wrote no losing row.
    assert "almost no negatives to rank against" not in src


def test_the_college_feed_now_records_the_games_he_did_not_score():
    """The reason 1+ was unscoreable: `pass_td` held 4,474 college rows
    and not one of them was a zero. A ranking measurement needs
    negatives, and `anytime_td` — the one college market with a measured
    ranking — is the one market whose feed already wrote them."""
    from engine.sources.cfbstats import ALWAYS, MARKETS, ZERO_WHEN
    for market, opportunity in (("pass_td", "pass_att"),
                                ("rush_td", "carries"),
                                ("rec_td", "receptions")):
        assert ZERO_WHEN.get(market) == opportunity, market
        assert opportunity in MARKETS, opportunity
    assert "anytime_td" in ALWAYS, \
        "the market that proved the rule stopped writing its zeros"


def test_the_measurement_is_written_down_where_the_model_lives():
    """A number in a table with no provenance is a number nobody can
    check. The module note carries the sample, the split and both
    figures."""
    src = open(os.path.join(ROOT, "engine", "passtd.py"),
               encoding="utf-8").read()
    for fact in ("0.6870", "0.7149", "2021-2024", "held-out", "3,423"):
        assert fact in src or fact.upper() in src, fact


# --- the whole chain, on a fixture ------------------------------------------
def test_a_priced_quarterback_prop_is_poisson_under_the_haircut():
    """The whole chain, and the assertion is at the RAW level because the
    card's own number is not comparable to either distribution.

    `evaluate_prop` publishes the model shrunk toward the book's fair by
    the tier haircut — Tier 3 keeps 30% of the disagreement — so a raw
    0.715 comes out as 0.5645 against a 0.5 fair. My first cut compared
    `hit_prob` to the two distributions with an "unless they are close"
    escape hatch, and the fixture I picked triggered the hatch: the
    assertion could not fail. Inverting the published shrink recovers
    the number the model actually produced, and that one IS comparable.

    A LOW ARM AT 0.5 is chosen deliberately: it is where the two
    distributions disagree most (Poisson 0.285 against a normal tail's
    0.375), so a wrong branch cannot hide inside the tolerance.
    """
    from engine.betting import evaluate_prop
    from engine.projection import build_projection
    from engine.quality import tier_shrink
    from engine.statmath import prob_over

    vals = [0, 1, 0, 0, 1, 0, 0, 1]
    prop = Prop(player="Backup Arm", team="LA", opponent="SEA",
                position="QB", market=PASS_TD,
                logs=[GameLog(week=w, opponent="Y", value=v)
                      for w, v in zip(range(8, 0, -1), vals)],
                career_avg=sum(vals) / len(vals), vs_opponent_avg=None,
                lines=[SportsbookLine(book="DK", line=0.5,
                                      over_odds=-110, under_odds=-110)])
    game = Game(home="LA", away="SEA", weather=Weather(dome=True),
                spread=-3.5, total=47.5)
    proj = build_projection(prop, game, Team("SEA", "SEA",
                                             DefenseProfile("SEA")))
    rec = evaluate_prop(prop, proj, game=game, sport="nfl")
    assert rec.tier == 3, rec.tier
    assert rec.side == "UNDER", rec.side           # a 0.34 arm is not an over

    shrink = tier_shrink("pass_td")
    raw_side = rec.fair_prob + (rec.hit_prob - rec.fair_prob) / shrink
    poisson_side = 1.0 - passtd.at_least(proj.mean, 0.5)
    normal_side = 1.0 - prob_over(0.5, proj.mean, proj.std)
    assert abs(poisson_side - normal_side) > 0.05, \
        "the fixture no longer separates the two distributions"
    assert abs(raw_side - poisson_side) < 0.01, \
        f"the card priced {raw_side:.3f}; Poisson says {poisson_side:.3f}, " \
        f"a normal tail says {normal_side:.3f}"


def test_the_haircut_that_shrink_test_inverts_is_the_published_one():
    """The test above divides by `tier_shrink`. If that ever stopped
    being the transform `evaluate_prop` applies, the inversion would
    quietly recover the wrong number and still pass."""
    from engine.quality import tier_shrink
    src = open(os.path.join(ROOT, "engine", "betting.py"),
               encoding="utf-8").read()
    assert "tier_shrink" in src
    assert 0.0 < tier_shrink("pass_td") <= 1.0


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
