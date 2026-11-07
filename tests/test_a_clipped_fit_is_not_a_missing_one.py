"""Measured-and-capped and never-measured both read 0.5. They are opposites.

Measured on the droplet, 2026-09-19, while chasing why the college board
publishes nothing:

    mlb  spread     shrink 0.5     n=16,520
    mlb  total      shrink 0.5     n=16,520
    mlb  moneyline  shrink 0.0     n= 1,113
    nfl  spread/total/moneyline    shrink 0.0
    cfb  spread 0.0218  total 0.1265  moneyline 0.0

`MAX_ADOPTED` is 0.5 and `betting.MARKET_SHRINK` — the fallback when
NOTHING has been measured — is also 0.5. So a market reading 0.5 is
either:

  * never measured, the board pricing on a guess. That is the condition
    that cost 7.64 units on twelve NFL rows in August 2026 (#73/#74);
  * measured on sixteen thousand games, where the model's disagreement
    with the close held up BETTER than the ceiling allows and
    `_adopted_shrink` clamped it down.

The first is the total absence of information. The second is the
strongest statement this module can make. They arrived at the same
number, `shrink_for` returned a bare float, and `note_for` said nothing
for either — its rule being "only speak when the measurement changed
something", which is right about a fit that LANDED on the prior and
wrong about one CLAMPED to it.

So the one case with the most to say was the one case that was silent,
and it read on the card exactly like a market nobody had looked at.
That is the failure shape this codebase keeps paying for, and
`gamebets.measured_shrink` carries a docstring about the adjacent
version of it ("THE TWO WAYS TO GET NONE ARE NOT THE SAME FACT").

The store has kept `slope` beside `shrink` all along. Nothing asked.

Run directly:
`python3 tests/test_a_clipped_fit_is_not_a_missing_one.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamecal as G                             # noqa: E402


def _store(entry):
    """Point `measured` at one fit, without touching the real store."""
    real = G.measured
    G.measured = lambda sport, market: entry
    return real


def _restore(real):
    G.measured = real


def _fit(shrink, slope, n=16520, hit=0.52):
    return {"shrink": shrink, "slope": slope, "n": n, "hit_rate": hit}


# --- telling the two apart ---------------------------------------------
def test_a_fit_clamped_by_the_ceiling_is_clipped():
    """The droplet's MLB spread: 16,520 games, the fit wanted 0.71 and
    the cap held it at 0.5."""
    real = _store(_fit(0.5, 0.71))
    try:
        assert G.clipped("mlb", "spread") is True
    finally:
        _restore(real)


def test_a_fit_that_landed_on_the_prior_is_not_clipped():
    """Slope and adopted agree — the measurement chose 0.5, the ceiling
    did not impose it."""
    real = _store(_fit(0.5, 0.5))
    try:
        assert G.clipped("mlb", "spread") is False
    finally:
        _restore(real)


def test_never_measured_is_not_clipped_either():
    """THE CASE THIS EXISTS TO SEPARATE. No fit at all reaches 0.5 by
    the `MARKET_SHRINK` fallback, and calling that "clipped" would swap
    one conflation for another."""
    real = _store(None)
    try:
        assert G.clipped("mlb", "spread") is False
    finally:
        _restore(real)


def test_a_store_missing_the_slope_does_not_raise_onto_the_pricing_path():
    """`measured` is read for every game bet on every board. An older
    entry written before `slope` was persisted must cost the note, not
    the board."""
    for bad in ({"shrink": 0.5, "n": 999}, {"shrink": 0.5, "slope": None},
                {"shrink": "x", "slope": 0.7}, {}):
        real = _store(bad)
        try:
            assert G.clipped("mlb", "spread") is False, bad
        finally:
            _restore(real)


def test_the_ceiling_is_the_one_in_force_not_a_second_copy():
    """A test asserting 0.5 would keep passing if the cap moved."""
    real = _store(_fit(G.MAX_ADOPTED, G.MAX_ADOPTED + 0.2))
    try:
        assert G.clipped("mlb", "spread") is True
    finally:
        _restore(real)


# --- and the card says so ----------------------------------------------
def test_a_clipped_fit_now_speaks():
    """It was the one case with the most to say and the only one that
    said nothing."""
    real = _store(_fit(0.5, 0.71))
    try:
        note = G.note_for("mlb", "spread")
    finally:
        _restore(real)
    assert note, "a clipped fit is still silent"
    assert "16,520" in note or "16520" in note, note
    assert "cap" in note, "the note does not say what limited the price"
    assert "held up better" in note, note


def test_a_fit_that_merely_landed_on_the_prior_stays_quiet():
    """The original rule, unchanged: a measurement that changed nothing
    has nothing to add to a card, and this must not turn into a line on
    every card in the site."""
    real = _store(_fit(0.5, 0.5))
    try:
        assert G.note_for("mlb", "spread") is None
    finally:
        _restore(real)


def test_the_no_information_note_is_untouched():
    """Football's markets sit at 0.0 and their wording is what a reader
    already sees; this change must not have moved it."""
    real = _store(_fit(0.0, 0.0, n=897))
    try:
        note = G.note_for("nfl", "moneyline")
    finally:
        _restore(real)
    assert note and "carried no information" in note, note
    assert "Priced at the market until that changes" in note, note


def test_the_partial_note_is_untouched():
    real = _store(_fit(0.1265, 0.1265, n=3142))
    try:
        note = G.note_for("cfb", "total")
    finally:
        _restore(real)
    assert note and "13% of a disagreement" in note, note
    # THE PHRASE ALL THREE NOTES SHARE, pinned because the number alone
    # did not pin it: a mutation that cut "on our own record" left "13%
    # of a disagreement" intact and passed. What makes these lines
    # trustworthy to a reader is that they say whose record it is.
    assert "Measured on our own record" in note, note


def test_every_note_says_whose_record_it_is():
    """One family, one opening. A card that says "Measured" without
    saying measured against WHAT is the kind of authority this site does
    not get to borrow."""
    for shrink, slope, n in ((0.0, 0.0, 897), (0.1265, 0.1265, 3142),
                             (0.5, 0.71, 16520)):
        real = _store(_fit(shrink, slope, n=n))
        try:
            note = G.note_for("mlb", "spread")
        finally:
            _restore(real)
        assert note and note.startswith("Measured on our own record:"), \
            (shrink, note)


def test_an_unmeasured_market_still_says_nothing_here():
    """Deliberate and unchanged. Whether a board should announce that it
    is pricing on the 0.5 guess is a product decision that belongs with
    `gamebets._calibration_note`, which already owns the fault case —
    not a thing to bolt on while separating two other states."""
    real = _store(None)
    try:
        assert G.note_for("mlb", "spread") is None
    finally:
        _restore(real)


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
