"""The type and layout rules that a phone finds first.

Written after checking the new typography on a 320-414px screen with a
real browser. Everything asserted here is a defect that measurement found
and reading did not — including two I introduced myself in the same pass,
which is the argument for the file existing.

None of this replaces the Playwright audits; it catches the same faults at
source level, where they are cheap, so a stylesheet edit cannot quietly
reintroduce one between browser runs.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


CSS = _read("web", "css", "styles.css")
JS = _read("web", "js", "app.js")


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)


# --- the font files themselves ----------------------------------------------
def test_every_font_the_css_asks_for_is_actually_in_the_repo():
    """A missing woff2 is invisible on a laptop that has a similar system
    face and obvious on a phone that does not. It also breaks the promise
    the file opens with: that this renders with the network unplugged."""
    refs = set(re.findall(r'url\("\.\./fonts/([^"]+)"', CSS))
    assert refs, "no self-hosted fonts referenced at all"
    for name in refs:
        path = os.path.join(ROOT, "web", "fonts", name)
        assert os.path.exists(path), f"{name} is referenced but not shipped"
        assert os.path.getsize(path) > 4000, f"{name} looks truncated"


def test_no_font_file_ships_that_nothing_can_match():
    """The italic serif sat here declared and unreachable: no element on
    any page was ever Instrument Serif AND italic, so the face never
    downloaded and the file was pure repo weight. Shipping a font is a
    claim that something uses it."""
    refs = set(re.findall(r'url\("\.\./fonts/([^"]+)"', CSS))
    on_disk = {f for f in os.listdir(os.path.join(ROOT, "web", "fonts"))
               if f.endswith(".woff2")}
    assert on_disk == refs, f"unreferenced font files: {on_disk - refs}"


def test_the_header_comment_still_describes_what_ships():
    n = len(set(re.findall(r'url\("\.\./fonts/([^"]+)"', CSS)))
    words = {2: "Two", 3: "Three", 4: "Four"}[n]
    assert f"{words} files" in CSS, \
        f"{n} font files ship but the note at the top says otherwise"


# --- the comment that ate a rule --------------------------------------------
def test_comments_are_balanced():
    """Twice in one sitting I appended a paragraph to an existing comment
    and left the original `*/` in the middle of it. The tail then parses as
    a SELECTOR, swallowing the rule underneath — and the page still looked
    right on a phone, because the fallback happened to be one column. A
    stylesheet cannot tell you it lost a rule, so count the delimiters."""
    depth = i = 0
    line = 1
    stray = []
    while i < len(CSS):
        if CSS.startswith("/*", i) and not depth:
            depth, i = 1, i + 2
            continue
        if CSS.startswith("*/", i):
            if not depth:
                stray.append(line)
            depth, i = 0, i + 2
            continue
        if CSS[i] == "\n":
            line += 1
        i += 1
    assert not stray, f"stray '*/' (comment reopened?) at lines {stray}"
    assert not depth, "a comment is never closed; everything after it is dead"


# --- grid blowout -----------------------------------------------------------
PHONE_PX = 320


def test_no_grid_track_has_a_floor_wider_than_a_small_phone():
    """minmax(340px, 1fr) is a FLOOR, not a preference: in a 296px column
    the track stays 340px and overflows, and .card's overflow:hidden then
    cuts the text off rather than letting it scroll. Measured at 320px it
    chopped 44px off every Polymarket and Fantasy card. min(Npx, 100%)
    lets the floor collapse to the container, which costs nothing at any
    width where the floor already fit."""
    bad = []
    for m in re.finditer(r"minmax\(\s*(min\(\s*)?(\d+)px", _strip_comments(CSS)):
        guarded, px = m.group(1), int(m.group(2))
        if px > PHONE_PX and not guarded:
            ln = _strip_comments(CSS)[:m.start()].count("\n") + 1
            bad.append((ln, px))
    assert not bad, f"unguarded grid floors wider than a phone: {bad}"


def test_the_five_up_form_tiles_share_the_row_instead_of_fighting_for_it():
    """A bare 1fr is minmax(AUTO, 1fr), so the track with the longest label
    grows and the last tile leaves the card."""
    assert "repeat(5, minmax(0, 1fr))" in CSS


def test_the_metric_rows_drop_to_two_up_on_a_small_phone():
    """Four columns inside a 320px card leave 33px of usable label width.
    "chances" is one unbreakable word about 45px wide, so it ran straight
    out of the card."""
    block = CSS[CSS.index("@media (max-width: 420px)"):]
    block = block[:block.index("\n}\n")]
    assert ".card.longshot .metrics" in block and "repeat(2, 1fr)" in block


# --- flex blowout, and the fix that was worse than the bug ------------------
def test_a_card_head_with_only_a_title_can_still_shrink():
    """My first pass pinned `.card-head > :last-child` to flex:0 0 auto to
    stop a status chip being clipped. Most card heads hold ONE child, which
    is both first and last — so that child stopped shrinking entirely and
    went 830px wide inside a 258px head. The guard has to name a trailing
    SIBLING, not a last child."""
    assert ".card-head > :last-child:not(:first-child) { flex: 0 0 auto; }" in CSS
    assert ".card-head > * { min-width: 0; }" in CSS


def test_a_card_head_wraps_rather_than_pushing_the_chip_off():
    head = re.search(r"\.card-head \{[^}]*\}", CSS).group(0)
    assert "flex-wrap: wrap" in head


# --- the display face has a floor, and it is kept ---------------------------
def test_the_serif_is_not_used_below_its_stated_floor():
    """The file states the rule — never below ~17px — and then one column
    heading used it at 14px. A browser sweep found it; this keeps the rule
    and the stylesheet from disagreeing again."""
    assert "never used below ~17px" in CSS
    trend = re.search(r"\.trend-col h3 \{[^}]*\}", CSS).group(0)
    # The size is asserted through the ramp, not as a literal. This pinned
    # "font-size: 14px" and failed the moment that declaration became
    # var(--fs-lg) — while the rule it exists to protect (a heading under
    # the serif's floor must be on the sans) was never in danger.
    step = re.search(r"font-size: var\(--fs-([0-9a-z]+)\)", trend).group(1)
    size = float(re.search(rf"--fs-{step}: *([0-9.]+)px", CSS).group(1))
    assert size < 17, f"{size}px is at or above the serif's stated floor"
    assert "font-family: var(--font-sans)" in trend, \
        "a sub-17px heading is back on the display face"


def test_no_rule_asks_the_serif_for_a_weight_it_does_not_have():
    """Instrument Serif ships 400 only. A heavier request is synthesised —
    a smeared outline, worst at masthead size on a phone."""
    for m in re.finditer(r"\.brand h1 \{[^}]*\}", CSS):
        assert "font-weight: 400" in m.group(0), \
            "the masthead is asking for fake bold again"


# --- where the URL and the page can disagree --------------------------------
def test_the_header_label_is_refreshed_wherever_the_view_changes():
    """syncMenuLabel was wired to the tap handlers only, so the phone's
    back-swipe re-rendered the page and left the header naming the tab you
    had just left — the one line whose whole job is saying where you are.
    switchView is the single place the highlight moves, so it belongs
    there."""
    fn = JS[JS.index("function switchView("):JS.index("function initialView(")]
    assert "syncMenuLabel();" in fn


def test_an_empty_hash_is_a_destination_and_not_a_no_op():
    """The first tab tap pushes on top of the bare URL, so backing all the
    way out lands on "/" — where the handler returned early and left the
    last tab on screen with the address bar claiming the board."""
    fn = JS[JS.index('window.addEventListener("hashchange"'):]
    fn = fn[:fn.index("\n  });")]
    assert 'switchView("recommended")' in fn
    assert "exitStandaloneMode();" in fn, \
        "backing out of Polymarket would leave standalone chrome behind"
    assert "if (!h || h === state.view) return;" not in fn, \
        "the empty hash is being swallowed again"




# --- the theme toggle sat on top of the menu bar ----------------------------
def test_the_theme_toggle_is_not_positioned_over_the_menu_bar():
    """Reported from the phone: the moon button "sitting like bugged in with
    the recommended bar". It was `position: absolute; top: 8px; right: 14px`
    — and the menu pill is a bordered box ~40px tall starting at the same y,
    so the toggle's circle sat ON its right edge with its own right side
    clipped by the screen. Two overlapping bordered boxes.

    The fix is not a nudge. It belongs in the status row, which is a GRID —
    the reason `order` and `margin-left: auto` both did nothing when tried
    against `.menu-toggle`: they are not flex siblings of anything here."""
    # Not "the first max-width:760 block" — there are several, and this rule
    # lives in a later one. The same assumption broke test_about_page.py
    # once already.
    assert "#theme-toggle { position: static; }" in CSS
    assert "top: 8px; right: 14px" not in CSS
    assert "top: 10px; right: 16px" not in _strip_comments(CSS), \
        "the tablet breakpoint still floats it over the bar"


def test_the_status_row_has_a_column_for_it():
    """Three columns and four children put the toggle on its own row. The
    fourth column was removed when it was lifted onto the menu bar."""
    i = CSS.index(".slate-meta { flex: 1 1 100%; order: 5; display: grid;")
    block = CSS[i:CSS.index("}", i)]
    assert "grid-template-columns: auto auto minmax(0, 1fr) auto;" in block


def test_the_shrunk_toggle_keeps_a_44px_reach():
    """36px is under Apple's minimum, and a control you have to aim at is a
    control you stop using. Tap-tested: hits out to 25px above centre."""
    i = CSS.index(".slate-meta .theme-toggle::after")
    block = CSS[i:CSS.index("}", i)]
    assert "width: 44px; height: 44px;" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
