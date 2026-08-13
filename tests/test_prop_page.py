"""One prop, its own page — and the data behind it is real.

Ethan, 2026-08-13: "we should add a feature where we can click on the prop
we recommend and it takes us to a page like the players page that shows
the last 5 games of information for that prop including the bar graph we
just added."

WHY THIS WAS BUILDABLE WITHOUT A NEW FEED. Every recommendation already
carried a `logs` array the site had never rendered — 12 to 16 entries,
each with the opponent, the week, whether it was at home, the value, and
the sport's own extra (wind for the NFL, park and its HR factor for
baseball) — plus a `form` ladder of last 1/3/5/10/season/career. All of it
in the payload, none of it on screen. The page states the case from data
we already had rather than inventing a narrative to fill a layout.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def test_the_payload_really_carries_per_game_logs():
    """The page's whole claim is that this is measured, not narrated. If
    the build ever stops shipping `logs`, the page becomes a shell and
    this fails before a user finds out."""
    path = os.path.join(ROOT, "web", "data", "recommendations.json")
    rows = json.load(open(path, encoding="utf-8"))["recommendations"]
    withlogs = [r for r in rows if r.get("logs")]
    assert withlogs, "no recommendation carries per-game logs"
    g = withlogs[0]["logs"][0]
    # The four fields the table is built from, present on every sport.
    for k in ("value", "opponent", "home"):
        assert k in g, f"{k} missing from a game log"
    assert "week" in g or "date" in g, "a log row must be placeable in time"
    form = withlogs[0].get("form") or {}
    assert "last5" in form and "season" in form


def test_a_prop_is_identified_by_what_it_is_not_where_it_sat():
    """An index into tonight's list points at a different pick the moment
    the board rebuilds, and a bookmarked link would quietly lie rather
    than break. Identity is (player, market, side, line)."""
    # Sliced to propId's OWN body. A looser slice caught `tabindex` in the
    # helper below it and failed on a substring — a test that fires on
    # something it does not mean is a test nobody will trust twice.
    fn = APP[APP.index("function propId("):]
    fn = fn[:fn.index("\n}\n")]
    assert "r.player" in fn and "r.market" in fn and "r.side" in fn and "r.line" in fn
    for word in ("[i]", "idx", "indexOf", "slice("):
        assert word not in fn, f"identity must not be positional: {word}"


def test_the_view_is_registered_everywhere_a_view_has_to_be():
    """A view that renders but has no container, no order entry or no
    hash route is a page you can only reach by accident."""
    assert 'id="view-prop"' in HTML and 'id="prop-body"' in HTML
    assert '"recommended", "prop"' in APP, "prop missing from VIEW_ORDER"
    assert APP.count('h.startsWith("prop/")') == 2, "both hash entry points"
    assert 'if (state.view === "prop") renderPropPage();' in APP


def test_the_prop_page_borrows_the_board_s_tab_like_the_game_page_does():
    """Neither detail page has a tab of its own. Leaving the nav unlit
    reads as "you have navigated out of the app"."""
    assert '(name === "game" || name === "prop") ? "recommended"' in APP


def test_an_inner_control_wins_over_the_card_wide_click():
    """These cards carry a Play link and My Bets controls. A card-wide
    handler that swallowed them would trade a feature for a regression —
    verified in Chromium: clicking the inner button does not navigate,
    clicking the card body does."""
    assert 'e.target.closest("a, button, input, label, select, .chip")' in APP
    # Delegated, not per-card: these cards re-render on every slider move
    # and refresh, so per-card binds would leak and miss.
    assert 'document.addEventListener("click"' in APP
    assert 'e.target.closest("[data-prop]")' in APP


def test_the_card_is_a_control_for_a_keyboard_too():
    """A card you can click is a control, and a control that only answers
    a mouse is not finished."""
    assert 'document.addEventListener("keydown"' in APP
    assert 'e.key !== "Enter" && e.key !== " "' in APP
    assert ".openable:focus-visible" in CSS


def test_a_stale_link_says_so_rather_than_rendering_blank():
    """Props are rebuilt every slate, so a link outlives the pick. A blank
    page reads as broken; this says what happened. Verified in Chromium."""
    fn = APP[APP.index("function renderPropPage("):]
    fn = fn[:fn.index("\n}\n")]
    assert "not on tonight" in fn
    assert "empty-slate" in fn


def test_the_page_does_not_print_the_same_number_twice():
    """The chart's stat row already carries EV. Ethan had just finished
    pointing at exactly this duplication on the prop cards themselves."""
    fn = APP[APP.index("function renderPropPage("):]
    fn = fn[:fn.index("\n}\n")]
    head = fn[:fn.index("propAnalysis(r)")]
    assert "EV / unit" not in head, "EV is on the chart's stat row already"


def test_the_form_ladder_is_read_against_the_side_that_was_taken():
    """An average below the line is good news on an UNDER and bad news on
    an OVER. Colouring it by sign alone would paint half the board
    backwards — the same defect the bars were fixed for."""
    fn = APP[APP.index("function propFormRows("):APP.index("function renderPropPage(")]
    assert "over ? v > line : v < line" in fn


def test_the_log_table_grades_each_game_the_same_way_the_bars_do():
    fn = APP[APP.index("function propLogRows("):APP.index("function propFormRows(")]
    assert "over ? v > line : v < line" in fn
    # Home and away are not the same spot, and the table says which.
    assert 'g.home ? "vs" : "@"' in fn


def test_every_surface_that_lists_a_prop_offers_the_door():
    """Ethan, 2026-08-13: "anywhere we show a prop, we need to offer the
    option to click on it and show more data of that prop with the bar
    graph like u just did."

    The first cut wired only the two cards that already drew the chart,
    which missed the dashboard, the Edge Board and Top Picks — the three
    places a prop is most often seen. Every surface routes through the
    same helper now, so a new one cannot be half-wired.
    """
    for fn in ("cardHTML", "longShotCard"):
        i = APP.index(f"function {fn}(")
        body = APP[i:i + 3000]
        assert "propAttrs(r)" in body, f"{fn} is not a door"
        assert "propOpenable(r)" in body, f"{fn} claims the class unconditionally"
    # The dashboard's best-bets rows, the Edge Board rows and Top Picks.
    assert "id: betMark(r), open: propAttrs(r)" in APP, "dashboard rows"
    assert 'ev: r.ev_per_unit, grade: r.grade, rec: passesFilters(r),\n      open: propAttrs(r),' in APP \
        or "open: propAttrs(r)," in APP, "edge board rows"
    assert '<div class="tp-card ${propOpenable(r) ? "openable" : ""}"${propAttrs(r)}>' in APP


def test_a_game_bet_is_never_dressed_as_a_prop():
    """Moneylines, spreads and game totals sit in these same lists. They
    have no player and no game log, so a door on one would open a page
    with nothing to draw. `propOpenable` is where that is decided, once."""
    fn = APP[APP.index("function propOpenable("):APP.index("function propAttrs(")]
    assert "if (!r || !r.player) return false" in fn
    # And history is required too, because propAnalysis itself renders
    # nothing under three values.
    assert "logs >= 3 || vals >= 3" in fn
    # The game-line rows on the Edge Board must not carry the attribute.
    gb = APP[APP.index("const games = (state.data.game_bets || [])"):]
    gb = gb[:gb.index("return [...props, ...games]")]
    assert "propAttrs" not in gb, "a game line became clickable"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
