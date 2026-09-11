"""Thirty-two teams of "Active · undisclosed", all on screen at once.

Ethan, 2026-08-25: "we should make each team as a click down menu thing
instead of showing every single player all at once bc it makes a lot of
scrolling for that page."

The scroll was real and mostly noise. ESPN's NFL feed lists RETURNS as
well as injuries, so a typical team block is a dozen-plus rows reading
"Active · undisclosed" wrapped around the two that say something. On a
twelve-team fixture the by-team section measured 16,070px on a phone;
folded it is 3,925px — 76% shorter, and a real thirty-two-team board is
several times that.

FOLDING WITHOUT A SUMMARY WOULD JUST HIDE IT. A shut row saying only
"Carolina Panthers 17" makes you open all thirty-two to find the one
with a player out — the same scrolling with extra taps. So the tier
counts ride on the summary line, and a team with neither says so rather
than leaving the space blank.

AND THE SORT HAD TO FOLLOW. The section is titled "most banged-up first"
and sorted on ROW COUNT, which in a feed made of return filings means
"whoever had the most players practising". Folding made it impossible to
miss: the top row read "Philadelphia Eagles · no designations · 18".
It sorts on the tiers now, so the teams worth opening are at the top.

Run directly: `python3 tests/test_injury_fold.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index(") {", i) + 2
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"unbalanced braces reading {name}")


def test_each_team_is_a_native_disclosure():
    """Native <details>, so keyboard and screen-reader behaviour come for
    free and the page still works with JS broken."""
    fn = _fn("injTeamBlock")
    assert '<details class="inj-team">' in fn, "the team block no longer folds"
    assert "<summary" in fn, "a details with no summary cannot be opened"


def test_the_shut_row_says_whether_anything_is_wrong():
    """The whole reason folding is not just hiding."""
    fn = _fn("injTeamBlock")
    assert "it-tier bad" in fn and "it-tier warn" in fn, \
        "the summary stopped carrying the tier counts"
    assert "out</span>" in fn and "questionable</span>" in fn
    assert "no designations" in fn, \
        "a team with nothing wrong leaves the space blank again"


def test_the_teams_are_sorted_by_what_is_wrong_not_by_row_count():
    body = _fn("renderInjuries")
    i = body.index("const teams = Object.keys(byTeam)")
    seg = body[i:i + 400]
    assert "severity[b].out - severity[a].out" in seg, \
        'the section still sorts "most banged-up first" by row count'
    assert seg.index("severity[b].out") < seg.index("byTeam[b].length"), \
        "row count is still the first sort key"


def test_the_tier_counts_are_computed_once_and_handed_down():
    """The summary and the sort must agree, and a second count is a
    second chance to disagree."""
    body = _fn("renderInjuries")
    assert "const severity = {}" in body
    assert "injTeamBlock(t, byTeam[t], severity[t])" in body, \
        "the block recomputes the tiers the sort already counted"
    fn = _fn("injTeamBlock")
    assert "const { out, maybe } = sev" in fn, \
        "injTeamBlock is counting for itself again"


def test_nothing_is_open_by_default():
    """"Who just went down" is answered above by Fresh this week, which
    stays open. A reference section that auto-expands its biggest entries
    is the scroll all over again."""
    fn = _fn("injTeamBlock")
    assert not re.search(r"<details class=\"inj-team\"[^>]*\bopen\b", fn), \
        "a team block opens itself by default"


def test_the_marker_is_the_sites_own_not_the_browsers():
    """The UA triangle does not inherit colour and sits black on black in
    the dark theme, so this section draws its own."""
    assert ".inj-team > summary { cursor: pointer; list-style: none; }" in CSS
    i = CSS.index(".inj-team > summary::after")
    seg = CSS[i:i + 260]
    assert 'content: "+"' in seg
    assert '.inj-team[open] > summary::after' in CSS
    assert "-webkit-details-marker { display: none; }" in \
        CSS[CSS.index(".inj-team >"):CSS.index(".inj-team >") + 400]


def test_the_summary_is_reachable_by_keyboard():
    i = CSS.index(".inj-team > summary:focus-visible")
    assert "outline" in CSS[i:i + 160], \
        "the fold has no visible focus ring"


def test_the_tier_tags_are_styled_in_the_status_colours():
    for sel, tok in ((".it-tier.bad", "var(--bad)"),
                     (".it-tier.warn", "var(--warn)"),
                     (".it-tier.quiet", "var(--text-mute)")):
        i = CSS.index(sel)
        assert tok in CSS[i:i + 120], f"{sel} is not using {tok}"


def test_the_rows_inside_are_the_same_rows_as_before():
    """Folding changed where the list lives, not what a row looks like."""
    fn = _fn("injTeamBlock")
    assert 'class="card inj-list"' in fn, \
        "the by-team list stopped sharing the one row layout"
    assert "injRow(r, false)" in fn, \
        "the team block builds its own row markup now"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
