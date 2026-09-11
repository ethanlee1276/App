"""The park photograph sat outside the card it belongs to.

Ethan, 2026-09-06, on the live game centre: "second, there is no boarder
or anything for the render so its just sticking out the sides."

Every other row in the park card — the header, the batted-ball tiles,
the park facts, the situation — is laid out inside a 14px side gutter.
The photograph was the one child at `width: 100%` with no margin, so it
ran to the card's edge while everything above and below it stopped short
of that edge, which reads as the picture spilling out of the panel
rather than sitting inside it.

Pinned here as geometry rather than as a string: the park panel keeps a
side gutter, and that gutter is the SAME one the card's own header uses.
Writing the number twice is how the two drift apart again.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _rule(selector):
    """The declarations of one rule, by exact selector at the line start."""
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    assert m, f"no rule for {selector}"
    return m.group(1)


def _side_px(decls, prop):
    """The horizontal half of a `margin`/`padding` shorthand, in px.

    Reads the 1-to-4 value shorthand the way CSS does, so a rule that
    collapses `12px 14px` to a single `0` still answers the question the
    test is asking instead of raising on a short list.
    """
    m = re.search(prop + r":\s*([^;}]+)", decls)
    assert m, f"no {prop} in {decls!r}"
    vals = [int(v) for v in re.findall(r"(-?\d+)(?:px)?\b", m.group(1))]
    assert vals, f"{prop} has no length: {m.group(1)!r}"
    return vals[1] if len(vals) > 1 else vals[0]


def test_the_park_panel_is_inset_by_the_cards_own_gutter():
    park = _rule(".pbp-park")
    head = _rule(".pbp-parkhead")
    # `margin: <v> <h>` — the horizontal half is the gutter.
    park_gutter = _side_px(park, "margin")
    head_gutter = _side_px(head, "padding")
    assert park_gutter == head_gutter, f"park {park_gutter}px vs header {head_gutter}px"
    assert park_gutter > 0, "a zero gutter is the full-bleed bug again"
    # A margined box may not also claim the full width, or it overflows
    # by exactly the two margins it was given.
    assert "width: auto" in park, park
    assert "width: 100%" not in park, "100% plus a margin overflows the card"


def test_the_panel_carries_a_frame_and_clips_what_it_frames():
    park = _rule(".pbp-park")
    assert "border:" in park and "var(--hairline)" in park, park
    assert "var(--brand)" in park, "the frame follows the card's gold, not a second colour"
    assert "overflow: hidden" in park, "the photo, the wall marks and the arc stay inside"
    assert "border-radius: var(--radius)" in park, "corner shape comes from the theme token"


def test_no_full_width_rule_is_left_floating_under_the_framed_photo():
    # The tiles' top border used to separate them from a photo that ran
    # edge to edge. With the photo framed and inset, that rule would draw
    # a second line 14px below a border the photo already has.
    assert "border-top" not in _rule(".pbp-bb")


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
