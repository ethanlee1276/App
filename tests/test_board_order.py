"""What order the Recommended page puts its blocks in, and what that costs.

Ethan's call, 2026-08-08: "We need to show the stadiums and ballparks and
arenas and shit first on the recommended pages." So the venue scroller
moved above the picks.

THE OLD REASON IS STILL TRUE, which is why it is written down here instead
of deleted. The venues used to lead, and were moved below the picks after a
measurement: on an iPhone 13 that order put "Tonight's picks" at 1030px —
1.6 screens below the fold, on the page that gets opened first every day.
Context was rendering ahead of the product.

WHAT CHANGED IS THE JUDGEMENT, NOT THE ARITHMETIC, and the arithmetic is
much kinder now than it was then. The 1030px figure came from 753px of
stacked venue diagrams. The scroller is a single row that scrolls sideways,
so the same decision costs a fraction of what it used to:

    picks start at        before      after       fold
    iPhone 13 (390)        366px      848px        844
    desktop   (1280)       369px      906px        900

The first pick now begins just below the fold on both — one short scroll,
against 1.6 screens. That is the trade, stated so that whoever reads this
next is arguing with a number rather than with a preference.

IF THAT NUMBER GROWS, THIS IS WHERE IT SHOWS UP. Anything added between the
top of the page and the picks pushes them further down, and there is no
longer any slack: at 848px on a phone the picks are already 4px past the
fold. Re-measure with tests/../scratchpad order.py rather than assuming.

Run directly: `python3 tests/test_board_order.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where the picks began, measured 2026-08-08 with the venues on top.
#: Not asserted against a live render — these tests read markup, not pixels
#: — but recorded so the next person has the before/after rather than a
#: claim that it "felt fine".
PICKS_TOP_PHONE, FOLD_PHONE = 848, 844
PICKS_TOP_DESKTOP, FOLD_DESKTOP = 906, 900


def _html():
    with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fh:
        return fh.read()


def _order(html, *ids):
    """Document positions of a list of element ids, in source order."""
    return [html.index(f'id="{i}"') for i in ids]


def test_the_venues_come_before_the_picks():
    """The instruction, in one assertion."""
    html = _html()
    a, b = _order(html, "games-title", "best-bets")
    assert a < b, "the venue scroller is back below the picks"


def test_the_scroller_follows_its_own_heading():
    html = _html()
    a, b = _order(html, "games-title", "games")
    assert a < b


def test_the_summary_tiles_still_lead():
    """RE-DECIDED 2026-08-11 (Ethan's render: "copy it and ship it"):
    the home page opens like the render — stadium strip, then the Top
    Picks strip, THEN tonight's tiles and the performance panels. The
    tiles still sit above the full pick cards, so the count still leads
    the thing it counts."""
    html = _html()
    assert html.index('id="top-picks"') < html.index('class="stats"')
    assert html.index('class="stats"') < html.index('id="home-perf"')
    assert html.index('id="home-perf"') < html.index('id="best-bets"')


def test_the_preseason_stays_under_the_picks():
    """It is a schedule, not a priced board, and it must never outrank
    one."""
    html = _html()
    a, b = _order(html, "best-bets", "preseason-board")
    assert a < b


def test_nothing_new_slipped_in_above_the_picks():
    """THE GUARD THAT MATTERS. At 848px on a phone the picks are already
    4px past the fold, so there is no slack left: one more block above them
    and the thing the page exists for is a full screen down.

    Listed explicitly rather than counted, so adding a block above the
    picks is a decision someone has to make in this file — with the fold
    numbers in the docstring in front of them — instead of a diff nobody
    notices.
    """
    import re
    html = _html()
    picks = html.index('id="best-bets"')
    # Scoped to the Recommended view: the header and every other <section>
    # carry ids too, and counting those measures the whole document rather
    # than the thing above the picks.
    start = html.index('id="view-recommended"')
    # 2026-08-11: top-picks and home-perf joined by Ethan's explicit
    # call — the render's home IS a dashboard above the full board. The
    # picks strip that moved up is itself picks, so the thing the page
    # exists for got closer, not further.
    allowed = {"view-recommended", "probation-note", "talent-note", "stats",
               "games-title", "games", "top-picks", "home-perf",
               # The strip's own chrome (2026-08-11 fidelity pass): the
               # header wrapper with its working controls, and the
               # scroller wrapper with its arrows. Chrome ON the strip,
               # not new content above the picks.
               "games-head", "games-controls", "games-sport", "games-sort",
               "games-mode-strip", "games-mode-grid", "games-outer",
               "games-prev", "games-next",
               # Parlay Mode (2026-08-11): the old Parlay Zone's tickets,
               # hidden unless the sidebar switch is on — zero fold cost
               # in the default state.
               "parlay-mode", "parlays-title", "parlays-sub", "parlays-body"}
    above = [m.group(1) for m in re.finditer(r'id="([\w-]+)"',
                                             html[start:picks])]
    unexpected = [x for x in above if x not in allowed]
    assert not unexpected, (
        f"new block(s) above the picks: {unexpected}. The picks already "
        f"start at {PICKS_TOP_PHONE}px on a {FOLD_PHONE}px phone fold — "
        f"re-measure before adding another.")


def test_the_reason_the_old_order_existed_is_still_recorded():
    """A future reader who only sees "venues first" will move them back the
    next time a phone feels cramped, and re-derive the same 1030px."""
    html = _html()
    i = html.index("VENUES FIRST")
    block = html[i:i + 900]
    assert "1030px" in block
    assert "Ethan" in block


def test_the_measurement_lives_in_this_file():
    doc = " ".join((__doc__ or "").split())
    assert "848px" in doc and "906px" in doc
    assert "1030px" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
