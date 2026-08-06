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
from engine import ledger                                     # noqa: E402


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
    assert "settled bets to reach two sigma" in " ".join(out.split())


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


def test_loss_cause_is_never_a_slice():
    """It is only written on bets that LOST, so every bucket it makes is
    0-N by construction: -100% ROI at an enormous z, a tautology wearing
    the clothes of the strongest finding on the page. On a real journal it
    printed "loss cause · variance: 118 bets, -100.0%, z -12.37" above two
    findings that were actually true."""
    assert "loss cause" not in bleed.DIMENSIONS
    rows = ([bet("lost", loss_cause="variance") for _ in range(60)]
            + [bet("won") for _ in range(60)])
    out = _run(rows)
    assert "loss cause" not in out
    assert "-100.0%" not in out


def test_a_slice_that_is_the_whole_book_is_not_a_second_finding():
    """"sport · mlb" on a book that is 96% baseball convicts for exactly
    the reason the headline does, and reads as independent confirmation of
    itself."""
    rows = book(20, 130, sport="mlb")
    out = _run(rows)
    tail = out[out.index("WHAT THE RECORD WILL SUPPORT"):]
    assert "headline relabelled" in tail
    assert "survives a bar set" not in tail, \
        "a whole-book slice was reported as a finding"


# --- units vs win rate, which are different questions ------------------------
def test_a_significant_rate_with_a_quiet_units_test_is_not_read_as_fine():
    """The real journal's shape, and the one that must not be mishandled.

    Win rate is 3.2 sigma under what the prices require; the units test is
    only 1.4 because stakes vary and varying stakes add P&L variance that
    says nothing about pick quality. Reporting "NOT SIGNIFICANT" off the
    units test alone told a book whose picking IS provably below the bar
    that its record proved nothing.
    """
    import random
    rnd = random.Random(1)
    rows = []
    # 108-119 at short prices, sized the way Kelly sizes: mostly small with
    # a few large. Seeded, so the divergence is fixed rather than lucky.
    for i in range(227):
        rows.append(bet("won" if i < 108 else "lost", odds=-140,
                        stake=rnd.choice([0.05, 0.05, 0.05, 0.1, 0.1, 0.8])))
    s = bleed.measure(rows)
    assert s["z_rate"] < -2, s["z_rate"]
    assert abs(s["z"]) < abs(s["z_rate"]), "stake variance did not damp units"
    # Flattened: the copy wraps across print() calls, and a test that
    # breaks on rewrapping is a test of the line breaks.
    out = " ".join(_run(rows).split())
    assert "SIGNIFICANT ON WIN RATE" in out
    assert "one finding, not two contradictory ones" in out
    assert "Do not read that as the model being fine" in out
    assert "NOT SIGNIFICANT on either" not in out


def test_the_bets_needed_line_matches_the_test_it_describes():
    """It read "needs about 93 settled bets ... there are 227" directly
    under a NOT SIGNIFICANT verdict — the projection came from the win-rate
    gap while the verdict came from the units test, so the page contradicted
    itself in three lines."""
    # Only printed when NEITHER test is significant, so it can never again
    # sit under a verdict driven by the other one.
    out = _run(book(52, 48))
    if "NOT SIGNIFICANT on either" in out:
        i = out.index("needs about")
        n = int(out[i:].split()[2].replace(",", ""))
        assert n > 227, "a gap needing fewer bets than we have is significant"


def test_either_test_can_convict_and_the_label_says_which():
    rate_only = {"z": 0.5, "z_rate": -4.0}
    unit_only = {"z": -4.0, "z_rate": 0.5}
    both = {"z": -4.0, "z_rate": -4.0}
    neither = {"z": -1.0, "z_rate": -1.0}
    assert bleed._bar(rate_only, 3.0) == "CONVICTS (rate)"
    assert bleed._bar(unit_only, 3.0) == "CONVICTS (units)"
    assert bleed._bar(both, 3.0) == "CONVICTS"
    assert bleed._bar(neither, 3.0) == ""


def test_the_bar_accounts_for_running_two_tests_per_slice():
    """Correcting for the slices and not for the tests halves the bar."""
    rows = []
    for m in ("hits", "total_bases", "strikeouts", "outs"):
        rows += book(14, 14, market=m)
    out = _run(rows)
    cuts = bleed.slices(rows, bleed.MIN_N)
    assert f"|z| ≥ {bleed.sidak_z(2 * len(cuts)):.2f}" in out
    assert "×2 tests" in out


def test_the_two_z_scores_can_disagree_and_both_are_shown():
    """A book that wins its long prices and loses its short ones can sit
    under the required win RATE while making money. Reporting only the rate
    would call that book broken."""
    # Wins the +400s well above their 20% bar, loses the -400s below their
    # 80% bar. Profitable overall; well under the required win rate.
    rows = book(14, 26, odds=400) + book(28, 32, odds=-400)
    s = bleed.measure(rows)
    assert s["roi"] > 0, "fixture is not actually profitable"
    assert s["z_rate"] < -2 < s["z"], (s["z_rate"], s["z"])
    out = _run(rows)
    assert "z on units" in out and "z on win rate" in out


def test_the_units_test_uses_each_bet_s_own_price():
    """Under the null every bet is fairly priced, so profit has mean zero.
    A fairly-priced book must therefore score near zero, whatever its odds
    mix — if it does not, the variance term is wrong."""
    for odds in (-300, -110, 250):
        be = bleed.breakeven(odds)
        n = 4000
        wins = round(be * n)
        z = bleed.roi_z(book(wins, n - wins, odds=odds))
        assert abs(z) < 0.5, (odds, z)


def test_clv_ties_are_counted_apart_from_losses():
    """A line that never moved is not the market running us over. Folding
    ties into "did not beat" reported 16% on a book that was mostly flat."""
    rows = ([bet(close=1.5, line=1.5) for _ in range(60)]      # tied
            + [bet(close=2.0, line=1.5) for _ in range(20)]    # beat
            + [bet(close=1.0, line=1.5) for _ in range(20)])   # behind
    s = bleed.measure(rows)
    assert abs(s["clv_tied"] - 0.6) < 1e-9
    assert abs(s["clv_beat"] - 0.2) < 1e-9
    assert abs(s["clv_behind"] - 0.2) < 1e-9
    assert abs(s["clv_beat"] + s["clv_tied"] + s["clv_behind"] - 1.0) < 1e-9


def test_a_short_priced_book_is_told_its_breakeven_is_not_52_percent():
    """47.6% reads as unlucky against 52.4% and as a different problem
    entirely against 58%."""
    out = _run(book(108, 119, odds=-200))
    assert "Note the break-even" in out
    assert "not the 52.4%" in out


def test_an_empty_journal_says_so_instead_of_dividing_by_zero():
    assert bleed.report([]) == 0
    s = bleed.measure([])
    assert s["n"] == 0 and s["roi"] == 0.0 and s["z"] == 0.0


# --- which book are we even looking at ---------------------------------------
def test_the_default_scope_is_the_real_money_record():
    """'main' is the only bucket with real stakes and a real ROI. The paper
    buckets — pricedout, loose, longshot — are flat-stake observations, and
    pooling them into a P&L would report a number nobody wagered."""
    import inspect
    src = inspect.getsource(bleed.load)
    assert 'category="main"' in src


def test_category_all_pools_every_bucket_the_way_the_miner_does():
    """engine/losspatterns.records_from_ledger has NO category filter, so
    the miner and the hypothesis lab read every bucket pooled — on the real
    journal that is 3,134 rows against the 227 these tools default to. The
    lab can therefore confirm a pattern bleed never sees, and the two
    disagreeing is confusing rather than informative unless you can look at
    the same book it does."""
    import inspect
    from engine import losspatterns as lp
    assert "category" not in inspect.getsource(lp.records_from_ledger)

    conn = ledger.connect(":memory:")
    for i in range(60):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,status,category,stake_units,pnl_units) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01T10:00:00", "mlb", "2026-08-01", f"P{i}", "hits",
             "OVER", 1.5, "dk", -110, 0.6, "won" if i < 30 else "lost",
             "main" if i < 30 else "longshot", 1.0, 0.9 if i < 30 else -1.0))
    conn.commit()
    assert len(bleed.load(conn)) == 30
    assert len(bleed.load(conn, category="all")) == 60


def test_the_bucket_is_a_slice_so_the_pooling_can_be_tested():
    """The question the comparison exists for: do the paper buckets
    calibrate like the real one? The fitters pool them, so if they do not,
    a correction fitted on the pool fits neither population."""
    assert "bucket" in bleed.DIMENSIONS
    rows = ([bet("won", market="hits") | {"category": "main"} for _ in range(30)]
            + [bet("lost", market="hits") | {"category": "longshot"}
               for _ in range(30)])
    cuts = bleed.slices(rows, min_n=25)
    buckets = {b for d, b, _ in cuts if d == "bucket"}
    assert buckets == {"main", "longshot"}, buckets


def test_the_slice_bands_are_the_miner_s_own():
    """One vocabulary, so a number seen here can be tested there.

    This file used to band the circumstance dimensions itself, and the
    bands did not match: "rested" was under 2 weighted relief innings where
    the miner's "pen fresh" is under 3. That is not cosmetic. A finding
    read off this report gets registered in the hypothesis lab, which
    speaks the miner's vocabulary — and a slice named here that does not
    exist there produces a hypothesis matching nothing, collecting at 0/40
    forever while looking like missing data rather than a mistranslation.
    """
    from engine import losspatterns as lp
    for value, dim in ((4.0, "pen own"), (4.0, "pen opp")):
        assert bleed.DIMENSIONS[dim]({dim.replace(" ", "_"): value}) == \
            lp.pen_band(value)
    assert bleed.DIMENSIONS["claimed p"]({"hit_prob": 0.65}) == lp.prob_band(0.65)
    assert bleed.DIMENSIONS["capture lag"]({"lead_min": 30}) == lp.lead_band(30)
    assert bleed.DIMENSIONS["rest"]({"rest_days": 1}) == lp.rest_band(1)
    # And no dimension may invent a band the miner has never seen.
    banders = {"claimed p": lp.prob_band, "capture lag": lp.lead_band,
               "rest": lp.rest_band, "clock": lp.clock_band,
               "pen own": lp.pen_band, "pen opp": lp.pen_band,
               "horizon": lp.horizon_band}
    for name in banders:
        assert name in bleed.DIMENSIONS, name


def test_every_journaled_dimension_the_lab_can_test_is_sliceable_here():
    """If the lab can register a hypothesis on a dimension, this report has
    to be able to show it — otherwise the tool that FINDS things and the
    tool that TESTS them disagree about what exists."""
    from engine.hypotheses import DIMS
    covered = {"side", "odds", "prob", "horizon", "book", "lead", "park",
               "wind", "slot", "rest", "clock", "pen_opp", "pen_own"}
    assert set(DIMS) == covered, "DIMS moved; recheck bleed's coverage"
    here = set(bleed.DIMENSIONS)
    for want in ("side", "book", "price", "claimed p", "horizon", "capture lag",
                 "park", "wind", "lineup", "rest", "clock", "pen own",
                 "pen opp"):
        assert want in here, want


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
