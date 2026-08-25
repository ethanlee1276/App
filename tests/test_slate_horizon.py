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

THE PRESEASON POINTER IS GONE, 2026-08-25. The note used to end with
"Preseason is what is being played now →" while the preseason block was
on the page; the block retired at Ethan's request ("get rid of the pre
season section for nfl") and the pointer went with it. The note's own
job — say WHEN the board is, when that is not now — is unchanged and is
what this file pins.
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


def test_the_preseason_pointer_stayed_retired():
    """The strip used to point at the preseason block ("Preseason is what
    is being played now →"). Both retired 2026-08-25 — a link to an
    anchor that no longer exists moves the address bar and nothing else,
    which is the exact bug the pointer's own machinery was built to
    stop."""
    b = _fn()
    assert "state.preseason" not in b
    assert "#preseason-board" not in b
    assert "renderPreseason" not in APP, \
        "renderPreseason is back — is the section returning on purpose?"


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


def test_nothing_here_prices_anything():
    """The note says when the board is; it must not grow into a board.
    (Written in the preseason era — "keep it schedule only" — and the
    claim outlives the section that prompted it.)

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
