"""The tool that ends the guess-and-check loop, and the one thing it must
never do.

`sim_reconcile.py` only runs where statsapi.mlb.com is reachable, so every
round of "what is wrong with those lineups" cost a round trip: run it
there, paste the output, guess here, change something, run it again. Three
of those rounds produced confident explanations — the plate-appearance
one, the lineup-heterogeneity one, the more-rounds one — and all three
were wrong. One produced a fix that had to be reverted for breaking a
lineup nobody had thought to check.

The dump carries every hitter's projected means and batting spot, which is
a complete input to the whole chain, so a failing lineup can be rebuilt and
re-run anywhere. These tests defend the three properties that make the tool
worth having:

  * it SEPARATES the four causes — the sampler, the fit's own noise,
    convergence, a real disagreement — because they call for opposite
    fixes and "the gate failed" does not distinguish them;
  * it asks the GATE's question with the gate, not with a second threshold
    invented alongside it. An earlier draft used its own cutoff and
    disagreed with the gate about healthy lineups, which is the exact
    failure it exists to prevent;
  * it credits a knob only when that knob HALVES the gap and lands inside
    the tolerance. A tool built to stop people guessing does not get to
    read its own sampler wobble as a diagnosis.
"""

import io
import json
import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sim_diagnose as SD                                     # noqa: E402
from engine.mlb import gamesim as G                           # noqa: E402
from engine.mlb.models import HITS, HOME_RUNS, TOTAL_BASES    # noqa: E402

NORMAL = [(1.05, 1.72, 0.14), (0.98, 1.60, 0.12), (1.02, 1.95, 0.22),
          (0.95, 1.90, 0.26), (0.88, 1.55, 0.17), (0.82, 1.34, 0.12),
          (0.75, 1.18, 0.09), (0.70, 1.05, 0.07), (0.62, 0.92, 0.05)]


def _cell(rows, tol=0.06):
    return {"tol": tol, "worst": 0.11, "hitters": {
        f"b{i}": {"spot": i,
                  "projected": {HITS: h, TOTAL_BASES: tb, HOME_RUNS: hr},
                  "simulated": {}, "se": {},
                  "pa_expected": None, "pa_simulated": None}
        for i, (h, tb, hr) in enumerate(rows, start=1)}}


def _dump(cells) -> str:
    path = os.path.join(tempfile.mkdtemp(), "d.json")
    open(path, "w").write(json.dumps(cells))
    return path


#: Diagnosing a lineup means three fits and three 120,000-trial runs, which
#: is most of a minute. Several tests below ask different questions of the
#: SAME diagnosis, so it is run once per distinct dump and the transcript
#: reused. Keyed on the dump's contents, not its path, since each call site
#: writes to a fresh temp directory.
_SEEN: dict = {}


def _out(path) -> str:
    key = open(path).read()
    if key not in _SEEN:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            SD.main([path])
        _SEEN[key] = buf.getvalue()
    return _SEEN[key]


# --- it rebuilds the real thing -------------------------------------------
def test_a_lineup_is_rebuilt_from_projections_and_spots_alone():
    """The claim the whole tool rests on: projected means plus batting spot
    is a complete input to the chain, so no feed is needed to re-run it."""
    rates, targets = SD._rebuild(_cell(NORMAL))
    assert len(targets) == 9
    assert [r.spot for r in rates] == list(range(1, 10))
    # And the rates really do invert the projections they came from.
    b3 = next(r for r in rates if r.name == "b3")
    pa = G.expected_pa(3)
    assert abs((b3.single + b3.double + b3.triple + b3.hr) * pa - 1.02) < 1e-9


def test_a_short_order_is_padded_exactly_as_the_gate_pads_it():
    """Diagnosing a lineup the gate never simulated would answer a question
    nobody asked."""
    rates, targets = SD._rebuild(_cell(NORMAL[:7]))
    assert len(rates) == 9 and len(targets) == 7
    assert all(n.startswith("_filler") for n in
               {r.name for r in rates} - set(targets))


def test_a_hitter_whose_triple_is_not_baseball_stays_out():
    """Same exclusion the gate makes: the sim cannot reproduce a triple no
    outcome table could, and grading it blames the wrong model."""
    bad = list(NORMAL)
    bad[4] = (1.5, 0.4, 0.3)              # total bases below hits
    _, targets = SD._rebuild(_cell(bad))
    assert "b5" not in targets and len(targets) == 8


# --- it separates the causes ----------------------------------------------
def test_a_lineup_that_only_failed_on_noise_is_told_so():
    """The gate takes the max over hundreds of comparisons, so at 20,000
    trials it fails on lineups that are fine. Those must come back as the
    trial count and nothing else, or someone goes hunting a model bug."""
    out = _out(_dump({"CLEAN": _cell(NORMAL)}))
    assert "does not reproduce" in out, out
    assert "sampler noise" in out, out


def test_a_real_gap_is_sized_against_both_the_tolerance_and_the_sampler():
    """At 120,000 trials a 1% gap is many sigma and still a sixth of what
    the gate forgives. Significant and important are different questions
    and one number cannot answer both, so a failure reports each."""
    rare = list(NORMAL)
    rare[7] = UNREACHABLE
    out = _out(_dump({"RARE": _cell(rare)}))
    assert "tolerance" in out and "sigma" in out, out


#: A hitter given a home-run rate of two ten-thousandths a game. Nothing
#: on a real slate looks like this; it is here because it is the only
#: synthetic line found that reliably fails the gate at 120,000 trials,
#: which is what the failing branch needs in order to be tested at all.
#:
#: Worth recording what it is NOT. Four real lineups failed on hitters
#: with impossible batting averages — OAK's Carlos Cortes at 0.055 hits a
#: game over 3.8 plate appearances, which is .014 — and the obvious guess
#: was that a near-zero projection breaks the fit. It does not: dropping
#: Cortes's exact line into an ordinary order PASSES, reproducing even his
#: plate-appearance drift (3.95 → 3.82 against a live 3.81). Only the
#: absurd home-run value below fails, and it fails with the three markets
#: moving +9.4% / +3.3% / +20.8% — which is not one rescale and so is not
#: the live signature either. The live failures are not reproduced here.
UNREACHABLE = (0.0552, 0.1186, 0.0002)


def test_a_failing_lineup_is_diagnosed_rather_than_just_reported():
    rare = list(NORMAL)
    rare[7] = UNREACHABLE
    out = _out(_dump({"RARE": _cell(rare)}))
    assert "still FAILS" in out, out
    assert "b8" in out, out
    assert "VERDICT:" in out, out


def test_the_two_fitting_knobs_are_reported_separately():
    """More trials per round and more rounds fix different things — the
    fit's own sampler noise versus convergence — and prescribing the wrong
    one is how the previous attempt got reverted. Both are measured."""
    rare = list(NORMAL)
    rare[7] = UNREACHABLE
    out = _out(_dump({"RARE": _cell(rare)}))
    assert "fit at 60,000 trials/round" in out, out
    assert "fit for 18 rounds" in out, out


def test_markets_disagreeing_by_different_amounts_is_not_a_fit_problem():
    """The discriminator the whole tool turns on. One rescale moves a
    hitter's three markets by the SAME percentage; the unreachable line
    moves them +9.4% / +3.3% / +20.8%, so no rescale reaches it and
    pointing at calibrate would be the fourth wrong guess in a row."""
    rare = list(NORMAL)
    rare[7] = UNREACHABLE
    out = _out(_dump({"RARE": _cell(rare)}))
    assert "NOT a single rescale" in out, out


def test_a_projection_that_is_not_a_hitter_is_named_before_the_sim_is():
    """Every lineup on the run that prompted this tool carried one: OAK's
    Carlos Cortes at 0.055 hits a game over 3.8 plate appearances is a .014
    batting average. Asking which of the two models is wrong about him is
    the wrong question — the projection is not a number a hitter can have,
    and the sim only inherits it."""
    odd = list(NORMAL)
    odd[7] = (0.0552, 0.1186, 0.005)
    out = _out(_dump({"ODD": _cell(odd)}))
    assert "not a hitter" in out, out
    assert "PROJECTION-engine finding" in out, out
    # And an ordinary order says nothing of the kind.
    assert "not a hitter" not in _out(_dump({"FINE": _cell(NORMAL)}))


def test_the_implausibility_bar_sits_below_even_a_pitcher_hitting():
    """It has to flag the broken, not the bad. A genuinely poor regular
    sits near 0.15 hits per plate appearance and must pass unremarked, or
    the warning becomes noise and stops being read."""
    assert SD.IMPLAUSIBLE_AVG < 0.10
    worst_real = min(h / G.expected_pa(i) for i, (h, _, _)
                     in enumerate(NORMAL, start=1))
    assert worst_real > SD.IMPLAUSIBLE_AVG


def test_a_knob_only_counts_if_it_halves_the_gap():
    """A coin-flip improvement is not a cure. `fixed` requires the residual
    to land inside the tolerance AND at half the original, so sampler
    wobble in the diagnosis cannot be read as a diagnosis."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "sim_diagnose.py"), encoding="utf-8").read()
    assert "abs(x) < abs(d) / 2" in src


def test_the_single_rescale_signature_is_reported():
    """calibrate scales all of a hitter's reaching outcomes by ONE factor,
    so a fitting problem moves his three markets by the same percentage.
    Three markets disagreeing by different amounts is not a fitting problem
    and must not be reported as one — that mistake is what sent two
    sessions after calibrate when the answer was elsewhere."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "sim_diagnose.py"), encoding="utf-8").read()
    assert "SAME_RESCALE" in src
    assert "NOT a single rescale" in src


# --- it behaves when there is nothing to do -------------------------------
def test_a_missing_dump_says_how_to_make_one():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = SD.main([os.path.join(tempfile.mkdtemp(), "nope.json")])
    assert code == 1
    assert "--dump" in buf.getvalue()


def test_an_empty_dump_is_the_gate_passing_not_an_error():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = SD.main([_dump({})])
    assert code == 0
    assert "passed" in buf.getvalue()


def test_a_lineup_too_thin_to_diagnose_is_skipped_not_guessed_at():
    out = _out(_dump({"THIN": _cell(NORMAL[:4])}))
    assert "nothing to diagnose" in out, out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
