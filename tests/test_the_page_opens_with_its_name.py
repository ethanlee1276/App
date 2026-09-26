"""v4: a page opens with its name.

Ethan, 2026-09-22: "all the pages are cluttered and confusing and hard
to read all the data." Thirty of the forty views open with a
`.section-title` and its `.sub`, drawn as the same small tracked caps
every section head inside the page uses — so a page opened the way a
paragraph does. The first title in a view is now the page's name in
the display face at the hero's size; the section heads under it keep
the caps, so the two levels read as two. The why? apparatus is
untouched.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _rule(opener):
    assert opener in CSS, opener
    block = CSS[CSS.index(opener):]
    return block[:block.index("}")]


def test_the_first_title_in_a_view_is_the_pages_name():
    rule = _rule(".view > .section-title:first-child, .section-title.page-title {")
    assert "font-family: var(--font-display)" in rule
    assert "font-size: var(--fs-2xl)" in rule, "the hero's size, not a kicker's"
    assert "text-transform: none" in rule and "color: var(--text)" in rule
    assert "letter-spacing: -.01em" in rule


def test_the_section_heads_under_it_keep_the_caps():
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    blocks = re.findall(r"\.section-title\s*\{([^}]*)\}", body)
    assert any("uppercase" in b for b in blocks), "the inner heads lost the caps — two levels became one"
    # and the page title rule is a descendant rule, not a fourth `.section-title {`
    assert body.count(".view > .section-title:first-child, .section-title.page-title {") == 1


def test_the_sub_stays_a_plain_line_and_the_why_still_folds_it():
    sub = _rule(".view > .section-title:first-child .sub, .section-title.page-title .sub {")
    assert "font-size: var(--fs-sm)" in sub and "color: var(--text-mute)" in sub
    assert ".section-title .sub.sub-collapsed { display: none; }" in CSS
    assert ".view > .section-title:first-child .why-toggle, .section-title.page-title .why-toggle { align-self: center; }" in CSS


def test_a_title_inside_a_body_wrapper_is_still_the_pages_name():
    """Live, Picks and the game pages render their title inside a body
    div, where `.view > :first-child` cannot see it. The enhancer marks
    the first real title in every view and un-marks any other."""
    body = APP[APP.index("function markPageTitles("):]
    body = body[:body.index("\n}\n")]
    assert 'view.querySelector(".section-title:not(.minor):not(.subhead)")' in body
    assert 'if (t !== first) t.classList.remove("page-title");' in body, "a page with a redrawn title would carry two names"
    assert 'if (first) first.classList.add("page-title");' in body
    subs = APP[APP.index("function enhanceSectionSubs("):]
    subs = subs[:subs.index("\n}\n")]
    assert "markPageTitles(root);" in subs, "not run on every render"


def test_the_live_panels_trailing_note_is_a_caveat():
    """The note under the Live tab's open bets was a bare styled
    paragraph, so the caveat fold could not see it."""
    assert '<p class="list-note" style="padding:8px 14px 10px;margin:0">${foot}</p>' in APP
    assert 'font-size:var(--fs-xs);color:var(--text-mute)">${foot}</p>' not in APP


def test_most_views_actually_open_this_way():
    h = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
    views = re.findall(r'<section class="view[^"]*" id="view-([a-z]+)"[^>]*>(.*?)(?=<section class="view|</main>)', h, flags=re.S)
    opens = [n for n, body in views if re.match(r'\s*<div class="section-title[^"]*"', body)]
    assert len(views) >= 38 and len(opens) >= 28, (len(views), len(opens))


APP = (ROOT / "web" / "js" / "app.js").read_text()
PHONE = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]


def test_a_four_cell_record_row_has_its_own_columns():
    """The calibration rows have no icon and no book cell; on the
    six-column grid their first cell fell into the 20px icon track and
    the band printed over the words (desktop, 2026-09-22)."""
    # Four since 2026-09-26: the Record page's Most Likely board by tier
    # (recBoardSection) is the same four-cell row.
    assert APP.count('class="rl-row rl-cal ') == 4, "the four calibration templates carry the modifier"
    assert ".rl-row.rl-cal { grid-template-columns: 112px minmax(0, 1fr) 90px 72px; }" in CSS
    # …and the phone restates its five-track area layout at the same
    # specificity, so the desktop rule does not outrank it there. The
    # phone's row rule lives in its own ≤760px block, so the check walks
    # back to that block's media header rather than assuming which one.
    rule = ".rl-row.rl-cal { grid-template-columns: 20px auto minmax(0, 1fr) auto 72px; }"
    assert rule in CSS
    i = CSS.index(rule)
    at = CSS.rindex("@media", 0, i)
    assert "max-width: 760px" in CSS[at:CSS.index("{", at)], "the phone restatement is not in a phone block"
    assert CSS.rindex(".rl-row, .pm-rows .rl-row {", 0, i) > at, "declared after the phone's row rule, in the same block, so it wins on order"


def test_the_fantasy_rooms_sit_two_abreast_on_a_phone():
    assert "  .room-index { grid-template-columns: 1fr 1fr; gap: 6px; }" in PHONE
    base = CSS[CSS.index(".room-index {"):]
    base = base[:base.index("}")]
    assert "repeat(auto-fit, minmax(min(200px, 100%), 1fr))" in base, "the desktop index still flows"
    assert ".rc-what" in CSS, "the description is still drawn — every room named and described"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
