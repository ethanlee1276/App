"""Two panels on the Live page: edge bets and Most Likely, kept apart.

Ethan, 2026-09-05: "the most likley bets should also show in the live
page, we need to have two seperate pages in the live page, one for edge
bets, and one for most likley bets."

Most Likely rows journal with `category='likely'` — flat stake, zero
dollar exposure, their own book on the Record page. Neither Live-page
feed selected that category: the open-bet tracker (`mlb_build.py`) and
the sweat (`engine/sweat.py`) both took `('main','longshot')`, so the
likelihood board's rows could not reach the Live tab at all. Both select
them now, and both renderers split by the `category` every row already
carries — the two are different products, and one list would make the
edge count wrong and the likelihood rows look like bets we sized.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
BUILD = (ROOT / "mlb_build.py").read_text()
SWEAT = (ROOT / "engine" / "sweat.py").read_text()


def _fn(name):
    """One function's source. The Live renderers sit at the tail of
    app.js where the next definition is `async function` or nothing at
    all — a slice that looks only for a plain `function` raises there."""
    i = APP.index(f"function {name}(")
    ends = [k for k in (APP.find("\nfunction ", i + 1),
                        APP.find("\nasync function ", i + 1)) if k != -1]
    return APP[i:min(ends) if ends else len(APP)]


# --- the feeds ---------------------------------------------------------------
def test_the_tracker_selects_likely_rows():
    i = BUILD.index("_where = (")
    seg = BUILD[i:i + 200]
    assert "'likely'" in seg, seg


def test_the_cross_sport_count_stays_edge_only():
    """`open_elsewhere` says how many EDGE bets are on other boards. A
    likelihood row is not a bet we sized, so it neither counts there nor
    is subtracted from there."""
    i = BUILD.index("_all_open = _lpc.execute(")
    seg = BUILD[i:i + 300]
    assert "category IN ('main','longshot')" in seg and "'likely'" not in seg
    assert '_edge_shown = sum(1 for r in rows if r.get("category") != "likely")' in BUILD
    assert 'max(0, _all_open - _edge_shown)' in BUILD, \
        "the subtraction still removes the likely rows from the elsewhere count"


def test_the_sweat_selects_likely_rows():
    i = SWEAT.index("where = (")
    seg = SWEAT[i:i + 200]
    assert "'likely'" in seg, seg


def test_a_likely_row_is_journaled_under_that_category():
    """The whole split keys on this literal. If the journal stops writing
    it, both panels silently become one again."""
    src = (ROOT / "engine" / "ledger.py").read_text()
    i = src.index("def log_most_likely(")
    seg = src[i:i + 6000]
    assert "'likely'" in seg or '"likely"' in seg, "log_most_likely no longer stamps the category"


# --- the page ----------------------------------------------------------------
def test_the_tracker_draws_two_panels():
    body = _fn("renderLivePicks")
    assert 'rows.filter((r) => r.category !== "likely")' in body
    assert 'rows.filter((r) => r.category === "likely")' in body
    assert "Open edge bets" in body and "Open Most Likely bets" in body
    assert 'panel(edge, "Open edge bets"' in body, "the edge panel is never rendered"
    assert 'panel(likely, "Open Most Likely bets"' in body, "the likely panel is never rendered"


def test_a_likely_row_never_prints_a_stake_or_a_riding_warning():
    """Flat-staked and never sized: printing "0.10u" or "the price has
    moved off the bar" on a likelihood row would present it as a bet."""
    body = _fn("renderLivePicks")
    assert 'r.category !== "likely" && r.stake_units > 0' in body
    assert 'r.category !== "likely" && offBoard(r)' in body


def test_each_panel_has_its_own_empty_state():
    body = _fn("renderLivePicks")
    assert "No open edge bets on today’s card." in body
    assert "No open Most Likely bets on today’s card" in body


def test_the_sweat_splits_the_same_way():
    body = _fn("renderSweatZone")
    assert 'picks.filter((p) => p.category !== "likely")' in body
    assert 'picks.filter((p) => p.category === "likely")' in body
    assert "The sweat — Most Likely" in body
    assert "likelyPicks.map(row)" in body, "the likely list is split off and never drawn"


def test_the_rows_still_open_a_door():
    """The door on every open bet (Ethan, 2026-08-23) must survive the
    restructure — it is the one function the list reaches for."""
    body = _fn("renderLivePicks")
    assert "ridingAttrs(r)" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
