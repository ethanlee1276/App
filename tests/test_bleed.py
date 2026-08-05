"""bleed: read a losing record without inventing a reason for it.

The failure mode this guards is not a wrong number, it is a confident one.
Sort a coin-flip journal fifteen ways and some cut lands two sigma out —
that is what two sigma MEANS at fifteen tries — and the reflex is to turn
that market off. So the tests here are mostly about refusal: that the bar
rises with the number of looks, that small slices never convict, that a
headline inside the noise says so, and that break-even is read off the
prices actually taken rather than assumed to be -110.

Fixtures are constructed with known properties, so a test that passes is a
measurement rather than a re-run of whatever is in the journal today.

Run directly: `python3 tests/test_bleed.py`
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bleed                                                  # noqa: E402


def bet(status="won", odds=-110, stake=1.0, market="hits", book="FanDuel",
        side="OVER", line=1.5, close=None, sport="mlb", **kw):
    pnl = (stake * (odds / 100.0 if odds > 0 else 100.0 / -odds)
           if status == "won" else -stake)
    d = {"sport": sport, "date": "2026-07-01", "player": "P",
         "market": market, "side": side, "line": line, "book": book,
         "odds": odds, "grade": "B", "status": status, "pnl_units": pnl,
         "stake_units": stake, "hit_prob": 0.55, "closing_line": close,
         "loss_cause": None, "lineup_slot": None, "park_hr": None,
         "wind_out": None, "roofed": None, "lead_min": None,
         "rest_days": None, "body_clock": None, "pen_own": None,
         "pen_opp": None}
    d.update(kw)
    return d


def book(wins, losses, **kw):
    return ([bet("won", **kw) for _ in range(wins)]
            + [bet("lost", **kw) for _ in range(losses)])


# --- the correction that stops the fishing -----------------------------------
def test_the_bar_rises_with_the_number_of_looks():
    """One look is 1.96. Sixty looks at the same family-wise rate is ~3."""
    assert abs(bleed.sidak_z(1) - 1.96) < 0.01
    # 1 - 0.95^(1/60) ≈ 0.000855 per look, whose two-sided z is ≈ 3.33.
    b60 = bleed.sidak_z(60)
    assert 3.25 < b60 < 3.40, b60
    # Monotone, so adding a dimension can never make convicting EASIER.
    bars = [bleed.sidak_z(n) for n in (1, 5, 20, 60, 200)]
    assert bars == sorted(bars)


def test_the_bar_actually_holds_the_family_wise_rate():
    """The point of the number, checked rather than asserted: the chance of
    at least one false positive across n independent looks stays at alpha."""
    for n in (10, 60):
        z = bleed.sidak_z(n, 0.05)
        per_look = 2 * (1 - bleed._phi(z))
        assert abs((1 - (1 - per_look) ** n) - 0.05) < 1e-6


def test_slices_below_the_floor_are_never_tested_at_all():
    """A 100% ROI on eight bets must not appear as a finding, and must not
    inflate the bar for the slices that are real either."""
    rows = book(4, 4) + book(30, 30, market="total_bases")
    cuts = bleed.slices(rows, min_n=25)
    markets = {b for d, b, _ in cuts if d == "market"}
    assert markets == {"total_bases"}, markets


# --- break-even read from the prices, not assumed -----------------------------
def test_breakeven_follows_the_price_actually_taken():
    assert abs(bleed.breakeven(-110) - 0.5238) < 0.001
    assert abs(bleed.breakeven(+150) - 0.40) < 0.001
    assert abs(bleed.breakeven(-200) - 0.6667) < 0.001


def test_a_plus_money_slice_is_judged_against_its_own_bar():
    """Flat -110 would call a 45% win rate on +150 dogs a disaster. It is a
    5-point EDGE, and the z has to say so."""
    s = bleed.measure(book(45, 55, odds=150))
    assert abs(s["breakeven"] - 0.40) < 0.001
    assert s["z"] > 0, "a profitable dog book was scored as losing"
    assert s["roi"] > 0


def test_a_favourite_book_at_the_same_win_rate_is_judged_losing():
    s = bleed.measure(book(55, 45, odds=-200))
    assert s["win_rate"] == 0.55
    assert s["z"] < 0, "55% on -200 favourites is well under break-even"


# --- the headline ------------------------------------------------------------
def test_a_record_inside_the_noise_reports_itself_as_such(capsys=None):
    """Ethan's actual shape: 105-111 at -110 is z ≈ -1.1 and means nothing."""
    s = bleed.measure(book(105, 111))
    assert abs(s["z"]) < 2
    assert -1.5 < s["z"] < -0.7, s["z"]


def test_a_genuinely_broken_book_does_clear_two_sigma():
    """The positive control — otherwise "not significant" is just a function
    that always says no."""
    s = bleed.measure(book(300, 700))
    assert s["z"] < -2


# --- CLV ---------------------------------------------------------------------
def test_clv_is_side_aware():
    assert bleed.clv_of(bet(side="OVER", line=1.5, close=2.0)) == 0.5
    assert bleed.clv_of(bet(side="UNDER", line=1.5, close=2.0)) == -0.5
    assert bleed.clv_of(bet(side="UNDER", line=2.0, close=1.5)) == 0.5
    assert bleed.clv_of(bet(close=None)) is None


def test_clv_coverage_is_reported_not_assumed():
    """Averaging CLV over the bets that HAVE a close, while reporting how
    many that is — a mean over 42% of the book is not a book-wide number
    and must not read as one."""
    rows = book(5, 5, close=2.0) + book(5, 5)
    s = bleed.measure(rows)
    assert s["clv_n"] == 10 and s["n"] == 20
    assert s["clv"] is not None


def test_a_book_with_no_closes_reports_none_rather_than_zero():
    """Zero CLV means "we took the closing number". No data means we cannot
    say. Collapsing them would turn silence into a finding."""
    s = bleed.measure(book(10, 10))
    assert s["clv"] is None and s["clv_n"] == 0


# --- the report --------------------------------------------------------------
def _run(rows, **kw):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bleed.report(rows, **kw)
    return buf.getvalue()


def test_the_report_leads_with_significance_before_any_slice():
    out = _run(book(105, 111))
    assert out.index("NOT SIGNIFICANT") < out.index("SLICES")
    assert "settled bets to clear two sigma" in out


def test_the_report_refuses_to_convict_a_coin_flip_sliced_many_ways():
    """The whole point. A journal with no real structure must produce no
    findings, however many ways it is cut."""
    rows = []
    for i, m in enumerate(("hits", "total_bases", "strikeouts", "outs")):
        for bk in ("FanDuel", "DraftKings", "BetMGM"):
            rows += book(14, 14, market=m, book=bk)
    out = _run(rows)
    assert "Nothing. No slice clears" in out
    assert "fitting" in out


def test_a_real_structural_break_survives_the_corrected_bar():
    """The positive control for the slicing half: one market genuinely
    broken, buried among healthy ones, still has to come out."""
    rows = []
    for m in ("hits", "total_bases", "strikeouts"):
        rows += book(60, 55, market=m)
    rows += book(20, 130, market="home_runs")
    out = _run(rows)
    assert "WHAT THE RECORD WILL SUPPORT" in out
    tail = out[out.index("WHAT THE RECORD WILL SUPPORT"):]
    assert "home_runs" in tail, tail
    assert "Nothing." not in tail


def test_an_empty_journal_says_so_instead_of_dividing_by_zero():
    assert bleed.report([]) == 0
    s = bleed.measure([])
    assert s["n"] == 0 and s["roi"] == 0.0 and s["z"] == 0.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
