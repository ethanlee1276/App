"""A game card counts every pick we have on it — Edge and Most Likely.

Ethan, 2026-09-25, circling "1 PICK" on Texans @ Colts: "it's only
tracking the edge bets, we need it too track edge and most likely bets
users can see exactly how many bets we have on each game". The chip read
`gameBetCount`, which counted the Edge board's props and game lines and
nothing from Most Likely. A bet both boards posted is one bet.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_chip_counts_both_boards_and_says_the_split():
    card = _fn("gameCard")
    assert "const counts = gamePickCounts(g);" in card
    assert "${counts.edge} Edge · ${counts.likely} Most Likely" in card
    assert "return gamePickCounts(g).total;" in _fn("gameBetCount")


def test_a_bet_on_both_boards_counts_once():
    if not shutil.which("node"):
        return
    harness = ("const passesFilters=()=>true, passesGameBet=()=>true, showableLikelyRow=()=>true;\n"
               + _fn("propInGame") + _fn("gamePickCounts")
               + "const state={data:JSON.parse(process.argv[2])};"
               "process.stdout.write(JSON.stringify(gamePickCounts({home:'IND',away:'HOU'})));")
    path = os.path.join(tempfile.mkdtemp(), "c.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    prop = {"player": "Jonathan Taylor", "team": "IND", "opponent": "HOU",
            "market": "rush_yds", "side": "OVER", "line": 70.5}
    data = {
        "recommendations": [prop],
        "game_bets": [],
        "most_likely": [
            dict(prop, side="over"),                                  # the same bet
            dict(prop, line=40.5),                                    # a different number
            {"player": "C.J. Stroud", "team": "HOU", "opponent": "IND",
             "market": "pass_yds", "side": "over", "line": 200.5},
            {"kind": "game", "player": "IND ML", "team": "IND", "opponent": "HOU",
             "home": "IND", "away": "HOU", "market": "moneyline", "side": "IND"},
            {"player": "Someone Else", "team": "KC", "opponent": "BUF",
             "market": "rec_yds", "side": "over", "line": 50.5},     # another game
        ]}
    out = subprocess.run(["node", path, json.dumps(data)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert json.loads(out.stdout) == {"edge": 1, "likely": 4, "total": 4}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
