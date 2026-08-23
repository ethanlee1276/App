"""Ethan's edge-panel render, 2026-08-23.

"this section here still looks like the old site, make it look like the
new site and also follow this render too make it look more neat."

It did look like the old site: three paragraphs of grey prose under a
bare table, in a panel that is really THREE separate instruments stacked
— the AUC table, the closing-line check, and the run history. Unbroken
prose made them read as one long caveat.

THE FOUR TILES ARE THE PART WORTH GUARDING. A summary strip is exactly
where a panel starts reassuring people, and this is the panel that exists
to refuse that: it is the one on the site whose job is to say "no
measurable edge" out loud. So every tile is DERIVED — from the verdict,
from the sample, from the timestamp, or from a comparison of two counts
already in the payload. None of them is a sentence somebody typed and
none can say something kinder than the numbers.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth, k = 0, j
    while k < len(APP):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
        k += 1
    raise AssertionError(f"unbalanced braces reading {name}")


FN = _fn("recEdgePanel")


def test_the_verdict_tile_reads_the_verdict():
    """"Trust the model?" must never be able to say Yes while the panel
    above it says no measurable edge."""
    assert "e.verdict" in FN
    for key in ("edge_is_noise", "edge_inverted", "edge_predicts"):
        assert key in FN, key
    i = FN.index("edge_predicts:")
    assert '"Yes"' in FN[i:i + 90], "the only Yes is not on the passing verdict"
    # And no other branch may produce one.
    assert FN.count('"Yes"') == 1


def test_the_sample_tile_is_the_measured_sample():
    assert "e.n == null" in FN and "e.n" in FN


def test_data_quality_compares_two_real_counts():
    """The tile that would be easiest to fake. It reports the rows the
    test could USE against the rows the record counts, so a book with
    picks missing a stored probability says so rather than claiming a
    clean sample it does not have."""
    assert "settled - e.n" in FN
    assert '"Partial"' in FN and '"High"' in FN
    # THE WHOLE TILE CALL, cut at its closing brace rather than at a
    # character count — the branch that names what is missing sits past
    # any round number, and this test failed on its own first run for
    # exactly that reason.
    i = FN.index('statCardHTML("shield"')
    blk = FN[i:FN.index('statCardHTML("chart"', i)]
    assert "missing" in blk, "the tile stopped reading the comparison"
    assert "no stored probability" in blk, \
        "a partial sample no longer says what is missing"


def test_the_timestamp_tile_reads_the_run_not_the_clock():
    """"Last measured" is when the test ran, not when the page loaded."""
    assert "e.ts" in FN
    assert "new Date(e.ts" in FN


def test_no_tile_carries_a_hand_written_claim():
    """Every value in the strip traces to the payload."""
    i = FN.index("const tiles =")
    strip = FN[i:FN.index("return `", i)]
    for derived in ("trust[0]", "trust[1]", "e.n", "stamp"):
        assert derived in strip, derived


# --- the render's shape ---------------------------------------------------

def test_each_instrument_gets_its_own_note():
    """Three instruments, three marks — the panel's paragraphs were one
    grey block before."""
    assert FN.count('class="ev-note"') == 3
    assert ".ev-note" in CSS and ".ev-ico" in CSS


def test_the_run_list_is_coloured_by_the_coin_flip():
    """0.500 is the line the whole panel is about, and a wall of identical
    grey numbers was hiding the one thing the list says."""
    assert 'a >= 0.5 ? "pos" : "neg"' in FN
    assert ".ev-run.pos" in CSS and ".ev-run.neg" in CSS


def test_the_claimed_edge_row_wears_the_accent():
    i = CSS.index(".rec-edge-tbl tr.lead-row td {")
    assert "var(--brand)" in CSS[i:i + 120]


def test_the_corner_mark_is_decoration_and_says_so():
    """Decoration that competes with a confidence interval has to go —
    so it is faint, behind everything, hidden from a screen reader, and
    gone on a phone where the space is the content's."""
    assert 'class="ev-mark" aria-hidden="true"' in FN
    i = CSS.index(".ev-mark {")
    rule = CSS[i:CSS.index("}", i)]
    assert "pointer-events: none" in rule and "opacity" in rule
    assert ".ev-mark { display: none; }" in CSS


def test_the_statistics_table_scrolls_rather_than_pushing_the_page():
    """Four columns of figures have a width below which they stop being
    readable. The box scrolls; the page must not."""
    assert 'class="ev-scroll"' in FN
    i = CSS.index(".ev-scroll {")
    assert "overflow-x: auto" in CSS[i:i + 60]


def test_the_panel_still_refuses_to_flatter():
    """The copy this panel exists for. If these strings ever soften, the
    tiles above them are decorating a lie."""
    i = APP.index("const EDGE_VERDICTS = {")
    block = APP[i:APP.index("\n};", i)]
    assert "No measurable edge" in block
    assert "Edge points backwards" in block
    assert "did not win more often" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
