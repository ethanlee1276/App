"""The selection haircut: does the correction earn its own application?

Ethan's journal claimed 51.5% and landed 42.5% over 113 bets, and 59.7%
against 49.7% over the 197 before that. engine/selectionfit.py exists to
turn that measured over-claim into a correction on every probability the
board publishes. These tests pin the four things that make it safe to run
unattended, because each one has a failure mode that looks like working
software:

  * a real gap gets corrected, and by roughly the right amount;
  * a noise-sized gap gets nothing (or the fit chases variance forever);
  * a young journal gets nothing (or 40 bets set the whole board's size);
  * a refit un-does its own prior work first (or the correction erases
    itself the night after it ships, and oscillates from then on).

Plus the two wiring facts: the haircut reaches the betting path, and it
never changes which SIDE we bet.
"""

import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import selectionfit as sf                          # noqa: E402


def journal(n, claimed, true_shift, sport="mlb", ts="2026-07-01", seed=7):
    """A journal whose bets really are biased by ``true_shift``.

    Outcomes are DRAWN from the true probability rather than assigned by a
    fixed win count and shuffled. That distinction is not cosmetic: a fixed
    count makes the early and late halves anti-correlated by construction —
    every extra winner up front is a loser at the back — so the held-out
    test fails on data that has no drift in it at all. The first cut of this
    file did exactly that and made a working gate look broken.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, "
                 "hit_prob REAL, odds INTEGER, status TEXT, ts TEXT, "
                 "category TEXT)")
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        p = min(0.88, max(0.32, rng.gauss(claimed, 0.05)))
        won = rng.random() < sf.shift_prob(p, true_shift)
        rows.append([sport, "hits", "OVER", p, -110,
                     "won" if won else "lost", ts, "main"])
    conn.executemany("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)", rows)
    return conn


#: A nine-point over-claim in log-odds — the size the journal measured.
REAL_BIAS = -0.36


def test_a_real_over_claim_is_corrected_and_lands_near_the_gap():
    e = sf.measure(journal(310, 0.515, REAL_BIAS))["pooled"]
    assert e["applied"] is True
    assert e["shift"] < 0
    # The correction must actually close most of the gap. Applying it to
    # the mean claim should land within a point of what really happened —
    # a shift that only shaves a third of a nine-point miss is a fit that
    # ran but did not fix anything.
    corrected = sf.shift_prob(e["claimed"], e["shift"])
    assert abs(corrected - e["landed"]) < 0.012, corrected
    # And it has to be an improvement by the score it was fitted on.
    assert e["brier_after"] < e["brier_before"]


def test_a_noise_sized_gap_is_measured_and_refused():
    e = sf.measure(journal(310, 0.515, 0.0, seed=4))["pooled"]
    assert e["n"] == 310
    assert e["applied"] is False
    assert e["shift"] == 0.0
    # Named for what it is. A gap inside one standard error reported as
    # "we under-claim" would be a different (and wrong) finding.
    assert "noise" in e["reason"]


def test_a_young_journal_gets_nothing_and_says_what_it_needs():
    e = sf.measure(journal(60, 0.515, REAL_BIAS))["pooled"]
    assert e["applied"] is False
    assert "60 of 100" in e["reason"]
    # Fitted anyway, so the page can show the trend before the floor —
    # measuring early is fine, BETTING early is not.
    assert e["shift_raw"] < 0


def test_an_under_claim_is_published_but_never_applied():
    e = sf.measure(journal(310, 0.470, 0.40))["pooled"]
    assert e["gap"] > 0
    assert e["shift"] > 0            # the fit says raise
    assert e["applied"] is False     # we decline
    assert "UNDER-claim" in e["reason"]


def test_the_shift_never_exceeds_its_cap():
    # A catastrophic sample: claimed 70%, landing far under it.
    e = sf.measure(journal(300, 0.70, -2.2))["pooled"]
    assert abs(e["shift"]) <= sf.SHIFT_CAP
    assert e["capped"] is True


def test_a_refit_undoes_its_own_prior_correction():
    """The oscillation guard.

    Once a shift ships, later claims already contain it. A naive refit on
    those measures nothing left to fix, stores ~0, and ERASES a working
    correction — after which the gap returns and the next refit re-applies
    it, forever. Both halves are asserted: that the naive answer really is
    ~0 (so the danger is real, not theoretical), and that un-shifting
    recovers the original.
    """
    store = Path(tempfile.mkdtemp()) / "selection.json"
    first = sf.refresh(journal(310, 0.515, REAL_BIAS), path=store)
    shift = first["pooled"]["shift"]
    assert shift < -0.2

    # A second era, priced with that shift live.
    later = sqlite3.connect(":memory:")
    later.row_factory = sqlite3.Row
    later.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, "
                  "hit_prob REAL, odds INTEGER, status TEXT, ts TEXT, "
                  "category TEXT)")
    src = journal(310, 0.515, REAL_BIAS)
    for r in src.execute("SELECT * FROM bets"):
        later.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)",
                      (r["sport"], r["market"], r["side"],
                       sf.shift_prob(r["hit_prob"], shift), r["odds"],
                       r["status"], "2099-01-01", "main"))

    naive = sf.measure(later, {})["pooled"]["shift"]
    assert abs(naive) < 0.05, "the danger is not real; this test is worthless"

    aware = sf.measure(later, first)["pooled"]["shift"]
    assert abs(aware - shift) < 0.02, (aware, shift)


def test_a_sport_under_the_floor_borrows_the_pool():
    conn = journal(310, 0.515, REAL_BIAS, sport="mlb")
    for r in journal(20, 0.55, REAL_BIAS, sport="nba", seed=3).execute(
            "SELECT * FROM bets"):
        conn.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)", tuple(r))
    store = Path(tempfile.mkdtemp()) / "selection.json"
    sf.refresh(conn, path=store)
    sf.reset_cache()
    assert sf.shift_for("mlb", store) < 0
    assert sf.basis_for("mlb", store) == "own"
    # NBA has 20 settled bets — nowhere near its own floor — so it runs on
    # the pooled number rather than on nothing. The pooled number is not
    # MLB's: it is fitted over both sports' rows, which is the point of
    # having it rather than copying the biggest sport's answer.
    assert sf.basis_for("nba", store) == "pooled"
    assert sf.shift_for("nba", store) == sf.load(store)["pooled"]["shift"]
    assert sf.shift_for("nba", store) < 0
    # A sport with no journal at all still gets the pool: the thing being
    # corrected is how we select, not what we know about basketball.
    assert sf.shift_for("cfb", store) < 0


def test_no_store_means_no_correction():
    missing = Path(tempfile.mkdtemp()) / "nope.json"
    sf.reset_cache()
    assert sf.shift_for("mlb", missing) == 0.0
    assert sf.apply_haircut("mlb", 0.61, missing) == 0.61
    assert sf.report(missing)["live"] is False


def test_the_held_out_test_is_a_gate_not_a_report():
    """docs/SELECTION_CORRECTION.md §7, enforced in code.

    "Fitted is not validated. Split the journal by date. Fit on the
    earlier part only. Measure the gap on the LATER part, with and
    without. Ship only if the held-out gap closes." A correction that
    improved only its own training data would be exactly the failure the
    doc pre-registered as a reason to abandon.
    """
    e = sf.measure(journal(310, 0.515, REAL_BIAS))["pooled"]
    h = e["holdout"]
    assert h["ran"] and h["improved"] and e["applied"]
    # Chronological, not random: a random split leaks the same nights into
    # both halves and cannot answer "does this help bets it has not seen".
    assert h["train_n"] + h["test_n"] == 310
    assert h["test_n"] == int(310 * sf.HOLDOUT_FRACTION)
    assert h["gap_after"] < h["gap_before"]
    assert h["brier_after"] < h["brier_before"]


def test_a_correction_that_fails_out_of_sample_is_refused():
    """A journal biased early and clean late. In-sample the fit sees a
    real gap; out of sample the correction makes things worse, and the
    board must not get it."""
    early = journal(220, 0.515, -0.55, seed=2)
    rows = list(early.execute("SELECT * FROM bets"))
    late = journal(120, 0.515, 0.0, seed=9)
    for r in late.execute("SELECT * FROM bets"):
        early.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)", tuple(r))
    e = sf.measure(early)["pooled"]
    assert e["shift"] < 0                    # the pooled fit still wants one
    assert e["holdout"]["ran"]
    assert e["holdout"]["improved"] is False
    assert e["applied"] is False
    assert "held-out" in e["reason"]
    assert len(rows) == 220                  # the early era really is there


def test_the_gate_has_power_and_does_not_fire_on_nothing():
    """The two numbers that decide whether any of this is worth running.

    A gate that never applies is a correction that does not exist; one
    that always applies is a coin flip with a docstring. Measured over 40
    independent journals at the size Ethan's actually is.
    """
    import random as _r
    hits = sum(sf.measure(journal(310, 0.515, REAL_BIAS, seed=100 + s)
                          )["pooled"]["applied"] for s in range(40))
    false_alarms = sum(sf.measure(journal(310, 0.515, 0.0, seed=200 + s)
                                  )["pooled"]["applied"] for s in range(40))
    assert hits >= 28, f"only {hits}/40 — the gate is too strict to matter"
    assert false_alarms <= 6, f"{false_alarms}/40 on unbiased journals"
    assert _r  # the fixtures are seeded; no ambient randomness in this test


def test_an_empty_journal_never_overwrites_a_real_fit():
    """A refit that measured nothing must not erase what was measured.

    Found in the suite, not in review: a settle-pass test running against
    an empty ledger called refresh(), which wrote its blank result over
    the live store — and the rest of the run then priced with no haircut
    and reported all green. A fit with zero settled bets is an absence of
    evidence, not evidence of no bias.
    """
    store = Path(tempfile.mkdtemp()) / "selection.json"
    sf.refresh(journal(310, 0.515, REAL_BIAS), path=store)
    sf.reset_cache()
    before = sf.shift_for("mlb", store)
    assert before < -0.2

    empty = sqlite3.connect(":memory:")
    empty.row_factory = sqlite3.Row
    empty.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, "
                  "hit_prob REAL, odds INTEGER, status TEXT, ts TEXT, "
                  "category TEXT)")
    out = sf.refresh(empty, path=store)
    assert out.get("unchanged")
    sf.reset_cache()
    assert sf.shift_for("mlb", store) == before


def test_the_switch_turns_the_haircut_off_for_a_measurement():
    """Tests that price synthetic slates need a known correction state.

    Without this, any file that builds a board and asserts on it depends
    on whatever last night's settle pass fitted — the failure lands three
    files from anything named calibration.
    """
    store = Path(tempfile.mkdtemp()) / "selection.json"
    sf.refresh(journal(310, 0.515, REAL_BIAS), path=store)
    sf.reset_cache()
    assert sf.shift_for("mlb", store) < 0
    with sf.disabled():
        assert sf.shift_for("mlb", store) == 0.0
        assert sf.apply_haircut("mlb", 0.58, store) == 0.58
    assert sf.shift_for("mlb", store) < 0        # restored on the way out


def test_the_slate_pricing_tests_keep_the_switch_off():
    """The three files that broke when the store went live stay guarded.

    An assertion on the files themselves, because the thing being
    protected is a property of the suite: these price a board and assert
    on the output, so a live haircut empties them.
    """
    root = Path(__file__).parent
    for name in ("test_fatigue_journaled.py", "test_lab.py",
                 "test_ladder_all_sports.py"):
        src = (root / name).read_text()
        assert "set_enabled(False)" in src, name


def test_the_edge_moves_with_the_probability_not_independently():
    """`apply_selection` is the betting path's only entry point.

    edge is ``hit − fair`` and the haircut does not touch fair, so the two
    have to move by the same amount. A board that cut the probability and
    left the headline edge alone would advertise an edge its own stake had
    already stopped believing in.
    """
    from engine.betting import apply_selection
    hit, edge = 0.60, 0.05
    got_hit, got_edge = apply_selection(hit, edge, "mlb")
    assert abs((got_hit - hit) - (got_edge - edge)) < 1e-12


def test_the_haircut_runs_after_the_side_is_chosen():
    """It can shrink a bet out of existence; it can never flip one.

    Read off the source rather than the output: the assertion is about
    ORDER, and an output test would pass on a board where the haircut
    happened to change no sides today.
    """
    import inspect
    from engine import betting
    from engine.mlb import betting as mlb_betting
    for mod in (betting, mlb_betting):
        src = inspect.getsource(mod)
        assert src.index("pick_side(prop.lines") < src.index("= apply_selection("), \
            f"{mod.__name__}: the haircut must not run before pick_side"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
