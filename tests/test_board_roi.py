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


def test_the_price_summary_is_a_break_even_rate_not_an_average_of_odds():
    """THE COLUMN THIS REPLACED WAS ARITHMETIC NONSENSE, and the live run
    proved it: "+396" printed beside a 48% hit rate and an ROI of
    -11.86%, three numbers that cannot all be true. Backing the price out
    of the ROI gave -120. American odds are not a linear scale and a
    handful of long losers had dragged a mean that described nothing.

    A flat-stake portfolio breaks even at n / sum(decimal odds). That is
    exact, it is the number the hit rate has to beat, and one outlier
    cannot move it far."""
    rows = []
    for w in range(40):
        slate = [{"season": 2025, "week": str(w + 1), "cal": 0.9 - i * 0.1,
                  "rank": i + 1, "player": f"P{i}",
                  # One +2000 lottery ticket among four -110 favourites.
                  "odds": 2000 if i == 4 else -110, "scored": 1 if i < 2 else 0}
                 for i in range(5)]
        rows += slate
    got = tdbook.roi_lines(rows, depths=(5,))
    cells = got[2].split()
    need = float(cells[4].rstrip("%")) / 100.0
    # Four at -110 (decimal 1.909) and one at +2000 (21.0) sum to 28.64,
    # so the portfolio breaks even at 5/28.64 = 17.5%. An AVERAGE of the
    # American values would have read about +378.
    assert 0.16 < need < 0.19, need
    assert "+378" not in got[2] and "396" not in got[2]


def test_short_is_the_column_that_decides():
    """Hit minus needs. Negative at every depth means the board does not
    clear its own prices, however well it ranks."""
    rows = []
    for w in range(30):
        rows += _slate(2025, str(w + 1),
                       [(0.9, -200, 1), (0.8, -200, 1),
                        (0.7, -200, 0), (0.6, -200, 0)])
    got = "\n".join(tdbook.roi_lines(rows, depths=(4,)))
    # 50% hit against -200, which needs 66.7%.
    assert "50.0%" in got and "66.7%" in got
    assert "-16.7%" in got, got
    assert "rank the field perfectly and you still lose" in got


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
