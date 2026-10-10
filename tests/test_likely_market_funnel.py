"""The Most Likely board says, market by market, where its props went.

Ethan, 2026-09-15: "some days we'd be showing four or five passing
props, and then the next day they'd all be gone ... I didn't see any
passing yard props." A census by reason across the whole board cannot
say which market lost its rows or to which bar. This can, and the page
prints it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(player, market, **kw):
    got = {"player": player, "team": "DET", "opponent": "CHI", "market": market,
           "market_label": market, "side": "over", "line": 62.5, "book": "DK",
           "odds": -110, "has_market": True, "fair_prob": 0.58, "projection": 70.0,
           "ev_per_unit": 0.02, "reasons": ["because"],
           "recent_values": [70, 71, 68, 66], "date": "2026-09-14",
           "hit_prob": 0.62, "raw_prob": 0.63, "engine_raw_prob": 0.63}
    got.update(kw)
    return got


def test_each_market_is_counted_from_offered_to_shown():
    props = [_row("A Back", "rush_yds"),
             _row("B Back", "rush_yds", has_market=False, book="proxy"),
             _row("C End", "rec_yds"),
             _row("D Quarterback", "pass_yds", hit_prob=0.50, raw_prob=0.50,
                  engine_raw_prob=0.50)]
    kinds: dict = {}
    board = K.build(props, sport="nfl", census_by_kind=kinds)
    ms = kinds["prop"]["markets"]
    assert set(ms) == {"rush_yds", "rec_yds", "pass_yds"}, ms
    assert ms["rush_yds"]["offered"] == 2 and ms["rush_yds"]["priced"] == 1
    assert ms["rush_yds"]["shown"] == 1 and ms["rush_yds"]["refused"] == {"no real book price": 1}
    assert ms["rec_yds"] == {"offered": 1, "priced": 1, "kept": 1, "shown": 1, "refused": {}, "laddered": 0, "ladder": {}}
    # The quarterback under the main floor is counted against HIS market:
    # refused at the bar, then seated by the reserve at the lower floor —
    # and the funnel says both, which is exactly what a reader needs to
    # tell a thin market from a missing one.
    assert ms["pass_yds"]["offered"] == 1 and ms["pass_yds"]["kept"] == 0
    assert ms["pass_yds"]["refused"] == {"under the likelihood floor": 1}
    qb = [r for r in board if r["player"] == "D Quarterback"]
    assert qb and qb[0].get("reserve") is True
    assert ms["pass_yds"]["shown"] == 1                       # seated from the reserve
    assert {r["market"] for r in board if r.get("kind", "prop") == "prop"} <= {"rush_yds", "rec_yds", "pass_yds"}
    # The board-wide census still adds up to the per-market ones.
    total = sum(sum(m["refused"].values()) for m in ms.values())
    assert sum(kinds["prop"]["refused"].values()) == total


def test_the_page_prints_it_under_the_board():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function likelyMarketFunnel(" in app
    i = app.index("function renderLikely(")
    assert "likelyMarketFunnel(state.data.likely_census_by_kind)" in app[i:i + 4000]
    k = app.index("function likelyMarketFunnel(")
    body = app[k:app.index("\nfunction ", k + 10)]
    for word in ("offered", "priced", "shown"):
        assert word in body
    # The game-line and touchdown kinds on the same ledger (Ethan,
    # 2026-09-15, on the MLB board: "There is no money lines or pitchers
    # props or game totals") — a kind the slate handed nothing is left
    # off rather than printed as a zero row.
    assert '(k.game || {}).offered > 0' in body and '"Game lines"' in body
    assert '(k.td || {}).offered > 0' in body and '"Touchdowns"' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
