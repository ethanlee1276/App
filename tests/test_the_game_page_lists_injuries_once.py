"""The game page lists a game's injuries once.

Ethan, 2026-09-28, on PHI@CHI: "We show the injuries twice." The matchup
scan's "Injuries and what they open" card and the game plan's "Who is out,
and where the work goes" step draw the same rows (engine/gameplan.absences
reads scan.injuries). With a plan on the page the scan drops its card;
without one (locked or not built) the scan keeps it.

Run directly: `python3 tests/test_the_game_page_lists_injuries_once.py`
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
PLAN = (ROOT / "engine" / "gameplan.py").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\nfunction ", i + 1)]


def test_the_plan_step_is_built_from_the_scan_s_injuries():
    assert '{"key": "out", "title": "Who is out, and where the work goes", "rows": absences(scan)}' in PLAN
    i = PLAN.index("def absences(")
    assert "injuries" in PLAN[i:i + 1500]


def test_the_scan_drops_its_card_when_the_plan_is_on_the_page():
    fn = _fn("matchupScanHTML")
    assert re.search(r"const inj = gamePlanFor\(g\) \? \[\] : \(scan\.injuries \|\| \[\]\);", fn)
    assert "Injuries and what they open" in fn, "the card itself stays for a page with no plan"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
