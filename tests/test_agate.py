"""Six tables wore a class that did not exist.

Ethan, 2026-08-23, circling the By-book row on My Bets: "just that whole
line just looks very cluttered and not good, and we should make it look
better."

IT WAS NOT A STYLING CHOICE THAT HAD GONE STALE. There was no `.agate`
selector anywhere in the stylesheet. Three comments in that sheet name
`.agate` as part of the shared kit — "reuses .stats/.agate/.card/.btn" —
and the class sits on six tables, so it read as covered in every review
anybody ever gave it. Measured in the browser, those tables were
rendering at the browser's own defaults: `border-collapse: separate`,
`padding: 1px`, centred headings, no rules, `width: auto`. That is the
whole of "cluttered" — a 1990s table squeezed into a 390px phone,
overflowing far enough that the ROI heading was cut down to "RO".

THE LESSON WORTH KEEPING is not "write the rule". It is that a class name
in a template and a class name in a comment both look like evidence and
neither is. So the first test below walks every class the JS puts on a
`<table>` and demands the sheet actually style it — which is a check no
amount of reading the markup could have replaced.

The second half of the fault was arithmetic, not CSS: the `Bets` column
counted every bet at a book INCLUDING pending ones, while Staked, Profit
and ROI are realized figures that skip them. One open $25 bet rendered as
"1 · $0.00 · $0.00 · —", a row that looks broken because it is quietly
describing two different populations at once.

Run directly: `python3 tests/test_agate.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(src, name):
    """A function body by brace matching, past its parameter list."""
    i = src.index("function " + name + "(")
    j, depth = src.index("(", i), 0
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = src.index("{", j), 0
    for k in range(start, len(src)):
        if src[k] == "{":
            d += 1
        elif src[k] == "}":
            d -= 1
            if not d:
                return src[i:k + 1]
    raise AssertionError(name + " never closes")


# --- the fault that hid in plain sight ----------------------------------------
def test_every_table_class_is_actually_styled():
    """The one check that would have caught this. `.agate` was named in
    six templates and three comments and defined nowhere, and reading
    either the markup or the comments told you it was fine."""
    classes = set(re.findall(r'<table class="([a-z0-9 _-]+)"', APP))
    assert classes, "the sweep found no tables at all — the regex broke"
    for group in classes:
        for cls in group.split():
            assert re.search(rf"^\.{re.escape(cls)}\b", CSS, re.M), (
                f'<table class="{cls}"> is styled nowhere in the sheet, so '
                "it renders at the browser's defaults")


def test_the_rule_sets_the_things_a_bare_table_gets_wrong():
    """Each of these was measured on the unstyled table and each is a
    visible part of the mess: separate borders, 1px padding, centred
    headings, and a width that ignores its container."""
    i = CSS.index(".agate {")
    block = CSS[i:CSS.index("\n.rank-scroll", i)]
    for prop in ("width: 100%", "border-collapse: collapse",
                 "font-variant-numeric: tabular-nums", "padding:",
                 "text-align: left", "border-bottom:"):
        assert prop in block, f"the rule never sets {prop}"


def test_numbers_align_on_a_class_and_not_on_a_column_index():
    """`td:not(:first-child)` was the tempting shortcut and it is wrong
    here: the CSV import preview's second and third columns are Book and
    Bet, both prose, and right-aligning them trades one mess for
    another."""
    i = CSS.index(".agate {")
    block = CSS[i:CSS.index("\n.rank-scroll", i)]
    assert ".agate th.num, .agate td.num { text-align: right; }" in block
    assert ":not(:first-child)" not in block


def test_a_numeric_column_carries_the_class_on_its_heading_too():
    """A right-aligned column under a left-aligned heading is the same
    ragged look the rule was written to fix."""
    for table in re.findall(r'<table class="agate">(.*?)</table>', APP, re.S):
        head = table[:table.index("</thead>")] if "</thead>" in table else ""
        body = table[table.index("</thead>"):] if "</thead>" in table else table
        # `<th(?![a-z])` — without the guard this matches `<thead>` as a
        # <th> whose attributes are "ead", which shifts every column by
        # one and convicts an innocent heading.
        heads = re.findall(r"<th(?![a-z])([^>]*)>", head)
        # Column i of the first body row decides column i of the heading.
        row = re.search(r"<tr>(.*?)</tr>", body, re.S)
        if not row or not heads:
            continue
        cells = re.findall(r"<td([^>]*)>", row.group(1))
        for i, cell in enumerate(cells[:len(heads)]):
            if 'class="num"' in cell:
                assert 'class="num"' in heads[i], (
                    f"column {i + 1} is right-aligned and its heading is "
                    f"not: {heads[i]!r}")


def test_the_grouped_tables_name_what_they_group_by():
    """Both grouped tables on My Bets had an empty first <th>, so the
    column naming what is being grouped — a sport, or a price band — was
    the one with no label. Two identical-looking tables stacked with
    nothing naming either is most of why the page read as unfinished.

    NOT WRITTEN AS "no empty <th> anywhere", which was the first cut and
    is a rule four legitimate columns break: a heading over an × button
    or a sparkline is correctly blank, and "Actions" above a delete
    control is noise, not information. The fault was a MISSING NAME on a
    naming column, so that is what this checks."""
    fn = _fn(APP, "renderMyBets")
    assert "const groupTable = (g, label, order)" in fn, (
        "the grouped tables cannot be labelled")
    assert "<th>${escapeHtml(label)}</th>" in fn, "the label is never printed"
    assert 'mbGroup(bets, (b) => b.sport || null), "Sport"' in fn
    assert 'mbBand(b.odds)), "Price"' in fn


# --- the row that disagreed with itself ---------------------------------------
def test_the_bets_column_counts_what_the_money_columns_count():
    """One open $25 bet at Caesars rendered as "1 · $0.00 · $0.00 · —":
    `Bets` counted it, the realized columns did not. A row describing two
    populations at once looks broken, and it was."""
    fn = _fn(APP, "renderMyBets")
    i = fn.index("const bookRows")
    block = fn[i:fn.index("}).join(\"\");", i)]
    assert "const settled = s.n - s.pending;" in block, (
        "the Bets column is counting pending bets the money columns skip")
    assert "${settled || " in block, "the count is still s.n"


def test_a_book_with_nothing_settled_shows_dashes_not_zero():
    """$0.00 staked reads as "bet nothing there". The truth is "nothing
    has finished", and those are different sentences."""
    fn = _fn(APP, "renderMyBets")
    i = fn.index("const bookRows")
    block = fn[i:fn.index("}).join(\"\");", i)]
    assert 'settled ? mbMoney(s.staked) : "—"' in block
    assert "settled\n        ? mbMoney(s.profit, true)" in block \
        or 'settled ? mbMoney(s.profit, true) : "—"' in block


def test_the_open_bets_are_still_named_somewhere():
    """Dropping them from the count must not drop them from the page —
    that would be a tracker quietly forgetting money that is at risk."""
    fn = _fn(APP, "renderMyBets")
    assert "agate-sub" in fn and "open</span>" in fn
    assert ".agate-sub" in CSS, "the note is unstyled"
    # …and the heading says what the column counts.
    assert "Counts settled bets only" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
