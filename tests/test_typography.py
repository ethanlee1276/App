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


def _font_refs_everywhere():
    """Every file that can name a font file, not just the stylesheet.

    This used to read styles.css alone, which was true right up until the
    Night Form prototype landed with its own @font-face block and five new
    faces. The rule it enforces — shipping a font is a claim that something
    uses it — is unchanged; the search just has to cover everywhere a claim
    can be made, or it starts reporting live fonts as dead weight."""
    refs = set()
    for base, _dirs, files in os.walk(os.path.join(ROOT, "web")):
        for name in files:
            if not name.endswith((".css", ".html", ".js")):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                refs |= set(re.findall(r'url\("(?:\.\./)?fonts/([^"]+)"', fh.read()))
    return refs


def test_no_font_file_ships_that_nothing_can_match():
    """The italic serif sat here declared and unreachable: no element on
    any page was ever Instrument Serif AND italic, so the face never
    downloaded and the file was pure repo weight. Shipping a font is a
    claim that something uses it."""
    refs = _font_refs_everywhere()
    on_disk = {f for f in os.listdir(os.path.join(ROOT, "web", "fonts"))
               if f.endswith(".woff2")}
    assert on_disk == refs, (
        f"unreferenced font files: {sorted(on_disk - refs)}; "
        f"referenced but missing: {sorted(refs - on_disk)}")


def test_the_prototype_self_hosts_its_faces_like_the_rest_of_the_site():
    """The redesign brings three new families. Loading them from a CDN
    would break the promise the stylesheet opens with — that this renders
    with the network unplugged — and would be invisible on a laptop that
    has already cached them."""
    page = _read("web", "preview-nightform.html")
    assert "fonts.googleapis" not in page and "fonts.gstatic" not in page, \
        "the prototype is fetching fonts from a CDN"
    for family in ("Bodoni Moda", "Archivo Narrow", "IBM Plex Mono"):
        assert f'font-family:"{family}"' in page, f"{family} is not declared"


def test_the_header_comment_still_describes_what_ships():
    n = len(set(re.findall(r'url\("\.\./fonts/([^"]+)"', CSS)))
    words = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
             7: "Seven", 8: "Eight"}[n]
    assert f"{words} files" in CSS, \
        f"{n} font files ship but the note at the top says otherwise"


# --- the comment that ate a rule --------------------------------------------
def _delimiter_faults(css):
    """Walk one block of CSS and report where its comments stop matching.

    Returns (stray '*/' line numbers, is-a-comment-left-open), both counted
    from the first line of the block."""
    depth = i = 0
    line = 1
    stray = []
    while i < len(css):
        if css.startswith("/*", i) and not depth:
            depth, i = 1, i + 2
            continue
        if css.startswith("*/", i):
            if not depth:
                stray.append(line)
            depth, i = 0, i + 2
            continue
        if css[i] == "\n":
            line += 1
        i += 1
    return stray, bool(depth)


def _css_everywhere():
    """Every block a CSS comment can be opened in, not just the stylesheet.

    This is the same widening `_font_refs_everywhere` needed, for the same
    reason and against the same page: the balance check below read
    styles.css alone, which was true until pages started carrying their own
    <style> blocks. preview-nightform.html now holds twenty comments in
    nineteen kilobytes of CSS that nothing was counting. A comment that
    reopens there eats the rule under it exactly as it would in the
    stylesheet, and an inline block gets less proofreading, not more.

    Line numbers are offset back to the containing file so a failure names
    a line you can actually open."""
    blocks = [("web/css/styles.css", CSS, 0)]
    for base, _dirs, files in os.walk(os.path.join(ROOT, "web")):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as fh:
                txt = fh.read()
            rel = os.path.relpath(path, ROOT)
            for m in re.finditer(r"<style[^>]*>(.*?)</style>", txt, re.S):
                blocks.append((rel, m.group(1), txt[:m.start(1)].count("\n")))
    return blocks


def test_comments_are_balanced():
    """Twice in one sitting I appended a paragraph to an existing comment
    and left the original `*/` in the middle of it. The tail then parses as
    a SELECTOR, swallowing the rule underneath — and the page still looked
    right on a phone, because the fallback happened to be one column. A
    stylesheet cannot tell you it lost a rule, so count the delimiters."""
    for label, css, line0 in _css_everywhere():
        stray, unclosed = _delimiter_faults(css)
        assert not stray, (
            f"{label}: stray '*/' (comment reopened?) at lines "
            f"{[n + line0 for n in stray]}")
        assert not unclosed, \
            f"{label}: a comment is never closed; everything after it is dead"


def test_the_balance_check_reads_the_inline_style_blocks_too():
    """The check above is only as good as the list of places it looks, and
    that list is a walk that silently returns whatever it finds. If a page
    stops matching the <style> pattern — or the walk quietly returns just
    the stylesheet again — the balance test still passes, green and blind.
    Pin the pages that carry their own CSS."""
    found = {label for label, _css, _line0 in _css_everywhere()}
    for page in ("web/og-card.html", "web/preview-nightform.html"):
        assert page in found, f"{page} carries a <style> block nothing checks"


def test_a_reopened_comment_is_actually_caught():
    """The scanner is the thing being trusted, so make it fail on demand —
    otherwise a refactor that quietly stops counting reads as all-clear."""
    stray, unclosed = _delimiter_faults("a{color:red}\n/* note */ and more */\n")
    assert stray == [2] and not unclosed
    assert _delimiter_faults("/* never closed\n.rule{x:y}\n")[1]
    assert _delimiter_faults("/* fine */\n.rule{x:y}\n") == ([], False)


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


def test_no_rule_asks_the_display_face_for_a_weight_it_does_not_have():
    """A weight the face does not ship is SYNTHESISED — the browser smears
    the outline — and it is worst at masthead size on a phone.

    This used to hardcode 400, because Instrument Serif shipped 400 only.
    Bodoni Moda ships 700 and 900 here, so the constant was wrong the
    moment the face changed while the RULE stayed exactly right. Derive the
    allowed set from the @font-face declarations instead: then adding a
    weight to the masthead without shipping the file fails, and swapping
    the family again does not need this test edited."""
    fam = re.search(r'--font-display:\s*"([^"]+)"', CSS).group(1)
    have = {int(w) for w in re.findall(
        rf'font-family:\s*"{re.escape(fam)}";[^}}]*?font-weight:\s*(\d+)', CSS, re.S)}
    assert have, f"{fam} is the display face but ships no @font-face"
    for m in re.finditer(r"\.brand h1 \{[^}]*\}", CSS):
        want = re.search(r"font-weight:\s*(\d+)", m.group(0))
        assert want, "the masthead sets no weight, so it inherits one"
        assert int(want.group(1)) in have, (
            f"the masthead asks {fam} for {want.group(1)}; "
            f"only {sorted(have)} ship — the rest are synthesised")


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
    #
    # What matters is that the toggle stays IN FLOW, not that it says one
    # exact word. This used to assert the literal `position: static`, which
    # then had to become `relative` — the toggle's 44px reach pseudo-element
    # is absolutely positioned, so an unpositioned toggle sends it to the
    # nearest positioned ancestor (the sticky .topbar) and parks an invisible
    # 44x44 tap-blocker in the centre of the header. `static` and `relative`
    # lay out identically here; `absolute` and `fixed` are the bug. Assert
    # that, so the fix for one defect cannot read as a regression of another.
    # test_masthead_brief.py owns the containing-block half of this.
    css = _strip_comments(CSS)
    for body in re.findall(r"#theme-toggle\s*\{([^}]*)\}", css):
        pos = re.search(r"position\s*:\s*([a-z-]+)", body)
        if pos:
            assert pos.group(1) in ("static", "relative"), \
                f"the toggle is `position: {pos.group(1)}` again — it floats " \
                "over the menu bar's bordered pill instead of sharing the row"
    assert re.search(r"#theme-toggle\s*\{[^}]*position\s*:", css), \
        "nothing pins the toggle's position any more; it will inherit " \
        "whatever the desktop rule says at phone widths"
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
