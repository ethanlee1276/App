"""Two pages answered the same question, each with half the answer.

Ethan, 2026-09-10: "when you search a player, we need to combine the page
we just did where we show the sims and versus and all that shit with the
current bar charts and all of that."

THE SPLIT. The PROP PAGE (`renderPropPage`) carried the depth — shop the
price, how the line moved today, the game script, why the pick, what it
had to clear, its comparables, the sim lab. The PLAYER SEARCH CARD
(`profileHTML`) carried the bar chart, the form tiles, the market chips
and the log table. Neither had the other's half, and the card is what a
reader lands on when they type a name, which is nearly always how they
arrive.

WHY IT IS A FLAG AND NOT THE NEW DEFAULT, which is the part of this
change most likely to be "simplified" later by somebody who has not read
the measurement in `renderPlayers`: with no query that page once rendered
293 full profiles — 4,315 table rows, 139,451 pixels. Multiplying an
unsearched browse by eight more sections walks straight back into it. A
SEARCH gets the depth; a browse stays a list. `openPlayerRoute` fills the
search box before it renders, so the addressable player page is always
the deep one.

TWO TRAPS PAID FOR HERE. `shown.map(profileHTML)` hands the callback the
INDEX as its second argument, which is where the options object goes — the
flag would have read as simply not working. And the market chips
re-render by replacing the element they sit inside, so a deep card has to
be ONE outermost element or a chip switch swaps the chart and leaves the
previous market's price table and sim lab sitting underneath it.

Run directly: `python3 tests/test_player_page_depth.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _rule(sel):
    """One CSS rule's body, by selector."""
    i = CSS.index(sel + " {")
    return CSS[i:CSS.index("}", i)]


def _fn(name):
    """The body of one JS function, by name."""
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


# --- the prop page's own sections, on the search card -----------------------
def test_the_card_carries_every_section_the_prop_page_has():
    """The report, in one assertion. Each is the PROP PAGE'S OWN function
    called unchanged — a second implementation would be a second thing to
    keep in step, which is the trap the peek overlay's comment already
    names."""
    fn = _fn("propDepthHTML")
    for call in ("booksTableHTML(r)", "lineMoveHTML(r)", "scriptCardHTML(r)",
                 "chainHTML(r)", "checksHTML(r)", "compsHTML(r)",
                 "simLabHTML(r)"):
        assert call in fn, call
    assert "Why this pick" in fn, "the reasons list did not come across"


def test_the_depth_never_draws_a_second_log_table_or_versus_block():
    """The point of combining two pages is one of each, not two. The card
    above already carries both; what is added is only what it lacked."""
    fn = _fn("propDepthHTML")
    assert "vsBlockHTML" not in fn, "a second versus block"
    assert "propLogRows" not in fn and "log-table" not in fn, \
        "a second game log under the one the chart already draws"
    assert "propFormRows" not in fn, "a second form block under the tiles"


def test_the_priced_card_is_the_only_one_that_grows_it():
    """A market nobody priced tonight has no book table, no tape, no
    checks and no sim — the history card would draw eight empty strings
    and a wrapper."""
    assert "pricedProfileHTML(priced.get(mkt), chips, vsTail, deep)" in APP
    hist = _fn("historyProfileHTML")
    assert "propDepthHTML" not in hist


# --- one outermost element --------------------------------------------------
def test_a_deep_card_is_one_element_and_not_two_siblings():
    """`.prof-tab`'s handler replaces the element the chip sits inside.
    Two siblings would swap the article and orphan the depth."""
    fn = _fn("pricedProfileHTML")
    assert '`<div class="profile-deep">${art}${propDepthHTML(r)}</div>`' in fn
    assert ": art;" in fn, "the shallow card should stay a bare article"


def test_switching_markets_replaces_the_whole_unit_and_keeps_its_depth():
    i = APP.index('e.target.closest(".prof-tab")')
    fn = APP[i:i + 1400]
    assert 'chip.closest(".profile-deep") || chip.closest(".profile")' in fn, \
        "the chip still replaces the article alone"
    # AND RE-RENDERS AT THE SAME DEPTH. Read back off the DOM rather than
    # remembered, so a chip switch cannot quietly turn a deep card
    # shallow — which would look like the sections vanishing at a tap.
    assert 'deep: card.classList.contains("profile-deep")' in fn


# --- a search is deep, a browse is not --------------------------------------
def test_the_search_render_passes_an_options_object_not_the_map_index():
    """`shown.map(profileHTML)` passes the INDEX where the options go.
    `{deep}` off a number is undefined, which is the shallow card — the
    flag would have looked simply broken."""
    assert "shown.map((p) => profileHTML(p, { deep: !!q })).join" in APP
    # `.join` on the end, because the comment beside the call quotes the
    # bare form to explain what it must not be — matching that would fail
    # against the very note that documents the trap.
    assert "shown.map(profileHTML).join" not in APP


def test_an_unsearched_browse_stays_shallow():
    """The measurement this defers to is forty lines above it in the same
    function: 293 profiles, 139,451px. `!!q` is what keeps the depth on
    the one player who was asked about."""
    i = APP.index("async function renderPlayers(")
    body = APP[i:APP.index("\n/* The UFC hero", i)]
    assert "deep: !!q" in body
    assert "139,451px" in body, "the measurement that justifies the flag is gone"


def test_the_addressable_player_page_is_always_the_deep_one():
    """`openPlayerRoute` is what `#player/nfl/<name>` and every roster row
    lands on. It fills the search box first, so `!!q` is true by the time
    the card is drawn."""
    fn = _fn("openPlayerRoute")
    assert "state.search = name" in fn
    assert fn.index("state.search = name") < fn.index("renderPlayers()")


def test_the_peek_overlay_stays_the_quick_look():
    """Ethan asked for the popup precisely so a chart would not cost a
    page (2026-08-22). A sim lab in a modal is the opposite of that."""
    fn = APP[APP.index("async function openPeek("):]
    fn = fn[:fn.index("\nfunction closePeek(")]
    assert re.search(r"profileHTML\(name\)(?!\s*,)", fn), \
        "the peek asked for the deep card"


# --- several sims on one page -----------------------------------------------
def test_the_sim_lab_is_keyed_by_its_prop():
    """Three cards on a search page meant three elements named `sim-run`,
    `getElementById` answering with the first one whatever was clicked,
    and two labs that never ran."""
    fn = _fn("simLabHTML")
    assert 'data-sim="${escapeAttr(propId(r))}"' in fn
    assert 'id="sim-run"' not in APP and 'id="sim-bars"' not in APP, \
        "a fixed id is back, so only one lab on a page can work"


def test_the_sim_resolves_its_row_the_way_every_other_door_does():
    i = APP.index('e.target.closest(".sim-run")')
    fn = APP[i:i + 700]
    assert "findProp(lab.dataset.sim)" in fn, \
        "a registry that would have to be kept in step with the board"
    assert "lab.dataset.running" in fn, "two taps would race two animations"


def test_the_running_flag_is_cleared_when_the_run_ends():
    """Otherwise the lab runs once and is dead for the life of the page —
    the same defect as the id collision, arriving later."""
    fn = _fn("runSim")
    assert "delete lab.dataset.running" in fn


def test_the_sim_writes_inside_its_own_card():
    fn = _fn("runSim")
    assert 'lab.querySelector(".sim-bars")' in fn
    assert 'lab.querySelector(".sim-read")' in fn
    assert "getElementById" not in fn


def test_the_prop_page_no_longer_binds_one_by_hand():
    """One wiring, not two: the delegated listener covers the prop page
    too, and a leftover bind would double every run on it."""
    assert "bindSimLab" not in APP


# --- and a door to the bet's own page ---------------------------------------
def test_the_pick_block_opens_the_props_own_page():
    """Ethan, 2026-09-10, over the CFB prop page: "when you search a
    player, you should be able too click on them and it will pull up this
    page with ALLLLL the information."

    He could not. The card has carried the prop page's depth since this
    morning, but it was never a DOOR — so the one block it could not
    reach was the page built for the bet itself: the full `propAnalysis`
    chart with the line through it and the hit-rate/EV/confidence strip,
    which is what he screenshotted."""
    fn = _fn("pricedProfileHTML")
    assert '<div class="profile-pick"${propAttrs(r)}>' in fn, \
        "the pick block is not a door"
    # THE SITE'S ONE DEFINITION OF AN OPENABLE PROP, not a second copy of
    # the rule — a row with fewer than three logged games opens a page
    # whose centrepiece is missing, and `propAttrs` is what knows that.
    assert "propOpenable(r)" in fn, "the arrow appears on rows with no page"


def test_the_door_is_the_pick_and_not_the_whole_card():
    """A deep card runs several screens and contains the market chips,
    the versus select and the sim lab. A click target that tall swallows
    all of them."""
    # THE OPENING TAG, not the region before the pick block. Scanning the
    # region swept up the comment that explains this very decision, which
    # names `propAttrs` — the third time today an assertion has failed
    # against its own note.
    fn = _fn("pricedProfileHTML")
    i = fn.index('<article class="profile"')
    tag = fn[i:fn.index(">", i) + 1]
    assert "data-prop" not in tag and "propAttrs" not in tag, \
        f"the whole article became the door: {tag}"


def test_a_door_inside_the_peek_closes_the_peek():
    """The overlay draws this same card. Without this the tap would
    switch the view UNDERNEATH the dialog and leave it sitting over the
    prop page with the body still scroll-locked behind it."""
    fn = _fn("openProp")
    assert "closePeek()" in fn
    # IN THE FUNNEL, not in the two listeners. Click and keyboard both
    # come through here, and so does every router path.
    assert fn.index("closePeek()") < fn.index("switchView(\"prop\")")


def test_the_door_looks_like_one():
    """Ethan, 2026-09-09: a lot of the buttons blend into the text, so
    you cannot tell they are buttons."""
    assert "cursor: pointer" in _rule(".profile-pick[data-prop]")
    assert ".profile-pick .pp-go" in CSS


# --- styles -----------------------------------------------------------------
def test_the_new_surfaces_have_their_styles():
    for sel in (".profile-deep", ".prof-depth"):
        assert sel + " " in CSS or sel + "," in CSS or sel + "{" in CSS, sel


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
