"""A game on the Live tab's strip that has not started opens its game page.

Ethan, 2026-09-24, circling the 3:10 and 6:05 chips above a live
play-by-play: "I should be able to click on the games up here as well and
it takes us to the normal game page." A chip for a game under way (or
over) still switches the play-by-play, which is the strip's job; a chip
before first pitch was disabled because there is no play-by-play yet. It
now opens the board's game page, and stays disabled only when the board
does not carry that game.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_an_upcoming_chip_carries_its_board_game():
    strip = _fn("pbpStripHTML")
    assert "const bg = !door && state.sport === league && state.data" in strip
    assert "x.home === g.home && x.away === g.away" in strip
    assert 'data-pbp-game="${escapeAttr(gameId(bg))}"' in strip
    assert '" disabled"' in strip, "a game the board does not carry has no page to open"


def test_the_tap_opens_the_game_page_or_the_play_by_play():
    page = _fn("renderPbpPage")
    assert "el.dataset.pbpGame\n        ? openGame(el.dataset.pbpGame) : openPbp(league, el.dataset.pbp)" in page


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
