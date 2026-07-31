"""The phone header retracts while you scroll — without reflowing anything.

The header is four stacked rows and position:sticky, so on a phone it held
about a quarter of the screen for the whole scroll. It now slides out of
the way on a downward scroll and returns on any upward one.

The invariant these tests protect is not "it hides" — it is HOW. Every
previous attempt to change this header's size at runtime (the sport-emoji
tile, the wrapping status chips) reflowed the page and produced the "top
of the page keeps enlarging" bug. Moving it with a transform cannot: a
transform is painted, not laid out. So a future edit that reaches for
height/display/margin here has reintroduced that bug, and should fail.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _tuck_rule():
    css = _read("web", "css", "styles.css")
    m = re.search(r"body\.nav-tucked \.topbar \{([^}]*)\}", css)
    assert m, "the retracting-header rule is gone"
    return m.group(1)


def test_the_header_moves_by_transform_only():
    body = _tuck_rule()
    assert "translateY(-100%)" in body
    # Any of these would resize the header instead of moving it, which
    # reflows every pixel of content below it.
    for reflowing in ("height", "display", "margin", "padding", "top:"):
        assert reflowing not in body, f"{reflowing} reflows the page"


def test_it_is_scoped_to_touch_devices():
    css = _read("web", "css", "styles.css")
    at = css.rfind("@media", 0, css.find("body.nav-tucked .topbar"))
    query = css[at:css.find("{", at)]
    assert "max-width: 760px" in query
    assert "pointer: coarse" in query, "phone landscape needs it too"


def test_an_open_menu_is_never_hidden():
    # The menu panel lives inside the header. CSS backstop…
    css = _read("web", "css", "styles.css")
    assert re.search(r"body\.menu-open \.topbar \{[^}]*transform:\s*none", css)
    # …and the toggle itself un-tucks before opening.
    app = _read("web", "js", "app.js")
    assert 'if (open) document.body.classList.remove("nav-tucked");' in app


def test_the_scroll_handler_is_wired_and_cheap():
    app = _read("web", "js", "app.js")
    assert "function initHeaderTuck()" in app
    assert "initHeaderTuck();" in app, "defined but never called"
    fn = app[app.index("function initHeaderTuck()"):]
    fn = fn[:fn.index("\n}\n")]
    # A scroll listener that isn't passive blocks scrolling on iOS, and one
    # that isn't rAF-throttled runs layout reads on every scroll event.
    assert "passive: true" in fn
    assert "requestAnimationFrame" in fn
    assert "menu-open" in fn, "must not fight the menu"


def test_the_top_of_a_page_always_shows_the_header():
    fn = _read("web", "js", "app.js")
    fn = fn[fn.index("function initHeaderTuck()"):]
    fn = fn[:fn.index("\n}\n")]
    m = re.search(r"SHOW_ABOVE = (\d+)", fn)
    assert m and 0 < int(m.group(1)) <= 200, "no always-visible zone at the top"
    # iOS overscroll reports a negative scrollY; unclamped, the delta
    # inverts and the header flickers at the top of every page.
    assert "Math.max(0, window.scrollY)" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
