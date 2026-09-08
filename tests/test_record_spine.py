"""The Record page's receipts room reads in one order, calendar first.

Ethan, 2026-09-08: "re organize all the record pages for every sport as
everything's is just scattered around and unorganized. Maybe we put the
profit calendars at the top of the pages."

The room ran verdict, book sections, the process row with its long
disclosure, two notes, the curve, the calendar, the splits, the settled
rows, the edge panel — and on "All bets" the Most Likely record led and
the pooled book sections trailed after everything, so the two scopes
read in different orders. Every one of those panels earned its place on
some day; nobody ever set them in a row.

THE SPINE, on every scope: the profit calendar; the Most Likely record
on "All bets"; the verdict and its two caveats; records by book; the
running curve; the splits; the settled picks; how this is measured (the
process grade, the era, what counts as a tracked bet); and last the
working, is there an edge at all. Built once in renderRecord; the rooms
add nothing around it.

Run directly: `python3 tests/test_record_spine.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _receipts():
    i = APP.index("const receipts = calendar")
    return APP[i:APP.index("\n  `;", i)]


ORDER = [
    "const receipts = calendar",
    'recLikelySection(d.likely)',
    "+ verdict + unstaked + small",
    "recBookSections(d.book_records, scope)",
    "recAnalytics(src.curve",
    "recSplitsSection(o, !!scoped)",
    "recRecentSection(src.recent || [], o.settled)",
    "How this is measured",
    '<div class="rec-process-row">',
    "recEpochHTML(d, src)",
    'recDisclosure("What counts as a tracked bet"',
    "${edgePanel}",
]


def test_the_room_reads_in_one_order_on_every_scope():
    body = _receipts()
    at = [body.index(m) for m in ORDER]
    assert at == sorted(at), [m for m, a in zip(ORDER, at)]
    assert "const calendar = recCalendarHTML(src.curve);" in APP


def test_the_calendar_is_the_first_thing_in_the_room():
    body = _receipts()
    head = body[:body.index("verdict")]
    assert "calendar" in head and "recLikelySection" in head
    # Nothing draws before the calendar: the string starts with it.
    assert body.startswith("const receipts = calendar\n")


def test_the_rooms_add_nothing_around_the_string():
    """Prefixing the Most Likely record and appending the pooled book
    sections in `_recordRooms` is how the two scopes came to read in two
    orders. One call each, both inside `receipts`."""
    i = APP.index("function _recordRooms(")
    rooms = APP[i:APP.index("\nfunction ", i + 10)]
    assert "     receipts]," in rooms
    assert "recLikelySection(" not in rooms and "recBookSections(" not in rooms
    assert APP.count("recLikelySection(d.likely)") == 1
    assert APP.count("recBookSections(d.book_records, scope)") == 1
    assert "the calendar, the verdict, every settled pick" in rooms


def test_the_notes_qualify_the_verdict_not_the_curve():
    """The unstaked-picks note and the small-sample note are caveats on
    the headline; they sat under the process row, a screen away from the
    number they qualify."""
    body = _receipts()
    assert body.index("+ verdict + unstaked + small") < body.index("recBookSections(")
    assert "${unstaked}" not in body and "${small}" not in body, "a note is drawn twice"


def test_the_measurement_block_has_a_heading_and_sits_before_the_working():
    body = _receipts()
    i = body.index("How this is measured")
    assert 'icon("scale", 15)' in body[i - 120:i]
    assert "what counts as a tracked bet" in body[i:i + 300]
    assert body.index("recRecentSection") < i < body.index('<div class="rec-process-row">') < body.index("${edgePanel}")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
