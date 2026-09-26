"""Every sport's matchup sits on its venue render, the Pick of the Day's way.

Ethan, 2026-09-24, on the game page's new header: "make sure you change
that so every sport now has [the] new render … we want everything to
match." The game page is one renderer for football, baseball and both
basketball leagues, each on its own family of renders; UFC has no game
page, so each fight card wears one of the six octagon renders.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_one_game_page_for_every_team_sport():
    i = APP.index("const VENUE_FAMILY = ")
    fam = APP[i:APP.index("};", i)]
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba"):
        assert f"{sport}:" in fam, sport
    page = _fn("renderGamePage")
    assert '<div class="gp-hero is-hero">' in page, "no sport is left on the old boxed art"
    assert "const art = mlb ? ballpark(g) : nba ? court(g) : stadium(g);" in page
    for family in ("football", "baseball", "basketball"):
        assert list((ROOT / "web" / "img" / "venues" / "variants").glob(f"{family}-*.jpg")), family


def test_the_ballpark_is_named_once():
    page = _fn("renderGamePage")
    assert '<div class="gp-sub">${escapeHtml(whenLabel(g.date, g.kickoff))}</div>' in page
    assert "(g.stadium || {}).name || g.park_name" in page, "the eyebrow names it"


def test_every_ufc_fight_card_wears_an_octagon():
    for fn in ("pickCard", "passCard"):
        i = APP.index(f"const {fn} = ")
        body = APP[i:i + 900]
        assert "card fight-hero" in body and "fightArtStyle(" in body and "fightEyebrowHTML(" in body, fn
    for n in range(1, 7):
        assert (ROOT / "web" / "img" / "venues" / "variants" / f"octagon-{n}.jpg").exists(), n
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = ("const venueSrc = (s) => s; const absoluteSrc = (s) => '/' + s;\n" + _fn("fightArtStyle")
            + "process.stdout.write(JSON.stringify(['A vs B', 'A vs B', 'C vs D', 'E vs F', 'G vs H']"
            + ".map((f) => fightArtStyle({ fight: f }))));")
    got = json.loads(subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60, check=True).stdout)
    assert got[0] == got[1], "a bout keeps its picture across refreshes"
    assert all(re.fullmatch(r"--fight-art:url\(/img/venues/variants/octagon-[1-6]\.jpg\)", x) for x in got), got


def test_the_art_stays_in_the_top_band_under_the_type():
    rule = CSS[CSS.index(".card.fight-hero::after {"):]
    rule = rule[:rule.index("}")]
    assert "height: 300px" in rule and "var(--fight-art)" in rule and "mask-image: var(--mask-fade-down)" in rule
    assert ".card.fight-hero > * { position: relative; z-index: 1; }" in CSS
    assert ".card.fight-hero::before { z-index: 2; }" in CSS, "the grade stripe stays on top"
    head = CSS[CSS.index(".card.fight-hero .card-head .player {"):]
    assert "font-family: var(--font-headline)" in head[:head.index("}")]


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
