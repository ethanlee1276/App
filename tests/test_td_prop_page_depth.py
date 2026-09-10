"""The touchdown page opened, and four of its rooms were empty.

Ethan, 2026-09-10, once the Most Likely scorers finally reached their
prop page: "It's working, but it's not showing the last five games. or
the shop the price. for the form or how the line is moving today."

Every one was a missing FIELD rather than a broken renderer, and the
renderers say so plainly — each of those four sections is written to draw
nothing when its key is absent:

    logs        `Last N games`            (r.logs)
    form        `Form`                    (r.form)
    all_lines   `Shop the price`          (quotesForSide reads all_lines)
    line_series `How the line moved today`(lineMoveHeadline + r.line_series)

THREE OF THE FOUR WERE ALREADY IN SCOPE and thrown away. `td_watchlist`
had the whole `prop` in hand: it flattened `prop.logs` to twelve bare
numbers for the card's spark and discarded the rest, and never looked at
`prop.lines` at all. So the page could not draw a game log, a form
window, or a single competing quote for a market where shopping the price
matters more than most — an anytime-touchdown line moves 40 cents between
books.

THE FOURTH IS A REACH, not a field. `attach_series` hangs today's tape on
a row, and the build called it on `result["recommendations"]` alone — so
the one section that comes from the tape rather than from the row was
blank on every scorer on both TD lists. It also skips any row whose side
is not OVER or UNDER, which is why the watchlist could not have been
served before it was stamped with one (2b3d598).

The keys are spelled exactly as `pipeline._rec_to_dict` spells them. A
page that reads one shape must not need a second.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.touchdowns import _td_form

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


TD = _src("engine", "touchdowns.py")
BUILD = _src("nfl_build.py")
APP = _src("web", "js", "app.js")


def _watch_row():
    i = TD.index("def td_watchlist(")
    return TD[i:]


# --- the three fields that were in scope and discarded ----------------------
# They are read out of `prop_depth`, which both the watch list and the
# value picks now spread — see `test_the_keys_match_...` for the link.
def test_the_row_carries_the_game_log_not_just_the_spark():
    """`recent_values` is twelve bare numbers for the card's sparkline;
    the page's "Last N games" needs the opponent and the week beside each
    one, which `prop.logs` has and the row was dropping."""
    block = _depth_helper()
    assert '"logs": [{"week": g.week, "opponent": g.opponent,' in block
    assert '"recent_values"' in block, "the card's spark must survive too"


def test_the_row_carries_its_form_windows():
    assert '"form": _td_form(' in _depth_helper()


def test_the_row_carries_every_book_that_quoted_it():
    """Shopping matters more here than almost anywhere — an
    anytime-touchdown price moves 40 cents between books."""
    block = _depth_helper()
    assert '"all_lines": [' in block
    assert '"over_odds": ln.over_odds, "under_odds": ln.under_odds' in block


def test_the_form_windows_are_spelled_the_way_the_page_reads_them():
    """`propFormRows` reads these by name; a helpful rename is a blank
    section."""
    assert set(_td_form([1, 2, 3])) == {
        "last1", "last3", "last5", "last10", "season", "career",
        "vs_opponent"}


def test_the_form_windows_are_the_averages_they_claim_to_be():
    got = _td_form([2, 0, 1, 1, 0, 3, 0])
    assert got["last1"] == 2.0
    assert got["last3"] == 1.0
    assert got["last5"] == 0.8
    assert got["season"] == 1.0


def test_an_empty_log_gives_empty_windows_rather_than_a_zero():
    """A zero average and no games played are different facts, and the
    page prints the second as a dash."""
    assert all(v is None for v in _td_form([]).values())


# --- the fourth: a reach, not a field ---------------------------------------
def test_todays_tape_reaches_both_touchdown_lists():
    i = BUILD.index("_ns = attach_series(")
    call = BUILD[i:i + 320]
    assert 'result.get("long_shots")' in call
    assert 'result.get("longshot_watch")' in call


def test_it_is_the_same_pass_and_not_a_second_read():
    """`_today` is read once above; a second `todays_rows` call for the
    TD rows would double the cost of the block to serve the same tape."""
    i = BUILD.index("_ns = attach_series(")
    call = BUILD[i:i + 320]
    assert call.count("todays_rows(") == 0


# --- the renderers were never the problem -----------------------------------
def test_each_section_draws_nothing_without_its_key():
    """Which is why this reads as four broken rooms rather than one
    error: the page is written to be silent, so a missing field looks
    exactly like a market with nothing to say."""
    i = APP.index("function renderPropPage(")
    page = APP[i:APP.index("\nfunction ", i + 1)]
    assert "${shown ? `<div class=\"section-title\">Last ${shown} game" in page
    assert '${(r.form && Object.keys(r.form).length) ?' in page
    for fn, guard in (("booksTableHTML", 'q.same.length + q.other.length < 2'),
                      ("lineMoveHTML", "if (!h) return \"\";")):
        j = APP.index(f"function {fn}(")
        assert guard in APP[j:APP.index("\n}", j)], fn


def _depth_helper():
    i = TD.index("def prop_depth(")
    return TD[i:TD.index("\ndef ", i + 1)]


def test_the_keys_match_the_ordinary_prop_rows_own_spelling():
    """A page that reads one shape must not need a second.

    The keys moved into `prop_depth` on 2026-09-10, so that the VALUE
    picks could read the same four fields — they had none of them, and a
    scorer the board recommends was therefore not even a door. The watch
    row spreads the helper; the helper is where the spelling lives."""
    pipe = _src("engine", "pipeline.py")
    helper = _depth_helper()
    for key in ('"logs": [', '"form": {', '"all_lines": ['):
        assert key in pipe, f"{key} is not what an ordinary prop publishes"
        assert key.split(":")[0] + ":" in helper, key
    assert "**prop_depth(prop)" in _watch_row(), \
        "the watch row no longer reads the shared helper"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
