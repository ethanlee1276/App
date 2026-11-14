"""Slice a source file by its own structure, not by a character count.

Dozens of tests here scope a search with a fixed window:

    i = APP.index("function gameBetCard(")
    assert "gameBetAttrs(r)" in APP[i:i + 3000]

The count is a guess about how long a function will stay, and the guess
expires. That exact line failed on 2026-08-27 with correct code, for the
third time in two weeks — the 08-17 chart pass and an 08-26 storage
slice were the other two. Every time the fix was to make the number
bigger, which resets the clock and teaches the next reader that a red
suite means "re-anchor" rather than "investigate". That is the expensive
part: a safety net you have learned to overrule.

The scope those tests actually want is a BLOCK — this function, this CSS
rule — and a block ends where its brace closes. That is knowable, so
`block` finds it.

WHY NOT JUST WIDEN EVERY WINDOW. Because the window is doing real work.
`assert "x" in APP[i:i + 200]` says "x appears NEAR here", and widening
it to the whole file makes the assertion vacuous — a test that cannot
fail is worse than one that fails for the wrong reason. Slicing to the
block keeps the scope honest AND stops it expiring.

Not a test module: `run_tests.py` collects `test_*.py`, so this is
imported, never collected.
"""

from __future__ import annotations

#: Brace-like pairs this understands. CSS rules and JS blocks both use
#: braces; the parenthesised form is here for an arrow function body.
PAIRS = {"{": "}", "(": ")", "[": "]"}


def block(src: str, anchor: str, opener: str = "{",
          start: int = 0) -> str:
    """From ``anchor`` to the close of the first ``opener`` after it.

    Brace-counting, so a nested block inside does not end the slice
    early — which is the whole reason this is not a `str.index("}")`.
    Strings and comments are NOT parsed: a lone brace inside a string
    literal would miscount. That is a real limit and an acceptable one
    here, because these callers are slicing real code blocks, and a
    miscount fails loudly (the slice ends in the wrong place and the
    assertion breaks) rather than quietly widening.

    Raises ValueError when the anchor is missing — the same failure a
    bare `.index()` gives, and the one that means "this test's anchor
    moved", which IS a real finding.
    """
    at = src.index(anchor, start)
    closer = PAIRS[opener]
    first = src.index(opener, at)
    depth = 0
    for pos in range(first, len(src)):
        ch = src[pos]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return src[at:pos + 1]
    return src[at:]


def function(src: str, anchor: str, start: int = 0) -> str:
    """A JS function's BODY, skipping its parameter list first.

    `block` alone gets this wrong, and did on its first real use:
    `function liveCardHTML({ sport, g, bets })` destructures its
    parameters, so the first `{` after the name opens the PARAMETER
    list, closes forty characters later, and the slice stops before the
    body starts. It failed loudly rather than quietly widening, which is
    the behaviour that made it findable in one run — but the right
    answer is to skip the parentheses and take the brace after them.

    Handles a default value containing braces, and an arrow function
    whose parameters are parenthesised, for the same reason.
    """
    at = src.index(anchor, start)
    first_brace = src.find("{", at)
    open_paren = src.find("(", at)
    # NO PARAMETER LIST TO SKIP when there is no paren at all, or when
    # the next paren comes after the block already opened — `const f = {`
    # has both shapes, and skipping to a paren somewhere later in the
    # file would slice a block that is not this one.
    if open_paren < 0 or first_brace < 0 or open_paren > first_brace:
        return block(src, anchor, start=start)
    depth = 0
    close_paren = None
    for pos in range(open_paren, len(src)):
        if src[pos] == "(":
            depth += 1
        elif src[pos] == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    if close_paren is None:
        return block(src, anchor, start=start)
    brace = src.find("{", close_paren)
    if brace < 0:
        return src[at:close_paren + 1]
    return src[at:brace + len(block(src, "{", start=brace))]


def until(src: str, anchor: str, stop: str, start: int = 0) -> str:
    """From ``anchor`` to the next ``stop`` — for scopes without braces.

    A section of a file that ends at the next heading, a run of lines
    that ends at a blank one. Falls back to the rest of the file when
    ``stop`` never appears, because "there is nothing after this" is a
    legitimate shape and not an error.
    """
    at = src.index(anchor, start)
    try:
        end = src.index(stop, at + len(anchor))
    except ValueError:
        return src[at:]
    return src[at:end]


def lines_after(src: str, anchor: str, count: int, start: int = 0) -> str:
    """``anchor`` plus the next ``count`` lines — an honest proximity check.

    For the assertions that really do mean "near here" rather than
    "inside this block". Counted in LINES rather than characters because
    a line is a unit a reader can check against the source; 200
    characters is not.
    """
    at = src.index(anchor, start)
    tail = src[at:]
    return "\n".join(tail.splitlines()[:count + 1])
