"""The game page draws BOTH books, and never adds them together.

Ethan, 2026-09-09, on the Week 1 opener's game page: "when you click on a
game on the reccomended page and u scroll down to the reccomended props,
is that showing just edge bets? if so, we need to show both edge bets and
most likley bets."

It was showing just the edge book. `renderGamePage` read
`recommendations`, `game_bets` and `long_shots` — all one book — and
never touched `most_likely`, so NE @ SEA rendered with one prop on it
while two of its players sat on the Most Likely board with nothing on
screen to say so.

The other half of this is the half that could rot quietly: the two books
do not share a record (tests/test_books_never_bleed.py), so the
likelihood rows must reach the page WITHOUT reaching the headline
"Recommended" count. Source-level pins, in the same style as the other
game-page tests.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(HERE, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    # `async function foo` — back up over the keyword or the slice starts
    # mid-declaration and the body no longer parses as what it is.
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    j = js.index("\nfunction ", i + 1)
    return js[i:j]


def _nocomments(src):
    """Comments out, THEN grep.

    A negative or ordering assertion that greps a function's text is
    satisfied by a comment quoting the very string it bans — and the
    comment above this feature quotes both "Recommended" and "likelies"
    while explaining why they must stay apart. Ask the code.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def test_the_game_page_reads_the_likelihood_board():
    page = _nocomments(_fn(_js(), "renderGamePage"))
    assert "state.data.most_likely" in page, \
        "the game page never reads the Most Likely board"
    # Through the SAME gate the Most Likely page applies, so a row refused
    # there cannot surface here instead.
    assert "showableLikelyRow" in page, \
        "likelihood rows reach this page without the board's own gate"
    # And scoped to THIS game, not the whole slate.
    i = page.index("state.data.most_likely")
    assert "propInGame" in page[i:i + 400], \
        "the whole slate's likelihood rows are drawn on one game's page"


def test_those_rows_are_drawn_with_the_board_s_own_card():
    page = _nocomments(_fn(_js(), "renderGamePage"))
    assert "likelies.map(likelyCard)" in page, \
        "the rows are computed and never rendered"
    assert "Most likely to hit" in page, "the section has no heading"


def test_the_headline_recommended_count_is_the_edge_book_only():
    """The books do not share a record, and this tile is where they would
    first be quietly added together."""
    page = _nocomments(_fn(_js(), "renderGamePage"))
    m = re.search(r'<div class="k">Recommended</div><div class="v">\$\{([^}]*)\}',
                  page)
    assert m, "the Recommended tile moved; re-anchor this test"
    expr = m.group(1)
    assert "props.filter" in expr and "bets.filter" in expr, \
        f"the edge book left the Recommended tile: {expr}"
    assert "likel" not in expr.lower(), \
        f"likelihood rows are being counted as Recommended: {expr}"


def test_the_likelihood_rows_get_their_own_labelled_tile():
    page = _nocomments(_fn(_js(), "renderGamePage"))
    m = re.search(r'<div class="k">Most likely</div><div class="v">\$\{([^}]*)\}',
                  page)
    assert m, "no Most likely tile on the game page"
    assert "likelies.length" in m.group(1)
    # The label has to say it is a separate book, the way Long shots does
    # — a bare count beside "Recommended" reads as more of the same thing.
    i = page.index('<div class="k">Most likely</div>')
    assert "own book" in page[i:i + 260], \
        "the tile does not say these are tracked separately"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
