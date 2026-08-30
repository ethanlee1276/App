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


def test_the_deeper_the_board_the_more_bets_it_counts():
    rows = []
    for w in range(40):
        rows += _slate(2025, str(w + 1),
                       [(0.9 - i * 0.05, 120, i % 2) for i in range(10)])
    got = tdbook.roi_lines(rows, depths=(5, 10))
    n5 = int(got[2].split()[2])
    n10 = int(got[3].split()[2])
    assert n10 == 2 * n5 == 400, (n5, n10)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
