"""A rule should be one device pixel, which `1px` stopped meaning.

Measured before the pass: **94 borders drawn as `1px solid`**, plus 6 at
2px, 5 at 3px and one pair at 1.6px. On a 2x display a 1px border is TWO
device pixels, so every divider on the page rendered at double the weight
it was drawn for — and every screen this site is read on is retina.

After: 93 of them go through `--hairline`, which is 1px on a 1x screen and
0.5px from 2dppx up.

The two exceptions are deliberate and both are checked here, because an
exception nobody wrote down gets "fixed" later:

  * the 2px and 3px borders are all `border-left` accent stripes — grade
    colour, warnings, the brand rail. They are structural marks, not
    rules, and halving them would make them read as dividers.
  * one DOTTED rule keeps its full pixel. Dots need width to still be
    dots; half a pixel of one is a smudge.

Run directly: `python3 tests/test_hairlines.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()

#: Comments explain the old values, so search declarations rather than the
#: raw file — otherwise the test matches its own reasoning.
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

BORDER = r"border(?:-(?:top|right|bottom|left))?:\s*"


def test_the_token_exists_and_is_a_full_pixel_by_default():
    """A 1x screen never enters the retina query, and there a real pixel
    is the correct hairline."""
    m = re.search(r"--hairline:\s*([0-9.]+)px", DECLS)
    assert m, "no --hairline token"
    assert float(m.group(1)) == 1.0, m.group(1)


def test_it_halves_on_a_retina_screen():
    m = re.search(r"@media \(min-resolution:\s*2dppx\)\s*\{[^}]*"
                  r"--hairline:\s*([0-9.]+)px", DECLS, flags=re.S)
    assert m, "no retina override"
    assert float(m.group(1)) == 0.5, m.group(1)


def test_no_solid_rule_is_drawn_at_a_raw_pixel():
    """The pass itself. 93 declarations moved; a raw `1px solid` in a new
    rule is how the 94th gets back in."""
    bad = re.findall(BORDER + r"1px\s+solid", DECLS)
    assert not bad, f"{len(bad)} raw 1px solid borders"


def test_the_hairline_is_actually_used_widely():
    """A token nothing references is worse than no token — it reads as a
    system while the page keeps its raw values."""
    n = len(re.findall(BORDER + r"var\(--hairline\)", DECLS))
    assert n > 80, n


# --- the exceptions, both on purpose -----------------------------------------
def test_the_accent_stripes_keep_their_weight():
    """2px and 3px are marks, not rules. If one turns up on a border-top
    or border-bottom that is a divider wearing a stripe's weight."""
    for w in ("2px", "3px"):
        for m in re.finditer(BORDER + w, DECLS):
            decl = DECLS[m.start():m.end()]
            assert "border-left" in decl or "border-bottom" in decl, decl


def test_exactly_one_dotted_rule_keeps_a_full_pixel():
    """Dots need width to read as dots. Half a pixel of one is a smudge,
    so this is the single solid-rule exemption and it stays countable."""
    dotted = re.findall(BORDER + r"1px\s+dotted", DECLS)
    assert len(dotted) == 1, dotted
    assert not re.findall(BORDER + r"var\(--hairline\)\s+dotted", DECLS)


def test_the_chevron_is_not_a_border_rule():
    """1.6px on .pz-runner > summary::after draws a disclosure chevron out
    of two borders. It is a glyph, and thinning it would thin the mark
    rather than a divider."""
    i = DECLS.index(".pz-runner > summary::after")
    block = DECLS[i:DECLS.index("}", i)]
    assert "1.6px" in block
    assert "--hairline" not in block


# --- it did not become a different change ------------------------------------
def test_nothing_but_borders_moved():
    """The substitution was scoped to border declarations. A box-shadow or
    an outline picking up --hairline would be a different change riding
    along inside this one."""
    for prop in ("box-shadow", "outline", "width", "height"):
        for m in re.finditer(rf"{prop}:[^;]*", DECLS):
            assert "--hairline" not in m.group(0), m.group(0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
