"""Live-now league shelves — the mixed slate grouped by sport.

Ethan, 2026-09-01, with a screenshot of the Live tab interleaving a CFB
game between two MLB ones: "In the live tab, make it easier too see
which games that are live is what sport. Right now they are all in a
row and it's hard too tell which is what sport."

The card corner's little league tag was the only signal, and it is a
whisper. On the "All" chip the board now draws one shelf per league —
logo, league name, live count — with that league's games under it, in
the same feed order the chips use. A single-league filter keeps the
flat grid, because the chip the reader pressed IS the label.

Run directly: `python3 tests/test_live_shelves.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _board_body():
    src = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = src.index("async function renderLiveBoard()")
    return src[i:src.index("\n(function initNewLook", i)]


def test_the_all_chip_shelves_games_by_league():
    body = _board_body()
    assert '_liveChip === "all"' in body
    assert 'class="lb-shelf"' in body
    # One shelf per league that actually has a live game, league name and
    # count on the header, that league's games under it.
    assert "Object.keys(LIVE_FEEDS).filter((s) => bySport[s])" in body
    assert "${bySport[s]} live" in body
    assert "games.filter((x) => x.sport === s)" in body


def test_a_single_league_filter_keeps_the_flat_grid():
    """The chip you pressed IS the label — shelving one league under its
    own name would be furniture."""
    body = _board_body()
    assert ': `<div class="lb-grid">${shown.map(liveCardHTML).join("")}</div>`' \
        in body


def test_the_shelf_is_data_driven_not_a_league_list():
    """The shelves come from LIVE_FEEDS and SPORT_META — the code names
    no league, so a sport added to the feeds grows its shelf by itself."""
    body = _board_body()
    i = body.index("const shelved")
    block = body[i:body.index("host.innerHTML", i)]
    code = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    assert "SPORT_META[s]" in code and "LEAGUE_LABEL[s]" in code
    for word in ('"MLB"', '"CFB"', '"NFL"', "'mlb'", "'cfb'"):
        assert word not in code, f"{word} hardcoded in the shelf builder"


def test_live_polls_revalidate_instead_of_redownloading_the_boards():
    """fetchAllLive pulls every league's board every 30 seconds on the
    Live tab — the MLB file is 8MB — and `no-store` re-downloaded all
    of it even when the build had not moved. `no-cache` keeps the exact
    freshness guarantee (the server is asked every time) and reuses the
    cached body on a 304, which is most polls. The fast scoreboard file
    keeps `no-store`: it is tiny and changes every few seconds, so a
    304 there is the rare case, not the common one."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = src.index("async function fetchAllLive()")
    body = src[i:src.index("\nfunction ", i)]
    assert 'await fetch(url, { cache: "no-cache" })' in body
    assert 'fetch(LIVE_FAST[sport], { cache: "no-store" })' in body
    # A cache-busting query string would defeat every 304 — the URL must
    # stay byte-identical between polls. (The Date.now() at the top of
    # the function is the 30-second memory cache, not a buster.)
    assert "?_=" not in body and "`${url}?" not in body
    # The two record.json readers ride the same trade.
    assert src.count('boardFetch("/data/record.json", { cache: "no-cache" })'
                     ) + src.count(
                     'boardFetch("data/record.json", { cache: "no-cache" })'
                     ) == 2


def test_the_shelf_has_its_own_css():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".lb-shelf {" in css
    assert ".lb-shelf + .lb-grid" in css, \
        "a shelved grid needs its own rhythm below the header"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
