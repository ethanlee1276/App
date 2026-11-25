"""A basketball season's pills say a game's average as one (step AFX, 25 November 2026).

The season card's small pills under its four numbers say the season's other counts (an NFL receiver's "97 targets").
Basketball's season line is a game's average, and only its whole numbers got through the pills' rule, so Jalen
Brunson's 2.0 turnovers a game read "17 games · 2 turnovers". A league whose season line is a game's average
(the career table's `per_game`) now says each pill to a tenth, "a game": "33.9 minutes a game".

Offline. Run directly: `python3 tests/test_a_basketball_seasons_pills_say_a_game.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLR = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
STUBS = "const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml; const trueMinus = (s) => s;\n"


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _pills(career, nums):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    i, k = PLR.index("const PLR_PILL_SKIP"), PLR.index("const plrIsRate")
    js = STUBS + PLR[i:PLR.index(";\n", i) + 2] + PLR[k:PLR.index(";\n", k) + 2] + _fn(PLR, "plrSeasonPills")
    d = {"season": 2026, "role": "box", "career": career}
    out = subprocess.run([node, "-e", js + f"\nprocess.stdout.write(JSON.stringify(plrSeasonPills({json.dumps(d)}, "
                          f"{json.dumps(nums)})));"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


BOX = [{"key": "min", "label": "MIN", "title": "Minutes"}, {"key": "pts", "label": "PTS", "title": "Points"},
       {"key": "stl", "label": "STL", "title": "Steals"}, {"key": "blk", "label": "BLK", "title": "Blocks"},
       {"key": "tov", "label": "TO", "title": "Turnovers"},
       {"key": "fg", "label": "FG", "title": "Field goals made-attempted"},
       {"key": "fgp", "label": "FG%", "title": "Field goal percentage"}]


def test_a_games_average_is_said_as_one():
    got = _pills({"per_game": True, "groups": [{"key": "box", "cols": BOX}],
                  "rows": [{"season": 2026, "gp": 17, "values": {"box.min": 33.9, "box.pts": 26.5, "box.stl": 0.7,
                                                                "box.blk": 0.2, "box.tov": 2.0, "box.fg": "9.2-19.1",
                                                                "box.fgp": 43.7}}]}, [{"key": "pts"}, {"key": "fgp"}])
    if got is None:
        print("      (skipped: no node)")
        return
    assert got == ('<div class="plr-pills"><span class="plr-pill">17 games</span>'
                   '<span class="plr-pill">33.9 minutes a game</span>'
                   '<span class="plr-pill">0.7 steals a game</span>'
                   '<span class="plr-pill">0.2 blocks a game</span></div>'), got


def test_a_whole_average_is_no_count():
    got = _pills({"per_game": True, "groups": [{"key": "box", "cols": BOX[4:5]}],
                  "rows": [{"season": 2026, "gp": 17, "values": {"box.tov": 2.0}}]}, [])
    if got is None:
        return
    assert "2.0 turnovers a game" in got and ">2 turnovers<" not in got, got


def test_a_seasons_totals_stay_counts():
    got = _pills({"groups": [{"key": "box", "cols": BOX[2:5]}],
                  "rows": [{"season": 2026, "gp": 17, "values": {"box.stl": 12, "box.blk": 3.5, "box.tov": 34}}]}, [])
    if got is None:
        return
    assert got == ('<div class="plr-pills"><span class="plr-pill">17 games</span>'
                   '<span class="plr-pill">12 steals</span><span class="plr-pill">34 turnovers</span></div>'), got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
