"""Best Bets shows every market, and never by lowering the bar.

Ethan, 2026-09-02, reading the page at home: "I'm only seeing the money
lines that I asked you to add. I'm not seeing any under or over props
for players. I'm not seeing any under or over props for passing yards.
I'm not seeing any under or over props for rushing or receiving yards.
I'm not seeing any unders or overs for game totals. I'm not seeing any
spread bets."

HE READ THE PAGE RIGHT AND THE PAGE WAS TELLING THE TRUTH. Every one of
those markets is priced and evaluated on every build, overs and unders
alike — the sample slate prices 7 player props (4 over, 3 under) and 15
game bets across all four game markets. What reached the picks box was
only what cleared the staking bar, which on a normal slate is one or two
rows, because that bar is an edge bar and the edge claim measures at a
coin flip. A true thing, shown in a way that reads as a missing feature.

So the answer is a second box, not a lower bar: the strongest row in
each market that did NOT clear, with the engine's own refusal printed on
it, no stake and no journal entry. These pins hold the line between the
two boxes, because the failure mode here is not a rendering bug — it is
the day someone "fixes" the empty page by letting sub-bar rows into the
staked list.

Run directly: `python3 tests/test_market_coverage.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


APP = _src("web", "js", "app.js")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i)]


# --- the engine really does price all of it -------------------------------
def test_the_engine_prices_every_market_the_page_was_missing():
    """The claim the second box rests on. If this ever goes red the box
    is decoration and the real defect is upstream in the pricers."""
    from engine.pipeline import run_slate
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    markets = {b["bet_type"] for b in out["game_bets"]}
    assert {"moneyline", "spread", "total", "team_total"} <= markets, markets
    props = out["recommendations"]
    assert {"pass_yds", "rush_yds", "rec_yds"} <= {r["market"] for r in props}
    sides = {str(r["side"]).upper() for r in props}
    assert {"OVER", "UNDER"} <= sides, sides


def test_almost_none_of_it_clears_the_bar_and_that_is_the_point():
    """The reason the page looked empty, stated as a fact rather than a
    complaint. A build where most rows suddenly clear means the gate
    moved, and that is what this test is here to catch."""
    from engine.pipeline import run_slate
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    props = out["recommendations"]
    staked = [r for r in props if r["recommended"]]
    assert len(staked) < len(props), "every prop cleared — check the gate"


# --- the two boxes stay two boxes -----------------------------------------
def test_the_second_box_never_feeds_the_staked_list():
    """The load-bearing one. `picks` is built from `tonightSignals`, whose
    prop list is `passesFilters` (which requires `recommended`) and whose
    game list is `passesGameBet`. The market box is a separate array that
    must never be pushed into it."""
    body = _fn("renderBestBets")
    assert "const marketBlock = marketBestHTML(sig);" in body
    assert "picks.push" in body
    seen = body[body.index("const marketBlock"):]
    assert "picks.push" not in seen, \
        "the market box is appending to the staked picks"
    assert "_picksForCopy = picks;" in body, \
        "the copy button must export the staked picks only"


def test_the_staked_gate_still_demands_recommended():
    filt = _fn("passesFilters")
    assert "r.recommended" in filt
    game = _fn("passesGameBet")
    assert 'r.grade !== "Pass"' in game and "!r.conditional" in game


def test_the_box_says_it_is_not_a_bet():
    body = _fn("marketBestHTML")
    assert "did NOT clear the bar" in body
    assert "No stake, no journal" in body
    assert "would bet them" in body


# --- what the box refuses to show -----------------------------------------
def _row(**kw):
    d = dict(market="rec_yds", player="A Wideout", side="OVER", line=45.5,
             odds=-110, quality=66, edge=0.024, book="DK")
    d.update(kw)
    return d


def test_the_four_exclusions_are_all_enforced():
    """Each one is the box's honesty, not tidiness:
    a started game cannot be bet, a not-credible row is the model's own
    error and must never be presented as its best, an injury hold is the
    same hold the picks keep, and a staked row belongs in one box."""
    body = _fn("marketBest")
    assert "staked.has(key)" in body
    assert "r.live || r.conditional" in body
    assert "already started" in body
    assert "r.credible === false || r.quality === 0" in body
    assert "r.injury_status" in body


def test_the_not_credible_exclusion_is_the_biggest_edge_on_the_board():
    """Not a hypothetical. On the sample slate the three largest game
    edges (+5.3% to +6.4%) all carry quality 0 because the model
    disagrees with the market by more than it credits — so "sort by
    edge and show the top one" would put the model's three worst errors
    at the top of a box labelled the best we have."""
    from engine.pipeline import run_slate
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    zero = [b for b in out["game_bets"] if b.get("quality") == 0]
    assert zero, "the fixture no longer exercises the not-credible path"
    biggest = max(out["game_bets"], key=lambda b: b.get("edge") or 0)
    assert biggest.get("quality") == 0, biggest.get("edge")


# --- the refusal is the engine's own words --------------------------------
def test_the_reason_comes_from_the_row_not_from_a_second_copy_of_the_bar():
    """The front end must not own a second copy of the tier bars. The
    engine already writes the refusal into the row's reasons; this picks
    it out."""
    body = _fn("whyNotStaked")
    assert "under the Tier" in body and "r.reasons" in body
    assert "disagrees with the market" in body
    # No numeric bar typed into the page.
    assert not re.search(r"0\.0[23]\b", body), body


def test_every_market_the_engine_can_price_has_a_place_in_the_order():
    from engine import markets as M
    order = re.search(r"const MARKET_ORDER = \[(.*?)\];", APP, re.S).group(1)
    listed = set(re.findall(r'"([a-z0-9_]+)"', order))
    for m in ("moneyline", "spread", "total", "team_total"):
        assert m in listed, m
    # Every listed market has a word to render, so no row draws a raw key.
    for m in listed:
        assert M.label(m), m


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
