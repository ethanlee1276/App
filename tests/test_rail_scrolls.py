"""The play feed is cut off at the viewport and scrolls itself.

Ethan, 2026-09-06, circling the rail on the play-by-play page: "we
should just make this menu cut off and let people scroll it so you dont
have to scroll all the way down the page bc its ugly."

The rail was `position: sticky` with no ceiling, which is sticky in name
only — an element taller than the viewport has nothing to stick to. So
it ran the full length of the feed and the page grew to match: every
pitch of a nine-inning game in one column, under a park card that ends
after four hundred pixels.

Measured in Chromium, 1440x900, two hundred pitches in the rail:

    before   page 30929px tall, rail not scrollable
    after    page   900px tall, rail 820px, scrolls its own 30943px

This is not a new pattern. `.rail` — the site's other sidebar — has done
exactly this since it was written: sticky under the topbar, capped at
the viewport, scrolling its own overflow, released back into normal flow
when the layout folds. The play feed was the one rail that never picked
it up, so the fix is to make it agree with its sibling rather than to
invent a second way of doing this.

The subtle half is `flex: 0 0 auto` on the children. `.card` carries
`overflow: hidden`, which makes it a legal flex item to compress, so the
first version of this capped the rail and the CARD swallowed the feed —
two hundred pitches clipped to nothing, no scrollbar anywhere. Cut off
but not scrollable, which is the useless half of the request. Chromium
said rail 820px, content 820px, scrolls false; that is what caught it.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _media_blocks(px):
    """Every `@media (max-width: <px>px)` block, brace-matched.

    Not a regex over "up to the next \n}": the stylesheet has both
    one-line and multi-line blocks at this width, and a lazy match walked
    straight past the one-liner into the wrong rule — it then answered
    with the TOP-LEVEL .pbp-rail and the test passed on the unfolded
    version of the very thing it was checking."""
    out, needle = [], f"@media (max-width: {px}px)"
    i = CSS.find(needle)
    while i != -1:
        j = CSS.index("{", i)
        depth, k = 1, j + 1
        while depth and k < len(CSS):
            if CSS[k] == "{":
                depth += 1
            elif CSS[k] == "}":
                depth -= 1
            k += 1
        out.append(CSS[j + 1:k - 1])
        i = CSS.find(needle, k)
    return out


def _rule(selector, media=None):
    hays = _media_blocks(media) if media else [CSS]
    assert hays, f"no @media max-width {media}"
    for hay in hays:
        m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", hay)
        if m:
            return m.group(1)
    raise AssertionError(f"no rule for {selector} (media={media})")


def test_the_feed_is_capped_at_the_viewport_and_scrolls_its_own_overflow():
    r = _rule(".pbp-rail")
    assert "position: sticky" in r
    assert "max-height:" in r and "100vh" in r, r
    assert "overflow-y: auto" in r, "cut off is only half of it — it has to scroll"
    # Under the topbar, not under an eyeballed 8px.
    assert "top: var(--topbar-h)" in r, r
    assert "top: 8px" not in r


def test_the_cards_in_it_keep_their_height():
    """`.card` has overflow:hidden, so a flex column will happily crush
    it and clip the feed instead of scrolling it."""
    assert re.search(r"(?m)^\.pbp-rail > \* \{[^}]*flex: 0 0 auto", CSS)


def test_it_follows_the_rail_the_site_already_had():
    """Two sidebars doing the same job two different ways is how one of
    them stops getting fixed."""
    mine, theirs = _rule(".pbp-rail"), _rule(".rail")
    for prop in ("position: sticky", "top: var(--topbar-h)", "overflow-y: auto"):
        assert prop in mine and prop in theirs, prop
    assert "calc(100vh - var(--topbar-h)" in mine and "calc(100vh - var(--topbar-h)" in theirs


def test_it_lets_go_at_the_same_width_the_layout_folds():
    """A rail that stays capped after the columns collapse is a nested
    scroller in the middle of a phone page. It has to release at the SAME
    breakpoint the grid does, or the two disagree about 'narrow'."""
    fold = re.search(r"@media \(max-width: (\d+)px\) \{ \.pbp-layout \{", CSS)
    assert fold, "the layout's own fold breakpoint moved"
    r = _rule(".pbp-rail", media=fold.group(1))
    assert "position: static" in r and "max-height: none" in r, r


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
