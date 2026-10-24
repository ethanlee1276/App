"""The game plan sets our number against real books only, and a play sits
in one step. The box, 2026-09-27, LAC@BUF: "Keleki Latu OVER 0.0
Receptions -110 proxy" under "where we disagree with the market", "Ray
Davis OVER 17.5 -110 proxy" under plays to avoid, and Dalton Kincaid OVER
56.5 receiving yards under BOTH plays that fit and plays to avoid."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gameplan as P                                   # noqa: E402

G = {"home": "BUF", "away": "LAC", "date": "2026-09-27", "kickoff": "13:00", "spread": -7.0, "total": 50.5,
     "scan": {"units": {}, "injuries": [], "method": {"teams": 32}}}


def _prop(player, market, line, book, **kw):
    return {"player": player, "team": "BUF", "opponent": "LAC", "position": "TE", "market": market,
            "market_label": market, "side": "OVER", "line": line, "odds": -110, "book": book,
            "hit_prob": 0.55, **kw}


def test_a_proxy_line_is_not_the_market():
    props = [_prop("Keleki Latu", "receptions", 0.0, "proxy", raw_prob=0.72, fair_prob=0.50),
             _prop("Dalton Kincaid", "receptions", 4.5, "FanDuel", raw_prob=0.72, fair_prob=0.50)]
    assert [r["player"] for r in P.gaps(G, props)] == ["Dalton Kincaid"]


def test_a_proxy_line_is_not_a_play_to_avoid():
    lines = [{"book": "FanDuel", "line": 56.5, "over_odds": -111, "under_odds": -109}]
    props = [_prop("Ray Davis", "rush_yds", 17.5, "proxy", trend_delta=43.6),
             _prop("Dalton Kincaid", "rec_yds", 56.5, "FanDuel", trend_delta=43.5, all_lines=lines)]
    assert [r["player"] for r in P.avoids(G, [], props)] == ["Dalton Kincaid"]


def test_a_warned_play_is_not_also_a_fit():
    lines = [{"book": "FanDuel", "line": 56.5, "over_odds": -111, "under_odds": -109}]
    props = [_prop("Dalton Kincaid", "rec_yds", 56.5, "FanDuel", trend_delta=43.5, all_lines=lines)]
    matchup = {"td": [], "props": [dict(props[0], model_prob=0.55, kind="prop")]}
    plan = P.plan_for(G, {"players": []}, props, [], matchup)
    by = {s["key"]: s for s in plan["steps"]}
    assert [r["player"] for r in by["avoid"]["rows"]] == ["Dalton Kincaid"]
    assert by["fits"]["rows"] == [], "one play, one step — the warning wins"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
