"""v5: the Record page leads with its ribbons.

Ethan, 2026-09-22: "I didn't see any redesigns to the record page."
The deck's record tiles — a ring for the hit rate, the W-L, the
headline number, the last five as form dots — now come from one
builder, and the Record page opens with them above its rooms: the
scope in view, and Zeno's book beside it. The receipts room still
begins with the calendar.
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


def test_one_builder_draws_the_ribbons_for_the_deck_and_the_page():
    b = _fn("recordRibbonsHTML")
    assert "function recordRibbonsHTML(rec, ov, recent)" in APP
    assert "if (ov.settled) {" in b and "if (zo.settled) {" in b, "no ribbon over nothing"
    assert 'dots(recent, "status")' in b and 'dots(z.recent, "result")' in b
    assert "return tiles.join(\"\");" in b
    deck = _fn("deckRecordHTML")
    assert "recordRibbonsHTML(rec, rec.overall, rec.recent)" in deck, "the deck draws the same picture"
    assert "const tile =" not in deck, "the deck no longer keeps its own copy"


def test_the_page_opens_with_the_scope_in_view_above_the_rooms():
    i = APP.index("async function renderRecord(")
    body = APP[i:APP.index("\nfunction ", i)]
    # The scope in view, not the pooled number — or, with a window chosen
    # (audit item 5, 2026-09-23), that scope's last N days, cut from its
    # own curve (tests/test_the_record_has_windows.py).
    assert ": recordRibbonsHTML(d, o, src.recent);" in body, "the scope in view, not the pooled number"
    j = body.rindex("host.innerHTML = scopeBar")   # the main assembly; two empty branches use the same opener earlier
    tail = body[j:j + 400]
    assert '(ribbons ? `<div class="hd-stats rec-ribbons">${ribbons}</div>' in tail
    assert tail.index("rec-ribbons") < tail.index("_recordRooms("), "above the rooms"
    assert "sweepRings(host);" in body[j:], "the ring must sweep on this page too"
    assert "const receipts = calendar\n" in body, "the receipts room still begins with the calendar"


def test_the_ribbons_are_spaced_as_a_lead():
    assert ".rec-ribbons { margin: 8px 0 16px; }" in CSS
    assert ".hd-stats {" in CSS


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
