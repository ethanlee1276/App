"""The second parlay pool is drawn, and drawn apart.

The screen learned to run over the Most Likely board on 2026-09-06 and
the payload reached the page with nothing to draw it — a feature only
the database could see, which is the shape this repo keeps finding in
itself: `cap_notes` rode in every board for a month unread, and the
correlation store recorded a `sport` nobody checked.

TWO THINGS THIS FILE GUARDS.

One renderer, not two. The doctrine, the verdict, the probation note and
the cards are identical for both pools because the SCREEN is identical —
only the legs differ, and the payload says which. Copying it would have
left two of them to drift.

And drawn APART. A likely ticket is paper measuring paper: its legs are
ranked leans, not bets. A reader who cannot tell the two records apart
on the page has exactly the problem the journal would have had without
its `source` column.

Run directly: `python3 tests/test_likely_parlay_render.py`
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ",
                                          "\nconst ", "\nlet ")]
    return APP[i:min([e for e in ends if e != -1] or [len(APP)])]


def test_one_renderer_serves_both_pools():
    body = _fn("renderParlays")
    assert 'renderParlays(key = "parlays", hostId = "parlays-body")' in body
    # It must read the payload THROUGH the parameter, or the second call
    # renders the first board's tickets under the second board's heading.
    assert "state.data[key]" in body, body[:400]
    assert "state.data.parlays" not in body, "the key parameter is bypassed"


def test_both_pools_are_actually_drawn():
    assert "renderParlays();" in APP
    assert 'renderParlays("likely_parlays", "likely-parlays-body");' in APP


def test_each_pool_has_its_own_host():
    for el in ("parlays-body", "likely-parlays-body"):
        assert f'id="{el}"' in HTML, el
    # And they are distinct elements, or one overwrites the other.
    assert HTML.count('id="likely-parlays-body"') == 1
    assert HTML.count('id="parlays-body"') == 1


def test_the_paper_caveat_is_on_the_page_not_only_in_the_code():
    """The legs are leans. A reader seeing a ticket needs to know that
    before they read a price off it."""
    i = HTML.index('id="likely-parlays-title"')
    block = HTML[i:i + 700]
    assert "PAPER" in block, block[:300]
    assert "never staked" in block
    assert "leans rather than bets" in block


def test_the_two_records_are_named_as_separate_on_the_page():
    i = HTML.index('id="likely-parlays-title"')
    block = HTML[i:i + 700]
    assert "own column of the Record page" in block, block[:300]


def test_the_shape_guard_still_covers_the_second_pool():
    """`nfl_build.py --games-only` once shipped `"parlays": []` — truthy,
    so the guard waved it through and the panel rendered itself out of
    undefined. Whatever produces `likely_parlays` can lie the same way,
    and it reaches the same guard because it is the same function."""
    body = _fn("renderParlays")
    assert 'if (!z || typeof z !== "object" || Array.isArray(z))' in body


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
