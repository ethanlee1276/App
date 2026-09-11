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


SLIP = _fn("slipExportText")
PICKS = _fn("picksExportText")


def test_no_stake_can_enter_either_export():
    """The structural promise: with no stake, no payout is derivable —
    which beats forbidding the WORDS, because a number has no words."""
    for body, who in ((SLIP, "slip"), (PICKS, "picks")):
        for word in ("stake", "units", "risk", "payout", "wager",
                     "bankroll", "toWin", "to_win"):
            assert word not in body.lower(), \
                f"the {who} export reads {word!r} — that is a wager"


def test_neither_export_ships_a_forbidden_phrase():
    for body in (SLIP, PICKS):
        for phrase in ("Place Bet", "place bet", "To Win", "Bet Slip",
                       "Cash Out", "Balance"):
            assert phrase not in body, f"sportsbook cosplay: {phrase!r}"


def test_both_exports_stamp_the_time_the_prices_were_read():
    for body, who in ((SLIP, "slip"), (PICKS, "picks")):
        assert "tzTime(" in body, \
            f"the {who} export copies prices with no clock on them"
        assert "confirm at your book" in body


def test_both_exports_say_the_site_takes_no_bets():
    for body in (SLIP, PICKS):
        assert "does not take bets" in body


def test_the_slip_export_carries_identity_price_and_book():
    for token in ("l.player", "l.market_label", "l.odds", "l.book",
                  "l.matchup"):
        assert token in SLIP, f"the slip export dropped {token}"


def test_the_slip_export_computes_nothing_new():
    """The combined price is the panel's own arithmetic, already on
    screen above the button. Nothing else is derived at copy time."""
    assert "slipAmerican()" in SLIP
    assert "slipImplied" not in SLIP, \
        "the export grew a probability the panel did not show"
    assert not re.search(r"[*/]\s*\d", SLIP), \
        "the export is doing arithmetic of its own"


def test_a_proxy_price_never_leaves_as_a_price():
    """A proxy line is our own recent-form baseline standing in until a
    book posts. Copied into text somebody keys into a sportsbook it
    becomes exactly the fake number the site refuses to print — Ethan,
    2026-08-26: "We should never ever display fake numbers on the site."
    The leg still travels; it is labelled instead of priced."""
    assert '=== "proxy"' in SLIP, "the export cannot tell a proxy apart"
    assert "no book price yet" in SLIP
    # and the combined price refuses to include one
    assert "anyProxy ? null : slipAmerican()" in SLIP, \
        "a product containing a proxy is a made-up number wearing the " \
        "authority of arithmetic"


def test_the_picks_export_copies_the_rows_that_were_drawn():
    """Rebuilding the list from state at click time lets the copy and
    the screen drift apart on a refresh."""
    assert "_picksForCopy = picks;" in APP
    assert "picksExportText(_picksForCopy)" in APP


def test_multi_line_text_is_never_shared_as_a_url():
    """copyRawURL hands a coarse pointer navigator.share({url}) — right
    for a link, and it mangles or refuses a parlay."""
    body = _fn("copyPlainText")
    assert "navigator.share({ text })" in body
    assert "{ url }" not in body
    assert "copyPlainText(slipExportText()" in APP
    assert "copyPlainText(picksExportText(" in APP


def test_the_controls_exist_and_say_what_they_do():
    assert 'id="slip-copy"' in APP and 'id="picks-copy"' in APP
    i = APP.index('id="slip-copy"')
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
