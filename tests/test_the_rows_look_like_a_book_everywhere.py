"""v5: the rows look like a book, everywhere — starting with Most Likely.

Ethan, 2026-09-22: "I didn't see any redesigns to … the section for
the most likely bets on each page." The shelf row on the home and the
Most Likely page still drew the old row. It now reads the way the
Picks page and the deck read: name, the game and the book beneath, the
price in a grey pill and our number in a green one, same door. The
Most Likely page's shelves lead with rows and keep the full cards one
tap away. And the first motion of the pass: rows rise briefly, and the
ribbon's ring sweeps in from zero.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(name)
    return re.sub(r"^\s*//.*$", "", APP[i:APP.index("\n}\n", i)], flags=re.M)


def test_the_most_likely_row_carries_the_price_and_the_number_as_pills():
    row = _fn("likelyRow")
    assert '<span class="hd-num">${r.odds != null' in row
    assert '`<span class="hd-o">${american(r.odds)}</span>`' in row, "the price in the grey pill"
    assert '<span class="ml-pct hd-p">${pct}</span>' in row, "our number in the green pill"
    k = row[row.index('<span class="k">'):row.index("</span></span>", row.index('<span class="k">'))]
    assert "american(r.odds)" not in k, "the sub-line no longer repeats the price"
    assert "r.book" in k, "the book stays in the sub-line"
    assert "${likelyOpen(r)}" in row, "same door"


def test_the_shelves_lead_with_rows_and_keep_the_cards_one_tap_away():
    shelf = _fn("likelyShelf")
    assert '<div class="ml-rows">${rows.map(likelyRow).join("")}</div>' in shelf
    assert '<details class="tn-full">' in shelf and '<div class="cards">${rows.map(likelyCard).join("")}</div>' in shelf, "no card lost"
    assert shelf.index("ml-rows") < shelf.index("tn-full"), "rows first"
    assert 'id="shelf-${escapeAttr(sh.key || "")}"' in shelf, "the jump bar still lands here"


def test_the_row_pills_are_the_decks_and_the_old_blob_is_gone():
    i = CSS.index(".ml-row .ml-pct {")
    rule = CSS[i:CSS.index("}", i)]
    assert "background" not in rule and "border-radius" not in rule, "the old green blob"
    assert ".hd-p {" in CSS and ".hd-o {" in CSS
    assert ".ml-row .hd-num { flex: 0 0 auto; }" in CSS


def test_rows_rise_briefly_and_the_live_strip_does_not():
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert "@keyframes rise { from { opacity: 0; transform: translateY(6px); }" in body
    assert ".ml-rows > .ml-row, .hd-card > .hd-row { animation: rise var(--dur-slow) var(--ease-out) both; }" in body
    assert "animation-delay: calc(var(--dur-fast) * 1.5)" in body, "the stagger is capped"
    assert ".hd-game { animation" not in body and ".hd-strip > .hd-game" not in body, "the live strip redraws on a clock; a rise there would flicker"
    assert re.search(r"\*,\s*\*::before[^{]*\{[^}]*animation-duration", body), "reduced motion must zero it"


def test_the_ring_sweeps_in_from_zero():
    rec = _fn("deckRecordHTML")
    assert 'style="--pc:0" data-pc="${pc}"' in rec, "drawn at zero, handed its number"
    sweep = _fn("sweepRings")
    assert "requestAnimationFrame(() => requestAnimationFrame(() => {" in sweep, "one frame paints the zero; the second moves it"
    assert 'el.style.setProperty("--pc", el.dataset.pc);' in sweep
    assert "sweepRings(host);" in _fn("renderHomeDeck")
    assert '@property --pc { syntax: "<number>"; inherits: false; initial-value: 0; }' in CSS, "unregistered, the arc snaps"
    i = CSS.index(".hd-ring {")
    assert "transition: --pc var(--dur-slow) var(--ease-out);" in CSS[i:CSS.index("}", i)]


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
