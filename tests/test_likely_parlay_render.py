"""The Most Likely parlays are drawn, and drawn apart (the Parlays page:
web/js/app.js renderParlayPage, engine/twoleg).

The old parlay screen learned to run over the Most Likely board on
2026-09-06 and the payload reached the page with nothing to draw it — a
feature only the database could see. On 2026-10-31 (Ethan: "get rid of the
parlay button and the parlay feature ... make the parlay feature an actual
button ... a section for the edge bet parlays and most likely bet parlays")
the screen's two panels gave way to the Parlays page, a button of its own in
the menu for the four leagues it builds for. What this file guards carries
over.

One renderer, not two. The card, the record line and the empty note are the
same for both pools because the builder is the same; only the legs differ,
and the payload says which pool a ticket belongs to.

And drawn APART. A Most Likely parlay and an Edge parlay are two records. A
reader who cannot tell them apart on the page, or cannot tell a staked
ticket from a tracked one, has exactly the problem the journal would have
had without its `source` column.

Run directly: `python3 tests/test_likely_parlay_render.py`
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
RECORD = (ROOT / "web" / "js" / "record.js").read_text()


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ",
                                          "\nconst ", "\nlet ")]
    return src[i:min([e for e in ends if e != -1] or [len(src)])]


def test_one_renderer_serves_both_pools():
    body = _fn("renderParlayPage")
    assert "TL_POOLS.map(" in body
    # It reads each pool THROUGH its key, or one pool's tickets land under
    # the other's heading.
    assert "z[pool]" in body, body[:400]
    assert "z.edge.tickets" not in body and "z.likely.tickets" not in body, "a pool read by name"


def test_both_pools_are_actually_drawn():
    assert 'const TL_POOLS = [["edge", "Edge parlays"' in APP
    assert '["likely", "Most Likely parlays"' in APP
    assert '["parlays-body", () => renderParlayPage(), true]' in APP


def test_the_page_is_a_button_with_one_host():
    assert HTML.count('id="parlays-body"') == 1
    assert 'data-view="parlays" id="parlays-tab"' in HTML, "a real button in the menu"
    assert 'id="likely-parlays-body"' not in HTML, "the old second panel left with the screen"
    assert 'id="parlay-mode"' not in HTML and 'id="pz-toggle"' not in HTML, "Parlay Mode is gone"


def test_staked_and_tracked_are_said_on_every_ticket():
    card = _fn("tlTicketHTML")
    assert "Staked ${t.stake_units}u" in card and "Tracked · no stake" in card
    page = _fn("renderParlayPage")
    assert "So a parlay is staked only when both legs are picks we stake" in page


def test_the_two_records_are_kept_apart():
    assert 'const pools = [["edge", "Edge parlays"], ["likely", "Most Likely parlays"]];' in RECORD
    line = _fn("tlRecordLine")
    assert "tl[pool]" in line and "x.pool === pool" in line, "each pool's own record and backtest row"


def test_the_shape_guard_still_covers_the_page():
    """A build that ships `"two_leg": []` or nothing at all draws a note,
    never a page rendered out of undefined."""
    body = _fn("renderParlayPage")
    assert 'if (!z || typeof z !== "object" || !z.edge)' in body


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
