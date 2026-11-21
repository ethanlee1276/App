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


def _code(name):
    """One function's CODE, with its prose removed.

    FOUR ASSERTIONS IN THIS FILE FAILED AGAINST THEIR OWN COMMENTS before
    this existed — a note explaining why something must NOT appear names
    the very identifier the assertion is scanning for. `_fn` is kept as
    it is because other tests here legitimately assert on comment
    content (the 139,451px measurement, the model's-own-curve copy); the
    distinction is whether the claim is about what the page RENDERS or
    about what the file SAYS, and those want different text.
    """
    src = re.sub(r"/\*.*?\*/", " ", _fn(name), flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


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
    assert "pricedProfileHTML(priced.get(mkt), chips, vsTail, deep, inPage)" in APP
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


# --- the page is deep, a search and a browse draw no card -------------------
def test_the_players_page_draws_its_card_deep_and_as_the_pages_own():
    """Ethan, 2026-11-17: a search lists names, and a name opens the
    player's page. The address is the one place the view draws a card, at
    full depth and as the page's own (no door out to the pick page), by an
    options object: `shown.map(profileHTML)` would pass the INDEX where the
    options go, and the flags would look simply broken."""
    i = APP.index("async function renderPlayers(")
    body = APP[i:APP.index("\n/* The UFC hero", i)]
    assert body.count("profileHTML(") == 2, "a card only for the page's own player"
    assert "host.innerHTML = profileHTML(own, { deep: true, inPage: true });" in body, "priced tonight"
    assert "host.innerHTML = profileHTML(m.player, { deep: true, inPage: true });" in body, "from the league's logs"
    assert "shown.map(profileHTML).join" not in APP


def test_a_search_and_a_browse_list_names_and_no_cards():
    """The measurement this defers to is in the same function: 293
    profiles, 139,451px, on a page nobody had searched. A search and a
    browse are a list of names now, a 64px row each, still capped."""
    i = APP.index("async function renderPlayers(")
    body = APP[i:APP.index("\n/* The UFC hero", i)]
    assert "searchListHTML(shown.map((p) => _profRows.get(p)[0]))" in body, "the board's names"
    assert "${searchListHTML(hits)}" in body, "the league's names"
    assert "139,451px" in body, "the measurement that justifies the cap is gone"


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
    assert '<div class="profile-pick"${door}>' in fn, "the pick block is not a door"
    # THE SITE'S ONE DEFINITION OF AN OPENABLE PROP, not a second copy of
    # the rule — a row with fewer than three logged games opens a page
    # whose centrepiece is missing, and `propAttrs` is what knows that.
    # Off the player's own page only (2026-11-17): there the card opens nothing.
    assert 'const door = inPage ? "" : propAttrs(r);' in fn
    assert '${door ? `<span class="pp-go" aria-hidden="true">→</span>` : ""}' in fn, \
        "the arrow appears on rows with no page"


def test_on_the_players_page_the_card_opens_nothing_and_carries_bet_it_and_ask():
    """Ethan, 2026-11-17, circling the pick page a search card had opened:
    "let's get rid of this page … and replace it with the actual player
    page". The card on the page has no door to it, so the pick page's two
    actions come to the card: the books, and a question with the pick
    attached. A market chip keeps the card the page's own."""
    fn = _fn("pricedProfileHTML")
    assert '${inPage ? profileActsHTML(r) : ""}' in fn
    acts = _fn("profileActsHTML")
    assert 'betItHTML(r, "btn primary")' in acts
    assert 'data-ask-pick="${escapeAttr(propId(r))}"' in acts and "data-ask-label=" in acts
    prof = _fn("profileHTML")
    assert "pricedProfileHTML(priced.get(mkt), chips, vsTail, deep, inPage)" in prof
    i = APP.index('e.target.closest(".prof-tab")')
    chip = APP[i:i + 1600]
    assert 'inPage: !!card.closest(".plr")' in chip, "a chip on the page drew the door back"
    assert ".prof-acts {" in CSS and ".prof-acts .betit-box .betit {" in CSS


def test_clicking_the_player_himself_opens_the_page():
    """Ethan, 2026-09-10, a second time with the same screenshots: "When
    you search up a player, you should be able to click on them, and then
    it will pull up this page showing more information."

    The first answer put the door on the pick block — the row that names
    the bet, which is right, and which sits at the BOTTOM of a card that
    now runs a screen and a half on a phone. "Click on THEM" is the face
    and the name at the top, and that was still inert."""
    fn = _fn("pricedProfileHTML")
    assert "escapeHtml(r.grade)}</span>`, door)}" in fn, "the head is not handed the pick's door"
    head = _fn("_profileHead")
    assert '<div class="profile-head"${door}>' in head


def test_an_unpriced_players_head_is_never_a_door():
    """The same head is drawn for a searched-up player with nothing
    priced tonight. That row has no market, no line and no side, so
    `propId` would build an id out of empty strings and the door would
    open a page that does not exist."""
    assert "propAttrs" not in _code("historyProfileHTML"), \
        "the history card grew a door"
    # PASSED IN, NOT COMPUTED IN THE HEAD — which is what keeps that true
    # without the head having to know which caller it has.
    head = _code("_profileHead")
    assert "propAttrs" not in head and "propId" not in head


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
    assert "cursor: pointer" in _rule(".profile-head[data-prop]")
    assert ".profile-pick .pp-go" in CSS


# --- styles -----------------------------------------------------------------
def test_the_sim_lab_shades_and_counts_the_picks_own_side():
    """An under pick was drawn as an over: the shaded bars were the right
    of the line, the readout counted overs ("the model says 38%" under a
    62% pick) and the note said "A 38% over still loses 6 nights in 10".
    It also called every league's counts "receptions". Now the side the
    pick wins on is the shaded one, counted and said, and the box shows
    the curve faintly before the first run instead of sitting empty."""
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    rows = {"under": {"side": "UNDER", "line": 26.5, "projection": 24.1, "hit_prob": 0.62},
            "over": {"side": "OVER", "line": 26.5, "projection": 28.9, "hit_prob": 0.62}}
    prog = "\n".join([
        "const escapeHtml = (s) => String(s), escapeAttr = escapeHtml, propId = () => 'x';",
        "const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;",
        _fn("invNorm"), _fn("simParams"), _fn("simBins"), _fn("simLabHTML"),
        f"const rows = {json.dumps(rows)};",
        "const out = {};",
        "for (const [k, r] of Object.entries(rows)) {",
        "  const html = simLabHTML(r);",
        "  out[k] = {read: /class=\"sim-read\">([^<]*)</.exec(html)[1],",
        "            note: /class=\"sim-note\">([\\s\\S]*?)<\\/p>/.exec(html)[1].replace(/\\s+/g, ' '),",
        "            ghost: html.includes('sim-bars ghost'),",
        "            bars: [...html.matchAll(/<i class=\"(pk)?\" style=\"transform:scaleY\\(([0-9.]+)\\)\"/g)]",
        "              .map((m) => [m[1] === 'pk', Number(m[2])])};",
        "}",
        "process.stdout.write(JSON.stringify(out));"])
    got = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-800:]
    out = json.loads(got.stdout)
    under, over = out["under"], out["over"]
    assert under["read"] == "The under wins in the shaded part of the curve.", under["read"]
    assert "A 62% under still loses 4 nights in 10." in under["note"], under["note"]
    assert "A 62% over still loses 4 nights in 10." in over["note"], over["note"]
    assert "receptions" not in under["note"], "a football word in every league's note"
    assert under["ghost"] and len(under["bars"]) == 34, "the curve is drawn before the first run"
    shaded = [pk for pk, _h in under["bars"]]
    assert shaded[0] and not shaded[-1] and shaded == sorted(shaded, reverse=True), \
        ("an under's shaded side is the left of the line", shaded)
    shaded = [pk for pk, _h in over["bars"]]
    assert not shaded[0] and shaded[-1] and shaded == sorted(shaded), ("an over's is the right", shaded)
    heights = [h for _pk, h in over["bars"]]
    assert max(heights) > 0.95 and heights[0] < 0.05 and heights[-1] < 0.05, ("a bell, peaked mid-box", heights)
    run = _code("runSim")
    assert "P.under ? x < P.line : x > P.line" in run, "the run counts the pick's side"
    assert "(the model says ${(100 * P.pPick)" in run, "and quotes the pick's chance"
    assert 'bars.classList.remove("ghost")' in run
    assert ".sim-bars.ghost i" in CSS and ".sim-bars i.pk" in CSS


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
