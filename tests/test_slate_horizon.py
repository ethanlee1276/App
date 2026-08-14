"""When the board is not tonight, the page says so.

Ethan, 2026-08-14: "there is games tonight yet they are not showing on
the website and there is no reccomended props or anything. its displaying
the first week of the regular season."

THE BOARD WAS NEVER WRONG ABOUT WHAT IT WAS SHOWING. `_current_nfl_week`
reads nflverse's schedule; nflverse carries no preseason at all
(`season_type in ("REG", "")`, nflverse.py:255), so the nearest fixture it
can see in mid-August is Week 1 — three weeks out and comfortably inside
the 45-day run-up window. It builds that week, and it is right to: Week 1
prep is what August is for.

The lie was the TITLE. "This week's stadiums" over fixtures from
September, while the football actually being played sat several screens
below under a heading nobody had reason to scroll to. A static per-sport
string cannot say when, so a note says it instead.

TWO THINGS THIS DELIBERATELY DOES NOT DO.

It does not price the preseason. Ethan, asked directly: "keep it schedule
only". A projection is volume times efficiency over prior games, and in
August a starter plays a series and a half behind a line that will not
start together again.

And it does not MOVE the preseason block above the strip, which was the
obvious fix and does not survive contact: `groupRecommended` re-parents
this whole view into subgroups after every renderer has run, so a DOM
move made in `renderPreseason` is undone moments later. That was measured
— the two elements came back in different subgroups — not guessed. The
note links instead.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def _fn():
    i = APP.index("function renderSlateHorizon()")
    return APP[i:APP.index("\nfunction ", i + 1)]


def test_the_note_has_a_home_in_the_markup():
    assert 'id="slate-horizon"' in HTML


def test_it_sits_with_the_strip_it_is_about():
    """A note about the board that renders somewhere else is a note about
    nothing. It goes between the strip's heading and the games."""
    i = HTML.index('id="slate-horizon"')
    assert HTML.index('id="games-outer"') > i > HTML.index('id="games-head"')


def test_it_runs_in_the_render_pass():
    i = APP.index("  renderGames();")
    assert "renderSlateHorizon();" in APP[i:i + 120]


def test_it_says_nothing_when_the_slate_is_now():
    """Every day of a real season lands here. A note that appears
    constantly stops being read, and this one has to still work in
    January."""
    assert "if (days <= 1) return;" in _fn()


def test_it_names_the_actual_date_and_the_distance():
    """"Not tonight" is half an answer. Which night it IS decides whether
    to come back tomorrow or in three weeks."""
    b = _fn()
    assert "formatGameDate(first)" in b
    assert "days" in b and "out" in b


def test_the_distance_is_measured_at_midday():
    """A date-only difference across a daylight-saving boundary lands on
    0.96 of a day and floors to the wrong number."""
    assert 'T12:00:00' in _fn()


def test_it_points_at_the_preseason_only_for_football():
    """The other four sports have no preseason block to point at."""
    assert 'state.sport === "nfl" ? state.preseason : null' in _fn()


def test_it_points_only_while_there_are_games_left_to_play():
    """A finished preseason is not what is being played now."""
    b = _fn()
    assert re.search(r'\(g\.date \|\| ""\) >= today', b)


def test_it_links_rather_than_reordering_the_page():
    """THE ONE THAT COST A REWRITE. Moving `#preseason-board` above the
    strip is the obvious fix and it does not survive `groupRecommended`,
    which re-parents the view into subgroups after every renderer has run
    — the two elements came back in different subgroups. The note links
    instead, and the comment in the code records why so the hoist is not
    re-attempted."""
    assert 'href="#preseason-board"' in _fn()
    pre = APP[APP.index("async function renderPreseason()"):]
    pre = pre[:pre.index("\nfunction ")]
    assert "dataset.homeIndex" not in pre, "the preseason hoist is back"
    assert "groupRecommended" in _fn(), "nothing records why it is a link"


def test_the_preseason_fetch_re_runs_the_note():
    """`state.preseason` is filled by an async fetch that lands after the
    note has already drawn once. Without the re-run the pointer is
    missing on the pass that matters — the first one."""
    pre = APP[APP.index("async function renderPreseason()"):]
    pre = pre[:pre.index("\nfunction ")]
    assert "renderSlateHorizon" in pre


def test_a_board_with_no_dates_says_nothing_rather_than_guessing():
    b = _fn()
    assert "if (!dates.length) return;" in b
    assert "if (!games.length) return;" in b


def test_the_empty_note_costs_no_fold():
    """`test_board_order` guards a phone fold budget the picks already sit
    at the edge of — 848px against an 844px fold. This block is allowed
    above the picks only because it is EMPTY in the state that measures:
    it returns before writing when the slate is today or tomorrow, and the
    host div has no styling of its own to give an empty element height.

    If either of those stops being true the exemption is void."""
    assert "if (days <= 1) return;" in _fn()
    # No rule may give the HOST height; `.slate-horizon` styles the <p>
    # that only exists when there is something to say.
    assert "#slate-horizon" not in CSS


def test_the_note_is_styled_in_both_pieces():
    for sel in (".slate-horizon", ".slate-jump"):
        assert sel in CSS, sel


def test_nothing_here_prices_the_preseason():
    """Ethan, asked directly: "keep it schedule only". The note is a
    pointer to a schedule and must not grow into a board.

    Checked against the EMITTED template rather than the whole function —
    the first version read the comments too and tripped on the word
    `groupRecommended`, which is an explanation, not output."""
    b = _fn()
    i = b.index("host.innerHTML = `")
    emitted = b[i:b.index("`;", i)].lower()
    for word in ("edge", "odds", "stake", "units", "recommend"):
        assert word not in emitted, f"the horizon note emits {word!r}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
