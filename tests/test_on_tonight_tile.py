"""The Dashboard's lead tile is called what it counts.

Ethan, 2026-09-05: the tile read "Recommended bets: 20" over a grid that
drew 2. The 20 was right — new picks plus the open bets still riding, by
his own 09-03 call — and the word was wrong. The number and what it
counts are unchanged; the label says "On tonight" and the new/riding
split leads the sub-line in bold.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def test_the_label_says_what_it_counts_and_the_count_is_unchanged():
    i = APP.index('k: "On tonight"')
    block = APP[i:i + 700]
    assert "to: live, dec: 0, lead: true" in block, "the number is still new + riding"
    assert 'k: "Recommended bets"' not in APP, "the old label is gone from the tiles"
    assert "const live = staked.length + riding.length;" in APP


def test_the_split_leads_the_subline_in_bold():
    i = APP.index('k: "On tonight"')
    block = APP[i:i + 700]
    assert '<b class="tile-split">${staked.length} new · ${plural(riding.length, "riding")}</b> at the' in block
    assert block.index("tile-split") < block.index("don’t add at tonight’s number")
    j = CSS.index(".tile-sub .tile-split {")
    assert "font-weight: 700" in CSS[j:j + 120] and "var(--text)" in CSS[j:j + 120]


def test_the_methodology_page_names_the_tile_it_refers_to():
    assert 'the "On tonight"\n      tile counts' in APP
    assert '"Recommended bets"\n      tile' not in APP


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
