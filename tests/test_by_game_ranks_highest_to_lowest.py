"""The Most Likely page's By-game view ranks each game highest to lowest.

Ethan, 2026-09-28, a screenshot of Eagles @ Bears in By-game: the rings read
61, 59, 55, 43, 76, 68, 66 — "This page should rank highest too lowest not
randomly placed". Two causes: the view mixed the tiers, and the default sort
inside a tier was the matchup score the card never prints. Each game now
lists its Top picks, then Strong, then Worth a look, each under its name,
highest hit rate first.

Run directly: `python3 tests/test_by_game_ranks_highest_to_lowest.py`
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_each_game_groups_by_tier_then_ranks_by_the_ring():
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    tiers = APP[APP.index("const OB_TIERS"):APP.index("];", APP.index("const OB_TIERS")) + 2]
    rows = [  # the screenshot's seven, by tier as their rings were coloured
        {"player": "Loveland rec", "tier": "top", "model_prob": 0.61, "game": "PHI@CHI", "matchup_strength": 1},
        {"player": "Burden rec", "tier": "top", "model_prob": 0.59, "game": "PHI@CHI", "matchup_strength": 2},
        {"player": "Loveland yds", "tier": "look", "model_prob": 0.55, "game": "PHI@CHI", "matchup_strength": 2},
        {"player": "Swift TD", "tier": "strong", "model_prob": 0.43, "game": "PHI@CHI", "matchup_strength": 2},
        {"player": "Swift yds", "tier": "look", "model_prob": 0.76, "game": "PHI@CHI", "matchup_strength": 0},
        {"player": "Raymond rec", "tier": "look", "model_prob": 0.68, "game": "PHI@CHI", "matchup_strength": 0},
        {"player": "Burden yds", "tier": "strong", "model_prob": 0.66, "game": "PHI@CHI", "matchup_strength": 1}]
    prog = ("const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml;\n"
            "const teamName = (t) => t; const whenLabel = () => ''; const gameId = () => 'g';\n"
            "const obCardHTML = (r) => `[${r.player}]`;\n"
            "const state = {data: {games: [{away: 'PHI', home: 'CHI'}]}};\n"
            + tiers + "\n" + _fn("obSorted") + _fn("obByGameHTML")
            + f"\nconsole.log(obByGameHTML({json.dumps(rows)}));")
    path = os.path.join(tempfile.mkdtemp(), "g.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout
    order = [seg.split("]")[0] for seg in out.split("[")[1:]]
    assert order == ["Loveland rec", "Burden rec", "Burden yds", "Swift TD",
                     "Swift yds", "Raymond rec", "Loveland yds"], order
    labels = [s.split("<")[0].strip() for s in out.split('class="mp-tier">')[1:]]
    assert labels == ["Top picks", "Strong", "Worth a look"], labels


def test_the_default_is_the_hit_rate_and_the_label_is_styled():
    assert 'obSort: "prob",' in APP and 'const k = state.obSort || "prob";' in APP
    assert ".mp-tier {" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
