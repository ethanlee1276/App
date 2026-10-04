"""The desktop line-shopper's tools (audit #42: V-14, V-23, O26).

Phase 5 left four pieces of #42 undone; this pins them:
  * the top bar's search is a real input on a wide screen, not a button
    dressed as one, and typing in it is the search;
  * each book's price carries the time the feed says that book last moved
    it, printed on the books strip and the prop page's shop table;
  * the pick boards keep the rail (riding, record, live) on a wide screen;
  * every scanner row has a Copy button with the row's own words.

Run directly: `python3 tests/test_the_desktop_shopper_has_its_tools.py`
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import oddsapi  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i)]


# --- search ------------------------------------------------------------
def test_the_bar_holds_a_real_search_input_on_a_wide_screen():
    i = HTML.index('id="nav-search-input"')
    tag = HTML[HTML.rindex("<", 0, i):HTML.index(">", i)]
    assert tag.startswith("<input") and 'type="search"' in tag, tag
    assert ".ns-input { display: none; }" in CSS
    wide = CSS[CSS.index(".ns-field { display: flex;"):]
    assert ".ns-input { display: block;" in wide[:900], "the field is never shown"


def test_typing_in_the_bar_is_the_search():
    body = APP[APP.index('const barBox = document.getElementById("nav-search-input");'):][:900]
    assert 'barBox.addEventListener("input"' in body
    assert "pageBox.value = barBox.value;" in body
    assert 'pageBox.dispatchEvent(new Event("input"))' in body, \
        "the bar must drive the one search handler, not a second copy of it"
    assert 'if (state.view !== "players") goSearch();' in body
    slash = APP[APP.index('if (e.key !== "/"'):][:500]
    assert "barBox.focus()" in slash, '"/" focuses the field on screen'


# --- a time on every price ----------------------------------------------
def test_the_parser_keeps_each_book_s_update_time():
    event = {"bookmakers": [{
        "key": "draftkings", "last_update": "2026-10-02T17:00:00Z",
        "markets": [{"key": "player_reception_yds", "last_update": "2026-10-02T18:42:00Z",
                     "outcomes": [
                         {"name": "Over", "description": "A Wideout", "point": 50.5, "price": -110},
                         {"name": "Under", "description": "A Wideout", "point": 50.5, "price": -110}]}]}]}
    out = oddsapi._parse_lines(event, None, sharp=False)
    (lines,) = out.values()
    assert lines[0].updated == "2026-10-02T18:42:00Z", lines[0]
    # The market's stamp wins; the book's is the fallback.
    del event["bookmakers"][0]["markets"][0]["last_update"]
    (lines,) = oddsapi._parse_lines(event, None, sharp=False).values()
    assert lines[0].updated == "2026-10-02T17:00:00Z"


def test_the_board_ships_it_and_the_page_prints_it():
    pipe = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
    assert '**({"at": ln.updated} if getattr(ln, "updated", "") else {})' in pipe
    q = _fn("quotesForSide")
    assert "Date.parse(ln.at)" in q
    assert 'at: Number.isFinite(t) ? tzTime(t) : ""' in q, "a missing stamp prints nothing"
    strip = _fn("booksStripHTML")
    assert "const at = x.at;" in strip and 'class="bs-at"' in strip
    table = _fn("booksTableHTML")
    assert "escapeHtml(x.at)" in table and "<th class=\"num\">As of</th>" in table


# --- the rail ----------------------------------------------------------
def test_the_pick_boards_keep_the_rail_on_a_wide_screen():
    fn = _fn("syncRail")
    assert "RAIL_BOARDS.includes(state.view)" in fn
    assert 'document.body.classList.toggle("rail-wide-only", board);' in fn
    assert "body.rail-wide-only .rail { display: none; }" in CSS


# --- copy a scanner row --------------------------------------------------
def test_every_scanner_row_can_be_copied():
    assert "armScanCopy(host);" in _fn("renderScanner")
    arm = _fn("armScanCopy")
    assert 'host.querySelectorAll(".hd-row.hd-scan")' in arm
    assert "navigator.clipboard.writeText(scanRowText(row))" in arm
    txt = _fn("scanRowText")
    assert '".hd-what b"' in txt and '".hd-what span"' in txt and '".hd-state"' in txt


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
