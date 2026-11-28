"""The Pick of the Day zone never goes blank without saying why.

Ethan, 2026-09-16: *"mlb isn't showing a pick of the day"*.

TWO HALVES OF ONE HOLE, and they hid each other.

`potd.attach` promises in its own docstring that a failure "lands in the
JSON as `pick_of_the_day_error`, where the page can see it, rather than
only in a log the launcher swallows". On the failure path it set that key
and DID NOT set `pick_of_the_day`.

`renderPickOfTheDay` then read:

    if (!got || typeof got !== "object") { host.innerHTML = ""; return; }
    if (d.pick_of_the_day_error) { …draw the error… }

— so a board with an error and no card returned at the first line, and
the error branch below it could never run. **The one state that branch
was written for was the one state it could not draw.** The most valuable
slot on the page went blank and nothing anywhere explained it.

Each half looks correct reading the other file. That is what makes this
worth a file of its own rather than a line in an existing one.

WHAT IS NOT CHANGED, deliberately: a board that carries no
`pick_of_the_day` AND no error still renders nothing. That is a board
built before the feature shipped, or a sport with no card, and an empty
frame there would cost a fold on a phone for no information — Ethan's
2026-09-05 call, pinned in tests/test_board_order.py. The fix is about
the ERROR case, which is a different fact.

Run through the gate's env.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


#: The fields `potd.build` actually returns. Read off the real function
#: rather than typed from memory — an error card missing one of these is
#: a card some reader downstream will crash on or silently skip.
BUILD_KEYS = sorted(potd.build([], "mlb", "2026-09-16"))


def _blows_up(result):
    """`attach` with the selector itself failing.

    The selector is replaced rather than fed a bad board, because
    `build` is deliberately hard to break — it survives non-rows, empty
    boards and missing dates, which is why feeding it rubbish measured
    nothing. What is under test here is `attach`'s FAILURE PATH, and the
    honest way to reach it is to make the thing it calls fail.
    """
    real = potd.build

    def boom(pool, *a, **k):
        # FAILS ON THE REAL POOL ONLY, which is the realistic shape: what
        # breaks a selector is the rows it was handed. `attach` builds
        # its error card by calling `build` again on an EMPTY pool, so a
        # stub that raised unconditionally would exercise the fallback
        # branch instead of the one under test — and did, until this
        # signature.
        if pool:
            raise RuntimeError("the board stage left no rows")
        return real(pool, *a, **k)

    potd.build = boom
    try:
        return potd.attach(result, "mlb")
    finally:
        potd.build = real


# --- the build always leaves a card ------------------------------------------
def test_a_selector_that_fails_still_writes_a_card():
    """THE HALF IN PYTHON. A missing key is the one shape the page
    cannot explain, so the failure path must not produce one."""
    # `most_likely` is not a list of dicts, which `build` cannot select
    # over — the realistic shape of a board assembled by a broken stage.
    result = {"date": "2026-09-16", "most_likely": [{"kind": "game"}]}
    line = _blows_up(result)
    assert "error" in line, line
    assert "pick_of_the_day" in result, \
        "the failure path left no card — the page cannot explain a missing key"
    got = result["pick_of_the_day"]
    assert got.get("pick") is None
    assert got.get("error"), got
    assert result.get("pick_of_the_day_error"), result.keys()


def test_the_error_card_carries_the_fields_every_reader_expects():
    """A bare {} would satisfy the test above and break `relock_potd`,
    which keys the lock on `sport`, and `verdict`, which the card
    renders. The shape is `build`'s, not an invention."""
    result = {"date": "2026-09-16", "most_likely": [{"kind": "game"}]}
    _blows_up(result)
    got = result["pick_of_the_day"]
    missing = [k for k in BUILD_KEYS if k not in got]
    assert not missing, (
        f"the error card is missing fields a real card carries: {missing}. "
        f"A bare dict satisfies 'the key exists' and still breaks every "
        f"reader downstream.")
    assert got["sport"] == "mlb", got["sport"]
    assert isinstance(got["verdict"], dict)
    # …and it is honestly labelled, so nothing mistakes it for a real
    # answer: there is no pick and the error travels with the card.
    assert got["pick"] is None
    assert got["error"] == "the board stage left no rows", got["error"]


def test_a_totally_broken_selector_still_leaves_a_renderable_card():
    """The template is obtained by CALLING `build` on an empty pool, so
    the obvious question is what happens when `build` is the thing that
    is broken. A minimal card still beats a missing key — the page can
    draw "no pick, here is why" from these four fields alone."""
    result = {"date": "2026-09-16", "most_likely": []}
    real = potd.build

    def boom(*a, **k):
        raise RuntimeError("build is gone entirely")

    potd.build = boom
    try:
        potd.attach(result, "mlb")
    finally:
        potd.build = real
    got = result["pick_of_the_day"]
    for key in ("sport", "date", "pick", "census", "note", "verdict"):
        assert key in got, f"even the fallback card has no {key!r}"
    assert got["pick"] is None
    assert "build is gone entirely" in got["note"]


def test_the_note_says_what_went_wrong_in_words():
    """Not a traceback and not silence. A reader of the card gets the
    sentence; `pick_of_the_day_error` keeps the raw text for a report."""
    result = {"date": "2026-09-16", "most_likely": [{"kind": "game"}]}
    _blows_up(result)
    note = result["pick_of_the_day"]["note"]
    assert "could not run" in note, note


def test_a_healthy_board_is_untouched_by_any_of_this():
    """The guard on the guard. None of the above may fire on a build
    that worked — an error card on a good day is worse than none."""
    result = {"date": "2026-09-16", "most_likely": []}
    potd.attach(result, "mlb")
    assert "pick_of_the_day" in result
    assert not result.get("pick_of_the_day_error"), result.get(
        "pick_of_the_day_error")
    assert "error" not in result["pick_of_the_day"], result["pick_of_the_day"]


# --- the page asks the error first -------------------------------------------
def _render_body():
    i = JS.index("async function renderPickOfTheDay()")
    return JS[i:i + 2500]


def test_the_page_asks_the_error_before_it_bails_on_a_missing_card():
    """THE HALF IN JAVASCRIPT, and the one that made the other
    invisible. Asked by position, because that IS the bug — both lines
    were present the whole time and in the wrong order."""
    body = _render_body()
    err = body.index("pick_of_the_day_error")
    bail = body.index('host.innerHTML = ""')
    assert err < bail, (
        "the renderer still bails on a missing card before it looks at "
        "the error — the error branch is unreachable in the one state it "
        "exists for")


def test_a_board_with_neither_still_draws_nothing():
    """NOT CHANGED, and it must not be. A board from before the feature
    shipped costs no fold — Ethan's 2026-09-05 call, pinned in
    tests/test_board_order.py."""
    body = _render_body()
    assert 'host.innerHTML = ""' in body, \
        "the empty-board bail is gone; an empty frame now costs a fold"
    assert "!got || typeof got !== \"object\"" in body


def test_the_error_is_shown_to_the_reader_not_just_logged():
    body = _render_body()
    i = body.index("pick_of_the_day_error")
    block = body[i:i + 400]
    assert "host.innerHTML" in block, "the error is read and never drawn"
    assert "escapeHtml" in block, "the error text is injected unescaped"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
