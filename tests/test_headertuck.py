"""The phone header follows the finger — without reflowing anything.

The header is four stacked rows and position:sticky, so on a phone it held
about a quarter of the screen for the whole scroll. It now moves with the
page: offset by exactly how far you have scrolled since your last change of
direction, clamped to its own height. Swipe up 40px, it moves up 40px;
reverse and it comes back at the same rate from wherever it is.

Two invariants are worth protecting here, and neither is "it hides".

1. HOW it moves. A transform is painted, not laid out, so content behind it
   cannot shift. Every previous attempt to change this header's size at
   runtime reflowed the page and produced the "top of the page keeps
   enlarging" bug. A future edit reaching for height/display/margin has
   reintroduced it.

2. That it tracks rather than snaps. A deadzone makes it ignore small
   drags; a CSS transition makes it glide on its own clock while the finger
   is still moving. Either one reads as the header lagging the page — which
   is exactly the version that got rejected.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _tuck_fn():
    app = _read("web", "js", "app.js")
    start = app.index("function initHeaderTuck()")
    return app[start:app.index("\n}\n", start)]


def test_the_header_moves_by_transform_only():
    fn = _tuck_fn()
    assert "style.transform = " in fn
    assert "translateY(" in fn
    # Any of these resizes the header instead of moving it, reflowing every
    # pixel of content below.
    for reflowing in ("style.height", "style.display", "style.marginTop",
                      "style.top", "classList.add"):
        assert reflowing not in fn, f"{reflowing} reflows the page"


def test_it_tracks_the_scroll_one_to_one():
    fn = _tuck_fn()
    # offset = clamp(offset - dy, -height, 0): the delta is applied whole,
    # never scaled and never rounded to an on/off state.
    assert re.search(r"headerOffset\s*=\s*Math\.min\(\s*0,\s*"
                     r"Math\.max\(\s*-height,\s*headerOffset\s*-\s*dy\s*\)\s*\)", fn), \
        "the offset is no longer a clamped 1:1 accumulation of scroll delta"
    assert "DEADZONE" not in fn, "a deadzone makes it ignore small drags"


def test_nothing_animates_the_transform():
    # A transition on .topbar's transform would animate on its own clock
    # while the finger is still on the glass.
    css = _read("web", "css", "styles.css")
    for m in re.finditer(r"\.topbar[^{]*\{([^}]*)\}", css):
        body = m.group(1)
        assert "transition" not in body, \
            "the header must not animate — it follows the finger"


def test_it_is_scoped_to_touch_devices():
    # The transform is written INLINE, so only this query keeps it off a
    # desktop — and the same query must gate the CSS backstop.
    app = _read("web", "js", "app.js")
    mq = re.search(r"HEADER_TUCK_MQ\s*=\s*\n?\s*\"([^\"]+)\"", app)
    assert mq, "no media query gating the tuck"
    assert "max-width: 760px" in mq.group(1)
    assert "pointer: coarse" in mq.group(1), "phone landscape needs it too"
    assert "matchMedia(HEADER_TUCK_MQ)" in app
    assert "!touch.matches" in app, "gate is defined but never checked"

    css = _read("web", "css", "styles.css")
    at = css.rfind("@media", 0, css.index("body.menu-open .topbar"))
    assert mq.group(1) in css[at:css.index("{", at)], \
        "the JS and CSS device gates have drifted apart"


def test_an_open_menu_is_never_hidden():
    # The menu panel lives inside the header. CSS backstop — !important
    # because it must beat the inline transform…
    css = _read("web", "css", "styles.css")
    assert re.search(r"body\.menu-open \.topbar \{[^}]*transform:\s*none\s*!important", css)
    # …and the toggle resets it before opening.
    app = _read("web", "js", "app.js")
    assert "if (open) showHeader();" in app
    assert "menu-open" in _tuck_fn(), "the scroll handler must not fight the menu"


def test_the_scroll_handler_is_wired_and_cheap():
    app = _read("web", "js", "app.js")
    assert "initHeaderTuck();" in app, "defined but never called"
    fn = _tuck_fn()
    # Non-passive scroll listeners block scrolling on iOS; unthrottled ones
    # run layout reads on every scroll event.
    assert "passive: true" in fn
    assert "requestAnimationFrame" in fn
    # offsetHeight per frame forces a layout flush; it's watched instead.
    assert "ResizeObserver" in fn, "header height must not be measured once"


def test_overscroll_cannot_invert_the_delta():
    # iOS reports a negative scrollY mid-bounce. Unclamped, dy flips sign
    # and the header twitches at the top of every page.
    fn = _tuck_fn()
    assert "Math.max(0, window.scrollY)" in fn
    assert "y === 0" in fn, "the top of a page must reset it to fully shown"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
