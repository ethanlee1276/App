"""A timestamp with no date, on a board that is empty on purpose.

Reported from the real site: MLB showed no picks at 11:17 AM and said the
book prices were "last pulled 3:32 PM". Both halves were true and both read
as broken.

The pull WAS at 3:32 PM — yesterday. The renderer printed the clock time and
dropped the day, so the freshest reading available said something that
cannot happen. And the empty board was the pacer holding its credits for the
pre-game window (2.5h before first pitch, when books actually post hitter
lines), not a model that rejected today's slate — but the empty state said
"every market missed the tier's edge bar", which is a claim about prices
that did not exist yet.

Neither is a data bug. Both are the page describing a working system in the
words of a broken one, which is worse than saying nothing.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
    JS = fh.read()


def _fn(name, end=None):
    start = JS.index(f"function {name}(")
    body = JS[start:]
    return body[:body.index("\n}\n") + 2]


# --- the timestamp ----------------------------------------------------------
def test_a_pull_from_another_day_says_which_day():
    """toLocaleTimeString alone renders yesterday afternoon as "3:32 PM",
    which at 11 AM is not a stale reading — it is an impossible one, and
    the only conclusion a reader can draw is that the feed is lying."""
    fn = _fn("oddsClockHTML")
    assert "yesterday" in fn, "a pull from yesterday still prints bare clock time"
    assert "toLocaleDateString" in fn, "older than yesterday has no date either"
    # The comparison has to be by CALENDAR DAY, not elapsed hours: a pull at
    # 11 PM read at 1 AM is two hours old and still "yesterday".
    assert "setHours(0, 0, 0, 0)" in fn, \
        "day boundaries computed from elapsed time will mislabel a late pull"


def test_the_day_label_is_not_shown_for_today():
    """Every pull inside the window is from today, so stamping a date on it
    would be noise on the common case."""
    fn = _fn("oddsClockHTML")
    assert re.search(r"if \(days <= 0\) return t;", fn), \
        "today's pulls must render as a bare time"


# --- the empty board --------------------------------------------------------
def test_an_empty_board_before_the_window_says_so_instead_of_blaming_the_gates():
    fn = _fn("prePriceHeadline")
    assert "window_opens_at" in fn
    assert "Date.now() >= opens" in fn, \
        "the headline must switch off once the window is actually open"
    assert 'return ""' in fn


def test_the_gate_census_is_labelled_stale_before_the_window():
    """The funnel still renders — hiding it would be its own lie — but the
    counts came from the last pull, so they describe a slate that has
    nothing to do with today."""
    i = JS.index("No qualifying plays at current numbers.")
    block = JS[i - 400:i + 900]
    assert "prePrice" in block, "the empty state ignores the pricing window"
    assert "stale, not as a verdict" in block


def test_the_headline_is_computed_once():
    """Calling it twice inside one render invites the two halves of the same
    card disagreeing if the window opens between them."""
    i = JS.index("const prePrice = prePriceHeadline();")
    tail = JS[i + 40:i + 4000]
    assert "prePriceHeadline()" not in tail, \
        "the headline is recomputed after being captured"


def test_the_explanation_names_the_pacer_and_not_just_the_books():
    """Two different things hold the morning board: the books have not
    posted hitter lines, and our own budgeter is deliberately not spending
    credits yet. A reader who only hears the first will go looking for a
    broken feed on our side."""
    fn = _fn("oddsClockHTML")
    assert "pacer" in fn and "Nothing is broken" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
