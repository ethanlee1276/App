"""The header came apart in two ways, at opposite ends of the width range.

Reported as one thing — "this area is all bugged out and also is taking up
WAY too much space" — and measured as two independent faults.

**At 1800px and up the top bar did not wrap at all.** `flex-wrap: wrap`
lived in `@media (max-width: 1799px)`, while the two-row layout in the
`min-width: 761px` block asks for `.brand { flex: 1 0 100% }`. A 100%-wide
item on a nowrap row cannot take a line of its own — it just refuses to
shrink and crushes its siblings. Measured at 1800: the switcher wrapped to
FOUR rows inside a squeezed brand, the page nav overflowed its own box by
274px and printed on top of the running-ROI line and the status chips, and
the header stood at 263px. Every width below 1800 was fine, which is
exactly why it survived: the bug only appears on a monitor bigger than the
one the layout was designed on.

**Below 1248px the switcher wrapped through the middle of a group.** With
`.sport-group { display: contents }` all eleven buttons are direct children
of the switcher, so a break can fall between any two of them. Measured on
the same build: the markets pair split across two rows at 960px, and the
record pair at 1100, 820 and 768. The separator hairline then sits on
whichever button happens to start row two — so the one mark that says "the
axis changed here" lands somewhere it does not mean.

Measured header height, before -> after, on a return visit (the state the
site is actually used in — `.brand-home` is hidden by the compact
masthead):

    1800  263 -> 196      960  279 -> 222
    1440  196 -> 196      900  254 -> 197
    1280  232 -> 232      820  254 -> 248
    1024  229 -> 223      768  254 -> 248

Run directly: `python3 tests/test_headerwrap.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8") as fh:
    CSS = fh.read()

#: The switcher override's own media query. Spelled once because two tests
#: below care about WHERE it is, not only that it exists.
#:
#: The trailing brace is load-bearing. Without it these strings also match
#: the same query quoted inside a COMMENT — the desktop block carries one
#: ("Folded into THIS block rather than opening a second @media
#: (min-width: 761px)") — and the brace scan then starts in the middle of
#: a comment and balances the wrong braces. The first cut of this file did
#: exactly that and failed a rule that was present and correct.
NARROW = "@media (min-width: 761px) and (max-width: 1247px) {"
DESKTOP = "@media (min-width: 761px) {"


def _block(css, start):
    """The `{...}` body that starts at or after `start`, brace-balanced."""
    depth, out, began = 0, [], False
    for ch in css[start:]:
        if ch == "{":
            depth += 1
            began = True
        elif ch == "}":
            depth -= 1
            if began and depth == 0:
                out.append(ch)
                break
        out.append(ch)
    return "".join(out)


# --- the wide-monitor fault --------------------------------------------------
def test_the_top_bar_wraps_in_the_base_rule():
    """Not inside any max-width block. A wrapping rule that stops applying
    above some width leaves the widest screens — the ones nobody develops
    on — as the only broken case."""
    i = CSS.index(".topbar {")
    assert "flex-wrap: wrap" in _block(CSS, i), \
        "the base .topbar rule no longer wraps; ≥1800px will crush the header"


def test_wrapping_is_not_left_behind_in_the_1799_block():
    """Where it used to live. Harmless if it is still there as well, but a
    lone copy there is the bug coming back."""
    i = CSS.find("@media (max-width: 1799px)")
    if i < 0:
        return
    body = _block(CSS, i)
    if ".topbar {" in body and "flex-wrap: wrap" in body:
        j = CSS.index(".topbar {")
        assert "flex-wrap: wrap" in _block(CSS, j), \
            "wrapping only exists under max-width: 1799px again"


def test_the_two_row_layout_still_asks_for_a_full_width_brand():
    """The reason the base rule must wrap. If this ever stops being 100%,
    the coupling above is worth re-reading rather than assuming."""
    i = CSS.index(DESKTOP)
    while ".brand { flex:" not in _block(CSS, i):
        i = CSS.index(DESKTOP, i + 1)
    assert "flex: 1 0 100%" in _block(CSS, i)


# --- groups must not come apart ----------------------------------------------
def test_a_group_is_a_box_on_desktop_so_a_wrap_lands_between_groups():
    """`display: contents` makes every button a direct flex child, which
    lets the row break inside a group. As boxes the groups are the flex
    items, so a break can only fall where the separator already claims it
    does."""
    i = CSS.index('.sport-group[data-group="markets"] .sport-btn:first-child')
    head = CSS.rindex(DESKTOP, 0, i)
    body = _block(CSS, head)
    assert ".sport-group { display: flex;" in body, \
        "the groups are back to display:contents and can split mid-group"
    assert "gap: inherit" in body, \
        "a group with its own fixed gap drifts from the switcher's at 1100px"


def test_the_phone_menu_still_gets_real_group_cards():
    """The phone build already relied on groups being boxes — each becomes
    its own labelled card. Nothing here may take that away."""
    i = CSS.index(".menu-open .sport-group {")
    assert "display: flex" in _block(CSS, i)


def test_the_dropdown_group_is_still_positioned_not_flowed():
    """`.sport-group` now has a `display` of its own, and the tools group
    is a `.sport-group` too. Its absolute rule is more specific, so it
    still wins — pinned because the day it stops, the More menu unfolds
    into the row instead of hanging under the button."""
    i = CSS.index('.sport-more .sport-group[data-group="tools"] {')
    body = _block(CSS, i)
    assert "position: absolute" in body and "display: none" in body


# --- the cascade-order trap --------------------------------------------------
def test_the_switcher_override_comes_after_the_rule_it_overrides():
    """THE MISTAKE THIS FILE KEEPS MAKING. `.sport-switch { flex: 1 1 100% }`
    was first written into the 761-1247 block that sits ~470 lines above
    `.sport-switch { flex: 0 1 auto; margin-left: 22px }`. Same specificity,
    later declaration wins, and a media query contributes none — so every
    declaration in the override did nothing.

    It was invisible because the layout changed anyway: `.brand
    { flex-wrap: wrap }` from the same block was doing all the work, so the
    measurement showed a real improvement while four of the five new
    declarations were dead. A source-order assertion is the only kind that
    catches this; both rules exist and both look right in isolation.
    """
    base = CSS.index(".sport-switch { flex: 0 1 auto;")
    i, over = CSS.find(NARROW), -1
    while i >= 0:
        if ".sport-switch { flex: 1 1 100%" in _block(CSS, i):
            over = i
            break
        i = CSS.find(NARROW, i + 1)
    assert over >= 0, "the narrow-width switcher override is gone"
    assert over > base, (
        f"the override at char {over} sits BEFORE the rule it overrides at "
        f"{base}; it is silently dead")


def test_the_narrow_override_gives_the_switcher_the_whole_width():
    """Below 1248 the brand block is 318px and the eleven buttons want
    860-900px, so beside the wordmark they are 86px short at 1100 and 346px
    short at 960 — two rows at 960 and three at 900, ~44px of header each.
    On its own line the switcher has 886px at 960, which is one row."""
    i = CSS.rindex(NARROW)
    while ".sport-switch { flex: 1 1 100%" not in _block(CSS, i):
        i = CSS.rindex(NARROW, 0, i)
    body = _block(CSS, i)
    assert ".brand { flex-wrap: wrap;" in body, \
        "the brand must wrap or the switcher cannot reach its own line"
    assert "margin-left: 0" in body, \
        "the 22px indent is for sitting beside the wordmark, not under it"
    assert "margin-top: 0" in body and "row-gap:" in body, \
        ("stacked, the row spacing is 24px of pure air — the switcher "
         "stopped wrapping and the header grew anyway")


# --- the More menu must stay on screen ---------------------------------------
#: The width at or above which the switcher holds all eleven buttons on one
#: line, so "More" ends the row. Measured: the buttons need 795px and the
#: content box is the viewport less 52px of bar padding, so 847 is the
#: narrowest width that fits and 846 is the first that wraps.
WRAP_POINT = 847


def test_the_more_menu_anchors_to_whichever_edge_keeps_it_on_screen():
    """Left-anchored at every width, the menu ran off the right of the
    viewport and gave the whole PAGE a horizontal scrollbar: 119px over at
    1280 before this file changed anything, and 7px at 960 / 67px at 900
    once the switcher went full-width and moved "More" to the far right.

    Above the wrap point "More" ends the row, so the menu's right edge
    belongs on the button's. Below it "More" can lead a wrapped second row
    (measured at x 26 at 820px), and there the left anchor is the correct
    one — which is why this is a breakpoint and not a flat swap.
    """
    q = f"@media (min-width: {WRAP_POINT}px) {{"
    assert q in CSS, f"the menu no longer flips its anchor at {WRAP_POINT}px"
    body = _block(CSS, CSS.index(q))
    assert '.sport-more .sport-group[data-group="tools"]' in body
    assert "right: 0" in body and "left: auto" in body, \
        "flipping the anchor needs BOTH, or the left offset still wins"


def test_the_anchor_flip_comes_after_the_rule_it_flips():
    """Same specificity as the base dropdown rule, so source order is the
    only thing making it apply."""
    base = CSS.index('.sport-more .sport-group[data-group="tools"] {')
    flip = CSS.index(f"@media (min-width: {WRAP_POINT}px) {{")
    assert flip > base, "the anchor flip sits above the rule it overrides"


def test_the_breakpoint_is_pinned_to_the_wrap_point_not_a_round_number():
    """The number is wrong in BOTH directions and the failure looks
    different each way. Too high (861 and 848 were both tried) and the
    widths between the wrap point and the breakpoint left-anchor while
    "More" still ends the row — 107px and 120px off the right edge. Too low
    and they right-anchor while "More" leads a wrapped row, hanging the
    menu 120px off the LEFT at 820.

    So this is not a value to round for tidiness. Adding a sport widens the
    switcher and moves the wrap point; re-measure it and change both the
    rule and this constant together.
    """
    assert WRAP_POINT not in (800, 850, 860, 861, 900, 1024), \
        "that is a round number, not the measured wrap point"
    i = CSS.index(f"@media (min-width: {WRAP_POINT}px) {{")
    why = CSS[max(0, i - 2600):i]
    assert "795" in why, "the content width the breakpoint derives from is gone"
    assert "wrap" in why.lower()


def test_the_dead_group_gap_is_now_live():
    """`.sport-group { gap: 3px }` at 761-1023 has been in the sheet all
    along doing nothing: `gap` needs a box, and these were `display:
    contents`. It was written by someone who believed they were boxes,
    which is the model the desktop rule now makes true."""
    q = "@media (min-width: 761px) and (max-width: 1023px) {"
    # There are TWO blocks on this query, and the rule is in the second.
    # Taking the first match found a block that never had it.
    bodies, i = [], CSS.find(q)
    while i >= 0:
        bodies.append(_block(CSS, i))
        i = CSS.find(q, i + 1)
    assert bodies, "the 761-1023 band is gone"
    assert any(".sport-group { gap: 3px; }" in b for b in bodies)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
