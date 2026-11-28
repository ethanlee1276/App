"""Tests for the backtest/calibration math (pure, no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backtest import (
    SettledProp, evaluate, settle_recommendations, _norm,
    _grade_calibration, GRADE_MIN_N, OVERCONFIDENT,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def _sp(hit_prob, actual, line=50.0, proj=55.0, odds=-110, rec=False, stake=1.0, close=None):
    return SettledProp("P", "rec_yds", line, odds, hit_prob, proj, actual,
                       recommended=rec, stake_units=stake, closing_line=close)


def test_outcome_over_under_push():
    assert _sp(0.5, 60, line=50).outcome == 1   # over hit
    assert _sp(0.5, 40, line=50).outcome == 0   # missed
    assert _sp(0.5, 50, line=50).outcome is None  # push


def test_projection_error():
    settled = [_sp(0.5, 50, proj=55), _sp(0.5, 60, proj=55)]  # errors +5, -5
    r = evaluate(settled)
    assert approx(r.mae, 5.0) and approx(r.rmse, 5.0)


def test_brier_perfect_vs_worst():
    perfect = [_sp(1.0, 60, line=50), _sp(0.0, 40, line=50)]   # confident & right
    worst = [_sp(0.0, 60, line=50), _sp(1.0, 40, line=50)]     # confident & wrong
    assert approx(evaluate(perfect).brier, 0.0)
    assert approx(evaluate(worst).brier, 1.0)


def test_calibration_well_calibrated():
    # 10 props predicted at 0.7; exactly 7 hit -> bin is perfectly calibrated.
    settled = [_sp(0.7, 60, line=50) for _ in range(7)] + \
              [_sp(0.7, 40, line=50) for _ in range(3)]
    r = evaluate(settled, n_bins=5)
    bin70 = next(b for b in r.bins if b.lo <= 0.7 < b.hi)
    assert bin70.n == 10 and approx(bin70.mean_pred, 0.7) and approx(bin70.hit_rate, 0.7)
    assert approx(r.ece, 0.0)


def test_calibration_miscalibrated_has_error():
    # Predicts 0.9 but only half hit -> large calibration error.
    settled = [_sp(0.9, 60, line=50) for _ in range(5)] + \
              [_sp(0.9, 40, line=50) for _ in range(5)]
    r = evaluate(settled)
    assert r.ece > 0.35


def test_betting_roi_and_winrate():
    # 3 recommended bets at +100 (decimal 2.0): 2 win, 1 loss, flat 1u.
    settled = [
        _sp(0.6, 60, line=50, odds=100, rec=True),  # win +1
        _sp(0.6, 70, line=50, odds=100, rec=True),  # win +1
        _sp(0.6, 40, line=50, odds=100, rec=True),  # loss -1
        _sp(0.6, 60, line=50, odds=100, rec=False), # not a bet
    ]
    r = evaluate(settled)
    assert r.n_bets == 3 and r.wins == 2
    assert approx(r.win_rate, 2/3)
    assert approx(r.net_units, 1.0)          # +1 +1 -1
    assert approx(r.roi, 1.0/3.0)            # net 1 / staked 3


def test_push_excluded_from_bets():
    settled = [_sp(0.6, 50, line=50, odds=-110, rec=True)]  # push
    r = evaluate(settled)
    assert r.n_bets == 1 and r.pushes == 1 and r.units_staked == 0.0


def test_clv_average():
    settled = [
        _sp(0.6, 60, line=48, odds=-110, rec=True, close=50),  # +2 CLV
        _sp(0.6, 40, line=49, odds=-110, rec=True, close=50),  # +1 CLV
    ]
    r = evaluate(settled)
    assert approx(r.avg_clv, 1.5)


# --- does conviction mean anything ------------------------------------------
# The reading that survives having no harvested book lines. On a database
# without them every bet is priced against the naive baseline, the
# market-relative segment is empty, and the grade ladder goes completely
# unexamined — which is the state this machine was in when it was asked
# whether it was ready to fire on elite picks. Run against four ingested
# NFL seasons it answered: A landed 49.6% against a claimed 54.2% while
# B+ landed 56.5%, in every season.

def _graded(grade, n, wins, claimed):
    """n settled recommendations in one band, `wins` of which landed."""
    out = []
    for k in range(n):
        won = k < wins
        out.append(SettledProp("P", "rec_yds", 50.0, -110, claimed, 55.0,
                               60.0 if won else 40.0, recommended=True,
                               grade=grade))
    return out


def test_grade_calibration_separates_claimed_from_landed():
    rows = _graded("A", 100, 50, 0.60)
    g = _grade_calibration(rows)["A"]
    assert g["n"] == 100
    assert approx(g["claimed"], 0.60, 1e-4)
    assert approx(g["landed"], 0.50, 1e-4)
    assert approx(g["gap"], -0.10, 1e-4)


def test_a_push_is_not_counted_as_half_a_forecast():
    """A push is not a wrong forecast, and averaging it in drags every
    band toward 50%."""
    rows = _graded("A", 10, 10, 0.60)
    rows += [SettledProp("P", "rec_yds", 50.0, -110, 0.60, 55.0, 50.0,
                         recommended=True, grade="A")]      # push
    g = _grade_calibration(rows)["A"]
    assert g["n"] == 10 and approx(g["landed"], 1.0, 1e-9)


def test_only_recommendations_are_graded():
    """A prop the board never recommended says nothing about the band it
    would have been in."""
    rows = _graded("A", 5, 5, 0.6)
    rows.append(SettledProp("P", "rec_yds", 50.0, -110, 0.6, 55.0, 40.0,
                            recommended=False, grade="A"))
    assert _grade_calibration([r for r in rows if r.recommended])["A"]["n"] == 5


def test_an_ungraded_row_lands_in_its_own_bucket():
    rows = [SettledProp("P", "rec_yds", 50.0, -110, 0.6, 55.0, 60.0,
                        recommended=True)]
    assert "ungraded" in _grade_calibration(rows)


def test_the_report_flags_an_overconfident_band():
    r = evaluate(_graded("A", 60, 24, 0.60) + _graded("B+", 60, 36, 0.52))
    text = r.summary()
    assert "Conviction" in text
    assert "overconfident" in text


def test_the_report_flags_a_ladder_that_does_not_separate():
    """The finding itself: a top band that lands no more often than the
    bottom one is a ranking, not a conviction."""
    r = evaluate(_graded("A", 60, 30, 0.55) + _graded("B+", 60, 42, 0.54))
    assert "ranking" in r.summary()


def test_a_ladder_that_separates_draws_no_complaint():
    r = evaluate(_graded("A", 60, 42, 0.66) + _graded("B+", 60, 30, 0.50))
    text = r.summary()
    assert "ranking" not in text
    assert "overconfident" not in text


def test_a_thin_band_is_not_reported_at_all():
    """Under the floor, "claimed 68% landed 50%" is two coin flips."""
    r = evaluate(_graded("A", GRADE_MIN_N - 1, 2, 0.60))
    assert "Conviction" not in r.summary()


def test_the_overconfidence_bar_is_wider_than_ordinary_noise():
    import math
    se = math.sqrt(0.25 / GRADE_MIN_N)
    assert OVERCONFIDENT < se, "the bar would fire on sampling noise"


def test_settle_recommendations_matches_by_name_market():
    recs = [
        {"player": "Amon-Ra St. Brown", "market": "rec_yds", "line": 79.5, "odds": -110,
         "hit_prob": 0.58, "projection": 88.0, "recommended": True, "stake_units": 0.7},
        {"player": "Nobody", "market": "rush_yds", "line": 40.5, "odds": -110,
         "hit_prob": 0.5, "projection": 42.0, "recommended": False, "stake_units": 0.0},
    ]
    actuals = {(_norm("Amon-Ra St. Brown"), "rec_yds"): 101.0}
    settled = settle_recommendations(recs, actuals)
    assert len(settled) == 1 and settled[0].actual == 101.0 and settled[0].outcome == 1


def test_backtest_driver_walk_forward():
    # Stub the data layer so the walk-forward loop can be exercised offline.
    import engine.sources.nflverse as nv
    import engine.pipeline as pl
    from engine import backtest as bt

    stats = [{"week": "5", "player_display_name": "RB One", "rushing_yards": "80",
              "passing_yards": "0", "receiving_yards": "0", "receptions": "0"}]
    saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
    nv.load_weekly_stats = lambda season: stats
    nv.build_slate = lambda season, w, upto_week=None: object()
    # **kw, so adding a pipeline argument does not break the double. This
    # stub pinned run_slate's exact signature and failed the moment Phase 2
    # threaded team_context through — a test asserting on a call shape it
    # does not care about.
    pl.run_slate = lambda slate, config=None, **kw: {"recommendations": [{
        "player": "RB One", "market": "rush_yds", "line": 70.0, "odds": -110,
        "hit_prob": 0.6, "projection": 82.0, "recommended": True, "stake_units": 1.0,
    }]}
    try:
        r = bt.backtest_from_stats(2024, [5])
        # actual 80 > line 70 -> the recommended bet wins.
        assert r.n == 1 and r.n_bets == 1 and r.wins == 1
    finally:
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = saved


def test_under_bets_are_graded_on_the_side_actually_bet():
    """``hit_prob`` is the probability the CHOSEN side wins, so scoring it
    against "did the over hit" grades every UNDER backwards — in the calibration
    bins and in the P&L. Real backtests hid this until calibration made the
    model start taking unders in volume."""
    from engine.backtest import SettledProp, evaluate

    # Player recorded 0 against a 1.5 line: the under won outright.
    under = SettledProp(player="X", market="total_bases", line=1.5, odds=-110,
                        hit_prob=0.70, projection=0.9, actual=0.0,
                        recommended=True, stake_units=1.0, side="UNDER")
    assert under.over_hit == 0          # the over lost...
    assert under.outcome == 1           # ...so our bet won

    over = SettledProp(player="Y", market="total_bases", line=1.5, odds=-110,
                       hit_prob=0.70, projection=2.1, actual=0.0,
                       recommended=True, stake_units=1.0, side="OVER")
    assert over.outcome == 0

    r = evaluate([under, over])
    assert r.wins == 1                  # exactly one of the two won

    # A push is a push whichever side was taken.
    push = SettledProp(player="Z", market="hits", line=1.0, odds=-110,
                       hit_prob=0.6, projection=1.0, actual=1.0,
                       recommended=True, side="UNDER")
    assert push.outcome is None


def test_closing_line_value_flips_sign_for_unders():
    """On an over you want the line to rise afterwards; on an under you want it
    to fall. One shared sign convention scores unders backwards."""
    from engine.backtest import SettledProp, evaluate

    over = SettledProp(player="A", market="rec_yds", line=50.0, odds=-110,
                       hit_prob=0.6, projection=60.0, actual=61.0,
                       recommended=True, closing_line=53.0, side="OVER")
    under = SettledProp(player="B", market="rec_yds", line=50.0, odds=-110,
                        hit_prob=0.6, projection=40.0, actual=39.0,
                        recommended=True, closing_line=47.0, side="UNDER")
    # Both beat the close by 3 points in their own direction.
    assert evaluate([over]).avg_clv == 3.0
    assert evaluate([under]).avg_clv == 3.0


def test_pnl_is_segmented_by_pricing_basis():
    """Only book-priced props say anything about beating the market, so their
    P&L must be reported separately instead of blended into the baseline
    majority — a 9% real-line subset is invisible inside an overall ROI."""
    from engine.backtest import SettledProp, evaluate

    def sp(basis, won):
        return SettledProp(player="P", market="rec_yds", line=50.0, odds=-110,
                           hit_prob=0.6, projection=55.0,
                           actual=60.0 if won else 40.0,
                           recommended=True, stake_units=1.0, basis=basis)

    r = evaluate([sp("book", True), sp("book", False),
                  sp("naive", True), sp("naive", True), sp("naive", False)])
    assert r.segments["book"]["n_bets"] == 2
    assert r.segments["book"]["wins"] == 1
    assert r.segments["naive"]["n_bets"] == 3
    assert "vs REAL book lines" in r.summary()


def test_book_segment_splits_by_side():
    """An OVER edge and an UNDER leak can cancel to a flat blended ROI, so the
    market-relative segment breaks out each side's record."""
    from engine.backtest import SettledProp, evaluate

    def sp(side, won):
        # actual relative to the line encodes the raw over result; `outcome`
        # flips it for unders, so build each case from the bet's own view.
        over_hit = won if side == "OVER" else not won
        return SettledProp(player="P", market="total_bases", line=1.5,
                           odds=-110, hit_prob=0.6, projection=1.8,
                           actual=2.0 if over_hit else 1.0,
                           recommended=True, stake_units=1.0,
                           side=side, basis="book")

    r = evaluate([sp("OVER", True), sp("OVER", True), sp("OVER", False),
                  sp("UNDER", False), sp("UNDER", False)])
    sides = r.segments["book"]["sides"]
    assert sides["OVER"]["n_bets"] == 3 and sides["OVER"]["wins"] == 2
    assert sides["UNDER"]["n_bets"] == 2 and sides["UNDER"]["wins"] == 0
    assert sides["OVER"]["roi"] > 0 > sides["UNDER"]["roi"]
    # Both sides present -> the summary shows the split.
    text = r.summary()
    assert "OVER " in text and "UNDER" in text


def test_book_segment_splits_by_grade():
    """If Strong picks don't beat Lean picks, the model's conviction carries
    no signal and tightening thresholds is pointless — the grade split makes
    that testable in the product's own vocabulary."""
    from engine.backtest import SettledProp, evaluate

    def sp(grade, won):
        return SettledProp(player="P", market="total_bases", line=1.5,
                           odds=-110, hit_prob=0.58, projection=1.8,
                           actual=2.0 if won else 1.0,
                           recommended=True, stake_units=1.0,
                           side="OVER", basis="book", grade=grade)

    r = evaluate([sp("Strong", True), sp("Strong", True),
                  sp("Play", True), sp("Play", False),
                  sp("Lean", False)])
    grades = r.segments["book"]["grades"]
    assert grades["Strong"]["n_bets"] == 2 and grades["Strong"]["wins"] == 2
    assert grades["Play"]["n_bets"] == 2 and grades["Play"]["wins"] == 1
    assert grades["Lean"]["n_bets"] == 1 and grades["Lean"]["wins"] == 0
    assert grades["Strong"]["roi"] > grades["Play"]["roi"] > grades["Lean"]["roi"]
    # Strong is printed before Play before Lean in the summary.
    text = r.summary()
    assert 0 < text.find("Strong") < text.find("Play ") < text.find("Lean")


def test_initialled_names_join_to_the_way_a_book_spells_them():
    """2026-08-30. Stripping the dots turned "A.J. Brown" into "a j
    brown" while a book writing "AJ Brown" gave "aj brown" — two
    different people, in the key SIX join sites share. Every initialled
    receiver and tight end could silently miss its price, and a failed
    join here does not look like a bug: it looks like no line was ever
    harvested for him.

    Found while joining the yardage mixture to real closes, which is the
    first thing that ever asked this key to match a book's spelling of a
    name with initials in it."""
    from engine.backtest import _norm
    for dotted, plain in (("A.J. Brown", "AJ Brown"),
                          ("D.K. Metcalf", "DK Metcalf"),
                          ("T.J. Hockenson", "TJ Hockenson"),
                          ("C.J. Stroud", "CJ Stroud")):
        assert _norm(dotted) == _norm(plain), (dotted, plain)
    # And it must not have eaten anything it should have kept.
    assert _norm("Marvin Harrison Jr.") == "marvin harrison"
    assert _norm("Ja'Marr Chase") == "jamarr chase"
    assert _norm("Amon-Ra St. Brown") == "amon ra st brown"
    assert _norm("Kenneth Walker III") == "kenneth walker"


def test_gluing_initials_only_ever_adds_matches():
    """The reason this was safe to change under six existing join sites:
    two spellings that already agreed still agree, so measurements move
    by gaining rows, never by losing them."""
    from engine.backtest import _norm
    for name in ("Christian McCaffrey", "Josh Jacobs", "Puka Nacua",
                 "De'Von Achane", "Bijan Robinson"):
        once = _norm(name)
        assert _norm(once) == once, name       # idempotent
        assert once == " ".join(once.split())


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
