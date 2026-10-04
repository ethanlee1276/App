"""The Home game tiles wear the game page's venue fade.

Ethan, 2026-09-24, on the "This week's stadiums" tiles: "These little game
tiles should have the same venue fading into it look as when you click
onto it." The band keeps its height (the strip must not grow); the photo
runs on behind the crests and the matchup name and dissolves into the
tile's own panel, and the matchup is set in the page's headline serif.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _rule(selector):
    i = CSS.index(selector + " {")
    return CSS[i:CSS.index("}", i)]


def test_the_photo_runs_on_behind_the_matchup():
    assert "--tile-fade-run: 84px;" in CSS
    assert "overflow: visible" in _rule(".hero-games .stadium-wrap")
    assert "height: calc(100% + var(--tile-fade-run))" in _rule(".hero-games .stadium-wrap .venue-photo")
    fade = _rule(".hero-games .stadium-wrap::after")
    assert "height: calc(100% + var(--tile-fade-run))" in fade and "background: var(--grad-tile-fade)" in fade


def test_the_fade_ends_in_the_tiles_own_panel():
    # The tile's ground is --panel (the hero-games card); a fade that ended
    # in any other colour would draw a seam under the matchup name.
    assert "background-color: var(--panel)" in _rule(".hero-games .game-card")
    tok = CSS[CSS.index("--grad-tile-fade:"):]
    tok = tok[:tok.index(";")]
    assert tok.rstrip().endswith("var(--panel) 100%)"), tok
    assert "transparent 34%" in tok, "the photo stays bright under the chips"


def test_the_type_and_the_chips_ride_above_the_fade():
    assert "z-index: 3" in _rule(".hero-games .game-card .game-info")
    assert "z-index: 2" in _rule(".hero-games .stadium-wrap::after")
    assert ".hero-games .stadium-wrap .game-wx-chip, .hero-games .stadium-wrap .fav-tag { z-index: 3; }" in CSS
    assert "font-family: var(--font-headline)" in _rule(".hero-games .gc-name")


def test_the_tile_is_still_the_same_card():
    i = APP.index("function gameCard(")
    body = APP[i:APP.index("\n}\n", i)]
    assert '<div class="stadium-wrap">${art}' in body
    assert 'data-onload="vp-on"' in body, "the drawing still hides under a loaded photo"
    assert "runnerOverlay(g)" in body, "the live bases still ride the photo"


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
