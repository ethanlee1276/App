"""The header was taking a quarter of the screen. Keeping it that way.

Eleven sport buttons made the desktop switcher 1,195px wide, which forced
the status row and the page nav each onto a line of their own: three
stacked rows, 227px, 25% of a 900px desktop and 28% of a laptop. Six
leagues stay visible because the league is the primary axis of the site;
the five tools moved behind a "More" menu.

Two things have to hold, and the second is the one that bites.

**The chrome has to stay small as sports get added.** The switcher grew
past a screen width once already; the guard is that tools live behind a
menu rather than in the row.

**The header height must never depend on WHICH sport is showing.** College
football hides three tabs it has no engine for, so at 1,024px it fitted on
one line while every other sport wrapped — 120px on one board and 168px on
the next, which moves everything under a finger already on its way down.
Content must not decide layout.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


# --- the structure ----------------------------------------------------------
def _group(html, name):
    """One `.sport-group`'s markup, by data-group name."""
    i = html.index(f'<div class="sport-group" data-group="{name}">')
    return html[i:html.index("</div>", i)]


def test_the_switcher_has_three_named_groups_and_nothing_loose():
    """Leagues, then Markets, then what's left behind More.

    The original split was leagues-visible / everything-else-hidden, because
    seven equal-looking buttons where two behaved differently was the
    confusion it was made to fix. Markets is the same idea taken one step
    further rather than a reversal of it: Polymarket and Fantasy are places
    you go looking for a bet on the same rhythm as a league, so hiding them
    cost a click every session; Why Us and About are about the SITE and
    belong exactly where they are.

    What the test still enforces is the part that mattered — no button is
    loose in the row. Every one is inside a named group.
    """
    html = _read("web", "index.html")
    leagues = re.findall(r'data-sport="(\w+)" data-kind="league"', html)
    tools = re.findall(r'data-sport="(\w+)" data-kind="tool"', html)
    assert set(leagues) == {"nfl", "cfb", "mlb", "nba", "wnba", "ufc"}
    # Rosters is NOT here: a roster belongs to a league, so it is a tab
    # inside each sport rather than a tool you navigate away to.
    # "record" joined the tools when The Book was promoted out of the
    # per-sport tab row: the receipts cover every sport plus the whole
    # learning loop, which is exactly what a standalone page is for.
    assert set(tools) == {"intel", "fantasy", "why", "about", "record"}
    assert 'data-view="rosters"' in html, "the per-sport tab is missing"

    for sport in leagues:
        assert f'data-sport="{sport}"' in _group(html, "leagues"), sport
    markets = _group(html, "markets")
    for sport in ("intel", "fantasy"):
        assert f'data-sport="{sport}"' in markets, f"{sport} left the row"
    assert 'data-sport="record"' in _group(html, "record"), \
        "The Book left its own group"
    # Only the site-about pages stay behind the menu, and they stay inside
    # the wrapper that positions the dropdown.
    more = html[html.index('id="sport-more"'):]
    more = more[:more.index("</div>\n      </div>")]
    for tool in ("why", "about"):
        assert f'data-sport="{tool}"' in more, f"{tool} is loose in the row"
    for sport in ("intel", "fantasy"):
        assert f'data-sport="{sport}"' not in more, f"{sport} is still hidden"


def test_the_markets_pair_is_separated_from_the_leagues_not_merged():
    """Visible is not the same as 'a league'. A hairline before the first
    markets button says the axis changed — without it this is the seven
    equal buttons the group split was made to stop."""
    css = _read("web", "css", "styles.css")
    assert '.sport-group[data-group="markets"] .sport-btn:first-child' in css
    rule = css[css.index('.sport-group[data-group="markets"] .sport-btn:first-child'):]
    assert "border-left" in rule[:rule.index("}")]


def test_the_markets_group_has_its_own_phone_card_and_slot():
    """On a phone the groups become labelled cards. A group with no order
    lands at 0 and jumps above the leagues it was meant to follow."""
    html = _read("web", "index.html")
    assert 'data-head="markets"' in html, "no heading for the phone card"
    css = _read("web", "css", "styles.css")
    for sel in ('.menu-open .menu-head[data-head="markets"]',
                '.menu-open .sport-group[data-group="markets"]'):
        assert sel in css, sel
        assert "order:" in css[css.index(sel):css.index(sel) + 90], sel


def test_the_more_menu_exists_and_is_wired():
    html = _read("web", "index.html")
    assert 'id="more-toggle"' in html
    assert 'aria-expanded="false"' in html and 'aria-haspopup="true"' in html
    app = _read("web", "js", "app.js")
    for fn in ("initMoreMenu", "closeMoreMenu", "markMoreMenu"):
        assert f"function {fn}(" in app, f"{fn} missing"
    assert "initMoreMenu();" in app, "defined but never called"


def test_the_menu_closes_every_way_a_menu_should():
    app = _read("web", "js", "app.js")
    fn = app[app.index("function initMoreMenu()"):]
    fn = fn[:fn.index("\nfunction markMoreMenu")]
    assert "Escape" in fn, "no keyboard escape"
    assert "wrap.contains(e.target)" in fn, "an outside click doesn't close it"
    assert 'querySelectorAll(".sport-btn:not(.more-toggle)")' in fn, \
        "picking an item should not need a second tap"


def test_a_button_with_no_sport_can_never_be_the_active_sport():
    """The More toggle wears .sport-btn for its looks. Without a guard it
    fell through the switcher with an undefined data-sport, blanked
    state.sport, and then matched the active test because
    undefined === undefined — so opening the menu marked itself as the
    current league and un-marked the real one."""
    app = _read("web", "js", "app.js")
    assert app.count("!!b.dataset.sport && b.dataset.sport ===") >= 1
    assert app.count("!!x.dataset.sport && x.dataset.sport ===") >= 2
    bind = app[app.index("function bind()"):]
    bind = bind[:bind.index("STANDALONE_MODES.includes(b.dataset.sport)")]
    assert "if (!b.dataset.sport) return;" in bind


def test_being_inside_a_tool_page_is_still_visible():
    """Collapsing five buttons into a menu must not cost 'where am I'."""
    app = _read("web", "js", "app.js")
    assert app.count("markMoreMenu();") >= 3, \
        "the marker has to refresh on sport switch, standalone entry and exit"
    css = _read("web", "css", "styles.css")
    assert ".more-toggle.has-active" in css


# --- the layout rules -------------------------------------------------------
def test_the_desktop_rows_are_assigned_not_left_to_the_wrap_algorithm():
    """Letting flex decide produced three rows: the brand got shrunk below
    its content width, the switcher wrapped inside it, and the nav and
    status row each took a line."""
    css = _read("web", "css", "styles.css")
    block = css[css.index("@media (min-width: 761px)"):]
    rule = block[block.index(".brand { flex:"):]
    rule = rule[:rule.index("}")]
    # Properties, not an exact string — the declaration gained an `order`
    # and the string match broke on a rule that was still correct.
    assert "flex: 1 0 100%" in rule, "the brand row must claim its own line"
    assert "flex-wrap: nowrap" in rule, "the switcher must not wrap inside it"
    # Row 2 has to be ordered, or the status floats mid-row.
    assert ".nav { flex: 0 1 auto; min-width: 0; order: 2; }" in block
    assert "order: 3" in block[block.index(".slate-meta { margin-left: auto"):
                               block.index(".slate-meta { margin-left: auto") + 160]


def test_the_status_row_drops_for_every_sport_or_none():
    """The bug this prevents: at 1,024 college football fitted on one line
    (it hides three tabs) while every other sport wrapped, so the header
    was 120px on one board and 168px on the next."""
    css = _read("web", "css", "styles.css")
    assert "@media (min-width: 761px) and (max-width: 1247px)" in css
    band = css[css.index("@media (min-width: 761px) and (max-width: 1247px)"):]
    band = band[:band.index("\n}")]
    assert ".slate-meta { flex: 1 0 100%;" in band


def test_the_phone_status_row_is_a_fixed_grid():
    """A wrapping row landed on a different number of lines per sport and
    the header changed height mid-tap. A fixed grid is the same height
    whatever the date string says."""
    css = _read("web", "css", "styles.css")
    i = css.index(".slate-meta { flex: 1 1 100%; order: 5; display: grid;")
    block = css[i:i + 240]
    assert "grid-template-columns: auto auto minmax(0, 1fr)" in block, \
        "the phone status row is no longer a fixed single-row grid"


def test_the_phone_menu_has_no_toggle_inside_the_menu():
    """The slide-down menu already groups the tools under their own
    heading; a second toggle in there would be a control that opens a
    control."""
    css = _read("web", "css", "styles.css")
    # There are several phone blocks; the rule may live in any of them, so
    # search them all rather than betting on which one (rindex found the
    # wrong one and failed a rule that was present).
    blocks = css.split("@media (max-width: 760px)")[1:]
    joined = "".join(b[:b.index("\n}")] if "\n}" in b else b for b in blocks)
    assert ".sport-more { display: contents; }" in joined
    assert ".more-toggle { display: none !important; }" in joined



def _media_block(css, query):
    """The body of an @media block, or "" when there is no such query."""
    needle = "@media " + query
    i = css.find(needle)
    if i < 0:
        return ""
    depth, out, started = 0, [], False
    for ch in css[i:]:
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                break
        out.append(ch)
    return "".join(out)


# --- the two tabs Standings and Rosters added -------------------------------
def test_the_tablet_nav_is_one_scrolling_row_not_two_stacked_ones():
    """Ten tabs do not lay out in a row at 761-1023px. They wrapped, and
    the header grew to 244px on an iPad in portrait — a quarter of the
    screen handed to chrome, which is the exact complaint the header work
    already answered at other widths."""
    css = _read("web", "css", "styles.css")
    block = _media_block(css, "(min-width: 761px) and (max-width: 1023px)")
    assert block, "no tablet-width nav rule at all"
    assert "flex-wrap: nowrap" in block, "the nav can still wrap to two rows"
    assert "overflow-x: auto" in block, "a nowrap row with no scroll hides tabs"


def test_the_tablet_sport_switcher_does_not_wrap_either():
    """Six leagues plus More is ~497px of buttons; at 768 they took a
    second row and pushed the brand row from 46px to 88."""
    css = _read("web", "css", "styles.css")
    assert ".sport-switch .sport-btn" in css
    block = css[css.index(".sport-switch .sport-btn"):]
    block = block[:block.index("}") + 1]
    assert "padding" in block and "font-size" in block


def test_the_sport_switcher_is_not_given_a_scroll_container():
    """It cannot have one: the More dropdown is absolutely positioned, and
    a scrolling parent would clip it open. Tighter buttons, not scrolling."""
    css = _read("web", "css", "styles.css")
    i = css.index("The sport switcher at tablet widths")
    # The one @media block that follows that comment, brace-matched.
    block = _media_block(css[i:], "(min-width: 761px) and (max-width: 1023px)")
    assert block, "the tablet sport-switcher rule vanished"
    assert "overflow-x" not in block, \
        "a scroll container here clips the More menu open"


def test_the_view_transition_cannot_scroll_the_page_sideways():
    """The tab slide-in translates a view by 30px, which widened the
    DOCUMENT for the third of a second the animation ran — so a swipe
    landing mid-transition jogged the whole page sideways on a phone."""
    css = _read("web", "css", "styles.css")
    main = css[css.index("main { max-width"):]
    main = main[:main.index("}") + 1]
    assert "overflow-x: clip" in main or "overflow-x: hidden" in main


def test_the_url_and_the_page_can_never_disagree():
    """Nothing listened for a hash change, so back, forward, a pasted
    #standings link and an in-page anchor all moved the address bar while
    leaving the previous view on screen — and the URL you then copied
    pointed at something you were not looking at."""
    js = _read("web", "js", "app.js")
    assert 'addEventListener("hashchange"' in js
    # A tab TAP is a navigation and earns a history entry, so the phone's
    # back-swipe returns to the tab you came from.
    assert "switchView(b.dataset.view, true)" in js
    assert "history.pushState" in js

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
