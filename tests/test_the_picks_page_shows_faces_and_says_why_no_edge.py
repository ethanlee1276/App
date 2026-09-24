"""The Picks page: every row wears its face or crest, and an empty Edge
board says why and shows the closest calls.

Ethan, 2026-09-24, on the Picks page: "it's not showing player or team
headshots and logos, and 2, it's not showing any edge bets". The rows were
drawn by `deckPickRow`, which had no mark; every other surface draws
`betMark`. And the Edge column printed "0 bets" over an empty box on a
night nothing cleared the bar — true, and read as broken.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_every_pick_row_wears_its_mark():
    row = _fn("deckPickRow")
    assert '`<span class="hd-mark">${betMark(r, 36)}</span>`' in row
    assert "${mark}<div class=\"hd-what\">" in row


def test_an_empty_edge_board_says_why_and_shows_the_closest_calls():
    page = _fn("renderTonight")
    assert "const edge = [...props, ...bets];" in page, "game lines count as edge rows too"
    assert "marketBest(tonightSignals())" in page
    assert "No bet cleared the bar tonight." in page
    assert "note: whyNotStaked(r)" in page, "each closest call says why it missed"
    assert 'small: "edge — under the bar"' in page


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        try:
            fn(); print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1; print(f"FAIL  {name}: {exc}")
    print(f"\n{2 - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
