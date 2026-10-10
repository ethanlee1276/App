"""v5: the desktop has a slip column.

A book keeps what you have going on the right. On a wide screen with
the rail, the deck's riding rows, the record ribbons and Zeno's
tickets live in the rail beside the feed; below 1280px they return to
the deck in its own order, so a phone never sees them move. The same
elements either way: the deck fills them by name, the ring sweeps
wherever they sit. Not a bet slip — the site never takes a bet.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(name)
    return re.sub(r"^\s*//.*$", "", APP[i:APP.index("\n}\n", i)], flags=re.M)


def test_the_column_is_first_in_the_rail_and_holds_the_three_sections():
    start = HTML.index('<aside class="rail"')
    rail = HTML[start:HTML.index("</aside>", start)]   # the sidebar closes an aside first
    rail_clean = re.sub(r"<!--.*?-->", "", rail, flags=re.S)
    first = re.search(r"<div[^>]*>", rail_clean).group(0)
    assert 'id="rail-slip"' in first, "the slip column leads the rail"
    assert 'const SLIP_SECTIONS = ["riding", "record", "zeno"];' in APP
    assert 'const SLIP_MQ = "(min-width: 1280px)";' in APP, "the rail's own breakpoint"


def test_wide_moves_them_in_and_narrow_moves_them_back_in_order():
    body = _fn("placeSlip")
    assert 'document.body.classList.contains("has-rail")' in body, "only where the rail is shown — the home"
    assert "window.matchMedia(SLIP_MQ).matches" in body
    assert "if (s.parentElement !== rail) rail.appendChild(s);" in body
    assert "HOME_DECK_ORDER.slice(HOME_DECK_ORDER.indexOf(k) + 1)" in body, "back into the deck in the deck's order"
    assert "deck.insertBefore(s, after || null);" in body


def test_the_deck_still_fills_and_sweeps_a_moved_section():
    fill = _fn("deckFill")
    assert '|| document.querySelector(`#rail-slip .hd-sec[data-sec="${sec}"]`)' in fill
    deck = _fn("renderHomeDeck")
    assert "placeSlip();" in deck and 'sweepRings(document.getElementById("rail-slip"));' in deck


def test_it_follows_the_rail_and_the_viewport():
    assert "placeSlip();" in _fn("syncRail"), "the rail's show rule places the column"
    assert 'window.matchMedia(SLIP_MQ).addEventListener("change", placeSlip);' in APP


def test_the_column_is_styled_and_nothing_hides_a_phone():
    assert ".rail-slip .hd-sec { margin-bottom: 14px; }" in CSS
    assert ".rail-slip .hd-ribbon { display: grid; grid-template-columns: 56px minmax(0, 1fr); align-items: center; }" in CSS
    assert ".rail-slip .hd-form { grid-column: 1 / -1; margin-top: 8px; }" in CSS, "the form dots go under the words in a 280px column"
    assert ".rail-slip .hd-big { white-space: nowrap; }" in CSS, "the record never breaks mid-number"
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "rail-slip" not in phone, "the phone never sees the column; the sections stay in the deck"


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
