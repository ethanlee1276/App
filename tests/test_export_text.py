"""Bet-slip export — text for YOUR book, never a slip on ours.

Ethan's constraint on this feature (docs/IDEAS.md #4) is absolute and
is the whole shape of the code: *"this site takes no wagers. Not a
slip, not a 'Place Bet', not a balance, no 'To Win' figure. This is
text to copy, and the tests that forbid a betting interface stay
exactly as they are. If that line feels thin, do not build it."*

So what this file pins is mostly what the export MUST NOT contain. The
convenience is small; the line it sits next to is not.

  * NO STAKE ENTERS, so no payout can be derived. That is the
    structural version of the promise, stronger than grepping for the
    words.
  * IT CARRIES A TIMESTAMP. A price copied without one invites somebody
    to key in a number that has since moved.
  * IT SAYS WHOSE BOOK IT IS FOR, in the text itself, because the text
    travels away from the site that produced it.

Run directly: `python3 tests/test_export_text.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
    APP = fh.read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i)]


PICKS = _fn("picksExportText")


def test_the_slips_export_left_with_the_slip():
    """The parlay slip, and its copy-as-text, left on 2026-10-31 (Ethan:
    "get rid of the parlay button and the parlay feature"). The picks'
    export stays, under the same promises."""
    assert "function slipExportText" not in APP and 'id="slip-copy"' not in APP


def test_no_stake_can_enter_the_export():
    """The structural promise: with no stake, no payout is derivable —
    which beats forbidding the WORDS, because a number has no words."""
    for word in ("stake", "units", "risk", "payout", "wager",
                 "bankroll", "toWin", "to_win"):
        assert word not in PICKS.lower(), f"the picks export reads {word!r} — that is a wager"


def test_the_export_ships_no_forbidden_phrase():
    for phrase in ("Place Bet", "place bet", "To Win", "Bet Slip",
                   "Cash Out", "Balance"):
        assert phrase not in PICKS, f"sportsbook cosplay: {phrase!r}"


def test_the_export_stamps_the_time_the_prices_were_read():
    assert "tzTime(" in PICKS, "the picks export copies prices with no clock on them"
    assert "confirm at your book" in PICKS


def test_the_export_says_the_site_takes_no_bets():
    assert "does not take bets" in PICKS


def test_the_picks_export_copies_the_rows_that_were_drawn():
    """Rebuilding the list from state at click time lets the copy and
    the screen drift apart on a refresh."""
    assert "_picksForCopy = picks;" in APP
    assert "picksExportText(_picksForCopy)" in APP


def test_multi_line_text_is_never_shared_as_a_url():
    """copyRawURL hands a coarse pointer navigator.share({url}) — right
    for a link, and it mangles or refuses a list."""
    body = _fn("copyPlainText")
    assert "navigator.share({ text })" in body
    assert "{ url }" not in body
    assert "copyPlainText(picksExportText(" in APP


def test_the_control_exists_and_says_what_it_does():
    assert 'id="picks-copy"' in APP
    i = APP.index('id="picks-copy"')
    assert "key into your own book" in APP[i - 250:i + 250]


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
