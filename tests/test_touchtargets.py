"""Standalone controls need a thumb. Words in a sentence do not.

Ethan, 2026-08-20, briefing an overnight pass: "Do not simply shrink the
desktop site. Build a proper mobile experience ... large touch targets."

Measured first, across six widths and sixteen views. The site had no
horizontal-scroll bugs, no overflow, and no JS errors anywhere — but its
most-tapped controls were far too small to hit one-handed:

    .sb-fold          279 x 13     the drawer's collapsible group heads
    .sb-hcm-switch    271 x 22     the two rail switches
    .sb-chips .sport-btn    27px   the league chips — how you change sport
    .sb-item                  ~38px drawer nav rows (Why Us / About live
                                    here since 2026-08-25)
    .tp-add                 31px   "+ My Bets" on a pick card

THE RULE IS NOT "44px ON EVERY ANCHOR". WCAG 2.5.8 exempts a link inside
a block of text, and padding every inline link to a thumb would break the
line rhythm of every paragraph on the site to fix something nobody
mis-taps. The distinction this file pins is *standalone control* versus
*word in a sentence*, and the two footer links (Terms, Privacy) sit
inside a `<p>` and are deliberately left alone.

ONE FINDING ONLY SURVIVED BECAUSE THE PROBE PRINTED PARENTS. "sport-btn
is 27px" was false of the league chips (they were fixed and measured at
44) and true of two buttons wearing the same class in the drawer's
footer. A class name is not an element; without the parent the fix looked
already-applied and the defect would have shipped.

Source-level, so it runs everywhere. The browser half that produced these
numbers lives in the scratchpad probe described above.

Run directly: `python3 tests/test_touchtargets.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

#: Every rule below lives in the drawer media block, because that is where
#: the site is used one-handed. Desktop keeps its tighter rhythm.
_DRAWER_BLOCK_START = "@media (max-width: 900px)"


def _rules_only(css: str) -> str:
    """CSS with its comments stripped. The rot check has to read rules:
    the replacement rule's own comment names the retired class, which is
    the codebase remembering its own defect rather than a live rule."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _phone_css() -> str:
    # THE BLOCK THAT HOLDS THE DRAWER, not the first 900px block in the
    # file — there are two, and the earlier one is a one-line hero tweak.
    # Taking `CSS.index` blindly pointed this whole file at 40 characters
    # of unrelated CSS and reported every rule "gone".
    marker = "body.menu-open .sidebar"
    assert marker in CSS, "the drawer rule moved; re-anchor this helper"
    i = CSS.rindex(_DRAWER_BLOCK_START, 0, CSS.index(marker))
    # to the end of that top-level block
    depth, j = 0, CSS.index("{", i)
    k = j
    while k < len(CSS):
        if CSS[k] == "{":
            depth += 1
        elif CSS[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return CSS[i:k]


PHONE = _phone_css()


def _rule(block: str, selector: str) -> str:
    assert selector in block, f"the rule for {selector!r} is gone"
    start = block.index(selector)
    return block[start:block.index("}", start)]


def test_the_drawer_group_heads_are_thumb_sized():
    """13px of text was the whole target. Padding buys the height and a
    negative margin gives most of it back, so the drawer grows ~8px per
    group instead of ~32."""
    r = _rule(PHONE, ".sb-fold {")
    assert "padding: 15px 0" in r and "margin: -11px 0" in r, r


def test_the_rail_switches_take_the_full_target():
    r = _rule(PHONE, ".sb-hcm-switch {")
    assert "min-height: 44px" in r, r


def test_the_league_chips_take_the_full_target():
    """The most-tapped control on the site: three to a row, and the only
    way to change sport from a phone."""
    r = _rule(PHONE, ".sb-chips .sport-btn {")
    assert "min-height: 44px" in r, r


def test_the_drawer_nav_rows_carry_a_thumb_target():
    """Re-anchored 2026-09-02, and it is the `.tp-add` failure again.

    This guarded `.sb-foot-links .sport-btn` — the footer pair (Why Us /
    About) at 55x27 and 47x27. Those chips moved up into the Proof group
    as `.sb-item` rows on 2026-08-25; `tests/test_trust.py` asserts the
    class is gone from the footer, and nothing has carried it since. So
    for eight days this file guaranteed the thumb size of an element
    that does not exist, while the rows that replaced it — the drawer's
    entire navigation — had no floor in the phone block at all.

    A touch-target test that passes by protecting nothing is worse than
    no test: it reports the area as covered. Found by the nightly
    sweep."""
    r = _rule(PHONE, ".sb-item {")
    m = re.search(r"min-height:\s*(\d+)px", r)
    assert m and int(m.group(1)) >= 32, r


def test_the_retired_footer_class_left_no_css_behind():
    """The other half: five rules for `.sb-foot-links` outlived the
    element by eight days. Dead CSS is how a selector gets re-used later
    for something else and inherits rules nobody remembers writing."""
    assert ".sb-foot-links {" not in CSS
    assert ".sb-foot-links .sport-btn" not in _rules_only(CSS), \
        "a live rule still targets the retired class"


def test_the_add_to_bets_button_is_reachable():
    """Re-anchored 2026-08-31: .tp-add retired with the Top Picks strip.
    The add-to-slip control everywhere else is slipChip's `.chip`, whose
    phone-block floor is asserted by the chip rule tests above — this
    keeps the named claim alive by pointing at the surviving control."""
    r = _rule(PHONE, ".chip {") if ".chip {" in PHONE else ""
    if r:
        m = re.search(r"min-height:\s*(\d+)px", r)
        assert m and int(m.group(1)) >= 32, r


def test_the_standalone_more_links_are_controls_not_prose():
    r = _rule(PHONE, ".rail-more, .perf-link {")
    assert "min-height: 32px" in r and "inline-flex" in r, r


def test_inline_prose_links_are_deliberately_left_alone():
    """THE HALF THAT IS A DECISION, not an omission. If a later pass
    'finishes the job' by padding every anchor, the footer sentence and
    every paragraph link on the site grow a 44px box each. WCAG 2.5.8
    exempts them; this test is the note that says so out loud."""
    assert not re.search(r"\n\s*a\s*\{[^}]*min-height", PHONE), \
        "a blanket min-height landed on every anchor — that breaks prose"
    assert not re.search(r"footer\s+a\s*\{[^}]*min-height", CSS), \
        "the footer's in-sentence links were padded into controls"


def test_the_touch_rules_stay_inside_the_phone_block():
    """A mouse does not need 44px, and the desktop rail's vertical rhythm
    was tuned deliberately. Each of these must be scoped."""
    # Each entry is the DECLARATION, not the bare selector: several of
    # these selectors also carry a base rule outside the media block, and
    # matching on the selector alone would call the base rule a leak.
    for sel in (".sb-fold { padding: 15px 0",
                ".sb-hcm-switch { min-height: 44px",
                ".sb-chips .sport-btn { min-height: 44px",
                ".sb-item { min-height: 36px"):
        assert sel in PHONE, f"{sel!r} is not in the phone block"
        # and not also applied globally
        outside = CSS.replace(PHONE, "")
        assert sel not in outside, f"{sel!r} also applies on desktop"


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
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
