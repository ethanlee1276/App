"""A measurement taken on the NFL is not a measurement about college.

Backlog #132. `engine.parlays.rho_meta` had no sport in it, so every
correlation the module knows was answered to whoever asked. A COLLEGE
quarterback stack was priced on +0.637 — measured over NFL 2021-2026 —
and the card said so in as many words: "measured at +0.64 on 2,844 of
our own games". Not one of those games was college.

It is the same fault `likely.CFB_TD_AUC` was created to end, where the
college board wore the NFL's 0.721 because `from_watch` read a shipped
constant with no idea whose chain built the row. The correlation prior
is a worse place for it: it is the ONLY thing standing between a
same-game ticket and being priced as if its legs were independent.

A sport with no measurement of its own now falls back to the PUBLISHED
PRIOR, and that is the fix rather than a shortfall. The prior is an
estimate that says it is one; a foreign measurement is an estimate
wearing somebody else's sample size, and the sample size is what invites
conviction.

Run directly: `python3 tests/test_parlay_sport_scope.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlays as P
from engine import corrfit


def test_every_measurement_names_the_sport_it_was_taken_on():
    """`MEASURED_SPORT` sits beside `MEASURED` rather than inside it, so
    the two can drift. They cannot drift past this: every entry needs a
    sport, and the sport has to agree with the provenance string the
    card quotes."""
    assert set(P.MEASURED_SPORT) == set(P.MEASURED), (
        set(P.MEASURED) ^ set(P.MEASURED_SPORT))
    for name, sport in P.MEASURED_SPORT.items():
        provenance = P.MEASURED[name][2]
        assert sport in provenance, (name, sport, provenance)


def test_college_does_not_inherit_the_nfl_passing_measurement():
    """THE BUG. +0.637 on 2,844 NFL team-weeks was pricing college."""
    nfl_r, nfl_meas = P.rho_for("qb_passing_game", 0.425, "nfl")
    cfb_r, cfb_meas = P.rho_for("qb_passing_game", 0.425, "cfb")
    assert nfl_meas is True and abs(nfl_r - 0.637) < 1e-9
    assert cfb_meas is False and abs(cfb_r - 0.425) < 1e-9, (cfb_r, cfb_meas)


def test_the_sample_size_goes_with_the_number_not_with_the_name():
    """The half of this that shipped broken in its own first cut: the
    `sport` reached `rho_n`'s signature and not its body, so a college
    card priced on the prior still printed "on 2,844 games" beside it.
    A provenance is worse than useless when it belongs to another
    sport's number."""
    assert P.rho_n("qb_passing_game", "nfl") == 2844
    assert P.rho_n("qb_passing_game", "cfb") == 0
    assert P.rho_n("lineup_stack", "mlb") > 0
    assert P.rho_n("lineup_stack", "cfb") == 0


def test_a_sport_keeps_its_own_measurements():
    for name, prior in (("possession_pie", -0.10), ("run_game_script", 0.30),
                        ("qb_td_wr_td", P.SAME_GAME_BASELINE_RHO),
                        ("qb_td_game", P.SAME_GAME_BASELINE_RHO)):
        r, meas = P.rho_for(name, prior, "nfl")
        assert meas is True, name
        assert abs(r - P.MEASURED[name][0]) < 1e-9, name
    for name in ("pitcher_vs_lineup", "lineup_stack"):
        r, meas = P.rho_for(name, 0.275, "mlb")
        assert meas is True and abs(r - P.MEASURED[name][0]) < 1e-9, name


def test_a_caller_that_names_no_sport_is_unchanged():
    """simrecon, engine/mlb/gamesim and the doctor read these without a
    sport. Scoping must not silently empty them."""
    r, meas = P.rho_for("qb_passing_game", 0.425)
    assert meas is True and abs(r - 0.637) < 1e-9
    assert P.rho_meta("lineup_stack") is not None


def test_a_college_ticket_never_claims_a_measurement_on_its_card():
    """The end-to-end shape: `relate` threads its own `sport` down, so
    the sentence the reader sees on a college stack carries no sample
    size and no measured figure."""
    a = {"player": "A QB", "team": "TOL", "market": "pass_yds",
         "side": "over", "line": 245.5}
    b = {"player": "A Wideout", "team": "TOL", "market": "rec_yds",
         "side": "over", "line": 65.5}
    nfl = P.relate("nfl", a, b)
    cfb = P.relate("cfb", a, b)
    assert nfl.measured is True and cfb.measured is False, (nfl, cfb)
    assert "2,844" in nfl.mechanism, nfl.mechanism
    assert "2,844" not in cfb.mechanism, cfb.mechanism
    assert "measured" not in cfb.mechanism.lower(), cfb.mechanism


def test_the_persisted_fit_is_scoped_by_the_sport_it_recorded():
    """Every stored fit has carried `sport` since it was first written —
    `corrfit.refresh` records `f.prior.sport` — and nothing read it
    back. An entry from before the field existed is left alone rather
    than guessed at."""
    corrfit._cache.clear()
    try:
        corrfit._cache[("x_pair", "nfl")] = {"r": 0.5, "n": 999, "sport": "nfl"}
        assert corrfit.measured("x_pair", "nfl")["n"] == 999
    finally:
        corrfit._cache.clear()
    state = {"y_pair": {"r": 0.5, "n": 9999, "sport": "nfl"},
             "z_pair": {"r": 0.5, "n": 9999}}
    real = corrfit._read_state
    corrfit._read_state = lambda: state
    try:
        corrfit._cache.clear()
        assert corrfit.measured("y_pair", "nfl") is not None
        assert corrfit.measured("y_pair", "cfb") is None, "NFL fit answered CFB"
        assert corrfit.measured("y_pair") is not None, "no sport asked, no filter"
        corrfit._cache.clear()
        assert corrfit.measured("z_pair", "cfb") is not None, \
            "an entry with no sport recorded predates the field"
    finally:
        corrfit._read_state = real
        corrfit._cache.clear()


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
