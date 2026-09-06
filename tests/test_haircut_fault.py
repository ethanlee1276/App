"""A store that would not open priced the board on the guess it replaced.

Found by sweeping for the shape that produced six separate bugs on
2026-09-03 and 09-04: a failure that arrives looking like an ordinary,
expected, empty result.

`gamebets.temper` asked `gamecal.shrink_for` for the measured market
haircut and swallowed any exception into `shrink = None`. But None was
already the answer for something else entirely — nothing MEASURED for
this market yet — and `betting.temper_edge` turns None into
`MARKET_SHRINK`, 0.5. So two different facts arrived at the same place:

    nothing measured yet   -> 0.5   ordinary, designed, correct
    the store RAISED       -> 0.5   a bug, and indistinguishable

THAT FALLBACK HAS ALREADY COST MONEY. `shrink_in_force`'s own docstring
records it: twelve NFL game bets open from August 8-12 2026, 7.64 units
staked, priced on the 0.5 guess before gamecal had measured anything,
three separate investigations to establish why, and voided (#73, #74).
A board that reverts to that same guess because a FILE will not open,
and says nothing about it, is that outage again with the cause hidden.

`shrink_in_force` made it worse in a quiet way. It exists so a row
remembers what priced it — "a row recording its correction can be
un-corrected and one that does not, cannot" — and it recorded None for
both causes too, so the field built to make this diagnosable could not
tell them apart either.

PRICING IS UNCHANGED. A fault still falls back to 0.5, because refusing
to price the board would be worse than pricing it on a stale number. The
change is that the fault now travels with the card, in the same reasons
list as every other piece of evidence — the rule this codebase applies
everywhere else, and did not apply here.

Run directly: `python3 tests/test_haircut_fault.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamebets                                  # noqa: E402
from engine.betting import MARKET_SHRINK, temper_edge        # noqa: E402


class _Store:
    """Stand in for `engine.gamecal` with a chosen behaviour."""

    def __init__(self, shrink=None, raises=None, note=""):
        self._shrink, self._raises, self._note = shrink, raises, note

    def shrink_for(self, sport, market):
        if self._raises:
            raise self._raises
        return self._shrink

    def note_for(self, sport, market):
        return self._note


class _Swap:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        import engine
        self.real = sys.modules.get("engine.gamecal")
        sys.modules["engine.gamecal"] = self.store
        return self

    def __exit__(self, *_):
        if self.real is None:
            sys.modules.pop("engine.gamecal", None)
        else:
            sys.modules["engine.gamecal"] = self.real


# --- the two Nones ------------------------------------------------------------
def test_nothing_measured_and_a_broken_store_are_different_answers():
    """THE DEFECT. Both used to be `None` and nothing downstream could
    ask which one it was."""
    with _Swap(_Store(shrink=None)):
        val, err = gamebets.measured_shrink("nfl", "spread")
    assert val is None and err is None, (val, err)

    with _Swap(_Store(raises=RuntimeError("gamecal.json is corrupt"))):
        val, err = gamebets.measured_shrink("nfl", "spread")
    assert val is None, val
    assert isinstance(err, RuntimeError), err


def test_a_measured_haircut_comes_back_untouched():
    with _Swap(_Store(shrink=0.18)):
        assert gamebets.measured_shrink("nfl", "spread") == (0.18, None)


def test_an_unasked_market_is_not_a_fault():
    """No sport or no market is a caller with nothing to ask, not a
    broken store — it must not raise a warning onto a card."""
    assert gamebets.measured_shrink("", "spread") == (None, None)
    assert gamebets.measured_shrink("nfl", "") == (None, None)


# --- what the fallback actually is --------------------------------------------
def test_the_silent_fallback_really_is_the_guess_that_was_replaced():
    """The premise, executed. If `temper_edge`'s default ever stops being
    the 0.5 guess this test should be the one that notices."""
    assert MARKET_SHRINK == 0.5
    at_none = temper_edge(0.70, 0.50, book="", allow_synthetic_line=True,
                          shrink=None)[0]
    at_half = temper_edge(0.70, 0.50, book="", allow_synthetic_line=True,
                          shrink=0.5)[0]
    assert at_none == at_half, (at_none, at_half)


def test_a_broken_store_still_prices_the_board():
    """Never let a calibration cost a board. The fault is reported, not
    raised — a refused board is worse than a stale number."""
    with _Swap(_Store(raises=RuntimeError("boom"))):
        hit, edge, credible = gamebets.temper(0.70, 0.50, "nfl", "spread")
    assert 0.0 < hit < 1.0, hit
    assert edge == hit - 0.50


# --- and it reaches the card --------------------------------------------------
def test_the_fault_is_written_onto_the_card():
    """THE POINT. The reason goes where every other piece of evidence on
    this card goes, because the card is what anyone actually reads."""
    with _Swap(_Store(raises=RuntimeError("gamecal.json is corrupt"))):
        notes = gamebets._calibration_note("nfl", "spread")
    joined = " ".join(notes)
    assert notes, "a broken haircut store left the card saying nothing"
    assert "could not be read" in joined, joined
    assert "0.5 fallback" in joined, joined
    assert "RuntimeError" in joined, "the card does not say what failed"


def test_a_healthy_store_says_nothing_about_faults():
    """A warning that appears on a working board is a warning nobody
    reads on a broken one."""
    with _Swap(_Store(shrink=0.18, note="haircut measured at 0.18")):
        notes = gamebets._calibration_note("nfl", "spread")
    joined = " ".join(notes)
    assert "could not be read" not in joined, joined
    assert "haircut measured at 0.18" in joined, joined


def test_nothing_measured_yet_is_not_reported_as_a_fault():
    """The ordinary early-season state. It has its own note from
    `gamecal`; it must not also raise an alarm."""
    with _Swap(_Store(shrink=None, note="no haircut measured yet")):
        joined = " ".join(gamebets._calibration_note("nfl", "spread"))
    assert "could not be read" not in joined, joined


def test_the_row_still_records_what_priced_it():
    """`shrink_in_force` is the field that lets a row be re-judged when
    the fit moves. Routing it through the pair must not change what it
    returns."""
    with _Swap(_Store(shrink=0.18)):
        assert gamebets.shrink_in_force("nfl", "spread") == 0.18
    with _Swap(_Store(shrink=None)):
        assert gamebets.shrink_in_force("nfl", "spread") is None
    with _Swap(_Store(raises=RuntimeError("boom"))):
        assert gamebets.shrink_in_force("nfl", "spread") is None


def test_one_reader_of_the_store_not_three():
    """`temper`, `_calibration_note` and `shrink_in_force` all needed the
    same number. Three copies of the try/except is three chances for one
    of them to keep swallowing."""
    import inspect
    src = inspect.getsource(gamebets)
    assert src.count("from .gamecal import shrink_for") == 1, \
        "the store is read from more than one place again"
    for fn in ("temper", "_calibration_note", "shrink_in_force"):
        body = inspect.getsource(getattr(gamebets, fn))
        assert "measured_shrink(" in body, f"{fn} does not share the reader"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
