"""Ethan's UFC render, 2026-08-25.

He sent a picture of the page he wants: the card numbers in bordered
boxes with a gold mark on each, a call to action on the hero, the venue
notice as a real callout instead of a grey footnote, and a RECORD
BREAKDOWN panel — a ring with the graded total in the middle and a legend
carrying the counts.

Two decisions inside that are worth pinning, because both could be undone
by someone doing the obvious thing:

  * the boxes are SCOPED to this page. §6.6 of the design doctrine says
    the opposite in as many words — "no card, no background, no border
    box … four equal bordered tiles with a big number in each is item 6
    on the anti-pattern list" — and that rule is about the dashboard,
    where four equal boxes made none of them the answer. Fine here, where
    the five numbers really are peers. Not fine leaking out and flipping
    every other page to the shape the rule was written against.

  * the ring counts PUSHES. A 2-9 record with a push in it is twelve
    graded fights, and a breakdown whose slices do not add up to the
    number in the middle of its own ring is the one thing this panel must
    never be.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


APP = _read("web", "js", "app.js")
VIS = _read("web", "js", "visuals.js")
CSS = _read("web", "css", "styles.css")


def _fn(src, decl):
    """One function's source, cut at the next top-level declaration.

    Never a fixed slice. This suite has gone red four times this week for
    a comment growing above the line a test looks for, and every one of
    those was the test being wrong.
    """
    i = src.index(decl)
    j = len(src)
    for end in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* "):
        k = src.find(end, i + len(decl))
        if k != -1:
            j = min(j, k)
    return src[i:j]


def _every(src, needle):
    """Every index of ``needle`` — because "the first one" is how a test
    ends up asserting against a rule it did not mean."""
    out, i = [], src.find(needle)
    while i != -1:
        out.append(i)
        i = src.find(needle, i + 1)
    return out


# --- the five card numbers ------------------------------------------------

def test_every_stat_card_is_built_by_one_helper():
    """Five hand-written blocks are five chances for one to lose its
    caption, and the caption is the part that carries the meaning."""
    assert APP.count("function statCardHTML(") == 1
    assert APP.count('<div class="stat-card">') == 1


def test_each_number_keeps_the_caption_that_explains_it():
    """"books post MMA lines late" is the whole reason a zero under
    AWAITING PRICES is not alarming."""
    body = _fn(APP, "async function renderUFC(")
    for cap in ("priced &amp; run through the model",
                "books post MMA lines late",
                "every fight that clears the bar",
                "the tightest in the system"):
        assert cap in body, cap
    # Five marks, five numbers.
    for mark in ("calendar", "gem", "clock", "target", "shield"):
        assert f'statCardHTML("{mark}"' in body, mark


def test_the_marks_it_asks_for_actually_exist():
    """`icon()` returns "" for a name it does not know — silent by
    construction, which is exactly the failure nobody notices in review.
    Two of these were added for this render."""
    i = APP.index("ICON_PATHS = {")
    paths = APP[i:APP.index("\n};", i)]
    names = set(re.findall(r"^\s*([a-z_0-9]+):", paths, re.M))
    for mark in ("calendar", "gem", "clock", "target", "shield", "trophy",
                 "chart", "star", "info", "rising"):
        assert mark in names, f"icon('{mark}') would draw nothing"


def test_a_single_bout_is_not_called_one_bouts():
    body = _fn(APP, "async function renderUFC(")
    assert 'bout${(c.fights || 0) === 1 ? "" : "s"}' in body


# --- the record breakdown -------------------------------------------------

def test_the_ring_total_counts_pushes():
    """Slices that do not add up to the number in the middle of their own
    ring is the one thing this panel must never be."""
    body = _fn(APP, "async function renderUFC(")
    assert "const graded = wins + losses + pushes;" in body
    # And all three are in the legend, including the one that is usually 0.
    for k in ('"Wins"', '"Losses"', '"Pushes"'):
        assert k in body, k


def test_a_zero_total_draws_an_empty_ring_rather_than_a_nan_arc():
    """The honest picture on a Tuesday before the first card."""
    ring = _fn(VIS, "function donutRing(")
    # The arcs are built only from segments with a positive value, so the
    # division that would produce NaN never runs on an empty book.
    assert "filter((s) => s && (s.value || 0) > 0)" in ring
    assert 'stroke="var(--border-soft)"' in ring, "no track ring to show"


def test_the_ring_is_drawn_not_charted():
    """A chart library is a network request between the reader and a
    number we already have, and the pages that depend on one go blank
    when the CDN does."""
    ring = _fn(VIS, "function donutRing(")
    assert "<svg" in ring and "circle" in ring
    for lib in ("echarts", "Chart(", "d3."):
        assert lib not in ring, lib


def test_the_percentages_come_off_the_same_total_as_the_ring():
    body = _fn(APP, "async function renderUFC(")
    assert "const pct = (n) => graded ?" in body, \
        "a second denominator is a second answer"


def test_the_disclosure_says_what_it_promises():
    """"Every pick. Every fight. No excuses." has to open onto something
    that is actually about that, or it is decoration."""
    body = _fn(APP, "async function renderUFC(")
    i = body.index("Every pick. Every fight. No excuses.")
    tail = body[i:i + 700]
    assert "Nothing is dropped" in tail
    assert "the ones that went badly included" in tail


# --- the hero's call to action --------------------------------------------

def test_the_cta_is_a_jump_on_this_page_not_a_route_elsewhere():
    """The fights are already here. Sending the reader to another view
    would be a lie about where they are going, and coming back would cost
    them their place."""
    body = _fn(APP, "async function renderUFC(")
    assert 'data-ufc-jump="1"' in body
    assert '<div id="ufc-fights"></div>' in body, \
        "the jump has no target that survives an empty card"
    handler = APP[APP.index('closest("[data-ufc-jump]")'):][:900]
    assert "switchView(" not in handler


def test_the_jump_is_still_a_jump_after_a_refresh():
    """renderUFC replaces its own innerHTML every sixty seconds, so a
    listener bound inside it is unbound a minute later. The nearest
    listener above this handler must be one bound at the DOCUMENT."""
    i = APP.index('closest("[data-ufc-jump]")')
    j = APP.rindex("addEventListener(", 0, i)
    assert APP[j - 9:j] == "document.", \
        "the jump is bound inside a host that gets replaced"


def _code(src):
    """Source with its comment lines removed.

    A test that greps a function for a string finds it in the COMMENT
    explaining why that string is wrong. This one did, on its first run:
    the handler's own note says `behavior: "auto"` is not instant, and
    the test read that as the code using "auto"."""
    out = []
    for line in src.splitlines():
        st = line.strip()
        if st.startswith("//") or st.startswith("*") or st.startswith("/*"):
            continue
        out.append(line)
    return "\n".join(out)


def test_reduced_motion_gets_an_instant_jump_not_an_auto_one():
    """`behavior: "auto"` is not instant — it defers to CSS, and this
    stylesheet sets `scroll-behavior: smooth` on the root."""
    raw = APP[APP.index('closest("[data-ufc-jump]")'):][:900]
    assert "prefers-reduced-motion" in raw
    code = _code(raw)
    assert '"instant"' in code
    assert '"auto"' not in code, "auto defers to the smooth root"


# --- the venue notice -----------------------------------------------------

def test_the_venue_notice_is_a_callout_in_both_directions():
    """It changes how every price on the page should be read, which is
    not a footnote — and the recorded case matters as much as the missing
    one."""
    body = _fn(APP, "async function renderUFC(")
    assert body.count('class="ufc-callout"') == 2
    assert "<strong>Venue not recorded</strong>" in body
    assert "cage size and\n          altitude are applied" in body \
        or "cage size and" in body


# --- the scoping ----------------------------------------------------------

def test_the_render_does_not_flip_every_other_page_into_boxes():
    """§6.6 is about the dashboard and it still stands there. This render
    rides its own classes rather than redefining the shared tile."""
    assert ".stat-card {" in CSS
    # The shared tile is untouched: still borderless, still a rule-divided
    # column rather than a box.
    tile = CSS[CSS.index("\n.tile {"):]
    tile = tile[:tile.index("\n.stats > .tile")]
    assert "border: 0;" in tile
    assert "background: none;" in tile


def test_the_new_blocks_take_their_corners_from_the_token():
    """The token is declared twice — 0 in the base block, 14px in the
    gold pass — so a number written here would produce the identical
    screenshot today and pin this page to the old value the day somebody
    changes it."""
    for cls in (".stat-card {", ".ufc-callout {", ".ufc-rb {"):
        i = CSS.index(cls)
        rule = CSS[i:CSS.index("}", i)]
        assert "border-radius: var(--radius-lg)" in rule, cls


def test_the_phone_gets_two_cards_a_row_rather_than_five_screens():
    """MEASURED AT 390x844: `minmax(190px, 1fr)` puts exactly one card per
    row — 2 x 190 + gap is 392 against a 366px column — so five numbers
    became five full-height blocks with the fights a long way under
    them."""
    # The block that mentions .stat-cards, not the first one at this
    # width — there was briefly a second, and this test found the wrong
    # one, which is the kind of near-miss that makes a suite untrusted.
    blocks = [CSS[m:CSS.index("\n}", m)]
              for m in _every(CSS, "@media (max-width: 520px) {")]
    hit = [b for b in blocks if ".stat-cards" in b]
    assert len(hit) == 1, f"{len(hit)} phone blocks style the cards"
    assert "repeat(2, minmax(0, 1fr))" in hit[0]
    assert ".ufc-hero-cta" in hit[0], "the hero button still floats on art"


def test_the_record_panel_stacks_before_it_squeezes():
    i = CSS.index(".ufc-record {")
    assert "minmax(0, 1.65fr)" in CSS[i:i + 300]
    # Same trap as the phone block: there is more than one 860px media
    # query in this stylesheet, and "the first one" is not this one.
    blocks = [CSS[m:CSS.index("\n}", m)]
              for m in _every(CSS, "@media (max-width: 860px) {")]
    hit = [b for b in blocks if ".ufc-record" in b]
    assert len(hit) == 1 and "grid-template-columns: 1fr" in hit[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
