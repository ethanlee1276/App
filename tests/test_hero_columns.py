"""The scoreboard hero has a column for every block in it.

Ethan, 2026-09-06, circling the top card on his phone: "this area on the
play by play screen is bugged out."

The hero is five children — away block, away score, the state in the
middle, home score, home block. The desktop rule gives them five
columns. The phone override moves the middle one out to its own
full-width row across the top, which leaves FOUR children still to
place — and it was handing them THREE columns.

So the grid did exactly what a grid does. Away block, away score and
home score filled row two, and the home block wrapped onto a row of its
own, left-aligned in column one, directly under the away team.
`justify-content: flex-end` then right-aligned it INSIDE that first
column, which is why it read as floating in the middle of nowhere rather
than as an obvious wrap.

Measured in Chromium at 390px, before and after:

    before   away block left 31px, home block left  31px   (stacked)
    after    away block left 31px, home block left 228px   (beside it)

at 900px the home block sits at 542 either way, which is why this was
only ever visible on a phone.

The test counts rather than matching a literal, so adding a sixth block
to the hero fails here instead of silently wrapping on someone's phone.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()

HERO = APP[APP.index('<div class="card pbp-hero">'):APP.index('<div class="card pbp-parkcard">')]


def _tracks(decl):
    """How many columns a grid-template-columns value declares."""
    return len(re.findall(r"(?:minmax\([^)]*\)|[\d.]+fr|auto|[\d.]+px)", decl))


def _hero_rule(media=None):
    hay = CSS
    if media:
        i = CSS.index(f"@media (max-width: {media}px) {{ .pbp-hero {{")
        hay = CSS[i:CSS.index("} }", i)]
    m = re.search(r"\.pbp-hero \{[^}]*grid-template-columns:\s*([^;}]+)", hay)
    assert m, f"no hero grid rule (media={media})"
    return m.group(1).strip()


def _blocks():
    """The hero's own children, by the classes the page gives them."""
    return (len(re.findall(r'class="pbp-hero-side"', HERO))
            + len(re.findall(r'class="pbp-hero-score"', HERO))
            + len(re.findall(r'class="pbp-hero-mid"', HERO))
            + len(re.findall(r'class="pbp-hero-side pbp-hero-home"', HERO)))


def test_the_hero_is_still_five_blocks():
    assert _blocks() == 5, HERO[:400]


def test_the_wide_layout_has_a_column_per_block():
    assert _tracks(_hero_rule()) == _blocks()


def test_the_phone_layout_has_a_column_per_block_that_is_left_in_the_row():
    """The middle block is lifted out to its own full-width row, so the
    row below it needs one column fewer — not two."""
    lifted = re.search(r"\.pbp-hero-mid \{[^}]*grid-column:\s*1 / -1", CSS)
    assert lifted, "the state block no longer spans its own row"
    assert _tracks(_hero_rule(media=700)) == _blocks() - 1


def test_the_home_block_still_hugs_its_own_side():
    """It is the right-alignment that turned the wrap into something
    that looked deliberate, so it has to stay honest about which column
    it is aligning inside of."""
    m = re.search(r"(?m)^\.pbp-hero-home \{([^}]*)\}", CSS)
    assert m and "flex-end" in m.group(1), m


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
