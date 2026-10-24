"""Journaled and graded, never staked — enforced, not just announced.

Four places promised it in almost the same words:

    engine/cfb/ratings.py   "puts the whole CFB board on probation:
                             journaled and graded, never staked"
    engine/hoops.py         "True when picks must be journaled and graded
                             but NOT bet"
    engine/coverage.py      "on probation — journaled and graded, not staked"
    web/js/app.js           "is on probation — graded, not bet"

Measured 2026-08-27: nothing read the flag. `evaluate_play` ran Kelly and
wrote a stake whatever it said, so an uncalibrated CFB board graded a
play A+ and sized it at 2% of bankroll under a banner saying it was not
being bet — and WNBA, whose fitted numbers are the NBA's, did the same.
A label in four files and an enforcement in none.

That is the twin of a fabricated number: instead of showing something
that is not real, it does something it says it is not doing. Someone
reading the banner is being told the wrong thing about their own money.

Run directly: `python3 tests/test_probation.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import probation as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAY = {"market": "spread", "selection": "KC -3", "odds": -110,
        "opposing_odds": -110, "p_model": 0.62, "p_market": 0.524,
        "book": "dk", "attention_tier": "standard",
        "information_certainty": 0.95, "attention_fit": 0.9,
        "situational_fit": 0.9, "matchup_fit": 0.9, "environment_fit": 0.9,
        "kickoff": "", "volatility": "normal",
        "game": {"home": "KC", "away": "BUF", "game_id": "1"}}


def _slate(fitted, games):
    from engine.cfb import pipeline as CP
    return CP.run_cfb_slate([dict(PLAY)],
                            meta={"ratings": {"fitted": fitted,
                                              "games": games}})


# --- the bug, pinned ---------------------------------------------------------
def test_an_unfitted_board_grades_and_does_not_stake():
    """The whole point. It publishes, it ranks, it grades — and the size
    is withheld, because there is no measured spread to size against."""
    r = _slate(fitted=False, games=1)
    play = r["plays"][0]
    assert r["probation"] is True
    assert play["grade_label"] == "A+"          # still graded
    assert play["stake_fraction"] == 0.0        # …and not staked
    assert r["exposure"] == 0.0


def test_the_play_survives_rather_than_falling_into_the_pass_list():
    """Gating before the caps would make every play look cap-trimmed and
    sweep the board into passes, losing the grades — and the grades are
    the entire point of a probation board."""
    r = _slate(fitted=False, games=1)
    assert len(r["plays"]) == 1
    assert r["no_qualifying"] is False
    assert not any(p.get("on_probation") for p in r["pass_list"])


def test_what_the_stake_would_have_been_rides_alongside():
    """Same shape the conditional plays already use, for the same reason:
    the card can say what the measurement is worth without pretending it
    is a bet."""
    r = _slate(fitted=False, games=1)
    play = r["plays"][0]
    assert play["stake_if_measured"] > 0
    assert play["on_probation"] is True
    assert play["probation_reasons"]


def test_the_conditionals_are_gated_too():
    """A hold's chip says "1.40u if confirmed". On a probation board that
    is false twice over: confirming the starter would not produce a stake
    either, because the thing being waited on is a measurement."""
    from engine.cfb import pipeline as CP
    src = open(os.path.join(ROOT, "engine", "cfb", "pipeline.py"),
               encoding="utf-8").read()
    assert 'stake_keys=("stake_if_confirmed",)' in src
    # …and it is applied to holds, not to published.
    line = [l for l in src.splitlines() if "stake_if_confirmed\"," in l][0]
    assert line.strip().startswith("holds = _unstake(")
    out = CP.run_cfb_slate([], meta={"ratings": {"fitted": False, "games": 1}})
    assert out["holds"] == []


def test_a_fitted_board_stakes_normally():
    r = _slate(fitted=True, games=3132)
    play = r["plays"][0]
    assert r["probation"] is False
    assert play["stake_fraction"] > 0
    assert "stake_if_measured" not in play
    assert r["exposure"] > 0


def test_the_payload_flag_is_read_off_the_slate_not_the_fit():
    """The two used to be able to drift: one said probation, the other
    sized the bets."""
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert 'out["probation"] = bool(result.get("probation"' in src


# --- the module ---------------------------------------------------------------
def test_an_unfitted_variance_blocks_a_stake():
    why = P.reasons(fitted=False, games=7)
    assert why and "7 graded game(s)" in why[0]


def test_a_fitted_variance_blocks_nothing():
    assert P.reasons(fitted=True, games=3132) == []


def test_an_unmeasured_haircut_advises_but_does_not_block():
    """A different and weaker claim than probation. It says the size
    rests on a guess, not that the guess is wrong — and the evidence it
    is too generous comes from ONE sport. Silencing a league on another
    league's fit is the cross-league borrowing this codebase refuses."""
    assert P.reasons(fitted=True, games=3132) == []
    assert P.advisories("cfb")


def test_a_sport_with_a_measured_haircut_gets_no_advisory():
    from engine import gamecal
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    import tempfile
    gamecal.STATE_PATH = os.path.join(tempfile.mkdtemp(), "gamecal.json")
    gamecal._cache.clear()
    try:
        gamecal._write_state({
            f"zz:{m}": {"shrink": 0.2, "slope": 0.2, "se": 0.05, "n": 900}
            for m in ("spread", "total")})
        gamecal._cache.clear()
        assert P.advisories("zz") == []
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


def test_a_broken_fitter_never_silently_unstakes():
    """A haircut lookup that raises must cost the advisory, not the
    board — the failure mode where a bug quietly withholds every size."""
    from engine import gamecal
    keep = gamecal.measured
    gamecal.measured = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    try:
        assert P.haircut_reason("cfb") is None
        assert P.advisories("cfb") == []
    finally:
        gamecal.measured = keep


def test_unstake_zeroes_every_size_field_in_one_pass():
    """Two calls would have the second overwrite the first's record of
    what the size would have been."""
    out = P.unstake([{"stake_fraction": 0.02, "stake_units": 1.8}], ["why"],
                    stake_keys=("stake_fraction", "stake_units"))[0]
    assert out["stake_fraction"] == 0.0 and out["stake_units"] == 0.0
    assert out["stake_if_measured"] == 0.02
    assert out["stake_if_measured_stake_units"] == 1.8


def test_a_card_that_was_never_sized_does_not_sprout_a_would_have_been():
    out = P.unstake([{"stake_fraction": 0.0}], ["why"])[0]
    assert P.CARRY_KEY not in out
    assert out["on_probation"] is True


def test_nothing_is_touched_when_there_is_nothing_to_enforce():
    cards = [{"stake_fraction": 0.02}]
    assert P.unstake(cards, []) is cards


def test_the_notes_read_as_sentences():
    assert P.note([]) == "" and P.advisory_note([]) == ""
    n = P.note(P.reasons(fitted=False, games=1))
    assert n.startswith("Graded and journaled, not staked:") and n.endswith(".")
    a = P.advisory_note(P.advisories("cfb"))
    assert a.startswith("Sized on an unmeasured haircut:")


# --- the other league that made the same promise -------------------------------
def test_the_hoops_gate_is_wired_too():
    """WNBA is calibrated=False, inheriting the NBA's fitted numbers, and
    published staked picks under the same banner."""
    src = open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
               encoding="utf-8").read()
    assert "from ..probation import unstake" in src
    assert 'stake_keys=("stake_fraction", "stake_units")' in src
    block = src[src.index("if tune.probation:"):]
    assert "inherited_from" in block[:600]


def test_the_hoops_reasons_are_always_defined():
    """`_why` is referenced in the return; a board that skipped the caps
    branch must not raise a NameError on the way out."""
    src = open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
               encoding="utf-8").read()
    assert "_why: list[str] = []" in src
    assert src.index("_why: list[str] = []") < src.index("if tune.probation:")


# --- the page -----------------------------------------------------------------
def test_the_banner_prefers_the_real_reason():
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "(d.probation_reasons || [])[0]" in src


def test_the_advisory_has_a_renderer_and_somewhere_to_render():
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert "function renderAdvisories(" in src
    assert "renderAdvisories();" in src
    assert 'id="advisory-note"' in html


def test_a_card_says_it_is_not_staked():
    """The stake chip hides at zero, so without this a probation card
    would show a pick with no size and no explanation — and "why is there
    no number here" is exactly what a banner at the top of the page
    cannot answer once you have scrolled to a card."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "const probChip = r.on_probation" in src
    assert "once measured" in src
    assert "${probChip}" in src


def test_the_not_staked_chip_mirrors_the_conditional_one():
    """Same shape, same class, same reason: a real number waiting on
    something real, deliberately not in the stake chip because nothing
    has been wagered."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    block = src[src.index("const probChip = r.on_probation"):]
    block = block[:block.index('const tierChip')]
    assert 'class="chip cond"' in block
    assert "stake_if_measured_units > 0" in block


def test_the_advisory_is_silent_with_nothing_to_say():
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    block = src[src.index("function renderAdvisories("):]
    block = block[:block.index("\n}\n") + 3]
    assert '!lines.length' in block and 'host.innerHTML = ""' in block


def test_the_advisory_is_silent_on_a_probation_board():
    """Its whole sentence is "these plays ARE staked, and here is what
    the size rests on" — false the moment nothing is staked, and it would
    sit directly under a banner saying so."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    block = src[src.index("function renderAdvisories("):]
    block = block[:block.index("\n}\n") + 3]
    assert "|| d.probation" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
