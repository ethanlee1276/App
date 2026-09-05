"""The site's organization: rooms instead of one long scroll.

Ethan, 2026-08-08: "Everything feels cluttered and kinda just thrown around
in place when I say to add something. We need more organization so its not
so confusing navigating the site."

MEASURED FIRST, because "cluttered" is a feeling and a number is a fact.
Counted in the source, and every page height measured in headless Chromium
against the checked-in sample data:

    players       139,451px   155 screens   293 full profiles, 4,315 rows
    fantasy         9,906px    11 screens   10 section titles
    recommended     6,994px     7.8 screens
    record            ...       22 sections composed into one column

Site-wide: 81 section titles across 47 render functions, every one of them
at identical visual weight. Nothing was badly built — things were appended,
one at a time, to whichever page was nearest, which is exactly what he
described.

WHAT HE CHOSE, asked before anything moved: sub-tabs inside a page rather
than new top-level tabs (the site already has eleven of those plus a sport
switcher, and more of them is what made it confusing), applied everywhere.

WHAT HE SUSPECTED AND THE MEASUREMENT DID NOT SUPPORT: duplicated content.
Four repeated section titles exist; three are one function emitting a
heading twice for two tables under one label, and "Teams" is Standings vs
Rosters, legitimately different pages. No real cross-page repetition, so
nothing was deduped.

Run directly: `python3 tests/test_organization.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _js():
    return _read("web", "js", "app.js")


def _fn(js, decl):
    """One function's source, cut at the next top-level function.

    A FIXED SLICE IS A TRIPWIRE ON THE WRONG THING. This test read
    `js[i:i + 1200]` and went red on 2026-08-23 because a COMMENT was
    added above the line it looks for — the contract it exists to protect
    was untouched. A test that fails when a comment grows is a test that
    teaches people to stop reading it.
    """
    i = js.index(decl)
    j = len(js)
    for end in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* ="):
        k = js.find(end, i + len(decl))
        if k != -1:
            j = min(j, k)
    return js[i:j]


# --- the component -----------------------------------------------------------
def test_a_room_with_nothing_in_it_is_never_given_a_tab():
    """THE RULE THAT MAKES THIS SAFE. The Record page hides most of its
    panels when scoped to one sport, so a fixed tab bar would offer five
    rooms and open two empty ones. Groups are built as strings first and
    only the ones with content become tabs."""
    js = _js()
    i = js.index("function subtabbedHTML(")
    body = js[i:i + 1400]
    assert 'groups.filter((g) => (g[3] || "").trim())' in body, body[:400]


def test_a_single_live_room_renders_with_no_bar_at_all():
    """Nothing becomes unreachable and nothing gains a tab bar it does not
    need — one room is just a page, exactly as before sub-tabs existed."""
    js = _js()
    i = js.index("function subtabbedHTML(")
    body = js[i:i + 1400]
    assert "if (live.length < 2) return" in body


def test_the_room_you_were_in_is_remembered():
    """Landing back on the first tab every time you glance at a page is the
    kind of small tax that makes people stop opening it."""
    js = _js()
    assert "const _subtab = {}" in js
    i = js.index("function bindSubtabs(")
    assert "_subtab[view] = id" in js[i:i + 1200]


def test_the_tabs_are_a_real_tablist_for_a_keyboard():
    """Five buttons a keyboard user has to Tab through to reach the sixth is
    not navigation, it is an obstacle course."""
    js = _js()
    i = js.index("function subtabbedHTML(")
    body = js[i:i + 1600]
    assert 'role="tablist"' in body and 'role="tab"' in body
    assert 'role="tabpanel"' in body
    assert 'aria-selected' in body
    bind = js[js.index("function bindSubtabs("):][:1600]
    assert "ArrowRight" in bind and "ArrowLeft" in bind


def test_only_one_room_is_ever_open():
    js = _js()
    bind = js[js.index("function bindSubtabs("):][:1600]
    assert "p.hidden = p.dataset.subgroup !== id" in bind


# --- the pages ---------------------------------------------------------------
def test_the_record_page_is_five_rooms_not_one_column():
    """22 sections in a single scroll was the worst offender by roughly ten
    times. They were never 22 subjects."""
    js = _js()
    i = js.index("function _recordRooms(")
    body = js[i:js.index("\nfunction ", i + 10)]
    for room in ("receipts", "products", "calibration", "learning", "health"):
        assert f'"{room}"' in body, room


def test_the_record_lead_is_inside_its_room_not_above_the_bar():
    """Rendered above the tabs, the page's own headline numbers would leave
    the bar floating in the middle of the page with content on both sides."""
    js = _js()
    assert "_recordRooms(d, src, pmv, scope, scoped, receipts)" in js
    i = js.index("function _recordRooms(")
    # `receipts` still lands inside the first room; the Records-by-book
    # sections (Ethan, 2026-09-01) ride directly after it in the same
    # room on the "all" scope. A sport's own sections LEAD its receipts
    # instead (2026-09-05, asked a second time because they sat under
    # everything), so the tail is guarded rather than repeated.
    assert '+ (scoped ? "" : recBookSections(d.book_records, scope))],' \
        in js[i:i + 2900]


def test_the_receipts_room_opens_on_the_receipts():
    """Ethan, 2026-08-20: "remove the paper bet section on the record page.
    its taking up to much space and we dont really need that area any more."

    It opened the tab with a paper/money split and a second list of a
    hundred paper bets, pushing the actual receipts below a screenful of
    apparatus. Nothing left the record with it: `overall` is
    `performance(conn)`, whose category default is ("main", "paper"), so
    both books were already pooled into every headline number and the
    panel only re-split what the curve had added together.

    IF IT IS EVER REBUILT, build it from `performance(conn, category="main")`.
    The removed version passed the POOLED book as its "Money rows" line, so
    the comparison it drew was paper against paper-plus-money — which is
    why this test pins the absence with the reason rather than just the
    absence.
    """
    js = _js()
    assert "recPaperBook" not in js, \
        "the paper/money split is back above the receipts"
    assert "paper_recent" not in js, \
        "the page is reading the hundred paper rows again"


def test_the_fantasy_page_is_four_rooms():
    js = _js()
    # Anchored past the lead, not on its exact concatenation — the
    # stale-usage banner joined the chain on 2026-08-24 and the claim
    # here is the four rooms, not the operands to the left of them.
    # Sliced to the END of the call, not a fixed window: the Waivers
    # room joined on 2026-08-26 and pushed "league" past 900 characters,
    # which is the same slice bug this suite keeps relearning. The claim
    # is that the four rooms exist, not that they fit in a byte count.
    i = js.index('subtabbedHTML("fantasy"')
    body = js[i:js.index("]) + _ffFoot", i)]
    for room in ("usage", "trade", "scripts", "league"):
        assert f'"{room}"' in body, room


def test_nothing_is_rendered_both_in_a_lead_and_in_a_room():
    """THE BUG THIS CAUGHT, in Chromium, on the first attempt: the offseason
    tracker and the draft kit rendered TWICE and there were two elements
    with id="sleeper-zone", because the strip that was supposed to remove
    them from the page lead silently matched nothing.

    An id is the cheap thing to count and the one that actually breaks —
    `getElementById` returns the first, so a later render can fill the copy
    nobody is looking at."""
    js = _js()
    i = js.index("const _ffLead = `")
    lead = js[i:js.index("`;", i)]
    for moved in ("sleeper-zone", "campHTML", "waiverPulseHTML",
                  "offseasonHTML", "draftKit"):
        assert moved not in lead, f"{moved} is in the lead AND in a room"


def test_an_unsearched_player_page_does_not_draw_every_profile():
    """MEASURED: 293 full profiles, 4,315 table rows, 139,451px — 155
    screens, on the page whose own tab hint is "search a player". The search
    box was filtering a DOM that had already been built in full."""
    js = _js()
    assert "function playerBrowseCap(" in js
    i = js.index("const capped = !q && players.length > cap")
    body = js[i:i + 600]
    assert "players.slice(0, cap)" in body


def test_an_empty_board_is_explained_not_apologised_for():
    """Ethan's render sweep, 2026-08-18: "NBA Players: rendered almost
    nothing (20 chars)". The twenty characters were a failed-search
    apology — with an empty quote in it — on a page nobody had searched;
    the board was simply empty, because the league is between seasons.
    The two states get different sentences now: an unsearched empty board
    names the sport and says where profiles come from, and the search
    apology is reserved for an actual search. Verified in Chromium: the
    NBA page draws 169 characters of explanation against the sample
    data's empty board."""
    # THE FUNCTION, NOT A NUMBER. This window went 4000 -> 9000 on
    # 2026-08-18 when the league-wide search branch landed ahead of the
    # empty-board copy, and blew past 9000 on 2026-08-23 when a COMMENT
    # was added inside it. Two false failures for one contract that never
    # changed. `_fn` cuts at the next top-level declaration, so the test
    # goes red when the ORDER is wrong and never when the file grows.
    body = _fn(_js(), "async function renderPlayers(")
    # Pinned by the apology's CODE form (curly quote + the interpolation
    # start), not its words — the first draft of this test matched the
    # words inside the fix's own comment, the same trap this suite has
    # now sprung four times.
    # Re-anchored 2026-09-01 when the apology grew the league's name in
    # front (the scoped search must SAY its scope): the stable code form
    # is now the tail of the sentence, not its head.
    apology = "players match “${"
    assert body.index("No priced props on the") < body.index(apology), \
        "the empty-board branch must be tried before the search apology"
    j = body.index("if (!q) {")
    assert "state.sport" in body[j:j + 700], "the empty state lost its sport name"


def test_the_search_reaches_the_league_not_just_the_board():
    """Ethan, 2026-08-18: "The search page for players isn't working
    still. You should be able too look up any player in the league too
    that specific sport." When the board has nothing, the answers come in
    order: the league API first (full profile cards fed by the history
    DB), the roster directory second (the offline fallback), the apology
    last. A stale keystroke's response must be dropped, and the head-only
    row a searched player rides in on must never register as a priced
    market — an unpriced chip would draw the pick block."""
    js = _js()
    body = _fn(js, "async function renderPlayers(")
    assert body.index("leagueSearch(q)") < body.index("rosterMatches(q)")
    assert body.count("!== q) return") >= 2, "the stale-keystroke guard"
    j = js.index("function profileHTML(")
    assert "rows.filter((r) => r.market_label)" in js[j:j + 700]
    k = js.index("async function leagueSearch(")
    assert "_leagueCache" in js[k:k + 700]
    # The search hits the ALL-LEAGUE endpoint. Pinning the exact query
    # string ("?sport=") was pinning the bug: it asserted the request was
    # scoped to one league, which is the thing Ethan asked us to stop
    # doing on 2026-08-23. The question is that the search is issued and
    # that a hit's LOGS come from that hit's own sport.
    k2 = js.index("async function leagueSearch(")
    req = js[k2:k2 + 900]
    assert "/api/players/search?q=" in req
    assert "sport=${encodeURIComponent(state.sport)}&q=" not in req, \
        "the search is scoped to one league again"
    k3 = js.index("async function leagueLogs(")
    logs = js[k3:k3 + 700]
    assert "/api/players/logs?sport=" in logs
    assert "sport || state.sport" in logs, \
        "a hit's logs must come from the hit's own league"


def test_searching_still_reaches_every_player():
    """The cap is on DISPLAY only. A cap applied before the filter would
    make anyone outside the first dozen unfindable, which is worse than the
    problem it fixes."""
    body = _fn(_js(), "async function renderPlayers(")
    # The dedupe ("const seen") became per-player GROUPING on 2026-08-17
    # — every market kept, one card per player — but the order contract
    # is the same: the search filter runs over the FULL list before any
    # grouping or display cap touches it.
    assert body.index("recs = recs.filter") < body.index("_profRows = new Map()")


def test_the_browse_cap_is_smaller_where_the_grid_is_one_column():
    """MEASURED AT 390x844 after the first cap shipped: `.player-grid` is
    `auto-fill, minmax(420px, 1fr)` — three columns on a laptop, ONE on a
    phone — so twelve cards stacked single-file came to 10,919px. Twelve
    point nine screens, which is the original complaint again on the device
    least able to afford it."""
    js = _js()
    i = js.index("function playerBrowseCap(")
    body = js[i:i + 400]
    assert "max-width: 760px" in body, body
    ns = re.findall(r"\b(\d+)\b", body.split("return")[1])
    assert "4" in ns and "12" in ns, ns


def test_the_cap_is_read_at_render_not_captured_once():
    """A rotated phone or a resized window is the same visitor. A constant
    read at load leaves them with whichever layout they started in."""
    js = _js()
    assert "const cap = playerBrowseCap();" in js, \
        "the cap is no longer evaluated per render"


def test_a_browser_without_matchmedia_gets_the_desktop_cap():
    """Failing open to FOUR would quietly halve a laptop's browse list."""
    js = _js()
    i = js.index("function playerBrowseCap(")
    body = js[i:i + 400]
    assert "window.matchMedia" in body and "typeof window" in body
    # The ELSE branch is the desktop number. Verified in node across all
    # three shapes: no matchMedia -> 12, desktop -> 12, phone -> 4. The
    # first version of this asserted the slice ended in a brace, which is
    # true of nothing in particular and proved no property at all.
    assert re.search(r"\?\s*4\s*:\s*12", body), body


# --- hierarchy ---------------------------------------------------------------
def test_section_titles_have_more_than_one_rank():
    """81 of them, all identical — so "Running P&L" and "Team-form sampler —
    measurement in progress" were the same announcement typographically."""
    css = _read("web", "css", "styles.css")
    assert ".section-title.lead" in css
    assert ".section-title.minor" in css


def test_the_quarantined_samplers_are_the_minor_rank():
    """They are deliberately kept visible and deliberately not competing
    with the number the page exists to show."""
    # Anchored on the MARKUP, not on the name. `.index()` on the bare name
    # found this file's own docstring quoting it — the same wrong-occurrence
    # trap that has bitten every string-scanning test in this repo.
    js = _js()
    for t in ("Looser-gates sampler", "Team-form sampler",
              "Stale-line sampler", "Not replayed yet", "Current model only"):
        titled = re.findall(r'class="section-title([^"]*)">' + re.escape(t), js)
        assert titled, f"{t} is no longer a section title"
        assert all("minor" in c for c in titled), f"{t} is not demoted"


def test_the_ranks_differ_by_size_and_weight_not_only_colour():
    """The mute tokens are already at the bottom of what stays legible —
    see the contrast ratchet — so rank cannot be spent on colour."""
    css = _read("web", "css", "styles.css")
    i = css.index(".section-title.minor {")
    block = css[i:i + 260]
    assert "font-size" in block
    assert "text-transform" in block or "letter-spacing" in block


# --- "hard to find which tab has what" ---------------------------------------
def test_every_tab_says_what_it_shows():
    """The names are insider shorthand — "Edge Board", "Scanner", "Long
    Shots". Each already carried a data-hint written for the phone menu;
    on desktop it was invisible, so the shorthand was all you got."""
    html = _read("web", "index.html")
    tabs = re.findall(r'<button class="nav-btn[^"]*"([^>]*)>', html)
    assert tabs, "no nav buttons found"
    missing = [t for t in tabs if "data-hint" not in t]
    assert not missing, f"{len(missing)} tab(s) with no hint"
    assert 'id="nav-hint"' in html


def test_the_hint_is_set_on_first_load_too():
    """The landing view is active in the markup and never goes through the
    view switch, so a hint set only there is blank on the page people
    actually arrive at — which is what the first version did."""
    js = _js()
    assert "function syncNavHint(" in js
    i = js.index("function syncNavHint(")
    assert 'querySelector(".nav-btn.active")' in js[i:i + 500]
    assert js.count("syncNavHint(") >= 3          # def + switch + startup


def test_the_hint_sits_under_the_tabs_rather_than_wherever_flex_put_it():
    """The insider-shorthand problem the hint solved is solved by the
    sidebar now (NEW LOOK, 2026-08-11): every page item carries its
    data-hint, and the bar's running hint line retired — display:none,
    not deleted, so syncNavHint keeps a target and nothing null-crashes."""
    css = _read("web", "css", "styles.css")
    i = css.index(".nav-hint {")
    assert "display: none" in css[i:i + 120]
    html = _read("web", "index.html")
    assert html.count("data-hint=") >= 10, "the per-page hints are gone"


def _first_room():
    """The element ids in REC_ROOMS' first room, read out of the source.

    Parsed rather than string-searched: `"games-title" in board` is true
    of the whole literal as well as of room one, so a slice taken by
    eyeballing the text would pass no matter which room the venues ended
    up in."""
    js = _js()
    i = js.index("const REC_ROOMS = [")
    lit = js[i:js.index("\n];", i)]
    # The first room's id list is the first bracketed run of quoted names
    # that contains more than one entry.
    for m in re.finditer(r"\[\s*(\"[^\]]+?)\]", lit, re.S):
        names = re.findall(r'"([a-z0-9-]+)"', m.group(1))
        if len(names) > 3:
            return names
    raise AssertionError("could not find REC_ROOMS' first room")


# --- Recommended's rooms -----------------------------------------------------
def test_the_recommended_board_is_three_rooms():
    """MEASURED IN CHROMIUM, against the checked-in sample slate: the NFL
    board ran 8.1 screens at 1440x900, and two blocks were 4.8 of them —
    `#gamebets` at 3.23 screens and `#rest-watch` at 1.50. Grouped, the
    tallest room is 3.3 and the one you land on is 2.7."""
    js = _js()
    i = js.index("const REC_ROOMS = [")
    # THE WHOLE LITERAL, not `js[i:i + 1200]`. That window went red on
    # 2026-08-30 because a COMMENT was added inside the array and pushed
    # `rest-watch` past byte 1200 — the contract this protects was
    # untouched. `_fn` at the top of this file already carries the same
    # lesson: "a test that fails when a comment grows is a test that
    # teaches people to stop reading it."
    body = js[i:js.index("\n];", i)]
    for room in ("board", "gamebets", "watch"):
        assert f'["{room}"' in body or f'"{room}",' in body, room
    assert "gamebets-title" in body and "rest-watch" in body


def test_the_venue_block_stays_in_the_room_you_land_on():
    """Ethan put the ballparks first on purpose — park, roof and wind are
    what the picks are read against. Grouping is not licence to reorder,
    so `games-title` and `games` open room one."""
    board = _first_room()
    # Since the fidelity pass the strip travels in its wrappers —
    # games-head (title + working controls) and games-outer (scroller +
    # arrows) — so the room moves the whole strip, chrome included.
    assert "games-head" in board and "games-outer" in board
    # In the FIRST room, not merely somewhere in the list — the whole
    # constraint is which room you land on.
    assert "gamebets" not in board and "rest-watch" not in board


def test_the_sliders_travel_with_the_cards_they_filter():
    """A Min-edge dial in a room containing no prop is a control that does
    nothing to anything on screen."""
    js = _js()
    i = js.index("const REC_ROOMS = [")
    board = js[i:js.index('["gamebets"', i)]
    assert '"rec-controls"' in board and '"cards"' in board
    assert 'id="rec-controls"' in _read("web", "index.html")


def test_the_rooms_are_rejudged_on_every_render_not_decided_once():
    """`#gamebets` is empty until the slate arrives, `#preseason-board`
    fills only in August, and switching leagues empties half the page. A
    room decided once at startup would offer a Game bets tab on a night
    with no game bets."""
    js = _js()
    # ORDER, NOT ADJACENCY. This read
    # `"renderRecommended();\n  // AFTER the renderers"` and went red on
    # 2026-08-30 when `renderLikelyTop()` was inserted between the two —
    # which is exactly the arrangement the contract wants, since the
    # grouping has to run after every renderer that fills a block. The
    # contract is that grouping comes LAST, so that is what is asserted.
    main = js[js.index("  renderRecommended();"):]
    at = main.index("  groupRecommended();")
    for renderer in ("renderRecommended();", "renderLikelyTop();"):
        assert main.index(f"  {renderer}") < at, renderer
    # The slider path re-renders the board and must re-group with it.
    assert ("renderGameBets(); renderRecommended(); groupRecommended();"
            in js)
    i = js.index("function subtabbedDOM(")
    body = js[i:i + 3600]
    assert "const live = groups.filter" in body, "emptiness must be recomputed"


def test_emptiness_is_judged_by_content_not_by_height():
    """Everything inside an inactive panel measures zero — `hidden` is
    display:none — so an offsetHeight test would call every room but the
    open one empty and collapse the bar to a single tab."""
    js = _js()
    i = js.index("function subtabbedDOM(")
    body = js[i:i + 3600]
    filled = body[body.index("const filled ="):body.index("const live =")]
    assert "offsetHeight" not in filled and "getBoundingClientRect" not in filled
    assert "textContent" in filled and "children.length" in filled
    # An element its own renderer switched off is not content.
    assert 'display === "none"' in filled


def test_an_empty_rooms_panel_is_hidden_and_never_removed():
    """Its elements are where fifteen renderers write by id. A renderer
    whose target has been deleted fails silently for the rest of the
    session."""
    js = _js()
    i = js.index("function subtabbedDOM(")
    body = js[i:i + 3600]
    assert ".remove()" not in body and "removeChild" not in body


def test_no_renderer_had_to_change_to_get_rooms():
    """The whole point of the DOM variant. Recommended's blocks are
    declared in index.html and filled in place by functions that find them
    by id; rebuilding the page as strings to reuse `subtabbedHTML` would
    have meant rewriting fifteen renderers to group one page."""
    html = _read("web", "index.html")
    for el in ("stats", "games", "best-bets", "gamebets", "rest-watch",
               "incentive-watch", "team-form", "cards"):
        assert f'id="{el}"' in html, el


def test_the_inventory_walks_the_rooms_before_it_harvests():
    """The preservation net records what is VISIBLE, and a closed room is
    display:none. Without this, growing rooms reads to the net as deleting
    every string inside them — the safety net reporting a reorganisation
    as data loss, which is how a safety net gets ignored."""
    inv = _read("tools", "inventory.mjs")
    assert "roomHarvest" in inv
    assert ".subnav-btn" in inv
    # Counts stay at rest: summing cards across rooms reports a number
    # nobody ever sees on one screen.
    assert "counts: r.counts" in inv


# --- the 2026-08-18 batch: the bar that moved, and two smooshed pages --------
def test_the_tab_bar_cannot_be_dragged_on_a_phone():
    """Ethan, 2026-08-18, screen recording of the fantasy page: "look how
    you can move that bar, fix that so that cant happen." The phone
    override made the row a horizontal scroller, and a scrollable row is
    a DRAGGABLE row — it parked wherever the finger left it, half a tab
    clipped at the screen edge and whole rooms hidden with no hint they
    exist. The row wraps now, so no .subnav rule may bring the scroller
    back. Checked on every .subnav rule, not just the one that had it."""
    css = _read("web", "css", "styles.css")
    starts = [m.start() for m in re.finditer(r"\.subnav\s*\{", css)]
    assert starts, "the subnav styles are gone entirely"
    for i in starts:
        rule = css[i:css.index("}", i)]
        assert "overflow-x" not in rule and "nowrap" not in rule, \
            "a .subnav rule is a horizontal scroller again"
    i = css.index(".subnav {")
    assert "flex-wrap: wrap" in css[i:css.index("}", i)]
    # The scrollbar-hider only ever existed to dress the scroller.
    assert ".subnav::-webkit-scrollbar" not in css


def test_the_buy_low_card_speaks_english():
    """The xFP buy-low card shipped with a sentence whose subject was a
    typo — Ethan circled it: "where it says 'he say the production is
    coming' makes no sense so fix that." The card's job is to be read by
    someone deciding a trade; it gets one plain sentence, parallel to the
    volume branch beside it."""
    js = _js()
    assert "his say the production" not in js
    assert "his chances are worth more than he has scored from them so far" in js


def test_game_script_cards_wear_the_clubs_marks_and_one_grid():
    """Ethan, 2026-08-18: "organize this game script page better and also
    include team logos next to the team names, i think that makse it look
    more professional." The card used to name each team in words up to
    six times across three stacked prose lines; now the matchup header
    carries both clubs' marks and every per-team number sits in one
    two-row grid — read across for a team, down for a stat."""
    js = _js()
    # The card template nests its own `.join("")` (the coach-change
    # warnings), so the block runs to the next statement, not to a join.
    i = js.index("const scriptCards =")
    block = js[i:js.index("const bsCount", i)]
    assert 'teamMark(s.away, 22, nflMap(), "nfl")' in block
    assert 'teamMark(s.home, 22, nflMap(), "nfl")' in block
    assert 'class="gs-grid"' in block
    # The grid's rows go through one builder, so the away and home lines
    # cannot drift apart in format; it wears the mark at row scale too.
    j = js.index("const gsRow =")
    assert 'teamMark(t, 18, nflMap(), "nfl")' in js[j:i]
    # The stat columns each explain themselves where a finger can ask.
    for col in (">Implied<", ">PROE<", ">EPA/play<", ">Pace<"):
        assert col in block, f"the {col} column lost its header"
    css = _read("web", "css", "styles.css")
    for sel in (".gs-match {", ".gs-grid {", ".gs-tm {"):
        assert sel in css, f"{sel} is unstyled"


def test_injury_rows_are_lines_not_columns():
    """Ethan, 2026-08-18, phone screenshot of the injuries page: "organize
    this page better as well. it seems so smooshed." It was a six-column
    table — Team, Player, Status, Injury, Filed, Return — which at 393px
    crushed every column and scrolled Status half off the screen. A row
    is now two lines with nothing to crush: identity and detail stack on
    the left, the verdict right-aligns."""
    js = _js()
    i = js.index("function injRow(")
    fn = js[i:js.index("\n}\n", i)]
    assert "<tr" not in fn and "<td" not in fn, "the table row is back"
    assert 'class="inj-line"' in fn
    assert "injTone(r.status)" in fn, "the status lost its availability colour"
    j = js.index("async function renderInjuries(")
    body = js[j:js.index("\n}\n", j)]
    assert "<table" not in body
    # BOTH SECTIONS, wherever they are written. The by-team block moved
    # into injTeamBlock() on 2026-08-25 when each team became a
    # <details>, so counting inside renderInjuries alone found one and
    # called a refactor a regression. The claim is that the two sections
    # share ONE row layout, not that both are typed in the same function.
    team_block = js[js.index("function injTeamBlock("):]
    team_block = team_block[:team_block.index("\n}\n")]
    assert body.count('class="card inj-list"') == 1, \
        "fresh-this-week lost the shared row layout"
    assert team_block.count('class="card inj-list"') == 1, \
        "the by-team list no longer shares the one row layout"
    # The column headers died with the columns.
    assert "INJ_HEAD" not in js
    css = _read("web", "css", "styles.css")
    for sel in (".inj-line {", ".inj-line-sub {", ".inj-line-right {"):
        assert sel in css, f"{sel} is unstyled"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
