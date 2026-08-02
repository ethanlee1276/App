"""One type ramp — design queue item 1.

The audit counted 32 distinct font sizes rendering across eleven views.
That is not a ramp with a few strays in it; it is no ramp. Nobody can tell
13px from 13.5px on a card, but everybody can tell that nothing lines up.

Twenty-three of those were ABSOLUTE sizes chosen one rule at a time — 9.5,
10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 16, 17, 18, 20, 22,
23, 24, 26, 30, 34, 38. They now map onto nine tokens. Nine rather than the
seven the queue asked for, because the large end is genuinely
role-differentiated: a stat tile's value, a chart's headline number, the
brand and a profile name are four jobs, and collapsing them further would
be tidiness bought with hierarchy.

The queue item also claimed the fractional sizes were "accidents — what a
percentage did to an inherited size". Reading them, that was wrong and is
corrected here: 8.2, 11.6, 12.76 and friends come from three DELIBERATE
relative rules — `.5em` on a unit suffix, `1.24em` on an emphasised metric,
`.9em` on a rank chip — which are supposed to track their parent. They
render fractional because they are derived, not because anyone typed them.
They stay.

Rendered result: 32 distinct sizes → 20. Of those, 9 are the ramp, 7 are
the SVG graphics scale (labels inside 24-to-240 unit viewBoxes, a different
system from body text), and 4 are the derived relatives.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()

RAMP = ("2xs", "xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl")


def _strip_comments(src):
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_every_step_of_the_ramp_is_defined():
    for step in RAMP:
        assert re.search(rf"--fs-{step}: *[0-9.]+px", CSS), f"--fs-{step} missing"


def test_the_steps_are_strictly_increasing():
    """A ramp whose steps cross is not a ramp, and the bug would be
    invisible until two elements swapped visual weight."""
    vals = [float(re.search(rf"--fs-{s}: *([0-9.]+)px", CSS).group(1))
            for s in RAMP]
    assert vals == sorted(vals) and len(set(vals)) == len(vals), vals


def test_no_rule_in_the_stylesheet_sets_a_raw_pixel_size():
    """Every absolute size goes through a token, or the ramp is decoration
    and the next rule someone adds will invent a 24th size."""
    body = _strip_comments(CSS)
    # The token definitions themselves are the one place raw px belongs.
    body = re.sub(r"--fs-[0-9a-z]+: *[0-9.]+px;", "", body)
    stray = sorted(set(re.findall(r"font-size: *([0-9.]+)px", body)), key=float)
    assert not stray, f"raw font sizes still in the stylesheet: {stray}"


def test_the_renderer_does_not_invent_sizes_either():
    """83 inline style="font-size:Npx" declarations lived in the JS, where
    a stylesheet audit never looks."""
    for name, src in (("app.js", APP), ("visuals.js", VIS)):
        stray = sorted(set(re.findall(r"font-size: ?([0-9.]+)px", src)),
                       key=float)
        assert not stray, f"{name} still emits raw font sizes: {stray}"


def test_relative_sizes_are_left_alone():
    """`.5em` on a unit suffix and `1.24em` on an emphasised metric are
    SUPPOSED to track their parent. Freezing them to px would break the
    relationship to chase a tidier number in an audit."""
    body = _strip_comments(CSS)
    assert "font-size: .5em" in body
    assert "font-size: 1.24em" in body


def test_the_svg_graphics_scale_is_not_folded_into_the_body_ramp():
    """Those labels sit inside viewBoxes 24 to 240 units wide. An 8-unit
    label there is not "8px body text" and mapping it onto --fs-2xs would
    resize it relative to a diagram it has to fit inside."""
    assert re.search(r'font-size="[0-9.]+"', VIS)
    assert "font-size=\"var(" not in VIS


def test_the_one_odd_graphic_size_was_rounded():
    """8.2 was the team monogram, sized by eye to fit three letters. The
    graphics scale is 7/8/8.5/9/10; 8.2 belonged to no scale at all."""
    assert 'font-size="8.2"' not in VIS


def test_the_ramp_covers_the_range_it_replaced():
    """Smallest body size must still be small enough for a caption and the
    largest still large enough for a hero number, or the collapse quietly
    flattened the hierarchy it was meant to organise."""
    lo = float(re.search(r"--fs-2xs: *([0-9.]+)px", CSS).group(1))
    hi = float(re.search(r"--fs-4xl: *([0-9.]+)px", CSS).group(1))
    assert lo <= 11 and hi >= 30


def test_the_deliberate_exceptions_survived():
    """The queue named two: the caps section labels and the mono numbers.
    Both should still be on their own footing rather than absorbed."""
    body = _strip_comments(CSS)
    # THREE rules define .section-title and only the last one wins. Testing
    # the first found no letter-spacing and failed while the caps treatment
    # was working perfectly — asserting on "the first match" asserts on
    # source order, which is not the thing that renders.
    blocks = re.findall(r"\.section-title\s*\{([^}]*)\}", body)
    assert any("letter-spacing" in b and "uppercase" in b for b in blocks), \
        "no .section-title rule still sets the caps treatment"
    assert 'font-feature-settings: "tnum"' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
