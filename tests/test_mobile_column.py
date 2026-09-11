"""The play-by-play column cannot be widened by what is inside it.

Ethan, 2026-09-06, from a phone: "Can you fix the mobile page, it's all
like pushed too the right of the screen and not centered."

Every card on the page was laid out wider than the screen — left edges
where they belonged, right edges off the side, which reads as the page
having been shoved right.

The cause is a one-word difference between the desktop rule and the
phone one. `1fr` is shorthand for `minmax(auto, 1fr)`, and `auto` as a
MINIMUM means the track grows to the min-content width of its widest
child. One child that cannot shrink — a table of nowrap cells, a long
unbroken string — and the whole track is wider than the viewport, taking
every sibling card with it. The desktop rule already clamped this with
`minmax(0, 1fr)`; only the phone was left on bare `1fr`.

Measured in Chromium against this stylesheet, a 360px viewport with a
three-cell nowrap table in the column:

    bare 1fr           card laid out at 369px   (9px off the screen)
    minmax(0, 1fr)     card laid out at 360px   (exact)

and at 428px with a wider table, 507px against a 428px screen.

Pinned at source rather than in a browser because the test suite has no
browser; the numbers above are what a browser said, recorded here so the
next reader does not have to take the rule on faith.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _track(selector, inside_media=False):
    """The grid-template-columns of one rule."""
    pat = (r"@media[^{]*max-width[^{]*\{\s*" if inside_media else r"(?m)^")
    m = re.search(pat + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no rule for {selector} (media={inside_media})"
    g = re.search(r"grid-template-columns:\s*([^;}]+)", m.group(1))
    assert g, m.group(1)
    return g.group(1).strip()


def test_the_phone_column_is_clamped_the_way_the_desktop_one_is():
    desk = _track(".pbp-layout")
    phone = _track(".pbp-layout", inside_media=True)
    assert desk.startswith("minmax(0, 1fr)"), desk
    assert "minmax(0, 1fr)" in phone, phone
    # The exact defect: a bare `1fr` track on the narrow screen.
    assert not re.fullmatch(r"1fr", phone), (
        "1fr is minmax(auto, 1fr) — the track grows to its widest child")


def test_both_halves_of_the_layout_may_shrink():
    """A grid item's own default minimum is `auto` as well, so clamping
    the track alone still leaves the item able to push past it."""
    m = re.search(r"(?m)^\.pbp-main, \.pbp-rail \{([^}]*)\}", CSS)
    assert m, "no shared min-width rule for the column and the rail"
    assert re.search(r"min-width:\s*0", m.group(1)), m.group(1)


def test_the_clamp_is_not_mistaken_for_a_fix_for_wide_content():
    """A wide table still needs its own scroller to be READABLE. The
    clamp only stops it dragging the page sideways, and the note has to
    say so or the next person will read it as licence to drop the
    scrollers."""
    at = CSS.index(".pbp-layout { display: grid")
    note = CSS[max(0, at - 1600):at]
    assert "overflow-x: auto" in note, "the note must name what this does NOT do"


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
