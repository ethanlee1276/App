"""One order of importance, followed everywhere the leagues are listed.

Ethan, 2026-09-01: "the NFL needs to be first, then CFB, then MLB, then
NBA, then WNBA, then UFC in the level of importance."

Said once in launch.SPORT_PRIORITY and pinned here against every list
that enumerates the leagues: the rebuild cycle (whoever builds first is
freshest, and does not wait behind a league he ranks lower), the boards
screen, the Live tab's feed table (its shelves and chips draw in key
order), the search scope chips, the search tie-break, and the top bar.

Run directly: `python3 tests/test_sport_priority.py`
"""

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

import launch                                                  # noqa: E402
from engine import playersearch                                # noqa: E402

ORDER = ("nfl", "cfb", "mlb", "nba", "wnba", "ufc")


def _src(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def test_the_order_is_said_once():
    assert launch.SPORT_PRIORITY == ORDER


def test_the_rebuild_cycle_builds_the_leagues_in_that_order_first():
    src = _src("launch.py")
    at = src.index("def refresh_all(")
    body = src[at:src.index("\ndef ", at + 10)]
    names = re.findall(r'_note_board\("([a-z]+)"', body)
    assert tuple(names[:6]) == ORDER, names
    # The tool boards come after every league, never between them.
    assert set(names[6:]) == {"predmarkets", "memes", "fantasy"}, names


def test_the_boards_screen_lists_them_in_that_order():
    keys = tuple(launch.BOARD_FILES)
    assert keys == tuple(s for s in ORDER if s in launch.BOARD_FILES), keys


def test_the_live_tab_and_the_search_chips_follow_it():
    js = _src("web/js/app.js")
    i = js.index("const LIVE_FEEDS = {")
    block = js[i:js.index("};", i)]
    feeds = re.findall(r"\b(nfl|cfb|mlb|nba|wnba):", block)
    assert tuple(feeds) == tuple(s for s in ORDER if s in feeds), feeds
    j = js.index("const SEARCH_SCOPES")
    assert '["nfl", "cfb", "mlb", "nba", "wnba", "ufc"]' in js[j:j + 120]


def test_the_search_tie_break_and_the_top_bar_follow_it():
    assert playersearch.SOURCES == ORDER
    html = _src("web/index.html")
    tabs = re.findall(r'class="sport-btn[^"]*" data-sport="([a-z]+)" '
                      r'data-kind="league"', html)
    assert tuple(tabs) == ORDER, tabs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
