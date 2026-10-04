"""The rail's Key insights card is retired.

Ethan, 2026-09-22: "retire the key insite card." It sat in the desktop
rail and repeated the first reason off tonight's top picks — the same
sentence each pick's own row carries one column to the left — under a
"More insights" link to the Record page, which has none. The rail keeps
the slip column, the prediction desk and the Live now box. The game
page's own Key insights panel (that game's notes) is a different thing
and stays.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_card_is_gone_from_the_rail():
    assert 'id="rail-insights"' not in HTML, "the card's slot is back in the rail"
    body = _fn("renderRail")
    assert "rail-insights" not in body and "Key insights</div>" not in body
    assert "More insights &#8594;</a>" not in APP, "a link to insights nobody draws"
    assert 'const liv = document.getElementById("rail-live");' in body and "if (!liv) return;" in body
    assert "renderRailDesk();" in body and "dashLiveGames()" in body, "the desk and the live box stay"
    rail = HTML[HTML.index('<aside class="rail"'):HTML.index("</aside>", HTML.index('<aside class="rail"'))]
    for keep in ('id="rail-slip"', 'id="rail-desk"', 'id="rail-live"'):
        assert keep in rail, keep


def test_its_list_styles_went_with_it():
    assert ".rail-list" not in CSS and "rail-list" not in APP, "styles for a list nothing draws"
    assert ".rail-more {" in CSS, "the desk and the live box still use the link style"


def test_the_game_pages_own_key_insights_stays():
    assert '<div class="card gp-notes"><div class="gp-panel-title">Key insights' in APP


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
