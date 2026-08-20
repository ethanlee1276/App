"""A pick whose price moved is still a pick we made.

Ethan, 2026-08-20: "bets that we recommended but doesn't pass the bar
anymore should still be shown in the green recommended box with the rest
of the props, we should just make a note on the prop in the yellow
lettering that the price has changed since we took the pick."

They used to sit in a separate orange card below the picks, which asked a
reader to look in two places for one night's book and made an open
position read as a footnote. One list now.

WHAT MUST NOT BLUR, and it is why the row is shaped differently rather
than simply appended. Two different sentences share this box:

    "bet this, at tonight's number"                  — the ranked picks
    "you already hold this; the number has moved
     and it would not qualify today"                 — a riding row

So a riding row takes no rank (the numbered list stays over things you
can act on), wears RIDING where a grade would be, and carries the price
move in warn colour. THE HEADLINE COUNT STILL COUNTS ONLY THE ACTIONABLE
PICKS and states the riding count separately — "3 picks tonight" when one
of them is un-bettable is exactly the small lie this page exists not to
tell.

Measured on a live render: header reads "13 picks tonight — this is the
whole list. 1 more is riding from an earlier pull at a price that no
longer qualifies — marked below, and not part of that count", one
`.grade.riding` chip, note colour rgb(247,157,0) = --warn, and zero
"Riding from earlier pulls" cards left on the page.

Run directly: `python3 tests/test_ridingrow.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
FLAT = " ".join(APP.split())


def _no_comments(src: str) -> str:
    """Source with comments blanked — the same split test_typography uses.

    The retirement note for the old card names it, which is the point of a
    retirement note. A test that cannot tell copy from a comment fails on
    the record of the fix.
    """
    out = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", out)


def test_the_separate_orange_card_is_gone():
    """Two boxes for one night's book is the thing being fixed."""
    copy = _no_comments(APP)
    assert "Riding from earlier pulls" not in copy, \
        "the separate riding card is back — its rows belong in the picks box"
    assert "riddenBlock" not in copy
    # …and the comment explaining why it went is worth keeping.
    assert "Riding from earlier pulls" in APP, \
        "the note recording why the card was retired was deleted"


def test_the_riding_rows_render_inside_the_picks_box():
    assert "${ridden.map(ridingRow).join(\"\")}" in APP, \
        "riding rows are no longer drawn in the recommended box"
    i = APP.index("${picks.map(pickRow).join(\"\")}")
    j = APP.index("${ridden.map(ridingRow).join(\"\")}", i)
    assert j - i < 200, "the riding rows drifted out of the picks card"


def test_the_note_is_in_warn_colour():
    """Ethan asked for it in yellow, and the reason is functional: it has
    to be readable as a different instruction at a glance."""
    i = CSS.index(".pick-moved {")
    block = CSS[i:CSS.index("}", i)]
    assert "color: var(--warn)" in block, block


def test_the_note_says_the_price_changed_since_we_took_it():
    assert "The price has changed since we took this pick" in FLAT, \
        "the note no longer says what actually happened"
    assert "don’t add more" in FLAT, \
        "the note stopped telling the reader not to buy at the new number"


def test_the_row_shows_both_prices():
    """"The price changed" without the two numbers is a claim the reader
    cannot check, on a page whose whole argument is checkability."""
    fn = FLAT[FLAT.index("const ridingRow ="):]
    fn = fn[:fn.index("const pickRow =")]
    assert "american(b.odds)" in fn and "american(cur.odds)" in fn, \
        "the placed price and the current price are no longer both shown"
    assert "no live quote" in fn, \
        "a market with no current quote has no honest branch any more"


def test_a_riding_row_is_not_ranked_among_the_picks():
    """The numbered list means "act on these". An un-bettable position
    holding rank 3 would read as an instruction."""
    fn = FLAT[FLAT.index("const ridingRow ="):]
    fn = fn[:fn.index("const pickRow =")]
    assert "${i + 1}" not in fn, "riding rows joined the ranked list"
    assert "grade riding" in fn, "the RIDING chip is gone"


def test_the_headline_count_excludes_the_riding_bets():
    """THE HONESTY HINGE. `picks.length` is the actionable count and must
    stay that; the riding count is stated separately."""
    i = APP.index("pick${picks.length === 1 ? \"\" : \"s\"} tonight — this is the whole list.")
    head = " ".join(APP[i:i + 900].split())
    assert "ridden.length" in head, \
        "the header no longer mentions the riding bets at all"
    assert "not part of that count" in head, \
        "the header no longer says the riding bets are excluded from the count"
    # and the count itself is still picks.length, not a sum
    assert "picks.length + ridden.length" not in APP, \
        "the headline count now includes un-bettable positions"


def test_a_night_with_no_new_picks_still_shows_what_is_held():
    """The evening a reader most needs to see an open position is the
    evening nothing new qualified — which is the branch that would have
    dropped them."""
    i = APP.index("No qualifying plays at current numbers.")
    branch = " ".join(APP[i:i + 2600].split())
    assert "ridden.map(ridingRow)" in branch, \
        "the empty-slate branch forgets the riding bets"
    assert "still riding" in branch


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
