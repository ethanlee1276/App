"""The phone Home's banner art is neither shown nor fetched, the four doors
keep the top of the deck, and nothing sits above them.

Audit 2026-09-30, O25 (roadmap #40) turned the banner art off on phones and
put two lines above the doors: the record ("447-490 · +1.1% ROI over 937
graded bets") and tonight's verdict ("No edge tonight · 24 on Most Likely").
Ethan, 2026-10-01, circling those two lines on the phone Home: "Please
remove what I circled it's ugly and we have other spots to display this
info." The record has its ribbon on the deck and its own page; tonight's
picks have Most Likely, Edge Picks and the Pick of the Day card. The
banner art stays off.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def test_nothing_sits_above_the_doors():
    assert "deckBriefHTML" not in APP and "hd-brief" not in APP and "hd-brief" not in CSS
    assert "toolsSec.prepend" not in _fn("renderHomeDeck")


def test_the_banner_art_is_neither_shown_nor_fetched_on_a_phone():
    hero = _fn("brandHeroHTML")
    assert '<source media="(max-width: 720px)" srcset="data:image/gif;base64,' in hero
    assert "<picture>" in hero and "</picture>" in hero
    i = CSS.index("/* The banner art is off on phones")
    assert ".qt-brand-art { display: none; }" in CSS[i:i + 300]


def test_the_deck_order_ethan_set_is_kept():
    i = APP.index("const HOME_DECK_ORDER = ")
    order = json.loads(APP[i + len("const HOME_DECK_ORDER = "):APP.index(";", i)])
    assert order[0] == "tools" and order.index("games") < order.index("likely")


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
