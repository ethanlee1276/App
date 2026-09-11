"""The shape tool has to be able to say "one parameter is enough".

A diagnostic that only ever finds something is not a diagnostic. These
tests are built around that: a book whose error IS a pure bias must come
back with the slope refused, and a book whose error genuinely grows with
confidence must come back with it adopted — and the second test is only
meaningful because the first one exists.

The books are DETERMINISTIC. Wins are assigned by count inside each
claim band rather than drawn at random, so the fits are exact and a
verdict cannot flicker between runs. A statistical tool with a flaky test
teaches you to ignore its failures.
"""

import io
import os
import sqlite3
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shapecheck as sc
from engine import selectionfit as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "shapecheck.py"), encoding="utf-8").read()


def _book(spec, reps=40):
    """(claim, outcome) pairs, chronologically interleaved.

    ``spec`` is [(claimed, true_rate)]. Each rep lays down one bet per
    claim level, so every walk-forward block sees the full spread of
    confidences — a block containing only 52% bets could not speak to a
    slope either way.
    """
    pairs = []
    tally = {c: 0.0 for c, _ in spec}
    for _ in range(reps):
        for c, true in spec:
            tally[c] += true
            if tally[c] >= 1.0:
                tally[c] -= 1.0
                pairs.append((c, 1))
            else:
                pairs.append((c, 0))
    return pairs


def _run(pairs, name="test book"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        sc.report(pairs, name)
    return buf.getvalue()


# --- the negative case, which is the one that makes the tool useful ---------
def test_a_pure_bias_book_refuses_the_slope():
    """Every claim is 8 points high, at every confidence. The correct
    answer is the one the live haircut already implements."""
    spec = [(0.52, 0.44), (0.58, 0.50), (0.64, 0.56), (0.70, 0.62)]
    out = _run(_book(spec))
    assert "ONE PARAMETER IS ENOUGH" in out, out


def test_a_flat_book_does_not_invent_a_correction():
    """Perfectly calibrated at every confidence: no bias, no slope."""
    spec = [(0.52, 0.52), (0.58, 0.58), (0.64, 0.64), (0.70, 0.70)]
    out = _run(_book(spec))
    assert "ONE PARAMETER IS ENOUGH" in out, out


# --- the positive case -----------------------------------------------------
def test_a_genuine_slope_is_detected():
    """Over-claiming that GROWS with confidence — 2 points off at 52%,
    18 at 78%. This is the shape a single pooled shift cannot express,
    and if the tool cannot see it here it cannot see it anywhere.

    IT TAKES 1,600 BETS TO FIRE, and that is a finding rather than a
    test-fixture detail. The same book at 600 bets sits at 1.3 standard
    errors and is correctly refused: separating a slope from a bias
    out-of-sample is a much more expensive measurement than measuring
    the bias, because the two models disagree by hundredths of a Brier
    point per row while a coin-flip outcome varies by whole ones.
    """
    spec = [(0.52, 0.50), (0.60, 0.53), (0.70, 0.58), (0.78, 0.60)]
    out = _run(_book(spec, reps=400))
    assert "ADOPT THE SLOPE" in out, out


def test_the_verdict_names_which_conditions_failed():
    """A refusal that does not say WHICH bar was missed is unactionable —
    'collect more data' and 'the slope is 1.01' are different answers."""
    spec = [(0.52, 0.44), (0.58, 0.50), (0.64, 0.56), (0.70, 0.62)]
    out = _run(_book(spec))
    assert "PASS" in out and "fail" in out
    assert "out-of-sample Brier improves" in out


def test_a_refusal_says_how_much_of_it_is_sample_size():
    """"The slope is not there" and "no sample this size could see a
    slope" are different answers, and at these sample sizes the second
    one is usually the true one. A verdict that does not separate them
    invites the wrong conclusion — that the shape question is closed."""
    spec = [(0.52, 0.50), (0.60, 0.53), (0.70, 0.58), (0.78, 0.60)]
    out = _run(_book(spec, reps=150))
    assert "ONE PARAMETER IS ENOUGH" in out
    assert "HOW MUCH OF THAT IS SAMPLE SIZE" in out
    assert "standard errors" in out


def test_the_needed_sample_always_exceeds_what_we_have():
    """n·(1.645/z)² with z below 1.645 is always larger than n, and that
    arithmetic is the point: whenever the bar is missed, the number
    printed is necessarily "more than the journal holds". A figure that
    could come back smaller would read as "you already have enough",
    which is the opposite of what a missed bar means."""
    st = [{"fit_a": (1.0, -0.3), "fit_b": (0.4, -0.1),
           "rows": _book([(0.52, 0.50), (0.78, 0.60)], reps=50)}]
    r = sc._paired(st)
    assert 0 < r["z"] < 1.645
    assert r["needed"] > r["n"]


def test_a_slope_that_predicts_worse_is_told_no_sample_would_help():
    """The other half of the honesty. If the held-out rows point AWAY
    from the slope, "collect more data" is the wrong advice — there is
    nothing there to collect toward, and saying so keeps a null from
    being read as a delay."""
    # fit_b deliberately mis-set so B predicts worse than A out of sample.
    st = [{"fit_a": (1.0, -0.3), "fit_b": (1.0, 0.9),
           "rows": _book([(0.52, 0.44), (0.70, 0.62)], reps=60)}]
    r = sc._paired(st)
    assert r["z"] <= 0.05
    assert r["needed"] is None


# --- the metric the cut is actually aimed at --------------------------------
def test_the_gap_is_reported_not_just_brier():
    """THE FIRST RUN OF THIS TOOL JUDGED THE CUT ON THE WRONG THING, and
    the real journal is what showed it: the live haircut improved Brier
    in 1 of 3 blocks and read as failing, while the quantity it was
    fitted to close was not in the table at all.

    Brier asks "does each claim predict its own outcome better". A pooled
    bias cannot do much for that — it moves every claim the same
    distance, improving the rows that lost and worsening the ones that
    won, which nearly cancels on a book near even money. The GAP asks "is
    the board's average claim honest", which is what the correction is
    for and what the over-claim costs, since every edge, EV and stake is
    computed from that claim.

    Both are printed. Neither is hidden. Picking one after seeing the
    numbers would be the failure this file exists to prevent, so the
    reason each is there is stated in the source above the verdict.
    """
    spec = [(0.52, 0.44), (0.58, 0.50), (0.64, 0.56), (0.70, 0.62)]
    out = _run(_book(spec))
    assert "gap none" in out and "Brier none" in out
    assert "CLOSED THE GAP in" in out
    assert "it improved Brier in" in out


def test_the_gap_is_signed_the_way_the_haircut_reads_it():
    """Negative means we still claim more than we land — the same sign
    convention `selectionfit` stores, so the two tools cannot be read
    against each other and disagree about direction."""
    over = [(0.60, 0), (0.60, 0), (0.60, 1), (0.60, 1), (0.60, 1)]  # claims 60, lands 60
    assert abs(sc._gap(over, 1.0, 0.0)) < 1e-9
    claiming_too_much = [(0.80, 0), (0.80, 1)]                      # claims 80, lands 50
    assert sc._gap(claiming_too_much, 1.0, 0.0) < 0


def test_a_cut_that_overshoots_is_visible_as_a_sign_flip():
    """Closing the gap and OVERcorrecting are different outcomes and the
    table has to tell them apart — a shift that turns -8 points of
    over-claim into +6 points of under-claim has not fixed anything, it
    has moved the error to the other side, and an absolute-value-only
    column would report that as an improvement."""
    i = SRC.index("def _gap(")
    fn = SRC[i:SRC.index("def _logloss(")]
    assert "abs(" not in fn, "the gap must stay signed"
    assert "landed - claimed" in fn


def test_the_two_metrics_disagreeing_is_explained_not_buried():
    """A reader who sees "closed the gap in 3 of 3, improved Brier in 1
    of 3" and is given no account of it will assume one of the numbers
    is broken."""
    assert "not a contradiction" in SRC
    assert "moves every" in SRC


# --- the guard most likely to bind on the real journal ----------------------
def test_a_narrow_board_is_told_it_cannot_answer():
    """THE HONEST FAILURE MODE. If every bet claims 52-56%, the data has
    no leverage on how error grows with confidence. Saying "no slope" and
    saying "this sample cannot see a slope" are different claims, and
    only one of them is true here."""
    spec = [(0.52, 0.44), (0.53, 0.45), (0.54, 0.46), (0.55, 0.47)]
    out = _run(_book(spec))
    assert "BELOW THE" in out and "leverage" in out.lower()
    assert "ONE PARAMETER IS ENOUGH" in out


def test_leverage_is_measured_before_the_slope_is_believed():
    """The bar is a named constant, not a number buried in a branch."""
    assert sc.ADOPT["min_logit_iqr"] > 0
    assert "claim spread ≥" in SRC


# --- the walk-forward ------------------------------------------------------
def test_the_walk_forward_scores_every_block_out_of_sample():
    """A block must never be in its own training window — that is the
    whole point, and an off-by-one here would silently turn the tool into
    an in-sample fit that always favours the bigger model."""
    pairs = _book([(0.52, 0.46), (0.60, 0.54)], reps=60)
    steps = sc._walk_forward(pairs)
    assert steps
    n = len(pairs)
    for s in steps:
        assert s["train_n"] + s["test_n"] <= n
        assert s["test_n"] > 0


def test_a_short_journal_gets_no_verdict_at_all():
    out = _run([(0.55, 1)] * 20)
    assert "too few" in out
    assert "ADOPT" not in out


# --- honesty ---------------------------------------------------------------
def test_it_never_writes_to_the_ledger():
    """Read-only means read-only: this reports on the correction, it does
    not become one."""
    body = "\n".join(l for l in SRC.splitlines()
                     if not l.strip().startswith("#"))
    for verb in ("INSERT", "UPDATE ", "DELETE", "commit()", "write_text"):
        assert verb not in body, f"{verb} in a read-only tool"
    assert "mode=ro" in SRC


def test_the_claims_are_un_shifted_before_they_are_measured():
    """THE TRAP THIS TOOL COULD MOST EASILY FALL INTO. A bet priced after
    the haircut shipped carries a hit_prob that already has the cut in
    it. Measuring the SHAPE of the error on corrected numbers describes
    the correction, not the model — and it would report the error as
    fixed on exactly the rows where it was being fixed. selectionfit owns
    that inverse, so it is reused rather than reimplemented."""
    assert "sf._pairs" in SRC
    assert "unshift" in SRC or "_pairs" in SRC


def test_the_decision_rule_is_stated_before_any_result():
    """A bar chosen after seeing the number is not a bar. It lives at the
    top of the file, above every function that computes anything."""
    i_rule = SRC.index("ADOPT = {")
    i_first_fit = SRC.index("def _fit_bias")
    assert i_rule < i_first_fit
    for key in ("out_of_sample_brier", "out_of_sample_logloss",
                "min_slope_distance", "bootstrap_share", "min_logit_iqr"):
        assert key in SRC


def test_the_slope_grid_can_express_under_confidence():
    """A grid running only below 1 would find over-confidence by
    construction — the arithmetic equivalent of asking a leading
    question."""
    assert min(sc._SLOPES) < 1.0 < max(sc._SLOPES)


def test_it_reads_the_same_books_the_record_does():
    """Fitting the shape on a population the record does not score would
    answer a question about a board nobody sees."""
    assert sc.BOOKS == sf.LEARNING_CATEGORIES


# --- model C: the step ------------------------------------------------------

def _deal(claimed, landed, n):
    """Outcomes spread evenly rather than sampled, so the shape under
    test is the shape that was dealt and not the seed."""
    out, w = [], 0
    for i in range(n):
        t = int(round((i + 1) * landed))
        out.append((claimed, 1 if t > w else 0))
        w = max(w, t)
    return out


def test_the_step_recovers_a_cut_that_is_really_there():
    """THE SHAPE THIS FILE'S OWN HEADER NAMES AND DID NOT FIT — "a step:
    one market or price band carries it and the rest is fine, and the
    pool hides it".

    Dealt honest below 0.55 and ten points high above it, which is the
    live MLB band table's shape. The fitter has to find the boundary and
    give the two sides different corrections."""
    rows = (_deal(0.45, 0.45, 400) + _deal(0.52, 0.52, 300)
            + _deal(0.62, 0.52, 300) + _deal(0.70, 0.58, 200))
    cut, lo, hi = sc._fit_step(rows)
    assert 0.54 <= cut <= 0.62, cut
    assert abs(lo) < 0.10, f"the honest side was corrected anyway: {lo}"
    assert hi < -0.25, f"the broken side was not corrected: {hi}"


def test_the_step_leaves_a_uniformly_honest_board_alone():
    rows = _deal(0.45, 0.45, 400) + _deal(0.65, 0.65, 400)
    _, lo, hi = sc._fit_step(rows)
    assert abs(lo) < 0.10 and abs(hi) < 0.10, (lo, hi)


def test_the_side_is_chosen_by_the_claim_not_by_the_corrected_value():
    """A correction able to move a bet across its own threshold would
    have no fixed point, and running it twice would disagree with
    running it once."""
    from engine import selectionfit as _sf
    # 0.56 sits just ABOVE a 0.55 cut, so it must take the high side's
    # correction — even though that correction lands it below the cut.
    got = sc._apply_step(0.56, 0.55, 0.0, -0.60)
    assert got == _sf._sigmoid(_sf._logit(0.56) - 0.60), (
        "the high side's bias was not the one applied")
    assert got < 0.55, (
        "this case no longer crosses the threshold, so it stops testing "
        "the rule it was written for")
    # And the low side is untouched by the high side's number.
    assert sc._apply_step(0.54, 0.55, 0.0, -0.60) == _sf._sigmoid(
        _sf._logit(0.54) + 0.0)


def test_the_cut_cannot_wander_to_the_edge_of_the_sample():
    """A threshold free to sit anywhere finds one, and it is the row
    that happened to lose."""
    assert min(sc._CUTS) >= 0.50 and max(sc._CUTS) <= 0.70


def test_a_thin_side_is_never_fitted():
    """Ten rows either side is the floor inside the fitter; the adoption
    bar asks for sixty in every scored block."""
    rows = _deal(0.45, 0.45, 400) + _deal(0.69, 0.40, 4)
    cut, lo, hi = sc._fit_step(rows)
    assert hi == 0.0 or abs(hi) < 0.9, (
        "four rows on one side produced a full-sized correction")


def test_the_step_is_declared_before_it_is_run():
    """Same discipline as the slope: every condition fixed in advance,
    so the verdict cannot be chosen after seeing the number."""
    for key in ("out_of_sample_brier", "out_of_sample_logloss",
                "min_bias_distance", "bootstrap_share", "min_side_rows",
                "beats_slope"):
        assert key in sc.ADOPT_STEP, key
    src = open(os.path.join(ROOT, "shapecheck.py"), encoding="utf-8").read()
    body = src[src.index("def _step_verdict("):]
    body = body[:body.index("\ndef ")]
    assert 'agg["brier_c"] < agg["brier_b"]' in body, (
        "a third parameter is being adopted without beating the second")
    assert "min_side_rows" in body and "min_bias_distance" in body


def test_a_refused_step_says_whether_it_is_the_shape_or_the_sample():
    """The distinction that matters most here. A band table showing a
    ten-point hole above 55% beside a verdict of "no" is exactly where
    somebody reads "the journal cannot tell yet" as "there is nothing
    there"."""
    src = open(os.path.join(ROOT, "shapecheck.py"), encoding="utf-8").read()
    body = src[src.index("def _step_verdict("):]
    body = body[:body.index("\ndef ")]
    assert "NOT 'THERE IS NO STEP'" in body
    assert "needed" in body, "no estimate of how much data would settle it"


def test_this_file_still_writes_nothing():
    """It reports; it does not change what the board prices with. Three
    parameters make that more important, not less."""
    src = open(os.path.join(ROOT, "shapecheck.py"), encoding="utf-8").read()
    for bad in ("sf.save", "json.dump", "write_text", "refresh("):
        assert bad not in src, bad


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
