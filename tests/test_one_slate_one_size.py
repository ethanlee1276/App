"""v5: one slate, one size.

Thirty-two empty slates are built with the slate's own classes — a bold
title at the body's large step over a dim sub — and six with a heading
and a paragraph: the Tonight and Edge boards, a stale prop link, the
meme record, Standings, Rosters. Measured at 390, those six rendered at
the display heading's size and weight (17.55px, 400) over a full-colour
15px paragraph, so the two most-read boards wore a different slate from
every other page. The stylesheet gives both shapes the same type; the
markup is left alone, since six call sites are six sets of anchors.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _rule(selector):
    i = CSS.index(selector + " {")
    return CSS[i + len(selector) + 2:CSS.index("}", i)]


def _decl(rule, prop):
    m = re.search(r"(?:^|;|\s)" + re.escape(prop) + r":\s*([^;]+)", rule)
    return m.group(1).strip() if m else None


def test_the_heading_built_slate_wears_the_class_built_type():
    title, h3 = _rule(".empty-slate .es-title"), _rule(".empty-slate > h3")
    for prop in ("font-size", "font-weight", "letter-spacing"):
        assert _decl(title, prop) == _decl(h3, prop), f"title {prop}: {_decl(title, prop)} vs h3 {_decl(h3, prop)}"
    assert _decl(h3, "font-family") == "var(--font-sans)", "an h3 defaults to the display face"
    sub, p = _rule(".empty-slate .es-sub"), _rule(".empty-slate > p")
    for prop in ("font-size", "color", "max-width", "line-height"):
        assert _decl(sub, prop) == _decl(p, prop), f"sub {prop}: {_decl(sub, prop)} vs p {_decl(p, prop)}"
    assert _decl(p, "margin") == "7px 0 0" and _decl(sub, "margin-top") == "7px"


def test_there_are_only_two_shapes_of_slate_and_both_are_styled():
    shapes = {"class": 0, "heading": 0}
    for m in re.finditer(r'class="empty-slate', APP):
        seg = APP[m.end():m.end() + 420]
        if 'class="es-title"' in seg:
            shapes["class"] += 1
        elif "<h3" in seg:
            shapes["heading"] += 1
        else:
            line = APP.count("\n", 0, m.start()) + 1
            raise AssertionError(f"a third shape of slate at app.js:{line}: {' '.join(seg[:120].split())}")
    assert shapes["class"] >= 30 and shapes["heading"] >= 1, shapes


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
