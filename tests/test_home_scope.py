"""A number on a page has to say what it counts.

Ethan, 2026-08-23, on the phone dashboard: "I thought it meant
performance breakdown for the whole site, but then I realized it was just
for MLB. So we need to be more specific."

He read the heading exactly as written. The card above it already said
"Your MLB performance" when the panel was sport-scoped; this one — the
same numbers drawn as a ring — said "Performance breakdown" and nothing
else, sitting directly above a ring whose total really is the whole book.
Two rings, two totals, 391 above 438, and no way to tell why they
disagree.

The rule this pins is not "label the donut". It is that every panel on
that dashboard states its own scope, in both directions — "All sports" is
written out rather than implied, because an unlabelled number is what
caused this in the first place.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    """One function, brace-matched — never a fixed slice."""
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


def test_the_breakdown_ring_names_its_own_scope():
    body = _fn("renderHomePerf")
    i = body.index("perf-donut-card")
    head = body[i:body.index("</div>", i)]
    assert "scopedToSport" in head, "the ring heading is scope-blind again"
    assert "sportName" in head


def test_the_unscoped_case_says_all_sports_rather_than_nothing():
    """The half that is easy to forget. A heading that names the sport
    when scoped and says nothing when not is still ambiguous exactly
    where it matters — on the page a first-time visitor lands on."""
    body = _fn("renderHomePerf")
    assert "All sports" in body


def test_the_two_rings_cannot_both_be_called_a_breakdown():
    """They sit one above the other with different totals. Whatever they
    are called, they must not be called the same thing."""
    body = _fn("renderHomePerf")
    titles = []
    for mark in ('<span class="rail-title">',):
        start = 0
        while True:
            i = body.find(mark, start)
            if i == -1:
                break
            titles.append(body[i + len(mark):body.index("</span>", i)])
            start = i + 1
    assert len(titles) >= 3, titles
    flat = [" ".join(t.split()) for t in titles]
    assert len(set(flat)) == len(flat), f"two panels share a heading: {flat}"


def test_the_sport_ring_and_the_all_sport_ring_read_different_totals():
    """The bug was not the wording alone — it was two totals with one
    label between them. This pins that they really are different sources,
    so the labels are load-bearing rather than decoration."""
    body = _fn("renderHomePerf")
    # The scoped ring counts `n` (the panel's own settled), the sports
    # ring counts `tot` (summed across every sport).
    assert 'class="donut-n">${n}<' in body
    assert 'class="donut-n">${tot}<' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
