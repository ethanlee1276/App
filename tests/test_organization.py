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
    assert "receipts]," in js[i:i + 2600]


def test_the_fantasy_page_is_four_rooms():
    js = _js()
    i = js.index("host.innerHTML = _ffLead + subtabbedHTML(")
    body = js[i:i + 900]
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
    assert "const PLAYER_BROWSE" in js
    i = js.index("const capped = !q && players.length > PLAYER_BROWSE")
    body = js[i:i + 600]
    assert "players.slice(0, PLAYER_BROWSE)" in body


def test_searching_still_reaches_every_player():
    """The cap is on DISPLAY only. A cap applied before the filter would
    make anyone outside the first dozen unfindable, which is worse than the
    problem it fixes."""
    js = _js()
    i = js.index("async function renderPlayers(")
    body = js[i:i + 900]
    assert body.index("recs = recs.filter") < body.index("const seen")


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
    """MEASURED IN CHROMIUM: the header is a flex ROW with hand-assigned
    order on every child — brand 1, nav 5, standing 9, slate-meta 10. A new
    element defaults to order 0, and this line rendered ABOVE the masthead,
    reading as a stray caption on the logo."""
    css = _read("web", "css", "styles.css")
    i = css.index(".nav-hint {")
    block = css[i:i + 400]
    assert "order:" in block, "no order — flex will sort it to the front"
    assert "flex: 1 1 100%" in block, "no line of its own"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
