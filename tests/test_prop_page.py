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

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def test_the_payload_really_carries_per_game_logs():
    """The page's whole claim is that this is measured, not narrated. If
    the build ever stops shipping `logs`, the page becomes a shell and
    this fails before a user finds out.

    Read against the BUILDERS, not against web/data/recommendations.json.
    That file is a build artefact and web/data/ is gitignored, so the
    first version of this test asserted something only Ethan's laptop
    could satisfy: green there, red in every fresh clone, for a reason
    that has nothing to do with the code being wrong. Same mistake
    test_prose.py made reaching for the live hypothesis store, and
    test_doctor_learning.py reading the real rung files.

    Driving the committed sample slates through the real pipelines costs
    a few seconds and buys three things the old form did not have: it
    holds on any machine, it names the builder that broke rather than the
    board that happened to be sitting on disk, and it covers BOTH sports
    instead of whichever one was built last."""
    from engine.mlb.pipeline import run_mlb_slate
    from engine.pipeline import run_slate

    for sport, out in (
        ("nfl", run_slate(os.path.join(ROOT, "data", "sample_slate.json"))),
        ("mlb", run_mlb_slate(os.path.join(ROOT, "data",
                                           "mlb_sample_slate.json"))),
    ):
        rows = out["recommendations"]
        withlogs = [r for r in rows if r.get("logs")]
        assert withlogs, f"{sport}: no recommendation carries per-game logs"
        g = withlogs[0]["logs"][0]
        # The fields the table is built from, present on every sport.
        for k in ("value", "opponent", "home"):
            assert k in g, f"{sport}: {k} missing from a game log"
        assert "week" in g or "date" in g, \
            f"{sport}: a log row must be placeable in time"
        form = withlogs[0].get("form") or {}
        assert "last5" in form and "season" in form, f"{sport}: form ladder"


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


def test_a_riding_row_is_a_door_too():
    """Ethan, 2026-08-22, on the riding list: "we should be able to click
    on these props and just like the other ones and it will pull up the
    bar graphs and shit for that person."

    Same cause as the game bets in 2026-08-13. A riding row comes from
    `live_picks` — the JOURNAL — so it carries a price and a stake and no
    game logs at all. propOpenable looked at the bet, found no history,
    and left the row inert while the identical prop opened everywhere
    else on the page."""
    i = APP.index("const ridingRow =")
    # To the end of the arrow function, not a fixed width: the door is
    # resolved once at the bottom of the template, and a slice chosen by
    # character count is the trap this suite keeps falling into.
    row = APP[i:APP.index("(ridingAttrs(b));", i) + len("(ridingAttrs(b));")]
    assert "ridingAttrs(b)" in row, "the riding row is still inert"
    assert '"openable"' in row, "it opens but does not look like it does"


def test_the_riding_door_opens_the_board_object_not_the_bet():
    """openProp resolves the id through allProps(). An id built from the
    BET would find nothing, because a riding row exists precisely when
    the board's line has moved off the one the bet was placed at."""
    fn = APP[APP.index("function ridingDoorProp("):APP.index("function ridingAttrs(")]
    assert "allProps()" in fn
    assert "propOpenable(r)" in fn, "it can open a prop with nothing to draw"
    attrs = APP[APP.index("function ridingAttrs("):]
    attrs = attrs[:attrs.index("\n}") + 2]
    assert "propAttrs(door)" in attrs, \
        "the id must come from the board object, not the journalled bet"


def test_the_riding_door_matches_on_player_and_market_only():
    """The row exists BECAUSE the number moved. Matching on side or line
    would make it openable only in the case where it would not be
    riding."""
    fn = APP[APP.index("function ridingDoorProp("):APP.index("function ridingAttrs(")]
    assert "b.market" in fn and "r.market" in fn
    assert "b.side" not in fn and "b.line" not in fn


def test_a_riding_row_with_nothing_behind_it_stays_inert():
    """A door onto an empty page is worse than no door.

    THIS TEST USED TO PIN A STRICTER RULE — that a row opened only when
    the board carried a prop with three or more games — and that rule was
    the bug: on a night with no qualifying plays the board carries
    nothing for anybody, so every row was dead. The prop page is still
    gated on having something to draw; what changed is that failing that
    gate now falls back to the player's own page rather than to nothing.

    What must still be inert: a row with no player at all, and a
    moneyline, whose "player" is a team."""
    fn = APP[APP.index("function ridingDoorProp("):APP.index("function ridingAttrs(")]
    assert "return null" in fn
    assert "propOpenable(r)" in fn, "the prop page can open with nothing to draw"
    attrs = APP[APP.index("function ridingAttrs("):]
    attrs = attrs[:attrs.index("\n}") + 2]
    assert 'return ""' in attrs, "every row now claims to be a door"
    assert "!b.player" in attrs


def test_a_riding_row_opens_a_popup_not_a_page():
    """Ethan, 2026-08-22: "i dont like how it takes you to the search page
    and automatically searches the palyer for you, we need to switch it
    too a pop up window that comes up with the bar graph and shit instead
    of taking you to a new whole page."

    Right on both counts. Navigating to Players and typing into its search
    box on the reader's behalf was a lot of machinery to look at one
    chart, and it lost the place they were reading.

    It also explains his OTHER complaint in the same message — that it
    "loads you at the bottom of the page". That was not a separate
    scroll bug; it was this navigation landing on a long page. Verified
    in Chromium: opening the peek leaves state.view and window.scrollY
    exactly where they were."""
    assert "function openPeek(" in APP, "the popup is gone"
    fn = APP[APP.index("function ridingAttrs("):]
    fn = fn[:fn.index("\n}") + 2]
    assert "data-peek=" in fn, "the riding row navigates again"
    assert "openPlayer(" not in fn


def test_the_peek_does_not_use_the_attribute_the_profile_tabs_use():
    """`data-player` is already on the profile card's market tabs. A
    delegated handler on it fires there too — which survives today only
    because those tabs are <button>s and the handler skips buttons. That
    is luck, not design, and it stops holding the moment one is restyled
    as a div."""
    fn = APP[APP.index("function ridingAttrs("):]
    fn = fn[:fn.index("\n}") + 2]
    assert "data-player=" not in fn
    assert 'data-player="${escapeAttr(player)}"' in APP, \
        "the profile tabs stopped using it — this test is now moot"


def test_the_popup_reuses_the_profile_card_rather_than_redrawing_it():
    """profileHTML already draws the head, the market tabs, the bar chart
    and the log rows. A second implementation is a second thing to keep
    in step with the first, and it is the chart that would drift."""
    fn = APP[APP.index("async function openPeek("):]
    fn = fn[:fn.index("\nfunction closePeek(")]
    assert "profileHTML(name)" in fn, "the popup draws its own card now"
    assert "player_stats" in fn and "leagueLogs(" in fn, \
        "a player with nothing on tonight's board gets no logs"


def test_the_popup_can_be_dismissed_every_way_a_dialog_should_be():
    fn = APP[APP.index("async function openPeek("):]
    fn = fn[:fn.index("\nfunction closePeek(")]
    assert "pk-close" in fn and "e.target === ov" in fn, \
        "no backdrop or close-button dismissal"
    assert 'role="dialog"' in fn and 'aria-modal="true"' in fn
    # THE RIGHT Escape HANDLER — app.js has three, and index() finds one
    # about a dropdown menu. Anchor on the handler that mentions the
    # dialog rather than on the first that mentions the key.
    esc = [l for l in APP.splitlines()
           if 'e.key === "Escape"' in l and "closePeek()" in l]
    assert esc, "Escape does not close the popup"


def test_a_riding_row_opens_even_when_the_board_is_empty():
    """THE HALF THE FIRST FIX MISSED. Rows only opened when the board
    still carried a prop object for that player — and then Ethan sent the
    same screenshot back with the rows circled again. Of course: a board
    reading "No qualifying plays at current numbers" has no prop object
    for ANYBODY, so on exactly the night you most want to look up what
    you are still riding, every row was inert.

    The player's own page has the form, the logs and the same bar chart,
    and it needs no board at all."""
    fn = APP[APP.index("function ridingAttrs("):]
    fn = fn[:fn.index("\n}") + 2]
    assert "data-peek=" in fn, "there is still no fallback door"
    assert "propAttrs(door)" in fn, "the prop page is no longer preferred"
    assert fn.index("propAttrs(door)") < fn.index("data-peek="), \
        "the fallback runs before the real prop page"


def test_a_moneyline_row_gets_no_player_door():
    """`b.player` holds a TEAM on those. A player page for "TOR" is a
    search that finds nobody, and an empty page looks broken in a way an
    unresponsive row does not."""
    fn = APP[APP.index("function ridingAttrs("):]
    fn = fn[:fn.index("\n}") + 2]
    assert 'b.market === "moneyline"' in fn


def test_the_peek_is_wired_to_both_mouse_and_keyboard():
    """A card you can click is a control, and a control that only answers
    a mouse is not finished — the same rule the prop doors already keep."""
    # THE RIGHT LISTENER, not the first one with that name — app.js has
    # five document click handlers, and `index()` finds one at line 211
    # that has nothing to do with doors. Anchor on what the handler DOES.
    for kind in ("click", "keydown"):
        marker = f'document.addEventListener("{kind}"'
        at, body = -1, None
        while True:
            at = APP.find(marker, at + 1)
            assert at >= 0, f"no {kind} handler mentions [data-prop]"
            chunk = APP[at:at + 800]
            if "[data-prop]" in chunk:
                body = chunk
                break
        assert "[data-peek]" in body, f"the {kind} handler ignores the peek"
        assert body.index("[data-prop]") < body.index("[data-peek]"), \
            "a row with a real prop behind it must open the prop page"


def test_opening_a_player_cannot_throw_out_of_a_delegated_handler():
    """It is reached from a document-level listener now. A throw there
    kills the handler for every OTHER door on the page, not just this
    one."""
    fn = APP[APP.index("function openPlayer("):]
    fn = fn[:fn.index("\n}") + 2]
    assert "if (box)" in fn or "box &&" in fn, \
        "a missing search box would throw and take the listener with it"


def test_the_bets_tile_counts_the_riding_ones_too():
    """Ethan, 2026-08-22: "if we still reccomended bets but the line moved
    and we are still displaying that we are riding those bets, then we
    should still be displaying however many props were reccomended … bc
    they were still given out and we are still riding them."

    A large honest 0 over seventeen live positions is a worse answer to
    "what am I on tonight" than counting them and saying which are
    which."""
    i = APP.index("const tiles = [")
    block = APP[i - 1400:i + 900]
    assert "const riding = ridingBets(sig)" in block
    assert "const live = staked.length + riding.length" in block
    assert 'to: live, dec: 0, lead: true' in block


def test_the_tile_says_which_are_new_and_which_are_riding():
    """Counting them without separating them would invite somebody to go
    and place seventeen bets at numbers that are gone."""
    i = APP.index('k: "Recommended bets"')
    block = APP[i:i + 700]
    assert "new ·" in block and "riding" in block
    assert "don’t add at tonight’s number" in block


def test_riding_money_is_not_counted_as_suggested_exposure():
    """It is already staked. Adding it to a figure headed "suggested"
    reads as stake it again."""
    i = APP.index('k: "Suggested exposure"')
    block = APP[i:i + 700]
    assert "already staked" in block
    # The number itself still comes from `exposure`, which sums `staked`.
    assert "to: exposure" in block


def test_one_definition_of_riding_serves_both_surfaces():
    """The picks box lists them and the tile counts them. Two copies of
    the filter would drift, and the failure is a headline disagreeing
    with the list directly underneath it."""
    assert APP.count("function ridingBets(") == 1
    # Assignments only — `function ridingBets(sig)` matches the bare
    # string too, and counting the definition as a call site is how this
    # assertion would keep passing after a surface stopped calling it.
    assert APP.count("= ridingBets(sig)") == 2, \
        "a surface stopped using the shared definition"
    fn = APP[APP.index("function ridingBets("):]
    fn = fn[:fn.index("\nfunction ", 1)]
    assert "live_picks" in fn and "phase === \"upcoming\"" in fn


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
