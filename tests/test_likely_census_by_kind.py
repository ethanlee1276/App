"""The likelihood census says where each KIND of row died.

Ethan, 2026-09-08: "Ok it seems like we have player props just barley
any money money lines are touchdown crap so maybe we should look into
that for the NFL most likely bets."

His census off the droplet that morning could not answer him. It is one
line per reason across three makers — "under the likelihood floor: 212"
is scorers, props and game cards in one number — and a shelf whose rows
were never handed in at all prints nothing, which reads exactly like a
shelf whose rows were all refused. Empty feed and emptying bar are
different faults with different fixes, and the census existed to tell
them apart.

`likely.build` now also fills `census_by_kind`: for each of "td",
"prop" and "game", how many rows were OFFERED, how many the bar KEPT,
how many were a DUPLICATE of a seated row, how many were SHOWN once the
caps ran, and the refusals by reason. The football boards publish it
as `likely_census_by_kind` beside the flat `likely_census`, which is
unchanged — it is the same refusals, summed.

Run directly: `python3 tests/test_likely_census_by_kind.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                                  # noqa: E402

FLOOR = "under the likelihood floor"


def _td(player="A Back", prob=0.62, **kw):
    row = {"player": player, "team": "DET", "opponent": "CHI", "book": "DraftKings",
           "odds": -180, "model_prob": prob, "implied_prob": 0.58, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [1, 0, 1], "game_date": "2026-09-14"}
    row.update(kw)
    return row


def _prop(player="A Rusher", **kw):
    row = {"player": player, "team": "DET", "opponent": "CHI", "market": "rush_yds",
           "market_label": "rush_yds", "side": "over", "line": 62.5, "book": "DK",
           "odds": -110, "has_market": True, "fair_prob": 0.52, "projection": 70.0,
           "ev_per_unit": 0.02, "reasons": ["because"], "recent_values": [66, 71, 58],
           "date": "2026-09-14", "hit_prob": 0.58, "raw_prob": 0.60, "alt_lines": []}
    row.update(kw)
    return row


def _game(**kw):
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             # A real NFL/CFB game card always names the book posting the
             # side it took, and the board refuses one that does not
             # (tests/test_game_price_names_its_book.py). A fixture
             # without it tests a card the system cannot produce.
             book="DraftKings",
             has_market=True, home="DET", away="CHI", team="DET", pick="DET",
             pick_is_home=True, pick_label="DET ML", side="", line=0.0,
             matchup="CHI @ DET", win_prob=0.64, fair_prob=0.62, edge=0.02,
             odds=-165, home_odds=-165, away_odds=140, ev_per_unit=0.03,
             confidence=6.0, stake_units=0.0, grade="Pass", credible=True,
             headline="DET ML", reasons=[], recommended=False, live=False,
             date="2026-09-14")
    d.update(kw)
    return d


def _spread(**kw):
    d = dict(bet_type="spread", market="spread", market_label="Spread", has_market=True,
    book="DraftKings",
             home="DET", away="CHI", team="DET", side="", line=-3.5, pick_label="DET -3.5",
             matchup="CHI @ DET", win_prob=0.52, fair_prob=0.50, edge=0.02, odds=-110,
             other_odds=-110, ev_per_unit=0.0, confidence=5.0, stake_units=0.0,
             grade="Pass", credible=True, headline="DET -3.5", reasons=[],
             recommended=False, live=False, date="2026-09-14")
    d.update(kw)
    return d


def _build(**kw):
    flat: dict = {}
    kinds: dict = {}
    board = K.build(kw.pop("props", []), kw.pop("td_picks", None), kw.pop("td_watch", None),
                    sport="nfl", census=flat, census_by_kind=kinds,
                    game_bets=kw.pop("game_bets", None), **kw)
    return board, flat, kinds


def test_each_kind_counts_what_it_was_offered_kept_and_refused():
    board, flat, kinds = _build(
        td_picks=[_td()],
        td_watch=[_td("Under Floor", prob=0.40), _td()],          # the second is a duplicate
        props=[_prop(), _prop("No Market", has_market=False)],
        game_bets=[_game(), _spread()])
    assert set(kinds) == {"td", "prop", "game"}, kinds
    # KEPT AND SHOWN ARE DIFFERENT NUMBERS, and the gap is the reserve.
    # `kept` counts rows that cleared the real bar; `shown` counts rows
    # that reached the page, which since 2026-09-09 includes the labelled
    # rows a thin shelf is topped up with. The sub-floor touchdown and
    # the sub-floor game line below are refused at the real bar — the
    # census says so — and shown underneath the rows that cleared.
    # The sub-floor TD is NOT topped up, and the reason is the whole
    # design: it sits 18 points under the market's own number, which is
    # `MAX_CREDIBLE_EDGE` — a TRUTH bar. The reserve relaxes the floor
    # and nothing else, so a row the board thinks is mispriced stays off
    # the page whether the shelf is thin or not.
    assert kinds["td"] == {"offered": 3, "kept": 1, "duplicate": 1, "shown": 1,
                           "refused": {FLOOR: 1}}, kinds["td"]
    assert kinds["prop"] == {"offered": 2, "kept": 1, "duplicate": 0, "shown": 1,
                             "refused": {"no real book price": 1}}, kinds["prop"]
    assert kinds["game"] == {"offered": 2, "kept": 1, "duplicate": 0, "shown": 2,
                             "refused": {FLOOR: 1}}, kinds["game"]
    assert sorted(r["kind"] for r in board) == ["game", "game", "prop", "td"]
    # …and the one row beyond those that cleared says what it is.
    assert sum(1 for r in board if r.get("reserve")) == 1, board


def test_the_flat_census_is_the_kinds_summed():
    _board, flat, kinds = _build(
        td_watch=[_td("x", prob=0.40), _td("y", prob=0.30)],
        props=[_prop("p", hit_prob=0.50, raw_prob=0.50), _prop("q", has_market=False)],
        game_bets=[_spread(), _game(live=True)])
    summed: dict = {}
    for k in kinds.values():
        for why, n in k["refused"].items():
            summed[why] = summed.get(why, 0) + n
    assert flat == summed, (flat, summed)
    assert flat[FLOOR] == 4 and flat["the game is already under way"] == 1, flat
    assert kinds["td"]["refused"] == {FLOOR: 2}
    assert kinds["prop"]["refused"] == {FLOOR: 1, "no real book price": 1}
    assert kinds["game"]["refused"] == {FLOOR: 1, "the game is already under way": 1}


def test_the_funnel_adds_up_for_every_kind():
    _board, _flat, kinds = _build(
        td_picks=[_td("a"), _td("b", prob=0.2)], td_watch=[_td("a"), _td("c")],
        props=[_prop("p"), _prop("p"), _prop("r", has_market=False)],
        game_bets=[_game(), _game(), _spread()])
    # SHOWN MINUS THE RESERVE IS WHAT THE BAR KEPT. This asserted
    # `shown <= kept` until 2026-09-09, which was true while every row on
    # the page had cleared the real bar. A thin shelf is topped up now,
    # so the page can carry rows the bar refused — and the gap between
    # the two numbers is exactly those rows, which is the invariant worth
    # holding: nothing appears that the census cannot account for.
    reserve_by_kind: dict = {}
    for r in _board:
        if r.get("reserve"):
            k = r.get("kind") or "prop"
            reserve_by_kind[k] = reserve_by_kind.get(k, 0) + 1
    for kind, f in kinds.items():
        assert f["offered"] == f["kept"] + f["duplicate"] + sum(f["refused"].values()), (kind, f)
        assert f["shown"] - reserve_by_kind.get(kind, 0) <= f["kept"], \
            (kind, f, reserve_by_kind)
    assert kinds["prop"]["duplicate"] == 1 and kinds["game"]["duplicate"] == 1


def test_shown_is_after_the_caps_and_kept_is_before_them():
    """Three scorers clear the bar; a board of one seats one. The bar
    kept three and the caps showed one — two different facts."""
    board, _flat, kinds = _build(td_watch=[_td("a"), _td("b"), _td("c")], limit=1)
    assert len(board) == 1
    assert kinds["td"]["kept"] == 3 and kinds["td"]["shown"] == 1, kinds["td"]
    assert kinds["td"]["refused"] == {}


def test_nothing_offered_reads_as_nothing_offered():
    _board, flat, kinds = _build()
    assert flat == {}
    for kind in ("td", "prop", "game"):
        assert kinds[kind] == {"offered": 0, "kept": 0, "duplicate": 0, "shown": 0,
                               "refused": {}}, kinds[kind]


def test_a_caller_that_did_not_ask_gets_the_census_it_always_got():
    flat: dict = {}
    board = K.build([_prop(), _prop("q", has_market=False)], sport="nfl", census=flat)
    assert len(board) == 1 and flat == {"no real book price": 1}


def test_the_football_boards_publish_it_beside_the_flat_census():
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    cfb = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert '"likely_census_by_kind": _likely_kinds,' in pipe
    assert "census_by_kind=_likely_kinds)" in pipe
    assert 'out["likely_census_by_kind"] = _ml_kinds' in cfb
    assert "census_by_kind=_ml_kinds)" in cfb
    assert "likely_census_by_kind" in checks and "`td` offered 0" in checks


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
