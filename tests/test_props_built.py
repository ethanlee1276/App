""""4 props analyzed" was the count AFTER pricing, and the other half was
thrown away.

Ethan, from the WNBA board: "these games never went live and we never
made any props." The tile said PROPS ANALYZED 4 on a two-game slate,
which reads as a model that considered almost nothing.

`props_analyzed` is `len(recs)`, and `recs` only holds props that got a
REAL BOOK PRICE. So the number cannot distinguish:

    we had four players' worth of history
    we built two hundred props and a book priced four

Those need opposite fixes — one is an ingest problem, the other is
waiting for a menu to post — and the tile showed the same 4 either way.

THE NUMBER THAT SEPARATES THEM WAS ALREADY BEING COMPUTED. `props_built`
is set from `len(slate.props)`, and sixty lines later `out["counts"]` was
REASSIGNED to a fresh dict, dropping it. Written, then discarded, in the
same function.

The comment right above the census says exactly why it matters — "430
props buildable from history, zero priced, no census, no explanation
anywhere" — which is the failure this was added to prevent, undone by an
assignment three hundred lines further down.

Run directly: `python3 tests/test_props_built.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- the count survives ---------------------------------------------------
def test_the_counts_dict_is_merged_not_replaced():
    """THE BUG. A bare `out["counts"] = {...}` drops everything set
    earlier in the same build."""
    src = _src("nba_build.py")
    assert 'out["counts"] = {**(out.get("counts") or {}),' in src


def test_props_built_is_still_written_before_it():
    src = _src("nba_build.py")
    assert 'out["counts"]["props_built"] = len(slate.props)' in src


def test_the_write_comes_before_the_merge():
    """Order is the whole bug: set, then overwritten."""
    src = _src("nba_build.py")
    assert src.index('out["counts"]["props_built"]') < \
        src.index('out["counts"] = {**(out.get("counts")')


def test_a_merge_actually_keeps_it():
    """The mechanic, not just the source text."""
    earlier = {"props_analyzed": 0, "recommended": 0, "props_built": 214}
    from_picks = {"props_analyzed": 0, "recommended": 0}
    merged = {**earlier, **from_picks,
              "props_analyzed": 4, "recommended": 0}
    assert merged["props_built"] == 214
    assert merged["props_analyzed"] == 4


def test_the_old_shape_would_have_lost_it():
    """Guards the guard: proves the fix is not a no-op."""
    earlier = {"props_built": 214}
    replaced = {**{"props_analyzed": 0}, "props_analyzed": 4}
    assert "props_built" not in replaced
    assert "props_built" in {**earlier, **replaced}


# --- and the page says which of the two it is -----------------------------
def test_the_tile_shows_what_was_built_when_it_exceeds_what_was_priced():
    src = _src("web", "js", "app.js")
    assert "d.counts.props_built > d.counts.props_analyzed" in src
    assert "built from history" in src


def test_the_subtitle_names_the_usual_cause():
    """"No book price yet" is actionable; a bare 4 is not."""
    src = _src("web", "js", "app.js")
    assert "no book price yet" in src


def test_it_says_nothing_extra_when_the_two_agree():
    """Every prop priced is not a diagnosis and should not wear one."""
    src = _src("web", "js", "app.js")
    at = src.index("d.counts.props_built > d.counts.props_analyzed")
    tail = src[at:at + 260]
    assert ': ""' in tail, tail


def test_the_college_board_now_shares_the_subtitle():
    """IT USED TO KEEP ITS OWN, and the reason expired on 2026-09-03.
    CFB counted priced game markets rather than props because it had no
    player model; `engine/cfb/props.py` gave it one, and the branch that
    protected the old sentence would have gone on hiding the new rows.

    The gap the shared subtitle names is exactly college's question —
    "of N built from history — the rest have no book price yet" is the
    honest answer to a Saturday with props built and no player odds
    bought — so cfb_build publishes both halves of it."""
    src = _src("web", "js", "app.js")
    assert '"Markets priced"' not in src
    assert "spreads, totals and moneylines" not in src
    build = _src("cfb_build.py")
    assert '"props_built": len(_built)' in build
    assert '"props_analyzed": sum(1 for r in _built' in build


# --- the census this restores was already argued for ----------------------
def test_the_build_still_carries_the_census_that_explains_the_gap():
    src = _src("nba_build.py")
    assert 'census = {"no_real_price": 0, "no_history": 0}' in src
    assert 'out["gate_census"]' in src


def test_the_reasoning_for_it_is_still_recorded():
    src = _src("nba_build.py")
    assert "zero priced, no census" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
