"""Ranking well is not the same as making money, and only one is measured.

Ethan, 2026-08-30: "why are we not putting money on the most likely and
long shots. i feel like we should expecially since we learned the ROI is
higher with the most likley bets."

We had not learned that. What was measured is RANKING — 0.72 AUC on who
scores, 0.69-0.77 on who clears a line — and CALIBRATION: the top five
rows of a slate land 60.2% against 53.4% claimed. Neither is profit.

The step that does not follow is the one in the middle. A board that
sorts the field perfectly still loses money paying -200 for a 60% shot,
because profit is decided by the PRICE and beating the price is the
0.468-AUC quantity that tests as noise. `board_report` gave the hit rate
with nothing to weigh it against, which is exactly how "it ranks well"
becomes "so it must pay".

So two things exist now. `tdbacktest.american_at` turns each depth's
landed rate into the price it breaks even at — computable with no odds
at all, and enough to frame the question. And `tdbook.board_priced` +
`roi_lines` join the board to the prices actually on the screen and
settle it, which needs `odds_history` and therefore the droplet.

Run directly: `python3 tests/test_board_roi.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import tdbook                                # noqa: E402
from engine.tdbacktest import american_at                # noqa: E402


def _slate(season, week, rows):
    return [{"season": season, "week": week, "cal": c, "rank": i + 1,
             "player": f"P{i}", "odds": o, "scored": s}
            for i, (c, o, s) in enumerate(rows)]


# --- the break-even price -------------------------------------------------
def test_break_even_matches_the_arithmetic_it_claims():
    """A coin flip breaks even at +100; 60% at -150; 25% at +300."""
    assert american_at(0.50) == "+100"
    assert american_at(0.60) == "-150"
    assert american_at(0.25) == "+300"
    assert american_at(0.75) == "-300"


def test_the_measured_top_of_the_board_breaks_even_at_minus_151():
    """The number that makes the decision concrete. The top five rows
    land 60.2%, which pays only if the screen is better than -151."""
    assert american_at(0.602) == "-151"


def test_it_survives_the_ends_rather_than_dividing_by_zero():
    for p in (0.0, 1.0, -1.0, 2.0):
        assert american_at(p)


def test_the_report_says_the_rate_alone_cannot_decide():
    """A hit rate printed with no price beside it is how ranking skill
    gets read as profit."""
    from engine import tdbacktest
    src = tdbacktest.board_report.__doc__ or ""
    import inspect
    body = inspect.getsource(tdbacktest.board_report)
    assert "BREAK EVEN AT" in body
    assert "worthless at -200 and free money at -110" in body
    assert "--roi" in body


# --- the ROI itself -------------------------------------------------------
def test_a_board_that_beats_its_price_reads_as_profitable():
    """Every row a 50% shot paid at +150 — a real edge, and the interval
    has to clear zero to say so."""
    rows = []
    for w in range(60):
        rows += _slate(2025, str(w + 1),
                       [(0.9, 150, 1), (0.8, 150, 0),
                        (0.7, 150, 1), (0.6, 150, 0)])
    got = "\n".join(tdbook.roi_lines(rows, depths=(4,)))
    assert "profitable" in got, got


def test_a_board_that_loses_to_its_price_says_so():
    """The same 50% hit rate at -200 is a losing board, and no amount of
    ranking skill changes that."""
    rows = []
    for w in range(60):
        rows += _slate(2025, str(w + 1),
                       [(0.9, -200, 1), (0.8, -200, 0),
                        (0.7, -200, 1), (0.6, -200, 0)])
    got = "\n".join(tdbook.roi_lines(rows, depths=(4,)))
    assert "losing" in got, got


def test_a_thin_board_declines_to_say():
    """An interval spanning zero is not a green light — the third answer
    this codebase keeps insisting on."""
    rows = []
    for w in range(6):
        rows += _slate(2025, str(w + 1), [(0.9, 100, 1), (0.8, 100, 0)])
    got = "\n".join(tdbook.roi_lines(rows, depths=(2,)))
    assert "inside the noise" in got, got
    assert "declining to say" in got


def test_it_ranks_within_the_slate_and_bootstraps_by_slate():
    """Rows in one slate share games and scripts. Resampling rows would
    report an interval several times too tight — the same discipline
    `board_report` already runs on."""
    import inspect
    src = inspect.getsource(tdbook.roi_lines)
    assert "sorted(g, key=lambda r: -r[\"cal\"])[:k]" in src
    assert "groups[rng.randrange(len(groups))] for _ in groups" in src


def test_the_price_taken_is_the_longest_on_the_screen():
    """What `odds.best_over_line` publishes. A numeric max is the right
    comparison across the whole American range, which is worth pinning
    because it looks like it needs a special case."""
    import inspect
    src = inspect.getsource(tdbook.board_priced)
    assert "max(int(o) for o in priced)" in src
    assert tdbook._decimal(100) == 2.0
    assert tdbook._decimal(-200) == 1.5
    assert tdbook._decimal(150) == 2.5


def test_an_empty_harvest_refuses_rather_than_reporting_zero():
    got = tdbook.roi_lines([])
    assert "no priced board rows" in " ".join(got)
    assert "odds_history" in " ".join(got)


def test_the_claim_is_priced_bet_by_bet_not_compressed_to_one_rate():
    """THE THIRD VERSION OF THIS COLUMN, and the first two were both
    wrong on live data.

    The first averaged AMERICAN odds, which are not a linear scale: the
    harvest printed "+396" beside a 48% hit rate and a -11.86% ROI.

    The second was `n / sum(decimal)` — the uniform win rate a flat
    portfolio breaks even at. Exact, and meaningless the moment prices
    differ: nine bets at -140 beside one at +2000 "break even at 27.5%"
    while the favourites each need 58.3% and the ticket needs 4.8%. It
    printed "needs 15.6%" against a 48% hit rate and a losing ROI, the
    same impossible triple in a subtler costume.

    A per-bet expectation cannot be dragged that way, because nothing is
    averaged across prices — each row is scored at its own."""
    rows = []
    for w in range(40):
        rows += [{"season": 2025, "week": str(w + 1), "cal": 0.5,
                  "rank": i + 1, "player": f"P{i}",
                  "odds": 2000 if i == 9 else -140,
                  "scored": 1 if i < 5 else 0} for i in range(10)]
    got = tdbook.roi_lines(rows, depths=(10,))
    cells = got[2].split()
    claimed = float(cells[4].rstrip("%")) / 100.0
    # Nine legs at -140 claim 0.5*0.714 - 0.5 = -0.143 each; the +2000 leg
    # claims 0.5*20 - 0.5 = +9.5. The mean is (9*-0.143 + 9.5)/10 = +0.821.
    assert abs(claimed - 0.821) < 0.01, claimed
    # And the retired scalar is gone from the output entirely.
    assert "needs" not in got[1]


def test_the_gap_is_realised_minus_claimed():
    """One column, and the only one that decides. A board claiming +5%
    and returning -5% is a ten-point gap however well it ranks."""
    rows = []
    for w in range(40):
        rows += _slate(2025, str(w + 1),
                       [(0.5, 100, 1), (0.5, 100, 0)])
    got = tdbook.roi_lines(rows, depths=(2,))
    cells = got[2].split()
    claimed = float(cells[4].rstrip("%")) / 100.0
    actual = float(cells[5].rstrip("%")) / 100.0
    gap = float(cells[6].rstrip("%")) / 100.0
    assert abs(claimed) < 1e-9, claimed        # 50% at +100 claims nothing
    assert abs(actual) < 1e-9, actual          # and returned nothing
    assert abs(gap - (actual - claimed)) < 1e-9


def test_a_board_the_price_already_knew_shows_the_gap():
    """The failure mode this whole report exists to catch: the model is
    right about who hits, the price is right too, and the vig is the
    difference."""
    rows = []
    for w in range(50):
        rows += _slate(2025, str(w + 1),
                       [(0.60, -140, 1), (0.60, -140, 1),
                        (0.60, -140, 0), (0.60, -140, 0)])
    got = tdbook.roi_lines(rows, depths=(4,))
    cells = got[2].split()
    claimed = float(cells[4].rstrip("%")) / 100.0
    actual = float(cells[5].rstrip("%")) / 100.0
    # Claims +2.9% at 60%/-140; delivers -14.3% on a 50% realised rate.
    assert claimed > 0 and actual < 0, (claimed, actual)


def test_one_depth_does_not_pretend_to_correct_for_a_family():
    got = "\n".join(tdbook.roi_lines(
        [r for w in range(20) for r in _slate(2025, str(w + 1),
                                              [(0.9, 100, 1), (0.8, 100, 0)])],
        depths=(2,)))
    assert "One depth asked" in got
    assert "1 depths" not in got and "1 chances" not in got


def test_the_deeper_the_board_the_more_bets_it_counts():
    rows = []
    for w in range(40):
        rows += _slate(2025, str(w + 1),
                       [(0.9 - i * 0.05, 120, i % 2) for i in range(10)])
    got = tdbook.roi_lines(rows, depths=(5, 10))
    n5 = int(got[2].split()[2])
    n10 = int(got[3].split()[2])
    assert n10 == 2 * n5 == 400, (n5, n10)


# --- asking seven depths is seven chances to be fooled --------------------
def test_the_shallow_end_is_priced_now():
    """Over 95 replayed slates the single most likely scorer landed
    67.4% against 60.0% claimed — a smaller, sharper board than the top
    five, and the place ranking is most likely to outrun the price.
    Nothing priced it until it was asked for."""
    assert tdbook.ROI_DEPTHS[:3] == (1, 2, 3)
    from engine.tdbacktest import BOARD_DEPTHS
    assert BOARD_DEPTHS == tdbook.ROI_DEPTHS, "the two reports must line up"


def test_the_verdict_is_judged_at_a_bar_raised_for_the_depth_count():
    """THE SAME CORRECTION AS `devigfit.BAND_Z` AND `calibrate.CURVE_Z`,
    applied to the one report that would put money on a board. A single
    "profitable" flag at a plain 95% across seven depths is close to a
    one-in-three coin flip."""
    import inspect
    src = inspect.getsource(tdbook.roi_lines)
    assert "ROI_FAMILY_ALPHA / max(1, len(depths))" in src
    assert tdbook.ROI_FAMILY_ALPHA == 0.05


def test_the_sibling_report_corrects_the_same_way():
    """`board_report` grew from four depths to seven at the same time.
    Correcting one and not the other is the inconsistency this codebase
    keeps finding in itself."""
    import inspect
    from engine import tdbacktest
    src = inspect.getsource(tdbacktest.board_report)
    assert "BOARD_FAMILY_ALPHA / max(1, len(depths))" in src
    assert tdbacktest.BOARD_FAMILY_ALPHA == tdbook.ROI_FAMILY_ALPHA


def test_the_bootstrap_is_deep_enough_for_the_corrected_tail():
    """At 0.05/7 two-sided the percentile sits three draws from the end
    of a 600-sample bootstrap. A bound decided by three numbers is not a
    bound."""
    from engine import tdbacktest
    for n in (tdbook.ROI_RESAMPLES, tdbacktest.BOARD_RESAMPLES):
        tail = 0.05 / len(tdbook.ROI_DEPTHS) / 2.0
        assert int(tail * n) >= 5, (n, int(tail * n))


def test_a_marginal_board_loses_its_flag_when_more_depths_are_asked():
    """The correction has to BITE, or it is decoration. The same rows
    judged at one depth and at seven give different words."""
    rows = []
    for w in range(40):
        rows += _slate(2025, str(w + 1),
                       [(0.9, 120, 1), (0.8, 120, 0),
                        (0.7, 120, 1), (0.6, 120, 0)])
    one = "\n".join(tdbook.roi_lines(rows, depths=(4,)))
    seven = "\n".join(tdbook.roi_lines(rows, depths=(1, 2, 3, 4, 5, 6, 7)))
    assert "profitable" in one, one
    # Same data, more questions — the four-deep line must be no more
    # confident than it was alone.
    four = [ln for ln in seven.splitlines() if ln.strip().startswith("top 4")]
    assert four, seven
    assert "inside the noise" in four[0] or "profitable" in four[0]


def test_the_footer_says_how_many_questions_were_asked():
    got = "\n".join(tdbook.roi_lines(
        [r for w in range(20) for r in _slate(2025, str(w + 1),
                                              [(0.9, 100, 1), (0.8, 100, 0)])],
        depths=(1, 2)))
    assert "2 depths" in got and "2 chances to be fooled" in got


# --- the harness has to measure the board the page publishes -------------
def test_the_harness_applies_the_pages_own_refusals():
    """THE FAILURE THAT TOOK FOUR RUNS TO SURFACE, and the one this file
    should have caught first.

    `tdbacktest.run` replays every player with prior form.
    `likely.build` — the actual page — refuses a row under MIN_PROB and
    any row disagreeing with the de-vigged market by more than
    MAX_CREDIBLE_EDGE, because a twenty-point gap in a heavily bet market
    is our error far more often than a discovery.

    The harness applied neither, so every ROI it reported was about a
    board the site never publishes. The tell was the claimed column:
    +72.24% at top 10, which backs out to a 48% model probability against
    a +259 price. That is a 21.7-point disagreement, and the page drops
    it before a reader sees it."""
    import inspect
    src = inspect.getsource(tdbook.board_priced)
    assert "MAX_CREDIBLE_EDGE" in src
    assert "MIN_PROB" in src
    assert "ONE_SIDED_HOLD" in src


def test_the_row_that_produced_the_impossible_claim_is_refused():
    """Named numbers, so the regression names itself."""
    from engine.betting import MAX_CREDIBLE_EDGE
    from engine.longshots import ONE_SIDED_HOLD
    from engine.odds import american_to_prob
    fair = american_to_prob(259) / ONE_SIDED_HOLD
    assert abs(0.48 - fair) > MAX_CREDIBLE_EDGE, fair


def test_a_credible_favourite_still_gets_through():
    """The filter must not empty the board — that would be the same
    failure in the other direction and would read as "no signal"."""
    from engine.betting import MAX_CREDIBLE_EDGE
    from engine.longshots import ONE_SIDED_HOLD
    from engine.odds import american_to_prob
    fair = american_to_prob(-140) / ONE_SIDED_HOLD
    assert abs(0.62 - fair) <= MAX_CREDIBLE_EDGE, fair


def test_the_funnel_is_published_rather_than_inferred():
    """A harness that quietly measures a different population than the
    page is exactly what happened here. The counts now travel with the
    report so the population is visible rather than assumed."""
    import inspect
    src = inspect.getsource(tdbook.board_priced)
    for key in ('"replayed"', '"priced"', '"thin"', '"incredible"'):
        assert key in src, key
    assert "funnel = dict(seen, kept=len(out))" in src
    cli = open(os.path.join(ROOT, "engine", "tdbook.py"),
               encoding="utf-8").read()
    assert "the board would show" in cli
    assert "disagreeing with the market" in cli


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
