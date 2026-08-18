"""Injury tags on every roster surface — the layer the Cade Mays report
demanded. Ethan, 2026-08-18: "We need too make sure that every sport is
up to date with all injuries and shit like that."

The injuries PAGE was already right; the gap was everywhere else. The
draft kit ranked a man who broke his wrist the week before and said
nothing; the mock draft would happily let the CPU-adjacent human take
him; a search profile showed a season of yards with no hint the player
was on IR. One cached fetch of the board the injuries page already
builds, one lookup, and a compact colored tag wherever a player's name
is a decision.

Disciplines pinned:

  * RETURNS NEVER TAG. An "Active" cleared-to-play row is the opposite
    of a designation — tagging it would re-create the exact confusion
    the injuries page just fixed.
  * ONE FETCH, CACHED. Every surface reads the same board; nobody
    re-fetches per row.
  * THE SHORT MAP READS LONGEST-FIRST, so "Injured Reserve" cannot
    stop at a shorter key and "Out" matches only when nothing more
    specific did.

Run directly: `python3 tests/test_injury_tags.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def test_the_board_is_fetched_once_and_cached():
    i = APP.index("async function loadInjuryBoard(")
    body = APP[i:i + 600]
    assert "_injBoard && Date.now() - _injBoardAt" in body
    assert 'fetch("data/injuries.json?t="' in body


def test_a_return_notice_never_tags():
    i = APP.index("function injFind(")
    body = APP[i:APP.index("function injTag(", i)]
    assert "!isReturnRow(r)" in body, \
        "a cleared-to-play row tagging a player re-creates the Mays bug"


def test_every_roster_surface_carries_the_tag():
    # The kit's three row kinds.
    assert APP.count('injTag("nfl", r.player)') >= 3
    # The mock draft's shared identity block tags every row at once.
    i = APP.index("const idBlock = (p, meta)")
    assert 'injTag("nfl", p.player)' in APP[i:i + 300]
    # Search profiles and the Also-matching rows are sport-aware.
    assert APP.count('injTag(state.sport || "nfl"') >= 2
    # The dossier carries the whole sentence, compact card and full page.
    assert "info.inj = injFind(" in APP
    assert "${injLineHTML(info.inj)}" in APP
    assert 'injLineHTML(injFind("nfl", p.player))' in APP


def test_the_pages_load_the_board_before_painting():
    i = APP.index("async function renderFantasy(")
    assert "loadInjuryBoard()" in APP[i:i + 700], \
        "fantasy renders synchronously from its payload — the board must ride the same await"
    j = APP.index("async function renderPlayers(")
    assert "await loadInjuryBoard()" in APP[j:j + 400]


def test_the_short_map_reads_longest_first():
    i = APP.index("const INJ_SHORT = [")
    block = APP[i:APP.index("];", i)]
    assert block.index('"injured reserve"') < block.index('["out"'), \
        "a substring key matching first mislabels the specific status"
    assert block.rstrip().endswith('["out", "OUT"],'), \
        '"out" is the least specific key and must be the last resort'


def test_the_tag_is_styled():
    assert ".inj-tag {" in CSS
    assert ".ffd-injline {" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
