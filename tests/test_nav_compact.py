"""The compact desktop navigation — one slim bar, everything one tap away.

Ethan, 2026-08-10: "maybe we shrink that top bar so there is just a
three-bar menu thing at the top that you select and it pulls everything
up? I don't want it to hide shit."

The contract pinned here: compact is the desktop DEFAULT (83px measured,
was 224); the ENTIRE existing switcher stays in the DOM and opens behind
the same #menu-toggle machinery the phone uses; the pin persists the
always-expanded preference; and phones are untouched — the class never
applies at or below 760px.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web/css/styles.css"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()


def test_compact_is_desktop_only_and_class_driven():
    """Every compact rule lives under min-width 761px AND the body class,
    so phones keep their own menu system untouched and the pin can flip
    desktop back to the full bar without a reload."""
    i = CSS.index("COMPACT NAVIGATION")
    block = CSS[i:]
    assert "@media (min-width: 761px)" in block[:2000]
    for sel in ("body.nav-compact header", "body.nav-compact .menu-toggle",
                "body.nav-compact.menu-open .sport-switch"):
        assert sel in block, f"{sel} missing — the bar or its dropdown broke"


def test_nothing_leaves_the_dom():
    """'I don't want it to hide shit' — the switcher, pages nav and
    record strip are display-toggled, never removed: the dropdown shows
    the SAME buttons every handler is already bound to."""
    i = CSS.index("COMPACT NAVIGATION")
    block = CSS[i:]
    assert "body.nav-compact .sport-switch" in block
    assert "body.nav-compact.menu-open .sport-switch { display: flex" in block
    assert "body.nav-compact.menu-open .nav { display: flex" in block


def test_the_one_row_bar_is_enforced():
    """A later masthead rule gives .brand flex-basis 100%, which stacked
    the bar's three slim pieces into three rows — 186px of 'compact'.
    The override is what makes the bar 83px instead."""
    i = CSS.index("COMPACT NAVIGATION")
    assert "body.nav-compact .brand { flex: 0 1 auto; }" in CSS[i:]


def test_the_pin_exists_and_persists():
    assert 'id="nav-pin"' in HTML
    assert "NAV_FULL_KEY" in JS and "qb_nav_full" in JS
    assert "function applyNavMode" in JS
    fn = JS[JS.index("function applyNavMode"):]
    fn = fn[:fn.index("\n}")]
    assert "(min-width: 761px)" in fn, "compact could leak onto phones"
    # The dropdown closes like a menu: outside click is handled.
    init = JS[JS.index("function initNavMode"):]
    assert "closeMobileMenu()" in init


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
