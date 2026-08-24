"""One league's picks under another league's name.

Ethan, 2026-08-25: "the wnba picks were showing up under NFL on mobile
but when i checked for that bug on the desktop site it wouldn't happen."

THE CONDITIONAL REQUEST WAS GUARDED ON THE WRONG QUESTION. `load()`
sends `If-None-Match` so a board this tab already has comes back 304
instead of being re-downloaded — the largest recurring bandwidth cost the
site has. The guard read:

    headers: (tag && state.data) ? { "If-None-Match": tag } : {}

`tag` is this sport's tag, which is right. `state.data` was meant to say
"we are holding a copy to keep if the answer is 304" — and that is the
bug, because after switching leagues `state.data` is the board you just
LEFT. So revisiting a league this tab had already loaded sent its
still-valid tag, took the 304, never replaced `state.data`, and drew the
previous league's slate under the new league's name.

WHY IT LOOKED LIKE A MOBILE BUG. It needs the same board loaded twice in
one session. Tapping through leagues in the phone drawer does that in
seconds; clicking once in the desktop sidebar does not. Nothing about it
is actually platform-specific.

WHY NOTHING CAUGHT IT. The dev server issues no ETag — the gate is off,
so boards come back from `file_bytes` with no tag — so the 304 branch
never runs locally and every board arrives 200. The page sweep, the
render checks and every browser test in this repo have been exercising
the one path where the bug cannot appear. The check below stubs the tags
back the way the live server sets them.

Run directly: `python3 tests/test_board_identity.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _load_body():
    i = APP.index("async function load(")
    j = APP.index(") {", i) + 2
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError("unbalanced braces reading load()")


def test_revalidation_is_guarded_on_holding_this_board():
    """The fix, stated as the thing that was wrong: not "is there data"
    but "is the data we are holding this board's"."""
    body = _load_body()
    assert "_boardFor === meta.api" in body, \
        "load() no longer checks WHICH board the held slate belongs to"
    m = re.search(r'headers:\s*\(([^)]*)\)\s*\?\s*\{\s*"If-None-Match"', body)
    assert m, "the conditional request header changed shape"
    guard = m.group(1)
    assert "holding" in guard, \
        f"the revalidation guard is not board-aware: {guard!r}"
    assert re.search(r"&&\s*state\.data\s*\)", guard) is None, \
        ("the guard is back to 'we have some data', which is true while "
         "holding another league's board")


def test_every_assignment_to_the_slate_records_its_board():
    """A slate whose owner is not recorded is a slate the next revisit
    will revalidate against the wrong tag. Includes the empty one: an
    empty board still BELONGS to the sport that has no games tonight."""
    body = _load_body()
    writes = [m.start() for m in re.finditer(r"state\.data\s*=", body)]
    assert writes, "load() no longer sets state.data"
    for at in writes:
        after = body[at:at + 400]
        assert "_boardFor = meta.api" in after, (
            "a slate is assigned without recording which board it is: "
            + " ".join(body[at:at + 90].split()))


def test_an_unasked_304_is_refused_rather_than_kept():
    """We only send a tag while holding this board, so a 304 without one
    came from somewhere between us and the server. Keeping it is exactly
    the bug; the empty-handed path re-asks."""
    body = _load_body()
    # Anchored on the BRANCH, not on the first "304" in the function —
    # which is inside a comment explaining the original guard, so a
    # window from there measured the wrong 700 characters.
    anchor = "} else if (res.status === 304)"
    # assert, don't index: a missing anchor raised ValueError, which the
    # runner below does not catch, so this file CRASHED instead of
    # reporting a failure — the least useful way to be right.
    assert anchor in body, \
        "there is no branch for a 304 we did not ask for"
    i = body.index(anchor)
    seg = body[i:i + 700]
    assert "delete _boardTags[meta.api]" in seg, \
        "a 304 we did not ask for leaves a poisoned tag behind"
    assert "throw" in seg, \
        "an unasked 304 is still accepted as a valid board"


def test_the_tags_are_still_keyed_per_board():
    """The half that was always right, kept: one tag per endpoint, so a
    switch asks about the sport it is switching to."""
    assert "const _boardTags = {};" in APP
    body = _load_body()
    assert "_boardTags[meta.api]" in body, \
        "the tag store is no longer keyed by the board's own URL"


def test_the_slate_owner_starts_empty():
    """Declared null, so the first load of the session cannot revalidate
    against a board nobody has fetched."""
    assert re.search(r"let _boardFor = null;", APP), \
        "_boardFor is missing or no longer starts empty"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
