"""Click a live game, read its whole play-by-play.

Ethan, 2026-09-05: "You should be able to click on each live game and
see a deeper play by play." The data half (tests/test_pbp_files.py)
writes one file per live game; this is the page that reads it.

Source pins, because the page is a few dozen lines of a 30,000-line
file and the failure modes — a door that opens the wrong page, a hash
nobody routes, a timer that keeps polling after the reader has left, a
renderer that reaches for a text field the file does not carry — are
all things no unit renders. The row language is the card's own
(`playsHTML`), so the football, hoops and MLB row pins in their files
cover this page too.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_view_exists_and_is_a_detail_view():
    assert '<section class="view" id="view-pbp">' in HTML
    assert '<div id="pbp-body"></div>' in HTML
    assert '"game", "pbp", "tonight"' in APP, "pbp sits in VIEW_ORDER beside game"
    assert 'const DETAIL_VIEWS = ["prop", "game", "pbp"];' in APP


def test_the_switcher_renders_it_lights_live_and_writes_the_hash():
    i = APP.index('  if (name === "pbp") {')
    seg = APP[i:i + 500]
    assert "renderPbpPage();" in seg
    assert "`#pbp/${encodeURIComponent(state.pbp.league)}/${encodeURIComponent(state.pbp.event)}`" in seg
    assert "_landScroll(name, leaving);" in seg
    assert ': name === "pbp" ? "live" : name;' in APP, "the Live tab stays lit"


def test_both_hash_routers_open_it_and_a_bad_hash_falls_back_to_live():
    assert APP.count('if (h.startsWith("pbp/")) { openPbpHash(h.slice(4)); return; }') == 2, \
        "the hash is routed in both places game/ is"
    body = _fn("openPbpHash")
    assert 'switchView("live")' in body
    assert 'openPbp(parts[0], parts[1], "live")' in body, "a hash landing goes back to Live"


def test_the_page_is_redrawn_where_the_game_page_is():
    """Both dispatch sites the game page has — the data refresh and the
    sport switch — pinned by their neighbours, since the page's own
    refresh timer uses the same line a third time."""
    assert ('  if (state.view === "game") renderGamePage();\n'
            '  if (state.view === "prop") renderPropPage();\n'
            '  if (state.view === "pbp") renderPbpPage();\n') in APP
    assert ('  if (state.view === "game") renderGamePage();\n'
            '  if (state.view === "pbp") renderPbpPage();\n'
            '});') in APP


def test_a_live_or_final_card_opens_the_play_by_play_and_a_scheduled_one_does_not():
    card = _fn("liveCardHTML")
    assert '(lv.state === "live" || lv.state === "final") && (g.event_id || g.game_pk)' in card
    assert 'data-pbp="${escapeAttr(String(g.event_id || g.game_pk))}"' in card
    board = _fn("renderLiveBoard")
    assert "if (el.dataset.pbp) { openPbp(s, el.dataset.pbp); return; }" in board
    # The door comes BEFORE the sport-switch dance, which is for the game page.
    assert board.index("if (el.dataset.pbp)") < board.index("if (s !== state.sport)")


def test_it_reads_the_deep_file_and_nothing_else():
    body = _fn("renderPbpPage")
    assert "boardFetch(`data/pbp/${encodeURIComponent(league)}_${encodeURIComponent(event)}.json`" in body
    assert "await fetch(" not in body, "a bare fetch is one whose failure nobody counts"
    assert "paidFetch" not in body, "free file, no entitlement"
    for prose in ("p.text", "p.description", "shortDescription", "d.text"):
        assert prose not in body, prose


def test_rows_are_drawn_by_the_cards_own_renderer():
    """Football and hoops rows still come from the card's renderer; the
    rail moved into `pbpRailHTML` when the page went to the render
    (2026-09-05), and baseball's pitch rows have their own row function
    there (tests/test_pbp_render.py)."""
    body = _fn("pbpRailHTML")
    assert "playsHTML({ plays: g.rows })" in body


def test_groups_are_the_way_each_sport_is_read_newest_first():
    body = _fn("pbpGroups")
    assert '(d.drives || []).slice().reverse()' in body, "football: newest drive first"
    assert '"SCORE"' in body and '"TURNOVER"' in body and '"IN PROGRESS"' in body
    assert "`${p.half || \"\"}${p.inning || \"\"}`" in body, "baseball: the card's own T6 label"
    assert "`OT${p.period - 4}`" in body, "hoops: OT past the fourth"
    assert "groups.forEach((g) => g.rows.reverse());" in body
    assert "return groups.reverse();" in body


def test_it_refreshes_while_live_and_stops_when_the_reader_leaves():
    body = _fn("renderPbpPage")
    assert 'if (lv.state === "live") again();' in body
    assert 'if (state.view === "pbp") renderPbpPage();' in body, "the timer checks the view before redrawing"
    assert 'if (state.view !== "pbp") return;' in body, "a fetch that lands after leaving draws nothing"
    assert "clearTimeout(_pbpTimer)" in body
    assert "}, 12000);" in body


def test_a_missing_file_says_why_and_offers_the_way_back():
    body = _fn("renderPbpPage")
    assert "No play-by-play on file for this game" in body
    assert "up to eight games" in body
    # The way back is wherever the reader came from (pinned in
    # tests/test_pbp_doors.py); here, only that the page offers one.
    assert "const way = pbpBack();" in body and "switchView(way.view)" in body


def test_the_header_names_the_teams_in_the_leagues_own_vocabulary():
    body = _fn("renderPbpPage")
    assert "teamMarkIn(league, abbr, 44)" in body, "the render's hero wears a bigger mark"
    assert "teamNameIn(league, abbr)" in body
    assert "LEAGUE_LABEL[league]" in body


def test_the_styles_exist():
    for cls in (".pbp-head", ".pbp-score", ".pbp-group-head", ".pbp-tag.turnover"):
        assert cls in CSS, cls


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
