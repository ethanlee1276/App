"""The More sheet holds the page still.

Ethan, 2026-09-22, from his phone with the sheet open: "when I'm in
this menu I'm able to swipe the page behind it and not the actual
menu."

iOS scrolls a body under a fixed sheet whatever `overflow` says. So
while the sheet is open the body is pinned in place — position fixed
at the scroll offset it had, which moreSheetOpen writes into `top` —
and put back to the same offset on close; the sheet scrolls itself and
a swipe past its end stays in it (overscroll-behavior: contain); the
scrim takes no gesture. Probed with a touch swipe on a scrolled page:
the sheet moved, the page did not, and the page came back where it was.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _fn(name):
    i = APP.index(f"function {name}(")
    return re.sub(r"^\s*//.*$", "", APP[i:APP.index("\n}\n", i)], flags=re.M)


def _phone():
    i = DECLS.index(".more-sheet { display: block; position: fixed;")
    start = DECLS.rfind("@media (max-width: 760px) {", 0, i)
    return DECLS[start:DECLS.index("\n}\n", i) + 3]


def test_the_body_is_pinned_where_it_was_while_the_sheet_is_open():
    p = _phone()
    assert "body.more-open { position: fixed; left: 0; right: 0; width: 100%; overflow: hidden; }" in p
    op = _fn("moreSheetOpen")
    assert "_moreScrollY = window.scrollY || 0;" in op and "document.body.style.top = `-${_moreScrollY}px`;" in op, \
        "pinned at the offset it had, or the page jumps to the top under the sheet"
    i = op.index('document.body.classList.add("more-open");')
    assert op.index("document.body.style.top = ") < i, "the offset is written before the pin takes effect"
    assert "sheet.scrollTop = 0;" in op, "the sheet opens at its top"
    assert 'const wasOpen = document.body.classList.contains("more-open");' in op
    assert 'document.body.style.top = "";' in op and "if (wasOpen) window.scrollTo(0, _moreScrollY);" in op, \
        "on close the page comes back to where it was"
    assert re.search(r"^let _moreScrollY = 0;", APP, re.M)


def test_the_sheet_scrolls_itself_and_the_scrim_takes_no_gesture():
    p = _phone()
    i = p.index(".more-sheet { display: block; position: fixed;")
    sheet = p[i:p.index("}", i)]
    assert "overflow-y: auto" in sheet and "overscroll-behavior: contain" in sheet, "a swipe past the sheet's end must stay in the sheet"
    i = p.index(".more-scrim { display: block; position: fixed; inset: 0; z-index: 57;")
    assert "touch-action: none" in p[i:p.index("}", i)]


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
