"""The likelihood board is a ranked page, so grade the top of it.

`TDBacktest.summary` grades probability BANDS. That is the right question
for a price — a +450 anytime-TD ticket is asking whether an 18% shot is
really 18% — and the wrong question for a page nobody reads by band.
People read the top of a ranked list.

The two populations do not have to agree, and they do not. Corrected
leave-one-season-out, the whole replay sits inside 1.4 points at every
band while the top five rows of a slate land 6.8 points ABOVE what they
claim, with a slate-bootstrapped interval of [+1.8%, +11.3%]. One-signed,
in the safe direction, and still wrong on exactly the rows a reader
trusts most. Ethan: "we need that page to be calibrated and elite."

REPORTED, NOT CORRECTED. There are only a few hundred replayed rows above
50% across five seasons. Fitting a flexible form on that is the failure
`calibrate.CURVE_Z` was just added to refuse; doing it here would be the
same mistake with the bar moved.

Run directly: `python3 tests/test_tdboard.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tdbacktest as TB                     # noqa: E402


class _Fit:
    """A fitted correction, without running a calibration search.

    INJECTED, BECAUSE THE SUITE MUST NOT READ THE BOX IT RUNS ON. Every
    other measurement in this file would otherwise depend on whether this
    machine happens to have a fitted store, which is how `test_nflready`
    and `test_likely` both passed standalone and failed in the sandbox.
    """

    def __init__(self, temperature=1.0, intercept=0.0):
        self.temperature = temperature
        self.intercept = intercept


def _neutral(_pairs):
    return _Fit()


def _slate(season, week, probs, scored):
    return [{"season": season, "week": week, "prob": p, "scored": s}
            for p, s in zip(probs, scored)]


def _rows(n_slates=8, per=6):
    """Slates where the model is honest: rank r scores with probability
    exactly what it claims, deterministically alternated so the realised
    rate matches the claim without needing a random draw."""
    out = []
    for w in range(n_slates):
        probs = [0.60, 0.50, 0.40, 0.30, 0.20, 0.10][:per]
        # Two in three of the 0.60 rows score, one in two of the 0.50s,
        # and so on — close enough to honest for the arithmetic tests.
        scored = [1 if (w % 5) < round(p * 5) else 0 for p in probs]
        out.extend(_slate(2024, w + 1, probs, scored))
    return out


# --- ranking ------------------------------------------------------------
def test_rank_is_within_the_slate_not_across_the_season():
    """A page is built one slate at a time. Ranking the whole season
    together would put every row of a high-total week above every row of
    a low-total one, which is not a board anybody sees."""
    rows = TB.board_rows(_rows(), fitter=_neutral)
    for week in range(1, 9):
        got = sorted((r for r in rows if r["week"] == week),
                     key=lambda r: r["rank"])
        assert [r["rank"] for r in got] == [1, 2, 3, 4, 5, 6]
        assert got[0]["cal"] >= got[-1]["cal"]


def _marked_seasons(seasons=(2023, 2024, 2025), per_season=1600):
    """Enough rows per season to clear MIN_FIT_PAIRS, each season carrying
    probabilities no other season uses — so a fit that saw its own season
    is visible in what it was handed."""
    rows = []
    for i, season in enumerate(seasons):
        base = 0.10 + 0.20 * i
        for w in range(per_season // 4):
            rows.extend(_slate(season, w + 1,
                               [base + 0.001 * j for j in range(4)],
                               [1, 0, 1, 0]))
    return rows


def test_the_correction_never_sees_the_season_it_grades():
    """Fitting on everything and reading the table off the same rows is
    how a correction looks perfect and generalises badly — the reading
    that let a curve chosen on noise sit in the store for two days."""
    seen = []

    def spy(pairs):
        seen.append({round(p, 4) for p, _ in pairs})
        return _Fit()

    rows = _marked_seasons()
    TB.board_rows(rows, fitter=spy)
    assert len(seen) == 3, len(seen)
    for season, handed in zip((2023, 2024, 2025), seen):
        own = {round(r["prob"], 4) for r in rows if r["season"] == season}
        assert not (own & handed), (season, sorted(own & handed)[:3])


def test_a_single_season_is_left_uncorrected_rather_than_fitted_on_itself():
    """With one season there is nothing left to train on once it is held
    out. The honest answer is the raw probability, not a correction
    fitted on the very rows it is about to grade."""
    called = []
    rows = _marked_seasons(seasons=(2024,))
    TB.board_rows(rows, fitter=lambda pairs: called.append(1) or _Fit())
    assert not called, "a lone season has no out-of-sample fit to make"
    assert all(r["cal"] == r["prob"] for r in rows)


def test_a_season_with_too_few_rows_behind_it_is_left_uncorrected_too():
    """Same rule, different cause: `MIN_FIT_PAIRS` rows have to exist
    OUTSIDE the season being graded, or the fit is thinner than the
    fitter's own floor and the raw number is the honest one."""
    rows = _marked_seasons(seasons=(2023, 2024), per_season=400)
    TB.board_rows(rows, fitter=_neutral)
    assert all(r["cal"] == r["prob"] for r in rows)


# --- the report ---------------------------------------------------------
def test_the_report_grades_depths_not_bands():
    got = TB.board_report(_rows(n_slates=12), depths=(3, 5),
                          fitter=_neutral)
    assert "top 3" in got and "top 5" in got
    assert "claimed" in got and "landed" in got


def test_a_depth_deeper_than_the_slate_is_skipped_not_faked():
    """A board of six rows cannot answer "how did the top twenty do".
    Padding it with whatever exists would answer a different question."""
    got = TB.board_report(_rows(n_slates=6, per=6), depths=(5, 20),
                          fitter=_neutral)
    assert "top 5" in got
    assert "top 20" not in got


def test_the_interval_is_bootstrapped_over_slates_not_rows():
    """Rows inside one slate share games, weather and game scripts and
    are nowhere near independent. Resampling rows would report an
    interval several times too tight and call noise a finding — which is
    the same error as the bare argmin two commits ago."""
    import inspect
    src = inspect.getsource(TB.board_report)
    assert "groups[rng.randrange(len(groups))] for _ in groups" in src
    assert "BOARD_RESAMPLES" in src


def test_a_real_gap_is_flagged_and_an_absent_one_is_not():
    """Both directions, on data built to have each."""
    honest = []
    for w in range(40):
        honest.extend(_slate(2024, w + 1, [0.5, 0.5, 0.5, 0.5],
                             [1, 0, 1, 0]))
    assert "<-- real" not in TB.board_report(honest, depths=(4,),
                                             fitter=_neutral)
    conservative = []
    for w in range(40):
        conservative.extend(_slate(2024, w + 1, [0.5, 0.5, 0.5, 0.5],
                                   [1, 1, 1, 0]))
    assert "<-- real" in TB.board_report(conservative, depths=(4,),
                                         fitter=_neutral)


def test_the_report_says_the_replay_is_not_a_published_record():
    """The number is flattering and the population is not the board's.
    A page quoting it without this sentence would be overstating what it
    has measured, which is the failure Ethan has caught twice."""
    got = TB.board_report(_rows(n_slates=12), depths=(5,), fitter=_neutral)
    assert "not a published record" in got
    assert "only shows priced ones" in got
    assert "neutral" in got


def test_the_report_says_the_page_shows_a_different_number_than_this():
    """THE TRAP THIS CLOSES, and it is the one that keeps recurring here:
    measuring one population and reading the answer as if it were about
    another. What is graded is the MODEL's probability. What the
    likelihood board displays for a touchdown is `hit_prob`, already
    shrunk halfway toward the book by `longshots.calibrated_prob` — its
    own source calls watch rows "pre-shrunk toward the market".

    If the market is roughly right at the top, that shrink closes part of
    the measured gap before a reader ever sees it. Quoting +6.8% as the
    page's miss without this sentence would be overstating a finding
    against a number the page does not show."""
    got = TB.board_report(_rows(n_slates=12), depths=(5,), fitter=_neutral)
    assert "shrunk toward the book" in got
    assert "before a reader sees it" in got
    assert "shrunk halfway toward the book" in TB.board_report.__doc__


def test_an_empty_replay_says_so_instead_of_dividing_by_nothing():
    assert TB.board_report([], fitter=_neutral) == "No slates to grade."


def test_the_docstring_states_why_the_gap_is_reported_not_corrected():
    """A measured miss with no fix attached invites the next person to
    fit one. The reason it is refused belongs next to the number."""
    assert "CURVE_Z" in TB.board_report.__doc__


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
