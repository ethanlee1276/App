"""The gate funnel appears once, not twice.

Ethan, 2026-08-14, on an empty MLB board: "we are showing 'where props
died' twice."

TWO INDEPENDENT BLOCKS DREW IT and on the one night that matters — the
night nothing is recommended — both fired:

  * the Best Bets panel's "No qualifying plays at current numbers" card,
    high on the page;
  * the board's own empty message a scroll below it.

Same table, same numbers, twice on one screen. Two copies of an
explanation do not explain twice as well; they read as a rendering fault
and cost the reader time working out whether the second one is different.

WHICH ONE SURVIVES IS A CHOICE, NOT A RACE. The funnel answers "why is
this list blank", so it stays with the list, beside the sliders its own
copy tells you to loosen. The Best Bets card keeps its own sentence,
which stands without a table under it.

A first-come-wins flag was the other way to do it and would have been
worse: `renderBestBets` is async, so which block won would change
between refreshes and the table would appear to wander up and down the
page.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _calls():
    """Every place the funnel is actually emitted, excluding its own
    definition."""
    return [m.start() for m in re.finditer(r"\$\{censusFunnelHTML\(\)\}", APP)]


def test_the_funnel_is_emitted_from_exactly_two_places():
    """One is the board's empty state; the other is a COLLAPSED
    disclosure that only exists when there ARE picks, so the two can
    never be open on the same screen. A third call site is how the
    duplicate came back."""
    assert len(_calls()) == 2, f"{len(_calls())} call sites — one too many"


def test_the_best_bets_empty_card_no_longer_repeats_it():
    """The exact block from the screenshot: the card that says "No
    qualifying plays at current numbers" used to print the whole funnel
    underneath, a scroll above the board printing it again."""
    i = APP.index("No qualifying plays at current numbers.")
    card = APP[i:i + 2200]
    assert "${censusFunnelHTML()}" not in card, \
        "the Best Bets empty card is drawing the funnel again"
    # And it still explains itself in words.
    assert "Loosening the\n           sliders shows what was held and why" in card


def test_the_board_keeps_it():
    """It is the answer to "why is this list blank" and the list is
    here."""
    # THE FUNNEL'S POSITION, not the markup around it. This pinned
    # `<p class="loading">${msg}</p>` — the empty board wore the
    # loading treatment until the empty-state pass on 2026-08-23 gave
    # it the slate it deserved. What this test is about is that the
    # funnel follows the empty message, whatever that message is set
    # in.
    i = APP.index("${censusFunnelHTML()}`;")
    block = APP[i - 800:i]
    assert 'class="empty-slate"' in block, "the empty board lost its slate"
    assert "msgTitle" in block, "the funnel drifted off the empty branch"


def test_the_survivor_is_chosen_statically_not_by_a_flag():
    """`renderBestBets` is async. A "first caller wins" guard would make
    the funnel's position depend on which fetch resolved first, so it
    would move between refreshes — a worse bug than the one being
    fixed, and much harder to see."""
    fn = APP[APP.index("function censusFunnelHTML()"):]
    fn = fn[:fn.index("\n}\n")]
    # CODE ONLY. The scan used to read the whole function body, which
    # meant any DISPLAY STRING containing one of these words failed it —
    # "game already started" is a gate's own label, not a guard. Quoted
    # and templated text comes out first so the check still catches the
    # thing it was written for (a module-scoped draw-once flag) and
    # stops catching English.
    import re
    code = re.sub(r"`[^`]*`|\"[^\"]*\"|'[^']*'", "", fn)
    code = re.sub(r"//[^\n]*", "", code)
    for word in ("_drawn", "once", "already"):
        assert not re.search(rf"\b{word}\b", code), \
            f"the funnel is self-gating on `{word}`"


def test_the_disclosure_is_still_collapsed():
    """The second call site is inside a <details>. If it ever renders
    open, a night with a game bet and no props shows the table twice
    again — once expanded here, once on the empty board."""
    i = APP.index("where the other props died")
    block = APP[max(0, i - 300):i + 200]
    assert "<details" in block
    assert "open" not in block.split("<details")[1].split(">")[0], \
        "the disclosure ships expanded"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
