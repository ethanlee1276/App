"""White text on the solid brand violet was a tier too faint.

Ethan, 2026-08-20: "Check: contrast ... ARIA labels, form labels,
semantic buttons, image alt text."

Swept every rendered text node in twelve views against its COMPOSITED
background. Alt text, form labels and accessible button names came back
clean — zero each. Colour did not:

    white on --brand (#8D5BF2)     APCA Lc -74.5    WCAG 4.28
    white on --brand-solid (#7C43E4) APCA Lc -82.3  WCAG 5.56

`contrast.py`'s own ladder rates Lc 74.5 as "larger or secondary text"
and Lc 82.3 as "body text, minimum". The seven rules below fill solid
with the identity violet and print 10-13px labels on it — small text in a
tier meant for large. So the FILL moved, not the brand: `--brand-solid`
is the midpoint of `--grad-brand`, a colour the palette already
contained, and `--brand` is untouched because it is the render's identity
and one gold mark sits on it.

TWO THINGS THIS FILE IS REALLY ABOUT.

**The ruler was wrong first, and believing it would have been a
disaster.** The initial sweep reported 205 failures, including near-white
text at 1.13:1 on a near-black page. It read `rgba(255,255,255,.04)` —
the 4% wash this design uses for card surfaces — took the first three
numbers and called the surface pure white. Every card in a dark UI became
a defect. Composite the alpha and the real count was 2. Acting on 205
would have repainted a palette that was never wrong.

**The rendered sweep found 2 of the 7.** The other five —
`.nav-acct-init`, `.plan-band`, `.al-cat.on`, `.stub-cta`,
`.mbc-view.active` — live in states no sweep visited: a signed-in avatar,
a pricing band behind a flag, a selected alert category, a stub page.
`test_no_rule_puts_white_on_the_light_brand_as_a_solid_fill` is the
general form, over source, and it is what caught them. Breadth is not
optional; a picture only shows what was on screen.

Run directly: `python3 tests/test_brandfill.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contrast as ct                                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
WHITE = (255, 255, 255)

#: The tier `contrast.py` calls "body text, minimum". Small UI labels are
#: body text; a chip is not a headline.
BODY_LC = 75.0


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _token(name):
    block = CSS[CSS.index("NEW LOOK — 2026-08-11"):]
    m = re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})\s*;", block)
    assert m, f"--{name} is not defined in the new-look block"
    return _hex(m.group(1))


def test_the_measurement_reproduces():
    """The number this whole file rests on. If it moves, the fix below is
    answering a question nobody asked any more."""
    lc = abs(ct.lc(WHITE, _hex("#8D5BF2")))
    assert 73 < lc < 76, f"white on the identity violet now measures Lc {lc:.1f}"


def test_the_safe_fill_reaches_the_body_tier():
    solid = _token("brand-solid")
    lc = abs(ct.lc(WHITE, solid))
    assert lc >= BODY_LC, \
        f"white on --brand-solid is Lc {lc:.1f}, under the body-text tier {BODY_LC}"


def test_the_identity_violet_did_not_move():
    """A contrast miss on some chips is not a licence to restyle the
    product. `--brand` is the render's colour."""
    assert _token("brand") == _hex("#8D5BF2"), \
        "the brand violet changed — that is a design decision, not a fix"


def test_the_safe_fill_is_a_colour_the_palette_already_had():
    """A new colour is a new thing to keep consistent. This one is the
    midpoint of --grad-brand."""
    m = re.search(r"--grad-brand: linear-gradient\(135deg, (#[0-9A-Fa-f]{6}), (#[0-9A-Fa-f]{6})\)", CSS)
    assert m, "--grad-brand is no longer the two-stop violet this was derived from"
    a, b = _hex(m.group(1)), _hex(m.group(2))
    mid = tuple((a[i] + b[i]) // 2 for i in range(3))
    solid = _token("brand-solid")
    assert all(abs(solid[i] - mid[i]) <= 2 for i in range(3)), \
        f"--brand-solid {solid} is no longer the gradient's midpoint {mid}"


def test_no_rule_puts_white_on_the_light_brand_as_a_solid_fill():
    """THE GENERAL FORM, and the one that did the work. Five of the seven
    defects were in states the rendered sweep never reached."""
    bad = []
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        sel, body = m.group(1).strip(), m.group(2)
        if not re.search(r"background:\s*var\(--brand\)", body):
            continue
        if re.search(r"color:\s*(#fff\b|#ffffff\b|white)", body, re.I):
            bad.append(sel.splitlines()[-1].strip()[:60])
    assert not bad, ("white on a solid --brand fill is Lc 74.5, a tier below "
                     f"small text — use var(--brand-solid): {bad}")


def test_the_seven_rules_that_were_repaired_stayed_repaired():
    for sel in (".mbc-chip.active", ".ra-range.active", ".mbc-view.active",
                ".nav-acct-init", ".stub-cta", ".al-cat.on", ".plan-band"):
        i = CSS.index(sel)
        block = CSS[i:CSS.index("}", i)]
        assert "var(--brand-solid)" in block, \
            f"{sel} fills with the identity violet again"


def test_the_wcag_number_is_kept_as_a_footnote_not_the_verdict():
    """This repo judges dark pairs with APCA on purpose — see
    tests/test_contrast.py, which exists because WCAG 2.x misjudges them.
    The WCAG figures in this file's docstring are context, and the
    assertions above are all APCA."""
    src = open(__file__, encoding="utf-8").read()
    body = src[src.index('"""', src.index('"""') + 3):]
    # The needle is assembled rather than written, because a literal
    # would match THIS line and the check would fail on itself — which is
    # exactly what the first draft did.
    apca, wcag = "ct." + "lc(", "ct." + "wcag("
    assert apca in body, "the assertions stopped using APCA"
    hits = [ln for ln in body.splitlines()
            if wcag in ln and "assembled rather than written" not in ln]
    assert not hits, \
        f"a WCAG ratio became an assertion — this repo's verdict is APCA: {hits}"


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
