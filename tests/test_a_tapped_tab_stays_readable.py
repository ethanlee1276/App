"""A sub-tab just tapped stays readable (22 November 2026).

A phone keeps :hover on the last thing touched. The site-wide hover for buttons and sub-tabs
(`.subnav-btn:hover`, the "no hard lines" pass) comes later in styles.css than `.subnav-btn.active` and
out-ranks it, so the tab just tapped on Report Picks, the Record or any page with sub-tabs sat in the hover grey
wearing the brand's dark ink: measured in a phone-sized browser, background rgba(255,255,255,0.086) and text
rgb(10,9,7). The Fantasy room cards had the same bug on 14 September and kept their own fix
(`.room-card.active:hover`). This holds that the selected sub-tab keeps the brand's fill under a hover, after
every rule that could take it away.

    python3 tests/test_a_tapped_tab_stays_readable.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rules(css: str):
    """(selectors, body, offset) for every plain rule, comments dropped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", css):
        yield [s.strip() for s in m.group(1).split(",")], m.group(2), m.start()


def test_the_selected_sub_tab_keeps_its_fill_under_a_hover():
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    grey = [at for sels, body, at in _rules(css) if ".subnav-btn:hover" in sels and "background" in body]
    keep = [at for sels, body, at in _rules(css)
            if ".subnav-btn.active:hover" in sels and re.search(r"background(-color)?:\s*var\(--brand\)", body)
            and "var(--brand-ink)" in body]
    assert grey, "the site-wide hover is where this test expects it"
    assert keep and max(keep) > max(grey), "the selected sub-tab's fill comes after every hover that greys it"


def test_the_room_cards_keep_theirs():
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert any(".room-card.active:hover" in sels and "var(--brand)" in body for sels, body, _ in _rules(css))


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
