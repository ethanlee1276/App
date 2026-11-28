"""A past season's league places say "that season", not "this season" (step AFV, 25 November 2026).

Cameron Boozer's college basketball page shows 2025-26, his newest college season, in the 2026-27 season, and its
card read "2025–26 season · Where each ranks in the CBB this season". The page now carries the league's own newest
season (engine/playerpage `league_season`, off the box scores as the player's own seasons are), and a card for an
older season says "Where each ranked in the CBB that season".

Offline. Run directly: `python3 tests/test_a_past_seasons_places_say_that_season.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import playerpage as PP                                         # noqa: E402

EV = __import__("test_every_player_has_a_page_of_their_own")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")


def test_the_page_says_the_leagues_newest_season():
    path, rosters = EV._fresh()
    now = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters)
    old = PP.page("nfl", "Josh Allen", season=2025, db_path=path, data_dir=rosters)
    assert (now["season"], now["league_season"]) == (2026, 2026)
    assert (old["season"], old["league_season"]) == (2025, 2026)


def test_the_card_says_that_season_for_an_older_one():
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return

    def fn(head):
        i = PAGE.index(head)
        return PAGE[i:PAGE.index("\n}\n", i) + 2]

    def const(head):
        i = PAGE.index(head)
        return PAGE[i:PAGE.index(";\n", i) + 2]
    prog = ("const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml; const lgCode = (s) => s.toUpperCase();\n"
            "const trueMinus = (s) => s;\n"
            + const("const PLR_RATES = ") + const("const PLR_WHOLE = ") + const("const PLR_TWO_YEARS = ")
            + const("const PLR_PILL_SKIP = ") + const("const plrIsRate = ") + const("const plrPast = ")
            + fn("function plrNum(v, label, avg) {") + fn("function plrSeasonLabel(sport, s) {")
            + fn("function plrOrd(n) {") + fn("function plrSeasonPills(d, nums) {")
            + fn("function plrSeasonHTML(d, note = \"\") {")
            + "const h = [{ key: 'pts', label: 'PTS', title: 'Points', value: 22.4, rank: 10, per_game: true }];\n"
              "console.log(JSON.stringify({\n"
              "  past: plrSeasonHTML({ sport: 'cbb', season: 2025, league_season: 2026, headline: h }),\n"
              "  now: plrSeasonHTML({ sport: 'cbb', season: 2026, league_season: 2026, headline: h }),\n"
              "  unsaid: plrSeasonHTML({ sport: 'cbb', season: 2026, headline: h }) }));\n")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    assert "2025–26 season <span>Where each ranked in the CBB that season</span>" in got["past"], got["past"][:300]
    assert "2026–27 season <span>Where each ranks in the CBB this season</span>" in got["now"], got["now"][:300]
    assert "Where each ranks in the CBB this season" in got["unsaid"], "an answer from before says it as before"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
