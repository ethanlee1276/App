"""The tile says twenty and the grid draws two.

Ethan, 2026-09-04: "mlb best bets is only showing 2 bets but then it says
it has 20 but only showing 2."

TWO CHAINS, ONE PAGE. `engine/mlb/pipeline.py` stamps `hr_featured` on
every home-run prop — true for the three that lead the Long Shots page,
false for the rest, because "the Long Shots page and the Recommended page
show the SAME three, and there is no fourth". That is a DISPLAY rule: a
non-featured home run still passed every gate, still carries a stake, and
is still journaled.

    tonightSignals().props   passesFilters only   → the tile, Best Bets
    renderRecommended        + the display rule   → the card grid
    renderTonight            + the display rule   → the Tonight tab

The tile and the grid sit one above the other on the Dashboard. On an MLB
night whose recommended set is mostly home runs they disagree, and
nothing on the page reconciles them.

NEITHER NUMBER IS CHANGED HERE. Twenty were recommended and two belong on
this board; both are true, and the page now says so. The alternative —
picking one and deleting the other — is a product call that wants the
measurement first (docs/DROPLET_CHECKS.md).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name: str) -> str:
    """One function's source, to its closing brace at column zero."""
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j]


# --- the predicate ----------------------------------------------------------
def test_the_display_rule_has_one_definition():
    """It was written out three times as a bare `hr_featured !== false`
    comparison. Three copies of a rule that must agree is how the tile
    and the grid drifted in the first place."""
    assert "function heldForLongShots(" in APP
    assert "hr_featured !== false" not in APP, \
        "the raw comparison is back beside the predicate"
    assert APP.count("r.hr_featured === false") == 1, \
        "the field is read outside the predicate again"


def test_every_surface_that_hides_them_uses_it():
    # The Tonight tab's reader is `tonightPick` since 2026-09-05 (one
    # reader for the single-league tab and the all-sports page).
    for fn in ("renderRecommended", "tonightPick"):
        assert "heldForLongShots(" in _fn(fn), fn


def test_the_pipeline_still_stamps_what_the_page_reads():
    """A page-side predicate against a field nothing sets is a filter
    that never fires. The MLB pipeline is the only writer."""
    src = (ROOT / "engine" / "mlb" / "pipeline.py").read_text()
    assert 'r["hr_featured"] = r["player"] in featured' in src
    assert "LONGSHOT_BOARD = 3" in src


# --- what the page now says -------------------------------------------------
def test_the_grid_counts_the_recommended_picks_it_will_not_draw():
    body = _fn("renderRecommended")
    assert "const elsewhere = recs.filter((r) => r._ok && heldForLongShots(r));" in body, \
        "the gap is not measured, so it cannot be named"


def test_the_gap_is_named_with_a_number_and_a_destination():
    body = _fn("renderRecommended")
    i = body.index("elsewhereNote")
    seg = body[i:i + 900]
    assert "${elsewhere.length}" in seg, seg[:200]
    assert "recommended" in seg, seg[:200]
    assert "#longshots" in seg, "it says they are missing and not where they are"


def test_the_note_is_actually_rendered():
    """Computed and never appended is the shape of half the bugs in this
    repo's history."""
    body = _fn("renderRecommended")
    assert "host.innerHTML += elsewhereNote;" in body, body[-600:]


def test_an_empty_grid_does_not_blame_the_sliders_for_a_display_rule():
    """"No props clear your filters" is FALSE when every one of them did
    and a display rule held them — and it sends a reader to a knob that
    cannot change the answer, the same wrong advice the census branch
    beside it exists to stop giving."""
    body = _fn("renderRecommended")
    i = body.index("} else if (elsewhere.length) {")
    seg = body[i:i + 900]
    assert "home-run dart" in seg, seg[:200]
    assert "#longshots" in seg, seg[:200]
    assert "journaled" in seg, "it does not say they are still real bets"
    # And the slider message is still there for the case it IS the answer.
    assert "No props clear your filters" in body


def test_the_analyzed_note_no_longer_absorbs_them():
    """`hidden` used to be `recs.length - visible.length`, which swallowed
    the recommended-but-not-drawn picks into a sentence about a thousand
    analyzed rows. A reader chasing two missing picks was handed a number
    they never asked about."""
    body = _fn("renderRecommended")
    assert ("const hidden = recs.length - visible.length - elsewhere.length;"
            in body), body[-800:]


def test_neither_number_is_silently_changed():
    """The tile still counts every recommended pick; the grid still draws
    the featured ones. This change adds a sentence, it does not pick a
    winner — that call wants the measurement in docs/DROPLET_CHECKS.md."""
    sig = _fn("tonightSignals")
    assert "heldForLongShots" not in sig, \
        "the tile quietly stopped counting them — that is a product call"
    assert "props: (d.recommendations || []).filter(passesFilters)," in sig
    best = _fn("renderBestBets")
    assert "heldForLongShots" not in best, \
        "the Best Bets picks box quietly stopped listing them"


# --- the arithmetic, on rows -------------------------------------------------
def _rows(n_hr_featured=2, n_hr_other=18, n_plain=0):
    rows = []
    for i in range(n_hr_featured):
        rows.append({"market": "home_runs", "hr_featured": True})
    for i in range(n_hr_other):
        rows.append({"market": "home_runs", "hr_featured": False})
    for i in range(n_plain):
        rows.append({"market": "hits"})
    return rows


def test_the_reported_shape_reproduces():
    """Twenty recommended, two drawn — the split Ethan described, if the
    other eighteen are non-featured home runs."""
    rows = _rows()
    counted = len(rows)
    drawn = len([r for r in rows if r.get("hr_featured") is not False])
    assert (counted, drawn) == (20, 2), (counted, drawn)


def test_a_prop_with_no_hr_featured_key_is_always_drawn():
    """Every non-home-run market, and every sport but MLB, carries no
    such key. `undefined === false` is false, which is the behaviour —
    asserted rather than assumed, because a predicate that hid them would
    empty every other board."""
    for r in ({"market": "hits"}, {"market": "strikeouts"},
              {"market": "anytime_td"}, {}):
        assert r.get("hr_featured") is not False, r


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
