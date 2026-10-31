"""Inside a tier, the stronger matchup ranks first, in every sport.

Ethan, 2026-09-26, after the card fix: Kincaid's card said "Good matchup"
at last, "but it's still listed as the number one pick with the breakout
candidates below him". The tier used the matchup, but the order inside a
tier was our chance alone, and the page re-sorted by chance again, so the
read never touched the ranking. engine/likelyboard now ranks a pick the
matchup backs strongly (a breakout or avoid read, a touchdown matchup of
STRONG_TD of 8 or better) ahead of one it merely backs, then by chance,
and the page's default sort is that same order.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as B                                  # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _read(player, team, opp, read, label, market):
    return {"player": player, "team": team, "opp": opp, "pos": "WR", "read": read, "label": label,
            "lean": [market]}


def _prop(player, team, opp, market, prob, side="OVER"):
    return {"kind": "prop", "player": player, "team": team, "opponent": opp, "market": market,
            "side": side, "line": 4.5, "odds": -130, "model_prob": prob, "implied_prob": prob - 0.03}


def _board(sport, home, away, rows, reads):
    result = {"games": [{"home": home, "away": away}], "recommendations": [],
              "scan_reads": {f"{away}@{home}": {"players": reads}},
              "most_likely": rows, "matchup_picks": [], "td_scenarios": []}
    return B.build(result, sport=sport)["rows"]


def test_a_breakout_ranks_above_a_likelier_good_matchup_in_every_scanned_sport():
    for sport, home, away, market in (("nfl", "MIA", "BUF", "receptions"),
                                      ("cfb", "Georgia", "Tennessee", "receptions"),
                                      ("mlb", "NYY", "BOS", "hits")):
        rows = _board(sport, home, away,
                      [_prop("Dalton Kincaid", away, home, market, 0.70),
                       _prop("Breakout Guy", home, away, market, 0.62)],
                      [_read("Dalton Kincaid", away, home, "good", "Good matchup", market),
                       _read("Breakout Guy", home, away, "breakout", "Breakout candidate", market)])
        assert [r["tier"] for r in rows] == ["top", "top"], (sport, [r["checks"] for r in rows])
        assert [r["player"] for r in rows] == ["Breakout Guy", "Dalton Kincaid"], sport
        assert [r["matchup_strength"] for r in rows] == [2, 1], sport


def test_the_tier_still_comes_first_and_chance_breaks_ties():
    rows = _board("nfl", "MIA", "BUF",
                  [_prop("A", "BUF", "MIA", "receptions", 0.66), _prop("B", "BUF", "MIA", "receptions", 0.72),
                   _prop("C", "MIA", "BUF", "receptions", 0.80)],
                  [_read("A", "BUF", "MIA", "good", "Good matchup", "receptions"),
                   _read("B", "BUF", "MIA", "good", "Good matchup", "receptions")])
    assert [r["player"] for r in rows] == ["B", "A", "C"], "C has no read: Strong, below both Top picks"
    assert rows[2]["matchup_strength"] == 0


def test_a_sport_with_no_matchup_read_ranks_by_chance_as_before():
    rows = _board("nba", "BOS", "NYK",
                  [_prop("A", "BOS", "NYK", "points", 0.66), _prop("B", "BOS", "NYK", "points", 0.72)], [])
    assert [r["player"] for r in rows] == ["B", "A"]
    assert {r["matchup_strength"] for r in rows} == {0}


def test_the_page_default_sort_is_the_number_on_the_card():
    """Ethan, 2026-09-28, on the By-game view: "This page should rank highest
    too lowest not randomly placed." The engine still ranks a breakout ahead
    (the tests above); the page's default inside a tier is the hit rate the
    card prints, and the matchup order is one tap away."""
    assert 'obSort: "prob",' in APP
    i = APP.index("function obSorted(")
    fn = APP[i:APP.index("\n}\n", i) + 2]
    assert 'const k = state.obSort || "prob";' in fn
    if not shutil.which("node"):
        return
    rows = [{"player": "Kincaid", "model_prob": 0.70, "matchup_strength": 1},
            {"player": "Breakout", "model_prob": 0.62, "matchup_strength": 2},
            {"player": "Old board", "model_prob": 0.75}]
    prog = ("const state = {};\n" + fn + f"\nconst rows = {json.dumps(rows)};\n"
            "state.obSort = 'best'; const a = obSorted(rows).map((r) => r.player);\n"
            "state.obSort = 'prob'; const b = obSorted(rows).map((r) => r.player);\n"
            "console.log(JSON.stringify([a, b]));")
    path = os.path.join(tempfile.mkdtemp(), "s.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    a, b = json.loads(subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout)
    assert a == ["Breakout", "Kincaid", "Old board"], "Strongest matchup is still one tap away"
    assert b == ["Old board", "Kincaid", "Breakout"], a


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
